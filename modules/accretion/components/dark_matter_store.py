"""Accretion's complete report archive and sole persistence/query interface.

Workspace transactions enqueue durable deliveries. Delivery commits this archive
before acknowledging the queue; replay is idempotent. No archive operation creates
an entity, performs attribution, evaluates admission, or scores a finding.
"""

from contextlib import closing
import hashlib
from itertools import islice
import json
import math
from pathlib import Path
import sqlite3
from uuid import uuid4

from modules.workspace.components.primitives import now
from ..databases.dark_matter_schema import SCHEMA_VERSION, create_archive
from .dark_matter_fields import catalogue, json_value, normalize_fields
from .report_profiles import inventory_metadata, resolve_profile

_PROMOTED = frozenset({"promoted", "qualified", "associated", "lead"})
_COLUMNS = {
    key: f"r.{key}"
    for key in (
        "record_id",
        "import_id",
        "report_type",
        "stage",
        "outcome",
        "reason",
        "hostname",
        "ip",
        "root_domain",
        "region",
        "port",
        "asn",
        "observed_at",
        "recorded_at",
        "updated_at",
    )
}
_SELECT = "SELECT r.*,s.name source_name,s.path source_path,s.metadata source_metadata FROM records r JOIN sources s ON s.import_id=r.import_id"


def _dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _filter_value(value):
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("Filter values must be scalar")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Filter numbers must be finite")
    if isinstance(value, int) and not -(2**63) <= value < 2**63:
        raise ValueError("Filter integer exceeds the supported range")
    return value


def source_record_id(source_sha256, sheet, row):
    """Source identity remains usable even when every report value is malformed."""
    return hashlib.sha256(f"{source_sha256}:{sheet}:{row}".encode()).hexdigest()


def _source_position(row):
    source = row.get("source", row) if isinstance(row, dict) else getattr(row, "source", row)
    if isinstance(source, dict):
        sheet, number = source.get("sheet", ""), source.get("row")
    else:
        sheet, number = source.sheet, source.row
    if not isinstance(number, int) or isinstance(number, bool) or number < 0:
        raise ValueError("A source row needs its nonnegative row number")
    return source, str(sheet), number


def _source_row(row):
    """Project a source row; callers never construct an archive-specific envelope."""
    source, sheet, number = _source_position(row)
    fields = source.get("fields") if isinstance(source, dict) else source.fields
    if not isinstance(fields, dict) or not all(isinstance(key, str) for key in fields):
        raise ValueError("Source fields must be a mapping with string keys")
    result = {"source": {"sheet": str(sheet), "row": number, "fields": json_value(fields)}}
    if isinstance(row, dict):
        for key in ("reason", "outcome", "report_type"):
            if key in row:
                result[key] = row[key]
    return result


def _decision(row, default_outcome, default_reason):
    reason = str(row.get("reason", default_reason) or "")
    outcome = row.get("outcome")
    if outcome is None:
        if reason == "pending_qualification":
            outcome = "pending"
        else:
            outcome = default_outcome
    return str(outcome), reason


class DarkMatterStore:
    """Complete source rows, outcome history and bounded field queries."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / "dark_matter.sqlite3"
        if not self.path.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as db:
                create_archive(db)
                db.commit()
                db.execute("PRAGMA journal_mode=WAL")
        with closing(self._connect(readonly=True)) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise ValueError("Unsupported Dark Matter database schema")

    def _connect(self, *, readonly=False):
        address = self.path.as_uri() + "?mode=ro" if readonly else self.path
        db = sqlite3.connect(address, uri=readonly, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        if readonly:
            db.execute("PRAGMA query_only=ON")
        return db

    def record_batch(
        self,
        source,
        rows,
        *,
        stage="filter",
        outcome="rejected",
        reason="",
        event_id=None,
        recorded_at=None,
    ):
        """Store complete rows and their decisions in one archive transaction."""
        stamp, event_id = recorded_at or now(), event_id or uuid4().hex
        import_id = str(source["import_id"])
        digest = str(source.get("sha256") or source.get("source_sha256") or "")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("Source requires a SHA-256 fingerprint")
        configured = source.get("report_type", "auto")
        fallback = resolve_profile({}, source.get("name", ""), configured)["id"]
        schema_version = source.get("schema_version") or inventory_metadata()["sha256"]
        ids, observed = [], set()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM delivered_events WHERE event_id=?", (event_id,)
            ).fetchone():
                return {"record_ids": [], "replayed": True}
            db.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?) ON CONFLICT(import_id) DO UPDATE SET metadata=excluded.metadata",
                (
                    import_id,
                    digest,
                    str(source.get("name", "")),
                    str(source.get("path", "")),
                    _dump(json_value(source)),
                ),
            )
            incoming = iter(rows)
            while batch := list(islice(incoming, 500)):
                batch_rows = [_source_row(value) for value in batch]
                batch_ids = [
                    source_record_id(digest, value["source"]["sheet"], value["source"]["row"])
                    for value in batch_rows
                ]
                existing = dict(
                    db.execute(
                        "SELECT record_id,raw_fields FROM records WHERE record_id IN (SELECT value FROM json_each(?))",
                        (_dump(batch_ids),),
                    ).fetchall()
                )
                inserts, updates, decisions = [], [], []
                for record_id, row in zip(batch_ids, batch_rows):
                    original = row["source"]
                    ids.append(record_id)
                    fields = original["fields"]
                    report_type = row.get("report_type") or (
                        resolve_profile(fields, source.get("name", ""), configured)["id"]
                        if fields.get("report_type") and configured in ("", None, "auto")
                        else fallback
                    )
                    item_outcome, item_reason = _decision(row, outcome, reason)
                    observed.update((report_type, key) for key in fields)
                    prior = existing.get(record_id)
                    if prior is not None and json.loads(prior) != fields:
                        raise ValueError(
                            "Source identity already belongs to different original fields"
                        )
                    if prior is not None:
                        updates.append(
                            (
                                import_id,
                                stage,
                                item_outcome,
                                item_reason,
                                int(item_outcome in _PROMOTED),
                                stamp,
                                record_id,
                            )
                        )
                    else:
                        original_fields, normalized, errors, domain = normalize_fields(fields)
                        inserts.append(
                            (
                                record_id,
                                digest,
                                original["sheet"],
                                original["row"],
                                import_id,
                                report_type,
                                schema_version,
                                _dump(original_fields),
                                _dump(normalized),
                                _dump(errors),
                                normalized.get("hostname"),
                                normalized.get("ip"),
                                domain,
                                normalized.get("region"),
                                normalized.get("port"),
                                normalized.get("asn"),
                                normalized.get("timestamp"),
                                stage,
                                item_outcome,
                                item_reason,
                                int(item_outcome in _PROMOTED),
                                stamp,
                                stamp,
                            )
                        )
                    decisions.append(
                        (event_id, record_id, import_id, stage, item_outcome, item_reason, stamp)
                    )
                db.executemany(
                    "INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    inserts,
                )
                db.executemany(
                    "UPDATE records SET import_id=?,stage=?,outcome=?,reason=?,promoted=max(promoted,?),updated_at=? WHERE record_id=?",
                    updates,
                )
                db.executemany(
                    "INSERT INTO outcomes(event_id,record_id,import_id,stage,outcome,reason,recorded_at) VALUES(?,?,?,?,?,?,?)",
                    decisions,
                )
            db.executemany("INSERT OR IGNORE INTO observed_fields VALUES(?,?)", sorted(observed))
            db.execute("INSERT INTO delivered_events VALUES(?)", (event_id,))
            db.execute("UPDATE archive_state SET revision=revision+1 WHERE id=1")
        return {"record_ids": ids, "replayed": False}

    def record_outcome(
        self,
        record_ids,
        *,
        import_id,
        stage,
        outcome,
        reason="",
        event_id=None,
        recorded_at=None,
    ):
        """Append a decision; promoting a never-archived source is a deliberate no-op.

        A source can qualify without ever entering this archive. Recording an
        unsuccessful decision, however, requires retaining its original row first.
        """
        stamp, event_id = recorded_at or now(), event_id or uuid4().hex
        ids = list(dict.fromkeys(record_ids))
        updated = 0
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM delivered_events WHERE event_id=?", (event_id,)
            ).fetchone():
                return {"updated": 0, "replayed": True}
            for record_id in ids:
                if not db.execute(
                    "SELECT 1 FROM records WHERE record_id=?", (record_id,)
                ).fetchone():
                    if outcome in _PROMOTED:
                        continue
                    raise ValueError(f"Dark Matter source record does not exist: {record_id}")
                db.execute(
                    "INSERT INTO outcomes(event_id,record_id,import_id,stage,outcome,reason,recorded_at) VALUES(?,?,?,?,?,?,?)",
                    (event_id, record_id, import_id, stage, outcome, reason, stamp),
                )
                db.execute(
                    "UPDATE records SET stage=?,outcome=?,reason=?,updated_at=?,promoted=max(promoted,?) WHERE record_id=?",
                    (stage, outcome, reason, stamp, int(outcome in _PROMOTED), record_id),
                )
                updated += 1
            db.execute("INSERT INTO delivered_events VALUES(?)", (event_id,))
            if updated:
                db.execute("UPDATE archive_state SET revision=revision+1 WHERE id=1")
        return {"updated": updated, "not_archived": len(ids) - updated, "replayed": False}

    @staticmethod
    def _public(row):
        item = dict(row)
        metadata = json.loads(item.pop("source_metadata"))
        item["source"] = {
            **metadata,
            "name": item.pop("source_name"),
            "path": item.pop("source_path"),
            "sheet": item["sheet"],
            "row": item.pop("row_number"),
            "report_type": item["report_type"],
            "schema_version": item["schema_version"],
        }
        for field in ("raw_fields", "normalized_fields", "errors"):
            item[field] = json.loads(item[field])
        item["promoted"] = bool(item["promoted"])
        return item

    def get(self, record_id):
        with closing(self._connect(readonly=True)) as db:
            db.execute("BEGIN")
            row = db.execute(_SELECT + " WHERE r.record_id=?", (record_id,)).fetchone()
            if not row:
                return None
            result = self._public(row)
            result["outcomes"] = [
                dict(value)
                for value in db.execute(
                    "SELECT import_id,stage,outcome,reason,recorded_at FROM outcomes WHERE record_id=? ORDER BY sequence",
                    (record_id,),
                )
            ]
            return result

    @staticmethod
    def _predicate(filters, include_promoted=False, q=""):
        clauses, params = ([] if include_promoted else ["r.promoted=0"]), []
        if not isinstance(filters, (list, tuple)) or len(filters) > 32:
            raise ValueError("Filters must be a list with at most 32 predicates")
        for predicate in filters:
            if not isinstance(predicate, dict) or not isinstance(predicate.get("field"), str):
                raise ValueError("Each filter needs a field name")
            name, operation = predicate["field"], predicate.get("op", "eq")
            if not name or len(name) > 300:
                raise ValueError("Invalid field name")
            raw = predicate.get("source", "normalized") == "raw"
            if predicate.get("source", "normalized") not in {"normalized", "raw"}:
                raise ValueError("Field source must be normalized or raw")
            if operation == "invalid":
                clauses.append("EXISTS(SELECT 1 FROM json_each(r.errors) f WHERE f.key=?)")
                params.append(name)
                continue
            if name in _COLUMNS and not raw:
                expression = _COLUMNS[name]
            else:
                column = "raw_fields" if raw else "normalized_fields"
                expression = f"(SELECT f.value FROM json_each(r.{column}) f WHERE f.key=?)"
                params.append(name)
            value = predicate.get("value")
            if operation in {"exists", "missing"}:
                clauses.append(
                    expression + (" IS NOT NULL" if operation == "exists" else " IS NULL")
                )
                if operation == "missing" and not raw:
                    clauses.append("NOT EXISTS(SELECT 1 FROM json_each(r.errors) f WHERE f.key=?)")
                    params.append(name)
            elif operation in {"eq", "ne", "gt", "gte", "lt", "lte"}:
                _filter_value(value)
                operator = {
                    "eq": "IS",
                    "ne": "IS NOT",
                    "gt": ">",
                    "gte": ">=",
                    "lt": "<",
                    "lte": "<=",
                }[operation]
                clauses.append(f"{expression} {operator} ?")
                params.append(value)
            elif operation == "contains":
                _filter_value(value)
                clauses.append(f"instr(lower(CAST({expression} AS TEXT)),lower(?))>0")
                params.append(str(value or ""))
            elif operation == "in":
                if not isinstance(value, list) or len(value) > 100:
                    raise ValueError("The in operator requires at most 100 values")
                for item in value:
                    _filter_value(item)
                clauses.append(f"{expression} IN (SELECT value FROM json_each(?))")
                params.append(_dump(value))
            else:
                raise ValueError(f"Unsupported filter operator: {operation}")
        if q:
            if len(q) > 300:
                raise ValueError("Search text exceeds 300 characters")
            clauses.append(
                "(instr(lower(r.raw_fields),lower(?))>0 OR instr(lower(r.reason),lower(?))>0 OR instr(lower(s.name),lower(?))>0)"
            )
            params.extend((q, q, q))
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), params

    def query(
        self,
        filters=(),
        fields=None,
        sort="recorded_at",
        limit=25,
        offset=0,
        include_promoted=False,
        q="",
    ):
        limit, offset = max(1, min(100, int(limit))), max(0, int(offset))
        if fields is not None and (
            not isinstance(fields, list)
            or len(fields) > 1000
            or not all(isinstance(field, str) for field in fields)
        ):
            raise ValueError("Selected fields must be a list")
        key = sort.removeprefix("-").removeprefix("+")
        if key not in _COLUMNS:
            raise ValueError("Unsupported sort field")
        where, params = self._predicate(filters, include_promoted, q)
        with closing(self._connect(readonly=True)) as db:
            db.execute("BEGIN")
            counts = dict(
                db.execute(
                    "SELECT r.outcome,count(*) FROM records r JOIN sources s ON s.import_id=r.import_id"
                    + where
                    + " GROUP BY r.outcome",
                    params,
                ).fetchall()
            )
            rows = db.execute(
                _SELECT
                + where
                + f" ORDER BY {_COLUMNS[key]} {'ASC' if sort.startswith('+') else 'DESC'},r.record_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            )
            items = [self._public(row) for row in rows]
            if fields is not None:
                wanted = set(fields)
                for item in items:
                    for column in ("raw_fields", "normalized_fields", "errors"):
                        item[column] = {
                            key: value for key, value in item[column].items() if key in wanted
                        }
            return {
                "items": items,
                "total": sum(counts.values()),
                "limit": limit,
                "offset": offset,
                "counts": counts,
            }

    def iter_records(self, filters=(), *, include_promoted=False, limit=100000):
        where, params = self._predicate(filters, include_promoted)
        with closing(self._connect(readonly=True)) as db:
            db.execute("BEGIN")
            for row in db.execute(
                _SELECT + where + " ORDER BY r.record_id LIMIT ?",
                [*params, max(0, min(100000, int(limit)))],
            ):
                yield self._public(row)

    def revision(self):
        with closing(self._connect(readonly=True)) as db:
            return db.execute("SELECT revision FROM archive_state WHERE id=1").fetchone()[0]

    def field_catalog(self, report_type=None):
        with closing(self._connect(readonly=True)) as db:
            observed = db.execute("SELECT report_type,name FROM observed_fields").fetchall()
        return catalogue(observed, report_type)

    def facets(self, field, filters=(), limit=50, *, include_promoted=False):
        if not isinstance(field, str) or not field or len(field) > 300:
            raise ValueError("Invalid facet field")
        where, params = self._predicate(filters, include_promoted)
        expression = _COLUMNS.get(field)
        if expression is None:
            expression = "(SELECT f.value FROM json_each(r.normalized_fields) f WHERE f.key=?)"
            params = [field, *params]
        with closing(self._connect(readonly=True)) as db:
            rows = db.execute(
                f"SELECT {expression} value,count(*) count FROM records r JOIN sources s ON s.import_id=r.import_id"
                + where
                + " GROUP BY value ORDER BY count DESC,value LIMIT ?",
                [*params, max(1, min(100, int(limit)))],
            )
            return {"field": field, "items": [dict(row) for row in rows]}


def _source_metadata(imported):
    config = imported.get("config") or {}
    if isinstance(config, str):
        config = json.loads(config)
    return {
        "import_id": imported.get("import_id") or imported["id"],
        "sha256": imported["sha256"],
        "name": imported["name"],
        "path": imported.get("path", ""),
        "report_type": imported.get("report_type") or config.get("report_type", "auto"),
        "schema_version": imported.get("schema_version") or inventory_metadata()["sha256"],
        "acquisition": imported.get("acquisition") or config.get("acquisition", {}),
    }


def _import_source(db, import_id):
    imported = db.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
    if imported is None:
        raise ValueError("Import does not exist")
    return _source_metadata(dict(imported))


def prepare_batch(import_record, rows, *, stage="filter", outcome="rejected", reason=""):
    """Prepare immutable, 500-row deliveries before reserving the workspace writer."""
    source = _source_metadata(import_record)
    prepared, batch = [], []
    stamp = now()
    for row in rows:
        batch.append(_source_row(row))
        if len(batch) == 500:
            prepared.append(
                (
                    uuid4().hex,
                    "records",
                    _dump(
                        {
                            "source": source,
                            "rows": batch,
                            "stage": stage,
                            "outcome": outcome,
                            "reason": reason,
                        }
                    ),
                    stamp,
                )
            )
            batch = []
    if batch:
        prepared.append(
            (
                uuid4().hex,
                "records",
                _dump(
                    {
                        "source": source,
                        "rows": batch,
                        "stage": stage,
                        "outcome": outcome,
                        "reason": reason,
                    }
                ),
                stamp,
            )
        )
    return tuple(prepared)


def enqueue_prepared(db, prepared):
    """Publish prepared deliveries atomically with the caller's stage completion."""
    db.executemany(
        "INSERT INTO dark_matter_outbox(event_id,operation,payload,recorded_at) VALUES(?,?,?,?)",
        prepared,
    )
    return tuple(event[0] for event in prepared)


def enqueue_batch(db, import_id, rows, *, stage="filter", outcome="rejected", reason=""):
    """Enqueue source records in the caller's transaction; rollback means no delivery."""
    source = _import_source(db, import_id)
    return enqueue_prepared(
        db, prepare_batch(source, rows, stage=stage, outcome=outcome, reason=reason)
    )


def enqueue_outcome(db, import_id, entries, *, stage, outcome, reason=""):
    """Callers identify source entries; Dark Matter owns their archive identities."""
    source = _import_source(db, import_id)
    ids = [
        source_record_id(source["sha256"], sheet, number)
        for _, sheet, number in map(_source_position, entries)
    ]
    event_id, stamp = uuid4().hex, now()
    payload = {
        "record_ids": ids,
        "import_id": import_id,
        "stage": stage,
        "outcome": outcome,
        "reason": reason,
    }
    db.execute(
        "INSERT INTO dark_matter_outbox(event_id,operation,payload,recorded_at) VALUES(?,?,?,?)",
        (event_id, "outcome", _dump(payload), stamp),
    )
    return event_id


def enqueue_outcomes(db, import_id, decisions, *, stage):
    """Batch per-row decisions without copying or normalizing the source again."""
    grouped = {}
    for entry, outcome, reason in decisions:
        grouped.setdefault((outcome, reason), []).append(entry)
    for (outcome, reason), entries in grouped.items():
        enqueue_outcome(db, import_id, entries, stage=stage, outcome=outcome, reason=reason)


def drain(root, *, archive=None):
    """Deliver committed events in order; a crash before acknowledgement replays safely."""
    root = Path(root)
    delivered = 0
    with closing(sqlite3.connect(root / "workbench.sqlite3", timeout=15)) as db:
        db.row_factory = sqlite3.Row
        while row := db.execute(
            "SELECT * FROM dark_matter_outbox ORDER BY sequence LIMIT 1"
        ).fetchone():
            if archive is None:
                archive = DarkMatterStore(root)
            payload = json.loads(row["payload"])
            method = (
                archive.record_batch if row["operation"] == "records" else archive.record_outcome
            )
            method(**payload, event_id=row["event_id"], recorded_at=row["recorded_at"])
            with db:
                db.execute("DELETE FROM dark_matter_outbox WHERE event_id=?", (row["event_id"],))
            delivered += 1
    return delivered


def archive_counts(db):
    """Read diagnostics from an existing archive snapshot without opening storage."""
    records, unpromoted, invalid = db.execute(
        "SELECT count(*),coalesce(sum(promoted=0),0),coalesce(sum(errors<>'{}'),0) FROM records"
    ).fetchone()
    return {
        "records": records,
        "unpromoted_records": unpromoted,
        "invalid_records": invalid,
        "outcomes": db.execute("SELECT count(*) FROM outcomes").fetchone()[0],
        "revision": db.execute("SELECT revision FROM archive_state WHERE id=1").fetchone()[0],
    }


def delivery_status(db):
    """Read delivery backlog from the caller's workspace snapshot."""
    pending, oldest = db.execute(
        "SELECT count(*),min(recorded_at) FROM dark_matter_outbox"
    ).fetchone()
    return {"pending": pending, "oldest_pending_at": oldest}
