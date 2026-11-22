"""Library's active explainer snapshot and initial-content boundary."""

from modules.workspace.components.primitives import now
from ..resources.defaults import CITATION_TITLES, EXPLAINERS, PREVIOUS_EXPLAINERS
from .repositories import content


def snapshot_blocks(db):
    """Capture active wording; previously pinned/report snapshots remain independent."""
    return content.blocks(db)


def seed_defaults(db):
    """Seed new workspaces or advance an untouched shipped edition, preserving its history."""
    previous = {key: (title, body, sources) for key, title, body, sources in PREVIOUS_EXPLAINERS}
    for key, title, body, sources in EXPLAINERS:
        inserted = db.execute(
            "INSERT OR IGNORE INTO explainers(id,title,body,sources,revision,updated_at) VALUES(?,?,?,?,1,?)",
            (key, title, body, sources, now()),
        ).rowcount
        db.execute("INSERT OR IGNORE INTO explainer_state(block_id) VALUES(?)", (key,))
        block = content.current(db, key)
        publisher, source_title = CITATION_TITLES[key]
        citations = [
            {
                "url": sources,
                "publisher": publisher,
                "title": source_title,
                "retrieved_at": "2026-11-22",
            }
        ]
        if inserted:
            block["source_metadata"] = citations
        if not db.execute(
            "SELECT 1 FROM explainer_revisions WHERE block_id=? AND revision=?",
            (key, block["revision"]),
        ).fetchone():
            content.retain(db, block, action="seeded")
        if (
            block["revision"] == 1
            and not block["archived_at"]
            and block["origin"] == "bundled"
            and not block.get("source_metadata")
            and (title, body, sources) != previous.get(key)
            and tuple(block[field] for field in ("title", "body", "sources")) == previous.get(key)
        ):
            block.update(
                title=title,
                body=body,
                sources=sources,
                source_metadata=citations,
                revision=2,
                updated_at=now(),
            )
            content.publish(db, block, actor="Library", action="bundled_update")
