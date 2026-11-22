"""Reusable synthetic contacts api fixtures and builders."""

import time

import pytest

from modules.entities.components.contact_discovery.engine import REVISION
from modules.entities.tests.support.contacts import attributed_entity, contact_result
from modules.investigations.components.cases import Cases
from modules.workspace.components.api import create_app
from tests.session_helpers import TestClient


class FixtureCore:
    def __init__(self, calls):
        self.calls = calls

    def discover(self, root_hostname, *, aliases=(), cancel_event=None, source_url=None):
        self.calls.append((root_hostname, aliases))
        result = contact_result(root_hostname)
        result["aliases"] = list(aliases)
        result["source_url"] = source_url or ""
        result["discovery_revision"] = REVISION
        return result


@pytest.fixture
def fixture(tmp_path):
    calls = []
    app = create_app(
        tmp_path / "data", worker=False, contact_discovery_factory=lambda: FixtureCore(calls)
    )
    entity = attributed_entity(app.state.store)
    case = Cases(app.state.store).create(entity["id"])
    with TestClient(app) as client:
        yield app, client, entity, case, calls


def finished(jobs, identity, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = jobs.get(identity)
        if result["state"] not in ("queued", "running", "cancelling"):
            return result
        time.sleep(0.01)
    raise AssertionError("Contact discovery did not settle")
