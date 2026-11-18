"""Locked-package integrity and bounded DNS parser security regression."""

from pathlib import Path
import hashlib
import importlib.util
import json
import zipfile
from types import SimpleNamespace

import dns.name
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "check_dependencies", ROOT / "tools/check_dependencies.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def pointer_chain(count):
    # At most 35 bytes. This proves the limit, not resource exhaustion.
    data = bytearray(b"\0")
    offset = 0
    for _ in range(count):
        previous, offset = offset, len(data)
        data.extend((0xC000 | previous).to_bytes(2, "big"))
    return bytes(data), offset


def test_dns_compression_chain_limit_and_valid_control():
    assert dns.name.from_wire(*pointer_chain(16))[0] == dns.name.root
    with pytest.raises(dns.name.PointerChainTooLong):
        dns.name.from_wire(*pointer_chain(17))


def test_release_dependency_locks_and_standalone_wheels_agree():
    packages = gate.verify()
    assert next(p for p in packages if p["name"] == "dnspython")["version"] == "2.9.2"


def test_changed_wheel_is_rejected_before_any_advisory_request(tmp_path):
    (tmp_path / "wheelhouse").mkdir()
    filename = "example-1.0-py3-none-any.whl"
    path = tmp_path / "wheelhouse" / filename
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("example-1.0.dist-info/METADATA", "Name: example\nVersion: 1.0\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "wheelhouse-sha256.json").write_text(json.dumps({filename: digest}))
    (tmp_path / "requirements-windows.txt").write_text("example==1.0 --hash=sha256:" + digest)
    assert gate.wheel_inventory(tmp_path)["example"]["version"] == "1.0"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Changed wheel"):
        gate.wheel_inventory(tmp_path)


def test_requirement_version_mismatch_is_rejected(tmp_path):
    (tmp_path / "wheelhouse").mkdir()
    filename = "example-1.0-py3-none-any.whl"
    path = tmp_path / "wheelhouse" / filename
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("example-1.0.dist-info/METADATA", "Name: example\nVersion: 1.0\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "wheelhouse-sha256.json").write_text(json.dumps({filename: digest}))
    (tmp_path / "requirements-windows.txt").write_text("example==2.0 --hash=sha256:" + digest)
    with pytest.raises(ValueError, match="metadata/hash"):
        gate.wheel_inventory(tmp_path)


@pytest.mark.parametrize(
    "row",
    [
        {"name": "example", "version": "1.0", "skip_reason": "unknown package", "vulns": []},
        {"name": "example", "version": "2.0", "vulns": []},
    ],
)
def test_incomplete_or_wrong_version_scan_is_not_a_pass(monkeypatch, row):
    def scan(command, **_):
        Path(command[command.index("-o") + 1]).write_text(json.dumps({"dependencies": [row]}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gate.subprocess, "run", scan)
    with pytest.raises(ValueError, match="audit"):
        gate.audit([{"name": "example", "version": "1.0"}])


def test_known_advisory_scan_preserves_failure(monkeypatch):
    def scan(command, **_):
        Path(command[command.index("-o") + 1]).write_text(
            json.dumps(
                {
                    "dependencies": [
                        {"name": "example", "version": "1.0", "vulns": [{"id": "SYNTHETIC-1"}]}
                    ]
                }
            )
        )
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(gate.subprocess, "run", scan)
    result = gate.audit([{"name": "example", "version": "1.0"}])
    assert result["status"] == "vulnerabilities_found"
    assert result["advisory_count"] == 1
