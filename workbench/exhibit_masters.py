"""Immutable rendered exhibit pages carried by review and report snapshots.

Rendering functions are supplied by the output facade, keeping this storage
contract independent of the layout/renderer implementation. Hashes detect
accidental mutation; they are not a digital signature or a trust boundary.
"""

from base64 import b64decode, b64encode
from copy import deepcopy
from dataclasses import asdict, dataclass
from functools import lru_cache
from hashlib import sha256
import json
import re

from .vector_layout import ExhibitPage, FONT_ROOT
from .report_operations import check_deadline


def digest(value):
    return sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def model_digest(model):
    return digest({key: value for key, value in model.items() if key != "rendered_masters"})


@lru_cache(maxsize=1)
def font_digest():
    return digest(
        {
            name: sha256((FONT_ROOT / name).read_bytes()).hexdigest()
            for name in (
                "DejaVuSans.ttf",
                "DejaVuSans-Bold.ttf",
                "DejaVuSans.woff",
                "DejaVuSans-Bold.woff",
                "NotoSansSC-Regular.ttf",
                "NotoSansSC-Regular.woff",
            )
        }
    )


@dataclass
class RenderedPage:
    page: ExhibitPage
    svg: bytes
    png: bytes
    standalone_svg: bytes


def _svg_parts(blob, resources):
    """Store repeated font definitions once, retaining every original SVG byte."""
    parts, start = [], 0
    for match in re.finditer(rb"<defs><style>.*?</style></defs>", blob, re.DOTALL):
        if match.start() > start:
            parts.append({"data": b64encode(blob[start : match.start()]).decode("ascii")})
        resource = match.group()
        key = sha256(resource).hexdigest()
        resources.setdefault(key, b64encode(resource).decode("ascii"))
        parts.append({"resource": key})
        start = match.end()
    if start < len(blob):
        parts.append({"data": b64encode(blob[start:]).decode("ascii")})
    return parts


def _restore_svg(parts, resources):
    if not isinstance(parts, list):
        raise ValueError("Rendered SVG resource structure is invalid.")
    result = []
    for part in parts:
        if isinstance(part, dict) and set(part) == {"data"}:
            result.append(b64decode(part["data"], validate=True))
        elif isinstance(part, dict) and set(part) == {"resource"}:
            if part["resource"] not in resources:
                raise ValueError("Rendered SVG resource is missing.")
            result.append(resources[part["resource"]])
        else:
            raise ValueError("Rendered SVG resource structure is invalid.")
    return b"".join(result)


def prepare(model, layout, svg, png):
    saved = model.get("rendered_masters")
    if saved is not None:
        if saved.get("metadata_only"):
            raise ValueError(
                "Editor artwork metadata cannot reconstruct a report; use the full verified snapshot."
            )
        if saved.get("schema") not in {1, 2} or saved.get("model_sha256") != model_digest(model):
            raise ValueError(
                "Rendered exhibit no longer matches its reviewed content; rebuild and review it."
            )
        if saved.get("font_sha256") != font_digest():
            raise ValueError(
                "Bundled exhibit fonts changed; rebuild and review the exhibit before export."
            )
        if not saved.get("pages"):
            raise ValueError("Rendered exhibit contains no pages.")
        resources = {}
        if saved["schema"] == 2:
            for key, encoded in saved.get("resources", {}).items():
                value = b64decode(encoded, validate=True)
                if sha256(value).hexdigest() != key:
                    raise ValueError("Rendered SVG resource integrity check failed.")
                resources[key] = value
        result = []
        for number, item in enumerate(saved["pages"], 1):
            check_deadline()
            geometry = item["geometry"]
            if digest(geometry) != item["geometry_sha256"]:
                raise ValueError("Rendered exhibit geometry integrity check failed.")
            if geometry["id"] != model["id"] or geometry["page"] != number:
                raise ValueError("Rendered exhibit page order is inconsistent.")
            blobs = {}
            for name in ("svg", "png", "standalone_svg"):
                value = (
                    _restore_svg(item[name], resources)
                    if saved["schema"] == 2 and name != "png"
                    else b64decode(item[name], validate=True)
                )
                if sha256(value).hexdigest() != item[name + "_sha256"]:
                    raise ValueError("Rendered exhibit artifact integrity check failed: " + name)
                blobs[name] = value
            result.append(RenderedPage(ExhibitPage(**geometry), **blobs))
        return result
    return [
        RenderedPage(page, svg(page), png(page), svg(page, standalone=True))
        for page in layout(model)
    ]


def capture(model, rendered):
    if "rendered_masters" in model:
        return  # prepare() verified it; never replace an existing reviewed master.
    records, resources = [], {}
    for item in rendered:
        check_deadline()
        geometry = asdict(item.page)
        record = {"geometry": geometry, "geometry_sha256": digest(geometry)}
        for name in ("svg", "png", "standalone_svg"):
            blob = getattr(item, name)
            record[name] = (
                b64encode(blob).decode("ascii") if name == "png" else _svg_parts(blob, resources)
            )
            record[name + "_sha256"] = sha256(blob).hexdigest()
        records.append(record)
    model["rendered_masters"] = {
        "schema": 2,
        "layout_revision": model["layout_revision"],
        "model_sha256": model_digest(model),
        "font_sha256": font_digest(),
        "resources": resources,
        "pages": records,
    }


def reuse(model, frozen):
    saved = frozen.get("rendered_masters") or {}
    if (
        saved.get("model_sha256") == model_digest(model)
        and saved.get("font_sha256") == font_digest()
    ):
        model["rendered_masters"] = deepcopy(saved)
        return True
    return False
