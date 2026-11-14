"""Package checks retain integrity without whole-artifact memory allocations."""

import hashlib
import json
import io
from pathlib import Path

import pytest

from workbench.package_integrity import validated_inventory
from workbench import package_integrity


def test_inventory_streams_large_members_and_still_detects_changes(tmp_path, monkeypatch):
    member = tmp_path / "notification.pdf"
    chunk = b"synthetic report bytes" * 1024
    digest = hashlib.sha256()
    with member.open("wb") as stream:
        for _ in range(512):
            stream.write(chunk)
            digest.update(chunk)
    manifest = {"files": {member.name: digest.hexdigest()}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    original = Path.read_bytes

    def bounded_read(path):
        if path == member:
            pytest.fail("Inventory allocated the complete report artifact")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", bounded_read)
    assert validated_inventory(tmp_path, {member.name})[0] == manifest
    with member.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="changed files"):
        validated_inventory(tmp_path, {member.name})


def test_oversized_manifest_rejected_before_opening_body(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b" " * 101)
    monkeypatch.setattr(package_integrity, "MAX_PACKAGE_MANIFEST_BYTES", 100)
    original = Path.open

    def no_body_read(path, *args, **kwargs):
        if path == manifest:
            pytest.fail("Oversized manifest body was opened")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_body_read)
    with pytest.raises(ValueError, match="manifest exceeds.*read limit"):
        validated_inventory(tmp_path, set())


def test_manifest_growth_after_stat_is_still_bounded(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b"{}")
    monkeypatch.setattr(package_integrity, "MAX_PACKAGE_MANIFEST_BYTES", 100)
    original = Path.open
    read_sizes = []

    class GrowingManifest(io.BytesIO):
        def read(self, size=-1):
            read_sizes.append(size)
            return super().read(size)

    def grown_body(path, *args, **kwargs):
        if path == manifest:
            return GrowingManifest(b" " * 1000)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", grown_body)
    with pytest.raises(ValueError, match="manifest exceeds.*read limit"):
        package_integrity.read_manifest(tmp_path)
    assert read_sizes == [101]
