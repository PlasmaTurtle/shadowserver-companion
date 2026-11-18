"""One deterministic narrative per notification, across all included findings.

The approved template supplies the shared prose. Only aggregation, grammatical
number and the scope of insertable values change. Source rows, per-finding
overrides and the historical template remain intact.
"""

from collections import OrderedDict
from datetime import date

from . import approved_template as approved

REVISION = "consolidated-2026-11-07-v1"


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


def generate_narrative(lead, draft):
    groups = [g for g in approved.narrative_groups(lead, draft) if not g.get("excluded")]
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
    template = approved.NARRATIVE
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
    versions = grouped_values(
        groups, lambda g: (software(g), g["version"] or "not supplied in the source record")
    )
    version_text = "; ".join(
        (reported_version(members[0]) if len(versions) > 1 else version)
        + (" (" + scopes(members, detailed=detailed_scopes) + ")" if len(versions) > 1 else "")
        for (_, version), members in versions.items()
    )
    ranges = grouped_values(
        groups,
        lambda g: g["affected_versions"]
        or (
            "not supplied in the selected source"
            if g["cves"]
            else "not applicable; no CVE reported"
        ),
    )
    range_text = "; ".join(
        value + (" (" + scopes(members, detailed=detailed_scopes) + ")" if len(ranges) > 1 else "")
        for value, members in ranges.items()
    )
    if len(labels) > 1:
        template = template.replace("a critical security finding", "critical security findings")
    if len(hosts) > 1:
        template = template.replace("the domain [ASSET HOSTNAME]", "the domains [ASSET HOSTNAME]")
    if len(versions) > 1:
        template = template.replace(
            "The reported software version is", "The reported software versions are"
        )
    if len(ips) > 1 or len(hosts) > 1:
        template = template.replace(
            "the reported asset is associated", "the reported assets are associated"
        )
    profile = approved.entity_profile(lead)
    stamp = date.fromisoformat(draft["report_date"])
    values = {
        "TODAY'S DATE": stamp.strftime("%B") + f" {stamp.day}, {stamp.year}",
        "ASSET IP's": joined(ips),
        "ASSET PROTOCOL": "",
        "ASSET PORT": service_text,
        "ASSET HOSTNAME": joined(hosts),
        "VULNERABILITIES": joined(labels),
        "FINDING STATEMENT": statement,
        "ASSET SOFTWARE": joined(software(g) for g in groups),
        "ASSET SOFTWARE VERSION": version_text,
        "CVE AFFECTED VERSIONS": range_text,
        "ORGANIZATION": draft.get("company") or lead["company"] or lead["domain"],
        "ENTITY CITY": profile.get("city") or "city not recorded",
        "ENTITY STATE": " " + (profile.get("state") or "state not recorded"),
    }
    narrative = approved.TOKENS.sub(lambda m: str(values[m.group(1)]), template)
    # Manual insertables can contain line breaks; only their rendered spacing
    # changes. The exact supplied values remain in the draft/source appendix.
    return " ".join(narrative.split())
