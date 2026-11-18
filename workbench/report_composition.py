"""Pure, offline composition of a notification from one case snapshot."""

from copy import deepcopy
from . import approved_template as approved
from .appendix import appendix_nodes
from .exhibit_models import build_exhibits
from .cve_intelligence import select_ssvc
from urllib.parse import urlsplit
from .cve_state import cve_excluded

TEMPLATE = {
    "id": "standard",
    "version": 3,
    "marking": "For Informational Purposes Only",
    "font_size": 10,
    "font_family": "ReportSans",
    "margins_inches": [0.85, 0.85, 0.7, 0.75],
    "section_order": ["Introduction", "Vulnerabilities", "Attribution", "Information", "Closing"],
    "headings": {
        "assets": "Affected assets",
        "cve_table": "CVE summary",
        "cve_descriptions": "Published vulnerability descriptions",
        "attribution": "Attribution",
        "references": "References",
        "resources": "Recommended resources",
    },
    "table_style": "grid-repeating-header",
    "signature_layout": "agency-office",
}


def valid_url(value):
    try:
        part = urlsplit(value or "")
        return part.scheme in ("http", "https") and bool(part.netloc)
    except (ValueError, TypeError):
        return False


def attribution_url(value):
    return valid_url(value) or (
        isinstance(value, str) and value.startswith("dns://") and len(value) > 6
    )


def source_usable(record):
    if (
        record.get("verification_status") != "published"
        or not str(record.get("description", "")).strip()
    ):
        return False
    return any(
        valid_url(s.get("public_url") or s.get("url"))
        and (s.get("retrieved_at") or record.get("retrieved_at"))
        for s in record.get("sources", [])
    )


def fallback_usable(value):
    return (
        value.get("action") == "fallback"
        and valid_url(value.get("source_url"))
        and all(
            isinstance(value.get(k), str) and value[k].strip()
            for k in ("description", "publisher", "retrieved_at", "evidence_text", "reason")
        )
    )


def resolved_record(cve_id, draft):
    disposition = draft.get("cve_dispositions", {}).get(cve_id, {})
    if cve_excluded(cve_id, draft):
        return None, "excluded"
    record = next((r for r in draft.get("cve_records", []) if r.get("id") == cve_id), {})
    if fallback_usable(disposition) and record.get("verification_status") not in (
        "reserved",
        "rejected",
    ):
        return {
            "id": cve_id,
            "verification_status": "published",
            "source": disposition["publisher"],
            "description": disposition["description"],
            "manual_fallback": True,
            "public_url": disposition["source_url"],
            "retrieved_at": disposition["retrieved_at"],
            "sources": [
                {
                    "publisher": disposition["publisher"],
                    "title": cve_id + " official-source fallback",
                    "public_url": disposition["source_url"],
                    "retrieved_at": disposition["retrieved_at"],
                }
            ],
            "captured_evidence": disposition["evidence_text"],
        }, "fallback"
    return record, "published" if source_usable(record) else "unresolved"


class Citations:
    def __init__(self):
        self.items = []
        self.keys = {}

    def add(self, source, **defaults):
        item = {**defaults, **{k: v for k, v in source.items() if v not in (None, "")}}
        url = item.get("public_url") or item.get("url", "")
        if not attribution_url(url):
            return None
        key = (
            url,
            item.get("revision_id", ""),
            item.get("sha256") or item.get("body_sha256") or item.get("revision_id", ""),
            item.get("retrieved_at", ""),
        )
        if key not in self.keys:
            number = len(self.items) + 1
            self.keys[key] = number
            self.items.append(
                {
                    "number": number,
                    "publisher": item.get("publisher", urlsplit(url).netloc),
                    "title": item.get("title", "Source record"),
                    "url": url,
                    "published_at": item.get("date_published") or item.get("published_at", ""),
                    "updated_at": item.get("date_updated") or item.get("updated_at", ""),
                    "retrieved_at": item.get("retrieved_at", ""),
                    "revision_id": item.get("revision_id", ""),
                    "record_path": item.get("record_path", ""),
                    "sha256": item.get("sha256") or item.get("body_sha256", ""),
                }
            )
        return self.keys[key]


def markers(numbers):
    return " ".join(f"[{n}]" for n in dict.fromkeys(numbers) if n)


def public_source(record, publisher=None):
    sources = record.get("sources", [])
    if publisher:
        return next((s for s in sources if publisher.lower() in s.get("publisher", "").lower()), {})
    selected = next(
        (
            s
            for s in sources
            if record.get("record_path") and s.get("record_path") == record["record_path"]
        ),
        None,
    )
    if selected:
        return selected
    selected = next(
        (
            s
            for s in sources
            if s.get("publisher") == record.get("source") and s.get("http_status", 200) == 200
        ),
        None,
    )
    return selected or next(
        (
            s
            for s in sources
            if s.get("http_status", 200) == 200
            and not any(p in s.get("publisher", "").lower() for p in ("first", "cisa"))
        ),
        {},
    )


def claim_reference(refs, record, claim, issues, label, *, default=None, **defaults):
    """Use a claim's explicit captured revision; never substitute a different one.

    Older primary-source metrics have no per-field revision, so their known
    primary response remains valid support. Optional values without a record
    stay absent; an included value that names a missing revision is an issue.
    """
    revision = claim.get("source_revision_id")
    source = default if default is not None else public_source(record)
    if revision:
        candidates = list(record.get("sources", []))
        candidates += [s.get("source", {}) for s in record.get("supplementary_records", [])]
        if revision == record.get("revision_id"):
            candidates.append({**public_source(record), "revision_id": revision})
        source = next((s for s in candidates if s.get("revision_id") == revision), {})
    if not source or not valid_url(source.get("public_url") or source.get("url")):
        issues.append(f"{record['id']} {label}: supporting source record is missing")
        return None
    if not (source.get("retrieved_at") or defaults.get("retrieved_at")):
        issues.append(f"{record['id']} {label}: source retrieval time is missing")
        return None
    return refs.add(source, **defaults)


def compose(data):
    d, profile = data["draft"], data["profile"]
    template = deepcopy(TEMPLATE)
    selection = d.get("report_template", {})
    template.update({key: selection[key] for key in ("marking", "font_size") if key in selection})
    refs = Citations()
    citation_issues = []
    nodes = []
    supporting_images = []

    def text(value, style="body"):
        if value:
            nodes.append({"kind": "text", "text": str(value), "style": style})

    def heading(value, level=1, section_key=None):
        node = {"kind": "heading", "text": value, "level": level}
        if section_key:
            node["section_key"] = section_key
        nodes.append(node)

    def table(headers, rows, widths):
        nodes.append({"kind": "table", "headers": headers, "rows": rows, "widths": widths})

    for value in (profile["department"], profile["agency"], profile["office"]):
        text(value, "agency")
    if data.get("demo"):
        text("DEMONSTRATION DATA", "notice")
    text(template["marking"], "marking")
    heading("Introduction", section_key="introduction")
    to = "\n".join(d.get(k, "") for k in ("contact_name", "company", "address") if d.get(k))
    sender = "\n".join(
        filter(
            None,
            [d.get("sender_name"), d.get("sender_title"), profile["agency"], profile["office"]],
        )
    )
    for label, value in [
        ("To", to),
        ("From", sender),
        ("Date", d["report_date"]),
        ("Subject", d["subject"]),
    ]:
        nodes.append({"kind": "metadata", "label": label, "text": value})
    text(d["intro"])
    nodes.append({"kind": "exhibit", "exhibit_id": "EX-SUMMARY", "section_owner": "introduction"})
    nodes.append({"kind": "page_break", "section_owner": "vulnerabilities"})
    from .notification_narrative_v4 import (
        SOURCE_AWARE_REVISIONS,
        has_non_http,
        severity_summary,
    )

    findings_title = (
        "Reported Findings"
        if d.get("narrative_revision") in SOURCE_AWARE_REVISIONS and has_non_http(data)
        else "Vulnerabilities"
    )
    heading(findings_title, section_key="vulnerabilities")
    for paragraph in d["narrative"].split("\n\n"):
        text(paragraph)
    displayed_severity = severity_summary(data)
    if displayed_severity != "Not specified":
        text("Reported severity: " + displayed_severity)
    dispositions = d.get("cve_dispositions", {})
    nodes.append(
        {"kind": "exhibit", "exhibit_id": "EX-VULNERABILITY", "section_owner": "vulnerabilities"}
    )
    cve_rows, descriptions, excluded = [], [], []
    resolved_records = {}
    for cve_id in data["cves"]:
        record, state = resolved_record(cve_id, d)
        resolved_records[cve_id] = deepcopy(record) if record else None
        if state == "excluded":
            excluded.append({"id": cve_id, "reason": dispositions[cve_id]["reason"]})
            continue
        if state == "unresolved":
            descriptions.append(
                {
                    "id": cve_id,
                    "label": "Source unresolved - disposition required before certification",
                    "text": "",
                    "citations": [],
                }
            )
            cve_rows.append(
                [
                    {"text": cve_id},
                    {"text": "Unresolved"},
                    {"text": "Unavailable"},
                    {"text": "Unavailable"},
                    {"text": "Unavailable"},
                ]
            )
            continue
        publisher = record.get("source") or public_source(record).get("publisher", "CVE Program")
        url = record.get("public_url") or f"https://www.cve.org/CVERecord?id={cve_id}"
        source = public_source(record)
        ref = claim_reference(
            refs,
            record,
            {},
            citation_issues,
            "published description",
            default=source,
            publisher=publisher,
            title=cve_id + " vulnerability record",
            public_url=url,
            retrieved_at=record.get("retrieved_at", ""),
            date_published=record.get("date_published", ""),
            date_updated=record.get("date_updated", ""),
            revision_id=record.get("revision_id", ""),
        )
        assessments = record.get("cvss_assessments", [])
        if not assessments and record.get("cvss") is not None:
            assessments = [
                {
                    "score": record["cvss"],
                    "source": record.get("cvss_source", "Source not supplied"),
                    "version": record.get("cvss_version", ""),
                    "severity": record.get("severity", ""),
                }
            ]
        claim_refs = {
            "description": [ref],
            "cvss": [],
            "epss": [],
            "kev": [],
            "ransomware": [],
            "ssvc": [],
            "impacts": [],
        }
        cvss_lines = []
        for assessment in assessments:
            metric_ref = claim_reference(
                refs,
                record,
                assessment,
                citation_issues,
                "CVSS",
                title=cve_id + " CVSS assessment",
                **(
                    {
                        "public_url": url,
                        "revision_id": record.get("revision_id", ""),
                        "retrieved_at": record.get("retrieved_at", ""),
                    }
                    if not assessment.get("source_revision_id")
                    else {}
                ),
            )
            claim_refs["cvss"].append(metric_ref)
            cvss_lines.append(
                f"{assessment['score']} {assessment.get('severity', '')} | CVSS {assessment.get('version', '')}\n"
                f"{assessment.get('source', 'Source not supplied')} {markers([metric_ref])}"
            )
        cvss = "\n".join(cvss_lines) or "Unavailable"
        epss = "Unavailable"
        if record.get("epss") is not None:
            eref = claim_reference(
                refs,
                record,
                {},
                citation_issues,
                "EPSS",
                default=public_source(record, "FIRST"),
                publisher="FIRST",
                title=cve_id + " EPSS score",
                public_url="https://www.first.org/epss/",
                retrieved_at=record.get("epss_retrieved_at", ""),
            )
            claim_refs["epss"] = [eref]
            epss = f"{float(record['epss']) * 100:.2f}% probability\nScore date: {record.get('epss_date') or 'not supplied'}"
            if record.get("epss_percentile") is not None:
                epss += f"\nPercentile: {float(record['epss_percentile']) * 100:.2f}"
            epss += " " + markers([eref])
        kev = "Unavailable"
        if record.get("kev") is not None:
            kref = claim_reference(
                refs,
                record,
                {},
                citation_issues,
                "KEV",
                default=public_source(record, "CISA"),
                publisher="CISA",
                title="Known Exploited Vulnerabilities Catalog",
                public_url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                retrieved_at=record.get("kev_retrieved_at", ""),
            )
            claim_refs["kev"] = [kref]
            kev = "Listed" if record["kev"] else "Not listed in retrieved catalog"
            details = record.get("kev_details") or {}
            if details.get("dateAdded"):
                kev += "\nAdded: " + details["dateAdded"]
            kev += (
                "\nCatalog: "
                + (record.get("kev_date") or "date not supplied")
                + " "
                + markers([kref])
            )
        ransomware = record.get("ransomware") or {}
        if ransomware.get("source_revision_id") or ransomware.get("availability") == "supplied":
            claim_refs["ransomware"] = [
                claim_reference(
                    refs,
                    record,
                    ransomware,
                    citation_issues,
                    "ransomware assessment",
                    default=public_source(record, "CISA"),
                    title="Known Exploited Vulnerabilities Catalog",
                    public_url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                )
            ]
        selected = d.get("selected_ssvc_assessments", {}).get(cve_id) or record.get(
            "selected_ssvc_assessment_id"
        )
        assessment = select_ssvc(record.get("ssvc_assessments", []), selected)
        if assessment:
            claim_refs["ssvc"] = [
                claim_reference(
                    refs,
                    record,
                    assessment,
                    citation_issues,
                    "SSVC assessment",
                    title=cve_id + " exploitation assessment",
                )
            ]
        for impact in record.get("impacts", []):
            claim_refs["impacts"].append(
                claim_reference(
                    refs,
                    record,
                    impact,
                    citation_issues,
                    "potential impact",
                    title=cve_id + " potential impact",
                )
            )
        resolved_records[cve_id]["claim_citations"] = claim_refs
        cve_rows.append(
            [
                {"text": cve_id, "url": url},
                {
                    "text": publisher
                    + (" (fallback)" if state == "fallback" else "")
                    + " "
                    + markers([ref])
                },
                {"text": cvss},
                {"text": epss},
                {"text": kev},
            ]
        )
        label = "Published source description - " + publisher
        if record.get("description_contributor"):
            label += "; contributor: " + record["description_contributor"]
        if state == "fallback":
            label += " (documented official-source fallback)"
        descriptions.append(
            {"id": cve_id, "label": label, "text": record["description"], "citations": [ref]}
        )
    if excluded:
        heading("Reported identifiers excluded from this notification")
        for item in excluded:
            text(item["id"] + ": " + item["reason"], "small")
    nodes.append({"kind": "page_break"})
    heading("Attribution", section_key="attribution")
    text(approved.ATTRIBUTION)
    text("Business: " + d["company"])
    if d.get("address"):
        text(d["address"])
    qualified = data["qualified_lead"]
    attribution_groups = []
    for index, group in enumerate(qualified.get("validated_leads", [])):
        proof = (
            qualified.get("whois", [])[index] if index < len(qualified.get("whois", [])) else {}
        ) or {}
        hostnames = sorted(
            {str(e["source"]["fields"].get("hostname", "")) for e in group["entries"]}
        )
        ips = sorted({str(e["ip"]) for e in group["entries"]})
        reference = refs.add(
            {
                "public_url": proof.get("source_url"),
                "publisher": proof.get("registry", "Registration or DNS source"),
                "retrieved_at": proof.get("retrieved_at"),
                "sha256": proof.get("body_sha256"),
                "revision_id": proof.get("result_id"),
            },
            title="Attribution evidence for " + group["hostname"],
        )
        details = proof.get("evidence", {}).get("details", {})
        attribution_groups.append(
            {
                "hostname": group["hostname"],
                "hostnames": hostnames,
                "ips": ips,
                "source": deepcopy(proof),
                "citation": reference,
            }
        )
    nodes.append(
        {"kind": "exhibit", "exhibit_id": "EX-ATTRIBUTION", "section_owner": "attribution"}
    )
    if d.get("sos_verified"):
        text(
            "Business-registration information reviewed by the analyst; supporting details are recorded with the case.",
            "small",
        )
    for item in data["evidence"]:
        reference = refs.add(
            {
                "public_url": item.get("source_url"),
                "retrieved_at": item.get("captured_at"),
                "publisher": "Analyst-captured exhibit",
                "sha256": item.get("sha256"),
            },
            title=item.get("caption") or item["kind"],
        )
        supporting_images.extend(
            [
                {
                    "kind": "heading",
                    "text": item.get("caption") or item["kind"].replace("_", " ").title(),
                    "level": 2,
                    "section_owner": "attribution",
                },
                {
                    "kind": "image",
                    "id": item["id"],
                    "caption": item.get("caption", ""),
                    "section_owner": "attribution",
                },
                {
                    "kind": "text",
                    "text": "Captured: " + item.get("captured_at", "") + " " + markers([reference]),
                    "style": "small",
                    "section_owner": "attribution",
                },
            ]
        )
    nodes.append({"kind": "page_break"})
    from .information_model import (
        SUPPORTED_REVISIONS as INFORMATION_REVISIONS,
        build_information_exhibit,
    )

    information = None
    if d.get("information_revision") in INFORMATION_REVISIONS:
        information = build_information_exhibit(data, refs)
        nodes.append(
            {
                "kind": "exhibit",
                "exhibit_id": "EX-INFORMATION",
                "section_key": "information",
                "section_owner": "information",
            }
        )
    else:
        heading("Information", section_key="information")
        heading("Suggested Security Practices", 2)
        from .sender_identity import security_intro

        text(security_intro(approved.SECURITY_INTRO, d))
        for index, step in enumerate(approved.NEXT_STEPS.splitlines(), 1):
            text(f"{index}. {step}", "list_item")
        heading("Protecting Your Business from Cyber Fraud", 2)
        text(approved.FRAUD_INTRO)
        for item in approved.FRAUD_RISKS:
            text("• " + item, "list_item")
        text(approved.FRAUD_STATS_INTRO)
        for item in approved.FRAUD_STATS:
            text("• " + item, "list_item")
        heading("Advisory Information & Partnership", 2)
        text(approved.PARTNERSHIP)
        for block in data["explainers"]:
            if block["id"] in approved.SYSTEM_BLOCKS:
                continue
            nums = []
            for url in filter(None, (x.strip() for x in block.get("sources", "").splitlines())):
                metadata = next(
                    (
                        item
                        for item in block.get("source_metadata", [])
                        if item.get("url") == url or item.get("public_url") == url
                    ),
                    {},
                )
                nums.append(
                    refs.add(
                        metadata, public_url=url, title="Supporting reference for " + block["title"]
                    )
                )
            override = d.get("explainer_overrides", {}).get(block["id"], {})
            heading(override.get("title", block["title"]))
            text(override.get("body", block["body"]) + (" " + markers(nums) if nums else ""))
    exhibits, appendix = build_exhibits(
        data, refs, attribution_groups, descriptions, excluded, resolved_records
    )
    if information is not None:
        information["appendix_entry_ids"] = [
            entry["id"]
            for entry in appendix["entries"]
            if any(ref in entry["referenced_by"] for ref in ("EX-INFORMATION", "Information"))
        ]
        exhibits.append(information)
    from .vulnerability_model import (
        SUPPORTED_REVISIONS as VULNERABILITY_REVISIONS,
        build_vulnerability_exhibit,
    )

    if d.get("vulnerability_revision") in VULNERABILITY_REVISIONS:
        exhibits = [
            build_vulnerability_exhibit(data, e, descriptions, excluded, resolved_records)
            if e["type"] == "vulnerability"
            else e
            for e in exhibits
        ]
        start = next(i for i, n in enumerate(nodes) if n.get("section_key") == "vulnerabilities")
        end = next(i for i in range(start, len(nodes)) if nodes[i]["kind"] == "page_break")
        nodes[start:end] = [
            {
                "kind": "exhibit",
                "exhibit_id": "EX-VULNERABILITY",
                "section_key": "vulnerabilities",
                "section_owner": "vulnerabilities",
            }
        ]
    from .attribution_model import REVISION as ATTRIBUTION_REVISION, build_attribution_exhibit

    if d.get("attribution_revision") == ATTRIBUTION_REVISION:
        exhibits = [
            build_attribution_exhibit(data, e, attribution_groups)
            if e["type"] == "attribution"
            else e
            for e in exhibits
        ]
        start = next(i for i, n in enumerate(nodes) if n.get("section_key") == "attribution")
        end = next(i for i in range(start, len(nodes)) if nodes[i]["kind"] == "page_break")
        nodes[start:end] = [
            {
                "kind": "exhibit",
                "exhibit_id": "EX-ATTRIBUTION",
                "section_key": "attribution",
                "section_owner": "attribution",
            }
        ]
    nodes.append({"kind": "page_break"})
    from .closing_page_model import SUPPORTED_REVISIONS as CLOSING_REVISIONS, build_closing_exhibit
    from .appendix_view import SUPPORTED_REVISIONS as APPENDIX_REVISIONS, build_appendix_views

    closing_review = d.get("closing_revision") in CLOSING_REVISIONS
    appendix_review = d.get("appendix_revision") in APPENDIX_REVISIONS
    include_appendix = d.get("include_appendix", True) is not False
    reference_nodes = []
    for item in refs.items:
        label = f"[{item['number']}] {item['publisher']}. {item['title']}."
        for key, prefix in [
            ("published_at", "Published"),
            ("updated_at", "Updated"),
            ("retrieved_at", "Retrieved"),
        ]:
            if item.get(key):
                label += f" {prefix}: {item[key]}."
        if not item.get("retrieved_at"):
            label += " Retrieval date not recorded."
        reference_nodes.append(
            {
                "kind": "reference",
                "text": label,
                "url": item["url"],
                "number": item["number"],
                "section_owner": "closing",
            }
        )
    if not include_appendix and reference_nodes:
        heading("References", section_key="closing")
        nodes.extend(reference_nodes)
        nodes.append({"kind": "page_break", "section_owner": "closing"})
    if closing_review:
        exhibits.append(build_closing_exhibit(data, appendix))
        nodes.append(
            {
                "kind": "exhibit",
                "exhibit_id": "EX-CLOSING",
                "section_key": "closing",
                "section_owner": "closing",
            }
        )
    else:
        heading("Closing", section_key="closing")
        if reference_nodes and not appendix_review and include_appendix:
            heading("References")
            nodes.extend(reference_nodes)
        resources = list(dict.fromkeys(x.strip() for x in d["resources"].splitlines() if x.strip()))
        if resources:
            heading("Recommended resources")
            for index, url in enumerate(resources):
                nodes.append(
                    {
                        "kind": "link",
                        "text": url,
                        "url": url,
                        "keep_with_next": len(resources) <= 6 and index < len(resources) - 1,
                    }
                )
        from .sender_identity import responsibility

        text(responsibility(approved.RESPONSIBILITY, d))
        text(d["closing"], "closing")
        text(
            "\n".join(
                filter(
                    None,
                    [
                        d.get("sender_name"),
                        d.get("sender_title"),
                        profile["agency"],
                        profile["office"],
                    ],
                )
            ),
            "signature",
        )
        if not include_appendix:
            text("The full supporting appendix is available upon request.", "closing")
    appendix_navigation = None
    if appendix_review:
        appendix_views, native_appendix, appendix_navigation = build_appendix_views(
            appendix, revision=d["appendix_revision"]
        )
        exhibits.extend(appendix_views)
    else:
        native_appendix = appendix_nodes(appendix)
    if (closing_review or not include_appendix) and reference_nodes and not appendix_review:
        marker = next(
            i for i, node in enumerate(native_appendix) if node.get("anchor") == "appendix-D"
        )
        native_appendix[marker + 1 : marker + 1] = [
            {
                "kind": "heading",
                "text": "Sources cited in this notification",
                "level": 2,
                "section_owner": "closing",
            },
            *reference_nodes,
        ]
    if cve_rows and not appendix_review:
        marker = next(
            (i for i, node in enumerate(native_appendix) if node.get("anchor") == "appendix-C"),
            None,
        )
        if marker is not None:
            native_appendix.insert(
                marker + 1,
                {
                    "kind": "table",
                    "headers": ["CVE", "Official reference", "CVSS", "EPSS", "CISA KEV"],
                    "rows": cve_rows,
                    "widths": [1.15, 1.1, 1.6, 1.45, 1.5],
                    "section_owner": "vulnerabilities",
                },
            )
    supporting_appendix = [*native_appendix, *supporting_images]
    if include_appendix:
        nodes.extend(supporting_appendix)
    # Page review is explicitly selected; existing and historical drafts keep
    # their pinned introduction until the reviewed revision is adopted.
    from .introduction_model import SUPPORTED_REVISIONS as INTRO_REVISIONS, build_introduction

    if d.get("introduction_revision") in INTRO_REVISIONS:
        first_break = next(i for i, n in enumerate(nodes) if n["kind"] == "page_break")
        nodes[:first_break] = [
            {
                "kind": "introduction",
                "section_key": "introduction",
                "model": build_introduction(data, exhibits),
            }
        ]
    policy = data.get("document_policy") or d.get("document_policy", {})
    from .appendix_view import COMPACT_REVISIONS

    if d.get("appendix_revision") in COMPACT_REVISIONS:
        for model in exhibits + [node["model"] for node in nodes if node["kind"] == "introduction"]:
            model["compact_appendix"] = True
            if "alt_text" in model:
                model["alt_text"] = (
                    model["alt_text"]
                    .replace(
                        "Full original fields are retained in Appendix A.",
                        "Supporting observations are retained in Appendix A.",
                    )
                    .replace(
                        "Full source descriptions and assessments are in Appendix C.",
                        "Supporting vulnerability records are in Appendix C.",
                    )
                )
    paragraph_alignment = policy.get("paragraph_alignment")
    if not include_appendix or paragraph_alignment == "justify":
        for model in exhibits + [node["model"] for node in nodes if node["kind"] == "introduction"]:
            if not include_appendix and model.get("type") != "appendix":
                model["include_appendix"] = False
                if "alt_text" in model:
                    model["alt_text"] = (
                        model.get("alt_text", "")
                        .replace(
                            "Full source references follow in the Companion Appendix.",
                            "Full source references appear in References.",
                        )
                        .replace(
                            "Supporting references are retained in Appendix D.",
                            "Supporting references appear in References.",
                        )
                        .replace(
                            "Full original fields are retained in Appendix A.",
                            "Full original fields are available upon request.",
                        )
                        .replace(
                            "Full source descriptions and assessments are in Appendix C.",
                            "Full source descriptions and assessments are available upon request.",
                        )
                    )
                for item in model.get("items", []):
                    if (
                        item.get("description_excerpt")
                        == "Published description unavailable; see Appendix C"
                    ):
                        item["description_excerpt"] = (
                            "Published description unavailable; supporting records are available upon request"
                        )
            if paragraph_alignment == "justify":
                model["paragraph_alignment"] = "justify"
    # Assign every native node a review owner, including interleaved appendix
    # partitions. Existing section keys remain the five builder sections.
    owner = "introduction"
    for node in nodes + ([] if include_appendix else supporting_appendix):
        owner = node.get("section_key", owner)
        node.setdefault("section_owner", owner)
    content = {
        "version": 3,
        "approved_copy_revision": approved.REVISION,
        "template": template,
        "sections": nodes,
        "citations": refs.items,
        "citation_integrity_issues": list(dict.fromkeys(citation_issues)),
        "exhibits": exhibits,
        "appendix": appendix,
        **(
            {"appendix_navigation": appendix_navigation}
            if appendix_navigation and include_appendix
            else {}
        ),
        **(
            {
                "include_appendix": False,
                "supporting_appendix_sections": supporting_appendix,
                "supporting_appendix_navigation": appendix_navigation or {},
            }
            if not include_appendix
            else {}
        ),
        "attribution_groups": attribution_groups,
        "excluded_cves": excluded,
        "source_selections": [
            {
                "id": r.get("id"),
                "revision_id": r.get("revision_id"),
                "body_sha256": r.get("body_sha256"),
            }
            for r in d["cve_records"]
        ],
        "block_revisions": [
            {"id": b["id"], "revision": b.get("revision", 1)} for b in data["explainers"]
        ],
    }
    from .recipient_edition import apply_edition

    return apply_edition(data, content)
