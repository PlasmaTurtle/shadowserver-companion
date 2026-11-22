"""Shared security execution stays bounded even when a native provider stalls."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from modules.workspace.components import aegis
from modules.workspace.components.aegis import execution
from modules.workspace.components.aegis.errors import SecurityExecutionError
from tests.content_scan_helpers import install


def test_native_timeouts_hold_capacity_until_contexts_actually_close(monkeypatch):
    pool = execution.SecurityExecutor(capacity=2, max_timeout=0.04)
    monkeypatch.setattr(execution, "_executor", pool)
    provider, _ = install(monkeypatch)
    original = provider.AmsiScanBuffer.callback
    release = threading.Event()

    def stalled(*args):
        release.wait(2)
        return original(*args)

    provider.AmsiScanBuffer.callback = stalled
    try:
        for _ in range(3):
            start = time.monotonic()
            with pytest.raises(aegis.ContentScanError) as caught:
                aegis.scan_text("inert fixture", timeout=999)
            assert caught.value.code == "content_scan_unavailable"
            assert time.monotonic() - start < 0.3
        # The third request does not start a third native context or worker.
        assert [e[0] for e in provider.events] == ["initialize", "initialize"]
    finally:
        release.set()
        pool._jobs.join()
    assert sum(e[0] == "close" for e in provider.events) == 2
    assert aegis.scan_buffer(b"later inert fixture")["status"] == "allowed"
    assert sum(e[0] == "initialize" for e in provider.events) == 3
    assert sum(e[0] == "close" for e in provider.events) == 3


def test_cancellation_before_admission_does_not_start_windows_provider(monkeypatch):
    provider, _ = install(monkeypatch)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(aegis.ContentScanError) as caught:
        aegis.scan_buffer(b"inert fixture", cancel_event=cancel)
    assert caught.value.receipt["status"] == "unavailable"
    assert not provider.events


def test_active_cancellation_returns_promptly_without_releasing_occupied_slot():
    pool = execution.SecurityExecutor(capacity=1, max_timeout=1)
    started, release, cancel = threading.Event(), threading.Event(), threading.Event()

    def stalled():
        started.set()
        release.wait(2)
        return "finished"

    def cancel_after_start():
        assert started.wait(1)
        cancel.set()

    trigger = threading.Thread(target=cancel_after_start, daemon=True)
    trigger.start()
    try:
        with pytest.raises(SecurityExecutionError) as caught:
            pool.run(stalled, cancel_event=cancel)
        assert caught.value.code == "security_cancelled"
        with pytest.raises(SecurityExecutionError) as caught:
            pool.run(lambda: pytest.fail("Occupied slot must not be replaced"), timeout=0.025)
        assert caught.value.code == "security_capacity"
    finally:
        release.set()
        pool._jobs.join()
        trigger.join(1)
    assert pool.run(lambda: "reused") == "reused"


def test_bursts_wait_within_budget_and_never_exceed_native_capacity():
    pool = execution.SecurityExecutor(capacity=2, max_timeout=1)
    lock = threading.Lock()
    active = maximum = 0

    def work():
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return "allowed"

    with ThreadPoolExecutor(max_workers=4) as callers:
        jobs = [callers.submit(pool.run, work) for _ in range(4)]
        assert [job.result() for job in jobs] == ["allowed"] * 4
    assert maximum == 2


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_budget_cannot_start_a_native_scan(monkeypatch, timeout):
    provider, _ = install(monkeypatch)
    with pytest.raises(aegis.ContentScanError):
        aegis.scan_buffer(b"inert fixture", timeout=timeout)
    assert not provider.events


@pytest.mark.parametrize(
    "status,provider,verdict",
    [
        ("allowed", "windows_amsi", "clean"),
        ("allowed", "windows_amsi", "not_detected"),
        ("allowed", "windows_amsi", "below_block_threshold"),
        ("blocked", "windows_amsi", "detected"),
        ("blocked", "windows_amsi", "administrator_policy"),
        ("unavailable", "windows_amsi", "scan_unavailable"),
        ("not_supported", "none", "windows_scan_not_performed"),
        ("empty", "none", "empty_not_scanned"),
    ],
)
def test_receipt_contract_shared_across_text_and_binary_consumers(status, provider, verdict):
    for representation in ("bytes", "utf-16-le"):
        receipt = dict(
            status=status, provider=provider, representation=representation, verdict=verdict
        )
        checked = aegis.validate_scan_receipt(receipt, representation=representation)
        assert checked == receipt and checked is not receipt
        with pytest.raises(aegis.InputValidationError):
            aegis.validate_scan_receipt({**receipt, "provider": "untrusted_provider"})
        with pytest.raises(aegis.InputValidationError):
            aegis.validate_scan_receipt({**receipt, "verdict": "safe_forever"})


def test_legacy_unrecorded_receipt_requires_explicit_permission():
    receipt = dict(
        status="not_recorded", provider="none", representation="none", verdict="not_recorded"
    )
    with pytest.raises(aegis.InputValidationError):
        aegis.validate_scan_receipt(receipt)
    assert (
        aegis.validate_scan_receipt(receipt, allow_unrecorded=True, representation="utf-16-le")
        == receipt
    )
    for changed in ({"provider": "windows_amsi"}, {"representation": "bytes"}, {"extra": "value"}):
        with pytest.raises(aegis.InputValidationError):
            aegis.validate_scan_receipt({**receipt, **changed}, allow_unrecorded=True)


def test_public_unavailable_factory_has_fixed_non_content_receipt():
    error = aegis.scan_unavailable(representation="bytes")
    assert error.code == "content_scan_unavailable"
    assert (
        aegis.validate_scan_receipt(error.receipt, representation="bytes")["status"]
        == "unavailable"
    )


def test_shared_security_package_depends_only_on_itself_and_standard_library():
    import ast
    from pathlib import Path
    import sys

    folder = Path(aegis.__file__).parent
    local_modules = {path.stem for path in folder.glob("*.py")}
    for path in folder.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                assert all(
                    item.name.split(".")[0] in sys.stdlib_module_names for item in node.names
                ), path.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1 and node.module.split(".")[0] in local_modules, path.name
                else:
                    assert node.module.split(".")[0] in sys.stdlib_module_names, path.name
    assert aegis.strict_json_loads('{"valid":true}') == {"valid": True}
    assert aegis.parse_media_type("text/html; charset=utf-8")[0] == "text/html"
