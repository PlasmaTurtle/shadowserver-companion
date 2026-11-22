"""Reusable synthetic attribution exhibit fixtures and builders."""

from modules.investigations.components.attribution_model import build_attribution_exhibit


def inputs(method="rdap", *, count=2):
    entries = [
        {
            "id": "entry-" + str(n),
            "ip": "192.0.2." + str(n + 14),
            "source": {"fields": {"hostname": "remote.example.com"}},
        }
        for n in range(count)
    ]
    record = {
        "startAddress": "192.0.2.0",
        "endAddress": "192.0.2.255",
        "email": "security@example.com",
        "name": "Example Organization",
        "extension": {"source": "retain this"},
    }
    match = {
        "target_domain": "example.com",
        "matched_domain": "example.com",
        "field_path": "/email",
        "value": "security@example.com",
    }
    details = {"network_start": "192.0.2.0", "network_end": "192.0.2.255"}
    if method == "dns":
        record = {"query": "remote.example.com", "type": "A", "answers": ["192.0.2.14"]}
        match.update(matched_domain="remote.example.com", field_path="/answers", value="192.0.2.14")
        details = {
            "resolved_hostname": "remote.example.com",
            "dns_forward_match": True,
            "basis": "forward",
        }
    if method == "rdap_keyword":
        match.update(matched_domain="", field_path="/name", value="Example Organization")
        details["matched_words"] = ["example"]
    evidence = {
        "ip": "192.0.2.14",
        "method": method,
        "source_name": "Synthetic resolver" if method == "dns" else "Synthetic registry",
        "source_url": "dns://system/remote.example.com/A"
        if method == "dns"
        else "https://sources.example/record",
        "retrieved_at": "2026-11-01T09:00:00Z",
        "from_cache": True,
        "match": match,
        "details": details,
    }
    proof = {
        "ip": "192.0.2.14",
        "evidence": evidence,
        "record": record,
        "evaluated_at": "2026-11-07T14:00:00Z",
        "registry": evidence["source_name"],
        "source_url": evidence["source_url"],
        "retrieved_at": evidence["retrieved_at"],
    }
    data = {
        "draft": {"company": "Example Company", "address": "100 Example Way", "sos_verified": True},
        "qualified_lead": {"validated_leads": [{"hostname": "example.com", "entries": entries}]},
    }
    model = {
        "id": "EX-ATTRIBUTION",
        "type": "attribution",
        "report_revision": 3,
        "items": [
            {
                "label": "example.com",
                "appendix_entry_ids": ["B-1", "A-1"],
                "observation_ids": ["entry-0"],
            }
        ],
        "appendix_entry_ids": ["B-1"],
        "source_citations": [4],
    }
    groups = [{"hostname": "example.com", "source": proof, "citation": 4}]
    return data, model, groups


def build(parts):
    return build_attribution_exhibit(*parts)


def google_dns_inputs():
    from attribution.google_dns import query_url

    parts = inputs("dns")
    proof = parts[2][0]["source"]
    proof["record"] = {
        "Status": 0,
        "TC": False,
        "RD": True,
        "RA": True,
        "AD": False,
        "CD": False,
        "Question": [{"name": "remote.example.com.", "type": 1}],
        "Answer": [
            {"name": "remote.example.com.", "type": 5, "TTL": 60, "data": "edge.provider.test."},
            {"name": "unrelated.test.", "type": 1, "TTL": 60, "data": "192.0.2.200"},
            {"name": "edge.provider.test.", "type": 1, "TTL": 60, "data": "192.0.2.14"},
        ],
    }
    proof["evidence"]["match"].update(field_path="/Answer/2/data", value="192.0.2.14")
    proof["evidence"]["details"].update(record_type="A", resolver_kind="public recursive resolver")
    proof["registry"] = proof["evidence"]["source_name"] = "Google Public DNS"
    proof["source_url"] = proof["evidence"]["source_url"] = query_url("remote.example.com.", "A")
    proof["body_sha256"] = "1" * 64
    return parts
