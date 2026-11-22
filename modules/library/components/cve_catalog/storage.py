"""Reusable NVD reference data, kept outside immutable case evidence and backups."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

from .analytics import CatalogAnalytics, ensure_schema, index_record, journal_change
from .risk_policy import date as date
from ..intelligence.metrics import select_nvd_metric

CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")


def stamp(value=None):
    return (
        (value or datetime.now(timezone.utc))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class CatalogStorage(CatalogAnalytics):
    def __init__(self, workspace_root):
        self.workspace_root = Path(workspace_root).resolve()
        self.folder = Path(str(self.workspace_root) + "-reference") / "nvd"
        self.db = self.folder / "catalog.sqlite3"

    def _initialize(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db, timeout=15, uri=True)
        try:
            schema = db.execute("PRAGMA user_version").fetchone()[0]
            if schema == 1:
                # SQLite backup seeds use DELETE mode; restore concurrent readers/writers.
                db.execute("PRAGMA journal_mode=WAL").fetchone()
                ensure_schema(db)
                db.execute(
                    "CREATE INDEX IF NOT EXISTS records_modified_order ON records(modified DESC,id DESC)"
                )
                db.execute("DROP INDEX IF EXISTS records_modified")
                db.commit()
                return
            if schema != 0:
                raise ValueError("The catalog was created by a newer application version")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records(
                    id TEXT PRIMARY KEY, description TEXT NOT NULL, status TEXT NOT NULL,
                    published TEXT NOT NULL, modified TEXT NOT NULL, severity TEXT NOT NULL,
                    score REAL, raw_json TEXT NOT NULL, raw_sha256 TEXT NOT NULL,
                    source_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS records_modified_order ON records(modified DESC,id DESC);
                CREATE INDEX IF NOT EXISTS records_severity ON records(severity);
                CREATE TABLE IF NOT EXISTS feeds(
                    year INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, modified TEXT NOT NULL,
                    imported_at TEXT NOT NULL, record_count INTEGER NOT NULL
                );
            """)
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS search_records USING fts5(id UNINDEXED, description)"
                )
                fts = True
            except sqlite3.OperationalError as error:
                if "no such module" not in str(error):
                    raise
                fts = False
            db.execute(
                "INSERT OR REPLACE INTO metadata VALUES ('fts_enabled',?)", (json.dumps(fts),)
            )
            ensure_schema(db)
            db.execute("PRAGMA user_version=1")
            db.commit()
        finally:
            db.close()

    @contextmanager
    def connection(self, *, readonly=False):
        if not readonly:
            self._initialize()
        target = self.db.as_uri() + "?mode=ro" if readonly else str(self.db)
        db = sqlite3.connect(target, timeout=15, uri=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        try:
            if readonly:
                schema = db.execute("PRAGMA user_version").fetchone()[0]
                if schema != 1:
                    raise ValueError(
                        "The catalog was created by a newer application version"
                        if schema > 1
                        else "The catalog is not initialized"
                    )
                db.execute("BEGIN")
            yield db
            if not readonly:
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
            with self.connection(readonly=True) as conn:
                return self.metadata(key, default, db=conn)
        row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put_metadata(self, key, value, *, db=None):
        if db is None:
            with self.connection() as conn:
                return self.put_metadata(key, value, db=conn)
        db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value)))

    def set_enabled(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("Daily updates must be enabled or disabled.")
        self.put_metadata("enabled", enabled)
        return self.status()

    def status(self):
        if not self.db.is_file():
            return {
                "source": "NVD",
                "total": 0,
                "enabled": False,
                "bootstrap_complete": False,
                "years_complete": [],
                "required_years": list(range(2002, datetime.now(timezone.utc).year + 1)),
                "last_success_at": None,
                "next_check_at": None,
                "server_retry_at": None,
                "last_error": None,
                "last_attempt_at": None,
                "sync_cursor": None,
                "stale": True,
                "db_bytes": 0,
                "attribution": "This product uses data from the NVD API but is not endorsed or certified by the NVD.",
            }
        with self.connection(readonly=True) as db:
            years = [r[0] for r in db.execute("SELECT year FROM feeds ORDER BY year")]
            required = list(range(2002, datetime.now(timezone.utc).year + 1))
            last = self.metadata("last_success_at", db=db)
            return {
                "source": "NVD",
                "total": db.execute("SELECT count(*) FROM records").fetchone()[0],
                "enabled": self.metadata("enabled", False, db=db),
                "bootstrap_complete": bool(self.metadata("api_bootstrap_complete", False, db=db))
                or all(y in years for y in required),
                "api_bootstrap": self.metadata("api_bootstrap", db=db),
                "download_method": self.metadata(
                    "download_method",
                    "api" if self.metadata("api_bootstrap", db=db) else "feeds",
                    db=db,
                ),
                "timings": self.metadata("sync_timings", {}, db=db),
                "years_complete": years,
                "required_years": required,
                "last_success_at": last,
                "next_check_at": self.metadata("next_check_at", db=db),
                "server_retry_at": self.metadata("server_retry_at", db=db),
                "last_error": self.metadata("last_error", db=db),
                "last_attempt_at": self.metadata("last_attempt_at", db=db),
                "sync_cursor": self.metadata("sync_cursor", db=db),
                "stale": not last
                or (datetime.now(timezone.utc) - date(last)).total_seconds() > 172800,
                "db_bytes": self.db.stat().st_size
                + (
                    Path(str(self.db) + "-wal").stat().st_size
                    if Path(str(self.db) + "-wal").exists()
                    else 0
                ),
                "attribution": "This product uses data from the NVD API but is not endorsed or certified by the NVD.",
            }

    def get(self, cve_id):
        cve_id = str(cve_id).upper()
        if not CVE_ID.fullmatch(cve_id):
            raise ValueError("Invalid CVE identifier")
        if not self.db.is_file():
            return None
        with self.connection(readonly=True) as db:
            row = db.execute(
                "SELECT raw_json,raw_sha256,source_json,modified FROM records WHERE id=?", (cve_id,)
            ).fetchone()
            checked = self.metadata("last_success_at", db=db)
        if row is None:
            return None
        if hashlib.sha256(row[0].encode("utf-8")).hexdigest() != row[1]:
            raise ValueError("The local CVE record failed its integrity check")
        raw, source = json.loads(row[0]), json.loads(row[2])
        if not isinstance(raw, dict) or raw.get("id") != cve_id or not isinstance(source, dict):
            raise ValueError("The local CVE record does not match its identifier or provenance")
        return {
            "cve": raw,
            "source": {**source, "record_sha256": row[1]},
            "last_modified": row[3],
            "catalog_checked_at": checked,
            "catalog_stale": not checked
            or (datetime.now(timezone.utc) - date(checked)).total_seconds() > 172800,
        }

    def search(self, query="", *, limit=50, offset=0, severity=None):
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("Search text must be at most 200 characters.")
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 500000
        ):
            raise ValueError("Invalid catalog page.")
        if not self.db.is_file():
            return {"items": [], "total": 0, "limit": limit, "offset": offset, "has_records": False}
        fts = self.metadata("fts_enabled", False)
        args, clauses, join = [], [], ""
        q = query.strip()
        if CVE_ID.fullmatch(q.upper()):
            clauses.append("r.id=?")
            args.append(q.upper())
        elif q.upper().startswith("CVE-"):
            prefix = q.upper()
            # Binary prefix bounds use the primary-key index; SQLite's default
            # case-insensitive LIKE otherwise scans the full public catalog.
            if re.fullmatch(r"CVE-(?:\d{0,4}|\d{4}-\d*)", prefix):
                clauses.append("r.id>=? AND r.id<?")
                args.extend((prefix, prefix + "\uffff"))
            else:
                clauses.append("0")
        elif q and fts:
            words = re.findall(r"[\w.-]+", q, re.UNICODE)
            if words:
                join = " JOIN search_records s ON s.rowid=r.rowid"
                clauses.append("search_records MATCH ?")
                args.append(
                    " AND ".join('"' + word.replace('"', '""') + '"*' for word in words[:20])
                )
            else:
                clauses.append("0")
        elif q:
            clauses.append("r.description LIKE ? ESCAPE '\\'")
            args.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        if severity is not None and severity != "":
            severity = str(severity).upper()
            if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "UNKNOWN"}:
                raise ValueError("Unknown severity")
            clauses.append("r.severity=?")
            args.append(severity)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection(readonly=True) as db:
            total = db.execute("SELECT count(*) FROM records r" + join + where, args).fetchone()[0]
            has_records = (
                bool(total) or db.execute("SELECT 1 FROM records LIMIT 1").fetchone() is not None
            )
            rows = db.execute(
                "SELECT r.id,r.description,r.status,r.published,r.modified,r.severity,r.score FROM records r"
                + join
                + where
                + " ORDER BY r.modified DESC,r.id DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "has_records": has_records,
            "limit": limit,
            "offset": offset,
        }

    def upsert(self, db, cve, source):
        if not isinstance(cve, dict) or not CVE_ID.fullmatch(str(cve.get("id", ""))):
            raise ValueError("Feed contains an invalid CVE record")
        identifier = cve["id"]
        modified = stamp(date(cve["lastModified"]))
        published = stamp(date(cve["published"]))
        status = cve.get("vulnStatus")
        if not isinstance(status, str) or not status:
            raise ValueError("CVE record has no status")
        description = next(
            (
                item["value"]
                for item in cve.get("descriptions", [])
                if isinstance(item, dict)
                and item.get("lang") == "en"
                and isinstance(item.get("value"), str)
            ),
            "",
        )
        score, severity = None, "UNKNOWN"
        chosen = select_nvd_metric(cve)
        if chosen:
            data = chosen["cvssData"]
            score = float(data["baseScore"])
            severity = (
                data.get("baseSeverity")
                or chosen.get("baseSeverity")
                or (
                    "CRITICAL"
                    if score >= 9
                    else "HIGH"
                    if score >= 7
                    else "MEDIUM"
                    if score >= 4
                    else "LOW"
                    if score > 0
                    else "NONE"
                )
            ).upper()
        raw = json.dumps(
            cve, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
        )
        digest = hashlib.sha256(raw.encode()).hexdigest()
        existing = db.execute(
            "SELECT modified,raw_sha256,rowid,raw_json FROM records WHERE id=?", (identifier,)
        ).fetchone()
        if existing and (
            existing[0] > modified
            or existing[0] == modified
            and existing[1] == digest
            and hashlib.sha256(existing[3].encode()).hexdigest() == existing[1]
        ):
            return False
        db.execute(
            "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET description=excluded.description,status=excluded.status,published=excluded.published,modified=excluded.modified,severity=excluded.severity,score=excluded.score,raw_json=excluded.raw_json,raw_sha256=excluded.raw_sha256,source_json=excluded.source_json",
            (
                identifier,
                description,
                status,
                published,
                modified,
                severity,
                score,
                raw,
                digest,
                json.dumps(source, allow_nan=False),
            ),
        )
        if existing and hashlib.sha256(existing[3].encode()).hexdigest() == existing[1]:
            journal_change(db, json.loads(existing[3]), cve, existing[1], digest, stamp())
        indexing_started = time.perf_counter()
        index_record(db, cve, digest)
        if hasattr(self, "_measure"):
            self._measure("index_seconds", time.perf_counter() - indexing_started)
        if not self.metadata("fts_enabled", False, db=db):
            return True
        rowid = (
            existing[2]
            if existing
            else db.execute("SELECT rowid FROM records WHERE id=?", (identifier,)).fetchone()[0]
        )
        if existing:
            db.execute("DELETE FROM search_records WHERE rowid=?", (rowid,))
        db.execute(
            "INSERT INTO search_records(rowid,id,description) VALUES (?,?,?)",
            (rowid, identifier, description),
        )
        return True
