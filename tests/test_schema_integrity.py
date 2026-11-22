"""Upgrade safety, relational integrity, explicit result references and query plans."""

from tests.support.qualification import registry_factory, capture_website

import sqlite3
from contextlib import closing

import pytest

from modules.workspace.databases.migrations import SCHEMA_VERSION
from modules.workspace.components.store import Store
from modules.workspace.databases import migrations
from tests.schema_helpers import legacy_database
from tests.support.workbench import app, client, import_rows, ready
from modules.attribution.tests.support.attribution_review import review_app, accept_payload


@pytest.mark.parametrize("version,review_columns", [(0, False), (1, False), (2, False), (2, True)])
def test_legacy_upgrade_preserves_original_rows_and_is_idempotent(
    client, app, version, review_columns
):
    import_rows(client, app)
    store = app.state.store
    before = store.all("SELECT id,payload FROM entries ORDER BY rowid")
    lead_id = store.one("SELECT id FROM leads")["id"]
    legacy_database(store, version, review_columns)
    upgraded = Store(store.root)
    assert upgraded.one("PRAGMA user_version")["user_version"] == SCHEMA_VERSION
    assert upgraded.all("SELECT id,payload FROM entries ORDER BY rowid") == before
    assert upgraded.lead(lead_id)["hostnames"] == [
        {"name": "mail.example.com", "root_domain": "example.com"}
    ]
    assert "entity_id" not in {r["name"] for r in upgraded.all("PRAGMA table_info(hostnames)")}
    assert not upgraded.all("PRAGMA foreign_key_check")
    backups = list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == version
        assert db.execute("SELECT count(*) FROM entries").fetchone()[0] == len(before)
    Store(store.root)
    assert (
        list((store.root / "backups").glob(f"before-schema-{SCHEMA_VERSION}-*.sqlite3")) == backups
    )


def test_upgrade_failure_rolls_back_every_change(client, app, monkeypatch):
    import_rows(client, app)
    store = app.state.store
    legacy_database(store, 1)
    before = store.all("SELECT id,payload FROM entries ORDER BY rowid")
    original = migrations.MIGRATIONS[3]

    def fail(db):
        original(db)
        raise RuntimeError("simulated interrupted upgrade")

    monkeypatch.setitem(migrations.MIGRATIONS, 3, fail)
    with pytest.raises(RuntimeError, match="interrupted upgrade"):
        Store(store.root)
    assert store.one("PRAGMA user_version")["user_version"] == 1
    assert "merged_into" not in {r["name"] for r in store.all("PRAGMA table_info(leads)")}
    assert store.all("SELECT id,payload FROM entries ORDER BY rowid") == before


def test_future_version_rejected_before_schema_or_record_changes(client, app):
    import_rows(client, app)
    store = app.state.store
    with store.transaction() as db:
        db.execute("UPDATE imports SET status='running'")
        db.execute("PRAGMA user_version=99")
    before = store.all("SELECT * FROM imports")
    with pytest.raises(ValueError, match="Unsupported workbench database version"):
        Store(store.root)
    assert store.all("SELECT * FROM imports") == before
    assert store.one("PRAGMA user_version")["user_version"] == 99
    assert not list((store.root / "backups").iterdir())


def test_inconsistent_legacy_ownership_is_not_silently_reassigned(client, app):
    import_rows(client, app)
    store = app.state.store
    legacy_database(store)
    with closing(sqlite3.connect(store.db)) as db:
        db.execute("UPDATE hostnames SET entity_id='wrong-entity'")
        db.commit()
    with pytest.raises(ValueError, match="Conflicting hostname ownership"):
        Store(store.root)
    assert store.one("PRAGMA user_version")["user_version"] == 2
    assert store.one("SELECT entity_id FROM hostnames")["entity_id"] == "wrong-entity"


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE jobs SET status='typo'",
        "UPDATE imports SET status='typo'",
        "UPDATE leads SET status='typo'",
        "UPDATE jobs SET refresh_requested=2",
        "UPDATE leads SET demo=2",
        "UPDATE leads SET draft_revision=-1",
        "UPDATE imports SET groups_done=-1",
        "UPDATE leads SET attribution_entry_id='missing'",
        "UPDATE entries SET hostname='missing.example.com'",
        "DELETE FROM entries WHERE id IN (SELECT attribution_entry_id FROM domain_groups)",
    ],
)
def test_invalid_writes_fail_and_transaction_remains_unchanged(client, app, sql):
    import_rows(client, app)
    store = app.state.store
    store.export_all()  # Ensure normal export remains usable after rollback.
    entries = store.all("SELECT * FROM entries")
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as db:
            db.execute(sql)
    assert store.all("SELECT * FROM entries") == entries
    assert not store.all("PRAGMA foreign_key_check")
    store.export_all()


def test_composite_foreign_key_rejects_wrong_group_even_after_entity_merge(client, app):
    from tests.support.workbench import FakeRegistry, observations

    import_rows(client, app)
    first = client.get("/api/leads").json()[0]

    class Other(FakeRegistry):
        def lookup(self, ip):
            record = super().lookup(ip)
            return type(record)(
                record.ip,
                record.registry,
                record.source_url,
                record.retrieved_at,
                {"contact": "support@another.com"},
            )

    app.state.intake.attribution_factory = registry_factory(Other)
    import_rows(
        client,
        app,
        [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.4.4"}],
        "another.csv",
    )
    second = next(
        lead_item for lead_item in client.get("/api/leads").json() if lead_item["id"] != first["id"]
    )
    store = app.state.store
    store.merge_entities(
        first["id"], second["id"], first["draft_revision"], second["draft_revision"]
    )
    groups = store.all("SELECT * FROM domain_groups ORDER BY root_domain")
    assert groups[0]["entity_id"] == groups[1]["entity_id"]
    before = store.all("SELECT * FROM domain_groups")
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as db:
            db.execute(
                "UPDATE domain_groups SET attribution_entry_id=? WHERE root_domain=?",
                (groups[0]["attribution_entry_id"], groups[1]["root_domain"]),
            )
    assert store.all("SELECT * FROM domain_groups") == before
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as db:
            db.execute("UPDATE domain_groups SET entity_id=?", (first["id"],))
    assert not store.all("PRAGMA foreign_key_check")


def test_review_upgrade_backfills_reference_and_retains_decisions(review_app):
    app, client, group, state, content = review_app
    accepted = client.post(
        "/api/groups/" + group["id"] + "/review", json=accept_payload(group)
    ).json()
    store = app.state.store
    expected = store.all("SELECT * FROM attribution_reviews")
    result_id = group["attribution_result"]["result_id"]
    legacy_database(store, 2, review_columns=True)
    Store(store.root)
    assert (
        store.one("SELECT attribution_result_id FROM jobs WHERE id=?", (group["id"],))[
            "attribution_result_id"
        ]
        == result_id
    )
    assert store.all("SELECT * FROM attribution_reviews") == expected
    assert store.lead(accepted["lead_id"])["attribution"]["result_id"] == result_id
    assert not store.all("PRAGMA foreign_key_check")


def test_current_result_reference_does_not_depend_on_attempt_json(review_app):
    app, client, group, state, content = review_app
    with app.state.store.transaction() as db:
        db.execute("UPDATE jobs SET attempts='[]' WHERE id=?", (group["id"],))
    detail = client.get("/api/groups/" + group["id"]).json()
    assert detail["attribution_result"]["result_id"] == group["attribution_result"]["result_id"]
    assert client.get("/api/reviews").json()[0]["matches"]
    assert (
        client.post(
            "/api/groups/" + group["id"] + "/review", json=accept_payload(group)
        ).status_code
        == 200
    )


def test_review_decision_constraints(review_app):
    app, client, group, state, content = review_app
    client.post("/api/groups/" + group["id"] + "/review", json=accept_payload(group))
    for sql in (
        "UPDATE attribution_reviews SET decision='typo'",
        "UPDATE attribution_reviews SET evidence_index=-1",
        "UPDATE attribution_reviews SET lead_id=NULL",
        "UPDATE attribution_reviews SET result_id=NULL",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            with app.state.store.transaction() as db:
                db.execute(sql)


def test_cross_database_reference_rejects_missing_or_wrong_domain(review_app):
    from attribution import EvidenceStore
    from attribution.models import AttributionResult

    app, client, group, state, content = review_app
    result_id = "b" * 32
    for create_result in (False, True):
        if create_result:
            with EvidenceStore(app.state.store.root / "attribution.sqlite3") as store:
                result = AttributionResult(
                    result_id,
                    "unrelated.com",
                    "review",
                    "2026-11-06T17:00:00Z",
                    (),
                    None,
                    None,
                    (),
                    (),
                    {"id": "root-domain-v2"},
                    {},
                )
                store.save_result(result)
        with app.state.store.transaction() as db:
            db.execute(
                "UPDATE jobs SET attribution_result_id=? WHERE id=?", (result_id, group["id"])
            )
        response = client.get("/api/groups/" + group["id"])
        assert response.status_code == 422
        payload = {**accept_payload(group), "result_id": result_id}
        assert (
            client.post("/api/groups/" + group["id"] + "/review", json=payload).status_code == 422
        )
        assert not client.get("/api/leads").json()


@pytest.mark.parametrize(
    "query,index",
    [
        ("SELECT * FROM domain_groups WHERE entity_id=?", "domain_groups_entity"),
        (
            "SELECT * FROM reports WHERE entity_id=? ORDER BY created_at DESC",
            "reports_entity_created",
        ),
        (
            "SELECT * FROM attribution_reviews WHERE job_id=? ORDER BY reviewed_at",
            "reviews_job_time",
        ),
    ],
)
def test_frequent_queries_use_relationship_indexes(tmp_path, query, index):
    store = Store(tmp_path)
    plan = store.all("EXPLAIN QUERY PLAN " + query, ("example",))
    assert any(index in row["detail"] for row in plan)
