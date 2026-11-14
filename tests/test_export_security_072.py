"""Evidence originals and manifest-only exports preserve bytes without active suffixes."""

import hashlib
import io
import json
from workbench import compact_json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from PIL import Image

from test_workbench import app, client, import_rows, ready, attach
from workbench.image_evidence import decode_screenshot
from workbench.package_integrity import validated_inventory, write_export, package_folder


def png_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (3, 2), "white").save(stream, "PNG")
    return stream.getvalue()


@pytest.mark.parametrize(
    "name", ["capture.html", "capture.svg", "capture.exe", "capture", "capture.png.html"]
)
def test_decodable_image_cannot_adopt_active_or_unknown_extension(name):
    with pytest.raises(ValueError, match="filename"):
        decode_screenshot(name, png_bytes() + b"\nSYNTHETIC_APPENDIX_MARKER")


def test_extension_and_decoded_image_format_must_agree():
    with pytest.raises(ValueError, match="does not match"):
        decode_screenshot("capture.jpg", png_bytes())


def test_screenshot_original_is_neutral_and_preserved_in_certified_package(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    original = png_bytes() + b"\nSYNTHETIC_CAPTURE_TRAILING_BYTES"
    rejected = client.post(
        f"/api/leads/{lead_id}/evidence",
        files={"file": ("capture.html", original, "image/png")},
    )
    assert rejected.status_code == 400
    accepted = client.post(
        f"/api/leads/{lead_id}/evidence",
        files={"file": ("capture.png", original, "image/png")},
    )
    assert accepted.status_code == 200, accepted.text
    item = accepted.json()["evidence"][0]
    assert item["filename"] == "capture.png"
    assert item["path"].endswith(".original.bin")
    assert app.state.store.path(item["path"]).read_bytes() == original
    assert item["sha256"] == hashlib.sha256(original).hexdigest()
    preview = client.get(f"/api/evidence/{item['id']}/image")
    assert preview.headers["content-type"] == "image/png"
    assert b"SYNTHETIC_CAPTURE_TRAILING_BYTES" not in preview.content
    ready(client, lead_id)
    result = client.post(f"/api/leads/{lead_id}/finalize")
    assert result.status_code == 200, result.text
    response = client.get(f"/api/reports/{result.json()['id']}/zip")
    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        snapshot = compact_json.loads(archive.read("snapshot.json"))
        stored = next(e for e in snapshot["evidence"] if e["id"] == item["id"])
        assert stored["source_metadata"]["decoded_format"] == "PNG"
        assert stored["source_metadata"]["media_type"] == "image/png"
        assert stored["source_metadata"]["original_filename"] == "capture.png"
        assert archive.read(stored["path"]) == original
        assert stored["path"].endswith(".original.bin")
        manifest = json.loads(archive.read("manifest.json"))
        assert set(archive.namelist()) == set(manifest["files"]) | {"manifest.json"}


def make_package(folder, *, legacy=False):
    folder.mkdir()
    evidence = "evidence/capture.html" if legacy else "evidence/capture.original.bin"
    values = {
        "notification.pdf": b"SYNTHETIC_PDF",
        "notification.docx": b"SYNTHETIC_DOCX",
        "snapshot.json": json.dumps(
            {"evidence": [{"path": evidence, "name": "capture.html"}]}
        ).encode(),
        evidence: png_bytes() + b"SYNTHETIC_CAPTURE_MARKER",
    }
    for name, body in values.items():
        p = folder / name
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(body)
    manifest = {"files": {n: hashlib.sha256(b).hexdigest() for n, b in values.items()}}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return values


def export_bytes(folder):
    manifest, raw = validated_inventory(
        folder, {"notification.pdf", "notification.docx", "snapshot.json"}
    )
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        write_export(archive, folder, manifest, raw)
    return stream.getvalue()


def test_unlisted_file_or_symlink_is_never_collected(tmp_path):
    folder = tmp_path / "package"
    values = make_package(folder)
    outside = tmp_path / "other-case.txt"
    outside.write_bytes(b"SYNTHETIC_OTHER_CASE")
    (folder / "unexpected.txt").write_bytes(b"UNLISTED")
    (folder / "unexpected-link").symlink_to(outside)
    with ZipFile(io.BytesIO(export_bytes(folder))) as archive:
        assert set(archive.namelist()) == set(values) | {"manifest.json"}
        assert b"SYNTHETIC_OTHER_CASE" not in b"".join(archive.read(n) for n in archive.namelist())


def test_listed_symlink_is_rejected_even_when_target_hash_matches(tmp_path):
    folder = tmp_path / "package"
    make_package(folder)
    pdf = folder / "notification.pdf"
    inside = folder / "same-bytes.pdf"
    pdf.rename(inside)
    pdf.symlink_to(inside)
    with pytest.raises(ValueError, match="symbolic links"):
        export_bytes(folder)


def test_package_directory_cannot_redirect_through_a_link(tmp_path):
    actual = tmp_path / "reports"
    actual.mkdir()
    (actual / "case").mkdir()
    (tmp_path / "linked-reports").symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic links"):
        package_folder(tmp_path, "linked-reports/case")


def test_export_rechecks_member_bytes_after_inventory_validation(tmp_path):
    folder = tmp_path / "package"
    make_package(folder)
    manifest, raw = validated_inventory(
        folder, {"notification.pdf", "notification.docx", "snapshot.json"}
    )
    (folder / "notification.pdf").write_bytes(b"CHANGED_AFTER_VALIDATION")
    with ZipFile(io.BytesIO(), "w") as archive, pytest.raises(ValueError, match="changed files"):
        write_export(archive, folder, manifest, raw)


def test_legacy_export_has_separate_transport_manifest_and_preserves_certified_bytes(tmp_path):
    folder = tmp_path / "legacy"
    originals = make_package(folder, legacy=True)
    originals["manifest.json"] = (folder / "manifest.json").read_bytes()
    before = {n: hashlib.sha256(b).hexdigest() for n, b in originals.items()}
    with ZipFile(io.BytesIO(export_bytes(folder))) as archive:
        assert "evidence/capture.html" not in archive.namelist()
        assert archive.read("evidence/capture.html.bin") == originals["evidence/capture.html"]
        assert archive.read("snapshot.json") == originals["snapshot.json"]
        assert archive.read("certified-manifest.json") == originals["manifest.json"]
        assert "manifest.json" not in archive.namelist()
        transport = json.loads(archive.read("export-manifest.json"))
        assert transport["filename_mapping"] == {
            "evidence/capture.html": "evidence/capture.html.bin"
        }
        assert set(archive.namelist()) == set(transport["files"]) | {"export-manifest.json"}
        for name, digest in transport["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        certified = json.loads(archive.read("certified-manifest.json"))
        for name, digest in certified["files"].items():
            delivered = transport["filename_mapping"].get(name, name)
            assert hashlib.sha256(archive.read(delivered)).hexdigest() == digest
    assert {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in originals} == before


@pytest.mark.parametrize(
    "name",
    [
        "../outside.txt",
        "/outside.txt",
        "evidence\\outside",
        "evidence/../outside",
        "evidence/file:stream",
        "evidence//file",
    ],
)
def test_manifest_names_are_portable_and_canonical(tmp_path, name):
    folder = tmp_path / "package"
    make_package(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["files"][name] = "0" * 64
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        export_bytes(folder)
