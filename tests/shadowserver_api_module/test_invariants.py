"""Independent invariants for the shared public data and operation boundary."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta
import json
import threading
import unittest
from unittest.mock import patch

from workbench.shadowserver_reports.control import Operation
from workbench.shadowserver_reports.errors import (
    BudgetExceeded,
    Cancelled,
    ConfigurationError,
    DeadlineExceeded,
)
from workbench.shadowserver_reports.models import (
    CatalogResult,
    Credentials,
    QuerySpec,
    ReportDescriptor,
    ReportSelection,
)


DAY = date(2026, 11, 8)


class ModelInvariantTests(unittest.TestCase):
    def test_credentials_redacted_and_invalid_values_not_echoed(self):
        credentials = Credentials("sensitive-key-sentinel", "sensitive-secret-sentinel")
        self.assertNotIn("sentinel", repr(credentials))
        self.assertNotIn("sentinel", str(credentials))
        with self.assertRaises(FrozenInstanceError):
            credentials.api_key = "changed"
        for key, secret in ((None, "secret"), ("key", None), ("", "secret"), ("key", " ")):
            with self.subTest(key=key, secret=secret), self.assertRaises(ConfigurationError):
                Credentials(key, secret)

    def test_catalog_public_form_and_repr_exclude_capabilities(self):
        report = ReportDescriptor(
            "report.csv",
            "subscription",
            "scan_http_vulnerable",
            "2026-11-08",
            "opaque?capability-sentinel",
            {"unknown": "private-sentinel"},
        )
        result = CatalogResult((report,), "complete")
        for public in (repr(report), repr(result), json.dumps(result.public_dict())):
            self.assertNotIn("capability-sentinel", public)
            self.assertNotIn("private-sentinel", public)
        self.assertEqual(len(report.source_fingerprint), 64)

    def test_logical_identity_not_refreshed_token_but_tracks_provenance(self):
        common = ("report.csv", "subscription", "scan_http_vulnerable", "2026-11-08")
        a, b = ReportDescriptor(*common, "token1"), ReportDescriptor(*common, "token2")
        self.assertEqual(a.logical_id, b.logical_id)
        self.assertNotEqual(a.source_fingerprint, b.source_fingerprint)
        c = ReportDescriptor("report.csv", "another-subscription", common[2], common[3], "token1")
        self.assertNotEqual(a.logical_id, c.logical_id)

    def test_date_bounds_and_selector_snapshot(self):
        subscriptions = ["first", "first", "second"]
        selection = ReportSelection(DAY, DAY + timedelta(days=365), subscriptions)
        subscriptions.append("third")
        self.assertEqual(selection.subscriptions, ("first", "second"))
        for start, end in (
            (DAY, DAY - timedelta(days=1)),
            (DAY, DAY + timedelta(days=366)),
            (datetime(2026, 11, 8), DAY),
            ("2026-11-08", DAY),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(ConfigurationError):
                ReportSelection(start, end)
        for invalid in (0, -1, True, 10001, "1000"):
            with self.subTest(limit=invalid), self.assertRaises(ConfigurationError):
                ReportSelection(DAY, DAY, limit=invalid)
        with self.assertRaises(ConfigurationError):
            ReportSelection(DAY, DAY, subscriptions="subscription")

    def test_query_copies_caller_fields_and_requires_nonoverlapping_scope(self):
        scope, filters = {"geo": "US"}, {"tag": ["cve-one"]}
        spec = QuerySpec(DAY, DAY, scope, filters)
        scope["geo"] = "FR"
        filters["tag"].append("cve-two")
        self.assertEqual(spec.scope, {"geo": "US"})
        self.assertEqual(spec.filters, {"tag": ["cve-one"]})
        for invalid in ({}, {"county": "test"}, {"geo": ""}, {"asn": True}, {"ip": None}):
            with self.subTest(scope=invalid), self.assertRaises(ConfigurationError):
                QuerySpec(DAY, DAY, invalid)
        with self.assertRaises(ConfigurationError):
            QuerySpec(DAY, DAY, {"geo": "US"}, {"geo": "FR"})
        for invalid in (float("nan"), object()):
            with self.subTest(value=invalid), self.assertRaises(ConfigurationError):
                QuerySpec(DAY, DAY, {"geo": "US"}, {"bad": invalid})


class OperationInvariantTests(unittest.TestCase):
    def test_exact_request_and_byte_boundaries_do_not_overcount_failure(self):
        op = Operation(max_requests=2, max_bytes=4)
        op.request()
        op.request()
        with self.assertRaises(BudgetExceeded):
            op.request()
        self.assertEqual(op.requests, 2)
        op.consume_bytes(4)
        op.consume_bytes(0)
        with self.assertRaises(BudgetExceeded):
            op.consume_bytes(1)
        self.assertEqual(op.bytes_received, 4)
        with self.assertRaises(ConfigurationError):
            op.consume_bytes(-1)
        with self.assertRaises(ConfigurationError):
            op.consume_bytes(True)

    def test_budget_counts_are_thread_safe(self):
        op = Operation(max_requests=10)

        def reserve(_):
            try:
                op.request()
                return True
            except BudgetExceeded:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(100)))
        self.assertEqual(sum(results), 10)
        self.assertEqual(op.requests, 10)

    def test_cancel_is_shared_and_has_priority(self):
        event = threading.Event()
        op = Operation(cancel_event=event)
        event.set()
        for call in (
            op.check,
            op.remaining,
            op.request,
            lambda: op.consume_bytes(1),
            lambda: op.wait(0),
        ):
            with self.assertRaises(Cancelled):
                call()
        self.assertEqual(op.requests, 0)
        self.assertEqual(op.bytes_received, 0)

    def test_deadline_and_retry_delay_fail_without_sleeping(self):
        with patch("workbench.shadowserver_reports.control.time.monotonic", return_value=100):
            op = Operation(timeout=10)
        with patch("workbench.shadowserver_reports.control.time.monotonic", return_value=109):
            self.assertEqual(op.remaining(), 1)
            with self.assertRaises(DeadlineExceeded):
                op.wait(2)
        with patch("workbench.shadowserver_reports.control.time.monotonic", return_value=110):
            with self.assertRaises(DeadlineExceeded):
                op.check()

    def test_invalid_numeric_configuration(self):
        for invalid in (0, -1, float("inf"), float("nan"), "5"):
            with self.subTest(timeout=invalid), self.assertRaises(ConfigurationError):
                Operation(timeout=invalid)
        for name in ("max_requests", "max_bytes"):
            for value in (0, -1, True, 1.5):
                with self.subTest(name=name, value=value), self.assertRaises(ConfigurationError):
                    Operation(**{name: value})


if __name__ == "__main__":
    unittest.main()
