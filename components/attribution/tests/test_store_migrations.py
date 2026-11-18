"""Evidence bytes survive upgrades; searchable columns cannot disagree with their snapshot."""
import json
import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from attribution import EvidenceStore
from attribution.models import AttributionResult, ResponseSnapshot, json_bytes
from attribution.migrations import _schema_one


def fixture_result(**changes):
    result = AttributionResult('a' * 32, 'example.com', 'no_match', '2026-11-06T15:00:00Z',
                               (), None, None, (), (), {'id': 'root-domain-v2'}, {})
    return replace(result, **changes)


def legacy_store(path):
    snapshot = ResponseSnapshot.create('https://example.com', 'https://example.com', 200,
                                       {'content-type': 'application/rdap+json'}, b'{"original":"bytes"}')
    payload = json_bytes(fixture_result().to_dict()).decode()
    with closing(sqlite3.connect(path)) as db:
        _schema_one(db)
        db.execute('INSERT INTO snapshots VALUES(?,?,?)', (snapshot.snapshot_id, json_bytes(snapshot.metadata()).decode(), snapshot.body))
        db.execute('INSERT INTO results VALUES(?,?,?)', ('a' * 32, '2026-11-06T15:00:00Z', payload))
        db.execute('PRAGMA user_version=1')
        db.commit()
    return snapshot, payload


def test_legacy_upgrade_preserves_responses_and_full_result(tmp_path):
    path = tmp_path / 'attribution.sqlite3'
    snapshot, payload = legacy_store(path)
    with EvidenceStore(path) as store:
        assert store._db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert store.snapshot(snapshot.snapshot_id).body == snapshot.body
        row = store._db.execute('SELECT * FROM results').fetchone()
        assert row['payload'] == payload
        assert (row['root_domain'], row['status'], row['policy_version']) == ('example.com', 'no_match', 'root-domain-v2')
    backups = list((tmp_path / 'backups').glob('attribution-before-schema-2-*.sqlite3'))
    assert len(backups) == 1
    with EvidenceStore(path):
        pass
    assert list((tmp_path / 'backups').iterdir()) == backups
    with closing(sqlite3.connect(backups[0])) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert db.execute('SELECT payload FROM results').fetchone()[0] == payload


def test_bad_legacy_result_rolls_back_upgrade(tmp_path):
    path = tmp_path / 'attribution.sqlite3'
    legacy_store(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE results SET payload='invalid json'")
        db.commit()
    with pytest.raises(ValueError):
        EvidenceStore(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert [r[1] for r in db.execute('PRAGMA table_info(results)')] == ['id', 'created_at', 'payload']
        assert db.execute('SELECT payload FROM results').fetchone()[0] == 'invalid json'


def test_future_evidence_schema_rejected_without_mutation(tmp_path):
    path = tmp_path / 'attribution.sqlite3'
    legacy_store(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='Unsupported attribution database version'):
        EvidenceStore(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 99
    assert not (tmp_path / 'backups').exists()


@pytest.mark.parametrize('assignment', [
    "root_domain='wrong.com'", "status='matched'", "status='typo'",
    "policy_version='wrong-version'", "created_at='wrong-date'", "id='wrong-id'", "payload='invalid json'",
])
def test_result_metadata_cannot_disagree_with_payload(assignment):
    with EvidenceStore(':memory:') as store:
        store.save_result(fixture_result())
        with pytest.raises(sqlite3.IntegrityError):
            with store._db:
                store._db.execute('UPDATE results SET ' + assignment)
        assert store.result('a' * 32)['status'] == 'no_match'


def test_filtered_history_and_indexed_lookup():
    with EvidenceStore(':memory:') as store:
        store.save_result(fixture_result())
        store.save_result(fixture_result(result_id='b' * 32, root_domain='other.com', status='review', evaluated_at='2026-11-06T16:00:00Z'))
        store.save_result(fixture_result(result_id='c' * 32, status='review', evaluated_at='2026-11-06T17:00:00Z'))
        assert [r['result_id'] for r in store.history(root_domain='EXAMPLE.com', status='review')] == ['c' * 32]
        assert [r['result_id'] for r in store.history(limit=1)] == ['c' * 32]
        for where, value, index in [('root_domain=?', 'example.com', 'results_domain_created'),
                                    ('status=?', 'review', 'results_status_created')]:
            plan = store._db.execute('EXPLAIN QUERY PLAN SELECT id FROM results WHERE ' + where + ' ORDER BY created_at DESC', (value,)).fetchall()
            assert any(index in r['detail'] for r in plan)


def test_custom_policy_without_version_is_not_invented():
    with EvidenceStore(':memory:') as store:
        store.save_result(fixture_result(policy={'rule': 'custom'}))
        assert store._db.execute('SELECT policy_version FROM results').fetchone()[0] is None


def test_cli_history_filters_use_saved_metadata(tmp_path, capsys):
    from attribution.cli import main
    path = tmp_path / 'attribution.sqlite3'
    with EvidenceStore(path) as store:
        store.save_result(fixture_result())
        store.save_result(fixture_result(result_id='b' * 32, root_domain='another.com', status='review'))
    assert main(['history', '--db', str(path), '--root-domain', 'example.com', '--status', 'no_match']) == 0
    assert [r['result_id'] for r in json.loads(capsys.readouterr().out)] == ['a' * 32]
