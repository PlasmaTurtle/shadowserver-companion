"""Compact captures restore exact artwork and continue to read historical captures."""

from base64 import b64encode
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

import pytest

from modules.investigations.components import exhibit_masters as masters
from modules.ui.components.exhibit_rendering import office_svg, png
from modules.investigations.components.services.notification_views import _editor_artwork_metadata
from modules.ui.components.vector_layout import ExhibitPage


def specimen():
    model = {"id": "EX-STORAGE", "layout_revision": "storage-test", "title": "Saved artwork"}
    rendered = []
    for number in range(1, 5):
        page = ExhibitPage(
            id=model["id"],
            page=number,
            width=489.6,
            height=80,
            elements=[("text", 20, 40, f"Saved page {number}", 10, False, "#000000")],
            alt_text=f"Saved page {number}",
        )
        rendered.append(
            masters.RenderedPage(page, office_svg(page), png(page), office_svg(page, True))
        )
    return model, rendered


def historical(model, rendered):
    """The original schema-1 encoding; no call to the current capture implementation."""
    result = deepcopy(model)
    records = []
    for page in rendered:
        geometry = asdict(page.page)
        record = {"geometry": geometry, "geometry_sha256": masters.digest(geometry)}
        for name in ("svg", "png", "standalone_svg"):
            blob = getattr(page, name)
            record[name] = b64encode(blob).decode("ascii")
            record[name + "_sha256"] = sha256(blob).hexdigest()
        records.append(record)
    result["rendered_masters"] = {
        "schema": 1,
        "layout_revision": model["layout_revision"],
        "model_sha256": masters.model_digest(model),
        "font_sha256": masters.font_digest(),
        "pages": records,
    }
    return result


def read_saved(model):
    def forbidden(*args, **kwargs):
        pytest.fail("Saved artwork was regenerated")

    return masters.prepare(model, forbidden, forbidden, forbidden)


def assert_identical(actual, expected):
    for restored, original in zip(actual, expected, strict=True):
        assert masters.digest(asdict(restored.page)) == masters.digest(asdict(original.page))
        assert restored.svg == original.svg
        assert restored.png == original.png
        assert restored.standalone_svg == original.standalone_svg


def test_shared_font_resources_reduce_saved_size_and_restore_exact_bytes():
    model, rendered = specimen()
    old = historical(model, rendered)
    masters.capture(model, rendered)
    assert model["rendered_masters"]["schema"] == 2
    assert len(model["rendered_masters"]["resources"]) == 1
    assert len(json.dumps(model)) < len(json.dumps(old)) / 4
    assert_identical(read_saved(json.loads(json.dumps(model))), rendered)
    projected = _editor_artwork_metadata(model)
    assert "resources" not in projected["rendered_masters"]
    assert len(json.dumps(projected)) < 10000
    with pytest.raises(ValueError, match="full verified snapshot"):
        read_saved(projected)


def test_historical_schema_and_captured_hashes_are_never_rewritten():
    model, rendered = specimen()
    old = historical(model, rendered)
    encoded = json.dumps(old, sort_keys=True)
    assert_identical(read_saved(old), rendered)
    masters.capture(old, rendered)
    assert json.dumps(old, sort_keys=True) == encoded
    assert masters.reuse(model, old)
    assert json.dumps(model, sort_keys=True) == encoded
    assert_identical(read_saved(model), rendered)


@pytest.mark.parametrize("damage", ["resource", "missing_resource", "fragment", "bad_fragment"])
def test_corrupt_shared_resources_or_page_fragments_are_rejected(damage):
    model, rendered = specimen()
    masters.capture(model, rendered)
    saved = model["rendered_masters"]
    resource = next(iter(saved["resources"]))
    if damage == "resource":
        saved["resources"][resource] = b64encode(b"changed fonts").decode()
    elif damage == "missing_resource":
        saved["resources"].clear()
    elif damage == "fragment":
        saved["pages"][0]["svg"][0] = {"data": b64encode(b"changed SVG").decode()}
    else:
        saved["pages"][0]["svg"] = "invalid parts"
    with pytest.raises(ValueError):
        read_saved(model)
