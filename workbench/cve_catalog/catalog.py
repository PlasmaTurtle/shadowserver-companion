"""Resumable full NVD import and transactionally checkpointed daily API updates."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import time

from .storage import CatalogStorage, date, stamp
from .streaming import records
from .content_validation import validated_gzip_chunks, verify_gzip_prefix
from ..aegis.json import strict_json_loads
from .transport import FEED_BASE, NVDTransport, CatalogDeferred, cancelled, retry_nvd

MAX_COMPRESSED = 256 * 1024 * 1024
MAX_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
_locks_guard = threading.Lock()
_locks = {}


class BulkPaginationChanged(CatalogDeferred):
    def __init__(self):
        super().__init__(
            "NVD bulk pagination changed. Saved records remain available; the next download will restart its page check.",
            300,
        )


def parse_meta(body):
    try:
        fields = dict(
            line.split(":", 1) for line in body.decode("utf-8-sig").splitlines() if ":" in line
        )
        fields = {k.strip(): v.strip() for k, v in fields.items()}
        size, compressed = int(fields["size"]), int(fields["gzSize"])
        digest = fields["sha256"].lower()
        modified = stamp(date(fields["lastModifiedDate"]))
    except (ValueError, KeyError, UnicodeError) as error:
        raise ValueError("Invalid NVD feed metadata") from error
    if (
        not 1 <= size <= MAX_UNCOMPRESSED
        or not 1 <= compressed <= MAX_COMPRESSED
        or not re.fullmatch(r"[a-f0-9]{64}", digest)
    ):
        raise ValueError("NVD feed exceeds supported limits or has an invalid checksum")
    return {"size": size, "gzSize": compressed, "sha256": digest, "lastModifiedDate": modified}


@contextmanager
def sync_lock(folder):
    with _locks_guard:
        lock = _locks.setdefault(str(folder), threading.Lock())
    if not lock.acquire(blocking=False):
        raise ValueError("A catalog update is already running")
    handle = None
    try:
        handle = (folder / "sync.lock").open("a+b")
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("A catalog update is already running in another process") from error
        yield
    finally:
        if handle:
            handle.close()
        lock.release()


class Catalog(CatalogStorage):
    def __init__(
        self,
        workspace_root,
        *,
        feed_cache=None,
        transport=None,
        years=None,
        clock=None,
        bootstrap="feeds",
    ):
        super().__init__(workspace_root)
        if bootstrap not in {"feeds", "api"}:
            raise ValueError("Invalid catalog bootstrap method")
        self.bootstrap = bootstrap
        self.sync_timings = {}
        self.feed_cache = Path(feed_cache) if feed_cache else None
        from .credentials import NVDKeys

        self.transport = transport or NVDTransport(NVDKeys(workspace_root).get)
        self.years = list(years) if years is not None else None
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.server_retry_at = None

    def check_retry(self):
        persisted = self.metadata("server_retry_at")
        throttled = self.metadata("rate_limit_retry_at")
        until = max(
            (date(value) for value in (persisted, throttled, self.server_retry_at) if value),
            default=None,
        )
        if until and until > self.clock():
            raise CatalogDeferred(
                "Catalog requests are paused until " + stamp(until),
                (until - self.clock()).total_seconds(),
            )

    def _defer(self, error):
        if error.server_requested or error.rate_limited:
            try:
                until = stamp(self.clock() + timedelta(seconds=error.retry_after))
            except OverflowError:
                until = stamp(datetime.max.replace(tzinfo=timezone.utc))
            self.server_retry_at = until
            try:
                self.put_metadata(
                    "server_retry_at" if error.server_requested else "rate_limit_retry_at", until
                )
            except OSError, ValueError, sqlite3.Error:
                pass

    def _meta(self, year, cancel_event):
        name = f"nvdcve-2.0-{year}.meta"
        cached = self.feed_cache / name if self.feed_cache else None
        if cached and cached.is_file():
            if cached.stat().st_size > 16384:
                raise ValueError("NVD metadata is too large")
            body = cached.read_bytes()
        else:
            body = self.transport.bytes(FEED_BASE + name, limit=16384, cancel_event=cancel_event)
        return parse_meta(body)

    def _download(self, year, meta, folder, cancel_event):
        started = time.perf_counter()
        name = f"nvdcve-2.0-{year}.json.gz"
        compressed = folder / name
        local = self.feed_cache / name if self.feed_cache else None
        if local and local.is_file():
            compressed = local
            if compressed.stat().st_size != meta["gzSize"]:
                raise ValueError("Cached NVD compressed size does not match its metadata")
        else:

            def download_attempt():
                count = 0
                # Retry the complete file, never append a new response to a
                # partial previous attempt. Publication still requires checksum
                # and full-record validation below.
                with compressed.open("wb") as output:
                    incoming_chunks = self.transport.chunks(
                        FEED_BASE + name, limit=meta["gzSize"], cancel_event=cancel_event
                    )
                    for chunk in validated_gzip_chunks(incoming_chunks, "nvd"):
                        cancelled(cancel_event)
                        count += len(chunk)
                        output.write(chunk)
                return count

            count = retry_nvd(download_attempt, cancel_event=cancel_event)
            if count != meta["gzSize"]:
                raise ValueError("NVD compressed size does not match its metadata")
        # Cached feeds receive the same content boundary before decompression;
        # a .gz extension or published digest is not a content-type guarantee.
        verify_gzip_prefix(compressed, "nvd")
        self._measure("download_seconds", time.perf_counter() - started)
        started = time.perf_counter()
        unpacked = folder / "feed.json"
        digest, count = hashlib.sha256(), 0
        try:
            with gzip.open(compressed, "rb") as incoming, unpacked.open("wb") as output:
                while chunk := incoming.read(1024 * 1024):
                    cancelled(cancel_event)
                    count += len(chunk)
                    if count > meta["size"] or count > MAX_UNCOMPRESSED:
                        raise ValueError("NVD uncompressed content exceeds its declared size")
                    digest.update(chunk)
                    output.write(chunk)
        except (gzip.BadGzipFile, EOFError) as error:
            raise ValueError("NVD compressed feed is incomplete or invalid") from error
        if count != meta["size"] or digest.hexdigest() != meta["sha256"]:
            raise ValueError("NVD uncompressed feed checksum does not match its metadata")
        self._measure("decompress_seconds", time.perf_counter() - started)
        return unpacked

    def _measure(self, key, seconds):
        self.sync_timings[key] = self.sync_timings.get(key, 0.0) + seconds

    def upsert(self, db, cve, source):
        started = time.perf_counter()
        prior_index = self.sync_timings.get("index_seconds", 0.0)
        try:
            return super().upsert(db, cve, source)
        finally:
            self._measure(
                "store_seconds",
                max(
                    0.0,
                    time.perf_counter()
                    - started
                    - (self.sync_timings.get("index_seconds", 0.0) - prior_index),
                ),
            )

    def _timed_records(self, path, cancel_event):
        iterator = iter(records(path, cancel_event))
        while True:
            started = time.perf_counter()
            try:
                record = next(iterator)
            except StopIteration:
                return
            finally:
                self._measure("parse_seconds", time.perf_counter() - started)
            yield record

    def _import_year(self, year, progress, cancel_event):
        cancelled(cancel_event)
        progress(
            {
                "phase": "bootstrap",
                "year": year,
                "records": 0,
                "message": f"Downloading CVE-{year} feed",
            }
        )
        meta = self._meta(year, cancel_event)
        with tempfile.TemporaryDirectory(prefix="import-", dir=self.folder) as temporary:
            (Path(temporary) / ".catalog-import-owned").write_text("NVD catalog staging v1\n")
            path = self._download(year, meta, Path(temporary), cancel_event)
            source = {
                "url": FEED_BASE + f"nvdcve-2.0-{year}.json.gz",
                "retrieved_at": stamp(self.clock()),
                "feed_sha256": meta["sha256"],
                "feed_modified_at": meta["lastModifiedDate"],
                "format": "NVD JSON 2.0 yearly feed",
            }
            count, changed = 0, 0
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                for record in self._timed_records(path, cancel_event):
                    record_year = (
                        int(str(record.get("id", ""))[4:8])
                        if re.fullmatch(r"CVE-\d{4}-\d{4,}", str(record.get("id", "")))
                        else None
                    )
                    if record_year is None or (
                        record_year != year and not (year == 2002 and 1999 <= record_year <= 2002)
                    ):
                        raise ValueError("NVD feed contains an invalid CVE year")
                    changed += bool(self.upsert(db, record, source))
                    count += 1
                    if count % 1000 == 0:
                        progress(
                            {
                                "phase": "bootstrap",
                                "year": year,
                                "records": count,
                                "message": f"Importing CVE-{year}: {count:,} records",
                                "timings": dict(self.sync_timings),
                            }
                        )
                if count == 0:
                    raise ValueError("NVD yearly feed is empty")
                db.execute(
                    "INSERT OR REPLACE INTO feeds VALUES (?,?,?,?,?)",
                    (year, meta["sha256"], meta["lastModifiedDate"], source["retrieved_at"], count),
                )
            progress(
                {
                    "phase": "bootstrap",
                    "year": year,
                    "records": count,
                    "changed": changed,
                    "message": f"CVE-{year} imported",
                    "timings": dict(self.sync_timings),
                }
            )
        return changed

    def _bootstrap_api(self, progress, cancel_event):
        """Commit each full page and its cursor together; resume after cancellation."""
        checkpoint = self.metadata("api_bootstrap") or {
            "start_index": 0,
            "started_at": stamp(self.clock()),
        }
        index = checkpoint["start_index"]
        changed = 0
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS api_bootstrap_seen(id TEXT PRIMARY KEY)")
        while True:
            cancelled(cancel_event)
            progress(
                {
                    "phase": "bootstrap_api",
                    "records": index,
                    "total_records": checkpoint.get("total"),
                    "message": f"Downloading CVE catalog: {index:,} records saved",
                }
            )
            body, url = self.transport.bulk_page(index, cancel_event=cancel_event)
            try:
                page = strict_json_loads(body, max_bytes=64 * 1024 * 1024, require_object=True)
                total, page_start, per_page = (
                    page["totalResults"],
                    page["startIndex"],
                    page["resultsPerPage"],
                )
                entries = page["vulnerabilities"]
                if page_start != index or (
                    type(total) is int and total < checkpoint.get("total", 0)
                ):
                    raise BulkPaginationChanged()
                if (
                    type(total) is not int
                    or not 1 <= total <= 2_000_000
                    or type(page_start) is not int
                    or page_start != index
                    or type(per_page) is not int
                    or not 1 <= per_page <= 2000
                    or not isinstance(entries, list)
                    or not 1 <= len(entries) <= per_page
                    or index + len(entries) > total
                ):
                    raise ValueError("Invalid NVD bulk API pagination")
                if index + len(entries) < total and len(entries) != per_page:
                    raise ValueError("NVD bulk API page is incomplete")
                source = {
                    "url": url,
                    "retrieved_at": stamp(self.clock()),
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                    "format": "NVD API 2.0 full catalog",
                }
                with self.connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    for item in entries:
                        cancelled(cancel_event)
                        record = item["cve"]
                        # Repeated IDs signal shifted pagination; never mark an incomplete snapshot ready.
                        if db.execute(
                            "SELECT 1 FROM api_bootstrap_seen WHERE id=?", (record["id"],)
                        ).fetchone():
                            raise BulkPaginationChanged()
                        changed += bool(self.upsert(db, record, source))
                        db.execute("INSERT INTO api_bootstrap_seen VALUES(?)", (record["id"],))
                    index += len(entries)
                    checkpoint.update(start_index=index, total=total)
                    self.put_metadata("api_bootstrap", checkpoint, db=db)
                    if index >= total:
                        if (
                            db.execute("SELECT count(*) FROM api_bootstrap_seen").fetchone()[0]
                            != total
                        ):
                            raise BulkPaginationChanged()
                        self.put_metadata("api_bootstrap_complete", True, db=db)
                        self.put_metadata("sync_cursor", checkpoint["started_at"], db=db)
                        self.put_metadata("api_bootstrap", None, db=db)
                        db.execute("DROP TABLE api_bootstrap_seen")
            except BulkPaginationChanged:
                # Reset only the coverage cursor. Previously stored CVEs remain
                # searchable, but cannot count as a completed snapshot.
                with self.connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("DELETE FROM api_bootstrap_seen")
                    self.put_metadata("api_bootstrap", None, db=db)
                raise
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise ValueError("Invalid NVD bulk API response") from error
            progress(
                {
                    "phase": "bootstrap_api",
                    "records": index,
                    "total_records": total,
                    "message": f"Catalog download: {index:,} of {total:,} CVEs saved",
                }
            )
            if index >= total:
                return changed

    def _window(self, start, end, progress, cancel_event, *, feed_seed=None):
        # The API query is serialized to milliseconds; use those exact same
        # boundaries to validate returned records, including boundary records.
        start, end = date(stamp(start)), date(stamp(end))
        index, expected_total, changed = 0, None, 0
        seen = set()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            while True:
                cancelled(cancel_event)
                started = time.perf_counter()
                body, url = self.transport.api_page(
                    stamp(start), stamp(end), index, cancel_event=cancel_event
                )
                self._measure("download_seconds", time.perf_counter() - started)
                try:
                    started = time.perf_counter()
                    page = strict_json_loads(body, max_bytes=64 * 1024 * 1024, require_object=True)
                    self._measure("parse_seconds", time.perf_counter() - started)
                    total, page_start = page["totalResults"], page["startIndex"]
                    entries = page["vulnerabilities"]
                    if (
                        type(total) is not int
                        or not 0 <= total <= 2_000_000
                        or type(page_start) is not int
                        or page_start != index
                        or not isinstance(entries, list)
                        or len(entries) > 2000
                    ):
                        raise ValueError("Invalid NVD API pagination")
                    if expected_total is not None and total != expected_total:
                        raise CatalogDeferred(
                            "NVD result count changed during synchronization; retrying this window later.",
                            300,
                        )
                    expected_total = total
                    if not entries and index < total or index + len(entries) > total:
                        raise ValueError("NVD API page is incomplete")
                    source = {
                        "url": url,
                        "retrieved_at": stamp(self.clock()),
                        "response_sha256": hashlib.sha256(body).hexdigest(),
                        "format": "NVD API 2.0 last-modified window",
                    }
                    for entry in entries:
                        cancelled(cancel_event)
                        record = entry["cve"]
                        identifier = record["id"]
                        if identifier in seen:
                            raise CatalogDeferred(
                                "NVD pagination repeated a CVE; retrying this complete window later.",
                                300,
                            )
                        seen.add(identifier)
                        modified = date(record["lastModified"])
                        if modified < start or modified > end:
                            raise CatalogDeferred(
                                "NVD records changed during synchronization; retrying this window later.",
                                300,
                            )
                        changed += bool(self.upsert(db, record, source))
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise ValueError("Invalid NVD API response") from error
                index += len(entries)
                progress(
                    {
                        "phase": "updates",
                        "records": index,
                        "total_records": total,
                        "message": f"Updating catalog: {index:,} of {total:,} records",
                        "timings": dict(self.sync_timings),
                    }
                )
                if index >= total:
                    break
            if len(seen) != expected_total:
                raise CatalogDeferred(
                    "NVD pagination did not contain the expected unique records; retrying later.",
                    300,
                )
            self.put_metadata("sync_cursor", stamp(end), db=db)
            if feed_seed is not None:
                # A cursor is reusable for this seed only after this entire
                # window and its records commit together.
                self.put_metadata("feed_catchup_seed", feed_seed, db=db)
        return changed

    def sync(self, *, cancel_event=None, progress=None):
        self.check_retry()
        try:
            return self._sync(cancel_event=cancel_event, progress=progress)
        except CatalogDeferred as error:
            self._defer(error)
            raise

    def _sync(self, *, cancel_event=None, progress=None):
        progress = progress or (lambda value: None)
        self._initialize()
        with sync_lock(self.folder):
            for path in self.folder.glob("import-*"):
                marker = path / ".catalog-import-owned"
                if (
                    path.is_dir()
                    and not path.is_symlink()
                    and marker.is_file()
                    and marker.stat().st_size < 64
                    and marker.read_text() == "NVD catalog staging v1\n"
                ):
                    shutil.rmtree(path)
            now = self.clock()
            self.put_metadata("last_attempt_at", stamp(now))
            self.put_metadata("last_error", None)
            years = self.years if self.years is not None else range(now.year, 2001, -1)
            with self.connection() as db:
                completed = {r[0] for r in db.execute("SELECT year FROM feeds")}
            self.sync_timings = {}
            self.put_metadata("download_method", self.bootstrap)
            changed = 0
            api_mode = self.bootstrap == "api" and self.years is None and self.feed_cache is None
            if self.years is None and self.feed_cache is None:
                if isinstance(self.transport, NVDTransport) and not self.transport.has_key():
                    raise ValueError(
                        "Add your NVD API key in Settings before downloading or updating the CVE catalog."
                    )
            if api_mode:
                if not self.status()["bootstrap_complete"]:
                    changed += self._bootstrap_api(progress, cancel_event)
            elif self.years is not None or not self.status()["bootstrap_complete"]:
                for year in years:
                    if type(year) is not int or not 2002 <= year <= now.year:
                        raise ValueError("Invalid feed year")
                    if year not in completed:
                        changed += self._import_year(year, progress, cancel_event)
            cursor = self.metadata("sync_cursor")
            with self.connection() as db:
                earliest = db.execute("SELECT min(modified) FROM feeds").fetchone()[0]
                feed_rows = db.execute(
                    "SELECT year,sha256,modified FROM feeds ORDER BY year"
                ).fetchall()
            feed_seed = None
            if (
                self.years is None
                and earliest
                and not self.metadata("api_bootstrap_complete", False)
            ):
                feed_seed = hashlib.sha256(
                    json.dumps([tuple(row) for row in feed_rows], separators=(",", ":")).encode()
                ).hexdigest()
            if cursor:
                start = date(cursor) - timedelta(minutes=5)
                if feed_seed is not None and self.metadata("feed_catchup_seed") != feed_seed:
                    # A partial/custom seed may already have an update cursor.
                    # Only a window committed against these exact feed snapshots
                    # proves coverage. Otherwise catch up from the oldest feed.
                    start = min(start, date(earliest) - timedelta(minutes=5))
            else:
                # Annual feeds have different publication times. Start before
                # the oldest imported snapshot, not after the bootstrap ends.
                start = (
                    date(earliest) - timedelta(minutes=5) if earliest else now - timedelta(days=1)
                )
            end = self.clock()
            if start > end:
                raise ValueError("Catalog update checkpoint is in the future")
            while start < end:
                boundary = min(start + timedelta(days=119), end)
                changed += self._window(
                    start, boundary, progress, cancel_event, feed_seed=feed_seed
                )
                if boundary >= end:
                    break
                start = boundary - timedelta(minutes=5)
            completed_at = stamp(self.clock())
            with self.connection() as db:
                if self.years is None:
                    # Complete annual or API seeds now follow incremental coverage;
                    # a new calendar year must not trigger another full import.
                    self.put_metadata("api_bootstrap_complete", True, db=db)
                self.put_metadata("sync_timings", self.sync_timings, db=db)
                self.put_metadata("last_success_at", completed_at, db=db)
                self.put_metadata("next_check_at", stamp(self.clock() + timedelta(days=1)), db=db)
                self.put_metadata("last_error", None, db=db)
            progress(
                {
                    "phase": "complete",
                    "message": "Catalog is up to date",
                    "changed": changed,
                    "timings": dict(self.sync_timings),
                }
            )
            return {"changed": changed, **self.status()}
