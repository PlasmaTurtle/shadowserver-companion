"""Bound request bytes before JSON parsing or multipart disk spooling."""

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException

MIB = 1024 * 1024


def request_limit(path):
    if path == "/api/data/import":
        return 2048 * MIB + MIB  # Existing 2 GiB backup contract + form framing.
    if path == "/api/imports/api-receipt":
        return 257 * MIB
    if path == "/api/imports":
        return 1001 * MIB  # Existing maximum of twenty 50 MiB reports.
    if path.startswith("/api/leads/") and path.endswith("/evidence"):
        return 21 * MIB
    return 32 * MIB


class RequestBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        limit = request_limit(scope.get("path", ""))
        headers = dict(scope.get("headers", []))
        response = JSONResponse(
            {"detail": "Request exceeds the upload size limit"}, status_code=413
        )
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                length = int(declared)
                if length < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({"detail": "Invalid content length"}, status_code=400)(
                    scope, receive, send
                )
            if length > limit:
                return await response(scope, receive, send)
        total = 0
        exceeded = False
        replaced = False

        async def bounded_receive():
            nonlocal total, exceeded
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    exceeded = True
                    if headers.get(b"content-type", b"").startswith(b"multipart/form-data"):
                        # Starlette closes its partially spooled files on this
                        # exception. Replace its generic 400 with 413 below.
                        raise MultiPartException("Request exceeds the upload size limit")
                    raise HTTPException(413, "Request exceeds the upload size limit")
            return message

        async def bounded_send(message):
            nonlocal replaced
            if exceeded:
                if not replaced:
                    replaced = True
                    await response(scope, receive, send)
                return
            await send(message)

        await self.app(scope, bounded_receive, bounded_send)
