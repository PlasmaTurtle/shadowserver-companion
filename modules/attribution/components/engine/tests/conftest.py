"""Synthetic RDAP fixtures: public IPs are inputs, all fixture registrations are invented."""

import httpx
import pytest

from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings


from attribution_test_support.rdap import Server


@pytest.fixture
def rig(tmp_path):
    server = Server()
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    settings = Settings(interval=0, retries=0)
    provider = RdapProvider(store, settings, transport=httpx.MockTransport(server))
    module = AttributionModule(store, providers=[provider], settings=settings)
    yield module, provider, server, store
    provider.close()
    store.close()
