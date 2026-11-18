"""Pure qualified-lead export projection shared by snapshots and JSON exports."""

from .presentation import HANDLING
from .observation_scope import finding_entries


def qualified_export(lead, root_by_id, case_id=None):
    groups = []
    sources = []
    report_rows = finding_entries(lead["entries"]) if case_id else lead["entries"]
    for group in lead["domain_groups"]:
        entries = [e for e in report_rows if root_by_id[e["id"]] == group["root_domain"]]
        if not entries:
            continue
        entries.sort(key=lambda e: e["id"] != group["attribution_entry_id"])
        exported = {"hostname": group["root_domain"], "entries": entries}
        # Attribution can still be supported by an observation excluded
        # from the reported findings. Keep it separate from recipient counts.
        if not any(entry["id"] == group["attribution_entry_id"] for entry in entries):
            supporting = next(
                (
                    entry
                    for entry in lead.get("scope_source_entries", [])
                    if entry["id"] == group["attribution_entry_id"]
                ),
                None,
            )
            if supporting:
                exported["supporting_observation"] = supporting
        groups.append(exported)
        sources.append(group)
    reported_names = {
        entry.get("source", {}).get("fields", {}).get("hostname") for entry in report_rows
    }
    hostnames = list(
        {
            item["name"]: item
            for item in lead["hostnames"]
            if not case_id or item["name"] in reported_names
        }.values()
    )
    return {
        "schema_version": 4 if case_id else 3,
        "handling": HANDLING,
        "notification_id": case_id or lead["id"],
        "entity_id": lead["id"],
        **({"case_id": case_id} if case_id else {}),
        **({"intake_score": lead["intake_score"]} if case_id and lead.get("intake_score") else {}),
        "entity_profile": lead.get("entity_profile", {}),
        "entity_name": lead["company"] or lead["domain"],
        "hostname": lead["domain"],
        "hostnames": hostnames,
        "attribution_entry_id": sources[0]["attribution_entry_id"] if sources else None,
        "validated_leads": groups,
        "whois": [g["attribution"] for g in sources],
    }
