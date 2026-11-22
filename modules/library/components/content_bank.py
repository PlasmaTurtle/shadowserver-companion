"""Library's active explainer snapshot and initial-content boundary."""

from modules.workspace.components.primitives import now
from ..resources.defaults import EXPLAINERS
from .repositories import content


def snapshot_blocks(db):
    """Capture active wording; previously pinned/report snapshots remain independent."""
    return content.blocks(db)


def seed_defaults(db):
    """Seed missing defaults and their history in the caller's startup transaction."""
    for key, title, body, sources in EXPLAINERS:
        db.execute(
            "INSERT OR IGNORE INTO explainers(id,title,body,sources,revision,updated_at) VALUES(?,?,?,?,1,?)",
            (key, title, body, sources, now()),
        )
        db.execute("INSERT OR IGNORE INTO explainer_state(block_id) VALUES(?)", (key,))
        block = content.current(db, key)
        if not db.execute(
            "SELECT 1 FROM explainer_revisions WHERE block_id=? AND revision=?",
            (key, block["revision"]),
        ).fetchone():
            content.retain(db, block, action="seeded")
