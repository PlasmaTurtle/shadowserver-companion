from contextlib import closing
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from workbench.shadowserver_reports.control import Operation
from workbench.shadowserver_reports.errors import (
    AuthenticationError,
    ConfigurationError,
    DownloadError,
    StorageError,
)
from workbench.shadowserver_reports.ledger import Ledger
from workbench.shadowserver_reports.models import (
    CatalogResult,
    DownloadReceipt,
    ReportDescriptor,
    ReportSelection,
)
from workbench.shadowserver_reports.sync import sync_once


def report(
    token="SYNTHETIC-CAPABILITY-ONE", filename="2026-11-06-example.csv", subscription="test-list"
):
    return ReportDescriptor(filename, subscription, "scan_http_vulnerable", "2026-11-06", token)


def receipt(item, content=b"timestamp,ip\n2026-11-06,192.0.2.1\n", reused=False):
    digest = hashlib.sha256(content).hexdigest()
    return DownloadReceipt(
        "/synthetic/" + digest + ".csv",
        item.filename,
        item.subscription,
        item.report_type,
        item.report_date,
        "2026-11-08T12:00:00Z",
        len(content),
        digest,
        item.source_fingerprint,
        item.logical_id,
        reused=reused,
    )


class FakeClient:
    def __init__(self, reports=(), completeness="complete", error=None):
        self.result = CatalogResult(tuple(reports), completeness)
        self.error = error
        self.selections = []

    def list_reports(self, selection, *, operation):
        operation.request()
        self.selections.append(selection)
        if self.error:
            raise self.error
        return self.result


class FakeDownloader:
    def __init__(self, *, fail_at=None, error=None, content=None, reused=False, cancel_after=None):
        self.calls = []
        self.fail_at = fail_at
        self.error = error or DownloadError("An invalid download link was returned.")
        self.content = content
        self.reused = reused
        self.cancel_after = cancel_after

    def download_report(self, item, *, operation):
        operation.request()
        self.calls.append(item)
        if self.fail_at == len(self.calls):
            raise self.error
        if self.cancel_after:
            self.cancel_after.set()
        if self.content:
            return receipt(item, self.content, reused=self.reused)
        return receipt(item, reused=self.reused)


class SyncLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sync.sqlite3"
        self.selection = ReportSelection(
            date(2026, 11, 1), date(2026, 11, 8), ("test-list",), ("scan_http_vulnerable",)
        )
        self.ledger = Ledger(self.path)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def rows(self, table):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM " + table)]

    def test_success_checkpoint_and_receipt_without_capabilities(self):
        item = report()
        result = sync_once(FakeClient([item]), FakeDownloader(), self.ledger, self.selection)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.checkpoint, "2026-11-08")
        self.assertEqual((result.downloaded, result.reused, result.failed), (1, 0, 0))
        self.assertEqual(self.rows("attempts")[0]["status"], "complete")
        self.assertNotIn(item.download_id.encode(), self.path.read_bytes())
        self.assertNotIn(item.download_id, str(result.public_dict()))

    def test_changed_token_same_content_retains_provenance_not_revision(self):
        first, rotated = report(), report(token="SYNTHETIC-CAPABILITY-ROTATED")
        sync_once(FakeClient([first]), FakeDownloader(), self.ledger, self.selection)
        downloader = FakeDownloader(reused=True)
        result = sync_once(FakeClient([rotated]), downloader, self.ledger, self.selection)
        self.assertEqual(len(downloader.calls), 1)
        self.assertEqual(result.reused, 1)
        self.assertEqual(self.ledger.statistics()["revisions"], 1)
        observations = self.rows("observations")
        self.assertEqual(len(observations), 2)
        self.assertEqual(len({r["source_fingerprint"] for r in observations}), 2)

    def test_reacquisition_receipt_preserves_new_local_location(self):
        item = report()
        first = receipt(item)
        second = replace(first, path="/synthetic/new-location.csv", reused=True)
        self.ledger.record_receipt(first)
        self.ledger.record_receipt(second)
        observations = self.rows("observations")
        self.assertEqual(
            {json.loads(row["receipt_json"])["path"] for row in observations},
            {first.path, second.path},
        )
        self.assertEqual(self.ledger.statistics()["revisions"], 1)

    def test_same_token_changed_content_preserves_revision(self):
        item = report()
        sync_once(FakeClient([item]), FakeDownloader(), self.ledger, self.selection)
        sync_once(
            FakeClient([item]),
            FakeDownloader(content=b"ip\n192.0.2.2\n"),
            self.ledger,
            self.selection,
        )
        revisions = self.ledger.revisions(item.logical_id)
        self.assertEqual(len(revisions), 2)
        self.assertNotEqual(revisions[0]["sha256"], revisions[1]["sha256"])

    def test_same_bytes_different_subscriptions_keep_both_sources(self):
        items = [report(), report(subscription="another-list")]
        result = sync_once(FakeClient(items), FakeDownloader(), self.ledger, self.selection)
        self.assertEqual(result.downloaded, 2)
        self.assertEqual(self.ledger.statistics()["revisions"], 2)
        self.assertEqual(len({r["sha256"] for r in self.rows("revisions")}), 1)

    def test_partial_and_unknown_catalog_never_checkpoint(self):
        for completeness in ("partial", "unknown"):
            result = sync_once(
                FakeClient([report()], completeness), FakeDownloader(), self.ledger, self.selection
            )
            self.assertEqual(result.status, "partial")
            self.assertEqual(result.downloaded, 1)
            self.assertIsNone(result.checkpoint)
        self.assertEqual(self.ledger.statistics()["checkpoints"], 0)

    def test_invalid_link_stops_before_next_download_and_restart_rechecks(self):
        items = [report(filename=f"report-{n}.csv") for n in range(3)]
        first = FakeDownloader(fail_at=2)
        result = sync_once(FakeClient(items), first, self.ledger, self.selection)
        self.assertEqual(len(first.calls), 2)
        self.assertEqual((result.downloaded, result.failed), (1, 1))
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.checkpoint)
        second = FakeDownloader(reused=True)
        result = sync_once(FakeClient(items), second, self.ledger, self.selection)
        self.assertEqual(len(second.calls), 3)
        self.assertEqual(result.status, "complete")
        self.assertEqual(self.ledger.statistics()["revisions"], 3)

    def test_cancel_after_download_commits_receipt_without_checkpoint(self):
        cancelled = threading.Event()
        result = sync_once(
            FakeClient([report()]),
            FakeDownloader(cancel_after=cancelled),
            self.ledger,
            self.selection,
            operation=Operation(cancel_event=cancelled),
        )
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.downloaded, 1)
        self.assertEqual(self.ledger.statistics()["observations"], 1)
        self.assertIsNone(result.checkpoint)

    def test_pre_cancelled_operation_does_not_call_client(self):
        event = threading.Event()
        event.set()
        client = FakeClient([report()])
        result = sync_once(
            client,
            FakeDownloader(),
            self.ledger,
            self.selection,
            operation=Operation(cancel_event=event),
        )
        self.assertEqual(result.status, "cancelled")
        self.assertFalse(client.selections)
        self.assertEqual(self.ledger.statistics()["attempts"], 0)

    def test_shared_request_budget_stops_run(self):
        downloader = FakeDownloader()
        result = sync_once(
            FakeClient([report()]),
            downloader,
            self.ledger,
            self.selection,
            operation=Operation(max_requests=1),
        )
        self.assertEqual(result.status, "partial")
        self.assertIn("budget_exceeded", result.reasons)
        self.assertEqual(result.failed, 1)
        self.assertFalse(downloader.calls)

    def test_authentication_error_safe_in_result_and_database(self):
        secret = "SYNTHETIC-SECRET-DO-NOT-LOG"
        result = sync_once(
            FakeClient(error=AuthenticationError(secret)),
            FakeDownloader(),
            self.ledger,
            self.selection,
        )
        self.assertEqual(result.reasons, ("authentication_error",))
        self.assertNotIn(secret, str(result))
        self.assertNotIn(secret.encode(), self.path.read_bytes())

    def test_lookback_preserves_late_report_recheck(self):
        sync_once(FakeClient(), FakeDownloader(), self.ledger, self.selection)
        client = FakeClient([report()])
        extended = replace(self.selection, end=date(2026, 11, 9))
        result = sync_once(client, FakeDownloader(), self.ledger, extended)
        self.assertEqual(client.selections[0].start, date(2026, 11, 7))
        self.assertEqual(client.selections[0].end, date(2026, 11, 9))
        self.assertEqual(result.checkpoint, "2026-11-09")

    def test_backfill_start_does_not_inherit_checkpoint(self):
        sync_once(FakeClient(), FakeDownloader(), self.ledger, self.selection)
        backfill = replace(self.selection, start=date(2026, 10, 1))
        client = FakeClient()
        sync_once(client, FakeDownloader(), self.ledger, backfill)
        self.assertEqual(client.selections[0].start, date(2026, 10, 1))

    def test_historical_end_never_regresses_checkpoint(self):
        sync_once(FakeClient(), FakeDownloader(), self.ledger, self.selection)
        historical = replace(self.selection, end=date(2026, 11, 3))
        client = FakeClient()
        result = sync_once(client, FakeDownloader(), self.ledger, historical)
        self.assertEqual(client.selections[0].start, self.selection.start)
        self.assertEqual(result.checkpoint, "2026-11-08")

    def test_profiles_isolate_history_and_checkpoints(self):
        sync_once(FakeClient([report()]), FakeDownloader(), self.ledger, self.selection)
        with Ledger(self.path, profile="another-account") as second:
            self.assertIsNone(second.get_checkpoint(self.selection))
            self.assertEqual(second.statistics()["observations"], 0)
            sync_once(FakeClient([report()]), FakeDownloader(), second, self.selection)
            self.assertEqual(second.statistics()["observations"], 1)
        self.assertEqual(self.ledger.statistics()["observations"], 1)

    def test_interrupted_run_remains_visible_and_new_run_recovers(self):
        run_id = self.ledger.begin_run(self.selection)
        self.ledger.begin_attempt(report(), run_id)
        self.ledger.close()
        self.ledger = Ledger(self.path)
        result = sync_once(FakeClient([report()]), FakeDownloader(), self.ledger, self.selection)
        self.assertEqual(result.status, "complete")
        self.assertEqual({r["status"] for r in self.rows("runs")}, {"running", "complete"})
        self.assertEqual(len(self.rows("observations")), 1)

    def test_checkpoint_refuses_unfinished_attempt(self):
        run_id = self.ledger.begin_run(self.selection)
        self.ledger.begin_attempt(report(), run_id)
        with self.assertRaises(StorageError):
            self.ledger.complete_run(run_id, self.selection)
        self.assertIsNone(self.ledger.get_checkpoint(self.selection))
        self.assertEqual(self.rows("runs")[0]["status"], "running")

    def test_receipt_must_match_attempt_and_transaction_rolls_back(self):
        run_id = self.ledger.begin_run(self.selection)
        attempt = self.ledger.begin_attempt(report(), run_id)
        with self.assertRaises(StorageError):
            self.ledger.record_receipt(receipt(report(token="different")), attempt)
        self.assertEqual(self.ledger.statistics()["revisions"], 0)
        self.assertEqual(self.ledger.statistics()["observations"], 0)

    def test_duplicate_catalog_entry_only_downloaded_once(self):
        item = report()
        downloader = FakeDownloader()
        result = sync_once(FakeClient([item, item]), downloader, self.ledger, self.selection)
        self.assertEqual(len(downloader.calls), 1)
        self.assertEqual(result.downloaded, 1)

    def test_bad_ledger_and_configuration_fail_safely(self):
        for invalid in ("", "../../profile", "private profile", "A" * 81):
            with self.assertRaises(ConfigurationError):
                Ledger(self.path, invalid)
        for days in (0, -1, 367, True, "two"):
            with self.assertRaises(ConfigurationError):
                sync_once(
                    FakeClient(), FakeDownloader(), self.ledger, self.selection, lookback_days=days
                )
        bad = Path(self.tmp.name) / "broken.sqlite3"
        bad.write_bytes(b"synthetic private bytes not a database")
        with self.assertRaisesRegex(StorageError, "Unable to open synchronization ledger"):
            Ledger(bad)


if __name__ == "__main__":
    unittest.main()
