"""Offline protocol fixtures. No production credentials or network traffic."""

import hashlib
import hmac
import io
import json
import threading
import unittest
from http.client import IncompleteRead
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from modules.accretion.components.shadowserver_reports.client import ReportsClient
from modules.accretion.components.shadowserver_reports.control import Operation
from modules.accretion.components.shadowserver_reports.errors import (
    AuthenticationError,
    AuthorizationError,
    BudgetExceeded,
    Cancelled,
    ConfigurationError,
    DeadlineExceeded,
    ProtocolError,
    TransportError,
)
from modules.accretion.components.shadowserver_reports.models import (
    Credentials,
    QuerySpec,
    ReportSelection,
)
from modules.accretion.components.shadowserver_reports.transport import SignedTransport


class Response:
    def __init__(self, value=None, *, raw=None, status=200, headers=None):
        self.body = io.BytesIO(json.dumps(value).encode() if raw is None else raw)
        self.status = status
        self.headers = headers or {}
        self.closed = False

    def read(self, count):
        return self.body.read(count)

    read1 = read

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


class Backend:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def transport(*responses, **kwargs):
    backend = Backend(*responses)
    client = SignedTransport(
        lambda: Credentials("fixture-key", "fixture-secret"), backend=backend, **kwargs
    )
    return client, backend


class TransportTests(unittest.TestCase):
    def test_signs_exact_unicode_body_once_and_does_not_mutate_input(self):
        backend = Backend(Response([]))
        client = SignedTransport(lambda: Credentials("fixture-key", "sëcret"), backend=backend)
        payload = {"description": "déjà vu", "n": 4}
        self.assertEqual(client.call("reports/list", payload), [])
        request, timeout = backend.calls[0]
        self.assertEqual(json.loads(request.data), {**payload, "apikey": "fixture-key"})
        self.assertIn("déjà".encode(), request.data)
        expected = hmac.new("sëcret".encode(), request.data, hashlib.sha256).hexdigest()
        self.assertEqual(request.get_header("Hmac2"), expected)
        self.assertNotEqual(
            expected, hmac.new("sëcret".encode(), request.data + b" ", hashlib.sha256).hexdigest()
        )
        self.assertNotIn("apikey", payload)
        self.assertLessEqual(timeout, 20)
        self.assertNotIn("fixture-key", request.full_url)

    def test_constructing_and_closing_transport_do_not_call_network(self):
        client, backend = transport()
        self.assertEqual(backend.calls, [])
        client.close()
        with self.assertRaises(ConfigurationError):
            client.call("test/ping", {})
        self.assertEqual(backend.calls, [])

    def test_only_allowed_read_only_endpoints(self):
        client, backend = transport()
        for endpoint in (
            "filters/update",
            "reports/download",
            "../reports/list",
            "https://other.example/",
        ):
            with self.assertRaises(ConfigurationError):
                client.call(endpoint, {})
        self.assertFalse(backend.calls)

    def test_rejects_caller_key_and_non_json_data(self):
        client, backend = transport()
        for payload in ({"apikey": "other"}, {"bad": float("nan")}, {"bad": object()}):
            with self.assertRaises(ConfigurationError):
                client.call("test/ping", payload)
        self.assertFalse(backend.calls)

    def test_auth_scope_and_redirect_errors_never_retry_or_leak(self):
        for status, error_type in (
            (401, AuthenticationError),
            (403, AuthorizationError),
            (412, AuthorizationError),
            (302, ProtocolError),
        ):
            with self.subTest(status=status):
                error = HTTPError(
                    "https://private.example/fixture-secret",
                    status,
                    "fixture-key",
                    {},
                    io.BytesIO(b"fixture-secret"),
                )
                client, backend = transport(error)
                with self.assertRaises(error_type) as caught:
                    client.call("reports/list", {})
                self.assertEqual(len(backend.calls), 1)
                self.assertNotIn("fixture", str(caught.exception))

    def test_response_status_retry_uses_one_owner_and_same_signed_bytes(self):
        client, backend = transport(
            Response(status=429, headers={"Retry-After": "0"}), Response([])
        )
        self.assertEqual(client.call("reports/list", {}), [])
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(backend.calls[0][0].data, backend.calls[1][0].data)

    def test_network_retries_are_bounded_and_errors_redacted(self):
        client, backend = transport(*[URLError("fixture-secret") for _ in range(3)])
        with patch.object(Operation, "wait"):
            with self.assertRaises(TransportError) as caught:
                client.call("reports/list", {})
        self.assertEqual(len(backend.calls), 3)
        self.assertNotIn("fixture-secret", str(caught.exception))

    def test_retry_after_cannot_exceed_operation_deadline(self):
        client, backend = transport(Response(status=429, headers={"Retry-After": "3600"}))
        with self.assertRaises(DeadlineExceeded):
            client.call("reports/list", {}, operation=Operation(timeout=1))
        self.assertEqual(len(backend.calls), 1)

    def test_request_budget_applies_to_retries(self):
        client, backend = transport(
            Response(status=503, headers={"Retry-After": "0"}), Response([])
        )
        with self.assertRaises(BudgetExceeded):
            client.call("reports/list", {}, operation=Operation(max_requests=1))
        self.assertEqual(len(backend.calls), 1)

    def test_cancellation_before_request_sends_nothing(self):
        event = threading.Event()
        event.set()
        client, backend = transport()
        with self.assertRaises(Cancelled):
            client.call("reports/list", {}, operation=Operation(cancel_event=event))
        self.assertFalse(backend.calls)

    def test_byte_limits_and_response_limits(self):
        client, _ = transport(Response(raw=b"[1,2,3,4]"))
        with self.assertRaises(BudgetExceeded):
            client.call("reports/list", {}, operation=Operation(max_bytes=3))
        client, _ = transport(Response(raw=b"[1,2,3,4]"), max_response_bytes=4)
        with self.assertRaises(ProtocolError):
            client.call("reports/list", {})

    def test_malformed_and_successful_http_error_documents_stop(self):
        for raw in (
            b"<html>error</html>",
            b"{broken",
            b'{"n":NaN}',
            b"\xff",
            b'{"error":"fixture-secret"}',
        ):
            client, backend = transport(Response(raw=raw))
            with self.assertRaises(ProtocolError) as caught:
                client.call("reports/list", {})
            self.assertEqual(len(backend.calls), 1)
            self.assertNotIn("fixture-secret", str(caught.exception))

    def test_provider_error_is_safe(self):
        def provider():
            raise ValueError("fixture-secret")

        client = SignedTransport(provider, backend=Backend())
        with self.assertRaises(ConfigurationError) as caught:
            client.call("test/ping", {})
        self.assertNotIn("fixture", str(caught.exception))

    def test_truncated_http_body_is_safe_and_bounded(self):
        class Broken(Response):
            def read1(self, count):
                raise IncompleteRead(b"fixture-secret", 100)

        client, backend = transport(Broken(), Broken(), Broken())
        with patch.object(Operation, "wait"):
            with self.assertRaises(TransportError) as caught:
                client.call("reports/list", {})
        self.assertEqual(len(backend.calls), 3)
        self.assertNotIn("fixture", str(caught.exception))

    def test_declared_length_truncation_does_not_accept_valid_short_json(self):
        client, backend = transport(
            *[Response(raw=b"[]", headers={"Content-Length": "50"}) for _ in range(3)]
        )
        with patch.object(Operation, "wait"):
            with self.assertRaises(TransportError):
                client.call("reports/list", {})
        self.assertEqual(len(backend.calls), 3)

    def test_invalid_declared_length_stops(self):
        client, backend = transport(Response([], headers={"Content-Length": "-10"}))
        with self.assertRaises(ProtocolError):
            client.call("reports/list", {})
        self.assertEqual(len(backend.calls), 1)

    def test_schema_can_have_a_legitimate_error_column(self):
        schema = {"ip": "string", "error": "string"}
        client, _ = transport(Response(schema))
        self.assertEqual(client.call("reports/schema", {"type": "scan_http_vulnerable"}), schema)


DAY = date(2026, 11, 8)


def report(day="2026-11-08", **extra):
    return {
        "file": f"{day}-scan_http_vulnerable-fixture.csv",
        "id": "fixture-token?opaque",
        "report": "fixture-org",
        "timestamp": day,
        "type": "scan_http_vulnerable",
        "url": "https://www.shadowserver.org/report-description",
        "future": "preserve",
        **extra,
    }


class FakeTransport:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def call(self, endpoint, payload, *, operation=None):
        if operation:
            operation.request()
        self.calls.append((endpoint, payload, operation))
        return self.results.pop(0)


class ClientTests(unittest.TestCase):
    def test_connection_numeric_string_variations_and_no_raw_info_leak(self):
        fake = FakeTransport(
            "pong UTC",
            [
                {
                    "access": ["reports"],
                    "status": "active",
                    "query_count": "12",
                    "query_limit": "0",
                    "apikey": "fixture-key",
                    "user": "private",
                    "domain": "request-ip-only",
                }
            ],
        )
        result = ReportsClient(fake).check_connection()
        self.assertTrue(result["reports_access"])
        self.assertEqual(result["accounts"][0]["query_count"], 12)
        self.assertEqual(result["accounts"][0]["query_limit"], 0)
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("request-ip-only", json.dumps(result))
        self.assertIs(fake.calls[0][2], fake.calls[1][2])

    def test_subscriptions_types_schema_preserve_unknown_fields(self):
        fake = FakeTransport(
            ["fixture-org"],
            [{"type": "scan_http_vulnerable", "future": 7}],
            {"timestamp": "string", "future": {"nested": "unknown"}},
        )
        client = ReportsClient(fake)
        self.assertEqual(client.list_subscriptions(), ["fixture-org"])
        self.assertEqual(client.list_report_types(DAY)[0]["future"], 7)
        self.assertEqual(client.get_schema("scan_http_vulnerable")["future"], {"nested": "unknown"})

    def test_catalog_partitions_days_and_preserves_report_dates(self):
        fake = FakeTransport([report()], [report("2026-11-09")])
        selection = ReportSelection(
            DAY, date(2026, 11, 9), ("fixture-org",), ("scan_http_vulnerable",)
        )
        result = ReportsClient(fake).list_reports(selection)
        self.assertEqual(result.completeness, "complete")
        self.assertEqual([r.report_date for r in result.reports], ["2026-11-08", "2026-11-09"])
        self.assertEqual(fake.calls[0][1]["reports"], ["fixture-org"])
        self.assertEqual(fake.calls[0][1]["types"], ["scan_http_vulnerable"])
        self.assertEqual(result.reports[0].metadata["future"], "preserve")
        self.assertNotIn("fixture-token", json.dumps(result.public_dict()))

    def test_catalog_at_limit_is_explicitly_partial(self):
        fake = FakeTransport([report()])
        result = ReportsClient(fake).list_reports(ReportSelection(DAY, DAY, limit=1))
        self.assertEqual(result.completeness, "partial")
        self.assertEqual(result.reasons, ("catalog_response_at_limit",))

    def test_large_total_budget_keeps_conservative_per_response_cap(self):
        fake = FakeTransport([report(id=f"fixture-{n}") for n in range(1000)])
        result = ReportsClient(fake).list_reports(ReportSelection(DAY, DAY, limit=10000))
        self.assertEqual(fake.calls[0][1]["limit"], 1000)
        self.assertEqual(result.completeness, "partial")

    def test_empty_catalog_is_successful_empty_not_access_failure(self):
        result = ReportsClient(FakeTransport([])).list_reports(ReportSelection(DAY, DAY))
        self.assertEqual(result.completeness, "complete")
        self.assertEqual(result.reports, ())

    def test_server_cannot_silently_broaden_scope(self):
        selection = ReportSelection(DAY, DAY, ("fixture-org",), ("scan_http_vulnerable",))
        for fields in ({"report": "outside"}, {"type": "other"}, {"timestamp": "2026-11-07"}):
            with self.subTest(fields=fields):
                with self.assertRaises(ProtocolError):
                    ReportsClient(FakeTransport([report(**fields)])).list_reports(selection)

    def test_missing_type_only_inferred_for_single_explicit_type(self):
        raw = report()
        del raw["type"]
        client = ReportsClient(FakeTransport([raw]), selector_style="wiki")
        result = client.list_reports(ReportSelection(DAY, DAY, types=("scan_http_vulnerable",)))
        self.assertEqual(result.reports[0].report_type, "scan_http_vulnerable")
        self.assertEqual(client.transport.calls[0][1]["type"], "scan_http_vulnerable")
        with self.assertRaises(ProtocolError):
            ReportsClient(FakeTransport([raw])).list_reports(ReportSelection(DAY, DAY))

    def test_wiki_mode_does_not_fall_back_or_broaden(self):
        fake = FakeTransport()
        with self.assertRaises(ConfigurationError):
            ReportsClient(fake, selector_style="wiki").list_reports(
                ReportSelection(DAY, DAY, types=("one", "two"))
            )
        self.assertFalse(fake.calls)

    def test_query_repeated_pages_stop_without_duplicate_records(self):
        fake = FakeTransport(["geo", "ip"], [{"ip": "192.0.2.1"}], [{"ip": "192.0.2.1"}])
        result = ReportsClient(fake).query_events(QuerySpec(DAY, DAY, {"geo": "us"}, page_size=1))
        self.assertEqual(result.completeness, "partial")
        self.assertEqual(result.reasons, ("repeated_page",))
        self.assertEqual(len(result.records), 1)

    def test_query_short_page_is_unknown_until_live_verified(self):
        fake = FakeTransport(["geo", "ip"], [{"ip": "192.0.2.1"}])
        result = ReportsClient(fake).query_events(QuerySpec(DAY, DAY, {"geo": "us"}))
        self.assertEqual(result.completeness, "unknown")
        self.assertEqual(result.pages, 1)

    def test_query_unsupported_fields_stop_before_data_request(self):
        fake = FakeTransport(["geo", "ip"])
        with self.assertRaises(ConfigurationError):
            ReportsClient(fake).query_events(
                QuerySpec(DAY, DAY, {"geo": "us"}, filters={"unsupported": "x"})
            )
        self.assertEqual(len(fake.calls), 1)

    def test_query_page_budget(self):
        result = ReportsClient(FakeTransport(["geo", "ip"], [{"ip": "192.0.2.1"}])).query_events(
            QuerySpec(DAY, DAY, {"geo": "us"}, page_size=1, max_pages=1)
        )
        self.assertEqual(result.reasons, ("page_limit_reached",))

    def test_query_fixed_server_page_size_with_partial_last_page(self):
        class OffsetTransport:
            def __init__(self):
                self.limits = []

            def call(self, endpoint, payload, *, operation=None):
                if payload.get("help"):
                    return ["geo", "n"]
                limit = payload["limit"]
                self.limits.append(limit)
                offset = (payload["page"] - 1) * limit
                return [{"n": n} for n in range(offset, offset + limit)]

        fake = OffsetTransport()
        result = ReportsClient(fake).query_events(
            QuerySpec(DAY, DAY, {"geo": "us"}, page_size=100, max_records=350)
        )
        self.assertEqual(fake.limits, [100, 100, 100, 100])
        self.assertEqual([r["n"] for r in result.records], list(range(350)))
        self.assertEqual(result.reasons, ("record_limit_reached",))

    def test_query_small_cap_never_changes_server_page_size(self):
        fake = FakeTransport(["geo", "n"], [{"n": n} for n in range(100)])
        result = ReportsClient(fake).query_events(QuerySpec(DAY, DAY, {"geo": "us"}, max_records=3))
        self.assertEqual(fake.calls[1][1]["limit"], 100)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.completeness, "partial")


if __name__ == "__main__":
    unittest.main()
