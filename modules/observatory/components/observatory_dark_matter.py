"""Present archive records without manufacturing canonical assets or findings."""

from ipaddress import ip_address

from modules.accretion.components.dark_matter import REASONS


def _text(value):
    return "" if value is None else str(value)


def project_record(record, locate, *, detail=True):
    """Translate the component's public record into an Observatory display row."""
    fields = record["raw_fields"]
    normalized = record["normalized_fields"]
    source = record["source"]
    identity = record["record_id"]
    observed = record.get("observed_at") or ""
    ip = record.get("ip") or ""
    try:
        address = ip_address(ip)
        nonpublic = not address.is_global or address.is_multicast
        valid_ip = True
    except ValueError:
        valid_ip, nonpublic = False, None
    latitude, longitude, basis, location_source, location_url = locate(normalized)
    reason = record.get("reason") or ""
    outcome = record["outcome"]
    status = (
        "review"
        if outcome == "review"
        else "pending"
        if outcome in {"pending", "deferred"}
        else "unqualified"
        if outcome in {"no_match", "no_public_ip"}
        else "excluded"
    )
    row = {
        "id": identity,
        "observation_id": identity,
        "record_kind": "source",
        "asset_id": None,
        "finding_id": None,
        "finding_ids": [],
        "admitted_finding_ids": [],
        "unadmitted_finding_ids": [],
        "condition_admissions": {},
        "finding_admission_states": {},
        "condition_findings": {},
        "condition_workflows": {},
        "ip": ip or _text(fields.get("ip")),
        "ip_valid": valid_ip,
        "nonpublic_ip": nonpublic,
        "hostname": record.get("hostname") or _text(fields.get("hostname")),
        "domain": record.get("root_domain") or "",
        "tag": _text(fields.get("tag")),
        "reported_tag": _text(fields.get("tag")),
        "version": _text(normalized.get("version")),
        "product": _text(
            normalized.get("product") or normalized.get("application") or normalized.get("service")
        ),
        "product_versions": [],
        "protocol": _text(normalized.get("protocol")),
        "port": _text(record.get("port")),
        "asn": record.get("asn"),
        "city": _text(normalized.get("city")),
        "region": _text(normalized.get("region")),
        "country": _text(normalized.get("geo") or normalized.get("country")),
        "latitude": latitude,
        "longitude": longitude,
        "location_basis": basis,
        "location_source": location_source,
        "location_source_url": location_url,
        "observed_at": observed,
        "observed_day": observed[:10],
        "observed_days": [observed[:10]] if observed else [],
        "imported_at": record["recorded_at"],
        "first_indexed_at": record["recorded_at"],
        "first_seen": observed,
        "last_seen": observed,
        "changed_at": record["updated_at"],
        "fresh_at": record["updated_at"],
        "admitted": False,
        "admission_state": "observed",
        "status": status,
        "workflow": "unworked",
        "intake_disposition": "dark_matter",
        "dark_matter": True,
        "intake_reason": reason,
        "disposition_reason": REASONS.get(reason, reason.replace("_", " ").capitalize()),
        "observation_count": 1,
        "reported_observation_count": 1,
        "approved_observation_count": 0,
        "legacy_unknown_observation_count": 0,
        "sightings": int(bool(observed)),
        "density_id": identity,
        "density_count": 1,
        "density_band": "normal",
        "admitted_density": 0,
        "dark_matter_density": 1,
        "density_days": int(bool(observed)),
        "temperature": None,
        "entity_id": None,
        "current_entity_id": None,
        "recorded_entity_id": None,
        "entity_name": "",
        "case_id": None,
        "case_stage": "",
        "lead_id": None,
        "entity_association_basis": "",
        "individually_attributed": False,
        "attribution_validated_at": None,
        "source": {
            "import_id": record["import_id"],
            "workbook": source.get("name", ""),
            "sheet": source.get("sheet", ""),
            "row": source.get("row"),
            "sha256": record["source_sha256"],
            "source_key": identity,
        },
        "import_ids": [record["import_id"]],
        "source_available": bool(source.get("path")),
        "original_url": f"/api/imports/{record['import_id']}/original"
        if source.get("path")
        else None,
        "detail_url": f"/api/eclipse/observations/{identity}",
        "report_type": record["report_type"],
        "stage": record["stage"],
        "outcome": record["outcome"],
    }
    if detail:
        row.update(
            fields=fields,
            normalized_fields=normalized,
            normalization_errors=record["errors"],
            outcomes=record.get("outcomes", []),
            attribution=None,
            cases=[],
            fields_error="",
        )
    return row


def append_records(snapshot, archive, locate, *, limit):
    """Append independent source rows; promotion is resolved by the archive API."""
    # A rejected finding can already retain a canonical observation while its
    # original source remains unpromoted in the archive. That is one source
    # event, not an extra observation. The archive detail remains accessible.
    represented = {
        row.get("source", {}).get("source_key")
        for row in snapshot["observations"]
        if row.get("source", {}).get("source_key")
    }
    rows, scanned = [], 0
    for record in archive.iter_records(limit=limit):
        scanned += 1
        if record["record_id"] in represented:
            continue
        rows.append(project_record(record, locate, detail=False))
    snapshot["observations"].extend(rows)
    counts = snapshot["counts"]
    for key in ("rows", "observations", "dark_matter_rows", "dark_matter_observations"):
        counts[key] = counts.get(key, 0) + len(rows)
    counts["mapped_rows"] += sum(row["latitude"] is not None for row in rows)
    counts["unplaced_rows"] += sum(row["latitude"] is None for row in rows)
    counts["distinct_ips"] = len({row["ip"] for row in snapshot["observations"] if row["ip_valid"]})
    counts["observation_days"] = len(
        {row["observed_day"] for row in snapshot["observations"] if row["observed_day"]}
    )
    if scanned == limit:
        snapshot["coverage_complete"] = False
        snapshot["warnings"].append(
            f"Archive display is limited to {limit:,} source records; use Dark Matter field filters for the complete selection."
        )
    return rows
