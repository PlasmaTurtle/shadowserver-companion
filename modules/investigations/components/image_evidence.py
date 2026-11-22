"""Screenshot format policy and immutable original-byte metadata."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
import pillow_heif

pillow_heif.register_heif_opener()
MAX_PIXELS = 40_000_000
FORMATS = {
    ".png": ({"PNG"}, "image/png"),
    ".jpg": ({"JPEG"}, "image/jpeg"),
    ".jpeg": ({"JPEG"}, "image/jpeg"),
    ".webp": ({"WEBP"}, "image/webp"),
    ".heic": ({"HEIF", "HEIC"}, "image/heic"),
    ".heif": ({"HEIF", "HEIC"}, "image/heif"),
}


def decode_screenshot(name, content):
    """Return a safe presentation image and metadata; never rewrite originals."""
    extension = Path(name).suffix.lower()
    if extension not in FORMATS:
        raise ValueError("Use a PNG, JPEG, WebP, or HEIC screenshot filename")
    expected, media_type = FORMATS[extension]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as raw:
                if raw.format not in expected:
                    raise ValueError("Screenshot filename does not match its decoded image format")
                if raw.width * raw.height > MAX_PIXELS:
                    raise ValueError("Screenshot exceeds the 40 megapixel limit")
                decoded_format = raw.format
                image = ImageOps.exif_transpose(raw).convert("RGB")
                image.load()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Use a valid PNG, JPEG, WebP, or HEIC screenshot") from error
    return image, {
        "original_filename": name,
        "decoded_format": decoded_format,
        "media_type": media_type,
        "sha256": hashlib.sha256(content).hexdigest(),
        "storage_policy": "Exact original bytes retained with a non-executable .bin extension",
    }


def metadata_path(evidence_id):
    return f"evidence/{evidence_id}-metadata.json"


def write_screenshot(store, identity, name, content, *, website_capture=None):
    """Retain original bytes and one safe PNG derivative, cleaning partial writes.

    The caller owns database publication and removes these files if it fails.
    A website capture uses the same image contract as an uploaded screenshot.
    """
    image, metadata = decode_screenshot(name, content)
    if website_capture is not None:
        if image.size != (1440, 900):
            raise ValueError("Capture did not return the expected desktop viewport")
        metadata.update(website_capture=website_capture, website_capture_id=identity)
    preview = io.BytesIO()
    image.save(preview, "PNG")
    preview_bytes = preview.getvalue()
    metadata["preview_sha256"] = hashlib.sha256(preview_bytes).hexdigest()
    encoded = json.dumps(metadata, ensure_ascii=False, allow_nan=False).encode("utf-8")
    paths = {
        "path": f"evidence/{identity}.original.bin",
        "preview_path": f"evidence/{identity}-preview.png",
        "metadata_path": metadata_path(identity),
    }
    try:
        for key, value in zip(paths, (content, preview_bytes, encoded)):
            store.path(paths[key]).write_bytes(value)
    except BaseException:
        remove_screenshot(store, paths)
        raise
    return {
        **paths,
        "sha256": metadata["sha256"],
        "preview_sha256": metadata["preview_sha256"],
        "metadata_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def remove_screenshot(store, paths):
    """Remove an unpublished capture; never call for a retained reference."""
    for key in ("path", "preview_path", "metadata_path"):
        store.path(paths[key]).unlink(missing_ok=True)
