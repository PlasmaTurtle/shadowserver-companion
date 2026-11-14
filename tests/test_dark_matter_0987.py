"""Accretion residue is durable usable evidence, never a junk review queue."""

import hashlib

from test_workbench import app, client, import_rows, observations
from workbench.dark_matter import browse, current_records, record_observations
from workbench.awareness import associate
from workbench.store import Store, now


def imported(store, identity, source_hash="a" * 64):
    with store.transaction() as db:
        db.execute(
            "INSERT INTO imports(id,fingerprint,sha256,name,path,created_at,config) VALUES(?,?,?,?,?,?,?)",
            (identity, identity, source_hash, "sample.csv", "originals/sample.csv", now(), "{}"),
        )


def outcome(row=2, *, disposition="dark_matter", reason="below_critical", **changes):
    fields = {**observations()[0], **changes}
    return {
        "source": {"workbook": "sample.csv", "sheet": "", "row": row, "fields": fields},
        "disposition": disposition,
        "reason": reason,
    }


def test_residue_records_only_usable_local_observations_and_compact_fields(tmp_path):
    store = Store(tmp_path)
    imported(store, "first")
    rows = [
        outcome(disposition="lead", unknown_extension="DO NOT DUPLICATE"),
        outcome(3, hostname="company123.org", reason="non_com_root_excluded"),
        outcome(4, hostname=""),
        outcome(5, ip="not-an-address"),
        outcome(6, region="Virginia"),
        outcome(7, tag=""),
    ]
    with store.transaction() as db:
        result = record_observations(db, "first", "a" * 64, rows, regions=["North Carolina"])
        # Passing Filter alone does not establish admission. Model the final
        # successful qualification separately from raw intake dispositions.
        associate(db, {"source": rows[0]["source"]}, import_id="first", admitted=True)
    assert result == {"lead": 1, "dark_matter": 1, "discarded": 4}
    saved = store.all("SELECT * FROM intake_observations")
    assert len(saved) == 2
    assert all("DO NOT DUPLICATE" not in row["summary"] for row in saved)
    result = browse(store)
    assert result["total"] == 1
    assert result["items"][0]["hostname"] == "company123.org"
    assert result["items"][0]["entity_id"] is None
    assert not store.all("SELECT * FROM lead_queue")
    assert not store.all("SELECT * FROM leads")


def test_reimport_deduplicates_density_retains_policy_history_and_rescue_wins(tmp_path):
    store = Store(tmp_path)
    for key in ("first", "second", "rescued"):
        imported(store, key)
    with store.transaction() as db:
        record_observations(db, "first", "a" * 64, [outcome()], recorded_at="2026-11-11T01:00:00Z")
        record_observations(db, "second", "a" * 64, [outcome()], recorded_at="2026-11-11T02:00:00Z")
    assert browse(store)["total"] == 1
    assert browse(store)["counts"]["observations"] == 1
    assert browse(store)["counts"]["evaluations"] == 2
    assert len(store.all("SELECT * FROM intake_observations")) == 2
    with store.transaction() as db:
        record_observations(db, "rescued", "a" * 64, [outcome(disposition="lead")])
        associate(db, {"source": outcome()["source"]}, import_id="rescued", admitted=True)
    assert browse(store)["total"] == 0
    assert browse(store)["counts"]["lead"] == 1
    assert len(store.all("SELECT * FROM intake_observations")) == 3


def test_literal_search_and_page_bounds_do_not_expand_results(tmp_path):
    store = Store(tmp_path)
    imported(store, "first")
    with store.transaction() as db:
        record_observations(
            db,
            "first",
            "a" * 64,
            [outcome(i, hostname=f"mail{i}.example.com") for i in range(2, 40)],
        )
    assert browse(store, q="%")["total"] == 0
    assert browse(store, q="example.com", limit=10, offset=10)["total"] == 38
    assert len(browse(store, limit=10, offset=10)["items"]) == 10
    assert browse(store, limit=10000)["limit"] == 100


def test_intake_dark_matter_is_official_and_later_root_association_is_not_promotion(client, app):
    base = {**observations()[0], "severity": "high", "version": "PHP/7.3.25"}
    prior, original = import_rows(client, app, [base], start_notifications=False)
    field = client.get("/api/dark-matter").json()
    assert field["total"] == 1
    assert field["items"][0]["entity_id"] is None
    assert client.get("/api/pending-leads").json() == []
    import_rows(
        client,
        app,
        [{**base, "severity": "critical", "ip": "8.8.8.8", "timestamp": "2026-11-12 01:00:00"}],
        name="later.csv",
        start_notifications=False,
    )
    field = client.get("/api/dark-matter").json()
    assert field["total"] == 1
    residue = field["items"][0]
    assert residue["entity_id"]
    assert residue["association_basis"] == "Saved asset association"
    assert residue["disposition"] == "dark_matter"
    assert client.get(residue["original_url"]).content == original
    result = client.get("/api/eclipse").json()
    row = next(r for r in result["observations"] if r["source"]["import_id"] == prior["id"])
    assert row["dark_matter"] is True
    assert row["intake_disposition"] == "dark_matter"
    assert row["entity_id"] == residue["entity_id"]
    assert row["individually_attributed"] is False
    assert row["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    selected = client.get("/api/eclipse/intelligence?intake=dark_matter").json()
    assert selected["counts"]["selected_rows"] == 1
    assert client.get("/api/dark-matter?limit=101").status_code == 422
    assert client.get("/api/eclipse/intelligence?intake=invalid").status_code == 422


def test_invalid_source_rows_never_become_official_dark_matter(client, app):
    import_rows(client, app, start_notifications=False)
    field = client.get("/api/dark-matter").json()
    assert all(item["hostname"] and item["region"] == "North Carolina" for item in field["items"])
    original = client.get("/api/eclipse").json()
    assert not any(not row["hostname"] for row in original["observations"])
    assert all(row["intake_disposition"] != "unclassified" for row in original["observations"])


def test_projection_reads_only_bounded_requested_identities(tmp_path):
    store = Store(tmp_path)
    imported(store, "first")
    with store.transaction() as db:
        record_observations(db, "first", "a" * 64, [outcome(i) for i in range(2, 902)])
    ids = [
        row["observation_id"] for row in store.all("SELECT observation_id FROM intake_observations")
    ]
    with store.read_snapshot() as db:
        selected = current_records(db, ids[:500], limit=450)
    assert len(selected) == 450
    assert set(selected) == set(sorted(ids[:500])[:450])
    assert all("summary" not in row for row in selected.values())


def test_deleting_legacy_queue_memory_does_not_revoke_canonical_admission(client, app):
    import_rows(client, app, start_notifications=False)
    before = client.get("/api/eclipse").json()["observations"]
    with app.state.store.transaction() as db:
        db.execute("DELETE FROM intake_observations")
    rows = client.get("/api/eclipse").json()["observations"]
    assert [(r["id"], r["admitted"], r["entity_id"]) for r in rows] == [
        (r["id"], r["admitted"], r["entity_id"]) for r in before
    ]
    assert all(row["intake_disposition"] in {"lead", "dark_matter"} for row in rows)
