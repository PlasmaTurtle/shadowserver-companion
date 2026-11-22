"""Conservative source-evidence checks, without inferring vulnerability merit."""

from __future__ import annotations

import math
import re

from .domains import CVE_TAG


_ABSENT = {
    "na",
    "none",
    "null",
    "unknown",
    "undefined",
    "unspecified",
    "unavailable",
    "undisclosed",
    "redacted",
    "notavailable",
    "notapplicable",
    "notdisclosed",
    "notreported",
    "notdetected",
}
_MAX_ABSENT_LENGTH = max(map(len, _ABSENT))
_CONDITION = re.compile(r"(?=[a-z0-9_.+/-]*[a-z])[a-z0-9][a-z0-9_.+/-]*", re.I)
_CVE_LIKE = re.compile(r"cve[-_\s]*(?:\d|$)", re.I)


def _absent_text(value):
    token = re.sub(r"[^a-z0-9]", "", value.casefold())
    return not token or token in _ABSENT


def version_is_placeholder(value):
    """Missing markers do not establish a software release; formats stay open.

    Vendor build strings and release names are legitimate source evidence, so
    this deliberately does not impose semver or require a numeric version.
    """
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, int):
        return False
    if isinstance(value, float):
        return not math.isfinite(value)
    if not isinstance(value, str):
        return True
    if _absent_text(value):
        return True
    # Also catch product prefixes such as PHP/unknown and version=N/A. Scan
    # backward once, keeping only a possible missing-marker suffix. Earlier
    # suffixes cannot match once this exceeds the longest normalized marker.
    # This avoids repeatedly normalizing long, delimiter-heavy input.
    folded = value.casefold()
    suffix = ""
    for index in range(len(folded) - 1, -1, -1):
        character = folded[index]
        if character in "/=:" and (not suffix or suffix in _ABSENT):
            return bool(folded[:index].strip())
        if "a" <= character <= "z" or "0" <= character <= "9":
            suffix = character + suffix
            if len(suffix) > _MAX_ABSENT_LENGTH:
                return False
    return False


def finding_rejection_reason(value):
    """Require a condition identifier, not severity plus unrelated banner text.

    Unknown scanner condition IDs remain supported. Only malformed CVE-shaped
    IDs and content that is not a machine-readable finding tag are rejected;
    catalog absence and vendor-specific tag names are not rejection criteria.
    """
    if not isinstance(value, str):
        return "unsupported_finding"
    # Check the remainder as well: one valid CVE must not hide a clipped second
    # identifier, and prefixes/suffixes must not turn a substring into a CVE.
    if any(
        _CVE_LIKE.search(token) and not CVE_TAG.fullmatch(token)
        for token in re.split(r"[;,:\s]+", value)
    ):
        return "malformed_cve_identifier"
    groups = [part.strip() for part in re.split(r"[;,:]", value) if part.strip()]
    if not groups:
        return "unsupported_finding"
    for group in groups:
        if _CONDITION.fullmatch(group) and not _absent_text(group):
            continue
        # Whitespace-separated CVE lists are common too. Arbitrary prose is
        # not an identifier and does not become evidence by splitting words.
        if all(
            CVE_TAG.fullmatch(token)
            or (token.casefold().startswith("eol-") and _CONDITION.fullmatch(token))
            for token in group.split()
        ):
            continue
        return "unsupported_finding"
    return None
