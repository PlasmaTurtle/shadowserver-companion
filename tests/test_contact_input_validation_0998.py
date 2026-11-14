"""Inert/offline response boundaries: no raw website bytes leave discovery."""

import asyncio
import hashlib
import json

import pytest

from workbench.contact_discovery import ContactDiscovery, FetchResponse
from workbench.contact_discovery.policy import DiscoveryError
from workbench.contact_discovery.transport import _read_body, bounded_fetch
from workbench.contact_discovery.validation import decode_response_text
from test_contact_discovery_090 import FixtureFetcher, ROOT, SECURITY, html


def test_script_and_redirect_markup_never_leave_discovery_or_trigger_subrequests():
    page = (
        '<html><head><script src="https://cdn.example.invalid/inert-fixture.js"></script>'
        '<meta http-equiv="refresh" content="0;url=https://outside.example.invalid/">'
        "</head><body><p>Security team: security@example.org</p>"
        '<script>const unused = "hidden@example.org";</script></body></html>'
    )
    fetcher = FixtureFetcher({ROOT: html(page)})
    result = ContactDiscovery(fetcher=fetcher).discover("example.org")
    assert fetcher.calls == [ROOT, SECURITY]
    assert [c["value"] for c in result["candidates"]] == ["security@example.org"]
    snapshot = result["snapshots"][0]
    assert "body" not in snapshot
    assert snapshot["sha256"] == hashlib.sha256(page.encode()).hexdigest()
    assert snapshot["captured_bytes"] == len(page.encode())
    assert snapshot["derived_evidence"]["contacts"][0]["value"] == "security@example.org"
    serialized = json.dumps(result)
    assert "cdn.example.invalid" not in serialized
    assert "hidden@example.org" not in serialized
    assert "<script" not in serialized


@pytest.mark.parametrize("status", [301, 403, 404, 500])
def test_error_and_redirect_bodies_are_metadata_only(status):
    body = b'<html><script src="https://cdn.example.invalid/inert-fixture.js"></script></html>'
    response = FetchResponse(status, {"content-type": "text/html", "location": "/contact"}, body)
    result = ContactDiscovery(fetcher=FixtureFetcher({ROOT: response})).discover("example.org")
    snapshot = result["snapshots"][0]
    assert snapshot["sha256"] == hashlib.sha256(body).hexdigest()
    assert snapshot["derived_evidence"] is None and "body" not in snapshot
    assert "inert-fixture" not in json.dumps(result)


def test_empty_javascript_shell_retains_only_metadata():
    page = (
        '<div id="app"></div><script src="https://cdn.example.invalid/inert-fixture.js"></script>'
    )
    result = ContactDiscovery(fetcher=FixtureFetcher({ROOT: html(page)})).discover("example.org")
    assert result["candidates"] == []
    assert result["snapshots"][0]["derived_evidence"] is None
    assert result["snapshots"][0]["retention_reason"] == "no_contacts_metadata_only"
    assert any(i["code"] == "render_required" for i in result["issues"])


@pytest.mark.parametrize(
    "body",
    [
        b"MZ inert fixture <p>security@example.org</p>",
        b"\xef\xbb\xbf MZ inert fixture <p>security@example.org</p>",
        b"PK\x03\x04<p>security@example.org</p>",
        b"%PDF-1.7<p>security@example.org</p>",
        b"<p>security@example.org</p>\x00",
        b"<p>security@example.org</p>\x01",
        b"<p>security@example.org</p>\xff",
    ],
)
def test_binary_or_invalid_text_cannot_supply_contacts_despite_html_mime(body):
    response = FetchResponse(200, {"content-type": "text/html"}, body)
    result = ContactDiscovery(fetcher=FixtureFetcher({ROOT: response})).discover("example.org")
    assert result["candidates"] == []
    assert result["snapshots"][0]["derived_evidence"] is None
    assert result["snapshots"][0]["sha256"] == hashlib.sha256(body).hexdigest()
    assert "body" not in result["snapshots"][0]
    assert any(i["code"] in {"invalid_text", "nontext_response"} for i in result["issues"])


@pytest.mark.parametrize(
    "content_type",
    [
        "application/octet-stream",
        "image/svg+xml",
        "text/plain",
        "application/javascript",
        "text/html,text/plain",
        "text/html; charset=utf-16",
        "text/html; charset=unknown",
        "text/html; charset=utf-8; charset=ascii",
        "text/html; charset",
        "",
    ],
)
def test_unsupported_or_ambiguous_media_never_reaches_html_parser(content_type):
    response = FetchResponse(200, {"content-type": content_type}, b"<p>security@example.org</p>")
    result = ContactDiscovery(fetcher=FixtureFetcher({ROOT: response})).discover("example.org")
    assert not result["candidates"]
    assert "body" not in result["snapshots"][0]
    assert result["snapshots"][0]["derived_evidence"] is None


@pytest.mark.parametrize(
    "charset,word",
    [("utf-8", "Zoë"), ("windows-1252", "Zoë"), ("iso-8859-1", "Zoë"), ("us-ascii", "Zoe")],
)
def test_declared_supported_text_encodings_preserve_contact(charset, word):
    body = f"<p>{word} Security team: security@example.org</p>".encode(charset)
    result = ContactDiscovery(
        fetcher=FixtureFetcher(
            {ROOT: FetchResponse(200, {"content-type": f"text/html; charset={charset}"}, body)}
        )
    ).discover("example.org")
    assert result["candidates"][0]["value"] == "security@example.org"
    assert word in result["candidates"][0]["sources"][0]["excerpt"]


def test_partial_utf8_trims_only_incomplete_final_codepoint():
    body = b"<p>security@example.org</p>\xe2\x82"
    assert decode_response_text(body, "text/html", partial=True) == "<p>security@example.org</p>"
    with pytest.raises(DiscoveryError, match="invalid bytes"):
        decode_response_text(body, "text/html")
    with pytest.raises(DiscoveryError, match="invalid bytes"):
        decode_response_text(b"<p>\xffsecurity@example.org</p>\xe2", "text/html", partial=True)


def test_valid_security_txt_derived_contact_and_original_digest_are_retained():
    body = b"Contact: mailto:security@example.org\nExpires: 2099-01-01T00:00:00Z\n"
    result = ContactDiscovery(
        fetcher=FixtureFetcher(
            {SECURITY: FetchResponse(200, {"content-type": "text/plain; charset=utf-8"}, body)}
        )
    ).discover("example.org")
    snapshot = next(s for s in result["snapshots"] if s["url"] == SECURITY)
    assert snapshot["sha256"] == hashlib.sha256(body).hexdigest()
    assert "body" not in snapshot
    assert result["candidates"][0]["value"] == "security@example.org"
    assert snapshot["derived_evidence"]["contacts"][0]["value"] == "security@example.org"


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/html", "content-type": "application/octet-stream"},
        {"content-type": "text/html\r\nX-Fixture: invalid"},
        {"content-type": "text/html", "content-length": "30", "transfer-encoding": "chunked"},
        {"content-type": "text/html", "content-length": "-1"},
        {"content-type": "text/html", "content-length": "2"},
        {"content-type": "text/html", "content-length": "200"},
        {"content-type": "text/html", "content-encoding": "gzip"},
    ],
)
def test_injected_transports_cannot_bypass_header_and_framing_validation(headers):
    fetcher = FixtureFetcher({ROOT: FetchResponse(200, headers, b"<p>security@example.org</p>")})
    with pytest.raises(DiscoveryError):
        bounded_fetch(fetcher, ROOT, timeout=2, max_bytes=4096)


def read_chunks(raw):
    async def read():
        reader = asyncio.StreamReader()
        reader.feed_data(raw)
        reader.feed_eof()
        return await _read_body(reader, {"transfer-encoding": "chunked"}, 4096)

    return asyncio.run(read())


def test_chunked_framing_requires_complete_terminator_and_bounded_valid_trailers():
    assert read_chunks(b"4\r\ntext\r\n0\r\nX-Fixture: safe\r\n\r\n") == (b"text", False)
    for raw in [
        b"4\r\ntext\r\n0\r\n",
        b"+4\r\ntext\r\n0\r\n\r\n",
        b"4\r\ntext\r\n0\r\nContent-Length: 4\r\n\r\n",
        b"4\r\ntext\r\n0\r\n" + b"X-Fixture: safe\r\n" * 40 + b"\r\n",
    ]:
        with pytest.raises(DiscoveryError):
            read_chunks(raw)
