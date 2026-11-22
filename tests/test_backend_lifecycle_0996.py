"""Producer shutdown and explicit credential replacement remain deterministic."""

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
from types import SimpleNamespace

import pytest

from modules.workspace.components.api import create_app
from modules.library.components.cve_catalog import credentials
from modules.library.components.cve_catalog.credentials import NVDKeys


OLD_KEY = "00000000-0000-4000-8000-000000000001"
NEW_KEY = "00000000-0000-4000-8000-000000000002"


class Vault:
    def __init__(self):
        self.values = {}
        self.deleted = []
        self.fail = ""

    def read(self, target):
        return self.values[target]

    def write(self, target, value):
        if self.fail == "write":
            raise OSError("Private backend error: " + NEW_KEY)
        self.values[target] = value

    def delete(self, target):
        if self.fail == "delete":
            raise OSError("Private backend error: " + OLD_KEY)
        self.deleted.append(target)
        return self.values.pop(target, None) is not None


@pytest.fixture
def keys(tmp_path, monkeypatch):
    monkeypatch.delenv("NVD_API_KEY", raising=False)
    value = NVDKeys(tmp_path, backend=Vault())
    yield value
    with credentials._lock:
        credentials._sessions.pop(value.identity, None)


@pytest.mark.parametrize("previously_saved", [False, True])
def test_session_only_replacement_never_restores_a_saved_key(keys, previously_saved):
    if previously_saved:
        keys.configure(OLD_KEY, remember=True)
    result = keys.configure(NEW_KEY, remember=False)
    assert result == {"configured": True, "source": "session", "remember_supported": True}
    assert keys.get() == NEW_KEY
    assert keys.backend.deleted == [keys.target]
    assert not keys.backend.values

    # Simulate a new process, while retaining the same OS vault.
    with credentials._lock:
        credentials._sessions.pop(keys.identity)
    assert keys.get() == ""
    assert keys.status()["source"] == "none"


@pytest.mark.parametrize("operation", ["replace", "forget", "save"])
def test_failed_vault_changes_preserve_existing_credentials_and_redact_errors(keys, operation):
    keys.configure(OLD_KEY, remember=True)
    keys.backend.fail = "write" if operation == "save" else "delete"
    with pytest.raises(ValueError, match="Windows Credential Manager") as caught:
        if operation == "forget":
            keys.forget()
        else:
            keys.configure(NEW_KEY, remember=operation == "save")
    assert OLD_KEY not in str(caught.value) and NEW_KEY not in str(caught.value)
    assert keys.get() == OLD_KEY
    assert keys.backend.values[keys.target] == OLD_KEY.encode("ascii")
    assert keys.status()["source"] == "windows"


def test_forget_waits_for_inflight_save_and_removes_its_result(keys):
    entered, resume, removing = threading.Event(), threading.Event(), threading.Event()
    write = keys.backend.write

    def delayed_write(target, value):
        entered.set()
        assert resume.wait(3)
        write(target, value)

    def forget():
        removing.set()
        return keys.forget()

    keys.backend.write = delayed_write
    with ThreadPoolExecutor(max_workers=2) as pool:
        saved = pool.submit(keys.configure, NEW_KEY, remember=True)
        try:
            assert entered.wait(3)
            forgotten = pool.submit(forget)
            assert removing.wait(3)
            with pytest.raises(TimeoutError):
                forgotten.result(timeout=0.1)
        finally:
            resume.set()
        assert saved.result(timeout=3)["configured"]
        assert forgotten.result(timeout=3)["configured"] is False
    assert keys.get() == ""
    assert not keys.backend.values


@pytest.mark.parametrize("failure", [None, "body", "startup", "closer", "cancel"])
def test_lifespan_drains_producers_before_consumers_even_when_cleanup_raises(
    tmp_path, monkeypatch, failure
):
    application = create_app(tmp_path / "lifecycle", worker=failure == "startup")
    application.state.report_operations = SimpleNamespace(close=lambda: None)
    services = (
        "cve_catalog",
        "intake",
        "api_acquisition",
        "source_jobs",
        "website_jobs",
        "asset_attribution_jobs",
        "contact_discovery_jobs",
        "acquisition_schedule",
        "entity_dns",
        "report_operations",
    )
    closed = []

    for name in services:
        service = getattr(application.state, name)
        original = service.close

        def close(name=name, original=original):
            closed.append(name)
            original()
            if failure == "closer" and name == "api_acquisition":
                raise RuntimeError("Synthetic closer error")

        monkeypatch.setattr(service, "close", close)

    if failure == "startup":

        def fail_start():
            raise RuntimeError("Synthetic startup error")

        monkeypatch.setattr(application.state.intake, "start", fail_start)

    async def exercise():
        async with application.router.lifespan_context(application):
            if failure == "body":
                raise RuntimeError("Synthetic body error")
            if failure == "cancel":
                raise asyncio.CancelledError()

    if failure:
        expected = asyncio.CancelledError if failure == "cancel" else RuntimeError
        with pytest.raises(expected):
            asyncio.run(exercise())
    else:
        asyncio.run(exercise())

    assert sorted(closed) == sorted(services)
    assert closed.index("acquisition_schedule") < closed.index("api_acquisition")
    assert closed.index("api_acquisition") < closed.index("intake")
    assert closed.index("intake") < closed.index("cve_catalog")
