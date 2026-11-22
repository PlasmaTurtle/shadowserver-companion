"""Source data survives admission while candidate boundaries reject invalid handoffs."""

from dataclasses import FrozenInstanceError, asdict
from ipaddress import ip_address

import pytest

from modules.accretion.components.intake import (
    CandidateGroup,
    CandidateObservation,
    SourceObservation,
    observation_payload,
    restore_observation,
)


def candidate(hostname="mail.example.com", ip="8.8.8.8", **metadata):
    source = SourceObservation("scan.csv", "CSV", 2, {"hostname": hostname, "ip": ip})
    return CandidateObservation(source, ip_address(ip).compressed, False, metadata)


def test_source_keeps_malformed_and_future_provider_values_detached():
    fields = {"hostname": None, "ip": "bad", "future_column": {"values": [0, False]}}
    source = SourceObservation("scan.csv", "", 0, fields)
    fields["future_column"]["values"].append("changed outside the observation")

    assert source.fields == {
        "hostname": None,
        "ip": "bad",
        "future_column": {"values": [0, False]},
    }
    with pytest.raises(FrozenInstanceError):
        source.row = 4
    with pytest.raises(ValueError):
        CandidateObservation(source, "bad", False)


@pytest.mark.parametrize("row", [-1, True, "2"])
def test_source_rejects_unusable_source_positions(row):
    with pytest.raises(ValueError, match="source row"):
        SourceObservation("scan.csv", "CSV", row, {})


def test_candidate_requires_canonical_ip_matching_the_original_source():
    source = SourceObservation("scan.csv", "CSV", 2, {"ip": "2001:0db8::1"})
    observation = CandidateObservation(source, "2001:db8::1", False)
    assert observation.source.fields["ip"] == "2001:0db8::1"
    with pytest.raises(ValueError, match="canonical and match"):
        CandidateObservation(source, "2001:db8::2", False)
    with pytest.raises(ValueError, match="canonical and match"):
        CandidateObservation(source, "2001:0db8::1", False)
    with pytest.raises(TypeError, match="boolean"):
        CandidateObservation(source, "2001:db8::1", 0)


def test_restore_preserves_saved_shape_and_detaches_nested_evidence():
    metadata = {"source_sha256": "a" * 64, "finding": {"kinds": ["cve"]}}
    observation = CandidateObservation(candidate().source, "8.8.8.8", False, metadata)
    metadata["finding"]["kinds"].append("outside change")
    payload = observation_payload(observation)
    restored = restore_observation(payload)
    assert asdict(restored) == payload
    assert set(payload) == {"source", "ip", "private_ip", "normalized"}
    payload["normalized"]["finding"]["kinds"].append("saved payload change")
    payload["source"]["fields"]["hostname"] = "changed.example.com"
    assert restored.normalized["finding"]["kinds"] == ["cve"]
    assert restored.source.fields["hostname"] == "mail.example.com"


def test_group_has_fixed_membership_and_rejects_raw_or_foreign_observations():
    observations = [candidate(), candidate("example.com", "8.8.4.4")]
    group = CandidateGroup("example.com", observations)
    observations.clear()
    assert len(group.observations) == 2
    with pytest.raises(FrozenInstanceError):
        group.root_domain = "other.com"
    with pytest.raises(ValueError, match="requires observations"):
        CandidateGroup("example.com", [])
    with pytest.raises(TypeError, match="only candidate observations"):
        CandidateGroup("example.com", [candidate().source])
    with pytest.raises(ValueError, match="different root domain"):
        CandidateGroup("example.com", [candidate("other.com")])
    with pytest.raises(ValueError, match="registrable root"):
        CandidateGroup("co.uk", [candidate()])
    with pytest.raises(ValueError, match="different root domain"):
        CandidateGroup("one.github.io", [candidate("two.github.io")])


def test_group_supports_reserved_demo_domains_without_filter_admission():
    group = CandidateGroup("example.test", [candidate("mail.example.test")])
    assert group.observations[0].source.fields["hostname"] == "mail.example.test"
    with pytest.raises(ValueError, match="different root domain"):
        CandidateGroup("example.test", [candidate("different.test")])
