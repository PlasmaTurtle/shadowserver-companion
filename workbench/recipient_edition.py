"""Explicit, versioned recipient projections; complete case content is retained.

Full-v1 is the implicit historical default. Compact-v1 changes presentation only
after an analyst selects and reviews it; no source record or pinned model changes.
"""

from copy import deepcopy

FULL = "full-v1"
COMPACT = "compact-v1"


def _node(kind, owner, **values):
    if kind == "text":
        values.setdefault("style", "body")
    return {"kind": kind, "section_owner": owner, **values}


def _markers(values):
    return " ".join(f"[{number}]" for number in dict.fromkeys(values) if number)


def _finding_nodes(model, include_appendix):
    owner = "vulnerabilities"
    nodes = [
        _node(
            "heading",
            owner,
            text="Reported vulnerabilities",
            level=1,
            section_key=owner,
            anchor="EX-VULNERABILITY",
        )
    ]
    nodes.append(
        _node(
            "text",
            owner,
            text=(
                "Have your IT staff or service provider confirm the installed product, version and "
                "exposure before choosing a response. A reported vulnerability is not confirmation "
                "of compromise. Scores describe different measures and should not be combined."
            ),
        )
    )
    rows = []
    for item in model["items"]:
        claims = item.get("claim_citations", {})
        scores = []
        for index, metric in enumerate(item.get("cvss_assessments", [])):
            refs = claims.get("cvss", [])[index : index + 1]
            if _markers(refs):
                scores.append(
                    f"CVSS {metric.get('score', 'Not supplied')} "
                    f"{metric.get('severity', '')} (v{metric.get('version') or '?'})\n"
                    f"{metric.get('source') or 'Contributor not supplied'} {_markers(refs)}"
                )
        if item.get("epss") is not None and _markers(claims.get("epss", [])):
            scores.append(
                f"EPSS {float(item['epss']) * 100:.2f}%\n"
                f"{item.get('epss_date') or 'Date not supplied'} {_markers(claims['epss'])}"
            )
        signals = []
        if item.get("kev") is not None and _markers(claims.get("kev", [])):
            signals.append(
                ("CISA KEV: listed" if item["kev"] else "CISA KEV: not listed in retrieved catalog")
                + " "
                + _markers(claims["kev"])
            )
        if item.get("selected_exploitation_label") and _markers(claims.get("ssvc", [])):
            signals.append(item["selected_exploitation_label"] + " " + _markers(claims["ssvc"]))
        ransomware = item.get("ransomware") or {}
        if ransomware.get("label") and _markers(claims.get("ransomware", [])):
            signals.append(ransomware["label"] + " " + _markers(claims["ransomware"]))
        identity = item.get("label", "Reported vulnerability")
        identity += " " + _markers(item.get("description_citations", []))
        versions = ", ".join(item.get("reported_versions") or []) or "Version not supplied"
        count = item.get("exposure_count", 0)
        rows.append(
            [
                {"text": identity},
                {"text": versions + f"\n{count} IP address" + ("es" if count != 1 else "")},
                {"text": "\n\n".join(scores) or "Not supplied"},
                {"text": "\n\n".join(signals) or "No assessment supplied"},
            ]
        )
    nodes.append(
        _node(
            "table",
            owner,
            headers=[
                "Finding",
                "Reported version",
                "Severity and probability",
                "Exploitation evidence",
            ],
            widths=[1.55, 1.2, 2.05, 2.0],
            rows=rows,
            keep_rows=True,
        )
    )
    nodes.append(
        _node(
            "text",
            owner,
            style="small",
            text=(
                "CVSS describes severity; EPSS estimates exploitation probability. Missing information "
                "is not a zero score or a finding that exploitation has not occurred. "
                + (
                    "Supporting source references follow in Appendix D. Full vulnerability descriptions "
                    "and the detailed narrative are available from the sender."
                    if include_appendix
                    else "The complete supporting descriptions and source records are available from the sender."
                )
            ),
        )
    )
    for item in model.get("excluded", []):
        nodes.append(
            _node("text", owner, text=f"Excluded identifier {item['id']}: {item['reason']}")
        )
    return nodes


def _action_nodes(data, information, closing):
    nodes = [
        _node(
            "heading",
            "information",
            text="Next steps for your business",
            level=1,
            section_key="information",
        )
    ]
    for index, step in enumerate(
        filter(None, data["draft"].get("recommendations", "").splitlines()), 1
    ):
        nodes.append(_node("text", "information", text=f"{index}. {step}", style="list_item"))
    nodes.append(
        _node("text", "information", text=data["draft"].get("limitations", ""), style="small")
    )
    # Retain analyst-selected supplementary copy; the generic background and
    # repeated report-family pages remain in the complete report.
    for block in information.get("blocks", []):
        if block.get("kind") == "explainer":
            nodes.extend(
                [
                    _node("heading", "information", text=block["title"], level=2),
                    _node(
                        "text",
                        "information",
                        text=block["body"] + " " + _markers(block.get("citations", [])),
                    ),
                ]
            )
    nodes.append(
        _node("heading", "closing", text="Resources and response", level=2, section_key="closing")
    )
    if closing.get("recipient_verification"):
        nodes.append(
            _node(
                "text",
                "closing",
                text="Verify this notice independently: " + closing["recipient_verification"],
            )
        )
    preferred = {
        "https://www.cisa.gov/resources-tools/resources/free-cybersecurity-services-and-tools",
        "https://www.cisa.gov/stopransomware/ransomware-guide",
        "https://complaint.ic3.gov/",
        "https://www.secretservice.gov/investigations/cyberincident",
    }
    for group in closing.get("resource_groups", []):
        for resource in group["items"]:
            if resource.get("active") and (
                resource["url"] in preferred or group["title"] == "Additional resources"
            ):
                nodes.append(_node("link", "closing", text=resource["label"], url=resource["url"]))
    nodes.append(_node("text", "closing", text=closing.get("responsibility", ""), style="small"))
    nodes.append(_node("text", "closing", text=closing.get("closing", "")))
    nodes.append(
        _node("text", "closing", text="\n".join(closing.get("sender_lines", [])), style="signature")
    )
    nodes.append(
        _node(
            "text",
            "closing",
            text=(
                "Compact recipient edition v1. The full report, general background and complete "
                "supporting evidence are retained by the sender and are available upon request."
            ),
            style="small",
        )
    )
    return nodes


def apply_edition(data, content):
    edition = data["draft"].get("recipient_edition", FULL)
    if edition == FULL:
        return content  # Preserve historical composition/fingerprint shape.
    if edition != COMPACT:
        raise ValueError("Unsupported recipient edition")
    originals = content["sections"]
    content["full_edition_sections"] = deepcopy(originals)
    content["recipient_edition"] = COMPACT
    models = {model["id"]: model for model in content["exhibits"]}
    information = models.get("EX-INFORMATION", {})
    closing = models.get("EX-CLOSING", {})
    # Require explicit current full-page models; legacy copy has a different
    # structure and must be upgraded through the existing layout adoption path.
    if not information.get("pages") or not closing.get("resource_groups"):
        raise ValueError("Adopt the current report layouts before selecting Compact recipient v1")
    result = []
    actions_added = False
    vulnerability = models.get("EX-VULNERABILITY", {})
    can_summarize = bool(vulnerability.get("items")) and all(
        item.get("finding_type") == "cve" for item in vulnerability["items"]
    )
    for node in originals:
        owner = node.get("section_owner")
        if (
            actions_added
            and content.get("include_appendix", True)
            and (
                str(node.get("exhibit_id", "")).startswith("EX-APPENDIX-")
                or node.get("anchor") == "companion-appendix"
            )
            and not any(
                str(previous.get("exhibit_id", "")).startswith("EX-APPENDIX-")
                or previous.get("anchor") == "companion-appendix"
                for previous in result
            )
        ):
            result.append(_node("page_break", "closing"))
        if node.get("exhibit_id") == "EX-VULNERABILITY" and can_summarize:
            result.extend(_finding_nodes(vulnerability, content.get("include_appendix", True)))
        elif node.get("exhibit_id") == "EX-INFORMATION":
            result.extend(_action_nodes(data, information, closing))
            actions_added = True
        elif node.get("exhibit_id") == "EX-CLOSING":
            continue
        elif actions_added and node["kind"] == "page_break" and owner == "information":
            continue
        else:
            result.append(node)
    # Avoid blank pages when the replaced closing page was separated by breaks.
    sections = []
    for node in result:
        if node["kind"] == "page_break" and sections and sections[-1]["kind"] == "page_break":
            continue
        sections.append(node)
    content["sections"] = sections
    return content


def full_report_snapshot(data):
    """Restore full reviewed sections without recomposing or changing evidence."""
    content = data["composition"]
    full = {**content, "sections": content["full_edition_sections"], "recipient_edition": FULL}
    full.pop("full_edition_sections", None)
    return {**data, "composition": full}
