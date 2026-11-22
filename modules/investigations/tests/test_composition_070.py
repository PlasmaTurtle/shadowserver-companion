"""Lossless recipient appendix and case-scoped exhibit acceptance checks."""

from copy import deepcopy
import json

from modules.investigations.components.appendix import Appendix, flatten_fields
from modules.investigations.components.report_composition import compose
from modules.investigations.tests.support.report_artifacts import specimen


def rich_specimen():
    data = specimen(1)
    entries = []
    for index in range(336):
        ip_index = index % 84
        ip = "192.0.2." + str((ip_index % 70) + 1)
        port = 8443 if ip_index >= 70 else 443
        fields = {
            "hostname": "mail.example.com",
            "ip": ip,
            "protocol": "tcp",
            "port": port,
            "tag": "CVE-2099-10000;eol-php",
            "version": "PHP/7.3.25 Apache/2.4.6",
            "timestamp": "2026-11-05T12:00:00Z",
            "unknown/field": 0,
            "enabled": False,
            "nullable": None,
            "empty": "",
            "nested": {"名字": ["first", "", None, False, 0]},
        }
        entries.append(
            {
                "id": "obs-" + str(index),
                "ip": ip,
                "private_ip": False,
                "source": {
                    "workbook": "synthetic.xlsx",
                    "sheet": "Rows",
                    "row": index + 2,
                    "fields": fields,
                },
                "normalized": {
                    "products": [
                        {"product": "PHP", "version": "7.3.25"},
                        {"product": "Apache", "version": "2.4.6"},
                    ]
                },
            }
        )
    data["qualified_lead"]["validated_leads"][0]["entries"] = entries
    proof = data["qualified_lead"]["whois"][0]
    proof.update(
        evaluated_at="2026-11-06T13:00:00Z",
        record={"startAddress": "192.0.2.0", "endAddress": "192.0.2.255"},
    )
    data["attribution_history"] = [
        {
            "status": "candidate",
            "retrieved_at": "2026-11-05T13:00:00Z",
            "matched_words": ["example"],
        },
        {"status": "failed", "attempted_at": "2026-11-05T12:30:00Z", "error": "No PTR record"},
    ]
    return data


def test_336_rows_70_ips_84_endpoints_full_fidelity_after_signature():
    data = rich_specimen()
    original = deepcopy(data)
    model = compose(data)
    assert data == original
    summary = next(e for e in model["exhibits"] if e["type"] == "summary")
    assert {i["label"]: i["value"] for i in summary["counts"]} == {
        "Unique reported IPs": 70,
        "Service endpoints": 84,
        "Source observations": 336,
        "Distinct reported CVEs": 1,
    }
    observations = [e for e in model["appendix"]["entries"] if e["kind"] == "observation"]
    assert len(observations) == 336
    assert len({e["id"] for e in observations}) == 336
    fields = {f["path"]: f for f in observations[0]["fields"]}
    assert fields["/source/fields/unknown~1field"]["value"] == 0
    assert fields["/source/fields/enabled"]["value"] is False
    assert fields["/source/fields/nullable"]["value"] is None
    assert fields["/source/fields/empty"]["value"] == ""
    assert fields["/source/fields/nested/名字/3"]["value"] is False
    assert {g["label"] for g in summary["groups"]} == {"PHP 7.3.25", "Apache 2.4.6"}
    assert all(
        len(g["observation_ids"]) + len(g["appendix_entry_ids"]) == g["value"] * 2
        for g in summary["groups"]
    )
    nodes = model["sections"]
    signature = next(i for i, n in enumerate(nodes) if n.get("style") == "signature")
    assert nodes[signature + 1]["kind"] == "page_break"
    assert nodes[signature + 2]["text"] == "Companion Appendix"
    assert all(
        n.get("section_owner")
        in {"introduction", "vulnerabilities", "attribution", "information", "closing"}
        for n in nodes
    )


def test_accepted_network_relation_preserves_distinct_times_and_history():
    model = compose(rich_specimen())
    attribution = next(e for e in model["exhibits"] if e["type"] == "attribution")
    assert attribution["counts"][0]["value"] == 70
    assert attribution["counts"][1]["value"] == 1
    item = attribution["items"][0]
    assert item["covering_network"] == "192.0.2.0 – 192.0.2.255"
    assert item["evidence_ip"] is None
    assert item["decision_at"] == "2026-11-06T13:00:00Z"
    assert item["retrieved_at"] == "2026-11-06T12:00:00Z"
    assert item["decision_by"] == "Attribution Module"
    history = [e for e in model["appendix"]["entries"] if e["kind"] == "attribution_history"]
    assert {e["status"] for e in history} == {"candidate", "failed"}
    assert all(e["owner"] == "attribution" for e in history)


def test_shared_source_deduplicated_but_all_references_remain():
    appendix = Appendix()
    source = {
        "id": "immutable-1",
        "sha256": "a" * 64,
        "publisher": "Fixture",
        "retrieved_at": "2026-11-06T12:00:00Z",
        "record": {"value": "retained"},
    }
    first = appendix.add_source({**source, "referenced_by": ["A-1"]}, referenced_by=["A-1"])
    second = appendix.add_source({**source, "referenced_by": ["A-2"]}, referenced_by=["A-2"])
    assert first["id"] == second["id"]
    model = appendix.model()
    assert len(model["entries"]) == 1
    assert model["entries"][0]["referenced_by"] == ["A-1", "A-2"]
    assert model["sources"][0]["referenced_by"] == ["A-1", "A-2"]
    different_revision = {**source, "id": "immutable-2", "retrieved_at": "2026-11-07T12:00:00Z"}
    appendix.add_source(different_revision)
    assert len(appendix.model()["entries"]) == 2


def test_supplied_empty_containers_and_inert_source_content():
    value = {
        "object": {},
        "array": [],
        "string": "",
        "zero": 0,
        "false": False,
        "null": None,
        "script": '<script>fetch("https://evil.example")</script>',
        "long": "X" * 10000,
    }
    fields = list(flatten_fields(value))
    assert len(fields) == len(value)
    assert {i["path"]: i["value"] for i in fields} == {"/" + k: v for k, v in value.items()}
    data = specimen()
    data["source_snapshots"] = [{"id": "case-source", "provider": "NVD", "record": value}]
    data["internal_contact_attempts"] = [{"secret_note": "MUST NOT EXPORT"}]
    result = compose(data)
    serialized = json.dumps(result, ensure_ascii=False)
    assert "MUST NOT EXPORT" not in serialized
    assert "X" * 10000 in serialized
    assert "<script>" in serialized  # stored as inert data; rendering escapes it


def test_revision_counter_and_irrelevant_app_state_do_not_change_models():
    data = specimen()
    first = compose(data)
    data.update(draft_revision=999, created_at="2030-01-01", ui_filter="hidden")
    second = compose(data)
    assert first == second


def test_reserved_and_rejected_cannot_use_manual_fallback():
    data = specimen()
    cve = data["cves"][0]
    data["draft"]["cve_dispositions"][cve] = {
        "action": "fallback",
        "reason": "test",
        "description": "test",
        "publisher": "Vendor",
        "source_url": "https://example.com/advisory",
        "retrieved_at": "2026-11-06",
        "evidence_text": "test",
    }
    for state in ("reserved", "rejected"):
        data["draft"]["cve_records"][0]["verification_status"] = state
        model = compose(data)
        item = next(e for e in model["exhibits"] if e["type"] == "vulnerability")["items"][0]
        assert item["verification_status"] == state
        assert (
            "unavailable" in item["description_excerpt"].lower()
            or "unresolved" in item["description_excerpt"].lower()
        )


def test_import_provenance_links_selected_observations_without_workstation_settings():
    from modules.investigations.components.source_capture import capture_sources

    import_data = {
        "id": "import-1",
        "name": "original.xlsx",
        "sha256": "a" * 64,
        "fingerprint": "b" * 64,
        "created_at": "2026-11-05T14:00:00Z",
        "config": json.dumps(
            {
                "critical_only": True,
                "report_type": "scan_http_vulnerable",
                "profile_inventory": {"commit": "pinned-fixture"},
                "analyst_name": "PRIVATE SETTING",
                "email": "private@example.com",
                "targeted_reason": "INTERNAL RESEARCH REASON",
                "api_key": "SECRET",
            }
        ),
    }

    class StoreFixture:
        def all(self, query, parameters):
            assert "ce.case_id=?" in query and parameters == ("case-1",)
            return [{**import_data, "entry_id": "obs-0"}, {**import_data, "entry_id": "obs-1"}]

    data = rich_specimen()
    data["case_id"] = "case-1"
    # No source body path or live attribution result is needed for this test.
    capture_sources(StoreFixture(), data)
    assert len(data["import_sources"]) == 1
    imported = data["import_sources"][0]
    assert imported["sha256"] == "a" * 64
    assert imported["imported_at"] == "2026-11-05T14:00:00Z"
    assert imported["parsing_policy"]["critical_only"] is True
    assert imported["referenced_by"] == ["obs-0", "obs-1"]
    model = compose(data)
    provenance = [e for e in model["appendix"]["entries"] if e["kind"] == "import_provenance"]
    assert len(provenance) == 1
    row_entries = [e for e in model["appendix"]["entries"] if e["kind"] == "observation"]
    assert sum(provenance[0]["id"] in e["source_ids"] for e in row_entries) == 2
    exported = json.dumps(model)
    assert all(
        value not in exported
        for value in (
            "PRIVATE SETTING",
            "private@example.com",
            "SECRET",
            "INTERNAL RESEARCH REASON",
        )
    )
