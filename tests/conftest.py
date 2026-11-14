"""No unit/integration test may quietly depend on public services."""

import pytest
import requests


@pytest.fixture(autouse=True)
def block_external_requests(monkeypatch):
    def blocked(*args, **kwargs):
        # A prohibited test request is not a transient network failure. Retry
        # tests install their own transport faults and controlled clocks.
        raise requests.RequestException("External networking disabled in tests")

    monkeypatch.setattr(requests, "get", blocked)
    from workbench.intelligence import acquisition

    monkeypatch.setattr(acquisition, "_response_get", blocked)
    # Offline source fixtures must not sleep on the cross-provider network gate.
    # Transport rate-limit tests exercise the original gate with a controlled clock.
    from workbench import cve_catalog

    monkeypatch.setattr(cve_catalog, "pace_nvd", lambda cancel_event=None, **kwargs: None)


@pytest.fixture(autouse=True)
def synthetic_native_content_scanner(monkeypatch):
    """Synthetic suites use controlled provider decisions, not the host's AMSI.

    Native-contract tests replace this provider with their own clean, blocked
    or unavailable cases; production scan functions and fail-closed behavior
    remain active throughout the suite.
    """
    from content_scan_helpers import NativeProvider
    from workbench.aegis import antimalware

    if not antimalware._is_windows():
        return None
    provider = NativeProvider()
    monkeypatch.setattr(antimalware, "_dll", provider)
    return provider
