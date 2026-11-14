"""Independent network-to-evidence regressions using inert, offline responses.

The fixture strings are markers, not malware samples. Nothing here makes a
network request or opens a browser. These tests exercise the user-facing contact
workflow rather than only the decoder or serializer implementation.
"""

from contextlib import closing

from copy import deepcopy
import hashlib
import json
import sqlite3
from zipfile import ZipFile

import pytest

from test_contacts_invariants_090 import attributed_entity
from workbench.cases import Cases
from workbench.contact_discovery import ContactDiscovery, FetchResponse
from workbench.contact_records import ContactRecords
from workbench.store import Store

ROOT = "https://example.com/"
MARKER = "INERT_EXTERNAL_SCRIPT_MARKER_0998"
SCRIPT_URL = "https://scripts.invalid/fixture-only.js"
CONTACT = "security@example.com"


class OfflineFetcher:
    def __init__(self, body, *, status=200, media="text/html; charset=utf-8"):
        self.body, self.status, self.media = body, status, media
        self.calls = []

    def fetch(self, url, *, timeout, max_bytes, cancel_event=None):
        self.calls.append(url)
        if url == ROOT:
            return FetchResponse(self.status, {"content-type": self.media}, self.body)
        return FetchResponse(404, {"content-type": "text/plain"}, b"")


def run_and_save(tmp_path, body, *, status=200, media="text/html; charset=utf-8"):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    records = ContactRecords(store)
    fetcher = OfflineFetcher(body, status=status, media=media)
    result = ContactDiscovery(fetcher=fetcher).discover("example.com")
    records.save_run(records.scope(entity["id"]), result)
    return store, entity, records, result, fetcher


def retained_payloads(store):
    values = []
    for table in ("contact_runs", "contact_candidates", "contact_sources"):
        values.extend(row["payload"] for row in store.all(f"SELECT payload FROM {table}"))
    values.extend(
        p.read_text(encoding="utf-8")
        for p in (store.root / "evidence" / "contact-discovery").rglob("*")
        if p.is_file()
    )
    return "\n".join(values)


def test_contact_value_survives_without_retaining_website_code(tmp_path):
    body = (
        f'<html><head><script src="{SCRIPT_URL}">{MARKER}</script></head>'
        f'<body><p>Security contact <a href="mailto:{CONTACT}">{CONTACT}</a></p>'
        f"<iframe>{MARKER}</iframe><!-- {MARKER} --></body></html>"
    ).encode()
    store, entity, records, result, fetcher = run_and_save(tmp_path, body)
    assert any(c["value"] == CONTACT for c in result["candidates"])
    assert SCRIPT_URL not in fetcher.calls
    assert all("body" not in s for s in result["snapshots"])
    saved = json.loads(store.all("SELECT payload FROM contact_runs")[0]["payload"])
    response = next(s for s in saved["snapshots"] if s["url"] == ROOT)
    assert response["sha256"] == hashlib.sha256(body).hexdigest()
    assert response["retention"] == "contact-extract-v1"
    artifact = store.path(response["path"]).read_bytes()
    assert response["artifact_sha256"] == hashlib.sha256(artifact).hexdigest()
    assert response["artifact_sha256"] != response["sha256"]
    assert response["path"].endswith(".contact.json")
    retained = retained_payloads(store)
    assert CONTACT in retained
    assert MARKER not in retained
    assert SCRIPT_URL not in retained
    assert "<script" not in retained.lower()
    archive_path = records.export(entity["id"])
    try:
        with ZipFile(archive_path) as archive:
            contents = b"\n".join(archive.read(n) for n in archive.namelist())
            assert MARKER.encode() not in contents
            assert SCRIPT_URL.encode() not in contents
            assert CONTACT.encode() in contents
            assert any(n.endswith(".contact.json") for n in archive.namelist())
    finally:
        archive_path.unlink()


@pytest.mark.parametrize(
    "status,media,body",
    [
        (503, "text/html", f"<html>{MARKER}</html>".encode()),
        (200, "application/octet-stream", f"<html>{MARKER}</html>".encode()),
        (200, "text/html", b"MZ\x00" + MARKER.encode()),
        (200, "text/html; charset=utf-8", b"\xff" + MARKER.encode()),
    ],
)
def test_unusable_response_body_never_reaches_disk_or_contact_export(tmp_path, status, media, body):
    store, entity, records, result, _ = run_and_save(tmp_path, body, status=status, media=media)
    assert result["candidates"] == []
    assert all("body" not in s for s in result["snapshots"])
    assert MARKER not in retained_payloads(store)
    saved = json.loads(store.all("SELECT payload FROM contact_runs")[0]["payload"])
    response = next(s for s in saved["snapshots"] if s["url"] == ROOT)
    assert response["sha256"] == hashlib.sha256(body).hexdigest()
    archive_path = records.export(entity["id"])
    try:
        with ZipFile(archive_path) as archive:
            assert not any(MARKER.encode() in archive.read(n) for n in archive.namelist())
    finally:
        archive_path.unlink()


def _simulate_legacy_capture(store, body, *, missing):
    """Reconstruct old on-disk format without invoking the former raw writer."""
    row = store.all("SELECT * FROM contact_runs")[0]
    run = json.loads(row["payload"])
    response = next(s for s in run["snapshots"] if s["url"] == ROOT)
    old_artifact = store.path(response["path"])
    response.pop("retention", None)
    response.pop("artifact_sha256", None)
    response.pop("derived_evidence", None)
    response.pop("evidence_kind", None)
    response["path"] = f"evidence/contact-discovery/{row['id']}/01-{response['sha256']}.body.txt"
    legacy = store.path(response["path"])
    if not missing:
        legacy.write_bytes(body)
    old_artifact.unlink()
    # The fixtures emulate a file produced by an older version. The live product
    # keeps immutable provenance triggers; temporarily remove/recreate them only
    # inside this offline fixture transaction.
    with closing(sqlite3.connect(store.db)) as db, db:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='contact_runs'"
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        db.execute("UPDATE contact_runs SET payload=? WHERE id=?", (json.dumps(run), row["id"]))
        for _, sql in triggers:
            db.execute(sql)
    return legacy


@pytest.mark.parametrize("missing", [False, True])
def test_legacy_contact_remains_usable_without_reading_or_reexporting_raw_html(
    tmp_path, missing, monkeypatch
):
    body = (
        f'<script>{MARKER}</script><p>Security contact <a href="mailto:{CONTACT}">{CONTACT}</a></p>'
    ).encode()
    store, entity, records, _, _ = run_and_save(tmp_path, body)
    legacy = _simulate_legacy_capture(store, body, missing=missing)
    before = legacy.read_bytes() if legacy.exists() else None
    candidate = records.state(entity["id"])["candidates"][0]
    case = Cases(store).create(entity["id"])

    def forbidden_refresh(*args, **kwargs):
        raise AssertionError("Missing legacy raw content must not trigger another network request")

    monkeypatch.setattr(ContactDiscovery, "discover", forbidden_refresh)
    selected = records.use(
        Cases(store),
        case["case_id"],
        candidate["id"],
        case["case"]["version"],
        candidate["revision"],
    )
    assert selected["contact_plan"]["contact_email"] == CONTACT
    archive_path = records.export(entity["id"])
    try:
        with ZipFile(archive_path) as archive:
            assert not any(MARKER.encode() in archive.read(n) for n in archive.namelist())
            assert not any(
                "contact-discovery" in n and n.endswith(".body.txt") for n in archive.namelist()
            )
    finally:
        archive_path.unlink()
    assert (legacy.read_bytes() if legacy.exists() else None) == before


def test_unknown_nested_response_fields_cannot_smuggle_bodies_into_storage(tmp_path):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    records = ContactRecords(store)
    body = f'<p>Security contact <a href="mailto:{CONTACT}">{CONTACT}</a></p>'.encode()
    result = ContactDiscovery(fetcher=OfflineFetcher(body)).discover("example.com")
    untrusted = f"<script>{MARKER}</script>"
    result["raw_html"] = untrusted
    result["snapshots"][0]["raw_html"] = untrusted
    result["snapshots"][0]["derived_evidence"] = {"raw_html": untrusted}
    result["candidates"][0]["raw_html"] = untrusted
    result["candidates"][0]["sources"][0]["raw_html"] = untrusted
    result["coverage"][0]["raw_html"] = untrusted
    result["issues"].append(
        {"code": "synthetic", "message": "No sensitive content", "raw_html": untrusted}
    )
    records.save_run(records.scope(entity["id"]), result)
    assert MARKER not in retained_payloads(store)


def test_entity_encoded_markup_is_rejected_before_any_contact_is_saved(tmp_path):
    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    records = ContactRecords(store)
    body = (
        f"<p>Security &lt;script&gt;{MARKER}&lt;/script&gt; "
        f'<a href="mailto:{CONTACT}">{CONTACT}</a></p>'
    ).encode()
    result = ContactDiscovery(fetcher=OfflineFetcher(body)).discover("example.com")
    assert result["candidates"]
    with pytest.raises(ValueError, match="plain text"):
        records.save_run(records.scope(entity["id"]), result)
    assert store.all("SELECT * FROM contact_runs") == []
    assert store.all("SELECT * FROM contact_candidates") == []
    assert not (store.root / "evidence" / "contact-discovery").exists()


@pytest.fixture
def derived_artifact(tmp_path):
    body = f'<p>Security contact <a href="mailto:{CONTACT}">{CONTACT}</a></p>'.encode()
    store, _, _, _, _ = run_and_save(tmp_path, body)
    row = store.all("SELECT * FROM contact_runs")[0]
    run = json.loads(row["payload"])
    snapshot = next(s for s in run["snapshots"] if s["url"] == ROOT)
    artifact = json.loads(store.path(snapshot["path"]).read_bytes())
    return store, row["id"], snapshot, artifact


def _replace_artifact(store, snapshot, artifact):
    raw = json.dumps(artifact, ensure_ascii=False).encode()
    store.path(snapshot["path"]).write_bytes(raw)
    snapshot["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
    snapshot["artifact_bytes"] = len(raw)


@pytest.mark.parametrize("mutation", ["kind", "url", "markup", "unknown_field", "duplicate_member"])
def test_schema_invalid_extract_rejected_even_with_matching_artifact_hash(
    derived_artifact, mutation
):
    from workbench.contact_evidence import snapshot_content

    store, run_id, snapshot, artifact = derived_artifact
    if mutation == "kind":
        artifact["contacts"][0]["kind"] = "script"
    elif mutation == "url":
        artifact["contacts"][0].update(kind="form", value="javascript:fixtureOnly()")
    elif mutation == "markup":
        artifact["contacts"][0]["excerpt"] = f"<script>{MARKER}</script>"
    elif mutation == "unknown_field":
        artifact["contacts"][0]["html"] = f"<script>{MARKER}</script>"
    _replace_artifact(store, snapshot, artifact)
    if mutation == "duplicate_member":
        raw = (
            store.path(snapshot["path"])
            .read_bytes()
            .replace(b'"schema": 1', b'"schema": 1, "schema": 1', 1)
        )
        store.path(snapshot["path"]).write_bytes(raw)
        snapshot["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        snapshot_content(store, run_id, snapshot)


@pytest.mark.parametrize(
    "key,value",
    [
        ("sha256", "not-a-sha256"),
        ("status_code", 404),
        ("retrieved_at", "2026-11-13T00:00:00"),
        ("retrieved_at", "not-a-date"),
        ("content_type", "application/octet-stream"),
        ("hash_scope", "captured_prefix"),
    ],
)
def test_contact_source_semantics_revalidated_after_artifact_hash_matches(
    derived_artifact, key, value
):
    from workbench.contact_evidence import snapshot_content

    store, run_id, snapshot, artifact = derived_artifact
    snapshot[key] = value
    artifact["source"][key] = value
    _replace_artifact(store, snapshot, artifact)
    with pytest.raises(ValueError):
        snapshot_content(store, run_id, snapshot)


def test_unknown_retention_cannot_downgrade_extract_validation(derived_artifact):
    from workbench.contact_evidence import snapshot_content

    store, run_id, snapshot, artifact = derived_artifact
    snapshot["retention"] = "unrecognized-format"
    with pytest.raises(ValueError, match="retention"):
        snapshot_content(store, run_id, snapshot)
