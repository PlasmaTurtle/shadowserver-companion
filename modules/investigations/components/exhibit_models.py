"""Deterministic exhibit models derived from case observations and saved sources."""

from __future__ import annotations

from modules.accretion.components.intake.versions import entry_fields, has_active_findings

from collections import OrderedDict
from copy import deepcopy
import re

from .appendix import Appendix, stable_id

CVE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)


def _unique(items):
    return list(dict.fromkeys(items))


def _fields(entry):
    return entry_fields(entry)


def _observation_label(entry):
    fields = _fields(entry)
    return (
        " · ".join(
            str(x)
            for x in (
                fields.get("hostname"),
                entry.get("ip") or fields.get("ip"),
                fields.get("timestamp"),
            )
            if x not in (None, "")
        )
        or "Reported observation"
    )


def _source_ref(source, refs, **defaults):
    return refs.add(source, **defaults)


def _signal_labels(record, selected_id=None):
    try:
        from modules.library.components.cve_intelligence import signal_labels

        result = signal_labels(record, selected_id)
        if isinstance(result, list):
            return result
    except ImportError:
        pass
    labels = []
    if record.get("kev") is True:
        labels.append("Known exploited · CISA KEV")
    elif record.get("kev") is False:
        labels.append("Not listed in retrieved KEV catalog")
    ransomware = record.get("ransomware") or {}
    if ransomware.get("label"):
        labels.append(ransomware["label"])
    assessments = record.get("ssvc_assessments") or []
    selected = next((x for x in assessments if x.get("id") == selected_id), None)
    selected = selected or next(
        (x for x in assessments if x.get("id") == record.get("selected_ssvc_assessment_id")), None
    )
    if selected and selected.get("label"):
        labels.append(
            selected["label"]
            + " · "
            + selected.get("publisher", "Source not supplied")
            + " · "
            + str(selected.get("assessed_at") or "Assessment date unavailable")
        )
    labels += [
        i["label"]
        for i in record.get("impacts", [])
        if i.get("label") and i.get("source_text") and i.get("basis")
    ]
    return labels


def build_exhibits(
    data, refs, attribution_groups, descriptions=(), excluded=(), resolved_records=None
):
    """Build the three exhibits and complete appendix without I/O or mutation."""
    appendix = Appendix()
    observations = []
    observation_entries = {}
    group_entries = OrderedDict()
    qualified = data.get("qualified_lead", {})
    for group_index, group in enumerate(qualified.get("validated_leads", [])):
        group_entries[group.get("hostname", "")] = []
        for position, original in enumerate(group.get("entries", [])):
            row = deepcopy(original)
            identity = {
                "entry_id": row.get("id"),
                "group": group.get("hostname"),
                "source": row.get("source", {}),
                "position": position,
            }
            observation_id = row.get("id") or stable_id("OBS", identity)
            entry = appendix.add(
                "A",
                "observation",
                _observation_label(row),
                row,
                identity=identity,
                referenced_by=["EX-SUMMARY"],
            )
            observation = {
                "id": observation_id,
                "entry_id": entry["id"],
                "row": row,
                "root_domain": group.get("hostname", ""),
                "fields": _fields(row),
            }
            observations.append(observation)
            observation_entries.setdefault(observation_id, []).append(entry["id"])
            group_entries[group.get("hostname", "")].append(entry["id"])
    # Imports always supply full qualified observations. A legacy snapshot with
    # only asset aggregates is labeled explicitly rather than inventing rows.
    if not observations:
        for position, asset in enumerate(data.get("assets", [])):
            entry = appendix.add(
                "A",
                "legacy_asset_summary",
                "Legacy saved asset summary",
                asset,
                identity={"legacy_asset": position, "value": asset},
                referenced_by=["EX-SUMMARY"],
            )
            observations.append(
                {
                    "id": stable_id("LEGACY", asset),
                    "entry_id": entry["id"],
                    "row": asset,
                    "fields": asset,
                    "root_domain": "",
                }
            )
    for source in data.get("import_sources", []):
        referenced_entries = [
            appendix_id
            for observation_id in source.get("referenced_by", [])
            for appendix_id in observation_entries.get(observation_id, [])
        ]
        metadata = {k: deepcopy(v) for k, v in source.items() if k != "referenced_by"}
        entry = appendix.add(
            "A",
            "import_provenance",
            "Original import · " + str(source.get("filename") or source.get("id")),
            metadata,
            identity={"import_id": source.get("id"), "sha256": source.get("sha256")},
            referenced_by=["EX-SUMMARY"] + referenced_entries,
        )
        for observation_entry in appendix.entries:
            if observation_entry["id"] in referenced_entries:
                observation_entry["source_ids"].append(entry["id"])
    ips = _unique(
        str(o["row"].get("ip") or o["fields"].get("ip"))
        for o in observations
        if o["row"].get("ip") or o["fields"].get("ip")
    )
    endpoints = _unique(
        (
            str(o["row"].get("ip") or o["fields"].get("ip", "")),
            str(o["fields"].get("protocol", "")),
            str(o["fields"].get("port", "")),
            str(o["row"].get("endpoint_role") or o["fields"].get("endpoint_role") or "reported"),
        )
        for o in observations
    )
    dates = sorted(
        str(o["fields"]["timestamp"]) for o in observations if o["fields"].get("timestamp")
    )
    products = OrderedDict()
    for o in observations:
        f = o["fields"]
        normalized = o["row"].get("normalized") or {}
        supplied_products = normalized.get("products") or []
        values = [
            (
                str(p.get("product") or "Product not supplied")
                + " "
                + str(p.get("version") or "Version not supplied")
            ).strip()
            for p in supplied_products
            if isinstance(p, dict)
        ]
        if not values:
            from .introduction_model import REVISION as INTRODUCTION_REVISION

            if data["draft"].get("introduction_revision") == INTRODUCTION_REVISION:
                # Keep source product and version together. A bare version is
                # not enough for the recipient to identify the affected software.
                product, version = str(f.get("product") or ""), str(f.get("version") or "")
                named_version = product and (
                    version.casefold() == product.casefold()
                    or version.casefold().startswith(
                        tuple(product.casefold() + separator for separator in ("/", " ", ":", "-"))
                    )
                )
                label = version if named_version else " ".join(filter(None, (product, version)))
                values = [label or "Product/version not supplied"]
            else:
                values = [
                    str(f.get("version") or f.get("product") or "Product/version not supplied")
                ]
        service = (
            str(f.get("protocol") or "Transport not supplied")
            + " "
            + str(f.get("port") if f.get("port") is not None else "Port not supplied")
        )
        for label in _unique(values):
            key = (label, service)
            item = products.setdefault(
                key,
                {
                    "label": label,
                    "detail": service,
                    "value": 0,
                    "observation_ids": [],
                    "appendix_entry_ids": [],
                    "ip_addresses": [],
                },
            )
            item["value"] += 1
            item["observation_ids"].append(o["id"])
            item["appendix_entry_ids"].append(o["entry_id"])
            ip = str(o["row"].get("ip") or f.get("ip") or "")
            if ip and ip not in item["ip_addresses"]:
                item["ip_addresses"].append(ip)
    summary = {
        "id": "EX-SUMMARY",
        "type": "summary",
        "title": "Summary Exhibit",
        "report_revision": data.get("report_revision", 1),
        "counts": [
            {"label": "Unique reported IPs", "value": len(ips)},
            {"label": "Service endpoints", "value": len(endpoints)},
            {"label": "Source observations", "value": len(observations)},
            {"label": "Distinct reported CVEs", "value": len(data.get("cves", []))},
        ],
        "reporting_period": {
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
        },
        "report_types": _unique(
            str(
                o["row"].get("report_type")
                or o["row"].get("source", {}).get("report_type")
                or (o["row"].get("normalized") or {}).get("profile", {}).get("id")
                or "Not supplied"
            )
            for o in observations
        ),
        "source_workbooks": _unique(
            str(o["row"].get("source", {}).get("workbook", "Not supplied")) for o in observations
        ),
        "groups": list(products.values()),
        "items": [],
        "appendix_entry_ids": [o["entry_id"] for o in observations],
        "source_citations": [],
        "count_note": "Observation counts are source rows. Repeated observations are not additional assets or proof of continuous exposure. Product/version groups may overlap by IP.",
        "alt_text": f"{len(ips)} unique reported IPs, {len(endpoints)} service endpoints, {len(observations)} source observations. Full original fields are retained in Appendix A.",
    }
    attribution_items = []
    from .attribution_model import REVISION as ATTRIBUTION_REVISION

    reviewed_attribution = data["draft"].get("attribution_revision") == ATTRIBUTION_REVISION
    for group in attribution_groups:
        proof = group.get("source", {})
        accepted_id = appendix.add(
            "B",
            "attribution_evidence" if reviewed_attribution else "accepted_attribution",
            ("Saved attribution evidence · " if reviewed_attribution else "Accepted association · ")
            + group["hostname"],
            proof,
            identity={"group": group["hostname"], "proof": proof},
            citations=[group.get("citation")],
            referenced_by=["EX-ATTRIBUTION"] + group_entries.get(group["hostname"], []),
            status="recorded" if reviewed_attribution else "accepted",
        )["id"]
        review = proof.get("review") or {}
        details = proof.get("evidence", {}).get("details", {})
        network = proof.get("record") or {}
        start, end = network.get("startAddress"), network.get("endAddress")
        evidence_range = (
            details.get("network_range")
            or details.get("cidr")
            or (str(start) + " – " + str(end) if start and end else "")
        )
        reported_ip = str(proof.get("ip") or "Supporting IP not supplied")
        target = evidence_range or reported_ip
        method = (
            "Analyst-reviewed registration-name match"
            if review
            else "DNS association"
            if proof.get("protocol") == "DNS"
            else "Synthetic demonstration record"
            if proof.get("protocol") == "SYNTHETIC"
            else "Exact domain in registration record"
        )
        decision_at = (
            review.get("reviewed_at")
            or proof.get("validated_at")
            or proof.get("decision_at")
            or proof.get("evaluated_at")
        )
        decision_by = (
            review.get("reviewer")
            or proof.get("validated_by")
            or proof.get("decision_by")
            or ("Attribution Module" if proof.get("evaluated_at") and not review else None)
        )
        matched = proof.get("attribution") or {}
        attribution_items.append(
            {
                "label": group["hostname"],
                "detail": reported_ip
                + (" → covering network " if evidence_range else " → evidence IP ")
                + target
                + " → "
                + str(proof.get("registry") or "Source not supplied"),
                "reported_ip": reported_ip,
                "evidence_ip": None if evidence_range else reported_ip,
                "covering_network": evidence_range or None,
                "method": method,
                "matched_field": matched.get("field"),
                "matched_value": matched.get("value"),
                "decision_at": decision_at,
                "decision_by": decision_by,
                "retrieved_at": proof.get("retrieved_at"),
                "source_url": proof.get("source_url"),
                "reported_asset_count": len(group.get("ips", [])),
                "supporting_attribution_count": 1,
                "observation_ids": [
                    o["id"] for o in observations if o["root_domain"] == group["hostname"]
                ],
                "appendix_entry_ids": [accepted_id] + group_entries.get(group["hostname"], []),
                "citations": [group["citation"]] if group.get("citation") else [],
            }
        )
    from .observation_scope import recipient_attribution_history

    history = recipient_attribution_history(data)
    for index, record in enumerate(history):
        status = (
            record.get("status")
            or record.get("decision")
            or record.get("outcome")
            or "Recorded history; decision not supplied"
        )
        appendix.add(
            "B",
            "attribution_history",
            str(status) + " · attribution evidence history",
            record,
            identity={"record": record, "position": index},
            referenced_by=["EX-ATTRIBUTION"],
            status=status,
        )
    attribution = {
        "id": "EX-ATTRIBUTION",
        "type": "attribution",
        "title": "Attribution Exhibit",
        "report_revision": data.get("report_revision", 1),
        "counts": [
            {"label": "Reported IPs", "value": len(ips)},
            {"label": "Supporting associations", "value": len(attribution_items)},
            {"label": "Other retained history records", "value": len(history)},
        ],
        "groups": [],
        "items": attribution_items,
        "appendix_entry_ids": [e["id"] for e in appendix.entries if e["partition"] == "B"],
        "source_citations": _unique(i["citation"] for i in attribution_groups if i.get("citation")),
        "alt_text": f"{len(ips)} reported IPs / {len(attribution_items)} supporting associations. The selected supporting relationship qualifies its domain group; this does not claim separate attribution for every asset.",
    }
    record_map = {r.get("id"): r for r in data["draft"].get("cve_records", [])}
    desc_map = {d["id"]: d for d in descriptions}
    excluded_map = {e["id"]: e["reason"] for e in excluded}
    vulnerability_items = []
    for cve in data.get("cves", []):
        original = deepcopy(record_map.get(cve) or {"id": cve, "verification_status": "unresolved"})
        selected = data["draft"].get("selected_ssvc_assessments", {}).get(cve) or original.get(
            "selected_ssvc_assessment_id"
        )
        if selected:
            original["case_selected_ssvc_assessment_id"] = selected
        disposition = data["draft"].get("cve_dispositions", {}).get(cve)
        if disposition:
            original["case_disposition"] = deepcopy(disposition)
        affected = [
            o
            for o in observations
            if cve in {c.upper() for c in CVE.findall(str(o["fields"].get("tag", "")))}
        ]
        # Legacy only-aggregate specimens still have an exact saved relationship.
        if not affected:
            affected = [
                o
                for o in observations
                if any(
                    cve in str(a.get("tag", "")) and str(a.get("ip")) == str(o["row"].get("ip"))
                    for a in data.get("assets", [])
                )
            ]
        desc = desc_map.get(cve, {})
        effective = deepcopy((resolved_records or {}).get(cve) or original)
        claim_citations = deepcopy(effective.get("claim_citations", {}))
        citations = _unique(c for values in claim_citations.values() for c in values if c)
        citations = _unique([*desc.get("citations", []), *citations])
        if claim_citations:
            original["report_claim_citations"] = claim_citations
        e = appendix.add(
            "C",
            "vulnerability_record",
            cve + (" · excluded: " + excluded_map[cve] if cve in excluded_map else ""),
            original,
            identity={
                "cve": cve,
                "revision_id": original.get("revision_id"),
                "intelligence_revision_id": original.get("intelligence_revision_id"),
            },
            citations=citations,
            referenced_by=["EX-VULNERABILITY"] + [o["entry_id"] for o in affected],
            status="excluded" if cve in excluded_map else original.get("verification_status"),
        )
        if cve in excluded_map:
            continue
        labels = _signal_labels(effective, selected if effective.get("ssvc_assessments") else None)
        vulnerability_items.append(
            {
                "label": cve,
                "detail": " · ".join(str(x) for x in labels)
                or "No optional exploitation assessment supplied",
                "finding_type": "cve",
                "verification_status": effective.get("verification_status"),
                "description_excerpt": desc.get(
                    "label", "Published description unavailable; see Appendix C"
                ),
                "source": effective.get("source"),
                "cvss_assessments": deepcopy(effective.get("cvss_assessments", [])),
                "epss": effective.get("epss"),
                "epss_percentile": effective.get("epss_percentile"),
                "epss_date": effective.get("epss_date"),
                "kev": effective.get("kev"),
                "ransomware": deepcopy(effective.get("ransomware")),
                "signals": labels,
                "impacts": deepcopy(effective.get("impacts", [])),
                "selected_ssvc_assessment_id": selected,
                "exposure_count": len(
                    {str(o["row"].get("ip") or o["fields"].get("ip")) for o in affected}
                ),
                "reported_versions": _unique(
                    str(o["fields"].get("version")) for o in affected if o["fields"].get("version")
                ),
                "observation_ids": [o["id"] for o in affected],
                "appendix_entry_ids": [e["id"]] + [o["entry_id"] for o in affected],
                "citations": citations,
                "claim_citations": claim_citations,
            }
        )
    eol_groups = OrderedDict()
    from .finding_explainers import (
        REVISION as FINDING_EXPLAINER_REVISION,
        enrich_eol_findings,
        match_snippet,
    )

    technical_snippets = (
        data["draft"].get("finding_explainer_snapshots", [])
        if data["draft"].get("finding_explainer_revision") == FINDING_EXPLAINER_REVISION
        else []
    )
    for o in observations:
        f = o["fields"]
        for tag in re.split(r"[;,\s]+", str(f.get("tag", ""))):
            if not re.search(r"(^|[-_])eol($|[-_])", tag, re.I) and not match_snippet(
                o["row"], tag, technical_snippets
            ):
                continue
            key = (tag, str(f.get("version") or "Version not supplied"))
            group = eol_groups.setdefault(
                key,
                {
                    "label": tag,
                    "detail": key[1],
                    "finding_type": "eol",
                    "cvss_assessments": [],
                    "signals": ["Reported end-of-life condition"],
                    "observation_ids": [],
                    "appendix_entry_ids": [],
                    "citations": [],
                },
            )
            group["observation_ids"].append(o["id"])
            group["appendix_entry_ids"].append(o["entry_id"])
    eol_items = enrich_eol_findings(data, observations, eol_groups, refs, appendix)
    vulnerability_items.extend(eol_items)
    # New source-aware reports retain actionable non-CVE observations as
    # finding cards. Historical models keep their exact CVE/EOL-only content.
    from .notification_narrative_v4 import SOURCE_AWARE_REVISIONS, source_context

    if data["draft"].get("narrative_revision") in SOURCE_AWARE_REVISIONS:
        observed_findings = OrderedDict()
        for observation in observations:
            if not has_active_findings(observation["row"]):
                continue
            fields = observation["fields"]
            tag = str(fields.get("tag") or "")
            if re.search(r"(^|[-_;,\s])eol($|[-_;,\s])", tag, re.I):
                continue
            if any(
                match_snippet(observation["row"], token, technical_snippets)
                for token in re.split(r"[;,\s]+", tag)
            ):
                continue
            context = source_context(observation["row"])
            if CVE.search(tag):
                # The missing-authentication observation remains distinct from
                # a CVE, including when that CVE is separately excluded.
                if context["id"] in {
                    "scan_mongodb",
                    "scan6_mongodb",
                } and "mongodb-noauth" in re.split(r"[;,\s]+", tag.casefold()):
                    tag = "mongodb-noauth"
                else:
                    continue
            key = (context["id"], tag, str(fields.get("version") or ""))
            item = observed_findings.setdefault(
                key,
                {
                    "label": tag or context["title"],
                    "detail": context["title"] + " - reported observation",
                    "finding_type": "observation",
                    "observation_ids": [],
                    "appendix_entry_ids": [],
                    "citations": [],
                    "cvss_assessments": [],
                    "signals": [],
                    "endpoints": [],
                    "version_detail": (
                        (
                            "Reported protocol version: "
                            if context["version_semantics"] == "protocol"
                            else "Reported software version: "
                        )
                        + key[2]
                    )
                    if key[2] and context["version_semantics"] in {"protocol", "software"}
                    else "",
                },
            )
            endpoint = " / ".join(
                str(value)
                for value in (
                    fields.get("hostname"),
                    observation["row"].get("ip") or fields.get("ip"),
                    fields.get("protocol"),
                    fields.get("port"),
                    fields.get("timestamp"),
                )
                if value not in (None, "")
            )
            if endpoint not in item["endpoints"]:
                item["endpoints"].append(endpoint)
            item["observation_ids"].append(observation["id"])
            item["appendix_entry_ids"].append(observation["entry_id"])
        for item in observed_findings.values():
            item["observation_scope"] = "; ".join(item.pop("endpoints"))
        vulnerability_items.extend(observed_findings.values())
    vulnerability = {
        "id": "EX-VULNERABILITY",
        "type": "vulnerability",
        "title": "Vulnerability Exhibit",
        "report_revision": data.get("report_revision", 1),
        "counts": [
            {"label": "Included CVEs", "value": len(data.get("cves", [])) - len(excluded_map)},
            {"label": "EOL conditions", "value": len(eol_items)},
            {"label": "Excluded reported CVEs", "value": len(excluded_map)},
        ],
        "items": vulnerability_items,
        "groups": [],
        "appendix_entry_ids": [e["id"] for e in appendix.entries if e["partition"] == "C"],
        "source_citations": _unique(
            c for item in vulnerability_items for c in item.get("citations", []) if c
        ),
        "alt_text": "Distinct reported CVEs and EOL conditions; scores and exploitation signals describe the published vulnerability, not confirmed compromise of this recipient. Full source descriptions and assessments are in Appendix C.",
    }
    # Explicitly supplied captured bodies are case scoped by the snapshot layer.
    # The Information review also carries its versioned public-reference extract.
    from .information_model import SUPPORTED_REVISIONS as INFORMATION_REVISIONS, reference_sources

    information_revision = data["draft"].get("information_revision")
    sources = list(data.get("source_snapshots", []))
    if information_revision in INFORMATION_REVISIONS:
        sources.extend(reference_sources(information_revision))
    if information_revision == "information-2026-11-10-v1":
        from .report_explainers import pinned_sources

        sources.extend(pinned_sources(data["draft"]))
    for source in sources:
        provider = str(source.get("provider") or source.get("publisher") or "").lower()
        partition = source.get("partition") or (
            "B"
            if any(
                s in provider for s in ("rdap", "dns", "arin", "ripe", "apnic", "lacnic", "afrinic")
            )
            else "C"
            if any(s in provider for s in ("cve", "nvd", "cisa", "first"))
            else "D"
        )
        if partition not in {"A", "B", "C", "D"}:
            partition = "D"
        citation = refs.add(source)
        appendix.add_source(
            source,
            partition=partition,
            referenced_by=source.get("referenced_by", []),
            citations=[citation],
        )
    for block in data.get("explainers", []):
        appendix.add(
            "D",
            "advisory",
            block.get("title", "Selected advisory"),
            block,
            identity={"block_id": block.get("id"), "revision": block.get("revision")},
            referenced_by=["Information"],
        )
    for evidence in data.get("evidence", []):
        safe = {
            k: deepcopy(v)
            for k, v in evidence.items()
            if k not in {"path", "preview_path", "lead_id", "case_id"}
        }
        appendix.add(
            "D",
            "supporting_material",
            evidence.get("caption") or "Analyst-captured supporting material",
            safe,
            identity={"evidence_id": evidence.get("id"), "sha256": evidence.get("sha256")},
            referenced_by=["Attribution"],
        )
    from .closing_page_model import (
        FIRST_REVIEW_REVISION,
        SUPPORTED_REVISIONS as CLOSING_REVISIONS,
        resource_groups,
    )

    if data["draft"].get("closing_revision") in CLOSING_REVISIONS:
        for group in resource_groups(data["draft"]):
            for resource in group["items"]:
                appendix.add(
                    "D",
                    "closing_resource",
                    resource["label"],
                    {"group": group["title"], **resource},
                    identity={"url": resource["url"], "revision": FIRST_REVIEW_REVISION},
                    referenced_by=["EX-CLOSING"],
                    owner="closing",
                )
    for reference in refs.items:
        appendix.add(
            "D",
            "reference",
            "[" + str(reference["number"]) + "] " + reference["title"],
            reference,
            identity={"citation": reference},
            citations=[reference["number"]],
            referenced_by=["Source register"],
        )
    exhibits = [summary, vulnerability, attribution]
    return exhibits, appendix.model()
