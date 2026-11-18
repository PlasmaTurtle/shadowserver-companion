"""One bounded pull; scheduling and application import remain external."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from .control import Operation
from .errors import Cancelled, ConfigurationError, ShadowserverError, StorageError
from .ledger import Ledger
from .models import DownloadReceipt, ReportSelection, SyncResult


def sync_once(client: Any, downloader: Any, ledger: Ledger,
              selection: ReportSelection, *, operation: Operation | None = None,
              lookback_days: int = 2) -> SyncResult:
    """Recheck a catalog window, preserve files, and checkpoint a complete scan.

    No download is skipped just because its token or filename was seen before.
    The downloader compares content hashes, which preserves corrections and
    recovers from an interrupted prior run. On the first operational failure the
    run stops: retries belong solely to the network layer, and repeated bad
    download attempts can trigger upstream blocking.

    A checkpoint is a *scan* watermark. The recent window is always scanned again
    because late publication is possible. Increase lookback or use a new earlier
    start date for a backfill; no fixed retention/delivery guarantee is assumed.
    """
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or not 1 <= lookback_days <= 366:
        raise ConfigurationError("lookback_days must be between 1 and 366.")
    op = operation or Operation()
    previous = ledger.get_checkpoint(selection)
    effective = selection
    if previous:
        try:
            lower = date.fromisoformat(previous) - timedelta(days=lookback_days - 1)
        except ValueError:
            raise StorageError("Synchronization checkpoint date is invalid.") from None
        if lower <= selection.end:
            effective = replace(selection, start=max(selection.start, lower))
    run_id = ledger.begin_run(selection, effective)
    receipts: list[DownloadReceipt] = []
    downloaded = reused = failed = 0
    active_attempt = None
    reasons: list[str] = []
    try:
        op.check()
        catalog = client.list_reports(effective, operation=op)
        if catalog.completeness != "complete":
            reasons.append("partial_catalog" if catalog.completeness == "partial" else "unknown_catalog")
        # Preserve safe, fixed module reason codes without copying remote data.
        for reason in catalog.reasons:
            safe = Ledger._safe_code(reason)
            if safe != "operation_failed" and safe not in reasons:
                reasons.append(safe)
        seen = set()
        for report in catalog.reports:
            op.check()
            identity = (report.logical_id, report.source_fingerprint)
            if identity in seen:
                continue  # One response may repeat the exact same catalog record.
            seen.add(identity)
            active_attempt = ledger.begin_attempt(report, run_id)
            receipt = downloader.download_report(report, operation=op)
            ledger.record_receipt(receipt, active_attempt)
            active_attempt = None
            receipts.append(receipt)
            if receipt.reused:
                reused += 1
            else:
                downloaded += 1
        op.check()
        if catalog.completeness == "complete":
            checkpoint = ledger.complete_run(run_id, selection)
            return SyncResult("complete", downloaded, reused, 0, tuple(receipts), checkpoint, ())
        ledger.finish_run(run_id, "partial", reasons[0])
        return SyncResult("partial", downloaded, reused, 0, tuple(receipts), previous, tuple(reasons))
    except (ShadowserverError, OSError, KeyboardInterrupt) as exc:
        is_cancelled = isinstance(exc, (Cancelled, KeyboardInterrupt))
        code = ("cancelled" if is_cancelled else
                Ledger._safe_code(getattr(exc, "code", "storage_error")))
        status = "cancelled" if is_cancelled else "partial"
        if active_attempt is not None:
            failed += 1
            try:
                ledger.fail_attempt(active_attempt, code)
            except StorageError:
                reasons.append("storage_error")
        try:
            ledger.finish_run(run_id, status, code)
        except StorageError:
            # Persisted running attempts remain evidence of an interruption.
            reasons.append("storage_error")
        if code not in reasons:
            reasons.append(code)
        return SyncResult(status, downloaded, reused, failed, tuple(receipts), previous, tuple(reasons))
