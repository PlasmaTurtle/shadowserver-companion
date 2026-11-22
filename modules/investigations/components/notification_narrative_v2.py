"""One deterministic narrative per notification, across all included findings.

The approved template supplies the shared prose. Aggregation, grammatical
number and evidence-aware sentences are deterministic; missing dates, products
and versions are never invented. Source rows, per-finding overrides and the
historical template remain intact. This module does not perform lookups.
"""

from modules.accretion.components.intake.versions import entry_fields, has_active_findings
from collections import OrderedDict

from modules.investigations.components import approved_template as approved

REVISION = "consolidated-2026-11-08-v2"


def unique(values):
    return list(dict.fromkeys(" ".join(str(v).split()) for v in values if str(v).strip()))


def joined(values):
    values = unique(values)
    if len(values) < 2:
        return "".join(values)
    if len(values) == 2:
        return " and ".join(values)
    return ", ".join(values[:-1]) + ", and " + values[-1]


def service(group):
    return (
        (group["protocol"] or "protocol not reported")
        + " "
        + (group["port"] or "port not reported")
    )


def software(group):
    return group["software"] or "software not identified in the source record"


def reported_version(group):
    version = group["version"] or "not supplied in the source record"
    product = group["software"]
    # Source versions sometimes include the product and sometimes are just a
    # number. Keep a bare number tied to its product in mixed-product prose.
    if product and product.casefold() not in version.casefold():
        return product + " " + version
    return version


def service_scope(members):
    return "; ".join(
        host + ": " + joined(ip for g in group for ip in g["ips"])
        for host, group in grouped_values(members, lambda g: g["hostname"]).items()
    )


def scopes(groups, *, detailed=False):
    if not detailed:
        return joined(g["hostname"] for g in groups)
    by_endpoint = OrderedDict()
    for group in groups:
        key = (group["hostname"], service(group))
        by_endpoint.setdefault(key, []).extend(group["ips"])
    return "; ".join(
        host + " (" + endpoint + "; " + joined(ips) + ")"
        for (host, endpoint), ips in by_endpoint.items()
    )


def findings(group):
    return group["cves"] or [group["tag"]]


def grouped_values(groups, key):
    result = OrderedDict()
    for group in groups:
        result.setdefault(key(group), []).append(group)
    return result


def published_product(group, draft):
    """Use a selected CNA product only when its association is unambiguous.

    This fills presentation text, never the detected version or source row.
    Every included CVE must identify the same single affected product. Missing
    records, excluded CVEs, and multi-product advisories cannot supply a guess.
    """
    if not group["cves"]:
        return ""
    products = []
    for cve in group["cves"]:
        records = [
            record
            for record in draft.get("cve_records", [])
            if record.get("id") == cve and record.get("verification_status") == "published"
        ]
        names = unique(
            product.get("product", "")
            for record in records
            for product in record.get("affected", [])
            if product.get("product")
            and (
                product.get("defaultStatus") == "affected"
                or any(v.get("status") == "affected" for v in product.get("versions", []))
            )
        )
        if len(names) != 1:
            return ""
        products.extend(names)
    names = unique(products)
    return names[0] if len(names) == 1 else ""


def published_ranges(group, draft):
    """Avoid repeating a CNA product name already present in its version text."""
    text = group["affected_versions"]
    override = draft.get("narrative_values", {}).get(group["key"], {}).get("affected_versions")
    if override and override.strip():
        return text
    for record in draft.get("cve_records", []):
        if (
            record.get("id") not in group["cves"]
            or record.get("verification_status") != "published"
        ):
            continue
        for product in record.get("affected", []):
            name = str(product.get("product", "")).strip()
            for version in product.get("versions", []):
                value = str(version.get("version", ""))
                if (
                    name
                    and version.get("status") == "affected"
                    and value.casefold().startswith(name.casefold() + " ")
                ):
                    prefix = record["id"] + " — "
                    text = text.replace(prefix + name + " " + value, prefix + value)
    return text


def version_statement(groups, *, detailed=False):
    """Keep unknown versions separate from published affected-version ranges."""
    known = [group for group in groups if group["version"]]
    missing = [group for group in groups if not group["version"]]
    versions = grouped_values(known, lambda g: (software(g), g["version"]))
    version_text = "; ".join(
        (reported_version(members[0]) if len(versions) > 1 else version)
        + (" (" + scopes(members, detailed=detailed) + ")" if len(versions) > 1 or missing else "")
        for (_, version), members in versions.items()
    )
    ranges = grouped_values(groups, lambda g: g["affected_versions"])
    range_text = "; ".join(
        value + (" (" + scopes(members, detailed=detailed) + ")" if len(ranges) > 1 else "")
        for value, members in ranges.items()
        if value
    )
    # Preserve the reviewed sentence when every value it requires is present.
    if not missing and all(g["affected_versions"] for g in groups):
        return (
            (
                "The reported software version is "
                if len(versions) == 1
                else "The reported software versions are "
            )
            + version_text
            + ", which may fall within the affected ranges of "
            + range_text
            + "."
        )
    sentences = []
    if known:
        sentences.append(
            (
                "The reported software version is "
                if len(versions) == 1
                else "The reported software versions are "
            )
            + version_text
            + "."
        )
    if missing:
        sentences.append(
            "A software version was not supplied for " + scopes(missing, detailed=detailed) + "."
            if known
            else (
                "The supplied observation does not include a software version."
                if len(groups) == 1
                else "The supplied observations do not include a software version."
            )
        )
    if range_text:
        sentences.append(
            (
                "The published affected range is "
                if len([r for r in ranges if r]) == 1
                else "The published affected ranges are "
            )
            + range_text
            + "."
        )
    without_range = [g for g in groups if g["cves"] and not g["affected_versions"]]
    if without_range:
        sentences.append(
            "Affected version ranges were not supplied in the selected source"
            + (
                " for " + scopes(without_range, detailed=detailed)
                if len(without_range) < len(groups)
                else ""
            )
            + "."
        )
    without_cve = [g for g in groups if not g["cves"]]
    if without_cve:
        sentences.append(
            "No CVE was reported"
            + (
                " for " + scopes(without_cve, detailed=detailed)
                if len(without_cve) < len(groups)
                else " for this finding"
            )
            + "."
        )
    if range_text or without_range:
        sentences.append(
            "Applicability requires confirmation against the installed product and version."
        )
    return " ".join(sentences)


def presentation_groups(lead, draft):
    """Share deterministic insertable values with the builder, without writes."""
    projected = {
        **lead,
        "entries": [
            {**entry, "source": {**entry.get("source", {}), "fields": entry_fields(entry)}}
            for entry in lead["entries"]
            if has_active_findings(entry)
        ],
    }
    groups = approved.narrative_groups(projected, draft)
    for group in groups:
        if group.get("excluded"):
            continue
        if not group["software"]:
            group["software"] = published_product(group, draft)
        group["affected_versions"] = published_ranges(group, draft)
    return groups


def generate_narrative(lead, draft):
    groups = [g for g in presentation_groups(lead, draft) if not g.get("excluded")]
    if not groups:
        return ""
    ips = unique(ip for group in groups for ip in group["ips"])
    hosts = unique(g["hostname"] for g in groups)
    labels = unique(label for group in groups for label in findings(group))
    services = grouped_values(groups, service)
    # Hostnames alone are insufficient when one host has different findings
    # or versions on different reported IPs, even if the port is the same.
    detailed_scopes = len(services) > 1 or len(hosts) < len(groups)
    service_text = (
        next(iter(services))
        if len(services) == 1
        else "; ".join(
            label + " (" + service_scope(members) + ")" for label, members in services.items()
        )
    )
    # A common finding can cover many hosts/IPs. Differing products or finding
    # sets carry their own endpoint scope, avoiding a cross-product of claims.
    finding_groups = grouped_values(groups, lambda g: (tuple(findings(g)), software(g)))
    template = approved.NARRATIVE.replace(
        "On [TODAY'S DATE], the United States Secret service",
        "The United States Secret Service",
    )
    # report_date is the date of the document, not proof of when the agency
    # received the scan. There is no receipt-date field in the current model.
    statement = ""
    if len(finding_groups) > 1:
        clauses = [
            joined(ids)
            + " (associated with "
            + product
            + " on "
            + scopes(members, detailed=detailed_scopes)
            + ")"
            for (ids, product), members in finding_groups.items()
        ]
        statement = "The identified " + (
            "vulnerability is " if len(labels) == 1 else "vulnerabilities are "
        )
        statement += "; ".join(clauses) + "."
        template = template.replace(
            "The identified vulnerability is [VULNERABILITIES], which are associated with [ASSET SOFTWARE].",
            "[FINDING STATEMENT]",
        )
    elif len(labels) == 1:
        template = template.replace(
            "which are associated with [ASSET SOFTWARE]",
            "which is associated with [ASSET SOFTWARE]",
        )
    else:
        template = template.replace(
            "The identified vulnerability is", "The identified vulnerabilities are"
        )
    template = template.replace(
        "The reported software version is [ASSET SOFTWARE VERSION], which may fall within the affected ranges of [CVE AFFECTED VERSIONS].",
        "[VERSION STATEMENT]",
    )
    if len(labels) > 1:
        template = template.replace("a critical security finding", "critical security findings")
    if len(hosts) > 1:
        template = template.replace("the domain [ASSET HOSTNAME]", "the domains [ASSET HOSTNAME]")
    if len(ips) > 1 or len(hosts) > 1:
        template = template.replace(
            "the reported asset is associated", "the reported assets are associated"
        )
    profile = approved.entity_profile(lead)
    location = ", ".join(str(profile[k]).strip() for k in ("city", "state") if profile.get(k))
    template = template.replace(
        " in [ENTITY CITY],[ENTITY STATE]", " in [ENTITY LOCATION]" if location else ""
    )
    values = {
        "ASSET IP's": joined(ips),
        "ASSET PROTOCOL": "",
        "ASSET PORT": service_text,
        "ASSET HOSTNAME": joined(hosts),
        "VULNERABILITIES": joined(labels),
        "FINDING STATEMENT": statement,
        "ASSET SOFTWARE": joined(software(g) for g in groups),
        "VERSION STATEMENT": version_statement(groups, detailed=detailed_scopes),
        "ORGANIZATION": draft.get("company") or lead["company"] or lead["domain"],
        "ENTITY LOCATION": location,
    }
    narrative = approved.TOKENS.sub(lambda m: str(values[m.group(1)]), template)
    # Manual insertables can contain line breaks; only their rendered spacing
    # changes. The exact supplied values remain in the draft/source appendix.
    return " ".join(narrative.split())
