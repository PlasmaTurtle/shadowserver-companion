"""Feature request contracts are usable without loading another module's interface."""

import json
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize(
    "owner,model,payload,field,expected",
    [
        (
            "attribution",
            "AttributionReviewValues",
            {"result_id": "a" * 32, "decision": "accept"},
            "decision",
            "accept",
        ),
        ("accretion", "GroupRetryValues", {}, "result_id", None),
        (
            "entities",
            "EntityRename",
            {"name": "  Example  ", "expected_revision": 1},
            "name",
            "Example",
        ),
        ("settings", "SettingsUpdate", {"regions": [" NC ", "NC"]}, "regions", ["North Carolina"]),
        ("library", "SourceJobRequest", {"cve_ids": ["CVE-2026-1234"]}, "refresh", False),
        ("investigations", "CaseCreate", {"entity_id": "example"}, "title", ""),
    ],
)
def test_owned_request_contract_works_without_other_feature_modules(
    owner, model, payload, field, expected
):
    root = Path(__file__).resolve().parents[1]
    program = textwrap.dedent(
        """
        import importlib
        import json
        import sys

        root, owner, model, payload, field = sys.argv[1:]
        class OtherFeaturesUnavailable:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith("modules.") and fullname.split(".")[1] != owner:
                    raise ImportError("Request contract loaded another feature: " + fullname)
        sys.path.insert(0, root)
        sys.meta_path.insert(0, OtherFeaturesUnavailable())
        contract = getattr(importlib.import_module(f"modules.{owner}.components.api_models"), model)
        print(json.dumps(contract.model_validate(json.loads(payload)).model_dump(mode="json")[field]))
        """
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", program, str(root), owner, model, json.dumps(payload), field],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == expected
