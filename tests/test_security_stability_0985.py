"""Audit regressions for input budgets and image integrity."""

import io
import json
import pytest
from PIL import Image
from starlette.requests import Request
from starlette.responses import JSONResponse
from modules.workspace.components.request_limits import RequestBodyLimit
from tests.support.workbench import app, client, import_rows
from modules.investigations.components.image_evidence import metadata_path


@pytest.mark.parametrize("multipart", [False, True])
def test_streaming_limit_also_handles_missing_content_length(multipart, monkeypatch):
    import asyncio
    import modules.workspace.components.request_limits as limits
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    server = FastAPI()
    server.add_middleware(RequestBodyLimit)

    @server.post("/upload")
    async def upload(request: Request):
        if multipart:
            async with request.form():
                return {"ok": True}
        return {"bytes": len(await request.body())}

    monkeypatch.setattr(limits, "request_limit", lambda path: 50)
    content = (
        (
            b'--bound\r\nContent-Disposition: form-data; name="file"; filename="x.png"\r\n\r\n'
            + b"a" * 100
            + b"\r\n--bound--\r\n"
        )
        if multipart
        else b"x" * 100
    )

    def chunks():
        yield content[:35]
        yield content[35:]

    headers = {"Content-Type": "multipart/form-data; boundary=bound"} if multipart else {}
    result = TestClient(server).post("/upload", content=chunks(), headers=headers)
    assert result.status_code == 413, result.text
    assert result.json()["detail"] == "Request exceeds the upload size limit"


def test_declared_over_limit_never_reads_the_body(monkeypatch):
    import asyncio
    import modules.workspace.components.request_limits as limits

    monkeypatch.setattr(limits, "request_limit", lambda path: 50)
    called = []
    sent = []

    async def handler(*args):
        called.append(True)

    async def receive():
        raise AssertionError("Oversized request was read")

    async def send(message):
        sent.append(message)

    asyncio.run(
        RequestBodyLimit(handler)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/test",
                "headers": [(b"content-length", b"9999")],
            },
            receive,
            send,
        )
    )
    assert not called and sent[0]["status"] == 413


def test_upload_hashes_preview_and_rejects_changed_image(client, app):
    import_rows(client, app)
    lead_id = client.get("/api/leads").json()[0]["id"]
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "navy").save(output, "PNG")
    response = client.post(
        f"/api/leads/{lead_id}/evidence",
        files={"file": ("site.png", output.getvalue(), "image/png")},
    )
    assert response.status_code == 200, response.text
    row = response.json()["evidence"][0]
    meta = json.loads(app.state.store.path(metadata_path(row["id"])).read_text(encoding="utf-8"))
    assert meta["preview_sha256"]
    app.state.store.path(row["preview_path"]).write_bytes(b"changed")
    response = client.get("/api/evidence/" + row["id"] + "/image")
    assert response.status_code == 409


def test_affected_fips_runtime_is_rejected_without_disabling_policy(monkeypatch):
    from modules.workspace.components import crypto_policy

    monkeypatch.setattr(crypto_policy.sys, "version_info", (3, 14, 10))
    monkeypatch.setattr(crypto_policy._hashlib, "get_fips_mode", lambda: 1)
    with pytest.raises(RuntimeError, match="FIPS mode has not been disabled"):
        crypto_policy.validate_runtime()
    monkeypatch.setattr(crypto_policy._hashlib, "get_fips_mode", lambda: 0)
    crypto_policy.validate_runtime()


def test_all_workers_close_even_when_lifespan_exits_with_an_error(tmp_path, monkeypatch):
    import asyncio
    from modules.workspace.components.api import create_app

    application = create_app(tmp_path / "lifecycle", worker=False)
    closed = []
    for name in (
        "cve_catalog",
        "intake",
        "source_jobs",
        "website_jobs",
        "asset_attribution_jobs",
        "contact_discovery_jobs",
        "api_acquisition",
    ):
        service = getattr(application.state, name)
        monkeypatch.setattr(service, "close", lambda name=name: closed.append(name))

    async def exercise():
        async with application.router.lifespan_context(application):
            raise RuntimeError("Synthetic shutdown error")

    with pytest.raises(RuntimeError, match="Synthetic"):
        asyncio.run(exercise())
    assert len(closed) == 7
