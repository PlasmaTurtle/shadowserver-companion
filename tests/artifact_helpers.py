"""Fault injection for isolated temporary workspaces, never application commands."""


def remove_artifact_commit(db, kind, artifact_id):
    """Model a rename followed by a lost DB commit, preserving production guards.

    Tests start with a known completed package, then remove exactly the rows the
    publication transaction would not have committed. Restore the guard before
    leaving this test transaction; historical artifacts are never mutable in use.
    """
    trigger = db.execute(
        "SELECT sql FROM sqlite_master WHERE name='immutable_artifact_records_delete'"
    ).fetchone()
    if trigger:
        db.execute("DROP TRIGGER immutable_artifact_records_delete")
        db.execute(
            "DELETE FROM artifact_records WHERE kind=? AND artifact_id=?", (kind, artifact_id)
        )
        db.execute(trigger[0])
    table = {"report": "reports", "closure": "case_closures"}[kind]
    db.execute(f"DELETE FROM {table} WHERE id=?", (artifact_id,))
