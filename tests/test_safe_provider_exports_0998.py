"""Previously retained provider bytes must pass content validation at export."""

from copy import deepcopy
import hashlib
import io
import json
from zipfile import ZipFile

import pytest

from test_report_pipeline_071 import SourceWorkspace, captured_snapshot
from workbench.report_package import PackageRenderers, _provider_capture, assemble_package


@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>INERT_UNTRUSTED_PROVIDER_RESPONSE</body></html>",
        b'{"message":"upstream unavailable"}',
        b'{"vulnerabilities":[],"vulnerabilities":[]}',
        '{"vulnerabilities":[]}'.encode("utf-16"),
    ],
)
def test_matching_hash_does_not_make_invalid_provider_bytes_exportable(tmp_path, body):
    path = tmp_path / "source.json"
    path.write_bytes(body)
    source = {
        "record_path": path.name,
        "sha256": hashlib.sha256(body).hexdigest(),
        "publisher": "NVD",
    }
    with pytest.raises(ValueError):
        _provider_capture(SourceWorkspace(tmp_path), source, cve_id="CVE-2099-10000")


def test_oversized_provider_file_is_rejected_before_read(tmp_path, monkeypatch):
    path = tmp_path / "source.json"
    with path.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    source = {"record_path": path.name, "publisher": "NVD"}
    with pytest.raises(ValueError, match="capture limit"):
        _provider_capture(SourceWorkspace(tmp_path), source, cve_id="CVE-2099-10000")


def test_invalid_primary_provider_response_cannot_reach_report_render(tmp_path):
    data, _ = captured_snapshot(tmp_path / "sources")
    body = b"<html>INERT_UNTRUSTED_PRIMARY_RESPONSE</html>"
    (tmp_path / "sources/source.json").write_bytes(body)
    data["draft"]["cve_records"][0]["body_sha256"] = hashlib.sha256(body).hexdigest()
    destination = tmp_path / "package"
    destination.mkdir()

    def forbidden_render(*args):
        pytest.fail("Invalid primary provider source reached rendering")

    with pytest.raises(ValueError):
        assemble_package(
            SourceWorkspace(tmp_path / "sources"),
            data,
            destination,
            PackageRenderers(forbidden_render, forbidden_render),
        )
    assert not list((destination / "evidence").iterdir())


def test_failed_supplementary_body_is_omitted_without_modifying_original(tmp_path, monkeypatch):
    from workbench import package_exhibits, report_package

    data, _ = captured_snapshot(tmp_path / "sources")
    body = b"<html>INERT_UNTRUSTED_SUPPLEMENTARY_RESPONSE</html>"
    (tmp_path / "sources/error.json").write_bytes(body)
    saved = {
        "record_path": "error.json",
        "sha256": hashlib.sha256(body).hexdigest(),
        "publisher": "CVE Program",
        "http_status": 503,
        "referenced_by": [data["draft"]["cve_records"][0]["id"]],
        "record": {"response_text": body.decode()},
    }
    data["source_snapshots"].append(saved)
    before = deepcopy(data)
    destination = tmp_path / "package"
    destination.mkdir()
    monkeypatch.setattr(package_exhibits, "export_gallery", lambda *a, **k: [])
    monkeypatch.setattr(report_package, "render_work_log", lambda *a, **k: None)
    monkeypatch.setattr(report_package, "write_evidence_reader", lambda *a, **k: None)

    def simple_render(snapshot, path, root):
        path.write_bytes(b"Synthetic document")

    built = assemble_package(
        SourceWorkspace(tmp_path / "sources"),
        data,
        destination,
        PackageRenderers(simple_render, simple_render),
    )
    omitted = built.snapshot["source_snapshots"][-1]
    assert omitted["availability"] == "omitted"
    assert "record_path" not in omitted and omitted["record"] is None
    assert omitted["sha256"] == saved["sha256"]
    assert data == before
    assert (tmp_path / "sources/error.json").read_bytes() == body
    assert all(body not in path.read_bytes() for path in destination.rglob("*") if path.is_file())


def _historical_provider_package(folder, body, *, embedded=False, standalone=True):
    from test_export_security_072 import make_package

    values = make_package(folder)
    snapshot = json.loads(values["snapshot.json"])
    source = {
        "publisher": "NVD",
        "sha256": hashlib.sha256(body).hexdigest(),
        "id": "CVE-2099-10000",
    }
    if standalone:
        source["record_path"] = "evidence/provider.json"
        values[source["record_path"]] = body
        (folder / source["record_path"]).write_bytes(body)
    if embedded:
        source["record"] = {"response_text": body.decode()}
    snapshot["source_snapshots"] = [source]
    values["snapshot.json"] = json.dumps(snapshot).encode()
    (folder / "snapshot.json").write_bytes(values["snapshot.json"])
    manifest = {
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in values.items()}
    }
    raw = json.dumps(manifest).encode()
    (folder / "manifest.json").write_bytes(raw)
    return values, manifest, raw


def test_historical_internal_export_omits_invalid_provider_body_and_preserves_certification(
    tmp_path,
):
    from workbench.package_integrity import write_export

    folder = tmp_path / "certified"
    body = b"<html>INERT_HISTORICAL_PROVIDER_ERROR</html>"
    originals, manifest, raw = _historical_provider_package(folder, body)
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        write_export(archive, folder, manifest, raw)
    with ZipFile(stream) as archive:
        assert "evidence/provider.json" not in archive.namelist()
        assert archive.read("snapshot.json") == originals["snapshot.json"]
        assert archive.read("certified-manifest.json") == raw
        transport = json.loads(archive.read("export-manifest.json"))
        assert (
            transport["omitted_files"]["evidence/provider.json"]["sha256"]
            == hashlib.sha256(body).hexdigest()
        )
        assert all(body not in archive.read(name) for name in archive.namelist())
        for name, digest in transport["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    assert all((folder / name).read_bytes() == content for name, content in originals.items())
    assert (folder / "manifest.json").read_bytes() == raw


def test_historical_valid_provider_capture_is_delivered_unchanged(tmp_path):
    from workbench.package_integrity import write_export

    body = b'{"vulnerabilities":[{"cve":{"id":"CVE-2099-10000","descriptions":[{"lang":"en","value":"Synthetic test"}]}}]}'
    folder = tmp_path / "certified"
    _, manifest, raw = _historical_provider_package(folder, body)
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        write_export(archive, folder, manifest, raw)
    with ZipFile(stream) as archive:
        assert archive.read("evidence/provider.json") == body
        assert archive.read("manifest.json") == raw
        assert "export-manifest.json" not in archive.namelist()


@pytest.mark.parametrize("standalone", [False, True])
def test_embedded_legacy_web_content_blocks_internal_export_but_recipient_remains_available(
    tmp_path, standalone
):
    from workbench.package_integrity import (
        LegacyUnvalidatedEvidence,
        write_export,
        write_recipient_export,
    )

    folder = tmp_path / "certified"
    body = b"<html>INERT_EMBEDDED_PROVIDER_ERROR</html>"
    originals, manifest, raw = _historical_provider_package(
        folder, body, embedded=True, standalone=standalone
    )
    with (
        ZipFile(io.BytesIO(), "w") as archive,
        pytest.raises(LegacyUnvalidatedEvidence, match="Recipient documents remain available"),
    ):
        write_export(archive, folder, manifest, raw)
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        write_recipient_export(archive, folder, manifest, raw)
    with ZipFile(stream) as archive:
        assert archive.read("notification.pdf") == originals["notification.pdf"]
        assert set(archive.namelist()) == {"notification.pdf", "recipient-manifest.json"}
    assert all((folder / name).read_bytes() == content for name, content in originals.items())
