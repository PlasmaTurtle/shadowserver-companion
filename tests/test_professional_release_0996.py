"""Release wording must not change installed identity or invent acceptance."""

import copy
import json
from pathlib import Path

import pytest

from modules.workspace.components.release import (
    check_output_name,
    installation_identity,
    load_release,
)


def metadata(tmp_path, **changes):
    data = {
        "schema": 1,
        "version": "0.9.96",
        "channel": "candidate",
        "edition": "chaos",
        "variant": "dark_matter",
        "review_name": "Professional Review",
        "home_confirmation": None,
        "windows_baseline": {
            "version": "0.9.95",
            "confirmed_on": "2026-11-12",
            "confirmed_by": "Synthetic operator",
            "notes": "Synthetic previous-version acceptance",
        },
    }
    data.update(changes)
    (tmp_path / "VERSION").write_text(data["version"])
    (tmp_path / "RELEASE.json").write_text(json.dumps(data))
    return data


def test_candidate_preserves_existing_install_identity_and_separates_acceptance(tmp_path):
    metadata(tmp_path)
    release = load_release(tmp_path)
    assert release["display_version"] == "0.9.96 (Release candidate)"
    assert release["validation_status"] == "awaiting_home_validation"
    assert release["home_confirmation"] is None
    assert release["windows_baseline"]["version"] == "0.9.95"
    identity = installation_identity(release["edition"], release["variant"])
    assert identity["app_id"] == "ShadowserverCompanionDarkMatter"
    assert identity["running_mutex"] == "Local\\ShadowserverCompanionDarkMatter.Installed.Running"
    assert (identity["port"], identity["demo_port"]) == (8881, 8882)
    check_output_name(Path("Companion-0.9.96-darkmatter-professional-review-rc.exe"), release)
    with pytest.raises(ValueError, match="candidate filenames"):
        check_output_name(Path("Companion-0.9.96-darkmatter.exe"), release)


def test_accepted_baseline_cannot_promote_changed_version(tmp_path):
    data = metadata(tmp_path, channel="stable")
    with pytest.raises(ValueError, match="explicit home confirmation"):
        load_release(tmp_path)
    data["home_confirmation"] = {
        "version": "0.9.95",
        "confirmed_by": "Synthetic operator",
        "confirmed_at": "2026-11-12T12:00:00-05:00",
        "notes": "Synthetic acceptance",
    }
    (tmp_path / "RELEASE.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identify this version"):
        load_release(tmp_path)
    data["home_confirmation"]["version"] = "0.9.96"
    (tmp_path / "RELEASE.json").write_text(json.dumps(data))
    release = load_release(tmp_path)
    assert release["channel"] == "stable"
    assert release["validation_status"] == "confirmed"
    assert release["display_version"] == "0.9.96"
    assert release["app_name"] == "Shadowserver Eclipse"
    check_output_name(Path("Companion-0.9.96-darkmatter.exe"), release)


@pytest.mark.parametrize("bad", [None, [], "", "0.9.96", "1.0.0", "../0.9.95"])
def test_baseline_requires_valid_earlier_version(tmp_path, bad):
    data = metadata(tmp_path)
    baseline = copy.deepcopy(data["windows_baseline"])
    baseline["version"] = bad
    metadata(tmp_path, windows_baseline=baseline)
    with pytest.raises(ValueError, match="earlier version"):
        load_release(tmp_path)


@pytest.mark.parametrize("bad", [None, [], 'Review"', "Review\nInjected", "X" * 65])
def test_review_label_cannot_inject_installer_or_document_content(tmp_path, bad):
    metadata(tmp_path, review_name=bad)
    with pytest.raises(ValueError, match="short plain-text"):
        load_release(tmp_path)
