"""Atomic local EPSS and KEV feeds, separate from NVD records and case evidence."""

from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import urljoin, urlsplit

import requests

from ..cve_intelligence import validate_kev_catalog
from .storage import date, stamp
from .transport import CatalogDeferred, cancelled, explicit_retry_seconds
from .content_validation import validate_feed_media, validated_gzip_chunks
from .control import remaining, transfer_deadline
from .feed_http import open_response as _response_get
from .risk_policy import (
    SCHEMA_VERSION as SCHEMA_VERSION,
    UnsupportedRiskSchema as UnsupportedRiskSchema,
    check_schema,
    freshness,
)
from modules.workspace.components.aegis.json import strict_json_loads

EPSS_FEED = "https://epss.empiricalsecurity.com/epss_scores-current.csv.gz"
KEV_FEED = "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"
CVE = re.compile(r"CVE-\d{4}-\d{4,19}")
MAX_COMPRESSED = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_KEV = 32 * 1024 * 1024
MAX_ROWS = 1_000_000
TRANSFER_BUDGET = 300.0


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class RiskTransport:
    """Only fixed official feeds and their approved HTTPS redirect hosts."""

    def download(self, provider, target, *, cancel_event=None):
        url = {"epss": EPSS_FEED, "kev": KEV_FEED}[provider]
        allowed = {
            "epss": {"epss.empiricalsecurity.com", "epss.cyentia.com"},
            "kev": {"raw.githubusercontent.com"},
        }[provider]
        deadline = transfer_deadline(TRANSFER_BUDGET)
        for _ in range(5):
            cancelled(cancel_event)
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in allowed
                or parsed.port not in (None, 443)
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Risk feed redirected outside its approved publisher")
            try:
                response = _response_get(
                    url,
                    stream=True,
                    timeout=(10, 30),
                    allow_redirects=False,
                    budget=remaining(deadline, cancel_event),
                    cancel_event=cancel_event,
                    limit=MAX_COMPRESSED if provider == "epss" else MAX_KEV,
                    headers={
                        "User-Agent": "ShadowserverCompanion/LocalRiskCatalog",
                        "Accept-Encoding": "identity",
                    },
                )
            except requests.RequestException as error:
                raise CatalogDeferred(
                    "Risk feed could not be reached; saved data remains available."
                ) from error
            with response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers.get("Location", ""))
                    continue
                if response.status_code in {429, 503}:
                    header = next(
                        (v for k, v in response.headers.items() if k.lower() == "retry-after"), None
                    )
                    delay = explicit_retry_seconds(header)
                    raise CatalogDeferred(
                        "Risk feed requested a retry later; saved data remains available.",
                        3600 if delay is None else max(60, delay),
                        server_requested=delay is not None,
                    )
                if response.status_code != 200:
                    raise CatalogDeferred(
                        f"Risk feed returned HTTP {response.status_code}; saved data remains available."
                    )
                validate_feed_media(response.headers, "gzip" if provider == "epss" else "json")
                count, checksum = 0, hashlib.sha256()
                limit = MAX_COMPRESSED if provider == "epss" else MAX_KEV

                def bounded_chunks():
                    nonlocal count
                    for chunk in response.iter_content(128 * 1024):
                        remaining(deadline, cancel_event)
                        if not isinstance(chunk, bytes):
                            raise ValueError("Risk feed transport returned non-byte data")
                        count += len(chunk)
                        if count > limit:
                            raise ValueError("Risk feed exceeded its download size or time budget")
                        checksum.update(chunk)
                        yield chunk

                temporary = None
                try:
                    if provider == "kev":
                        # KEV is bounded at 32 MiB. Validate the entire JSON and
                        # catalog schema in memory before creating any body file.
                        body = b"".join(bounded_chunks())
                        body.decode("utf-8-sig", errors="strict")
                        raw = validate_kev_catalog(
                            strict_json_loads(body, max_bytes=MAX_KEV, require_object=True)
                        )
                        if not raw["vulnerabilities"]:
                            raise ValueError("KEV feed contains no vulnerabilities")
                        chunks = (body,)
                    else:
                        # Keep full EPSS downloads streaming; gzip framing and
                        # the model/CSV header must pass before the first write.
                        chunks = validated_gzip_chunks(bounded_chunks(), "epss")
                    with tempfile.NamedTemporaryFile(
                        prefix=".risk-", suffix=".part", dir=Path(target).parent, delete=False
                    ) as output:
                        temporary = Path(output.name)
                        for chunk in chunks:
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    if not count:
                        raise ValueError("Risk feed was empty")
                    remaining(deadline, cancel_event)
                    temporary.replace(target)
                except requests.RequestException as error:
                    raise CatalogDeferred(
                        "Risk download was interrupted; saved data remains available."
                    ) from error
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                return {"url": url, "sha256": checksum.hexdigest(), "bytes": count}
        raise ValueError("Risk feed exceeded its redirect limit")


class RiskStore:
    def __init__(self, workspace_root, *, transport=None, clock=None):
        self.folder = Path(str(Path(workspace_root).resolve()) + "-reference") / "nvd"
        self.db = self.folder / "risk.sqlite3"
        self.transport = transport or RiskTransport()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def connection(self, *, write=False):
        if write:
            self.folder.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.db, timeout=10)
        else:
            db = sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=10)
        try:
            if not write:
                # Metadata, rows and the feed describe one committed revision.
                db.execute("BEGIN")
            check_schema(db)
            if write:
                db.execute("PRAGMA journal_mode=WAL")
                db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS epss(
                    id TEXT PRIMARY KEY,score REAL NOT NULL,percentile REAL NOT NULL,
                    score_date TEXT NOT NULL,model_version TEXT NOT NULL,raw_sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS kev(id TEXT PRIMARY KEY,raw_json TEXT NOT NULL,raw_sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feeds(provider TEXT PRIMARY KEY,raw_json TEXT NOT NULL,raw_sha256 TEXT NOT NULL);
                PRAGMA user_version=1;
                """)
            db.row_factory = sqlite3.Row
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def metadata(self, key, default=None, *, db=None):
        if db is None:
            if not self.db.is_file():
                return default
            with self.connection() as conn:
                return self.metadata(key, default, db=conn)
        row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put_metadata(self, key, value, *, db=None):
        if db is None:
            with self.connection(write=True) as conn:
                return self.put_metadata(key, value, db=conn)
        db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, encoded(value)))

    def _state(self, provider, *, db=None):
        value = self.metadata(provider, {}, db=db)
        return {
            "count": 0,
            "last_success_at": None,
            "last_attempt_at": None,
            "last_error": None,
            "next_check_at": None,
            "source_url": None,
            **value,
            **freshness(provider, value, self.clock()),
        }

    def status(self):
        if not self.db.is_file():
            return {"epss": self._state("epss"), "kev": self._state("kev"), "enabled": False}
        with self.connection() as db:
            return {
                "epss": self._state("epss", db=db),
                "kev": self._state("kev", db=db),
                "enabled": self.metadata("enabled", False, db=db),
            }

    def source(self, provider, state):
        return {
            "publisher": "FIRST EPSS" if provider == "epss" else "CISA KEV",
            "url": state.get("source_url"),
            "retrieved_at": state.get("last_success_at"),
            "sha256": state.get("sha256"),
            "count": state.get("count", 0),
            "score_date": state.get("score_date"),
            "model_version": state.get("model_version"),
            "catalog_version": state.get("catalog_version"),
            "date_released": state.get("date_released"),
        }

    def get(self, cve_id):
        identifier = str(cve_id).upper()
        if not CVE.fullmatch(identifier):
            raise ValueError("Invalid CVE identifier")
        return self.bulk([identifier]).get(identifier, {"epss": None, "kev": None})

    def bulk(self, cve_ids):
        ids = sorted({str(value).upper() for value in cve_ids if CVE.fullmatch(str(value).upper())})
        if len(ids) > MAX_ROWS:
            raise ValueError("Too many CVE identifiers")
        results = {identifier: {"epss": None, "kev": None} for identifier in ids}
        if not ids or not self.db.is_file():
            return results
        with self.connection() as db:
            epss, kev = self._state("epss", db=db), self._state("kev", db=db)
            if kev.get("last_success_at") and db.execute("SELECT count(*) FROM kev").fetchone()[
                0
            ] != kev.get("count"):
                raise ValueError("Local KEV index is incomplete")
            for start in range(0, len(ids), 500):
                chunk = ids[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                for row in db.execute(f"SELECT * FROM epss WHERE id IN ({placeholders})", chunk):
                    value = {
                        "cve": row["id"],
                        "epss": row["score"],
                        "percentile": row["percentile"],
                        "date": row["score_date"],
                        "model_version": row["model_version"],
                    }
                    if digest(value) != row["raw_sha256"]:
                        raise ValueError("Local EPSS record failed its integrity check")
                    results[row["id"]]["epss"] = {
                        "score": row["score"],
                        "percentile": row["percentile"],
                        "score_date": row["score_date"],
                        "model_version": row["model_version"],
                        "source": self.source("epss", epss),
                        "stale": epss["stale"],
                        "record_sha256": row["raw_sha256"],
                    }
                if kev.get("last_success_at"):
                    for identifier in chunk:
                        results[identifier]["kev"] = {
                            "listed": False,
                            "entry": None,
                            "source": self.source("kev", kev),
                            "stale": kev["stale"],
                        }
                for row in db.execute(f"SELECT * FROM kev WHERE id IN ({placeholders})", chunk):
                    if hashlib.sha256(row["raw_json"].encode()).hexdigest() != row["raw_sha256"]:
                        raise ValueError("Local KEV record failed its integrity check")
                    entry = json.loads(row["raw_json"])
                    if entry.get("cveID") != row["id"]:
                        raise ValueError("Local KEV record does not match its identifier")
                    results[row["id"]]["kev"] = {
                        "listed": True,
                        "entry": entry,
                        "source": self.source("kev", kev),
                        "stale": kev["stale"],
                        "record_sha256": row["raw_sha256"],
                    }
        return results

    batch = bulk

    def extract(self, key):
        """Return provider-compatible JSON plus provenance without an HTTP claim."""
        if key.startswith("epss:"):
            identifier = key.partition(":")[2]
            value = self.get(identifier)["epss"]
            if not value:
                return None
            raw = {
                "status": "OK",
                "total": 1,
                "offset": 0,
                "limit": 1,
                "data": [
                    {
                        "cve": identifier,
                        "epss": value["score"],
                        "percentile": value["percentile"],
                        "date": value["score_date"],
                    }
                ],
            }
            return {
                "data": raw,
                "source": value["source"],
                "stale": value["stale"],
                "record_sha256": value["record_sha256"],
            }
        if key != "kev" or not self.db.is_file():
            return None
        with self.connection() as db:
            state = self._state("kev", db=db)
            row = db.execute("SELECT * FROM feeds WHERE provider='kev'").fetchone()
            if not row or not state.get("last_success_at"):
                return None
            if hashlib.sha256(row["raw_json"].encode()).hexdigest() != row["raw_sha256"]:
                raise ValueError("Local KEV catalog failed its integrity check")
            raw = validate_kev_catalog(json.loads(row["raw_json"]))
            return {
                "data": raw,
                "source": self.source("kev", state),
                "stale": state["stale"],
                "record_sha256": row["raw_sha256"],
            }

    def fingerprint(self, key):
        provider = "epss" if key.startswith("epss:") else "kev" if key == "kev" else None
        return self.metadata(provider, {}).get("sha256") if provider else None

    def import_epss(self, path, source, *, cancel_event=None, progress=lambda _: None):
        size = 0
        with gzip.open(path, "rb") as incoming:
            # TextIOWrapper would buffer arbitrary lines before a size check.
            def lines():
                nonlocal size
                while line := incoming.readline(16385):
                    cancelled(cancel_event)
                    size += len(line)
                    if len(line) > 16384 or size > MAX_EXPANDED:
                        raise ValueError("EPSS feed exceeds its expanded size or line budget")
                    yield line.decode("utf-8-sig")

            stream = iter(lines())
            first = next(stream, "")
            model = re.search(r"model_version\s*:\s*([^,\s]+)", first)
            score_date = re.search(r"score_date\s*:\s*(\d{4}-\d{2}-\d{2})", first)
            if not first.startswith("#") or not model or not score_date:
                raise ValueError("EPSS feed is missing its model version or score date")
            day = datetime.strptime(score_date[1], "%Y-%m-%d").date().isoformat()
            if day > self.clock().date().isoformat():
                raise ValueError("EPSS feed has a future score date")
            rows = csv.DictReader(stream)
            if rows.fieldnames != ["cve", "epss", "percentile"]:
                raise ValueError("EPSS feed has unexpected columns")
            previous = self.metadata("epss", {})
            if previous.get("score_date", "") > day:
                raise ValueError("EPSS feed is older than the saved score date")
            count = 0
            with self.connection(write=True) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM epss")
                for row in rows:
                    identifier = row.get("cve", "")
                    if not CVE.fullmatch(identifier) or None in row:
                        raise ValueError("EPSS feed contains an invalid record")
                    try:
                        score, percentile = float(row["epss"]), float(row["percentile"])
                    except (ValueError, TypeError) as error:
                        raise ValueError("EPSS feed contains an invalid score") from error
                    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (score, percentile)):
                        raise ValueError("EPSS score is outside its valid range")
                    value = {
                        "cve": identifier,
                        "epss": score,
                        "percentile": percentile,
                        "date": day,
                        "model_version": model[1],
                    }
                    try:
                        db.execute(
                            "INSERT INTO epss VALUES (?,?,?,?,?,?)",
                            (identifier, score, percentile, day, model[1], digest(value)),
                        )
                    except sqlite3.IntegrityError as error:
                        raise ValueError("EPSS feed contains duplicate identifiers") from error
                    count += 1
                    if count > MAX_ROWS:
                        raise ValueError("EPSS feed contains too many records")
                    if count % 10000 == 0:
                        progress(
                            {
                                "phase": "epss",
                                "records": count,
                                "message": f"Indexing EPSS: {count:,} scores",
                            }
                        )
                if not count:
                    raise ValueError("EPSS feed contains no scores")
                cancelled(cancel_event)
                state = {
                    **source,
                    "count": count,
                    "score_date": day,
                    "model_version": model[1],
                    "expanded_bytes": size,
                }
                self.put_metadata("epss", state, db=db)
            return state

    def import_kev(self, path, source, *, cancel_event=None, progress=lambda _: None):
        if Path(path).stat().st_size > MAX_KEV:
            raise ValueError("KEV feed is too large")
        raw = validate_kev_catalog(
            strict_json_loads(Path(path).read_bytes(), max_bytes=MAX_KEV, require_object=True)
        )
        if not raw["vulnerabilities"]:
            raise ValueError("KEV feed contains no vulnerabilities")
        previous = self.metadata("kev", {})
        if previous.get("date_released") and date(previous["date_released"]) > date(
            raw["dateReleased"]
        ):
            raise ValueError("KEV feed is older than the saved catalog")
        if date(raw["dateReleased"]) > self.clock():
            raise ValueError("KEV feed has a future release date")
        if len(raw["vulnerabilities"]) > MAX_ROWS:
            raise ValueError("KEV feed contains too many records")
        body = encoded(raw)
        with self.connection(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM kev")
            for entry in raw["vulnerabilities"]:
                cancelled(cancel_event)
                value = encoded(entry)
                db.execute(
                    "INSERT INTO kev VALUES (?,?,?)",
                    (entry["cveID"], value, hashlib.sha256(value.encode()).hexdigest()),
                )
            db.execute(
                "INSERT OR REPLACE INTO feeds VALUES ('kev',?,?)",
                (body, hashlib.sha256(body.encode()).hexdigest()),
            )
            state = {
                **source,
                "count": raw["count"],
                "catalog_version": raw["catalogVersion"],
                "date_released": raw["dateReleased"],
            }
            self.put_metadata("kev", state, db=db)
        progress(
            {
                "phase": "kev",
                "records": raw["count"],
                "message": f"Indexed {raw['count']:,} known exploited vulnerabilities",
            }
        )
        return state

    def sync(self, provider, *, cancel_event=None, progress=lambda _: None):
        if provider not in ("epss", "kev"):
            raise ValueError("Unknown risk provider")
        state = self.metadata(provider, {})
        if state.get("retry_at") and date(state["retry_at"]) > self.clock():
            raise CatalogDeferred(
                "Risk provider requested a retry later.",
                (date(state["retry_at"]) - self.clock()).total_seconds(),
                server_requested=True,
            )
        self.folder.mkdir(parents=True, exist_ok=True)
        progress({"phase": provider, "message": "Downloading " + provider.upper(), "records": 0})
        with tempfile.TemporaryDirectory(prefix="risk-download-", dir=self.folder) as folder:
            path = Path(folder) / "feed"
            source = self.transport.download(provider, path, cancel_event=cancel_event)
            current = stamp(self.clock())
            source = {
                "source_url": source["url"],
                "sha256": source["sha256"],
                "download_bytes": source["bytes"],
                "last_success_at": current,
                "last_attempt_at": current,
                "last_error": None,
                "next_check_at": stamp(
                    datetime.fromtimestamp(self.clock().timestamp() + 86400, timezone.utc)
                ),
            }
            try:
                return (self.import_epss if provider == "epss" else self.import_kev)(
                    path, source, cancel_event=cancel_event, progress=progress
                )
            except (
                gzip.BadGzipFile,
                EOFError,
                UnicodeError,
                csv.Error,
                json.JSONDecodeError,
            ) as error:
                raise ValueError(
                    "Risk feed was incomplete or invalid; saved data remains available."
                ) from error
