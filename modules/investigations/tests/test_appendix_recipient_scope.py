"""Keep recipient source fields complete without repeating internal parser metadata."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json

from modules.investigations.components.appendix import Appendix
from modules.investigations.components import appendix_view
from modules.investigations.components.appendix_layout import layout_appendix


def fixture():
    appendix = Appendix()
    profile = {
        "id": "scan_http_vulnerable",
        "adapter_version": "synthetic-test",
        "declared_fields": [f"unused_{i}" for i in range(35)],
        "endpoint_roles": {"reported_service": {"hostname": "hostname", "ip": "ip"}},
    }
    for position in range(4):
        appendix.add(
            "A",
            "observation",
            "Synthetic observation",
            {
                "id": str(position),
                "ip": f"192.0.2.{position + 1}",
                "source": {
                    "workbook": "synthetic.csv",
                    "sheet": "CSV",
                    "row": position + 2,
                    "fields": {
                        "hostname": "mail.example.com",
                        "ip": f"192.0.2.{position + 1}",
                        "tag": "eol-php",
                        "version": "php/7.3.25",
                        "unknown/field": "Original unknown column",
                        "normalized/profile": "This is a source column, not internal metadata",
                        "zero": 0,
                        "disabled": False,
                        "blank": "",
                        "nothing": None,
                        "empty_list": [],
                        "empty_object": {},
                    },
                },
                "normalized": {
                    "schema_version": 1,
                    "observation_ref": str(position),
                    "profile": profile,
                    "eligibility": {"included_as_context": False, "severity": "critical"},
                    "products": [{"product": "php", "version": "7.3.25"}],
                    "findings": [],
                    "future_metadata": "Unknown future fields stay visible",
                },
            },
        )
    appendix.add(
        "A",
        "import_provenance",
        "Original import · synthetic.csv",
        {
            "filename": "synthetic.csv",
            "sha256": "a" * 64,
            "imported_at": "2026-11-08T00:00:00Z",
            "parsing_policy": {
                "critical_only": True,
                "report_profiles": [profile],
                "profile_inventory": {"sha256": "b" * 64, "count": 177},
            },
        },
    )
    return appendix.model()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fields(view):
    return {
        record["id"]: {
            field["path"]: field for group in record["groups"] for field in group["fields"]
        }
        for record in view["records"]
    }


def test_current_view_keeps_every_source_value_and_removes_only_known_internal_metadata():
    source = fixture()
    saved = deepcopy(source)
    views, _, _ = appendix_view.build_appendix_views(source)
    current = next(view for view in views if view["id"] == "EX-APPENDIX-A")
    visible = fields(current)
    for record in source["entries"]:
        for field in record["fields"]:
            path = field["path"]
            if path.startswith("/source/") or path.startswith("/normalized/products/"):
                shown = visible[record["id"]][path]
                assert {key: value for key, value in shown.items() if key != "label"} == field
        paths = visible[record["id"]]
        assert not any(path.startswith("/normalized/profile/") for path in paths)
        assert not any(path.startswith("/parsing_policy/report_profiles/") for path in paths)
        assert not any(path.startswith("/parsing_policy/profile_inventory/") for path in paths)
        if record["kind"] == "observation":
            assert "/normalized/future_metadata" in paths
            assert "/normalized/eligibility/included_as_context" in paths
    assert source == saved
    assert "complete import record" in " ".join(views[0]["reading_notes"])


def test_pinned_review_layout_keeps_its_original_model_and_page_geometry():
    models, nodes, navigation = appendix_view.build_appendix_views(
        fixture(), revision=appendix_view.FIRST_REVIEW_REVISION
    )
    assert (
        digest([models, nodes, navigation])
        == "413f72c9a2bdd9ca92af8629598152b149175c5b4203caf039a39caaba8e95ba"
    )
    assert (
        digest([[asdict(page) for page in layout_appendix(model)] for model in models])
        == "ae89df753cc2938ae9f5c78b4decfd10eba0c222396fb8eb76493ebb5d927901"
    )
    current, _, _ = appendix_view.build_appendix_views(fixture())
    old_observations = next(model for model in models if model["id"] == "EX-APPENDIX-A")
    new_observations = next(model for model in current if model["id"] == "EX-APPENDIX-A")
    assert len(layout_appendix(new_observations)) < len(layout_appendix(old_observations)) / 2
