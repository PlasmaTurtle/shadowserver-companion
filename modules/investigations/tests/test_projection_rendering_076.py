"""Content locks stay renderer-free; historical artwork stays hash-verified."""

from tests.filesystem_helpers import create_test_symlink

from copy import deepcopy
from hashlib import sha256
import json
from modules.workspace.components import compact_json
from time import perf_counter

import pytest

from tests.support.workbench import app, client, import_rows
from modules.ui.components import exhibit_rendering
from modules.investigations.components.services import notification_views


def case(client, app):
    import_rows(client, app)
    identifier = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + identifier).json()


def test_editable_case_get_and_save_never_generate_raster_masters(client, app, monkeypatch):
    monkeypatch.setattr(
        exhibit_rendering, "png", lambda *args: pytest.fail("Case projection generated a PNG")
    )
    started = perf_counter()
    lead = case(client, app)
    assert not any("rendered_masters" in e for e in lead["report_model"]["exhibits"])
    assert all(r["status"] == "draft" for r in lead["section_reviews"])
    fields = deepcopy(lead["draft"])
    fields["notes"] = "Administrative update"
    saved = client.put(
        f"/api/leads/{lead['id']}/draft",
        json={"expected_revision": lead["draft_revision"], "fields": fields},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft"]["notes"] == "Administrative update"
    print(f"\nEditable import/get/save: {perf_counter() - started:.3f}s")


def test_freeze_retains_content_without_artwork_and_get_reuses_it(client, app, monkeypatch):
    lead = case(client, app)
    rasterized = []
    original = exhibit_rendering.png

    def counted(page):
        rasterized.append(page.id)
        return original(page)

    monkeypatch.setattr(exhibit_rendering, "png", counted)
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 200, response.text
    assert rasterized == []
    frozen = next(r for r in response.json()["section_reviews"] if r["key"] == "closing")
    assert frozen["status"] == "validated"
    record = app.state.store.one(
        "SELECT * FROM section_validations WHERE id=?", (frozen["validation_id"],)
    )
    saved = compact_json.loads(record["snapshot_json"])
    assert (
        sha256(
            json.dumps(
                saved["snapshot"], sort_keys=True, ensure_ascii=False, default=str, allow_nan=False
            ).encode()
        ).hexdigest()
        == record["content_hash"]
    )
    assert saved["fingerprint_version"] == 2
    assert frozen["snapshot"] == saved["snapshot"]
    assert saved["snapshot"]["exhibits"]
    assert all("rendered_masters" not in model for model in saved["snapshot"]["exhibits"])
    assert "exhibit_masters" not in saved["snapshot"]

    monkeypatch.setattr(
        exhibit_rendering, "png", lambda *args: pytest.fail("Frozen PNG was rebuilt")
    )
    for name in (
        "layout_closing",
        "layout_appendix",
        "layout_vulnerabilities",
        "layout_attribution",
        "layout_information",
    ):
        monkeypatch.setattr(
            exhibit_rendering,
            name,
            lambda *args: pytest.fail("Projection laid out an unrelated or frozen exhibit"),
        )
    sizes = []
    original_projection = notification_views._editor_artwork_metadata

    def measured_projection(value):
        if isinstance(value, dict) and "case_id" in value and "section_reviews" in value:
            sizes.append(len(json.dumps(value).encode()))
        return original_projection(value)

    monkeypatch.setattr(notification_views, "_editor_artwork_metadata", measured_projection)
    started = perf_counter()
    repeated = client.get(f"/api/cases/{lead['case_id']}")
    elapsed = perf_counter() - started
    assert repeated.status_code == 200, repeated.text
    actual = next(r for r in repeated.json()["section_reviews"] if r["key"] == "closing")
    assert actual["status"] == "validated"
    assert actual["snapshot"] == frozen["snapshot"]
    # Content-only reviews no longer contain megabytes of artwork to strip.
    # The HTTP representation remains a compact serialization of the same data.
    assert repeated.json() == notification_views._editor_artwork_metadata(repeated.json())
    assert len(repeated.content) <= sizes[0]
    assert (
        app.state.store.one(
            "SELECT snapshot_json FROM section_validations WHERE id=?", (frozen["validation_id"],)
        )["snapshot_json"]
        == record["snapshot_json"]
    )
    print(
        f"\nFrozen GET: {elapsed:.3f}s; full projection {sizes[0]:,} bytes; "
        f"wire projection {len(repeated.content):,} bytes"
    )


@pytest.mark.parametrize("legacy_artwork", [False, True])
def test_historical_editor_preserves_complete_certified_snapshot(client, app, legacy_artwork):
    from modules.investigations.components.report_snapshot import snapshot
    from modules.workspace.components.primitives import now

    lead = case(client, app)
    if legacy_artwork:
        from modules.investigations.components.reviews.policy import fingerprints
        from modules.investigations.components.repositories.reviews import SectionReviewRepository

        legacy = snapshot(
            app.state.store,
            lead["id"],
            lead["case_id"],
            include_reviews=False,
            capture_sections=("closing",),
        )
        frozen = fingerprints(legacy, lead, sections=("closing",), version=1)["closing"]
        with app.state.store.transaction() as db:
            SectionReviewRepository(app.state.store).save_validation(
                db, lead["case_id"], "closing", "Earlier Analyst", frozen
            )
    else:
        response = client.post(
            f"/api/cases/{lead['case_id']}/sections/closing/validate",
            json={"expected_revision": lead["draft_revision"]},
        )
        assert response.status_code == 200, response.text
    # Exercise both original artwork-bearing review archives and new content
    # records. Certification has separate end-to-end output coverage.
    data = snapshot(app.state.store, lead["id"], lead["case_id"], capture_sections=())
    raw = json.dumps(data).encode()
    checksum = sha256(raw).hexdigest()
    folder = app.state.store.path("reports/projection-history")
    folder.mkdir(parents=True)
    (folder / "snapshot.json").write_bytes(raw)
    (folder / "manifest.json").write_text(json.dumps({"files": {"snapshot.json": checksum}}))
    with app.state.store.transaction() as db:
        db.execute(
            "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                "projection-history",
                lead["id"],
                lead["id"],
                lead["case_id"],
                1,
                now(),
                "reports/projection-history",
            ),
        )
        from modules.investigations.components.artifact_registry import register_artifact

        register_artifact(db, app.state.store.root, "report", "projection-history", legacy=True)
        db.execute(
            "UPDATE cases SET certified_report_id=?,stage='pending_notification' WHERE id=?",
            ("projection-history", lead["case_id"]),
        )
    shown = client.get(f"/api/cases/{lead['case_id']}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["historical_report"]["snapshot_verified"] is True
    if legacy_artwork:
        assert len(shown.content) < len(raw) / 10
    else:
        assert len(shown.content) <= len(raw)
    assert (folder / "snapshot.json").read_bytes() == raw
    assert sha256((folder / "snapshot.json").read_bytes()).hexdigest() == checksum
    retained = json.loads(raw)
    artwork = [e for e in retained["composition"]["exhibits"] if "rendered_masters" in e]
    if legacy_artwork:
        assert artwork and all(exhibit_rendering.prepared_pages(e) for e in artwork)
        shown_models = shown.json()["report_model"]["exhibits"]
        projected = [e for e in shown_models if "rendered_masters" in e]
        assert projected
        for model in projected:
            assert model["rendered_masters"]["metadata_only"] is True
            assert all(
                "png" not in page and page["png_sha256"]
                for page in model["rendered_masters"]["pages"]
            )
            with pytest.raises(ValueError, match="full verified snapshot"):
                exhibit_rendering.prepared_pages(model)
    else:
        assert artwork == []


def missing_rendered_package(client, app, modern):
    """Retain verified historical content after a rendered member is lost."""
    from modules.investigations.components.report_snapshot import snapshot
    from modules.workspace.components.primitives import now

    lead = case(client, app)
    data = snapshot(app.state.store, lead["id"], lead["case_id"], capture_sections=())
    raw = json.dumps(data).encode()
    folder = app.state.store.path("reports/snapshot-recovery")
    folder.mkdir(parents=True)
    (folder / "snapshot.json").write_bytes(raw)
    (folder / "notification.docx").write_bytes(b"Synthetic retained DOCX")
    manifest = {
        "files": {
            "snapshot.json": sha256(raw).hexdigest(),
            "notification.pdf": sha256(b"Synthetic missing PDF").hexdigest(),
            "notification.docx": sha256(b"Synthetic retained DOCX").hexdigest(),
        }
    }
    if modern:
        manifest.update(
            schema_version=4,
            report_id="snapshot-recovery",
            case_id=lead["case_id"],
            entity_id=lead["id"],
            notification_id=lead["case_id"],
            revision=1,
        )
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with app.state.store.transaction() as db:
        db.execute(
            "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path,certification_source) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                "snapshot-recovery",
                lead["id"],
                lead["id"],
                lead["case_id"],
                1,
                now(),
                "reports/snapshot-recovery",
                "analyst" if modern else "legacy_finalized",
            ),
        )
        from modules.investigations.components.artifact_registry import register_artifact

        register_artifact(db, app.state.store.root, "report", "snapshot-recovery", legacy=True)
        db.execute(
            "UPDATE cases SET certified_report_id=?,stage='pending_notification' WHERE id=?",
            ("snapshot-recovery", lead["case_id"]),
        )
    return lead, folder, manifest, data


@pytest.mark.parametrize("modern", [False, True])
def test_missing_pdf_preserves_verified_historical_view_without_authorizing_delivery(
    client, app, modern
):
    lead, folder, _, _ = missing_rendered_package(client, app, modern)
    before = (folder / "snapshot.json").read_bytes()
    report = app.state.store.one("SELECT * FROM reports WHERE id='snapshot-recovery'")
    shown = client.get(f"/api/cases/{lead['case_id']}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["historical_report"]["snapshot_verified"] is True
    assert not app.state.store.package_available(report)
    assert client.get("/api/reports/snapshot-recovery/pdf").status_code == 409
    # Snapshot verification never enters the full-package cache, even in one
    # shared verification operation.
    from modules.investigations.components.package_integrity import verification_scope

    with verification_scope():
        app.state.store.artifacts.snapshot_inventory(report)
        assert not app.state.store.package_available(report)
    assert (folder / "snapshot.json").read_bytes() == before


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("damage", ["binding", "snapshot-digest", "snapshot-case"])
def test_partial_historical_view_still_checks_identity_and_snapshot(client, app, modern, damage):
    lead, folder, manifest, data = missing_rendered_package(client, app, modern)
    if damage == "binding":
        manifest["report_id" if modern else "notification_id"] = "another-identity"
    elif damage == "snapshot-digest":
        (folder / "snapshot.json").write_bytes((folder / "snapshot.json").read_bytes() + b" ")
    else:
        data["case_id"] = "another-case"
        raw = json.dumps(data).encode()
        (folder / "snapshot.json").write_bytes(raw)
        manifest["files"]["snapshot.json"] = sha256(raw).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest))
    shown = client.get(f"/api/cases/{lead['case_id']}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["historical_report"]["snapshot_verified"] is False
    assert shown.json()["report_model"]["exhibits"] == []


@pytest.mark.parametrize(
    "damage", ["null-digest", "duplicate-manifest", "identity-downgrade", "link"]
)
def test_partial_historical_snapshot_cannot_bypass_manifest_or_path_validation(client, app, damage):
    lead, folder, manifest, _ = missing_rendered_package(client, app, modern=True)
    if damage == "null-digest":
        manifest["files"]["snapshot.json"] = None
    elif damage == "identity-downgrade":
        manifest = {"files": manifest["files"]}
    elif damage == "link":
        source = folder.parent / "outside-snapshot.json"
        (folder / "snapshot.json").rename(source)
        create_test_symlink(folder / "snapshot.json", source)
    serialized = json.dumps(manifest)
    if damage == "duplicate-manifest":
        serialized = '{"files": {},' + serialized[1:]
    (folder / "manifest.json").write_text(serialized)
    shown = client.get(f"/api/cases/{lead['case_id']}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["historical_report"]["snapshot_verified"] is False


def test_uncaptured_svg_projection_never_creates_png(monkeypatch):
    from modules.investigations.tools.preview_introduction import specimen
    from modules.investigations.components.report_composition import compose
    from modules.investigations.components.vulnerability_model import REVISION

    data = specimen(1)
    data["draft"]["vulnerability_revision"] = REVISION
    model = next(e for e in compose(data)["exhibits"] if e["id"] == "EX-VULNERABILITY")
    monkeypatch.setattr(
        exhibit_rendering, "png", lambda *args: pytest.fail("SVG-only operation generated a PNG")
    )
    result = exhibit_rendering.svg_pages(model)
    assert result and all("<svg" in svg for svg in result)
    assert "rendered_masters" not in model


def test_lightweight_capture_still_rejects_corrupted_frozen_artifact():
    from modules.investigations.tools.preview_vulnerabilities import specimen

    data = specimen()
    frozen = next(e for e in data["composition"]["exhibits"] if e["id"] == "EX-VULNERABILITY")
    current = deepcopy(frozen)
    current.pop("rendered_masters")
    frozen["rendered_masters"]["pages"][0]["png_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="artifact integrity"):
        exhibit_rendering.capture_exhibit_masters({"exhibits": [current]}, [frozen], sections=())
