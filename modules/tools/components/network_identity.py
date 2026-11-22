"""Offline network identity primitives; callers own eligibility and saved-key policy."""

from ipaddress import IPv4Address, IPv6Address, ip_address

import tldextract

# Use the bundled PSL snapshot, including tenant boundaries such as github.io.
# The library returns ExtractResult; an absent root stays absent for the caller
# to interpret. Extraction is deliberately not DNS-name or URL validation.
extract_domain = tldextract.TLDExtract(
    suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True
)


def root_domain(hostname: str) -> str:
    """Return the registrable domain, or the unchanged input if PSL has no root.

    Call extract_domain directly when an absent registrable domain must remain
    distinguishable from the supplied host, for example admission and DNS scope.
    """
    return extract_domain(hostname).top_domain_under_public_suffix or hostname


def comparison_address(
    value: str | int | bytes | IPv4Address | IPv6Address,
) -> IPv4Address | IPv6Address:
    """Parse an IP and compare IPv4-mapped IPv6 as the embedded IPv4 address.

    Accept the standard ``ip_address`` inputs and raise its ValueError for an
    invalid address. No trimming, zone rejection or public-address policy is
    applied. Use ip_address directly when the original address family is part
    of a stored identity; this function does not migrate or rewrite records.
    """
    address = ip_address(value)
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address
