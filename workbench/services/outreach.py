"""Reasoned outreach-policy writes; report content remains unchanged."""

from ..primitives import now


def save_policy(store, case_id, values):
    from ..cases import Cases

    actor = store.settings().get("analyst_name", "").strip()
    if not actor:
        raise ValueError("Set the analyst name in Settings before recording a decision")
    with store.transaction() as db:
        case = Cases(store).require(db, case_id, values["expected_version"])
        stamp = now()
        db.execute(
            """INSERT INTO case_outreach_policy VALUES(?,?,?,?,?,?)
          ON CONFLICT(case_id) DO UPDATE SET state=excluded.state,reason=excluded.reason,
          review_on=excluded.review_on,changed_by=excluded.changed_by,changed_at=excluded.changed_at""",
            (case_id, values["state"], values["reason"], values.get("review_on"), actor, stamp),
        )
        db.execute("UPDATE cases SET version=version+1,updated_at=? WHERE id=?", (stamp, case_id))
        store.log(
            db,
            "outreach_policy_changed",
            f"{actor}: {values['state']}; review {values.get('review_on') or 'not scheduled'}; {values['reason']}",
            case["entity_id"],
            case_id,
        )
    return Cases(store).view(case_id)
