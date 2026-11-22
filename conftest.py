"""Shared test fixtures for requests.get, Library transports and native scanning.

These patches are not a process-wide network sandbox. Tests using other
transports must provide their own controlled endpoints or fixtures.
"""

from pathlib import Path

import pytest
import requests

from tests.fixture_paths import validate_fixture_imports


def pytest_configure():
    """Fail before pytest's default collection can select ambiguous filenames."""
    try:
        validate_fixture_imports(Path(__file__).resolve().parent)
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error


@pytest.fixture(autouse=True)
def block_external_requests(monkeypatch):
    def blocked(*args, **kwargs):
        # A prohibited test request is not a transient network failure. Retry
        # tests install their own transport faults and controlled clocks.
        raise requests.RequestException("External networking disabled in tests")

    monkeypatch.setattr(requests, "get", blocked)
    from modules.library.components.intelligence import acquisition

    monkeypatch.setattr(acquisition, "_response_get", blocked)
    from modules.library.components.cve_catalog import feed_http

    monkeypatch.setattr(feed_http, "_stream_response", blocked)
    # Offline source fixtures must not sleep on the cross-provider network gate.
    # Transport rate-limit tests exercise the original gate with a controlled clock.
    from modules.library.components import cve_catalog

    monkeypatch.setattr(cve_catalog, "pace_nvd", lambda cancel_event=None, **kwargs: None)


@pytest.fixture(autouse=True)
def synthetic_native_content_scanner(monkeypatch):
    """Synthetic suites use controlled provider decisions, not the host's AMSI.

    Native-contract tests replace this provider with their own clean, blocked
    or unavailable cases; production scan functions and fail-closed behavior
    remain active throughout the suite.
    """
    from tests.content_scan_helpers import NativeProvider
    from modules.workspace.components.aegis import antimalware

    if not antimalware._is_windows():
        return None
    provider = NativeProvider()
    monkeypatch.setattr(antimalware, "_dll", provider)
    return provider
