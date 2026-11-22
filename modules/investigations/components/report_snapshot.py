"""Load case evidence and assemble the versioned report snapshot.

Snapshot creation keeps its historical review-state behavior: include_reviews
may record that a prior validation is stale. Callers choosing a read-only
comparison explicitly pass include_reviews=False. Rendering and package path
rewrites are separate operations and never belong in this loader.
"""

from __future__ import annotations

from modules.accretion.components.intake.versions import entry_fields

import hashlib
import json
from collections import OrderedDict
from contextlib import closing
from copy import deepcopy
from modules.workspace.components.primitives import now
from modules.workspace.components import compact_json
from .cases import Cases
from modules.library.components.content_bank import snapshot_blocks
from modules import __version__
from .report_drafts import CVE, hydrated_draft, readiness
from .report_composition import compose
from .source_capture import capture_sources
from .report_contracts import ReportSnapshot
from .image_evidence import metadata_path
from .package_integrity import verification_operation
from modules.leads.components.lead_export_model import qualified_export
from .observation_scope import finding_entries
from .report_screenshots import intact_screenshot, relevant_screenshots


@verification_operation
def snapshot(
    store,
    lead_id,
    case_id=None,
    *,
    include_reviews=True,
    include_validation_history=True,
    draft_override=None,
    capture_sections=None,
) -> ReportSnapshot:
    """Assemble evidence and optionally capture new exhibit artwork.

    Exports keep the eager default. Editor projections use ``capture_sections=()``;
    section validation names only that section. Matching frozen masters remain
    integrity-checked in every mode, and source checks are never bypassed.
    """
    cases = Cases(store)
    case_id = case_id or cases.default_id(lead_id)
    lead = cases.view(case_id)
    if not lead:
        raise ValueError("Notification not found")
    settings = store.settings()
    draft = (
        deepcopy(draft_override) if draft_override is not None else hydrated_draft(lead, settings)
    )
    if draft_override is not None:
        from .observation_scope import apply_scope

        apply_scope(lead, draft)
    from modules.settings.components.sender_identity import effective_settings

    settings = effective_settings(settings, draft)
    selected = draft["selected_explainers"]
    with closing(store.connect()) as db:
        blocks = {b["id"]: b for b in snapshot_blocks(db)}
    evidence = deepcopy([e for e in lead["evidence"] if e["included"]])
    from .website_evidence import export_references, source_matches

    for item in evidence:
        source_metadata = store.path(metadata_path(item["id"]))
        if source_metadata.is_file():
            metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
            if (
                metadata.get("sha256") != item["sha256"]
                or metadata.get("original_filename") != item["filename"]
            ):
                raise ValueError("Screenshot source metadata does not match its original record")
            item["source_metadata"] = metadata
        item["file_integrity"] = {}
        for key in ("path", "preview_path"):
            try:
                item["file_integrity"][key + "_sha256"] = hashlib.sha256(
                    store.path(item[key]).read_bytes()
                ).hexdigest()
            except OSError:
                item["file_integrity"][key + "_sha256"] = None
        item["file_integrity"]["capture_source_matches"] = source_matches(store, item)
    assets = OrderedDict()
    for entry in finding_entries(lead["entries"]):
        f = entry_fields(entry)
        key = (
            f.get("hostname"),
            entry["ip"],
            str(f.get("protocol", "")),
            str(f.get("port", "")),
            str(f.get("tag", "")),
            str(f.get("version", "")),
        )
        item = assets.setdefault(
            key,
            {
                "hostname": f.get("hostname", ""),
                "ip": entry["ip"],
                "port": f.get("port", ""),
                "protocol": f.get("protocol", ""),
                "version": f.get("version", ""),
                "tag": f.get("tag", ""),
                "asn": f.get("asn", ""),
                "location": ", ".join(str(f[k]) for k in ("city", "region", "geo") if f.get(k)),
                "private_ip": entry["private_ip"],
                "times": [],
            },
        )
        if f.get("timestamp"):
            item["times"].append(str(f["timestamp"]))
    for asset in assets.values():
        asset["first_seen"] = min(asset["times"]) if asset["times"] else ""
        asset["last_seen"] = max(asset["times"]) if asset["times"] else ""
    cves = sorted({c.upper() for asset in assets.values() for c in CVE.findall(str(asset["tag"]))})
    refs = list(
        dict.fromkeys(line.strip() for line in draft["resources"].splitlines() if line.strip())
    )
    pinned = {b["id"]: b for b in draft.get("explainer_snapshots", [])}
    chosen = [
        pinned.get(key, blocks.get(key)) for key in selected if key in pinned or key in blocks
    ]
    for block in chosen:
        refs.extend(x.strip() for x in block["sources"].splitlines() if x.strip())
    for cve in draft["cve_records"]:
        refs.extend(source["url"] for source in cve.get("sources", []) if source.get("url"))
    data = {
        "schema_version": 6,
        "app_version": __version__,
        "notification_id": case_id,
        "case_id": case_id,
        "entity_id": lead_id,
        "domain": lead["domain"],
        "entity_name": lead["company"],
        "hostnames": lead["hostnames"],
        "draft_revision": lead["draft_revision"],
        "created_at": now(),
        "demo": bool(lead["demo"]),
        "profile": settings,
        "entity_profile": lead.get("entity_profile", {}),
        "draft": draft,
        "assets": list(assets.values()),
        "cves": cves,
        "explainers": chosen,
        "evidence": evidence,
        "references": list(dict.fromkeys(refs)),
        "qualified_lead": qualified_export(
            lead, lead["scope_root_by_id"], case_id, websites=export_references(store, evidence)
        ),
        "readiness": readiness({**lead, "evidence": evidence}, draft, settings),
    }
    # Internal audit data is never fed to recipient composition. Original
    # rows and reasoned decisions stay available after recipient exclusion.
    data["observation_scope"] = deepcopy(lead.get("observation_scope", {}))
    data["scope_source_entries"] = deepcopy(lead.get("scope_source_entries", []))
    data["scope_source_groups"] = deepcopy(lead.get("scope_source_groups", []))
    # The case owns its dated intake assessment. Rendering never re-scores a
    # lead from today's catalog, and legacy cases receive no invented priority.
    if isinstance(lead.get("intake_score"), dict) and lead["intake_score"]:
        data["intake_score"] = deepcopy(lead["intake_score"])
    from modules.ui.components.presentation import document_policy, handling_issues

    data["schema_version"] = 7
    previous_revision = (
        store.one("SELECT max(revision) n FROM reports WHERE lead_id=?", (lead_id,))["n"] or 0
    )
    if lead.get("case", {}).get("stage", "in_progress") == "in_progress":
        data["report_revision"] = previous_revision + 1
    else:
        certified_id = lead.get("case", {}).get("certified_report_id")
        data["report_revision"] = next(
            (int(r["revision"]) for r in lead.get("reports", []) if r["id"] == certified_id),
            previous_revision,
        )
    data["document_policy"] = draft.setdefault("document_policy", document_policy(settings))
    data["handling"] = data["document_policy"]["handling"]
    capture_sources(store, data)
    data["readiness"].append(
        {
            "key": "source_integrity",
            "label": "Captured source evidence remains intact",
            "ok": not data["source_integrity_issues"],
        }
    )
    issues = handling_issues(
        draft,
        {
            "attribution": data["qualified_lead"].get("whois", []),
            "source_snapshots": data["source_snapshots"],
            "attribution_history": data["attribution_history"],
            "explainers": data["explainers"],
            "evidence": data["evidence"],
            "observations": data["qualified_lead"].get("validated_leads", []),
        },
    )
    data["readiness"].append(
        {
            "key": "handling",
            "label": "; ".join(issues)
            if issues
            else "Selected sources permit the report handling policy",
            "ok": not issues,
        }
    )
    data["composition"] = compose(data)
    from .attribution_model import REVISION as ATTRIBUTION_REVISION

    attribution_exhibit = next(
        (
            e
            for e in data["composition"]["exhibits"]
            if e.get("layout_revision") == ATTRIBUTION_REVISION
        ),
        None,
    )
    if attribution_exhibit is not None:
        items = attribution_exhibit.get("items", [])
        data["readiness"].append(
            {
                "key": "attribution_exhibit",
                "label": "Attribution exhibit evidence and validation details are complete",
                "ok": bool(items)
                and all(i.get("supported") and not i.get("review_required") for i in items),
            }
        )
    from modules.ui.components.exhibit_rendering import capture_exhibit_masters, is_page_exhibit

    frozen_exhibits = []
    if any(is_page_exhibit(e) for e in data["composition"]["exhibits"]):
        from .repositories.reviews import SectionReviewRepository

        active = SectionReviewRepository(store).active(case_id)
        resources = {}
        for section in ("introduction", "vulnerabilities", "attribution", "information", "closing"):
            if section in active:
                saved = compact_json.loads(
                    active[section]["snapshot_json"], resource_pool=resources
                )
                frozen_exhibits.extend(saved.get("snapshot", {}).get("exhibits", []))
                # Only exhibit content is needed from these records. Do not
                # retain the last record's duplicated frozen_context tree.
                del saved
        # The parsed exhibits now own their strings; release the raw SQLite
        # JSON before verification and the later review/history projections.
        active.clear()
    capture_exhibit_masters(data["composition"], frozen_exhibits, sections=capture_sections)
    frozen_exhibits.clear()
    data["readiness"].append(
        {
            "key": "citation_integrity",
            "label": "; ".join(data["composition"]["citation_integrity_issues"])
            or "Included source claims resolve to their preserved references",
            "ok": not data["composition"]["citation_integrity_issues"],
        }
    )
    data["readiness"].append(
        {
            "key": "evidence_integrity",
            "label": "Screenshot evidence files retain their recorded content",
            "ok": bool(relevant_screenshots({**lead, "evidence": evidence}))
            and all(intact_screenshot(item) for item in evidence),
        }
    )
    if include_reviews:
        from .reviews.queries import SectionReviewQueries

        reviews = SectionReviewQueries(store)
        data["section_reviews"] = reviews.describe(data, lead)
        data["section_history"] = reviews.history(case_id)
        # Preview needs current review decisions, not every historical artwork
        # tree. Certification keeps the complete evidence history by default.
        data["section_validations"] = (
            reviews.snapshots(case_id) if include_validation_history else []
        )
        data["readiness"] += [
            {
                "key": "section_" + r["key"],
                "label": r["label"] + " validated and current",
                "ok": r["status"] == "validated",
            }
            for r in data["section_reviews"]
        ]
    return data
