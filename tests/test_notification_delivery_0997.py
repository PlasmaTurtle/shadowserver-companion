"""Notification evidence stays correctly scoped, readable, and byte-verified."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from test_report_pipeline_071 import SourceWorkspace, captured_snapshot
from workbench.appendix import Appendix
from workbench.appendix_layout import BOTTOM, layout_appendix
from workbench.appendix_view import (
    COMPACT_REVISION,
    LEGACY_COMPACT_REVISION,
    build_appendix_views,
)
from workbench.evidence_dossier import field_values, finding_groups
from workbench.evidence_reader import write_evidence_reader
from workbench.report_package import PackageRenderers, assemble_package


def observation(appendix, version, *, products=None):
    return appendix.add(
        "A",
        "observation",
        "Reported HTTP finding",
        {
            "ip": "192.0.2.5",
            "source": {
                "filename": "vulnerable-http.csv",
                "fields": {
                    "hostname": "mail.example.test",
                    "port": 443,
                    "protocol": "tcp",
                    "tag": "CVE-2099-10001",
                    "version": "HTTP/1.1",
                    "component_version": version,
                },
            },
            "normalized": {
                "raw_version": version,
                "products": products or [],
            },
        },
    )


def render_stub(data, path, root):
    path.write_bytes(b"synthetic rendered output")


def test_new_appendix_uses_intake_version_and_previous_revision_retains_its_copy():
    appendix = Appendix()
    entry = observation(appendix, "PHP/7.4.33")
    original = deepcopy(entry)
    model = appendix.model()
    new, _, _ = build_appendix_views(model, COMPACT_REVISION)
    old, _, _ = build_appendix_views(model, LEGACY_COMPACT_REVISION)

    def service(views):
        return next(
            field["text"]
            for field in views[0]["records"][0]["groups"][0]["fields"]
            if field["label"] == "Service"
        )

    assert "PHP/7.4.33" in service(new) and "HTTP/1.1" not in service(new)
    assert "HTTP/1.1" in service(old) and "PHP/7.4.33" not in service(old)
    assert new[0]["layout_revision"] == COMPACT_REVISION
    assert old[0]["layout_revision"] == LEGACY_COMPACT_REVISION
    assert entry == original


def test_dossier_keeps_component_versions_distinct_and_retains_each_product_pair(tmp_path):
    appendix = Appendix()
    first = observation(
        appendix,
        "PHP/7.4.33 Apache/2.4.6",
        products=[
            {"product": "PHP", "version": "7.4.33"},
            {"product": "Apache", "version": "2.4.6"},
        ],
    )
    observation(appendix, "PHP/8.0.1")
    observation(appendix, "PHP/8.0.1")
    model = appendix.model()
    groups = finding_groups(model["entries"])
    assert len(groups) == 2
    assert [len(group["entries"]) for group in groups] == [1, 2]
    values = field_values(first)
    assert values["Version"] == "PHP/7.4.33 Apache/2.4.6"
    assert values["Reported software"] == "PHP · 7.4.33; Apache · 2.4.6"
    write_evidence_reader({"composition": {"appendix": model}}, tmp_path)
    html = (tmp_path / "Evidence_Record.html").read_text()
    assert html.count('class="record finding"') == 2
    assert "PHP · 7.4.33; Apache · 2.4.6" in html
    assert "2 source observations" in html


def test_pinned_protocol_version_is_not_overridden_by_a_component_column():
    appendix = Appendix()
    entry = observation(appendix, "IKE/1")
    # Intake intentionally classified this version as protocol evidence.
    field = next(f for f in entry["fields"] if f["path"] == "/source/fields/component_version")
    field.update(value="unrelated banner", text="unrelated banner")
    assert field_values(entry)["Version"] == "IKE/1"


def test_short_cve_appendix_entry_stays_together_without_changing_legacy_pagination():
    appendix = Appendix()
    appendix.add(
        "A",
        "observation",
        "Reported service",
        {
            "hostname": "mail.example.test",
            "ip": "192.0.2.1",
            "port": 443,
            "tag": "\n".join(["Reported banner line"] * 26),
        },
    )
    cve = appendix.add(
        "C",
        "vulnerability_record",
        "CVE-2099-10001",
        {
            "id": "CVE-2099-10001",
            "verification_status": "Published",
            "kev": True,
            "epss": 0.8,
            "epss_date": "2026-11-12",
        },
    )
    result = {}
    for revision in (LEGACY_COMPACT_REVISION, COMPACT_REVISION):
        models, _, _ = build_appendix_views(appendix.model(), revision)
        pages = layout_appendix(models[0])
        result[revision] = [
            page.page
            for page in pages
            if any(segment.get("record_id") == cve["id"] for segment in page.segments)
        ]
        assert all(
            segment["top"] + segment["height"] <= BOTTOM
            for page in pages
            for segment in page.segments
            if segment.get("field_path")
        )
    assert result[LEGACY_COMPACT_REVISION] == [1, 2]
    assert result[COMPACT_REVISION] == [2]


@pytest.mark.parametrize("wrapped", [False, True])
def test_local_nvd_source_has_a_readable_summary_and_unchanged_original(tmp_path, wrapped):
    record = {
        "id": "CVE-2099-10001",
        "vulnStatus": "Analyzed",
        "published": "2026-11-12T12:00:00.000",
        "lastModified": "2026-11-13T12:00:00.000",
        "descriptions": [
            {"lang": "es", "value": "Descripción publicada"},
            {"lang": "en", "value": "Published description with <literal markup>."},
        ],
    }
    raw = json.dumps({"cve": record} if wrapped else record).encode()
    source = tmp_path / "captured-record.json"
    source.write_bytes(raw)
    write_evidence_reader({}, tmp_path)
    html = (tmp_path / "Evidence_Record.html").read_text()
    assert "<h3>CVE-2099-10001</h3>" in html
    assert "Published description with &lt;literal markup&gt;." in html
    assert "<th>Status</th><td>Analyzed</td>" in html
    assert source.read_bytes() == raw


def test_packaging_uses_verified_bytes_even_if_the_source_changes_after_read(tmp_path, monkeypatch):
    data, raw = captured_snapshot(tmp_path / "sources")
    data["draft"]["cve_records"][0]["sources"] = []
    data["source_snapshots"] = []
    source = tmp_path / "sources/source.json"
    original_read = Path.read_bytes
    original_open = Path.open
    read_count = 0

    class ReadThenChange:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size):
            nonlocal read_count
            content = self.stream.read(size)
            read_count += 1
            source.write_bytes(b'{"changed":"after verification read"}')
            return content

    def bounded_read_then_change(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return ReadThenChange(stream) if path == source and mode == "rb" else stream

    monkeypatch.setattr(Path, "open", bounded_read_then_change)
    destination = tmp_path / "package"
    destination.mkdir()
    built = assemble_package(
        SourceWorkspace(tmp_path / "sources"),
        data,
        destination,
        PackageRenderers(render_stub, render_stub),
    )
    record = built.snapshot["draft"]["cve_records"][0]
    assert read_count == 1
    packaged = original_read(destination / record["record_path"])
    assert packaged == raw
    assert hashlib.sha256(packaged).hexdigest() == record["body_sha256"]


def test_optional_contact_read_failure_is_recorded_without_blocking_package(tmp_path, monkeypatch):
    from test_contacts_invariants_090 import contact_result
    from workbench.contact_evidence import prepare_snapshot

    data, _ = captured_snapshot(tmp_path / "sources")
    result = contact_result()
    captured, _ = prepare_snapshot(result["snapshots"][0], result["candidates"])
    captured["path"] = "evidence/contact-discovery/run-one/missing.contact.json"
    data["contact_research"] = {
        "contacts": [],
        "runs": [{"id": "run-one", "snapshots": [captured]}],
    }

    def missing_after_check(*args):
        raise FileNotFoundError("Capture became unavailable")

    monkeypatch.setattr("workbench.contact_evidence.snapshot_content", missing_after_check)
    destination = tmp_path / "package"
    destination.mkdir()
    built = assemble_package(
        SourceWorkspace(tmp_path / "sources"),
        data,
        destination,
        PackageRenderers(render_stub, render_stub),
    )
    capture = built.snapshot["contact_research"]["runs"][0]["snapshots"][0]
    assert capture["package_availability"] == "unavailable"
    assert "Capture became unavailable" in capture["package_issue"]
    assert "notification.pdf" in built.files
    assert "package_availability" not in data["contact_research"]["runs"][0]["snapshots"][0]
