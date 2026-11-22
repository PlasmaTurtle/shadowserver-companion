"""Report/package ownership contracts for the stabilization release."""

from copy import deepcopy
import hashlib
import json
from modules.workspace.components import compact_json

import pytest

from modules.investigations.components import reporting
from modules.investigations.components.report_package import PackageRenderers, assemble_package

from modules.investigations.tests.support.report_artifacts import (
    SourceWorkspace,
    captured_snapshot,
)


def test_package_owns_paths_but_preserves_raw_evidence_and_caller_snapshot(tmp_path):
    data, raw = captured_snapshot(tmp_path / "sources")
    before = deepcopy(data)
    destination = tmp_path / "package"
    destination.mkdir()
    built = assemble_package(
        SourceWorkspace(tmp_path / "sources"),
        data,
        destination,
        PackageRenderers(reporting.render_pdf, reporting.render_docx),
    )
    assert data == before
    packaged = built.snapshot
    assert packaged is not data
    assert packaged["draft"]["cve_records"][0]["record_path"] != "source.json"
    assert packaged["draft"]["cve_records"][0]["original_record_path"] == "source.json"
    assert (destination / packaged["draft"]["cve_records"][0]["record_path"]).read_bytes() == raw
    assert (destination / packaged["source_snapshots"][0]["record_path"]).read_bytes() == raw
    assert packaged["source_snapshots"][0]["record"]["unknown_extension"] == {
        "values": [None, False, 0]
    }
    assert (
        compact_json.loads((destination / "snapshot.json").read_text(encoding="utf-8")) == packaged
    )
    assert (
        json.loads((destination / "snapshot.json").read_text(encoding="utf-8"))["storage_format"]
        == compact_json.FORMAT
    )
    assert not any("-standalone." in name for name in built.files)
    assert all(
        artifact["format"] == "shared-gallery-v1" and artifact["gallery"] in built.files
        for artifact in packaged["exhibit_artifacts"]
    )
    for relative, digest in built.files.items():
        assert hashlib.sha256((destination / relative).read_bytes()).hexdigest() == digest
    assert {
        "notification.pdf",
        "notification.docx",
        "snapshot.json",
        "chronology.json",
        "work-log.pdf",
    } <= built.files.keys()
    # Later package edits cannot reach backwards into the draft or pinned sources.
    packaged["source_snapshots"][0]["record"]["unknown_extension"]["values"].append("package only")
    assert data == before


def test_failed_render_leaves_source_snapshot_and_captured_bytes_unchanged(tmp_path):
    data, raw = captured_snapshot(tmp_path / "sources")
    before = deepcopy(data)
    destination = tmp_path / "failed-package"
    destination.mkdir()

    def failed_render(snapshot, path, evidence_root):
        snapshot["draft"]["cve_records"][0]["description"] = "renderer-local mutation"
        raise RuntimeError("Synthetic render failure")

    with pytest.raises(RuntimeError, match="Synthetic render failure"):
        assemble_package(
            SourceWorkspace(tmp_path / "sources"),
            data,
            destination,
            PackageRenderers(failed_render, reporting.render_docx),
        )
    assert data == before
    assert (tmp_path / "sources/source.json").read_bytes() == raw


def test_corrupt_capture_is_rejected_before_rendering_without_mutating_snapshot(tmp_path):
    data, raw = captured_snapshot(tmp_path / "sources")
    before = deepcopy(data)
    (tmp_path / "sources/source.json").write_bytes(raw + b"changed")
    destination = tmp_path / "failed-package"
    destination.mkdir()

    def unexpected_render(*args):
        pytest.fail("Corrupt evidence reached the renderer")

    with pytest.raises(ValueError, match="integrity check"):
        assemble_package(
            SourceWorkspace(tmp_path / "sources"),
            data,
            destination,
            PackageRenderers(unexpected_render, unexpected_render),
        )
    assert data == before


def test_public_finalization_uses_public_preview_dependencies(monkeypatch):
    """Preview and certification continue to share replaceable public entry points."""
    calls = {}

    def fake_certify(store, lead_id, case_id, *, build_snapshot, renderers):
        calls.update(
            store=store,
            lead_id=lead_id,
            case_id=case_id,
            snapshot=build_snapshot,
            pdf=renderers.pdf,
            docx=renderers.docx,
        )
        return {"id": "report-fixture"}

    def replacement(*args):
        return None

    monkeypatch.setattr(reporting, "certify_report", fake_certify)
    monkeypatch.setattr(reporting, "render_pdf", replacement)
    assert reporting.finalize("workspace", "entity", "case") == {"id": "report-fixture"}
    assert calls == {
        "store": "workspace",
        "lead_id": "entity",
        "case_id": "case",
        "snapshot": reporting.snapshot,
        "pdf": replacement,
        "docx": reporting.render_docx,
    }
