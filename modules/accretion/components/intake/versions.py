"""Software-version selection without modifying original report columns."""

from .findings import version_is_placeholder


def version_sources(fields, profile=None):
    """Component versions are software evidence; protocol revisions stay separate."""
    names = ("component_version", "device_version", "version")
    if (profile or {}).get("version_semantics") in {"protocol", "unspecified"}:
        names = ("version",)
    names = (profile or {}).get("version_fields") or names
    return [
        {"source_field": name, "raw_version": fields[name]}
        for name in names
        if fields.get(name) is not None and str(fields[name]).strip()
    ]


def selected_version(fields, profile=None):
    sources = version_sources(fields, profile)
    return next(
        (s for s in sources if not version_is_placeholder(s["raw_version"])),
        sources[0]
        if sources
        else {"source_field": "version", "raw_version": fields.get("version")},
    )


def entry_fields(entry):
    """Presentation projection, respecting the version pinned at intake.

    Older normalized observations retain their prior interpretation and group
    keys. Newly imported observations pin the selected component/version value.
    The complete original columns remain in source.fields and the original file.
    """
    fields = entry.get("source", {}).get("fields", {})
    normalized = entry.get("normalized") or {}
    value = (
        normalized["raw_version"]
        if "raw_version" in normalized
        else selected_version(fields, normalized.get("profile"))["raw_version"]
    )
    projected = {**fields, "version": value or ""}
    if normalized.get("case_condition_scope") and "active_conditions" in normalized:
        # The release-line suffix belongs to finding identity. Report snippets
        # still match the original scanner tag; the version has its own field.
        projected["tag"] = ";".join(
            condition.split(":", 1)[0] if condition.startswith("eol") else condition
            for condition in normalized["active_conditions"]
        )
    return projected


def has_active_findings(entry):
    """Supporting attribution rows remain evidence without becoming new findings."""
    normalized = entry.get("normalized") or {}
    return not normalized.get("case_condition_scope") or bool(normalized.get("active_conditions"))


def project_conditions(entry, conditions):
    return {
        **entry,
        "normalized": {
            **entry.get("normalized", {}),
            "case_condition_scope": True,
            "active_conditions": conditions,
            "active_cves": [value for value in conditions if value.startswith("CVE-")],
        },
    }
