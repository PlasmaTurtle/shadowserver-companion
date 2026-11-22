"""Regression coverage for report stalls, atomic freezes and bounded preparation."""

from threading import Event, Thread
from copy import deepcopy
import json
import subprocess
import sys

import pytest

from tests.support.workbench import app, client, import_rows
from modules.ui.components import exhibit_rendering, vector_layout
from modules.investigations.components.report_operations import ReportOperations, check_deadline


def opened(client, app):
    import_rows(client, app)
    identifier = client.get("/api/leads").json()[0]["id"]
    return client.get("/api/leads/" + identifier).json()


def test_long_unbroken_raw_values_wrap_with_linear_measuring_work(monkeypatch):
    measured = 0
    width = vector_layout.text_width

    def counted(value, font, size):
        nonlocal measured
        measured += len(value)
        return width(value, font, size)

    monkeypatch.setattr(vector_layout, "text_width", counted)
    value = "x" * 100_000
    lines = vector_layout._wrap(value, 290)
    assert "".join(lines) == value
    assert all(width(line, "ExhibitSans", 10) <= 290 for line in lines)
    # Counts work rather than enforcing a wall-clock bound on shared CI. The
    # previous whole-tail loop measured >100M characters for this input.
    assert measured < 20 * len(value)


def legacy_wrap(value, width, size=10, bold=False):
    font = "ExhibitSans-Bold" if bold else "ExhibitSans"
    result = []
    for paragraph in vector_layout._value(value).split("\n"):
        current = ""
        for word in paragraph.split(" "):
            candidate = current + (" " if current else "") + word
            if vector_layout.text_width(candidate, font, size) <= width:
                current = candidate
                continue
            if current:
                result.append(current)
                current = ""
            while word and vector_layout.text_width(word, font, size) > width:
                cut = 1
                while (
                    cut < len(word)
                    and vector_layout.text_width(word[: cut + 1], font, size) <= width
                ):
                    cut += 1
                result.append(word[:cut])
                word = word[cut:]
            current = word
        result.append(current)
    return result or [""]


@pytest.mark.parametrize("bold", [False, True])
def test_optimized_wrap_preserves_existing_line_breaks(bold):
    for width in (1, 35, 170, 290, 489.6):
        for value in (
            "",
            "  Multiple  spaces\nnext line",
            "x" * 501,
            "参考資料 日本語 example",
            "https://example.com/" + "/long-record-name" * 30,
        ):
            assert vector_layout._wrap(value, width, 10.5, bold) == legacy_wrap(
                value, width, 10.5, bold
            )


@pytest.mark.parametrize("kind", ["compact", "prose", "table"])
def test_oversized_appendix_context_fails_promptly_instead_of_looping(kind):
    # Run in a killable child: a regression must fail the test, never hang pytest.
    source = """
from modules.investigations.components.appendix_layout import AppendixLayout, BOTTOM, LEADING, PAD
x = AppendixLayout({'id': 'X'})
x.current_record = {'id': 'r', 'title': 'Source record', 'label': 'A1', 'kind_label': 'Observation', 'citations': []}
x.current_group = {'title': 'Nested source group', 'path': '/field/' * 900}
x.y = 607
try:
    if KIND == 'compact':
        x.compact_fields({'fields': [{'label': 'value', 'path': '/value', 'text': 'Preserved content'}]})
    elif KIND == 'prose':
        x.fields({'fields': [{'label': 'value', 'path': '/description', 'text': 'source value ' * 100, 'value_type': 'string'}]})
    else:
        x.current_group['path'] = '/fields'
        x.new_page()
        available = int((BOTTOM - x.y - 24 - 2 * PAD) // LEADING)
        x.fields({'fields': [{'label': '\\n'.join(['label'] * available), 'path': '/value', 'text': '\\n'.join(['value'] * 100), 'value_type': 'array'}]})
except ValueError as error:
    assert 'Appendix' in str(error)
    print('bounded failure:', error)
else:
    raise AssertionError('Oversized repeated context was not rejected')
""".replace("KIND", repr(kind))
    result = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr
    assert "bounded failure:" in result.stdout


def test_draft_pdf_preview_does_not_create_unused_raster_masters(client, app, monkeypatch):
    lead = opened(client, app)
    monkeypatch.setattr(
        exhibit_rendering, "png", lambda *args: pytest.fail("PDF preview rasterized a page")
    )
    response = client.get(f"/api/leads/{lead['id']}/preview.pdf?case_id={lead['case_id']}")
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")
    assert not app.state.report_operations.busy()


def test_freeze_content_check_releases_writer_lock_and_rechecks_revision(client, app, monkeypatch):
    lead = opened(client, app)
    store = app.state.store
    from modules.investigations.components.services import reviews as review_service

    original = review_service.fingerprints
    changed = False

    def capture(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True

            def concurrent_write():
                with store.transaction() as db:
                    db.execute(
                        "UPDATE cases SET draft_revision=draft_revision+1 WHERE id=?",
                        (lead["case_id"],),
                    )

            completed = Event()

            def run_write():
                concurrent_write()
                completed.set()

            writer = Thread(target=run_write, daemon=True)
            writer.start()
            assert completed.wait(2), "Content preparation held the workspace writer lock"
            writer.join(timeout=2)
        return original(*args, **kwargs)

    monkeypatch.setattr(review_service, "fingerprints", capture)
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 422, response.text
    assert not store.all("SELECT * FROM section_validations WHERE case_id=?", (lead["case_id"],))
    assert not app.state.report_operations.busy()


def test_freeze_rechecks_dependencies_without_draft_revision_change(client, app, monkeypatch):
    lead = opened(client, app)
    store = app.state.store
    # Legacy drafts still depend on current sender settings. Current drafts
    # intentionally pin identity, so use a genuine pre-profile draft to prove
    # that freeze rechecks mutable dependencies without a draft revision change.
    with store.transaction() as db:
        row = db.execute("SELECT draft FROM cases WHERE id=?", (lead["case_id"],)).fetchone()
        draft = json.loads(row["draft"])
        draft.pop("sender_profile", None)
        db.execute("UPDATE cases SET draft=? WHERE id=?", (json.dumps(draft), lead["case_id"]))
    from modules.investigations.components.services import reviews as review_service

    original = review_service.fingerprints
    changed = False

    def capture(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            with store.transaction() as db:
                profile = deepcopy(store.settings())
                profile["analyst_name"] = "Changed while checking"
                db.execute(
                    "UPDATE settings SET value=? WHERE key='profile'", (json.dumps(profile),)
                )
        return result

    monkeypatch.setattr(review_service, "fingerprints", capture)
    response = client.post(
        f"/api/cases/{lead['case_id']}/sections/closing/validate",
        json={"expected_revision": lead["draft_revision"]},
    )
    assert response.status_code == 422, response.text
    assert "changed while" in response.json()["detail"]
    assert not store.all("SELECT * FROM section_validations WHERE case_id=?", (lead["case_id"],))


def test_report_deadline_and_duplicate_admission_release_activity():
    operations = ReportOperations()
    with pytest.raises(ValueError, match="time limit"):
        with operations.run("case", "preview", timeout=-1):
            assert operations.busy()
            check_deadline()
    assert not operations.busy()
    with operations.run("case", "freeze"):
        with pytest.raises(Exception, match="already running"):
            with operations.run("case", "preview"):
                pytest.fail("Concurrent report action was admitted")
    assert not operations.busy()


def test_pdf_geometry_path_preserves_identical_draft_and_frozen_pdf_bytes(
    client, app, monkeypatch, tmp_path
):
    from reportlab import rl_config
    from modules.investigations.components.report_snapshot import snapshot
    from modules.investigations.components import report_renderers

    lead = opened(client, app)
    data = snapshot(app.state.store, lead["id"], lead["case_id"], capture_sections=())
    monkeypatch.setattr(rl_config, "invariant", 1)
    current_path, legacy_path, frozen_path = (
        tmp_path / name for name in ("current.pdf", "legacy.pdf", "frozen.pdf")
    )
    report_renderers.render_pdf(data, current_path, app.state.store.root, draft=True)
    frozen = deepcopy(data)
    exhibit_rendering.capture_exhibit_masters(frozen["composition"])
    report_renderers.render_pdf(frozen, frozen_path, app.state.store.root, draft=True)
    original_layout = report_renderers.exhibit_layout

    def legacy_geometry(exhibit, policy=None):
        if exhibit_rendering.is_page_exhibit(exhibit):
            return [rendered.page for rendered in exhibit_rendering.prepared_pages(exhibit)]
        return original_layout(exhibit, policy)

    monkeypatch.setattr(report_renderers, "exhibit_layout", legacy_geometry)
    report_renderers.render_pdf(frozen, legacy_path, app.state.store.root, draft=True)
    assert current_path.read_bytes() == legacy_path.read_bytes() == frozen_path.read_bytes()
