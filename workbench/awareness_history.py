"""Entity finding history from canonical membership, with immutable report links."""

import json

from .intake.versions import entry_fields
from .case_conditions import notified_cve_exclusions
from .awareness import conditions
from .awareness_admission import facts_sql, state_sql
from . import ownership


def _version(row, *, approved=False):
    if approved and "approved_facts" in row.keys() and row["approved_facts"]:
        return json.loads(row["approved_facts"]).get("version", "")
    return entry_fields(
        {
            "source": {"fields": json.loads(row["summary"])},
            "normalized": json.loads(row["normalized"]),
        }
    ).get("version", "")


def entity_history(db, entity_id, *, limit=250):
    owner = "f.entity_id" if ownership.available(db) else "a.entity_id"
    pair_state = state_sql(db)
    rows = db.execute(
        """SELECT f.*,a.hostname,o.ip,o.summary,o.normalized
      FROM awareness_findings f JOIN awareness_assets a ON a.id=f.asset_id
      JOIN awareness_observations o ON o.id=f.latest_observation_id
      WHERE """
        + owner
        + """ IN(SELECT id FROM leads WHERE id=? OR merged_into=?) AND f.admitted=1 ORDER BY f.changed_at DESC,f.id""",
        (entity_id, entity_id),
    ).fetchall()
    facts = {
        row["id"]: {
            "observations": 0,
            "reported": 0,
            "legacy_unknown": 0,
            "reported_moments": set(),
            "latest_reported": None,
            "latest_approved": None,
            "days": set(),
            "moments": set(),
            "versions": set(),
            "notifications": {},
            "covered_versions": set(),
            "covered_observed": "",
        }
        for row in rows
    }
    ids = list(facts)
    exclusions = notified_cve_exclusions(db, entity_id) if ids else {}
    for start in range(0, len(ids), 350):
        batch = ids[start : start + 350]
        marks = ",".join("?" for _ in batch)
        for observation in db.execute(
            "SELECT m.finding_id,"
            + pair_state
            + " admission_state,"
            + facts_sql(db)
            + " approved_facts,o.* FROM awareness_memberships m JOIN awareness_observations o ON o.id=m.observation_id WHERE m.finding_id IN ("
            + marks
            + ")",
            batch,
        ):
            fact = facts[observation["finding_id"]]
            fact["reported"] += 1
            if observation["observed_at"]:
                fact["reported_moments"].add(observation["observed_at"])
            if fact["latest_reported"] is None or (
                observation["observed_at"],
                observation["id"],
            ) > (fact["latest_reported"]["observed_at"], fact["latest_reported"]["id"]):
                fact["latest_reported"] = observation
            if observation["admission_state"] == "legacy_unknown":
                fact["legacy_unknown"] += 1
            if observation["admission_state"] != "admitted":
                continue
            if fact["latest_approved"] is None or (
                observation["observed_at"],
                observation["id"],
            ) > (fact["latest_approved"]["observed_at"], fact["latest_approved"]["id"]):
                fact["latest_approved"] = observation
            fact["observations"] += 1
            if observation["observed_at"]:
                fact["days"].add(observation["observed_at"][:10])
                fact["moments"].add(observation["observed_at"])
            fact["versions"].add(str(_version(observation, approved=True)))
        for notification in db.execute(
            """SELECT DISTINCT m.finding_id,f.condition,s.entry_id,r.id report_id,r.case_id,r.revision,r.sent_at,e.observed_at,e.payload
          FROM awareness_memberships m JOIN awareness_findings f ON f.id=m.finding_id
          JOIN awareness_observations o ON o.id=m.observation_id
          JOIN awareness_sources s ON s.observation_id=o.id
          JOIN case_entries ce ON ce.entry_id=s.entry_id
          JOIN cases c ON c.id=ce.case_id
          JOIN reports r ON r.case_id=ce.case_id
          JOIN entries e ON e.id=ce.entry_id
          LEFT JOIN case_entry_conditions scope ON scope.case_id=ce.case_id AND scope.entry_id=ce.entry_id
          WHERE r.sent_at IS NOT NULL AND c.entity_id IN(SELECT id FROM leads WHERE id=? OR merged_into=?) AND m.finding_id IN ("""
            + marks
            + ") AND (scope.case_id IS NULL OR EXISTS(SELECT 1 FROM json_each(scope.conditions) WHERE value=f.condition)) AND NOT EXISTS(SELECT 1 FROM json_each(c.draft,'$.observation_scope') decision WHERE decision.key=e.id AND json_extract(decision.value,'$.decision')='exclude')",
            (entity_id, entity_id, *batch),
        ):
            if notification["condition"] in exclusions.get(notification["case_id"], ()):
                continue
            payload = json.loads(notification["payload"])
            if notification["condition"] not in {condition for condition, _ in conditions(payload)}:
                continue
            fact = facts[notification["finding_id"]]
            fact["notifications"][notification["report_id"]] = {
                key: notification[key]
                for key in ("entry_id", "report_id", "case_id", "revision", "sent_at")
            }
            fact["covered_versions"].add(str(entry_fields(payload).get("version", "")))
            fact["covered_observed"] = max(fact["covered_observed"], notification["observed_at"])
    latest_day = max((max(fact["moments"], default="")[:10] for fact in facts.values()), default="")
    totals = {
        "new": 0,
        "seen_again": 0,
        "changed": 0,
        "covered": 0,
        "not_seen": 0,
        "qualification_unknown": 0,
    }
    items = []
    for row in rows:
        fact = facts[row["id"]]
        approved = fact["latest_approved"]
        display = approved or fact["latest_reported"] or row
        latest_version = str(_version(approved, approved=True)) if approved else ""
        first_seen = min(fact["moments"], default="")
        last_seen = max(fact["moments"], default="")
        if not approved:
            state = "qualification_unknown"
        elif latest_day and last_seen[:10] < latest_day:
            state = "not_seen"
        elif fact["notifications"] and latest_version not in fact["covered_versions"]:
            state = "changed"
        elif not fact["notifications"] and len(fact["versions"]) > 1:
            state = "changed"
        elif fact["notifications"] and last_seen <= fact["covered_observed"]:
            state = "covered"
        elif len(fact["moments"]) > 1:
            state = "seen_again"
        else:
            state = "new"
        totals[state] += 1
        fields = json.loads(display["summary"])
        items.append(
            {
                "finding_id": row["id"],
                "asset_id": row["asset_id"],
                "hostname": row["hostname"],
                "ip": display["ip"],
                "protocol": str(fields.get("protocol") or ""),
                "port": str(fields.get("port") or ""),
                "finding": row["condition"],
                "observations": fact["observations"],
                "observation_days": len(fact["days"]),
                "first_observed": first_seen,
                "last_observed": last_seen,
                "reported_observation_count": fact["reported"],
                "approved_observation_count": fact["observations"],
                "legacy_unknown_observation_count": fact["legacy_unknown"],
                "observed_only_observation_count": fact["reported"]
                - fact["observations"]
                - fact["legacy_unknown"],
                "first_reported": min(fact["reported_moments"], default=""),
                "last_reported": max(fact["reported_moments"], default=""),
                "latest_reported_version": str(_version(fact["latest_reported"]))
                if fact["latest_reported"]
                else "",
                "legacy_first_observed": row["first_seen"],
                "legacy_last_observed": row["last_seen"],
                "versions": sorted(fact["versions"]),
                "latest_version": latest_version,
                "material_change_acquired_at": row["changed_at"] if approved else "",
                "notifications": sorted(
                    fact["notifications"].values(), key=lambda n: (n["sent_at"], n["report_id"])
                ),
                "state": state,
                "material_change": state in ("new", "changed"),
                "workflow": row["workflow"],
            }
        )
    items.sort(
        key=lambda item: (
            not item["material_change"],
            item["hostname"],
            item["finding"],
            item["ip"],
        )
    )
    return {
        "counts": totals,
        "total": len(items),
        "items": items if limit is None else items[:limit],
        "truncated": limit is not None and len(items) > limit,
        "latest_observed_date": latest_day or None,
        "coverage": "unknown",
        "basis": "Condition-specific approval with distinct reported, approved and legacy-unknown observations. Unknown historical qualification does not establish recurrence or material change. Not seen does not mean remediated.",
    }
