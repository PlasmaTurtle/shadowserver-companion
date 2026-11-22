"""Apply a report's case/entity transition in the caller's publication transaction."""


def activate_report(
    db,
    *,
    case_id,
    entity_id,
    report_id,
    draft_revision,
    updated_at,
    expected_version=None,
):
    """Return false for stale work without changing its case or entity.

    The service has already checked the report's evidence and review readiness.
    Older package manifests lack a case version; they retain their stage, draft
    and owner guards. This function neither opens nor commits a transaction.
    """
    changed = db.execute(
        """UPDATE cases
        SET stage='pending_notification',certified_report_id=?,version=version+1,updated_at=?
        WHERE id=? AND entity_id=? AND stage='in_progress' AND draft_revision=?
          AND (? IS NULL OR version=?)""",
        (
            report_id,
            updated_at,
            case_id,
            entity_id,
            draft_revision,
            expected_version,
            expected_version,
        ),
    )
    if changed.rowcount != 1:
        return False
    db.execute(
        "UPDATE leads SET status='completed',new_observations=0,updated_at=? WHERE id=?",
        (updated_at, entity_id),
    )
    return True
