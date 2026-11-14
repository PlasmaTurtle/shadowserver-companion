import contextlib
import ctypes
from datetime import date
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workbench.shadowserver_reports import cli
from workbench.shadowserver_reports.credentials import (
    EnvCredentialProvider,
    WindowsCredentialProvider,
    _CREDENTIALW,
    _WindowsCredentialStore,
)
from workbench.shadowserver_reports.errors import ConfigurationError, DownloadError
from workbench.shadowserver_reports.models import (
    CatalogResult,
    Credentials,
    DownloadReceipt,
    QueryResult,
    ReportDescriptor,
)


class MemoryCredentialStore:
    def __init__(self):
        self.items = {}

    def read(self, target):
        if target not in self.items:
            raise ConfigurationError("Missing credentials.")
        return self.items[target]

    def write(self, target, payload):
        self.items[target] = payload

    def delete(self, target):
        return self.items.pop(target, None) is not None


class CredentialsTests(unittest.TestCase):
    def test_env_is_lazy_and_does_not_persist(self):
        env = {}
        provider = EnvCredentialProvider(environ=env)
        with self.assertRaises(ConfigurationError):
            provider()
        env.update(SHADOWSERVER_API_KEY="synthetic-key", SHADOWSERVER_API_SECRET="synthetic-secret")
        self.assertEqual(provider().secret, "synthetic-secret")
        self.assertNotIn("synthetic", repr(provider()))
        env.clear()
        with self.assertRaises(ConfigurationError):
            provider()

    def test_unicode_store_round_trip_and_isolation(self):
        store = MemoryCredentialStore()
        first = WindowsCredentialProvider("first", _store=store)
        second = WindowsCredentialProvider("second", _store=store)
        first.store(Credentials("synthetic-key", "synthetic-sécret"))
        self.assertEqual(first().secret, "synthetic-sécret")
        with self.assertRaises(ConfigurationError):
            second()
        second.store(Credentials("key-2", "secret-2"))
        self.assertTrue(first.delete())
        self.assertFalse(first.delete())
        self.assertEqual(second().api_key, "key-2")

    def test_bad_profiles_and_corrupt_store(self):
        for value in ("../bad", "", "space here", "x" * 65, "bad\x00name"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                WindowsCredentialProvider(value)
        store = MemoryCredentialStore()
        provider = WindowsCredentialProvider(_store=store)
        for data in (
            b"not-json",
            b"[]",
            b'{"version":2}',
            b'{"version":1,"api_key":"hidden","secret":null}',
            b"\xff",
        ):
            store.write(provider.target, data)
            with self.assertRaises(ConfigurationError) as ctx:
                provider()
            self.assertNotIn("hidden", str(ctx.exception))

    def test_fixed_windows_record_layout(self):
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(ctypes.sizeof(_CREDENTIALW), 80)
            self.assertEqual(_CREDENTIALW.CredentialBlob.offset, 40)
            self.assertEqual(_CREDENTIALW.Attributes.offset, 56)

    def test_native_write_contract_uses_generic_current_user_record(self):
        captured = {}

        class NativeApi:
            def CredWriteW(self, pointer, flags):
                record = ctypes.cast(pointer, ctypes.POINTER(_CREDENTIALW)).contents
                captured.update(
                    target=record.TargetName,
                    kind=record.Type,
                    persist=record.Persist,
                    username=record.UserName,
                    flags=flags,
                    payload=ctypes.string_at(record.CredentialBlob, record.CredentialBlobSize),
                )
                return True

        store = _WindowsCredentialStore.__new__(_WindowsCredentialStore)
        store._api = NativeApi()
        store.write("ShadowserverReports/testing", b"synthetic-payload")
        self.assertEqual(captured["kind"], 1)
        self.assertEqual(captured["persist"], 2)
        self.assertEqual(captured["flags"], 0)
        self.assertEqual(captured["payload"], b"synthetic-payload")
        self.assertNotIn("synthetic", captured["username"])

    def test_native_read_releases_os_record_on_validation_error(self):
        record = _CREDENTIALW()
        record.CredentialBlobSize = 3000
        native_buffer = (ctypes.c_ubyte * 1)(42)
        record.CredentialBlob = ctypes.cast(native_buffer, ctypes.POINTER(ctypes.c_ubyte))
        freed = []

        class NativeApi:
            def CredReadW(self, target, kind, flags, output):
                ctypes.cast(output, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)))[0] = (
                    ctypes.pointer(record)
                )
                return True

            def CredFree(self, pointer):
                freed.append(True)

        store = _WindowsCredentialStore.__new__(_WindowsCredentialStore)
        store._api = NativeApi()
        with self.assertRaises(ConfigurationError):
            store.read("ShadowserverReports/testing")
        self.assertEqual(freed, [True])

    @unittest.skipIf(os.name == "nt", "This check covers the non-Windows error only.")
    def test_non_windows_adapter_fails_clearly(self):
        with self.assertRaises(ConfigurationError) as ctx:
            WindowsCredentialProvider()()
        self.assertIn("only on Windows", str(ctx.exception))


class CliTests(unittest.TestCase):
    selection = [
        "--start",
        "2026-11-07",
        "--end",
        "2026-11-07",
        "--subscription",
        "example",
        "--type",
        "scan_http_vulnerable",
    ]

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_missing_selector_and_accidental_secret_are_not_echoed(self):
        code, out, err = self.invoke(["list", "--start", "2026-11-07", "--end", "2026-11-07"])
        self.assertEqual(code, 1)
        self.assertFalse(out)
        self.assertEqual(json.loads(err)["error"]["code"], "configuration_error")
        code, out, err = self.invoke(["--api-key", "accidental-secret", "connection"])
        self.assertEqual(code, 1)
        self.assertNotIn("accidental-secret", out + err)

    def test_selectors_explicit_all_and_repeated(self):
        args = cli.build_parser().parse_args(
            [
                "list",
                "--start",
                "2026-11-07",
                "--end",
                "2026-11-08",
                "--all-subscriptions",
                "--all-types",
            ]
        )
        self.assertEqual(cli._selection(args).subscriptions, ())
        args = cli.build_parser().parse_args(
            ["list"] + self.selection + ["--subscription", "example2"]
        )
        self.assertEqual(cli._selection(args).subscriptions, ("example", "example2"))

    def test_bad_dates_and_nonfinite_budgets(self):
        for args in (
            ["--timeout", "nan", "connection"],
            ["--max-requests", "0", "connection"],
            ["list"] + self.selection[:1] + ["20261107"] + self.selection[2:],
        ):
            with self.subTest(args=args):
                code, out, err = self.invoke(args)
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(err)["error"]["code"], "configuration_error")

    def test_query_file_rejects_duplicate_keys_nan_large_and_wrong_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "input.json"
            for data in ('{"geo":"US","geo":"CH"}', '{"x":NaN}', "[]", '"' + "x" * 65536 + '"'):
                file.write_text(data)
                with self.assertRaises(ConfigurationError):
                    cli._json_file(file)
            file.write_text('{"geo":"US"}')
            self.assertEqual(cli._json_file(file), {"geo": "US"})

    def test_public_catalog_never_contains_download_capability(self):
        report = ReportDescriptor(
            "report.csv",
            "example",
            "scan_http_vulnerable",
            "2026-11-07",
            "synthetic-capability?do-not-print",
            {"id": "synthetic-capability?do-not-print"},
        )
        with patch(
            "workbench.shadowserver_reports.client.ReportsClient.list_reports",
            return_value=CatalogResult((report,), "complete"),
        ):
            code, out, err = self.invoke(["list"] + self.selection)
        self.assertEqual(code, 0, err)
        self.assertNotIn("do-not-print", out + err)
        self.assertEqual(json.loads(out)["reports"][0]["filename"], "report.csv")

    def test_partial_catalog_returns_nonzero_with_results(self):
        with patch(
            "workbench.shadowserver_reports.client.ReportsClient.list_reports",
            return_value=CatalogResult((), "partial", ("limit_reached",)),
        ):
            code, out, err = self.invoke(["list"] + self.selection)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["completeness"], "partial")

    def test_connection_without_reports_access_is_nonzero(self):
        with patch(
            "workbench.shadowserver_reports.client.ReportsClient.check_connection",
            return_value={"connected": True, "reports_access": False},
        ):
            code, out, err = self.invoke(["connection"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["reports_access"])

    def test_download_stops_after_first_failure(self):
        report = ReportDescriptor(
            "report.csv", "example", "scan_http_vulnerable", "2026-11-07", "synthetic-capability"
        )
        with (
            tempfile.TemporaryDirectory() as temp,
            patch(
                "workbench.shadowserver_reports.client.ReportsClient.list_reports",
                return_value=CatalogResult((report, report), "complete"),
            ),
            patch(
                "workbench.shadowserver_reports.download.ReportDownloader.download_report",
                side_effect=DownloadError("Download denied."),
            ) as method,
        ):
            code, out, err = self.invoke(["download"] + self.selection + ["--output", temp])
        self.assertEqual(code, 2)
        self.assertEqual(method.call_count, 1)
        self.assertEqual(json.loads(out)["status"], "partial")

    def test_query_unknown_completeness_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            scope = Path(temp) / "scope.json"
            scope.write_text('{"geo":"US"}')
            with patch(
                "workbench.shadowserver_reports.client.ReportsClient.query_events",
                return_value=QueryResult(({"ip": "192.0.2.1"},), "unknown", 1),
            ):
                code, out, err = self.invoke(
                    [
                        "query",
                        "--start",
                        "2026-11-07",
                        "--end",
                        "2026-11-07",
                        "--scope-json",
                        str(scope),
                    ]
                )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["kind"], "event_query")

    def test_keyboard_interrupt_and_unexpected_error_safe(self):
        with patch.object(cli, "_run", side_effect=KeyboardInterrupt):
            code, out, err = self.invoke(["connection"])
        self.assertEqual(code, 130)
        self.assertEqual(json.loads(err)["error"]["code"], "cancelled")
        with patch.object(cli, "_run", side_effect=RuntimeError("do-not-leak")):
            code, out, err = self.invoke(["connection"])
        self.assertEqual(code, 1)
        self.assertNotIn("do-not-leak", out + err)

    def test_configure_uses_hidden_prompt_and_no_credentials_output(self):
        store = MemoryCredentialStore()
        with (
            patch(
                "workbench.shadowserver_reports.credentials._WindowsCredentialStore",
                return_value=store,
            ),
            patch("sys.stdin.isatty", return_value=True),
            patch.object(cli.getpass, "getpass", side_effect=["synthetic-key", "synthetic-secret"]),
        ):
            code, out, err = self.invoke(["configure"])
        self.assertEqual(code, 0, err)
        self.assertNotIn("synthetic", out + err)
        self.assertEqual(json.loads(out)["status"], "configured")
        self.assertEqual(len(store.items), 1)

    def test_configure_will_not_fall_back_to_visible_input(self):
        with (
            patch(
                "workbench.shadowserver_reports.credentials._WindowsCredentialStore",
                return_value=MemoryCredentialStore(),
            ),
            patch("sys.stdin.isatty", return_value=False),
            patch.object(cli.getpass, "getpass") as getpass,
        ):
            code, out, err = self.invoke(["configure"])
        self.assertEqual(code, 1)
        getpass.assert_not_called()


if __name__ == "__main__":
    unittest.main()
