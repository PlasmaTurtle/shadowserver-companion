"""Dossier hierarchy must retain source scope and use only saved evidence edges."""

from copy import deepcopy
import json

from workbench.appendix import Appendix
from workbench.evidence_dossier import finding_groups, readable_time
from workbench.evidence_reader import write_evidence_reader
from test_compact_evidence_098 import ReaderLinks


def connected_records():
    appendix = Appendix()
    first = appendix.add(
        "A",
        "observation",
        "Observed service",
        {
            "hostname": "mail.example.test",
            "ip": "192.0.2.1",
            "tag": "CVE-2099-10001",
            "port": 443,
            "protocol": "tcp",
            "timestamp": "2026-11-10T12:00:00Z",
            "source": {"filename": "first.csv", "row": 2},
        },
    )
    second = appendix.add(
        "A",
        "observation",
        "Observed service again",
        {
            "hostname": "mail.example.test",
            "ip": "192.0.2.1",
            "tag": "CVE-2099-10001",
            "port": 443,
            "protocol": "tcp",
            "timestamp": "2026-11-11T12:00:00Z",
            "source": {"filename": "second.csv", "row": 4},
        },
    )
    attribution = appendix.add(
        "B",
        "accepted_attribution",
        "Saved registration",
        {
            "ip": "192.0.2.1",
            "source": "Registry",
            "decision": "accepted",
        },
        referenced_by=[first["id"]],
    )
    unrelated = appendix.add(
        "B",
        "attribution_history",
        "Unrelated lookup",
        {
            "ip": "192.0.2.1",
            "source": "Different source",
        },
    )
    vulnerability = appendix.add(
        "C",
        "vulnerability_record",
        "CVE-2099-10001",
        {
            "id": "CVE-2099-10001",
            "verification_status": "published",
        },
        referenced_by=[first["id"], second["id"]],
        citations=[1],
    )
    reference = appendix.add(
        "D",
        "reference",
        "[1] Published source",
        {
            "number": 1,
            "url": "https://example.test/advisory",
            "publisher": "Example",
        },
        citations=[1],
    )
    return appendix.model(), first, second, attribution, unrelated, vulnerability, reference


def test_grouped_findings_keep_all_observations_and_only_explicit_connections():
    model, first, second, attribution, unrelated, vulnerability, reference = connected_records()
    original = deepcopy(model)
    groups = finding_groups(model["entries"])
    assert len(groups) == 1
    assert [entry["id"] for entry in groups[0]["entries"]] == [first["id"], second["id"]]
    connections = {entry["id"] for entry in groups[0]["connections"]}
    assert connections == {attribution["id"], vulnerability["id"], reference["id"]}
    assert unrelated["id"] not in connections  # Same IP is not itself a provenance edge.
    assert model == original


def test_distinct_service_or_unknown_asset_identity_is_not_collapsed():
    appendix = Appendix()
    for port in (443, 8443):
        appendix.add("A", "observation", "Service", {"ip": "192.0.2.1", "port": port, "tag": "tls"})
    for _ in range(2):
        appendix.add("A", "observation", "Unknown asset", {"tag": "tls"})
    assert len(finding_groups(appendix.model()["entries"])) == 4


def test_dossier_uses_compact_references_and_preserves_every_original_anchor(tmp_path):
    model, *entries = connected_records()
    data = {"entity_name": "Example", "domain": "example.test", "composition": {"appendix": model}}
    original = deepcopy(data)
    (tmp_path / "notification.pdf").write_bytes(b"Synthetic report")
    (tmp_path / "snapshot.json").write_text(json.dumps(data))
    write_evidence_reader(data, tmp_path)
    html = (tmp_path / "Evidence_Record.html").read_text()
    parsed = ReaderLinks()
    parsed.feed(html)
    assert html.count('class="record finding"') == 1
    assert html.count('class="record bibliography-item"') == 1
    assert 'class="technical observation-batch"' in html
    assert "2 source observations" in html and "2 source files" in html
    assert "Linked evidence" in html
    assert 'data-group="records-a"' in html
    assert all(entry["id"] in parsed.ids for entry in entries)
    assert len(parsed.ids) == len(set(parsed.ids))
    assert all(href[1:] in parsed.ids for href in parsed.links if href.startswith("#"))
    assert data == original
    assert json.loads((tmp_path / "evidence/appendix-records.json").read_text()) == model


def test_timestamp_display_preserves_instant_and_does_not_guess_missing_zone():
    assert readable_time("2026-11-10T07:00:00-05:00") == "10 Nov 2026 · 12:00:00 UTC"
    assert readable_time("2026-11-10T12:00:00") == "2026-11-10T12:00:00"
    assert readable_time("unknown") == "unknown"


def test_supporting_sources_share_compact_bibliography_with_citations_first(tmp_path):
    appendix = Appendix()
    support = appendix.add(
        "D",
        "supporting_material",
        "Supporting guide",
        {
            "publisher": "Example",
            "url": "https://example.test/guide",
            "description": "Retained source context",
        },
    )
    reference = appendix.add(
        "D",
        "reference",
        "[1] Cited source",
        {"number": 1, "publisher": "Example", "url": "https://example.test/citation"},
        citations=[1],
    )
    data = {"entity_name": "Example", "composition": {"appendix": appendix.model()}}
    (tmp_path / "notification.pdf").write_bytes(b"Synthetic report")
    (tmp_path / "snapshot.json").write_text(json.dumps(data))
    write_evidence_reader(data, tmp_path)
    html = (tmp_path / "Evidence_Record.html").read_text()
    assert html.count('class="record bibliography-item"') == 2
    assert html.index('id="' + reference["id"] + '"') < html.index('id="' + support["id"] + '"')
    assert "Retained source context" in html
