"""Library research queries and workspace-owned saved selections."""

import hashlib
import json
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from modules.workspace.components.primitives import now, uid


class FieldSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(max_length=200)
    value: str = Field(max_length=2000)


class ArchiveSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=200)
    field: str = Field(default="", max_length=200)
    operator: Literal[
        "eq", "ne", "contains", "gt", "gte", "lt", "lte", "exists", "missing", "invalid"
    ] = "eq"
    value: str = Field(default="", max_length=2000)
    source: Literal["normalized", "raw"] = "normalized"


class ResearchSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    view: Literal["products", "cves", "fields", "changes", "dark-matter"] = "products"
    query: str = Field(default="", max_length=200)
    scope: Literal["critical", "critical_kev", "kev", "all"] = "critical"
    productId: str = Field(default="", max_length=100)
    version: str = Field(default="", max_length=200)
    field: str = Field(default="weakness", max_length=200)
    fieldSelection: FieldSelection | None = None
    cveQuery: str = Field(default="", max_length=200)
    cveSeverity: Literal["", "CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "UNKNOWN"] = "CRITICAL"
    selectedCve: str = Field(default="", pattern=r"^(?:CVE-\d{4}-\d{4,})?$", max_length=80)
    darkMatterSelection: ArchiveSelection = Field(default_factory=ArchiveSelection)


class SavedViewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    selection: ResearchSelection


class SavedViewUpdate(SavedViewInput):
    expected_revision: int = Field(ge=1, strict=True)


class SavedViewImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    views: list[SavedViewInput] = Field(max_length=100)


class SavedViewConflict(ValueError):
    pass


def _record(row):
    return {
        **{k: row[k] for k in ("id", "name", "revision", "created_at", "updated_at")},
        "selection": json.loads(row["selection"]),
    }


def _selection(value):
    return json.dumps(
        value.model_dump(),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


class Research:
    """Small local application service; reference results never mutate casework."""

    def __init__(self, store, catalog):
        self.store, self.catalog = store, catalog

    def views(self):
        with self.store.read_snapshot() as db:
            return [
                _record(row)
                for row in db.execute(
                    "SELECT * FROM library_saved_views ORDER BY updated_at DESC,id"
                )
            ]

    def create_view(self, body):
        identity, stamp = uid(), now()
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO library_saved_views VALUES(?,?,?,?,?,?,NULL)",
                (identity, body.name, _selection(body.selection), 1, stamp, stamp),
            )
            return _record(
                db.execute("SELECT * FROM library_saved_views WHERE id=?", (identity,)).fetchone()
            )

    def update_view(self, identity, body):
        with self.store.transaction() as db:
            changed = db.execute(
                "UPDATE library_saved_views SET name=?,selection=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                (body.name, _selection(body.selection), now(), identity, body.expected_revision),
            )
            if not changed.rowcount:
                self._conflict(db, identity)
            return _record(
                db.execute("SELECT * FROM library_saved_views WHERE id=?", (identity,)).fetchone()
            )

    def delete_view(self, identity, revision):
        with self.store.transaction() as db:
            if not db.execute(
                "DELETE FROM library_saved_views WHERE id=? AND revision=?", (identity, revision)
            ).rowcount:
                self._conflict(db, identity)
        return {"ok": True}

    @staticmethod
    def _conflict(db, identity):
        if not db.execute("SELECT 1 FROM library_saved_views WHERE id=?", (identity,)).fetchone():
            raise KeyError("Saved view not found")
        raise SavedViewConflict(
            "This saved view changed in another window. Reload before replacing it."
        )

    def import_views(self, body):
        with self.store.transaction() as db:
            for view in body.views:
                selection = _selection(view.selection)
                key = hashlib.sha256((view.name + "\0" + selection).encode()).hexdigest()
                stamp = now()
                db.execute(
                    "INSERT OR IGNORE INTO library_saved_views VALUES(?,?,?,?,?,?,?)",
                    (uid(), view.name, selection, 1, stamp, stamp, key),
                )
        return self.views()

    def search(self, query, limit):
        query = query.strip()
        empty = {"items": [], "total": 0, "error": None}
        groups = {key: dict(empty) for key in ("cves", "products", "explainers")}
        if not query:
            return {"query": query, "groups": groups}
        for kind, search in (
            ("cves", lambda: self.catalog.catalog.search(query, limit=limit, severity="")),
            ("products", lambda: self.catalog.catalog.products(query, scope="all", limit=limit)),
        ):
            try:
                value = search()
                groups[kind] = {"items": value["items"], "total": value["total"], "error": None}
            except (OSError, ValueError, sqlite3.Error):
                groups[kind]["error"] = (
                    "Local reference data is unavailable. Review catalog status."
                )
        term = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        try:
            with self.store.read_snapshot() as db:
                base = " FROM explainers e LEFT JOIN explainer_state s ON s.block_id=e.id WHERE coalesce(s.archived_at,'')='' AND e.title LIKE ? ESCAPE '\\'"
                total = db.execute("SELECT count(*)" + base, (term,)).fetchone()[0]
                rows = db.execute(
                    "SELECT e.id,e.title,e.revision" + base + " ORDER BY e.title,e.id LIMIT ?",
                    (term, limit),
                )
                groups["explainers"] = {
                    "items": [dict(row) for row in rows],
                    "total": total,
                    "error": None,
                }
        except (OSError, ValueError, sqlite3.Error):
            groups["explainers"]["error"] = (
                "Explainers are unavailable. Try loading the explanation panel again."
            )
        return {"query": query, "groups": groups}
