"""Offline update trust-boundary, lifecycle and release-notice regression checks."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench.release import installation_identity
from workbench.software_updates import (
    SoftwareUpdates,
    UpdateError,
    RELEASES_URL,
    REPOSITORY,
    _url,
    _ReleaseRedirects,
    version_tuple,
    bundled_notes,
    GitHubReleaseTransport,
)
from workbench.routes.software_updates import register

CURRENT = {
    "version": "0.11.1",
    "channel": "candidate",
    "edition": "chaos",
    "variant": "dark_matter",
}
APP_ID = installation_identity("chaos", "dark_matter")["app_id"]
MANIFEST = f"software-update-{APP_ID}.json"
INSTALLER = "ShadowserverEclipse-0.12.0-rc-Setup-x64.exe"
BYTES = b"MZ" + b"installer-fixture-" * 512


class Transport:
    def __init__(self, *, manifest_changes=None, release_changes=None, installer_bytes=BYTES):
        self.installer_bytes = installer_bytes
        manifest = {
            "schema": 1,
            "version": "0.12.0",
            "channel": "candidate",
            "edition": "chaos",
            "variant": "dark_matter",
            "app_id": APP_ID,
            "title": "Setup and updates",
            "highlights": ["Configure APIs and jurisdiction.", "Install verified updates."],
            "installer": {
                "name": INSTALLER,
                "sha256": hashlib.sha256(BYTES).hexdigest(),
                "size": len(BYTES),
            },
        }
        manifest.update(manifest_changes or {})
        self.manifest = json.dumps(manifest).encode()

        def asset(name, content):
            return {
                "name": name,
                "state": "uploaded",
                "size": len(content),
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/v0.12.0/{name}",
            }

        release = {
            "tag_name": "v0.12.0",
            "draft": False,
            "prerelease": True,
            "assets": [asset(MANIFEST, self.manifest), asset(INSTALLER, BYTES)],
        }
        release.update(release_changes or {})
        self.releases = [release]
        self.reads = []
        self.fail_read = False

    def read(self, url, limit, *, asset=False):
        self.reads.append(url)
        if self.fail_read:
            raise UpdateError("The release service could not be reached.")
        if url == RELEASES_URL:
            return json.dumps(self.releases).encode()
        assert asset and url.endswith(MANIFEST)
        return self.manifest

    def download(self, url, destination, size, progress, cancelled):
        assert url.endswith(INSTALLER)
        destination.write_bytes(self.installer_bytes)
        progress(len(self.installer_bytes))


def make(tmp_path, transport=None, **kwargs):
    root = tmp_path / "program"
    root.mkdir(exist_ok=True)
    (root / "CHANGELOG.md").write_text(
        "# 0.11.1 — Installed changes\n\n- A clear change.\n  Continued detail.\n\n# 0.11.0\n- Old detail.\n"
    )
    return SoftwareUpdates(
        tmp_path / "data",
        root=root,
        release=deepcopy(CURRENT),
        transport=transport or Transport(),
        **kwargs,
    )


def complete(service, operation):
    service.start(operation)
    service.future.result(timeout=5)
    return service.status()


def test_check_download_install_requires_explicit_action_and_rechecks_digest(tmp_path):
    launched = []
    stopped = []
    service = make(tmp_path, installed=True, launcher=lambda path: launched.append(path))
    service.shutdown = lambda: stopped.append(True)
    try:
        assert complete(service, "check")["phase"] == "available"
        assert not launched
        assert complete(service, "download")["phase"] == "ready"
        assert not launched
        service.path.write_bytes(b"MZ tampered")
        with pytest.raises(UpdateError, match="changed"):
            service.prepare_install()
        assert not launched and not stopped
        assert complete(service, "download")["phase"] == "ready"
        assert service.prepare_install()["phase"] == "installing"
        service.install()
        assert len(launched) == 1 and stopped == [True]
        assert launched[0].parent == service.directory
    finally:
        service.close()


@pytest.mark.parametrize(
    "changes,part",
    [
        ({"edition": "standard"}, "edition"),
        ({"variant": ""}, "edition"),
        ({"app_id": "OtherApp"}, "installation"),
        ({"version": "0.13.0"}, "tag"),
        ({"installer": {"name": "../../evil.exe", "size": len(BYTES), "sha256": "a" * 64}}, "name"),
        ({"installer": {"name": INSTALLER, "size": len(BYTES), "sha256": "a" * 64}}, "agree"),
    ],
)
def test_wrong_identity_or_manifest_never_offers_update(tmp_path, changes, part):
    service = make(tmp_path, Transport(manifest_changes=changes))
    try:
        status = complete(service, "check")
        assert status["phase"] == "failed" and part in status["message"]
        assert status["candidate"] is None
    finally:
        service.close()


def test_missing_public_release_is_not_reported_up_to_date(tmp_path):
    transport = Transport()
    transport.releases = []
    service = make(tmp_path, transport)
    try:
        status = complete(service, "check")
        assert status["phase"] == "unpublished"
        assert "No compatible release" in status["message"]
    finally:
        service.close()


def test_missing_digest_or_wrong_release_url_fails_closed(tmp_path):
    transport = Transport()
    transport.releases[0]["assets"][0]["digest"] = None
    service = make(tmp_path, transport)
    try:
        assert complete(service, "check")["phase"] == "failed"
        transport.releases[0]["assets"][0]["digest"] = (
            "sha256:" + hashlib.sha256(transport.manifest).hexdigest()
        )
        transport.releases[0]["assets"][1]["browser_download_url"] = (
            "https://github.com/attacker/other/releases/download/v0.12.0/" + INSTALLER
        )
        assert complete(service, "check")["phase"] == "failed"
    finally:
        service.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/PlasmaTurtle/shadowserver-companion/releases/download/v1/a.exe",
        "https://github.com.evil.example/PlasmaTurtle/shadowserver-companion/releases/download/v1/a.exe",
        "https://user@github.com/PlasmaTurtle/shadowserver-companion/releases/download/v1/a.exe",
        "file:///tmp/installer.exe",
        "https://127.0.0.1/a.exe",
        "https://github.com/PlasmaTurtle/shadowserver-companion/releases/download/../a.exe",
        "https://github.com/PlasmaTurtle/shadowserver-companion/releases/download/v1/%2e%2e.exe",
    ],
)
def test_update_source_and_redirect_allowlist(url):
    with pytest.raises(UpdateError):
        _url(url, asset=True)
    with pytest.raises(UpdateError):
        _url(url, asset=True, redirect=True)


def test_allowed_asset_redirect_stays_on_release_cdn():
    _url(
        "https://release-assets.githubusercontent.com/github-production-release-asset/123/abc?sig=example",
        asset=True,
        redirect=True,
    )
    with pytest.raises(UpdateError):
        _url("https://raw.githubusercontent.com/attacker/payload", asset=True, redirect=True)


def test_download_checksum_failure_is_retryable_and_leaves_no_partial(tmp_path):
    transport = Transport(installer_bytes=b"MZ" + b"x" * (len(BYTES) - 2))
    service = make(tmp_path, transport)
    try:
        complete(service, "check")
        status = complete(service, "download")
        assert status["phase"] == "failed" and "SHA-256" in status["message"]
        assert not list(service.directory.glob("*.partial"))
        assert not list(service.directory.glob("*.exe"))
        transport.installer_bytes = BYTES
        assert complete(service, "download")["phase"] == "ready"
    finally:
        service.close()


def test_check_network_failure_can_retry(tmp_path):
    transport = Transport()
    transport.fail_read = True
    service = make(tmp_path, transport)
    try:
        assert complete(service, "check")["phase"] == "failed"
        transport.fail_read = False
        assert complete(service, "check")["phase"] == "available"
    finally:
        service.close()


def test_stable_channel_does_not_offer_candidate(tmp_path):
    service = make(tmp_path)
    service.release["channel"] = "stable"
    try:
        assert complete(service, "check")["phase"] == "unpublished"
    finally:
        service.close()


def test_candidate_can_receive_stable_promotion_of_same_version(tmp_path):
    transport = Transport(
        manifest_changes={"channel": "stable"}, release_changes={"prerelease": False}
    )
    service = make(tmp_path, transport)
    service.release["version"] = "0.12.0"
    try:
        assert complete(service, "check")["phase"] == "available"
        service.release["channel"] = "stable"
        assert complete(service, "check")["phase"] == "current"
    finally:
        service.close()


def test_busy_workspace_and_noninstalled_runtime_cannot_install(tmp_path):
    service = make(
        tmp_path, installed=True, install_guard=lambda: "Wait for active imports to finish."
    )
    service.shutdown = lambda: None
    try:
        complete(service, "check")
        complete(service, "download")
        with pytest.raises(UpdateError, match="active imports"):
            service.prepare_install()
        assert service.status()["phase"] == "ready"
        service.install_guard = None
        service.installed = False
        with pytest.raises(UpdateError, match="Windows-installed"):
            service.prepare_install()
    finally:
        service.close()


def test_failed_launch_keeps_application_open_and_retryable(tmp_path):
    stopped = []
    reservations = []

    def launch(_path):
        raise OSError("private path must not be exposed")

    service = make(
        tmp_path,
        installed=True,
        launcher=launch,
        install_guard=lambda: reservations.append("reserved"),
        install_cancel=lambda: reservations.append("released"),
    )
    service.shutdown = lambda: stopped.append(True)
    try:
        complete(service, "check")
        complete(service, "download")
        service.prepare_install()
        service.install()
        assert service.status()["phase"] == "ready" and not stopped
        assert "private path" not in service.status()["message"]
        assert reservations == ["reserved", "released"]
    finally:
        service.close()


def test_install_checks_integrity_before_reserving_workspace(tmp_path):
    reservations = []
    service = make(
        tmp_path,
        installed=True,
        install_guard=lambda: reservations.append("reserved"),
        install_cancel=lambda: reservations.append("released"),
    )
    service.shutdown = lambda: None
    try:
        complete(service, "check")
        complete(service, "download")
        service.path.write_bytes(b"MZ changed")
        with pytest.raises(UpdateError):
            service.prepare_install()
        assert reservations == []
        complete(service, "download")
        service.prepare_install()
        service.path.write_bytes(b"MZ changed after reservation")
        service.install()
        assert reservations == ["reserved", "released"]
        assert service.status()["phase"] == "failed"
        assert complete(service, "download")["phase"] == "ready"
    finally:
        service.close()


def test_metadata_transport_enforces_byte_and_elapsed_limits(monkeypatch):
    transport = GitHubReleaseTransport()
    monkeypatch.setattr(transport, "_open", lambda *args, **kwargs: BytesIO(b"12345"))
    assert transport.read(RELEASES_URL, 5) == b"12345"
    with pytest.raises(UpdateError, match="allowed size"):
        transport.read(RELEASES_URL, 4)
    ticks = iter([0, 61])
    monkeypatch.setattr("workbench.software_updates.time.monotonic", lambda: next(ticks))
    with pytest.raises(UpdateError, match="took too long"):
        transport.read(RELEASES_URL, 5)


def test_whats_new_once_per_version_and_reopen_is_available(tmp_path):
    service = make(tmp_path)
    try:
        notes = service.whats_new()
        assert notes["should_show"] and notes["highlights"] == ["A clear change. Continued detail."]
        service.mark_seen(CURRENT["version"])
        assert service.whats_new()["should_show"] is False
        assert service.whats_new()["highlights"] == notes["highlights"]
        with pytest.raises(UpdateError):
            service.mark_seen("99.0.0")
        service.seen_file.write_text("[]")
        assert service.whats_new()["should_show"]
    finally:
        service.close()


def test_routes_expose_no_arbitrary_url_or_installer_parameters(tmp_path):
    service = make(tmp_path)
    app = FastAPI()
    register(app, updates=service)
    try:
        with TestClient(app) as client:
            assert client.get("/api/software/status").status_code == 200
            assert client.post("/api/software/install").status_code == 409
            assert (
                client.post(
                    "/api/software/whats-new/seen",
                    json={"version": "0.11.1", "url": "file:///evil"},
                ).status_code
                == 422
            )
            assert (
                client.post(
                    "/api/software/check", json={"url": "http://127.0.0.1/evil"}
                ).status_code
                == 202
            )
            service.future.result(timeout=5)
            assert service.transport.reads[0] == RELEASES_URL
    finally:
        service.close()


def test_version_order_is_numeric():
    assert version_tuple("0.11.10") > version_tuple("0.11.9")
    for value in ["0.01.2", "1.2", "v1.2.3", "1.2.3;cmd", "1.2.3-rc", True]:
        with pytest.raises(UpdateError):
            version_tuple(value)


def test_manifest_builder_uses_exact_installer_hash_and_bundled_notes(tmp_path):
    from tools.build_update_manifest import build_manifest

    root = tmp_path / "source"
    root.mkdir()
    (root / "VERSION").write_text(CURRENT["version"])
    (root / "RELEASE.json").write_text(json.dumps({"schema": 1, **CURRENT}))
    (root / "CHANGELOG.md").write_text("# 0.11.1 — Setup\n\n- " + "A" * 2000 + "\n")
    installer = tmp_path / "ShadowserverEclipse-0.11.1-rc-Setup-x64.exe"
    installer.write_bytes(BYTES)
    output = tmp_path / MANIFEST
    value = build_manifest(installer, output, root=root)
    assert value["installer"]["sha256"] == hashlib.sha256(BYTES).hexdigest()
    assert value["installer"]["size"] == len(BYTES)
    assert value["app_id"] == APP_ID
    assert len(value["highlights"][0]) == 1000
    assert json.loads(output.read_text()) == value
    with pytest.raises(ValueError, match="must be named"):
        build_manifest(installer, tmp_path / "other.json", root=root)
    wrong_version = tmp_path / "ShadowserverEclipse-0.10.0-rc-Setup-x64.exe"
    wrong_version.write_bytes(BYTES)
    with pytest.raises(ValueError, match="filename"):
        build_manifest(wrong_version, output, root=root)
    installer.write_bytes(b"not executable")
    with pytest.raises(ValueError, match="Windows executable"):
        build_manifest(installer, output, root=root)
