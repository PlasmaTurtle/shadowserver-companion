"""Deterministic section fingerprints, prerequisites and change explanations."""

from copy import deepcopy
import hashlib
import json
from modules.investigations.components import approved_template as approved

SECTIONS = {
    "introduction": "Introduction",
    "vulnerabilities": "Vulnerabilities",
    "attribution": "Attribution",
    "information": "Information",
    "closing": "Closing",
}
FIELDS = {
    "introduction": (
        "introduction_revision",
        "company",
        "contact_name",
        "address",
        "sender_name",
        "sender_title",
        "report_date",
        "subject",
        "intro",
        "report_template",
    ),
    "vulnerabilities": (
        "narrative_revision",
        "vulnerability_revision",
        "severity",
        "narrative",
        "narrative_values",
        "cve_records",
        "cve_dispositions",
        "selected_ssvc_assessments",
        "outreach_template",
    ),
    "attribution": ("attribution_revision", "website_verified", "sos_verified"),
    "information": (
        "information_revision",
        "recommendations",
        "limitations",
        "selected_explainers",
        "explainer_snapshots",
        "explainer_overrides",
    ),
    "closing": ("resources", "closing", "closing_revision"),
}
FIELDS = {key: fields + ("appendix_revision",) for key, fields in FIELDS.items()}
FINGERPRINT_VERSION = 2
PREREQUISITES = {
    "introduction": {
        "company",
        "sender",
        "sender_profile",
        "observation_scope",
        "observation_scope_nonempty",
    },
    "vulnerabilities": {
        "cve_reference",
        "narrative",
        "narrative_scope",
        "finding_explainers",
        "observation_scope",
        "observation_scope_nonempty",
    },
    "attribution": {
        "attribution",
        "attribution_exhibit",
        "website_screenshot",
        "evidence_integrity",
    },
    "information": {"report_explainers"},
    "closing": set(),
}


def _canonical(value):
    """Storage relocation does not alter the certified evidence bytes."""
    if isinstance(value, dict):
        return {
            k: _canonical(v)
            for k, v in value.items()
            if k not in {"record_path", "original_record_path", "path", "preview_path"}
        }
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def _content_model(value):
    """Remove output-only artwork and appendix navigation from reviewed content."""
    if isinstance(value, dict):
        result = {
            key: _content_model(item)
            for key, item in value.items()
            if key
            not in {
                "rendered_masters",
                "include_appendix",
                "compact_appendix",
                "appendix_note",
                "alt_text",
                "appendix_entry_ids",
                "report_revision",
            }
        }
        if isinstance(result.get("additional_assets"), str):
            result["additional_assets"] = result["additional_assets"].replace(
                " · full inventory available upon request", " · full inventory in Appendix A"
            )
        if result.get("description_excerpt") == (
            "Published description unavailable; supporting records are available upon request"
        ):
            result["description_excerpt"] = "Published description unavailable; see Appendix C"
        return result
    if isinstance(value, list):
        return [_content_model(item) for item in value]
    return value


def _review_nodes(content):
    """The main report's semantic nodes, before the separately presented appendix."""
    result = []
    for node in content["sections"]:
        if (
            str(node.get("exhibit_id", "")).startswith("EX-APPENDIX-")
            or node.get("anchor") == "companion-appendix"
        ):
            break
        if node["kind"] in {"page_break", "reference"}:
            continue
        if node.get("text") in {
            "References",
            "The full supporting appendix is available upon request.",
        }:
            continue
        result.append(node)
    return result


def content_projection(saved):
    """Compare an original artwork-based lock as content without rewriting it.

    Only output fields are removed. Evidence, source values, approved copy and
    declared editable fields remain comparison dependencies. Certified package
    verification continues to use its original manifest and file hashes.
    """
    payload = deepcopy(saved["snapshot"])
    fields = {
        key: deepcopy(value)
        for key, value in saved["frozen_fields"].items()
        if key not in {"appendix_revision", "include_appendix"}
    }
    payload.pop("exhibit_masters", None)
    payload["nodes"] = _content_model(_review_nodes({"sections": payload["nodes"]}))
    payload["exhibits"] = _content_model(
        [model for model in payload["exhibits"] if model.get("type") != "appendix"]
    )
    payload["fields"] = fields
    return payload


def fingerprints(data, lead, *, sections=None, version=FINGERPRINT_VERSION, prior_snapshots=None):
    """Version 1 preserves saved artwork hashes; version 2 only locks content.

    Legacy comparisons reuse the already saved vector masters. Comparing all
    model/dependency fields still detects edits without regenerating old artwork.
    New review records never create or persist rendered pages.
    """
    if version not in {1, FINGERPRINT_VERSION}:
        raise ValueError("Unsupported section fingerprint version")
    content_only = version == FINGERPRINT_VERSION
    selected = SECTIONS if sections is None else sections
    content = data["composition"]
    nodes = {key: [] for key in SECTIONS}
    current = "introduction"
    for node in _review_nodes(content) if content_only else content["sections"]:
        if node.get("section_key") in SECTIONS:
            current = node["section_key"]
        owner = node.get("section_owner", current)
        nodes[owner if owner in SECTIONS else current].append(deepcopy(node))
    snapshots = {}
    for key in selected:
        fields = {
            name: deepcopy(data["draft"].get(name))
            for name in FIELDS[key]
            if not (content_only and name == "appendix_revision")
        }
        # Missing/full remains the historical hash shape. Compact is an
        # explicit content choice that must be reviewed in every section.
        if data["draft"].get("recipient_edition", "full-v1") != "full-v1":
            fields["recipient_edition"] = data["draft"]["recipient_edition"]
        if (
            key == "vulnerabilities"
            and data["draft"].get("finding_explainer_revision")
            == "finding-explainers-2026-11-10-v1"
        ):
            fields["finding_explainer_revision"] = data["draft"]["finding_explainer_revision"]
            fields["finding_explainer_snapshots"] = deepcopy(
                data["draft"].get("finding_explainer_snapshots", [])
            )
        if (
            key == "information"
            and data["draft"].get("information_revision") == "information-2026-11-10-v1"
        ):
            fields["report_explainer_snapshots"] = deepcopy(
                data["draft"].get("report_explainer_snapshots", [])
            )
        # Omitted/default-true retains historical field/hash shape. A compact
        # recipient report freezes this global delivery choice with every section.
        if not content_only and data["draft"].get("include_appendix", True) is False:
            fields["include_appendix"] = False
        source = {}
        if key == "vulnerabilities":
            source = {
                "assets": data["assets"],
                "records": data["draft"].get("cve_records", []),
                "dispositions": data["draft"].get("cve_dispositions", {}),
            }
        elif key == "attribution":
            source = {
                "groups": lead.get("domain_groups", []),
                "evidence": data["evidence"],
                "website_verified": fields["website_verified"],
                "sos_verified": fields["sos_verified"],
            }
        elif key == "information":
            source = {
                "explainers": data["explainers"],
                "overrides": data["draft"].get("explainer_overrides", {}),
            }
            if data["draft"].get("information_revision") == "information-2026-11-10-v1":
                from ..report_explainers import canonical_source_types

                source["report_types"] = canonical_source_types(lead)
        # Only composition-relevant fields are hashed. Notes, unselected bank
        # revisions, contact research and unrelated preferences do not expire a review.
        owners = {
            "summary": "introduction",
            "vulnerability": "vulnerabilities",
            "attribution": "attribution",
        }
        exhibits = [
            deepcopy(e)
            for e in content.get("exhibits", [])
            if e.get("owner", e.get("section_owner", owners.get(e.get("type")))) == key
            and not (content_only and e.get("type") == "appendix")
        ]
        appendix = [
            deepcopy(e)
            for e in content.get("appendix", {}).get("entries", [])
            if e.get("owner", e.get("section_owner")) == key
        ]
        policy = deepcopy(data.get("document_policy", data["draft"].get("document_policy", {})))
        payload = {
            "nodes": nodes[key],
            "template": content["template"],
            "footer_domain": data["domain"],
            "source": _canonical(source),
            "exhibits": exhibits,
            "appendix": appendix,
            "document_policy": policy,
        }
        intake = data.get("intake_score")
        if isinstance(intake, dict) and intake.get("temperature") in (
            "cool",
            "warm",
            "hot",
            "blazing",
        ):
            # The discrete footer mark is part of frozen content. Absence stays
            # absent so historical unscored section hashes retain their shape.
            payload["outreach_temperature"] = intake["temperature"]
        if content_only:
            payload["nodes"] = _content_model(payload["nodes"])
            payload["exhibits"] = _content_model(payload["exhibits"])
            # Declared fields are part of the content contract even if one
            # selected layout does not currently display a field.
            payload["fields"] = deepcopy(fields)
        elif exhibits:
            prior_payload = (prior_snapshots or {}).get(key, {}).get("snapshot", {})
            if "exhibit_masters" in prior_payload:
                payload["exhibit_masters"] = deepcopy(prior_payload["exhibit_masters"])
            else:
                from modules.ui.components.exhibit_rendering import svg_pages

                payload["exhibit_masters"] = [
                    {"exhibit_id": e["id"], "svg": svg_pages(e, policy)}
                    for e in exhibits
                    if "rendered_masters" not in e
                ]
        from modules.settings.components.sender_identity import approved_copy

        context = {"approved_copy": approved_copy(data["draft"])}
        if key == "vulnerabilities":
            context["narrative_groups"] = approved.narrative_groups(lead, data["draft"])
        if key == "attribution":
            context["evidence"] = deepcopy(lead.get("evidence", []))
            context["attribution_summaries"] = deepcopy(lead.get("attribution_summaries", []))
        context["report_model"] = {
            "exhibits": exhibits,
            "appendix": {
                "entries": appendix,
                "index": [
                    e for e in content.get("appendix", {}).get("index", []) if e.get("owner") == key
                ],
            },
        }
        context["document_policy"] = policy
        if content_only:
            context["report_model"]["exhibits"] = _content_model(exhibits)
        snapshots[key] = {
            **({"fingerprint_version": FINGERPRINT_VERSION} if content_only else {}),
            "content_hash": hashlib.sha256(
                json.dumps(
                    payload, sort_keys=True, ensure_ascii=False, default=str, allow_nan=False
                ).encode()
            ).hexdigest(),
            "snapshot": payload,
            "frozen_fields": fields,
            "frozen_context": context,
        }
    return snapshots


def assert_current(reviews):
    stale = [r["label"] for r in reviews if r["status"] == "stale"]
    if stale:
        raise ValueError(
            "Preview is paused because frozen content changed. Reopen and review: "
            + ", ".join(stale)
        )


def changed_paths(before, after, prefix="", limit=100):
    """Explain dependency changes without copying sensitive source values into logs."""
    result = []

    def walk(left, right, path):
        if len(result) >= limit or left == right:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                if key not in left or key not in right:
                    result.append(path + "/" + str(key))
                else:
                    walk(left[key], right[key], path + "/" + str(key))
                if len(result) >= limit:
                    break
        elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
            for index, (a, b) in enumerate(zip(left, right)):
                walk(a, b, path + "/" + str(index))
        else:
            result.append(path or "/")

    walk(before, after, prefix)
    return result[:limit]


def check_key(key):
    if key not in SECTIONS:
        raise ValueError("Unknown report section")


def check_revision(case, expected_revision):
    if case["draft_revision"] != expected_revision:
        raise ValueError("This draft changed. Reload before validating or reopening a section.")
