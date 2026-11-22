"""Intake validation constants and compatible aliases of shared network helpers."""

import re
from ipaddress import ip_network

from modules.tools.components.network_identity import (
    comparison_address,
    root_domain as root_domain,
)

# Retain the intake/standalone CLI API while Tools owns comparison semantics.
registry_address = comparison_address

REQUIRED_COLUMNS = ("tag", "hostname", "ip", "region")
_DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
# Final labels use the same DNS syntax, including IDNA A-labels. The bundled
# Public Suffix List, not an ASCII-letter TLD heuristic, establishes the root.
HOSTNAME = re.compile(rf"(?:{_DNS_LABEL}\.)+{_DNS_LABEL}", re.I)
CVE_TAG = re.compile(r"(?<![a-z0-9-])CVE-[0-9]{4}-[0-9]{4,}(?![a-z0-9-])", re.I)
PRIVATE_NETWORKS = tuple(
    ip_network(block) for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)
DOMAIN_TOKEN = re.compile(
    r"(?<![a-z0-9_.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}(?![a-z0-9_-]|\.[a-z0-9_-])",
    re.IGNORECASE,
)
