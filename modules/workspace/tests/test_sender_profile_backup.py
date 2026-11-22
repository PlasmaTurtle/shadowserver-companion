"""Workspace transfers preserve unfinished identity but reject corrupted pins."""

from copy import deepcopy
import json

import pytest

from tests.support.workbench import app, client, import_rows, observations
from modules.settings.components.sender_identity import capture_profile, validate_saved_profile
from modules.workspace.components.workspace_data import export_workspace


@pytest.mark.parametrize("profile", [None, {}, capture_profile({})])
def test_legacy_and_unfinished_sender_profiles_remain_valid_for_transfer(profile):
    validate_saved_profile({"sender_profile": profile})


def test_workspace_export_rejects_corrupt_sender_pins_without_rewriting_case(client, app):
    import_rows(client, app, [{**observations()[0], "ip": "8.8.8.8"}])
    store = app.state.store
    case = store.one("SELECT id,draft FROM cases")
    draft = json.loads(case["draft"])
    valid = draft["sender_profile"]
    invalid = [
        [],
        "broken",
        {**valid, "revision": "unknown"},
        {**valid, "agency": []},
        {**valid, "unrecognized": "field"},
        {**valid, "analyst_name": "A" * 301},
        {**valid, "office": "Office\nSecond line"},
    ]
    for profile in invalid:
        changed = {**deepcopy(draft), "sender_profile": profile}
        with store.transaction() as db:
            db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(changed), case["id"]))
        before = store.one("SELECT * FROM cases WHERE id=?", (case["id"],))
        with pytest.raises(ValueError, match="Saved sender profile is invalid"):
            export_workspace(store)
        assert store.one("SELECT * FROM cases WHERE id=?", (case["id"],)) == before
    # Empty required fields are normal unfinished work, not corrupt backup data.
    changed["sender_profile"] = capture_profile({})
    with store.transaction() as db:
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(changed), case["id"]))
    archive = export_workspace(store)
    archive.unlink()
