"""Dark Matter is a complete rejected-row archive, independent of admission."""

from datetime import datetime, timezone
import json
import sqlite3

import pytest

from modules.accretion.components.dark_matter_store import (
    DarkMatterStore,
    drain,
    enqueue_batch,
    enqueue_outcome,
    prepare_batch,
    enqueue_prepared,
    archive_counts,
    delivery_status,
)
from modules.accretion.components.intake.records import SourceObservation
from modules.accretion.components.report_profiles import inventory
from modules.accretion.components import dark_matter_store
from modules.accretion.databases.dark_matter_schema import create_workspace_outbox


def source(import_id="sample"):
    return {
        "import_id": import_id,
        "sha256": "a" * 64,
        "name": "scan_http_vulnerable.csv",
        "path": "originals/report.csv",
        "report_type": "scan_http_vulnerable",
    }


def row(number=2, **fields):
    return SourceObservation("report.csv", "", number, fields)


def workspace(root):
    db = sqlite3.connect(root / "workbench.sqlite3")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE imports(id TEXT PRIMARY KEY,sha256 TEXT,name TEXT,path TEXT,config TEXT)"
    )
    db.execute(
        "INSERT INTO imports VALUES(?,?,?,?,?)",
        ("sample", "a" * 64, "scan_http_vulnerable.csv", "originals/report.csv", "{}"),
    )
    create_workspace_outbox(db)
    db.commit()
    return db


def test_all_provider_fields_unknown_fields_and_invalid_rows_are_archived(tmp_path):
    archive = DarkMatterStore(tmp_path)
    fields = {
        name: "provider value" for report in inventory().values() for name in report["fields"]
    }
    fields["future_provider_column"] = "a" * 10000
    originals = dict(fields)
    result = archive.record_batch(
        source(),
        [row(**fields), row(3, ip="not-an-ip"), row(4, region="Outside scope"), row(5)],
        reason="invalid_finding",
    )
    assert len(result["record_ids"]) == 4
    saved = archive.get(result["record_ids"][0])
    assert saved["raw_fields"] == originals
    assert len(saved["raw_fields"]["future_provider_column"]) == 10000
    assert saved["normalized_fields"]["ip"] is None
    assert "ip" in saved["errors"]
    assert archive.query()["total"] == 4
    catalog = {item["name"]: item for item in archive.field_catalog()["fields"]}
    assert not catalog["future_provider_column"]["known"]
    assert len([value for value in catalog.values() if value["known"]]) == 746
    assert fields == originals


def test_typed_queries_raw_values_diagnostics_and_pagination(tmp_path):
    archive = DarkMatterStore(tmp_path)
    archive.record_batch(
        source(),
        [
            row(
                2,
                port="00443",
                ip="2001:db8:0:0::1",
                hostname="EXAMPLE.COM.",
                asn="AS64500",
                timestamp="2026-11-21 01:02:03",
                cert_valid="yes",
                http_code="200",
                extra="Alpha",
            ),
            row(3, port="70000", ip="bad", extra="Beta"),
            row(4, extra="Alpha", **{'a.b"c': "strange header"}),
        ],
    )
    response = archive.query(filters=[{"field": "port", "op": "gte", "value": 400}])
    assert response["total"] == 1
    saved = response["items"][0]
    assert saved["port"] == 443
    assert saved["ip"] == "2001:db8::1"
    assert saved["hostname"] == "example.com"
    assert saved["normalized_fields"]["cert_valid"] is True
    assert saved["observed_at"] == "2026-11-21T01:02:03Z"
    assert saved["raw_fields"]["port"] == "00443"
    assert archive.query(filters=[{"field": "port", "op": "invalid"}])["total"] == 1
    assert archive.query(filters=[{"field": "port", "op": "missing"}])["total"] == 1
    assert (
        archive.query(filters=[{"field": "port", "op": "eq", "value": "00443", "source": "raw"}])[
            "total"
        ]
        == 1
    )
    assert (
        archive.query(filters=[{"field": 'a.b"c', "op": "contains", "value": "header"}])["total"]
        == 1
    )
    assert (
        archive.query(
            filters=[{"field": "extra", "op": "in", "value": ["Alpha"]}], limit=1, offset=1
        )["total"]
        == 2
    )
    assert archive.query(q="beta")["total"] == 1
    assert archive.facets("extra")["items"] == [
        {"value": "Alpha", "count": 2},
        {"value": "Beta", "count": 1},
    ]
    assert len(list(archive.iter_records(limit=2))) == 2
    with pytest.raises(ValueError, match="operator"):
        archive.query(filters=[{"field": "port", "op": "DROP TABLE records"}])


def test_outcomes_keep_originals_and_replay_is_idempotent(tmp_path):
    archive = DarkMatterStore(tmp_path)
    result = archive.record_batch(source(), [row(ip="bad")], event_id="batch", reason="invalid_ip")
    record_id = result["record_ids"][0]
    revision = archive.revision()
    assert archive.record_batch(source(), [row(ip="bad")], event_id="batch")["replayed"]
    assert archive.revision() == revision
    archive.record_outcome(
        [record_id],
        import_id="sample",
        stage="qualify",
        outcome="review",
        reason="manual_review",
        event_id="review",
    )
    archive.record_outcome(
        [record_id], import_id="sample", stage="associate", outcome="promoted", event_id="promote"
    )
    assert archive.query()["total"] == 0
    assert archive.query(include_promoted=True)["total"] == 1
    saved = archive.get(record_id)
    assert saved["raw_fields"] == {"ip": "bad"}
    assert [event["stage"] for event in saved["outcomes"]] == ["filter", "qualify", "associate"]
    assert archive.record_outcome(
        [record_id], import_id="sample", stage="associate", outcome="promoted", event_id="promote"
    )["replayed"]
    assert len(archive.get(record_id)["outcomes"]) == 3


def test_different_source_values_cannot_replace_an_existing_identity(tmp_path):
    archive = DarkMatterStore(tmp_path)
    archive.record_batch(source(), [row(ip="bad")])
    revision = archive.revision()
    with pytest.raises(ValueError, match="different original fields"):
        archive.record_batch(source("other"), [row(3, ip="new"), row(ip="changed")])
    assert archive.query()["total"] == 1
    assert archive.revision() == revision


def test_archive_accepts_workbook_values_without_clipping(tmp_path):
    archive = DarkMatterStore(tmp_path)
    result = archive.record_batch(
        source(),
        [
            row(
                timestamp=datetime(2026, 11, 21, tzinfo=timezone.utc),
                version="v" * 5000,
                value=float("nan"),
                region={"malformed": True},
            )
        ],
    )
    saved = archive.get(result["record_ids"][0])
    assert saved["normalized_fields"]["timestamp"] == "2026-11-21T00:00:00Z"
    assert saved["raw_fields"]["value"] == {"$type": "nonfinite_number", "value": "nan"}
    assert saved["normalized_fields"]["value"] is None
    assert len(saved["raw_fields"]["version"]) == 5000
    assert "region" in saved["errors"]


def test_workspace_rollback_and_delivery_replay(tmp_path, monkeypatch):
    archive = DarkMatterStore(tmp_path)
    db = workspace(tmp_path)
    try:
        enqueue_batch(db, "sample", [row(ip="bad")])
        db.rollback()
        assert drain(tmp_path) == 0
        assert archive.query()["total"] == 0
        event_id = enqueue_batch(db, "sample", [row(ip="bad")])[0]
        enqueue_outcome(
            db,
            "sample",
            [row(ip="bad")],
            stage="qualify",
            outcome="no_match",
            reason="attribution_no_match",
        )
        db.commit()
        queued = db.execute(
            "SELECT payload,recorded_at FROM dark_matter_outbox WHERE event_id=?", (event_id,)
        ).fetchone()
        archive.record_batch(**json.loads(queued[0]), event_id=event_id, recorded_at=queued[1])
        # The archive committed but acknowledgement never happened: restart replays it.
        assert drain(tmp_path) == 2
        assert db.execute("SELECT count(*) FROM dark_matter_outbox").fetchone()[0] == 0
        saved = archive.query()["items"][0]
        assert saved["outcome"] == "no_match"
        assert len(archive.get(saved["record_id"])["outcomes"]) == 2
        assert drain(tmp_path) == 0
    finally:
        db.close()


def test_unknown_outcome_record_fails_without_partial_updates(tmp_path):
    archive = DarkMatterStore(tmp_path)
    record_id = archive.record_batch(source(), [row(ip="bad")])["record_ids"][0]
    with pytest.raises(ValueError, match="does not exist"):
        archive.record_outcome(
            [record_id, "missing"], import_id="sample", stage="qualify", outcome="review"
        )
    assert archive.get(record_id)["outcome"] == "rejected"
    assert len(archive.get(record_id)["outcomes"]) == 1


def test_prepared_batches_are_immutable_bounded_and_published_together(tmp_path):
    archive = DarkMatterStore(tmp_path)
    original = {"ip": "invalid", "extra": "original"}
    prepared = prepare_batch(source(), [row(number, **original) for number in range(1, 502)])
    original["extra"] = "changed"
    assert isinstance(prepared, tuple)
    assert [len(json.loads(event[2])["rows"]) for event in prepared] == [500, 1]
    db = workspace(tmp_path)
    try:
        enqueue_prepared(db, prepared)
        db.commit()
        assert drain(tmp_path) == 2
        assert archive.query()["total"] == 501
        assert archive.query()["items"][0]["raw_fields"]["extra"] == "original"
    finally:
        db.close()


def test_http_date_uses_its_rfc_field_contract(tmp_path):
    archive = DarkMatterStore(tmp_path)
    result = archive.record_batch(source(), [row(http_date="Sat, 21 Nov 2026 12:34:56 GMT")])
    saved = archive.get(result["record_ids"][0])
    assert saved["normalized_fields"]["http_date"] == "2026-11-21T12:34:56Z"
    assert not saved["errors"]


def test_unknown_fields_do_not_inherit_types_from_name_suffixes(tmp_path):
    archive = DarkMatterStore(tmp_path)
    result = archive.record_batch(source(), [row(future_ip="a provider-specific description")])
    saved = archive.get(result["record_ids"][0])
    assert saved["normalized_fields"]["future_ip"] == "a provider-specific description"
    assert not saved["errors"]


def test_reimport_normalizes_each_source_row_only_once(tmp_path, monkeypatch):
    archive = DarkMatterStore(tmp_path)
    normalize = dark_matter_store.normalize_fields
    calls = []

    def counted(fields):
        calls.append(fields)
        return normalize(fields)

    monkeypatch.setattr(dark_matter_store, "normalize_fields", counted)
    record_id = archive.record_batch(source(), [row(port="443")])["record_ids"][0]
    archive.record_batch(source("second-policy"), [row(port="443")], reason="other_policy")
    archive.record_outcome(
        [record_id], import_id="second-policy", stage="qualify", outcome="review"
    )
    saved = archive.get(record_id)
    assert len(calls) == 1
    assert saved["raw_fields"] == {"port": "443"}
    assert saved["normalized_fields"] == {"port": 443}
    assert len(saved["outcomes"]) == 3


def test_promotion_outside_archive_is_an_idempotent_no_op(tmp_path):
    archive = DarkMatterStore(tmp_path)
    before = archive.revision()
    result = archive.record_outcome(
        ["not-archived"],
        import_id="sample",
        stage="associate",
        outcome="promoted",
        event_id="promotion",
    )
    assert result == {"updated": 0, "not_archived": 1, "replayed": False}
    assert archive.query(include_promoted=True)["total"] == 0
    assert archive.revision() == before
    assert archive.record_outcome(
        ["not-archived"],
        import_id="sample",
        stage="associate",
        outcome="promoted",
        event_id="promotion",
    )["replayed"]


def test_queries_never_mutate_the_archive(tmp_path):
    archive = DarkMatterStore(tmp_path)
    record_id = archive.record_batch(source(), [row(ip="invalid")])["record_ids"][0]
    with sqlite3.connect(archive.path) as db:
        before = list(db.iterdump())
    archive.query()
    archive.get(record_id)
    archive.field_catalog()
    archive.facets("stage")
    list(archive.iter_records())
    assert archive.revision() == 1
    with sqlite3.connect(archive.path) as db:
        assert list(db.iterdump()) == before


def test_unknown_database_schema_is_not_silently_replaced(tmp_path):
    archive = DarkMatterStore(tmp_path)
    with sqlite3.connect(archive.path) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(ValueError, match="schema"):
        DarkMatterStore(tmp_path)


def test_health_reads_component_counts_without_mutations(tmp_path):
    archive = DarkMatterStore(tmp_path)
    archive.record_batch(source(), [row(ip="invalid")])
    db = workspace(tmp_path)
    try:
        assert delivery_status(db) == {"pending": 0, "oldest_pending_at": None}
        enqueue_batch(db, "sample", [row(3)])
        assert delivery_status(db)["pending"] == 1
        with sqlite3.connect(archive.path) as snapshot:
            snapshot.execute("PRAGMA query_only=ON")
            assert archive_counts(snapshot) == {
                "records": 1,
                "unpromoted_records": 1,
                "invalid_records": 1,
                "outcomes": 1,
                "revision": 1,
            }
    finally:
        db.close()


@pytest.mark.parametrize(
    "operation,value",
    [
        ("eq", {"nested": "value"}),
        ("contains", ["nested"]),
        ("gte", float("nan")),
        ("in", [{"nested": "value"}]),
        ("in", [2**100]),
    ],
)
def test_invalid_filter_values_fail_at_the_component_boundary(tmp_path, operation, value):
    archive = DarkMatterStore(tmp_path)
    with pytest.raises(ValueError):
        archive.query(filters=[{"field": "port", "op": operation, "value": value}])


def test_later_policy_rejection_preserves_promotion_history_without_duplication(tmp_path):
    archive = DarkMatterStore(tmp_path)
    record_id = archive.record_batch(source(), [row(ip="bad")])["record_ids"][0]
    archive.record_outcome([record_id], import_id="sample", stage="associate", outcome="promoted")
    archive.record_batch(source("another-policy"), [row(ip="bad")], reason="policy_changed")
    assert archive.query()["total"] == 0
    saved = archive.query(include_promoted=True)["items"][0]
    assert saved["promoted"] is True
    assert saved["outcome"] == "rejected"
    assert [event["outcome"] for event in archive.get(record_id)["outcomes"]] == [
        "rejected",
        "promoted",
        "rejected",
    ]


def test_empty_delivery_does_not_initialize_an_archive(tmp_path):
    db = workspace(tmp_path)
    db.close()
    assert drain(tmp_path) == 0
    assert not (tmp_path / "dark_matter.sqlite3").exists()
