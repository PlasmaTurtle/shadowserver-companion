"""Reusable synthetic export security fixtures and builders."""

import hashlib
import io
import json

from PIL import Image


def png_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (3, 2), "white").save(stream, "PNG")
    return stream.getvalue()


def make_package(folder, *, legacy=False):
    folder.mkdir()
    evidence = "evidence/capture.html" if legacy else "evidence/capture.original.bin"
    values = {
        "notification.pdf": b"SYNTHETIC_PDF",
        "notification.docx": b"SYNTHETIC_DOCX",
        "snapshot.json": json.dumps(
            {"evidence": [{"path": evidence, "name": "capture.html"}]}
        ).encode(),
        evidence: png_bytes() + b"SYNTHETIC_CAPTURE_MARKER",
    }
    for name, body in values.items():
        p = folder / name
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(body)
    manifest = {"files": {n: hashlib.sha256(b).hexdigest() for n, b in values.items()}}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return values
