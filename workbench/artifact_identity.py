"""Bind verified package bytes to the database record that offers them.

Older manifests did not carry all modern identities. Check every identity they
do declare without manufacturing metadata or rewriting a retained package.
"""


def _matches(record, manifest, pairs, kind):
    for column, field in pairs:
        if field in manifest and column in record and record[column] != manifest[field]:
            raise ValueError(f"{kind} package identity does not match its saved database record")


def report_identity(record, manifest, resolve_entity):
    record = dict(record)
    # Case-based analyst certification always records package identities. Its
    # database origin cannot be downgraded by pointing at an identifier-free
    # legacy package. Pre-case migrations retain legacy_finalized instead;
    # path-only recovery has no saved origin to assert yet. Older case-based
    # manifests are accepted without demanding a newer schema number.
    requires_identity = (
        manifest.get("schema_version", 0) >= 3 or record.get("certification_source") == "analyst"
    )
    if requires_identity and (
        any(
            not isinstance(manifest.get(key), str) or not manifest[key]
            for key in ("report_id", "case_id", "entity_id")
        )
        or type(manifest.get("revision")) is not int
        or manifest["revision"] < 1
    ):
        raise ValueError("Report package is missing its required identity")
    _matches(
        record,
        manifest,
        (
            ("id", "report_id"),
            ("case_id", "case_id"),
            ("lead_id", "entity_id"),
            ("revision", "revision"),
        ),
        "Report",
    )
    # In original manifests notification_id meant the business; case-based
    # manifests explicitly carry case_id and retain entity_id separately.
    if "case_id" not in manifest and "entity_id" not in manifest:
        _matches(record, manifest, (("lead_id", "notification_id"),), "Report")
    elif "case_id" in manifest and "notification_id" in manifest:
        if manifest["case_id"] != manifest["notification_id"]:
            raise ValueError("Report package notification identity is inconsistent")
    original_entity = manifest.get("entity_id")
    if original_entity and record.get("entity_id"):
        # A merge moves current ownership, never the package's original entity.
        if resolve_entity(original_entity) != record["entity_id"]:
            raise ValueError("Report package belongs to a different current business")


def closure_identity(record, manifest):
    record = dict(record)
    # Closures were introduced with both identifiers in their first format.
    if any(
        not isinstance(manifest.get(key), str) or not manifest[key]
        for key in ("closure_id", "case_id")
    ):
        raise ValueError("Closing package is missing its required identity")
    _matches(record, manifest, (("id", "closure_id"), ("case_id", "case_id")), "Closing")
    if "snapshot_sha256" in record and (
        record["snapshot_sha256"] != manifest["files"].get("snapshot.json")
    ):
        raise ValueError("Closing package snapshot differs from its saved database digest")
