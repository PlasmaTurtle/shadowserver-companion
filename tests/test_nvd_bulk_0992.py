"""Authenticated bulk import, durable page cursors and secret-free boundaries."""

import json
import threading
from datetime import datetime, timezone
import pytest

from test_workbench import app, client
from workbench.cve_catalog import Catalog, CatalogCancelled, CatalogDeferred
from workbench.cve_catalog.credentials import NVDKeys
from workbench.cve_catalog import transport

KEY = "00000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def cve(number):
    return {
        "cve": {
            "id": f"CVE-2026-{number:04}",
            "published": "2026-01-01T00:00:00.000",
            "lastModified": "2026-11-12T11:00:00.000",
            "vulnStatus": "Analyzed",
            "descriptions": [{"lang": "en", "value": "Bulk catalog fixture"}],
        }
    }


class Bulk:
    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure

    def bulk_page(self, index, **kwargs):
        self.calls.append(index)
        if self.failure is not None:
            return self.failure(
                index
            ), "https://services.nvd.nist.gov/rest/json/cves/2.0?startIndex=" + str(index)
        return json.dumps(
            {
                "startIndex": index,
                "resultsPerPage": 2,
                "totalResults": 4,
                "vulnerabilities": [cve(index + 1), cve(index + 2)],
            }
        ).encode(), "https://services.nvd.nist.gov/rest/json/cves/2.0?startIndex=" + str(index)

    def api_page(self, start, end, index, **kwargs):
        return json.dumps(
            {"startIndex": 0, "resultsPerPage": 0, "totalResults": 0, "vulnerabilities": []}
        ).encode(), "https://services.nvd.nist.gov/rest/json/cves/2.0?lastModStartDate=" + start


def test_full_bulk_catalog_completes_and_next_run_only_updates(tmp_path):
    network = Bulk()
    catalog = Catalog(tmp_path / "work", transport=network, clock=lambda: NOW, bootstrap="api")
    result = catalog.sync()
    assert network.calls == [0, 2]
    assert (
        result["bootstrap_complete"] and result["total"] == 4 and result["download_method"] == "api"
    )
    assert result["years_complete"] == []
    assert catalog.get("CVE-2026-0001")["source"]["format"] == "NVD API 2.0 full catalog"
    assert catalog.metadata("sync_cursor") == NOW.isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    catalog.sync()
    assert network.calls == [0, 2]


def test_bulk_resume_keeps_committed_pages_and_correct_coverage(tmp_path):
    event = threading.Event()
    network = Bulk()
    root = tmp_path / "work"
    catalog = Catalog(root, transport=network, clock=lambda: NOW, bootstrap="api")

    def progress(value):
        if value.get("records") == 2:
            event.set()

    with pytest.raises(CatalogCancelled):
        catalog.sync(cancel_event=event, progress=progress)
    assert catalog.status()["total"] == 2 and not catalog.status()["bootstrap_complete"]
    assert catalog.metadata("api_bootstrap")["start_index"] == 2
    assert catalog.metadata("last_success_at") is None
    resumed = Catalog(root, transport=network, clock=lambda: NOW, bootstrap="api")
    resumed.sync()
    assert network.calls == [0, 2] and resumed.status()["total"] == 4


@pytest.mark.parametrize("case", ["duplicate", "truncated", "wrong_index", "invalid_record"])
def test_bad_page_never_advances_or_marks_catalog_ready(tmp_path, case):
    def failure(index):
        page = {
            "startIndex": index,
            "resultsPerPage": 2,
            "totalResults": 4,
            "vulnerabilities": [cve(index + 1), cve(index + 2)],
        }
        if index:
            if case == "duplicate":
                page["vulnerabilities"][0] = cve(1)
            elif case == "truncated":
                page["vulnerabilities"] = []
            elif case == "wrong_index":
                page["startIndex"] = 100
            else:
                page["vulnerabilities"][1]["cve"]["id"] = "bad"
        return json.dumps(page).encode()

    catalog = Catalog(
        tmp_path / "work", transport=Bulk(failure=failure), clock=lambda: NOW, bootstrap="api"
    )
    with pytest.raises((ValueError, CatalogDeferred)):
        catalog.sync()
    assert catalog.status()["total"] == 2 and not catalog.status()["bootstrap_complete"]
    assert catalog.metadata("last_success_at") is None


def test_bulk_requires_key_in_normal_setup(tmp_path):
    catalog = Catalog(tmp_path / "work")
    with pytest.raises(ValueError, match="NVD API key"):
        catalog.sync()
    assert catalog.status()["total"] == 0


def test_complete_legacy_catalog_moves_to_api_coverage_without_bulk_download(tmp_path):
    network = Bulk()
    catalog = Catalog(tmp_path / "work", transport=network, clock=lambda: NOW, bootstrap="api")
    catalog._initialize()
    with catalog.connection() as db:
        for year in range(2002, datetime.now(timezone.utc).year + 1):
            db.execute(
                "INSERT INTO feeds VALUES(?,?,?,?,?)",
                (year, "0" * 64, NOW.isoformat(), NOW.isoformat(), 1),
            )
    assert catalog.status()["bootstrap_complete"]
    assert catalog.sync()["download_method"] == "api"
    assert catalog.metadata("api_bootstrap_complete") is True
    assert network.calls == []


def test_key_is_only_sent_in_nvd_api_header_and_redirects_are_disabled(tmp_path, monkeypatch):
    captured = []

    class Response:
        status_code = 200
        headers = {}

        def close(self):
            pass

    def get(url, **kwargs):
        captured.append((url, kwargs))
        return Response()

    monkeypatch.setattr(transport.requests, "get", get)
    monkeypatch.setattr(transport, "pace_nvd", lambda *args, **kwargs: None)
    network = transport.NVDTransport(lambda: KEY)
    network.open(transport.API_URL + "?startIndex=0", api=True)
    network.open(transport.FEED_BASE + "nvdcve-2.0-2026.meta", api=True)
    assert captured[0][1]["headers"]["apiKey"] == KEY
    assert not captured[0][1]["allow_redirects"]
    assert "apiKey" not in captured[1][1]["headers"]
    assert all(KEY not in url for url, _ in captured)


def test_keyed_budget_is_shared_and_cancellable(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(transport, "_next_api", 0.0)
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(transport.time, "sleep", lambda v: clock.__setitem__(0, clock[0] + v))
    transport.pace_nvd(authenticated=True)
    transport.pace_nvd(authenticated=True)
    assert clock[0] == pytest.approx(102.0)
    event = threading.Event()
    event.set()
    with pytest.raises(CatalogCancelled):
        transport.pace_nvd(event, authenticated=True)


def test_api_key_storage_and_validation_never_echo_secrets(client, app):
    result = client.put("/api/nvd/credentials", json={"api_key": KEY, "remember": False})
    assert result.status_code == 200 and result.json()["configured"]
    assert KEY not in result.text
    assert NVDKeys(app.state.store.root).get() == KEY
    bad = client.put("/api/nvd/credentials", json={"api_key": KEY * 10})
    assert bad.status_code == 422 and KEY not in bad.text
    assert KEY not in client.get("/api/bootstrap").text
    assert KEY not in app.state.store.db.read_bytes().decode(errors="ignore")
    assert client.delete("/api/nvd/credentials").status_code == 200
    assert not NVDKeys(app.state.store.root).get()


def test_windows_credential_adapter_round_trip_is_separate_from_workspace(tmp_path):
    class Backend:
        def __init__(self):
            self.values = {}

        def read(self, target):
            return self.values[target]

        def write(self, target, value):
            self.values[target] = value

        def delete(self, target):
            self.values.pop(target, None)

    backend = Backend()
    keys = NVDKeys(tmp_path / "one", backend=backend)
    assert keys.configure(KEY, remember=True)["source"] == "windows"
    assert list(backend.values)[0].startswith("ShadowserverCompanion/NVD/")
    assert not (tmp_path / "one").exists()
    assert not NVDKeys(tmp_path / "other", backend=backend).get()
    assert keys.forget()["configured"] is False


def test_shifted_page_resets_coverage_without_deleting_saved_records(tmp_path):
    def shifted(index):
        return json.dumps(
            {
                "startIndex": index,
                "resultsPerPage": 2,
                "totalResults": 4,
                "vulnerabilities": [cve(1), cve(2)],
            }
        ).encode()

    network = Bulk(failure=shifted)
    catalog = Catalog(tmp_path / "work", transport=network, clock=lambda: NOW, bootstrap="api")
    with pytest.raises(CatalogDeferred):
        catalog.sync()
    assert catalog.metadata("api_bootstrap") is None
    assert catalog.status()["total"] == 2
    network.failure = None
    assert catalog.sync()["bootstrap_complete"]
    assert network.calls == [0, 2, 0, 2]


def test_invalid_environment_key_does_not_break_workspace_status(tmp_path, monkeypatch):
    monkeypatch.setenv("NVD_API_KEY", "invalid-secret")
    keys = NVDKeys(tmp_path)
    assert keys.status()["configured"] is False
    assert "invalid-secret" not in json.dumps(keys.status())
