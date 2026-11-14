"""Workspace priority queue from saved case facts; no network or workflow writes."""

import json
from datetime import date

from .services.case_queries import list_cases
from .contact_outcomes import contact_summaries
from .finding_history import entity_finding_history
from .case_guidance import saved_case_facts, working_case_action, working_case_signals
from .repositories.records import Records
from .intelligence_index import notification_records


def workspace_queue(store, as_of=None, limit=100):
    # Reuse one read-only snapshot for contact/history facts. Reopening SQLite
    # for every entity repeatedly discards its page cache on a large workspace.
    with store.read_snapshot() as db:
        return _workspace_queue(store, db, as_of, limit)


def _workspace_queue(store, db, as_of, limit):
    day = (as_of or date.today()).isoformat()
    reader = Records(db)
    # Rank all eligible work, but choose candidates before decoding historical
    # drafts, counting their source scope or preparing contact projections.
    candidates = reader.all(
        "SELECT id,entity_id,stage,updated_at FROM cases ORDER BY updated_at DESC,rowid DESC"
    )
    policies = {r["case_id"]: r for r in reader.all("SELECT * FROM case_outreach_policy")}
    from .repositories.lead_scopes import pending_counts

    unassigned = pending_counts(db)
    latest = {}
    for row in candidates:
        latest.setdefault(row["entity_id"], row["id"])
    eligible, decisions, histories, held = [], {}, {}, 0
    for row in candidates:
        policy = policies.get(row["id"], {"state": "active", "review_on": None, "reason": ""})
        reconsider = bool(policy.get("review_on") and policy["review_on"] <= day)
        new_observations = (
            unassigned.get(row["entity_id"], 0) if latest[row["entity_id"]] == row["id"] else 0
        )
        material_review = False
        if policy["state"] != "active" and not reconsider:
            if new_observations:
                if row["entity_id"] not in histories:
                    histories[row["entity_id"]] = entity_finding_history(
                        db, row["entity_id"], limit=None
                    )
                material_review = any(
                    item["material_change"]
                    and item["material_change_acquired_at"] > policy.get("changed_at", "")
                    for item in histories[row["entity_id"]]["items"]
                )
            if not material_review:
                held += 1
                continue
        if row["stage"] == "closed" and not reconsider and not new_observations:
            continue
        eligible.append(row["id"])
        decisions[row["id"]] = policy, reconsider, new_observations, material_review
    rows = list_cases(store, db=db, case_ids=eligible)
    selection = json.dumps(eligible)
    details = {
        r["id"]: r
        for r in reader.all(
            "SELECT id,draft,entity_snapshot,contact_email,contact_phone FROM cases WHERE id IN (SELECT value FROM json_each(?))",
            (selection,),
        )
    }
    guidance = saved_case_facts(db, eligible)
    settings = store.settings(db=db)
    reported_critical = {
        r["case_id"]
        for r in reader.all(
            """WITH selected AS MATERIALIZED (
            SELECT id,draft FROM cases WHERE id IN (SELECT value FROM json_each(?))
          ), excluded AS MATERIALIZED (
            SELECT c.id case_id,s.key entry_id FROM selected c
            JOIN json_each(c.draft,'$.observation_scope') s
            WHERE json_extract(s.value,'$.decision')='exclude'
          ) SELECT DISTINCT ce.case_id FROM selected c
          JOIN case_entries ce ON ce.case_id=c.id JOIN entries e ON e.id=ce.entry_id
          LEFT JOIN case_entry_conditions cc ON cc.case_id=c.id AND cc.entry_id=e.id
          LEFT JOIN excluded x ON x.case_id=c.id AND x.entry_id=e.id
          WHERE lower(json_extract(e.payload,'$.source.fields.severity'))='critical'
          AND (cc.conditions IS NULL OR json_array_length(cc.conditions)>0)
          AND x.entry_id IS NULL""",
            (selection,),
        )
    }
    contacts = contact_summaries(store, [row["entity_id"] for row in rows], db=db)
    items = []
    for row in rows:
        policy, reconsider, new_observations, material_review = decisions[row["id"]]
        facts = details[row["id"]]
        draft = json.loads(facts["draft"])
        records = notification_records(draft)
        source_critical = row["id"] in reported_critical
        if row["stage"] == "in_progress":
            from .intelligence_index import flags

            records, source_critical = working_case_signals(guidance[row["id"]], draft)
            row.update(flags(records))
        critical = source_critical or any(
            str(r.get("severity", "")).lower() == "critical"
            or (isinstance(r.get("cvss"), (int, float)) and r["cvss"] >= 9)
            for r in records
        )
        due = bool(
            row.get("follow_up_date") and row["follow_up_date"] <= day and row["stage"] != "closed"
        )
        intake_score = row.get("intake_score")
        reasons = []
        if intake_score:
            reasons.append(
                f"Accretion priority: {intake_score['temperature'].title()} · {intake_score['aggregate']:g}/100"
            )
        section, action_code = "", "workflow"
        if reconsider:
            reasons.append("Outreach decision due for reconsideration")
        if due:
            reasons.append("Follow-up due")
        if row.get("kev"):
            reasons.append("Known exploited vulnerability in saved sources")
        if critical:
            reasons.append("Critical severity in saved sources or retained report rows")
        if new_observations:
            reasons.append(f"{new_observations} observations outside prior notification scope")
        contact = contacts[row["entity_id"]]["has_usable_contact"]
        if reconsider:
            action, tab = (
                "Review outreach decision; retain the hold until explicitly changed"
                if policy["state"] != "active"
                else "Review the scheduled outreach decision",
                "contact",
            )
        elif material_review:
            action, tab = "Review changed findings; outreach remains on hold", "contact"
        elif row["stage"] == "closed" or new_observations and row["stage"] != "in_progress":
            action, tab = "Compare later findings with prior notification", "contact"
        elif row.get("next_action") and not (
            row["stage"] == "notification_completed"
            and row["next_action"] == "Prepare closing report"
        ):
            action, tab = row["next_action"], "contact"
        elif row["stage"] == "pending_notification":
            action, tab = (
                (
                    "Review an available contact and prepare outreach"
                    if contact
                    else "Find or review a suitable contact"
                ),
                "contact",
            )
            if contact and not (settings.get("outreach_verification_route") or "").strip():
                action = "Configure a public verification route before preparing outreach"
                action_code = "verification_route"
        elif row["stage"] == "notification_completed":
            action, tab = "Document the outcome and complete the closing report", "closing"
        else:
            action, tab, section, action_code = working_case_action(
                guidance[row["id"]], draft, json.loads(facts["entity_snapshot"] or "{}"), settings
            )
        if not contact and row["stage"] == "pending_notification":
            reasons.append("Contact route needs review")
        if not reasons:
            reasons.append("Active notification case")
        row.update(
            priority_reasons=reasons,
            suggested_action=action,
            action_tab=tab,
            action_section=section,
            action_code=action_code,
            urgency="known_exploited" if row.get("kev") else "critical" if critical else "standard",
            contact_recorded=contact,
            outreach_policy=policy,
            reconsideration_due=reconsider,
            later_observations=new_observations,
            material_change_review=material_review,
        )
        rank = (
            not (reconsider or due),
            intake_score is None,
            -intake_score["aggregate"] if intake_score else 0,
            not bool(row.get("kev")),
            not critical,
            not bool(new_observations),
            row["stage"] != "pending_notification",
            row.get("follow_up_date") or "9999",
            row["id"],
        )
        items.append((rank, row))
    items.sort(key=lambda item: item[0])
    return {
        "as_of": day,
        "items": [row for _, row in items[:limit]],
        "total": len(items),
        "held": held,
        "limit": limit,
        "truncated": len(items) > limit,
        "basis": "Due reviews and follow-ups, saved Accretion priority, then saved exploitation/severity signals, later observations and delivery readiness. Priority does not bypass outreach holds.",
    }
