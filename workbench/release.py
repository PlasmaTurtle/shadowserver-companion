"""Release identity is independent of case data and automated test results."""

from datetime import date, datetime
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def installation_identity(edition="standard", variant=""):
    """Allowlisted per-user identities; omitted variants retain historical homes."""
    if not isinstance(edition, str) or edition not in {"standard", "chaos"}:
        raise ValueError("Unknown application edition")
    if not isinstance(variant, str) or variant not in {"", "dark_matter"}:
        raise ValueError("Unknown application variant")
    if variant and edition != "chaos":
        raise ValueError("DarkMatter requires its existing installation identity")
    if variant == "dark_matter":
        app_id, app_name, port = (
            "ShadowserverCompanionDarkMatter",
            "Shadowserver Eclipse",
            8881,
        )
    elif edition == "chaos":
        app_id, app_name, port = "ShadowserverCompanionChaos", "Shadowserver Companion Chaos", 8879
    else:
        app_id, app_name, port = "OutreachWorkbench", "Shadowserver Companion", 8877
    return {
        "app_id": app_id,
        "app_name": app_name,
        "running_mutex": f"Local\\{app_id}.Installed.Running",
        "port": port,
        "demo_port": port + 1,
    }


def validate_workspace_identity(workspace, local_app_data, *, edition="standard", variant=""):
    """Never open another installed identity's managed data through an override."""
    identity = installation_identity(edition, variant)
    if not local_app_data:
        return
    workspace = Path(workspace).resolve()
    local = Path(local_app_data).resolve()
    for other in (
        "OutreachWorkbench",
        "ShadowserverCompanionChaos",
        "ShadowserverCompanionDarkMatter",
    ):
        if other != identity["app_id"] and workspace.is_relative_to((local / other).resolve()):
            raise ValueError(
                identity["app_name"] + " cannot open another installation's data. "
                "Export a backup in the other installation and import that copy from Settings > Data."
            )


def load_release(root=ROOT):
    """A stable label requires explicit, version-specific home confirmation.

    Build tools validate the same file that the runtime reads. Verification
    never writes it. Missing or inconsistent metadata is an error, not an
    implicit stable release.
    """
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    data = json.loads((root / "RELEASE.json").read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema") != 1
        or not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or data.get("version") != version
        or data.get("channel") not in {"unstable", "candidate", "stable"}
    ):
        raise ValueError("Release metadata must match VERSION and declare its release channel")
    confirmation = data.get("home_confirmation")
    if confirmation is not None:
        if (
            not isinstance(confirmation, dict)
            or confirmation.get("version") != version
            or not all(
                isinstance(confirmation.get(k), str) and confirmation[k].strip()
                for k in ("confirmed_by", "confirmed_at", "notes")
            )
        ):
            raise ValueError("Home confirmation must identify this version, author, date and notes")
        stamp = datetime.fromisoformat(confirmation["confirmed_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Home confirmation requires a timestamp with a timezone")
    if data["channel"] == "stable" and confirmation is None:
        raise ValueError("Stable promotion requires explicit home confirmation for this version")
    # A confirmed previous Windows release is useful compatibility evidence, but
    # must never masquerade as native acceptance of newly changed code.
    baseline = data.get("windows_baseline")
    if baseline is not None:
        if (
            not isinstance(baseline, dict)
            or not isinstance(baseline.get("version"), str)
            or not re.fullmatch(r"\d+\.\d+\.\d+", baseline["version"])
            or tuple(map(int, baseline["version"].split(".")))
            >= tuple(map(int, version.split(".")))
            or not all(
                isinstance(baseline.get(key), str) and baseline[key].strip()
                for key in ("confirmed_on", "confirmed_by", "notes")
            )
        ):
            raise ValueError("Windows baseline must identify an accepted earlier version")
        date.fromisoformat(baseline["confirmed_on"])
    review_name = data.get("review_name", "")
    if not isinstance(review_name, str) or (
        review_name and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]{0,63}", review_name)
    ):
        raise ValueError("Review name must be a short plain-text release label")
    edition = data.get("edition", "standard")
    variant = data.get("variant", "")
    identity = installation_identity(edition, variant)
    if edition == "chaos" and not variant and data["channel"] != "unstable":
        raise ValueError(
            "Chaos edition must remain unstable; use the standard edition for promotion"
        )
    if variant == "dark_matter":
        label = {
            "unstable": "Development release",
            "candidate": "Release candidate",
            "stable": "Release",
        }[data["channel"]]
        display_version = version + (f" ({label})" if data["channel"] != "stable" else "")
    else:
        display_version = f"{version} ({'Chaos, ' if edition == 'chaos' else ''}{data['channel']})"
    return {
        **data,
        "edition": edition,
        "variant": variant,
        "app_name": identity["app_name"],
        "display_version": display_version,
        "validation_status": "confirmed" if confirmation else "awaiting_home_validation",
    }


def check_output_name(path, release):
    if release["channel"] == "unstable" and "unstable" not in path.name.casefold():
        raise ValueError("Unstable release filenames must include 'unstable'")
    if release["channel"] == "candidate" and not re.search(
        r"(?:^|[-_.])(?:rc|candidate)(?:[-_.]|$)", path.name.casefold()
    ):
        raise ValueError("Release candidate filenames must include 'rc' or 'candidate'")
    if (
        release.get("edition") == "chaos"
        and not release.get("variant")
        and "chaos" not in path.name.casefold()
    ):
        raise ValueError("Chaos release filenames must include 'chaos'")

    normalized = re.sub(r"[-_\s]", "", path.name.casefold())
    if release.get("variant") == "dark_matter" and not any(
        label in normalized for label in ("shadowservereclipse", "darkmatter")
    ):
        raise ValueError("DarkMatter release filenames must identify Shadowserver Eclipse")
