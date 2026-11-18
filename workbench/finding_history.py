"""Read-only finding recurrence from retained source occurrences, never remediation."""

import hashlib
import json

from .intelligence.identifiers import identifiers
from .intake.versions import selected_version
from .intake.identity import signature
from .case_conditions import notified_cve_exclusions


def _facts(row):
    payload = json.loads(row["payload"])
    fields = payload.get("source", {}).get("fields", {})
    return payload, fields


def entity_finding_history(db, entity_id, *, limit=250):
    from .awareness import available

    if available(db):
        from .awareness_history import entity_history

        return entity_history(db, entity_id, limit=limit)
    rows = db.execute(
        "SELECT e.*,i.created_at acquisition_at FROM entries e LEFT JOIN imports i ON i.id=e.import_id WHERE e.lead_id=? ORDER BY e.observed_at,e.rowid",
        (entity_id,),
    ).fetchall()
    rows = [dict(row) for row in rows]
    memories = {
        row["signal_key"]: dict(row)
        for row in db.execute(
            "SELECT o.*,i.created_at acquisition_at FROM intake_observations o JOIN imports i ON i.id=o.import_id WHERE entity_id=? AND signal_key<>''",
            (entity_id,),
        )
    }
    retained = {signature(json.loads(row["payload"])) for row in rows}
    for key, memory in memories.items():
        if key in retained:
            continue
        fields = json.loads(memory["summary"])
        rows.append(
            {
                "id": memory["observation_id"],
                "payload": json.dumps({"source": {"fields": fields}, "ip": fields.get("ip", "")}),
                "tag": fields.get("tag", ""),
                "hostname": fields.get("hostname", ""),
                "ip": fields.get("ip", ""),
                "version": selected_version(fields)["raw_version"] or "",
                "observed_at": memory["observed_at"],
                "acquisition_at": memory["acquisition_at"],
            }
        )
    covered = {}
    exclusions = notified_cve_exclusions(db, entity_id)
    for row in db.execute(
        """SELECT ce.entry_id,r.id report_id,r.case_id,r.revision,r.sent_at
      FROM reports r JOIN case_entries ce ON ce.case_id=r.case_id JOIN cases c ON c.id=r.case_id
      WHERE r.entity_id=? AND r.sent_at IS NOT NULL
      AND NOT EXISTS(SELECT 1 FROM json_each(c.draft,'$.observation_scope') decision WHERE decision.key=ce.entry_id AND json_extract(decision.value,'$.decision')='exclude')
      ORDER BY r.sent_at,r.revision""",
        (entity_id,),
    ):
        covered.setdefault(row["entry_id"], []).append(dict(row))
    groups, counted = {}, set()
    latest_observed = max(
        [r["observed_at"][:10] for r in rows if r["observed_at"]]
        + [m["last_seen"][:10] for m in memories.values()]
        + [""]
    )
    for row in rows:
        payload, fields = _facts(row)
        signal = signature(payload)
        memory = memories.get(signal)
        first = memory["first_seen"] if memory else row["observed_at"]
        last = memory["last_seen"] if memory else row["observed_at"]
        cves = identifiers([row["tag"]])
        tags = cves or [row["tag"].strip().lower() or "Unspecified reported finding"]
        asset = (
            row["hostname"].lower(),
            row["ip"],
            str(fields.get("protocol", "")),
            str(fields.get("port", "")),
        )
        for tag in tags:
            key = (*asset, tag)
            group = groups.setdefault(
                key,
                {
                    "finding_id": hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24],
                    "hostname": row["hostname"],
                    "ip": row["ip"],
                    "protocol": asset[2],
                    "port": asset[3],
                    "finding": tag,
                    "observations": 0,
                    "first_observed": first,
                    "last_observed": last,
                    "latest_stamp": "",
                    "versions": [],
                    "latest_version": "",
                    "material_change_acquired_at": row["acquisition_at"] or "",
                    "notifications": [],
                    "covered_versions": [],
                    "covered_observed": "",
                },
            )
            if not memory or (signal, tag) not in counted:
                group["observations"] += len(json.loads(memory["seen_days"])) if memory else 1
                counted.add((signal, tag))
            group["first_observed"] = min(group["first_observed"], first)
            group["last_observed"] = max(group["last_observed"], last)
            if last >= group["latest_stamp"]:
                group["latest_version"] = row["version"]
                group["latest_stamp"] = last
            if row["version"] not in group["versions"]:
                group["versions"].append(row["version"])
                group["material_change_acquired_at"] = max(
                    group["material_change_acquired_at"], row["acquisition_at"] or ""
                )
            for notification in covered.get(row["id"], []):
                if tag in exclusions.get(notification["case_id"], ()):
                    continue
                if notification["report_id"] not in {
                    n["report_id"] for n in group["notifications"]
                }:
                    group["notifications"].append(notification)
                if row["version"] not in group["covered_versions"]:
                    group["covered_versions"].append(row["version"])
                group["covered_observed"] = max(group["covered_observed"], row["observed_at"])
    counts = {"new": 0, "seen_again": 0, "changed": 0, "covered": 0, "not_seen": 0}
    for group in groups.values():
        if latest_observed and group["last_observed"][:10] < latest_observed:
            state = "not_seen"
        elif group["notifications"] and group["latest_version"] not in group["covered_versions"]:
            state = "changed"
        elif not group["notifications"] and len(group["versions"]) > 1:
            state = "changed"
        elif group["notifications"] and group["last_observed"] <= group["covered_observed"]:
            state = "covered"
        elif group["observations"] > 1:
            state = "seen_again"
        else:
            state = "new"
        group["state"] = state
        group["material_change"] = state in ("new", "changed")
        counts[state] += 1
        del group["latest_stamp"]
        del group["covered_observed"]
        del group["covered_versions"]
    ordered = sorted(
        groups.values(),
        key=lambda g: (not g["material_change"], g["hostname"], g["finding"], g["ip"]),
    )
    return {
        "counts": counts,
        "total": len(ordered),
        "items": ordered[:limit],
        "truncated": limit is not None and len(ordered) > limit,
        "latest_observed_date": latest_observed or None,
        "coverage": "unknown",
        "basis": "Retained findings and compact repeat-sighting summaries for this business; not a complete coverage assessment. Not seen does not mean remediated.",
    }
