"""Reject network error pages before reference-feed staging, using offline bytes."""

from datetime import datetime, timezone
import gzip
import hashlib
import json

import pytest

from test_local_risk_0984 import epss_bytes, kev_raw
from workbench.cve_catalog import Catalog
from workbench.cve_catalog.content_validation import validated_gzip_chunks
from workbench.cve_catalog.risk import RiskTransport
from workbench.cve_catalog.transport import NVDTransport, FEED_BASE

MARKER = b"INERT_UNSUPPORTED_PAGE_0998"


class Response:
    status_code = 200

    def __init__(self, body, media, *, chunk_size=128 * 1024):
        self.body = body
        self.headers = {"Content-Type": media}
        self.chunk_size = chunk_size
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def close(self):
        pass

    def iter_content(self, ignored):
        for pos in range(0, len(self.body), self.chunk_size):
            self.reads += 1
            yield self.body[pos : pos + self.chunk_size]


@pytest.mark.parametrize(
    "provider,body,media",
    [
        ("kev", b"<html>" + MARKER + b"</html>", "text/html"),
        ("kev", b"<html>" + MARKER + b"</html>", "application/json"),
        ("kev", b'{"count":1,"count":2}', "application/json"),
        ("kev", b'{"error":"unavailable"}', "text/plain"),
        ("epss", b"<html>" + MARKER + b"</html>", "application/gzip"),
        ("epss", gzip.compress(b"<html>" + MARKER + b"</html>"), "application/gzip"),
        ("epss", gzip.compress(b"cve,epss,percentile\n"), "application/gzip"),
    ],
)
def test_risk_error_bodies_never_replace_target_or_leave_staging(
    tmp_path, monkeypatch, provider, body, media
):
    import requests

    response = Response(body, media, chunk_size=3)
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    target = tmp_path / "existing-feed"
    target.write_bytes(b"previous valid feed remains")
    with pytest.raises(ValueError):
        RiskTransport().download(provider, target)
    assert target.read_bytes() == b"previous valid feed remains"
    assert list(tmp_path.iterdir()) == [target]
    if media == "text/html":
        assert response.reads == 0


@pytest.mark.parametrize("provider", ["epss", "kev"])
def test_valid_risk_feeds_preserve_exact_bytes_across_tiny_chunks(tmp_path, monkeypatch, provider):
    import requests

    body = epss_bytes() if provider == "epss" else json.dumps(kev_raw()).encode()
    media = "application/octet-stream" if provider == "epss" else "text/plain; charset=utf-8"
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response(body, media, chunk_size=1))
    target = tmp_path / "feed"
    receipt = RiskTransport().download(provider, target)
    assert target.read_bytes() == body
    assert receipt["sha256"] == hashlib.sha256(body).hexdigest()
    assert receipt["bytes"] == len(body)


@pytest.mark.parametrize(
    "body",
    [
        b"<html>" + MARKER + b"</html>",
        gzip.compress(b"<html>" + MARKER + b"</html>"),
        gzip.compress(b'{"error":"unavailable"}'),
        gzip.compress(b'{"message":"vulnerabilities: []"}'),
    ],
)
def test_nvd_bad_document_never_yields_bytes_for_disk(body):
    saved = []
    with pytest.raises(ValueError):
        for chunk in validated_gzip_chunks(
            (body[pos : pos + 5] for pos in range(0, len(body), 5)), "nvd"
        ):
            saved.append(chunk)
    assert saved == []


def test_gzip_header_validation_is_bounded_and_preserves_valid_nvd():
    raw = json.dumps(
        {
            "format": "NVD_CVE",
            "version": "2.0",
            "vulnerabilities": [{"cve": {"id": "CVE-2026-1234"}}],
        }
    ).encode()
    body = gzip.compress(raw)
    assert (
        b"".join(validated_gzip_chunks((body[i : i + 1] for i in range(len(body))), "nvd")) == body
    )
    # A compressed whitespace bomb cannot consume arbitrary memory before
    # staging; neither the compressed prefix nor expanded error page is written.
    with pytest.raises(ValueError, match="header"):
        list(validated_gzip_chunks([gzip.compress(b" " * (128 * 1024))], "nvd"))


def test_nvd_transport_rejects_html_media_before_consuming_body(monkeypatch):
    import requests

    response = Response(b"<html>" + MARKER + b"</html>", "text/html")
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    with pytest.raises(ValueError, match="content type"):
        list(NVDTransport().chunks(FEED_BASE + "nvdcve-2.0-2026.json.gz", limit=1000))
    assert response.reads == 0


def test_cached_nvd_html_is_not_expanded_to_new_file(tmp_path):
    feeds = tmp_path / "feeds"
    feeds.mkdir()
    source = feeds / "nvdcve-2.0-2026.json.gz"
    body = b"<html>" + MARKER + b"</html>"
    compressed = gzip.compress(body)
    source.write_bytes(compressed)
    catalog = Catalog(
        tmp_path / "data",
        feed_cache=feeds,
        clock=lambda: datetime(2026, 11, 13, tzinfo=timezone.utc),
    )
    staging = tmp_path / "staging"
    staging.mkdir()
    with pytest.raises(ValueError):
        catalog._download(
            2026,
            {
                "gzSize": len(compressed),
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            },
            staging,
            None,
        )
    assert not (staging / "feed.json").exists()
    assert source.read_bytes() == compressed


@pytest.mark.parametrize(
    "body",
    [
        b'{"vulnerabilities": [], "vulnerabilities": []}',
        b'{"nested": {"id": 1, "id": 2}}',
        b'{"score": NaN}',
        b'{"score": Infinity}',
        b'{"score": -Infinity}',
        b'{"score": 1e999}',
    ],
)
def test_provider_json_rejects_ambiguous_or_nonfinite_input(body):
    from workbench.cve_catalog.content_validation import decode_json_object

    with pytest.raises(ValueError):
        decode_json_object(body)


@pytest.mark.parametrize(
    "raw_record",
    [
        '{"cve":{"id":"CVE-2026-1234","id":"CVE-2026-5678"}}',
        '{"cve":{"id":"CVE-2026-1234","futureField":NaN}}',
        '{"cve":{"id":"CVE-2026-1234","futureField":1e999}}',
    ],
)
def test_streamed_nvd_record_rejects_json_ambiguity(tmp_path, raw_record):
    from workbench.cve_catalog.streaming import records

    path = tmp_path / "synthetic.json"
    path.write_text('{"vulnerabilities":[' + raw_record + "]}")
    with pytest.raises(ValueError):
        list(records(path))


def test_nonfinite_catalog_record_is_rejected_before_database_write(tmp_path):
    from test_cve_catalog_0983 import record

    catalog = Catalog(tmp_path / "data")
    catalog._initialize()
    item = record()
    item["additiveFutureField"] = {"score": float("nan")}
    with catalog.connection() as db:
        with pytest.raises(ValueError):
            catalog.upsert(db, item, {"url": "https://example.com/reference"})
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 0
