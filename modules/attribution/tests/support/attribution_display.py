"""Reusable synthetic attribution display fixtures and builders."""

from dataclasses import asdict, replace
from types import SimpleNamespace

from attribution import EvidenceStore
from attribution.models import (
    AttributionEvidence,
    AttributionResult,
    CandidateIP,
    DomainMatch,
    ResponseSnapshot,
    json_bytes,
)

from modules.attribution.components.attribution_bridge import attribution_record

RETRIEVED = "2026-11-01T09:00:00Z"


EVALUATED = "2026-11-05T14:30:00Z"


def saved_record(tmp_path, *, method="rdap", review=None, basis=None):
    store = SimpleNamespace(root=tmp_path)
    raw = {
        "startAddress": "8.8.8.0",
        "endAddress": "8.8.8.255",
        "contact": "security@example.com",
        "unknown_extension": {"preserved": True},
    }
    url = "https://rdap.arin.net/registry/ip/8.8.8.8"
    name = "ARIN"
    match = DomainMatch("example.com", "example.com", "/contact", "security@example.com")
    details = {"network_start": "8.8.8.0", "network_end": "8.8.8.255"}
    if method == "dns":
        raw = {"answers": ["8.8.8.8"], "query": "mail.example.com", "type": "A"}
        url, name = "dns://system/mail.example.com/A", "Workstation DNS resolver"
        match = DomainMatch(
            "example.com", "mail.example.com", "/answers", "8.8.8.8", field_type="dns_address"
        )
        details = {
            "dns_forward_match": True,
            "basis": basis or "forward",
            "resolved_hostname": "mail.example.com",
            "reported_hostname": "remote.example.com",
        }
    elif method == "rdap_keyword":
        match = DomainMatch(
            "example.com", "", "/name", "Example Organization", field_type="organization_name"
        )
        details["matched_words"] = ["example"]
    snapshot = replace(
        ResponseSnapshot.create(url, url, 200, {}, json_bytes(raw)), retrieved_at=RETRIEVED
    )
    evidence = AttributionEvidence(
        method,
        "8.8.8.8",
        name,
        url,
        RETRIEVED,
        snapshot.snapshot_id,
        (snapshot.snapshot_id,),
        match,
        details,
        True,
    )
    partial = method == "rdap_keyword"
    result = AttributionResult(
        "saved-result",
        "example.com",
        "review" if partial else "matched",
        EVALUATED,
        (CandidateIP("0", "8.8.8.8", "remote.example.com"),),
        None if partial else "0",
        None if partial else "8.8.8.8",
        () if partial else (evidence,),
        (),
        {"version": "test-policy"},
        {},
        partial_evidence=(evidence,) if partial else (),
    )
    with EvidenceStore(tmp_path / "attribution.sqlite3") as database:
        database.save_snapshot(snapshot)
        database.save_result(result)
        record = attribution_record(
            database,
            result.result_id,
            result.root_domain,
            result.policy,
            asdict(evidence),
            review=review,
        )
    return store, record


def entry(row_id, ip, hostname="remote.example.com"):
    return {
        "id": row_id,
        "ip": ip,
        "private_ip": ip.startswith("10."),
        "source": {
            "workbook": "source.csv",
            "sheet": "CSV",
            "row": 2,
            "fields": {
                "hostname": hostname,
                "ip": ip,
                "tag": "eol-php",
                "version": "7.3.25",
                "unknown_column": "kept",
            },
        },
    }


def case_lead(record, entries=None):
    return {
        "id": "entity-one",
        "case_id": "case-one",
        "domain_groups": [
            {"root_domain": "example.com", "attribution_entry_id": "support", "attribution": record}
        ],
        "entries": entries or [entry("support", "8.8.8.8"), entry("other", "1.1.1.1")],
        "attribution": {"ip": "9.9.9.9", "registry": "NEW ENTITY RECORD - MUST NOT LEAK"},
        "hostnames": [{"name": "remote.example.com", "root_domain": "example.com"}],
    }
