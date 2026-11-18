"""Explicit, edition-bound software updates from the project's published releases.

The GitHub repository is the distribution trust boundary. Installer and manifest
SHA-256 digests must agree with GitHub's asset metadata. This is integrity
verification over authenticated HTTPS, not an Authenticode/signature claim.
No user API credentials, workspace records or telemetry enter this channel.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .release import installation_identity, load_release, check_output_name

REPOSITORY = "PlasmaTurtle/shadowserver-companion"
RELEASES_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
MAX_METADATA = 4 * 1024 * 1024
MAX_MANIFEST = 64 * 1024
MAX_INSTALLER = 1024 * 1024 * 1024
MAX_NOTES = 30
TIMEOUT = 20
DOWNLOAD_SECONDS = 15 * 60
_DIGEST = re.compile(r"sha256:([a-f0-9]{64})\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.exe\Z")
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
_CHANNEL_RANK = {"unstable": 0, "candidate": 1, "stable": 2}


class UpdateError(ValueError):
    """Safe, recipient-facing update failure."""


def version_tuple(value):
    if not isinstance(value, str) or len(value) > 32 or not _VERSION.fullmatch(value):
        raise UpdateError("The published update contains an invalid version.")
    return tuple(map(int, value.split(".")))


def validate_installer_name(name, release):
    if (
        not isinstance(name, str)
        or not _NAME.fullmatch(name)
        or not re.search(r"(?:^|[-_])v?" + re.escape(release["version"]) + r"(?=[-_.]|$)", name)
    ):
        raise UpdateError("The update installer filename does not identify this release.")
    try:
        check_output_name(Path(name), release)
    except ValueError:
        raise UpdateError(
            "The update installer filename does not identify this edition or channel."
        ) from None


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _url(url, *, asset=False, redirect=False):
    if not isinstance(url, str) or len(url) > 8192:
        raise UpdateError("The update download address is invalid.")
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        raise UpdateError("The update download address is invalid.") from None
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.fragment
        or any(ord(c) < 32 for c in url)
    ):
        raise UpdateError("Software updates require an approved HTTPS download address.")
    if redirect:
        if parsed.hostname not in {
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }:
            raise UpdateError("The update download redirected outside the approved release hosts.")
        if parsed.hostname != "github.com":
            return url
    if asset:
        prefix = f"/{REPOSITORY}/releases/download/"
        if parsed.hostname != "github.com" or not parsed.path.startswith(prefix) or parsed.query:
            raise UpdateError("The update asset is outside the project's published releases.")
        # No encoded separators, backslashes or dot-segment tricks in the source path.
        if re.search(r"%2f|%5c|%2e|\\", parsed.path, re.I) or any(
            p in {".", ".."} for p in parsed.path.split("/")
        ):
            raise UpdateError("The update asset path is invalid.")
    elif url != RELEASES_URL:
        raise UpdateError("The update metadata source is not approved.")
    return url


class _ReleaseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        _url(newurl, asset=True, redirect=True)
        return super().redirect_request(request, fp, code, message, headers, newurl)


class GitHubReleaseTransport:
    def __init__(self):
        self.opener = build_opener(_ReleaseRedirects())

    def _open(self, url, *, asset=False):
        _url(url, asset=asset)
        request = Request(
            url,
            headers={
                "User-Agent": "Shadowserver-Eclipse-Updater",
                "Accept": "application/octet-stream" if asset else "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            return self.opener.open(request, timeout=TIMEOUT)
        except HTTPError as error:
            if error.code == 404:
                raise UpdateError("The project has no accessible published update feed.") from None
            if error.code in (403, 429):
                raise UpdateError(
                    "The release service is temporarily limiting requests. Try again later."
                ) from None
            raise UpdateError("The release service could not complete the request.") from None
        except (URLError, TimeoutError, OSError):
            raise UpdateError(
                "The release service could not be reached. Check your connection and try again."
            ) from None

    def read(self, url, limit, *, asset=False):
        started = time.monotonic()
        chunks = []
        count = 0
        with self._open(url, asset=asset) as response:
            reader = getattr(response, "read1", response.read)
            while True:
                if time.monotonic() - started > 60:
                    raise UpdateError("The update metadata took too long. Try again.")
                chunk = reader(min(64 * 1024, limit + 1 - count))
                if not chunk:
                    return b"".join(chunks)
                count += len(chunk)
                if count > limit:
                    raise UpdateError("The update metadata exceeded the allowed size.")
                chunks.append(chunk)

    def download(self, url, destination, expected_size, progress, cancelled):
        started = time.monotonic()
        count = 0
        with self._open(url, asset=True) as response, destination.open("xb") as target:
            reader = getattr(response, "read1", response.read)
            while True:
                if cancelled.is_set():
                    raise UpdateError(
                        "The update download was cancelled when the application closed."
                    )
                if time.monotonic() - started > DOWNLOAD_SECONDS:
                    raise UpdateError("The update download took too long. Try again.")
                chunk = reader(256 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > expected_size:
                    raise UpdateError("The downloaded installer exceeded its published size.")
                target.write(chunk)
                progress(count)
            target.flush()
            os.fsync(target.fileno())
        if count != expected_size:
            raise UpdateError("The installer download was incomplete. Try again.")


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise UpdateError("The update metadata contains duplicate fields.")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, TypeError):
        raise UpdateError("The published update metadata is invalid.") from None


def _asset(release, name, limit):
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) > 100:
        raise UpdateError("The published release asset list is invalid.")
    matching = [a for a in assets if isinstance(a, dict) and a.get("name") == name]
    if len(matching) != 1:
        raise UpdateError("The release is missing a unique verified update asset.")
    asset = matching[0]
    size = asset.get("size")
    digest = asset.get("digest")
    if (
        asset.get("state") != "uploaded"
        or type(size) is not int
        or not 0 < size <= limit
        or not isinstance(digest, str)
        or not _DIGEST.fullmatch(digest)
    ):
        raise UpdateError("The release asset has no valid published SHA-256 or size.")
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", tag):
        raise UpdateError("The release tag is invalid.")
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe='')}/{quote(name, safe='')}"
    if asset.get("browser_download_url") != expected_url:
        raise UpdateError("The release asset does not belong to the selected release.")
    _url(expected_url, asset=True)
    return {"name": name, "size": size, "sha256": digest[7:], "url": expected_url}


def _manifest(value, release, installed, identity):
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise UpdateError("The release uses an unsupported update manifest.")
    for key in ("edition", "variant"):
        if value.get(key, "") != installed.get(key, ""):
            raise UpdateError("The update belongs to a different application edition.")
    if value.get("app_id") != identity["app_id"]:
        raise UpdateError("The update belongs to a different installation.")
    version = value.get("version")
    version_tuple(version)
    if not re.fullmatch(
        r"v?" + re.escape(version) + r"(?:[-.][A-Za-z0-9._-]+)?", release["tag_name"]
    ):
        raise UpdateError("The update version does not match its release tag.")
    channel = value.get("channel")
    allowed = {
        "stable": {"stable"},
        "candidate": {"stable", "candidate"},
        "unstable": {"stable", "candidate", "unstable"},
    }[installed["channel"]]
    if (
        channel not in allowed
        or type(release.get("prerelease")) is not bool
        or release["prerelease"] != (channel != "stable")
    ):
        raise UpdateError("The published update is not compatible with this release channel.")
    installer = value.get("installer")
    if not isinstance(installer, dict):
        raise UpdateError("The update installer name is invalid.")
    validate_installer_name(installer.get("name"), value)
    asset = _asset(release, installer["name"], MAX_INSTALLER)
    if installer.get("sha256") != asset["sha256"] or installer.get("size") != asset["size"]:
        raise UpdateError("The update manifest and installer asset do not agree.")
    notes = value.get("highlights", [])
    title = value.get("title", f"Version {version}")
    if (
        not isinstance(notes, list)
        or len(notes) > MAX_NOTES
        or any(not isinstance(x, str) or not x.strip() or len(x) > 1000 for x in notes)
        or not isinstance(title, str)
        or not title.strip()
        or len(title) > 160
    ):
        raise UpdateError("The update release notes are invalid.")
    return {
        "version": version,
        "channel": channel,
        "edition": value["edition"],
        "variant": value.get("variant", ""),
        "app_id": identity["app_id"],
        "title": title,
        "highlights": notes,
        "installer": asset,
        "release_url": f"https://github.com/{REPOSITORY}/releases/tag/{release['tag_name']}",
    }


def bundled_notes(root, release):
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")[: 256 * 1024]
    match = re.search(
        r"^# " + re.escape(release["version"]) + r"(?:[ \t]+[^\n]*)?\n(.*?)(?=^# |\Z)",
        text,
        re.M | re.S,
    )
    if not match:
        return {
            "version": release["version"],
            "title": f"Version {release['version']}",
            "highlights": ["This release is installed. Detailed release notes are not bundled."],
        }
    heading = text[match.start() : text.find("\n", match.start())].lstrip("# ").strip()
    bullets = []
    for line in match.group(1).splitlines():
        if line.startswith("- "):
            bullets.append(line[2:].strip())
        elif line.startswith("  ") and bullets:
            bullets[-1] += " " + line.strip()
    return {
        "version": release["version"],
        "title": heading[:160],
        "highlights": [x[:1000] for x in bullets[:MAX_NOTES]] or ["This release is installed."],
    }


def _regular_directory(path):
    for item in (path, *path.parents):
        if item.exists() and (
            item.is_symlink() or getattr(item.stat(), "st_file_attributes", 0) & 0x400
        ):
            raise UpdateError("The update staging path cannot contain a link or junction.")
    path.mkdir(parents=True, exist_ok=True)


def verify_installer(path, candidate):
    if path.is_symlink() or not path.is_file():
        raise UpdateError("The downloaded installer is missing or unsafe. Download it again.")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise UpdateError("The downloaded installer is unsafe. Download it again.")
    expected = candidate["installer"]
    if info.st_size != expected["size"]:
        raise UpdateError("The downloaded installer changed. Download it again.")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        if source.read(2) != b"MZ":
            raise UpdateError("The downloaded file is not a Windows installer.")
        source.seek(0)
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected["sha256"]:
        raise UpdateError(
            "The downloaded installer failed SHA-256 verification. Download it again."
        )


class SoftwareUpdates:
    def __init__(
        self,
        workspace,
        *,
        root=None,
        release=None,
        transport=None,
        installed=None,
        launcher=None,
        install_guard=None,
        install_cancel=None,
    ):
        self.root = Path(root or Path(__file__).resolve().parents[1]).resolve()
        self.release = release or load_release(self.root)
        self.identity = installation_identity(
            self.release["edition"], self.release.get("variant", "")
        )
        workspace = Path(workspace).resolve()
        self.directory = workspace.parent / (workspace.name + "-software-updates")
        self.seen_file = workspace / "software-version-seen.json"
        self.transport = transport or GitHubReleaseTransport()
        self.installed = self._installed() if installed is None else bool(installed)
        self.launcher = launcher or self._launch
        self.install_guard = install_guard
        self.install_cancel = install_cancel
        self.shutdown = None  # Bound by the real server runtime, never a request parameter.
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="software-update")
        self.closed = threading.Event()
        self.future = None
        self.candidate = None
        self.path = None
        self.phase = "idle"
        self.message = "Check the project's published releases when you are ready."
        self.checked_at = None
        self.downloaded = 0

    def _installed(self):
        manifest = self.root.parent / "payload-manifest.json"
        try:
            value = _json(manifest.read_bytes())
            return (
                os.name == "nt"
                and self.root.name == "app"
                and (self.root.parent / "runtime" / "python.exe").is_file()
                and value.get("release", {}).get("edition") == self.release["edition"]
                and value.get("release", {}).get("variant", "") == self.release.get("variant", "")
            )
        except (OSError, UpdateError, AttributeError):
            return False

    def status(self):
        with self.lock:
            candidate = (
                None
                if self.candidate is None
                else {
                    k: self.candidate[k]
                    for k in ("version", "channel", "title", "highlights", "release_url")
                }
            )
            return {
                "phase": self.phase,
                "message": self.message,
                "checked_at": self.checked_at,
                "current_version": self.release["version"],
                "channel": self.release["channel"],
                "candidate": candidate,
                "downloaded_bytes": self.downloaded,
                "total_bytes": self.candidate["installer"]["size"] if self.candidate else None,
                "can_install": self.installed and callable(self.shutdown),
                "distribution_url": f"https://github.com/{REPOSITORY}/releases",
            }

    def start(self, operation):
        with self.lock:
            if (
                self.closed.is_set()
                or (self.future and not self.future.done())
                or self.phase == "installing"
            ):
                raise UpdateError("A software update operation is already in progress.")
            if operation == "check":
                self.candidate = None
                self.path = None
                self.downloaded = 0
                self.phase = "checking"
                self.message = "Checking published releases…"
                task = self._check
            elif operation == "download":
                if self.candidate is None or self.phase not in {"available", "ready", "failed"}:
                    raise UpdateError("Check for a compatible published update first.")
                self.phase = "downloading"
                self.message = "Downloading and verifying the installer…"
                self.downloaded = 0
                task = self._download
            else:
                raise UpdateError("Unknown software update operation.")
            self.future = self.executor.submit(self._run, task)
            return self.status()

    def _run(self, task):
        try:
            task()
        except UpdateError as error:
            with self.lock:
                self.phase, self.message = "failed", str(error)
        except Exception:
            with self.lock:
                self.phase, self.message = (
                    "failed",
                    "The update could not complete. Try again; your current installation is unchanged.",
                )

    def _check(self):
        started = time.monotonic()
        releases = _json(self.transport.read(RELEASES_URL, MAX_METADATA))
        if not isinstance(releases, list) or len(releases) > 100:
            raise UpdateError("The published release list is invalid.")
        name = f"software-update-{self.identity['app_id']}.json"
        candidates = []
        for item in releases:
            if self.closed.is_set():
                raise UpdateError("The update check was cancelled when the application closed.")
            if time.monotonic() - started > 180:
                raise UpdateError("The update check took too long. Try again.")
            if not isinstance(item, dict) or item.get("draft") is not False:
                continue
            assets = item.get("assets", [])
            if not isinstance(assets, list) or not any(
                isinstance(a, dict) and a.get("name") == name for a in assets
            ):
                continue
            # Any malformed manifest in this installation's named stream fails closed.
            asset = _asset(item, name, MAX_MANIFEST)
            raw = self.transport.read(asset["url"], MAX_MANIFEST, asset=True)
            if len(raw) != asset["size"] or hashlib.sha256(raw).hexdigest() != asset["sha256"]:
                raise UpdateError("The published update manifest failed SHA-256 verification.")
            value = _json(raw)
            if (
                isinstance(value, dict)
                and value.get("channel")
                not in {
                    "stable": {"stable"},
                    "candidate": {"candidate", "stable"},
                    "unstable": {"unstable", "candidate", "stable"},
                }[self.release["channel"]]
            ):
                continue
            candidate = _manifest(value, item, self.release, self.identity)
            candidates.append(candidate)
        with self.lock:
            self.checked_at = _stamp()
            if not candidates:
                self.phase = "unpublished"
                self.message = (
                    "No compatible release is published for this installation and channel. "
                    "The installed version remains available."
                )
                return

            def release_order(value):
                return version_tuple(value["version"]), _CHANNEL_RANK[value["channel"]]

            latest = max(candidates, key=release_order)
            if release_order(latest) <= release_order(self.release):
                self.phase, self.message = "current", "No newer compatible release is published."
            else:
                self.candidate = latest
                self.phase, self.message = (
                    "available",
                    f"Version {latest['version']} is available. Review the changes before installing.",
                )

    def _download(self):
        with self.lock:
            candidate = self.candidate
        _regular_directory(self.directory)
        final = self.directory / (candidate["installer"]["sha256"] + ".exe")
        partial = final.with_suffix(".partial")
        if partial.exists() or partial.is_symlink():
            partial.unlink()

        def progress(count):
            with self.lock:
                self.downloaded = count

        try:
            if final.exists():
                try:
                    verify_installer(final, candidate)
                except UpdateError:
                    final.unlink()
            if not final.exists():
                self.transport.download(
                    candidate["installer"]["url"],
                    partial,
                    candidate["installer"]["size"],
                    progress,
                    self.closed,
                )
                verify_installer(partial, candidate)
                os.replace(partial, final)
            verify_installer(final, candidate)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        with self.lock:
            self.path = final
            self.downloaded = candidate["installer"]["size"]
            self.phase = "ready"
            self.message = "The installer is verified and ready. Save your work before installing."

    @staticmethod
    def _launch(path):
        if os.name != "nt":
            raise UpdateError(
                "Installing updates is available in the Windows-installed application."
            )
        subprocess.Popen(
            [str(path), "/UPDATE", "/RESTART"],
            shell=False,
            close_fds=True,
            cwd=str(path.parent),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    def prepare_install(self):
        with self.lock:
            if not self.installed or not callable(self.shutdown):
                raise UpdateError(
                    "Installing updates is available in the Windows-installed application."
                )
            if self.phase != "ready" or self.path is None or self.candidate is None:
                raise UpdateError("Download and verify an update before installing it.")
            try:
                _regular_directory(self.directory)
                verify_installer(self.path, self.candidate)
            except UpdateError as error:
                self.phase, self.message = "failed", str(error)
                raise
            # Reserve the workspace only after verification succeeds. The guard
            # atomically refuses new work until shutdown or install_cancel.
            if self.install_guard:
                reason = self.install_guard()
                if reason:
                    raise UpdateError(str(reason))
            self.phase = "installing"
            self.message = "Closing the workspace and starting the verified installer…"
            return self.status()

    def install(self):
        # Invoked after the authenticated HTTP response has been sent.
        verified = False
        try:
            with self.lock:
                if self.phase != "installing":
                    return
                verify_installer(self.path, self.candidate)
                verified = True
                self.launcher(self.path)
            self.shutdown()
        except Exception:
            try:
                if self.install_cancel:
                    self.install_cancel()
            finally:
                with self.lock:
                    self.phase = "ready" if verified else "failed"
                    self.message = (
                        "The installer could not start. Your current installation remains open; try again."
                        if verified
                        else "The downloaded installer changed. Download it again before installing."
                    )

    def whats_new(self):
        notes = bundled_notes(self.root, self.release)
        try:
            seen = _json(self.seen_file.read_bytes())
        except (OSError, UpdateError):
            seen = {}
        if not isinstance(seen, dict):
            seen = {}
        return {**notes, "should_show": seen.get("version") != self.release["version"]}

    def mark_seen(self, version):
        if version != self.release["version"]:
            raise UpdateError("The release notice does not match this installed version.")
        with self.lock:
            self.seen_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.seen_file.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"version": version, "seen_at": _stamp()}) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self.seen_file)
        return {"version": version, "seen": True}

    def close(self):
        self.closed.set()
        self.executor.shutdown(wait=True, cancel_futures=True)
