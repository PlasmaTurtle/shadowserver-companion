"""Strict, explicit company-host scope for contact discovery."""

from __future__ import annotations

import ipaddress
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

from attribution.matching import normalize_domain

from modules.tools.components.network_identity import comparison_address, extract_domain

MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_REQUESTS = 8
MAX_PAGE_REQUESTS = 6
MAX_REDIRECT_REQUESTS = 2
MAX_CANDIDATES = 50
MAX_SECONDS = 30
MAX_REQUEST_SECONDS = 8


class DiscoveryError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def hostname(value):
    """Use Attribution's DNS identity, then apply contact destination policy."""
    if not isinstance(value, str) or not value or len(value) > 253:
        raise DiscoveryError("invalid_scope", "An approved DNS hostname is required.")
    if any(c.isspace() or ord(c) < 32 for c in value) or any(c in value for c in "/\\:@%?#"):
        raise DiscoveryError("invalid_scope", "The approved hostname contains invalid characters.")
    try:
        normalized = normalize_domain(value)
    except ValueError:
        raise DiscoveryError(
            "invalid_scope", "The approved hostname must be a complete DNS name."
        ) from None
    labels = normalized.split(".")
    if labels[-1].isdigit() or labels[-1] in {"localhost", "local", "internal", "invalid", "test"}:
        raise DiscoveryError("invalid_scope", "The approved hostname must be a public DNS name.")
    return normalized


def approved_scope(root, aliases=()):
    """Approve only the supplied company host and its apex/www counterpart.

    A redirect never expands this pair to an arbitrary subdomain or provider.
    Every request still resolves and validates its own exact hostname.
    """
    root = hostname(root)
    if isinstance(aliases, str):
        raise DiscoveryError("invalid_scope", "Aliases must be an explicit list of hostnames.")
    parent = root[4:] if root.startswith("www.") else ""
    parent_parts = extract_domain(parent) if parent else None
    # A registrable business can itself be named www (for example a tenant
    # under github.io). Never widen that scope to the provider/public suffix.
    strip_www = bool(parent_parts and parent_parts.domain and parent_parts.suffix)
    counterpart = hostname(parent if strip_www else "www." + root)
    for alias in aliases:
        if hostname(alias) != counterpart:
            raise DiscoveryError("invalid_alias", "Only the company apex/www pair is supported.")
    return root, (counterpart,)


def approved_url(value, hosts):
    """Canonical HTTPS source; remove only recognized tracking-only queries."""
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or any(c.isspace() or ord(c) < 32 for c in value)
        or "\\" in value
    ):
        raise DiscoveryError("invalid_url", "A source URL is malformed.")
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "https":
            raise DiscoveryError(
                "https_required", "Only HTTPS sources are permitted; no downgrade was followed."
            )
        if parsed.username is not None or parsed.password is not None or "%" in parsed.netloc:
            raise DiscoveryError(
                "invalid_url", "Credentials or encoded source hostnames are not permitted."
            )
        if parsed.port not in (None, 443):
            raise DiscoveryError("invalid_url", "Only the standard HTTPS port is permitted.")
        host = hostname(parsed.hostname or "")
    except ValueError as error:
        if isinstance(error, DiscoveryError):
            raise
        raise DiscoveryError("invalid_url", "A source URL is malformed.") from None
    if host not in hosts:
        raise DiscoveryError(
            "outside_scope",
            "The source host is outside the explicitly approved company scope; review required.",
        )
    if parsed.query:
        tracking = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "utm_id",
            "utm_source_platform",
            "utm_creative_format",
            "utm_marketing_tactic",
            "cm_sp",
            "gclid",
            "fbclid",
            "msclkid",
        }
        try:
            names = [
                name.casefold()
                for name, _ in parse_qsl(
                    parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=32
                )
            ]
        except ValueError:
            names = []
        if not names or any(name not in tracking for name in names):
            raise DiscoveryError(
                "query_not_supported",
                "Unknown query parameters require manual review; the URL was not fetched.",
            )
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    return urlunsplit(("https", host, path, "", ""))


def public_address(value):
    try:
        address = comparison_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and any(
        address in network
        for network in (
            ipaddress.ip_network("2002::/16"),
            ipaddress.ip_network("2001::/32"),
            ipaddress.ip_network("64:ff9b::/96"),
            ipaddress.ip_network("64:ff9b:1::/48"),
        )
    ):
        return False
    return bool(
        address.is_global
        and not (
            address.is_multicast
            or address.is_reserved
            or address.is_loopback
            or address.is_link_local
            or address.is_unspecified
        )
    )
