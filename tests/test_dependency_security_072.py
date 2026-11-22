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


def write_test_wheel(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("example-1.0.dist-info/METADATA", "Name: example\nVersion: 1.0\n")
        archive.writestr(
            "example-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_changed_wheel_is_rejected_before_any_advisory_request(tmp_path):
    (tmp_path / "wheelhouse").mkdir()
    filename = "example-1.0-py3-none-any.whl"
    path = tmp_path / "wheelhouse" / filename
    digest = write_test_wheel(path)
    (tmp_path / "requirements-windows.txt").write_text("example==1.0 --hash=sha256:" + digest)
    assert gate.wheel_inventory(tmp_path)["example"]["version"] == "1.0"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Changed wheel"):
        gate.wheel_inventory(tmp_path)


def test_requirement_version_mismatch_is_rejected(tmp_path):
    (tmp_path / "wheelhouse").mkdir()
    filename = "example-1.0-py3-none-any.whl"
    path = tmp_path / "wheelhouse" / filename
    digest = write_test_wheel(path)
    (tmp_path / "requirements-windows.txt").write_text("example==2.0 --hash=sha256:" + digest)
    with pytest.raises(ValueError, match="metadata/hash"):
        gate.wheel_inventory(tmp_path)


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_lock_requires_exactly_one_approved_artifact_per_package(tmp_path, change):
    folder = tmp_path / "wheelhouse"
    folder.mkdir()
    path = folder / "example-1.0-py3-none-any.whl"
    digest = write_test_wheel(path)
    (tmp_path / "requirements-windows.txt").write_text("example==1.0 --hash=sha256:" + digest)
    if change == "missing":
        path.unlink()
    elif change == "extra":
        (folder / "unapproved-1.0-py3-none-any.whl").write_bytes(b"unapproved artifact")
    else:
        (folder / "example-1.0-1-py3-none-any.whl").write_bytes(path.read_bytes())
    with pytest.raises(ValueError):
        gate.wheel_inventory(tmp_path)


@pytest.mark.parametrize(
    "filename",
    [
        "example-2.0-py3-none-any.whl",
        "other-1.0-py3-none-any.whl",
        "invalid.whl",
    ],
)
def test_approved_wheel_cannot_be_renamed_to_another_identity(tmp_path, filename):
    folder = tmp_path / "wheelhouse"
    folder.mkdir()
    digest = write_test_wheel(folder / filename)
    (tmp_path / "requirements-windows.txt").write_text("example==1.0 --hash=sha256:" + digest)
    with pytest.raises(ValueError, match="filename differs"):
        gate.wheel_inventory(tmp_path)


def test_public_constraints_are_generated_and_stale_versions_fail_readonly(tmp_path):
    records = {
        "requests": {"version": "2.34.2"},
        "idna": {"version": "3.20"},
        "outreach-attribution": {"version": "0.2.8"},
    }
    gate.sync_constraints(tmp_path, records, write=True)
    constraints = tmp_path / "requirements-constraints.txt"
    first = constraints.read_bytes()
    assert gate.pins(constraints, hashed=False) == {
        "idna": {"version": "3.20", "sha256": None},
        "requests": {"version": "2.34.2", "sha256": None},
    }
    gate.sync_constraints(tmp_path, records, write=True)
    assert constraints.read_bytes() == first
    constraints.write_text("requests==1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="constraints are stale"):
        gate.sync_constraints(tmp_path, records)
    assert constraints.read_text(encoding="utf-8") == "requests==1.0\n"


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
