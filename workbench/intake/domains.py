"""Offline hostname/IP helpers and workload validation constants."""

import re
from ipaddress import IPv6Address, ip_address, ip_network
import tldextract

REQUIRED_COLUMNS = ("tag", "hostname", "ip", "region")
_DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
# Final labels use the same DNS syntax, including IDNA A-labels. The bundled
# Public Suffix List, not an ASCII-letter TLD heuristic, establishes the root.
HOSTNAME = re.compile(rf"(?:{_DNS_LABEL}\.)+{_DNS_LABEL}", re.I)
CVE_TAG = re.compile(r"(?<![a-z0-9-])CVE-[0-9]{4}-[0-9]{4,}(?![a-z0-9-])", re.I)
PRIVATE_NETWORKS = tuple(
    ip_network(block) for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)
EXTRACT_DOMAIN = tldextract.TLDExtract(
    suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True
)
DOMAIN_TOKEN = re.compile(
    r"(?<![a-z0-9_.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}(?![a-z0-9_-]|\.[a-z0-9_-])",
    re.IGNORECASE,
)


def root_domain(hostname: str) -> str:
    """Use the installed PSL snapshot without making a network request."""
    extracted = EXTRACT_DOMAIN(hostname)
    return extracted.top_domain_under_public_suffix or hostname


def registry_address(value: str):
    address = ip_address(value)
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address
