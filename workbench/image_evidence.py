"""Screenshot format policy and immutable original-byte metadata."""

from __future__ import annotations

import hashlib
import io
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
