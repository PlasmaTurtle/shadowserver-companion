"""Revision-bound citation metadata for reusable advisory blocks."""

import json

from .primitives import dump, now


def metadata_key(block_id, revision):
    return f"block-sources:{block_id}:{revision}"


def snapshot_blocks(db):
    blocks = [dict(row) for row in db.execute("SELECT * FROM explainers ORDER BY rowid")]
    for block in blocks:
        row = db.execute(
            "SELECT payload FROM cache WHERE key=?", (metadata_key(block["id"], block["revision"]),)
        ).fetchone()
        if row:
            block["source_metadata"] = json.loads(row["payload"])
    return blocks


def save_source_metadata(db, block_id, revision, metadata):
    # Each library update increments its revision. Old citation metadata remains
    # available to pinned drafts and certified snapshots.
    db.execute(
        "INSERT INTO cache(key,payload,retrieved_at) VALUES(?,?,?)",
        (metadata_key(block_id, revision), dump(metadata), now()),
    )
