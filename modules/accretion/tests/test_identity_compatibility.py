"""Shared live network helpers must not rename persisted ingestion identities."""

from attribution.matching import normalize_domain
from modules.accretion.components.awareness_identity import address, asset_key, hostname
from modules.accretion.components.intake.identity import signature
from modules.accretion.components.intake import registry_address
from modules.tools.components.network_identity import comparison_address


def test_legacy_awareness_idna_and_address_family_are_deliberate_saved_key_contracts():
    entry = {
        "ip": "::ffff:8.8.8.8",
        "source": {"fields": {"hostname": "faß.de..", "ip": "::ffff:8.8.8.8"}},
    }
    key, name, saved_ip = asset_key(entry)
    assert key == "hostname:fass.de" and name == "fass.de"
    assert hostname("βόλος.gr") == "xn--nxasmq6b.gr"
    assert normalize_domain("faß.de") == "xn--fa-hia.de"
    assert saved_ip == address("::ffff:8.8.8.8") and saved_ip.startswith("::ffff:")
    assert hostname("127.0.0.1") == "127.0.0.1"
    assert address("fe80::1%eth0") == "fe80::1%eth0"
    # The retained CLI/intake API now delegates to the shared comparison contract.
    assert registry_address is comparison_address
    assert str(registry_address(entry["ip"])) == "8.8.8.8"


def test_existing_finding_signature_does_not_change_with_live_dns_identity():
    entry = {
        "ip": "8.8.8.8",
        "source": {
            "fields": {
                "hostname": "EXAMPLE.ORG.",
                "ip": "8.8.8.8",
                "protocol": "tcp",
                "port": "0443",
                "tag": "CVE-2025-1234",
                "version": "1.0",
            }
        },
    }
    assert asset_key(entry) == ("hostname:example.org", "example.org", "8.8.8.8")
    assert signature(entry) == "6ad951806a1b9a41df2535faf341578834017d4f68bf39c31c9c3838806f02d9"
