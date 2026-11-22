"""Offline transports for the real Attribution and retained-capture boundaries.

These fixtures supply source responses and a labelled viewport; production
qualification, matching, evidence persistence and case adoption remain active.
Browser rendering itself is checked by the native local-page acceptance tests.
"""

from dataclasses import dataclass
import io
import json
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageDraw
from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings

from modules.attribution.components.attribution_bridge import RegistrationAttribution
from modules.workspace.components.primitives import now


class WhoisLookupError(Exception):
    """Synthetic provider failure supplied by a test."""


@dataclass(frozen=True)
class WhoisRecord:
    ip: str
    registry: str
    source_url: str
    retrieved_at: str
    record: dict
    protocol: str = "RDAP"


def capture_website(
    url, *, cancel_event=None, skip_urls=(), require_usable=False, page_check=None, deadline=None
):
    if cancel_event and cancel_event.is_set():
        raise ValueError("Website capture cancelled")
    image = Image.new("RGB", (1440, 900), "#f0f4f8")
    draw = ImageDraw.Draw(image)
    draw.text((50, 50), "SYNTHETIC WEBSITE FIXTURE", fill="#15334a")
    draw.text((50, 90), url, fill="#15334a")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue(), {
        "requested_url": url,
        "final_url": url,
        "captured_at": now(),
        "capture_status": "captured",
        "http_status": 200,
        "title": "Synthetic website fixture",
        "site_name": "Example Company (synthetic)",
        "redirects": [url],
        "attempted_urls": [url],
        "attempts": [{"url": url, "outcome": "captured"}],
        "viewport": {"width": 1440, "height": 900},
        "load_readiness": {"document_loaded": True, "document_ready": True},
    }


def registry_factory(factory):
    """Adapt fixture response objects at HTTP, never a second qualification path."""

    def create(store, config, *, cancel_event=None):
        registry = factory()

        def respond(request):
            if "data.iana.org" in str(request.url):
                body = {"services": [[["0.0.0.0/0", "::/0"], ["https://rdap.arin.net/registry/"]]]}
            else:
                address = urlsplit(str(request.url)).path.rsplit("/", 1)[-1]
                try:
                    result = registry.lookup(address)
                except WhoisLookupError as error:
                    raise httpx.ConnectError(str(error), request=request) from error
                if result is None:
                    return httpx.Response(
                        404,
                        headers={"Content-Type": "application/rdap+json"},
                        stream=httpx.ByteStream(b"{}"),
                    )
                body = {
                    "objectClassName": "ip network",
                    "startAddress": result.ip,
                    "endAddress": result.ip,
                    **result.record,
                }
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rdap+json"},
                stream=httpx.ByteStream(json.dumps(body).encode()),
            )

        evidence = EvidenceStore(store.root / "attribution.sqlite3")
        provider = RdapProvider(
            evidence,
            Settings(interval=0, retries=0),
            transport=httpx.MockTransport(respond),
            cancel_event=cancel_event,
        )
        module = AttributionModule(evidence, providers=[provider], cancel_event=cancel_event)
        module._owns_store = True
        module._owned = [provider, registry]
        adapter = RegistrationAttribution.__new__(RegistrationAttribution)
        adapter.module = module
        return adapter

    return create
