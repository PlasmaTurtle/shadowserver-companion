"""Revision-checked explainer lifecycle; case/report snapshots are never edited here."""

import json

from modules.workspace.components.primitives import now, uid
from ..repositories import content


class ExplainerConflict(ValueError):
    def __init__(self, current):
        self.current = current
        super().__init__(
            "This explainer changed in another window. Your draft is retained; compare the current revision before saving."
        )


class ContentService:
    def __init__(self, store):
        self.store = store

    def list(self, *, include_archived=False):
        with self.store.read_snapshot() as db:
            return content.blocks(db, include_archived=include_archived)

    def get(self, block_id):
        with self.store.read_snapshot() as db:
            return content.current(db, block_id)

    @staticmethod
    def _check(db, block_id, expected_revision):
        block = content.current(db, block_id)
        if block["revision"] != expected_revision:
            raise ExplainerConflict(block)
        return block

    def _record(self, db, block, action, *, restored_from=None):
        profile = db.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
        actor = str(json.loads(profile[0]).get("analyst_name") or "").strip() if profile else ""
        content.publish(db, block, actor=actor, action=action, restored_from=restored_from)
        self.store.log(
            db,
            "explainer_" + action,
            f"{block['title']} — revision {block['revision']}",
            metadata={
                "explainer_id": block["id"],
                "revision": block["revision"],
                "restored_from": restored_from,
            },
        )
        return content.current(db, block["id"])

    def create(self, values):
        block = {**values, "id": uid(), "revision": 1, "updated_at": now(), "archived_at": ""}
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO explainers(id,title,body,sources,revision,updated_at) VALUES(?,?,?,?,?,?)",
                tuple(
                    block[key]
                    for key in ("id", "title", "body", "sources", "revision", "updated_at")
                ),
            )
            return self._record(db, block, "created")

    def update(self, block_id, values, expected_revision):
        with self.store.transaction() as db:
            prior = self._check(db, block_id, expected_revision)
            if prior["archived_at"]:
                raise ValueError("Restore this archived explainer before editing it")
            if "source_metadata" not in values:
                urls = {line.strip() for line in values["sources"].splitlines() if line.strip()}
                values = {
                    **values,
                    "source_metadata": [
                        item for item in prior.get("source_metadata", []) if item["url"] in urls
                    ],
                }
            block = {**prior, **values, "revision": prior["revision"] + 1, "updated_at": now()}
            return self._record(db, block, "updated")

    def archive(self, block_id, expected_revision, archived):
        with self.store.transaction() as db:
            prior = self._check(db, block_id, expected_revision)
            if bool(prior["archived_at"]) == archived:
                return prior
            stamp = now()
            block = {
                **prior,
                "revision": prior["revision"] + 1,
                "updated_at": stamp,
                "archived_at": stamp if archived else "",
            }
            return self._record(db, block, "archived" if archived else "unarchived")

    def restore(self, block_id, number, expected_revision):
        with self.store.transaction() as db:
            prior = self._check(db, block_id, expected_revision)
            old = content.revision(db, block_id, number)
            block = {key: old[key] for key in ("id", "title", "body", "sources", "source_metadata")}
            block.update(revision=prior["revision"] + 1, updated_at=now(), archived_at="")
            return self._record(db, block, "restored", restored_from=number)

    def revision(self, block_id, number):
        with self.store.read_snapshot() as db:
            return content.revision(db, block_id, number)

    def history(self, block_id, *, before=None, limit=30):
        with self.store.read_snapshot() as db:
            block = content.current(db, block_id)
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT revision,title,updated_at,actor,action,restored_from,archived_at "
                    "FROM explainer_revisions WHERE block_id=?"
                    + (" AND revision<?" if before is not None else "")
                    + " ORDER BY revision DESC LIMIT ?",
                    [block_id, *([before] if before is not None else []), limit + 1],
                )
            ]
            earliest = db.execute(
                "SELECT min(revision) FROM explainer_revisions WHERE block_id=?", (block_id,)
            ).fetchone()[0]
        return {
            "items": rows[:limit],
            "current_revision": block["revision"],
            "earliest_revision": earliest,
            "next_before": rows[limit - 1]["revision"] if len(rows) > limit else None,
        }

    def usage(self, block_id, *, limit=50, offset=0):
        # Query actual selections, not the full bank pinned as available in every draft.
        with self.store.read_snapshot() as db:
            content.current(db, block_id)
            where = " WHERE EXISTS(SELECT 1 FROM json_each(c.draft,'$.selected_explainers') selected WHERE selected.value=?)"
            total = db.execute("SELECT count(*) FROM cases c" + where, (block_id,)).fetchone()[0]
            rows = db.execute(
                "SELECT c.id,c.entity_id,c.title,c.stage,c.draft,c.certified_report_id FROM cases c"
                + where
                + " ORDER BY c.updated_at DESC,c.id LIMIT ? OFFSET ?",
                (block_id, limit, offset),
            ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                draft = json.loads(item.pop("draft"))
                pinned = next(
                    (b for b in draft.get("explainer_snapshots", []) if b.get("id") == block_id),
                    None,
                )
                item["explainer_revision"] = pinned.get("revision") if pinned else None
                item["has_case_wording"] = block_id in draft.get("explainer_overrides", {})
                items.append(item)
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "scope": "Current case selections; historical report packages retain their own copies.",
        }
