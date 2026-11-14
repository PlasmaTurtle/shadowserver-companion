"""Product identities and conservative version candidates from preserved CVE statements.

CPE configuration logic and CNA statements remain in the original record. A positive
version comparison is a research candidate, never proof of endpoint applicability.
"""

import hashlib
import json
import re

_PLACEHOLDERS = {"", "n/a", "na", "unknown", "unspecified", "not applicable", "none", "*", "-"}


def normalized(value):
    return " ".join(str(value or "").replace("_", " ").casefold().split())


def meaningful(value):
    return isinstance(value, str) and normalized(value) not in _PLACEHOLDERS


def identity(vendor, product, source=""):
    value = normalized(vendor) + "\0" + normalized(product)
    if not meaningful(vendor):
        value += "\0" + str(source)
    return "product:" + hashlib.sha256(value.encode()).hexdigest()[:24]


def cpe_parts(value):
    if not isinstance(value, str) or not value.startswith("cpe:2.3:"):
        return None
    parts = re.split(r"(?<!\\):", value)
    if len(parts) != 13:
        return None
    return [
        re.sub(r"\\(.)", r"\1", item) if index in (3, 4) else item
        for index, item in enumerate(parts)
    ]


def _cpe_nodes(node, path="configurations", inherited=False, depth=0):
    if depth > 40:
        return
    if isinstance(node, list):
        for i, child in enumerate(node):
            yield from _cpe_nodes(child, f"{path}[{i}]", inherited, depth + 1)
    elif isinstance(node, dict):
        if node.get("negate") is True:
            return
        conditional = inherited or node.get("negate") is True or node.get("operator") == "AND"
        for i, item in enumerate(node.get("cpeMatch", [])):
            if isinstance(item, dict):
                yield item, f"{path}.cpeMatch[{i}]", conditional
        for key in ("nodes", "children"):
            yield from _cpe_nodes(node.get(key, []), f"{path}.{key}", conditional, depth + 1)


def product_statements(cve):
    """Yield one source statement per product rule, retaining original identity."""
    for match, pointer, conditional in _cpe_nodes(cve.get("configurations", [])):
        parts = cpe_parts(match.get("criteria"))
        if not parts or match.get("vulnerable") is not True or not meaningful(parts[4]):
            continue
        vendor, product = parts[3], parts[4]
        conditions = []
        if conditional:
            conditions.append("Additional AND/negation configuration requirements")
        if any(v not in ("*", "-") for v in parts[7:]):
            conditions.append("Platform, edition, language or target requirements")
        if parts[6] not in ("*", "-"):
            conditions.append("Update/build label: " + parts[6])
        rule = {
            "kind": "CPE",
            "source": "NVD CPE configuration",
            "pointer": pointer,
            "criteria": match["criteria"],
            "status": "affected",
            "version": parts[5],
            "update": parts[6],
            "part": parts[2],
            "conditions": conditions,
            **{
                k: match[k]
                for k in (
                    "versionStartIncluding",
                    "versionStartExcluding",
                    "versionEndIncluding",
                    "versionEndExcluding",
                )
                if k in match
            },
        }
        yield identity(vendor, product), vendor, product, rule
    affected = cve.get("affected", [])
    if isinstance(affected, dict):
        affected = [affected]
    for group_index, group in enumerate(affected if isinstance(affected, list) else []):
        if not isinstance(group, dict):
            continue
        entries = group.get("affectedData", [group] if "product" in group else [])
        for entry_index, entry in enumerate(entries if isinstance(entries, list) else []):
            if not isinstance(entry, dict) or not meaningful(entry.get("product")):
                continue
            vendor = str(entry.get("vendor") or "")
            product = entry["product"]
            product_id = identity(
                vendor, product, group.get("source") or cve.get("sourceIdentifier") or cve.get("id")
            )
            vendor = vendor if meaningful(vendor) else "Unknown vendor"
            conditions = []
            for field in ("platforms", "modules", "programFiles", "programRoutines"):
                if entry.get(field):
                    conditions.append(
                        field + ": " + json.dumps(entry[field], ensure_ascii=False)[:500]
                    )
            base = {
                "kind": "CNA",
                "source": str(
                    group.get("source") or cve.get("sourceIdentifier") or "CVE affected statement"
                ),
                "pointer": f"affected[{group_index}].affectedData[{entry_index}]",
                "conditions": conditions,
                "default_status": entry.get("defaultStatus", "unknown"),
            }
            versions = entry.get("versions")
            if not isinstance(versions, list) or not versions:
                yield (
                    product_id,
                    vendor,
                    product,
                    {**base, "status": entry.get("defaultStatus", "unknown"), "version": "*"},
                )
            else:
                for version_index, version in enumerate(versions):
                    if isinstance(version, dict):
                        yield (
                            product_id,
                            vendor,
                            product,
                            {
                                **base,
                                **version,
                                "pointer": base["pointer"] + f".versions[{version_index}]",
                            },
                        )


def products_for_record(cve):
    result = {}
    for product_id, vendor, product, rule in product_statements(cve):
        if rule.get("status") == "unaffected":
            continue
        row = result.setdefault(
            product_id,
            {
                "id": product_id,
                "vendor": vendor,
                "product": product,
                "sources": set(),
                "aliases": set(),
                "rule_count": 0,
            },
        )
        row["sources"].add(rule["kind"])
        row["aliases"].add((vendor, product, rule["kind"]))
        row["rule_count"] += 1
    return result


def version_label(rule):
    if rule.get("kind") == "CPE":
        bounds = []
        for key, label in (
            ("versionStartIncluding", "≥"),
            ("versionStartExcluding", ">"),
            ("versionEndIncluding", "≤"),
            ("versionEndExcluding", "<"),
        ):
            if rule.get(key):
                bounds.append(label + " " + str(rule[key]))
        if bounds:
            return " and ".join(bounds)
        version = str(rule.get("version", "*"))
        update = rule.get("update")
        return ("All versions" if version == "*" else version) + (
            " · " + update if update not in (None, "*", "-") else ""
        )
    value = str(rule.get("version", "*"))
    if "lessThan" in rule:
        value = f"≥ {value} and < {rule['lessThan']}"
    elif "lessThanOrEqual" in rule:
        value = f"≥ {value} and ≤ {rule['lessThanOrEqual']}"
    if rule.get("changes"):
        value += " · exceptions apply"
    return "All versions" if value == "*" else value


def _numeric(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,8}(?:\.\d{1,8}){0,5}", value):
        return None
    return tuple(int(part) for part in value.split("."))


def _compare(left, right):
    size = max(len(left), len(right))
    a, b = left + (0,) * (size - len(left)), right + (0,) * (size - len(right))
    return (a > b) - (a < b)


def version_candidate(vendor, product, observed, rule):
    """Never infer an endpoint finding from a product name or unsafe version ordering."""
    observed = str(observed or "").strip()
    if not observed or len(observed) > 200:
        return {"state": "unresolved", "reason": "A reported version is needed"}
    if rule.get("conditions"):
        return {
            "state": "unresolved",
            "reason": "Additional product or configuration requirements need context",
        }
    if rule.get("changes"):
        return {
            "state": "unresolved",
            "reason": "The source lists version exceptions; inspect the complete statement",
        }
    status = rule.get("status", "unknown")
    version = str(rule.get("version", "*"))
    bounds = any(
        k in rule
        for k in (
            "lessThan",
            "lessThanOrEqual",
            "versionStartIncluding",
            "versionStartExcluding",
            "versionEndIncluding",
            "versionEndExcluding",
        )
    )
    if not bounds:
        if version not in ("*", "-") and observed != version:
            return {
                "state": "not_matched",
                "reason": "Reported version differs from this exact source version",
            }
        if version == "-" or status == "unknown":
            return {
                "state": "unresolved",
                "reason": "The source does not establish an affected version",
            }
        if status == "unaffected":
            return {"state": "not_matched", "reason": "The source marks this version unaffected"}
        return {
            "state": "candidate",
            "reason": "Version matches an affected source statement; endpoint applicability is not verified",
        }
    vendor_name, product_name = normalized(vendor), normalized(product)
    supported = (
        vendor_name == "php"
        and product_name == "php"
        or vendor_name in {"apache", "apache software foundation"}
        and product_name in {"http server", "httpd", "apache http server"}
        or vendor_name == "roundcube"
        and product_name in {"roundcube", "webmail", "roundcube webmail"}
        or vendor_name == "microsoft"
        and product_name.startswith(("exchange", "microsoft exchange"))
    )
    if rule.get("versionType") == "semver":
        supported = True
    current = _numeric(observed)
    if not supported or current is None:
        return {
            "state": "unresolved",
            "reason": "This product's version ordering is not supported; compare the source range",
        }
    comparisons = []
    if rule.get("kind") == "CNA":
        comparisons.extend([(version, ">=")])
        if "lessThan" in rule:
            comparisons.append((rule["lessThan"], "<"))
        if "lessThanOrEqual" in rule:
            comparisons.append((rule["lessThanOrEqual"], "<="))
    else:
        comparisons.extend(
            (rule[key], op)
            for key, op in (
                ("versionStartIncluding", ">="),
                ("versionStartExcluding", ">"),
                ("versionEndIncluding", "<="),
                ("versionEndExcluding", "<"),
            )
            if key in rule
        )
        if version not in ("*", "-"):
            comparisons.append((version, "="))
    for boundary, op in comparisons:
        number = _numeric(boundary)
        if number is None:
            return {
                "state": "unresolved",
                "reason": "The affected range uses a custom version format",
            }
        compared = _compare(current, number)
        if not {
            ">=": compared >= 0,
            ">": compared > 0,
            "<=": compared <= 0,
            "<": compared < 0,
            "=": compared == 0,
        }[op]:
            return {
                "state": "not_matched",
                "reason": "Reported version is outside this source range",
            }
    if status != "affected":
        return {
            "state": "not_matched" if status == "unaffected" else "unresolved",
            "reason": "The source does not mark this matching range affected",
        }
    return {
        "state": "candidate",
        "reason": "Version is within the source range; endpoint applicability is not verified",
    }


def record_versions(cve, product_id, observed="", limit=30):
    versions, total = [], 0
    seen = set()
    for pid, vendor, product, rule in product_statements(cve):
        if pid != product_id:
            continue
        key = json.dumps(rule, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        total += 1
        if len(versions) < limit:
            versions.append(
                {
                    **rule,
                    "range": version_label(rule),
                    "match": version_candidate(vendor, product, observed, rule)
                    if observed
                    else None,
                }
            )
    return versions, total
