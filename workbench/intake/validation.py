"""Deterministic pre-lookup row policy; complete input records are retained."""

from __future__ import annotations
import re
from collections.abc import Iterable
from ipaddress import ip_address
from .domains import (
    REQUIRED_COLUMNS,
    HOSTNAME,
    CVE_TAG,
    PRIVATE_NETWORKS,
    EXTRACT_DOMAIN,
    registry_address,
)
from .records import UnvalidatedEntry, ValidatedEntry
from .findings import finding_rejection_reason, version_is_placeholder
from .versions import selected_version


class EntryValidator:
    def __init__(self, regions: set[str], *, com_only=None, exclude_numeric_roots=None):
        if not regions:
            raise ValueError("Supply at least one in-jurisdiction region")
        self.regions = frozenset(region.casefold() for region in regions)
        # Accepted only for callers loading old configurations. Suffix and
        # numeric-root preferences were obsolete spreadsheet workarounds, not
        # domain-validity rules; they no longer affect admission.

    def validate(self, entries: Iterable[UnvalidatedEntry]) -> list[ValidatedEntry]:
        validated = []
        for entry in entries:
            result = self.validate_entry(entry)
            if result is not None:
                validated.append(result)
        return validated

    def validate_entry(self, entry: UnvalidatedEntry, *, profile=None) -> ValidatedEntry | None:
        if self.rejection_reason(entry, profile=profile) is not None:
            return None
        fields = entry.fields
        address = ip_address(fields["ip"])
        comparison_ip = registry_address(fields["ip"])
        return ValidatedEntry(
            source=entry,
            ip=address.compressed,
            private_ip=any(comparison_ip in network for network in PRIVATE_NETWORKS),
        )

    def rejection_reason(self, entry: UnvalidatedEntry, *, profile=None) -> str | None:
        fields = entry.fields
        if any(
            fields.get(name) is None
            or (isinstance(fields.get(name), str) and not fields[name].strip())
            for name in REQUIRED_COLUMNS
        ):
            return "missing_required_value"
        if str(fields["region"]).casefold() not in self.regions:
            return "outside_jurisdiction"
        # Keep the established HTTP/standalone rule. Reviewed service and
        # incident adapters may legitimately omit a software version; their
        # evidence consists of protocol responses, secret checks or indicators.
        # EOL findings still require an actual software version, not an IKE/RPC
        # protocol revision. This never manufactures a missing source value.
        tags = str(fields["tag"])
        has_eol = re.search(r"(?:^|[;,:\s])eol(?:$|[-;,:\s])", tags, re.I)
        reviewed_profile = profile or {}
        finding_reason = finding_rejection_reason(fields["tag"])
        if finding_reason == "malformed_cve_identifier":
            return finding_reason
        version = selected_version(fields, reviewed_profile)["raw_version"]
        version_missing = version is None or not str(version).strip()
        if has_eol and (version_missing or reviewed_profile.get("version_semantics") == "protocol"):
            return "missing_version"
        requires_version = bool(has_eol) or (
            reviewed_profile.get("version_requirement", "cve_or_version") == "cve_or_version"
            and not CVE_TAG.search(tags)
        )
        if requires_version and version_missing:
            return "missing_version"
        if requires_version and version_is_placeholder(version):
            return "placeholder_version"
        if finding_reason:
            return finding_reason
        hostname = fields["hostname"]
        if not isinstance(hostname, str) or len(hostname) > 253 or not HOSTNAME.fullmatch(hostname):
            return "invalid_hostname"
        extracted = EXTRACT_DOMAIN(hostname)
        if not extracted.suffix or not extracted.domain:
            return "invalid_hostname"
        reported_ip = fields["ip"]
        if not isinstance(reported_ip, str):
            return "invalid_ip"
        try:
            ip_address(reported_ip)
        except ValueError:
            return "invalid_ip"
        return None
