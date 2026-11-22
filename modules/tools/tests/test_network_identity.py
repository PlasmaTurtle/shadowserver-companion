"""Offline suffix boundaries and mapped-IP comparison for real tool callers."""

from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
import subprocess
import sys

import pytest

from modules.tools.components.network_identity import (
    comparison_address,
    extract_domain,
    root_domain,
)


@pytest.mark.parametrize(
    "host,root,suffix",
    [
        ("mail.example.co.uk", "example.co.uk", "co.uk"),
        ("mail.tenant.github.io", "tenant.github.io", "github.io"),
        ("www.github.io", "www.github.io", "github.io"),
        ("co.uk", "", "co.uk"),
        ("localhost", "", ""),
        ("example.notarealsuffix", "", ""),
    ],
)
def test_offline_suffix_information_keeps_tenant_and_missing_root_semantics(host, root, suffix):
    parts = extract_domain(host)
    assert parts.top_domain_under_public_suffix == root
    assert parts.suffix == suffix
    assert root_domain(host) == (root or host)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("::ffff:8.8.8.8", IPv4Address("8.8.8.8")),
        ("::ffff:0.0.0.0", IPv4Address("0.0.0.0")),
        ("::ffff:192.168.1.1", IPv4Address("192.168.1.1")),
        ("2001:db8::1", IPv6Address("2001:db8::1")),
        ("fe80::1%eth0", IPv6Address("fe80::1%eth0")),
        (134744072, IPv4Address("8.8.8.8")),
        (b"\x08\x08\x08\x08", IPv4Address("8.8.8.8")),
    ],
)
def test_comparison_folds_only_mapped_addresses_without_eligibility_policy(value, expected):
    assert comparison_address(value) == expected


def test_capture_and_network_identity_import_without_intake_or_network():
    # A fresh process prevents pytest's application fixtures from hiding an
    # accidental transitive import. Lazy PSL initialization must also be offline.
    program = """
import socket
import sys
import requests

def blocked(*args, **kwargs):
    raise AssertionError("Offline domain extraction attempted network I/O")

socket.socket.connect = blocked
requests.sessions.Session.request = blocked
from modules.tools.components.network_identity import extract_domain
from modules.tools.components.website_capture.navigation import navigation_candidates
assert extract_domain("a.tenant.github.io").top_domain_under_public_suffix == "tenant.github.io"
assert ("https://tenant.github.io/", True) in list(navigation_candidates("https://a.tenant.github.io/"))
assert not any(name == "modules.accretion" or name.startswith("modules.accretion.") for name in sys.modules)
"""
    subprocess.run(
        [sys.executable, "-c", program],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
