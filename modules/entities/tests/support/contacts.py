"""Reusable synthetic contacts fixtures and builders."""

import json
from dataclasses import asdict
from hashlib import sha256
from uuid import uuid4

import pytest
from attribution import EvidenceStore
from attribution.models import (
    AttributionEvidence,
    AttributionResult,
    CandidateIP,
    DomainMatch,
    ResponseSnapshot,
)

from modules.attribution.components.attribution_bridge import attribution_record
from modules.workspace.components.primitives import now, uid
from modules.workspace.components.store import Store


def attributed_entity(store, root="example.com", entity_id="business"):
    """Seed a genuinely retained attribution chain, not a display-only fixture."""
    entry_id = uuid4().hex
    url = "https://rdap.arin.net/registry/ip/8.8.8.8"
    body = json.dumps({"objectClassName": "ip network", "contact": root}).encode()
    response = ResponseSnapshot.create(url, url, 200, {}, body)
    evidence = AttributionEvidence(
        "rdap",
        "8.8.8.8",
        "Synthetic registry",
        url,
        response.retrieved_at,
        response.snapshot_id,
        (),
        DomainMatch(root, root, "/contact", root),
        {},
    )
    result = AttributionResult(
        uuid4().hex,
        root,
        "matched",
        now(),
        (CandidateIP(entry_id, "8.8.8.8", "mail." + root),),
        entry_id,
        "8.8.8.8",
        (evidence,),
        (),
        {"version": "synthetic"},
        {},
    )
    with EvidenceStore(store.root / "attribution.sqlite3") as database:
        database.save_snapshot(response)
        database.save_result(result)
        proof = attribution_record(
            database, result.result_id, root, result.policy, asdict(evidence)
        )
    payload = {
        "ip": "8.8.8.8",
        "root_domain": root,
        "private_ip": False,
        "source": {
            "workbook": "synthetic.csv",
            "sheet": "CSV",
            "row": 2,
            "fields": {
                "hostname": "mail." + root,
                "ip": "8.8.8.8",
                "tag": "eol-php",
                "version": "7.3.25",
            },
        },
        "tag": "eol-php",
        "version": "7.3.25",
    }
    with store.transaction() as db:
        db.execute(
            "INSERT OR IGNORE INTO leads(id,domain,created_at,updated_at,attribution,attribution_entry_id) VALUES(?,?,?,?,?,?)",
            (entity_id, root, now(), now(), json.dumps(proof), entry_id),
        )
        db.execute(
            "INSERT INTO domain_groups VALUES(?,?,?,?)",
            (root, entity_id, entry_id, json.dumps(proof)),
        )
        db.execute("INSERT INTO hostnames VALUES(?,?)", ("mail." + root, root))
        db.execute(
            "INSERT INTO entries(id,lead_id,payload,ip,hostname,tag,version,root_domain) VALUES(?,?,?,?,?,?,?,?)",
            (
                entry_id,
                entity_id,
                json.dumps(payload),
                "8.8.8.8",
                "mail." + root,
                "eol-php",
                "7.3.25",
                root,
            ),
        )
    return {"id": entity_id, "root": root, "proof": proof, "response": response}


def contact_result(root="example.com", value="security@example.com", *, candidates=True):
    url, stamp, snapshot_id = "https://" + root + "/", now(), uuid4().hex
    body = f'<p>Security contact: <a href="mailto:{value}">{value}</a></p>'.encode()
    candidate = {
        "key": sha256(("email\0" + value.lower()).encode()).hexdigest(),
        "kind": "email",
        "value": value,
        "name": "",
        "role": "",
        "purpose": "security",
        "sources": [
            {"snapshot_id": snapshot_id, "url": url, "excerpt": "Security contact: " + value}
        ],
        "review_required": True,
    }
    return {
        "schema": 1,
        "root_hostname": root,
        "aliases": [],
        "status": "relevant_found" if candidates else "not_found",
        "started_at": stamp,
        "finished_at": stamp,
        "request_count": 1,
        "bytes_received": len(body),
        "candidates": [candidate] if candidates else [],
        "issues": [],
        "snapshots": [
            {
                "id": snapshot_id,
                "url": url,
                "retrieved_at": stamp,
                "status_code": 200,
                "content_type": "text/html",
                "title": "Synthetic contact page",
                "sha256": sha256(body).hexdigest(),
                "body": body,
            }
        ],
    }


@pytest.fixture
def records(tmp_path):
    from modules.entities.components.contact_records import ContactRecords

    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    return store, ContactRecords(store), entity


def entity_only(store, entity_id="business", domain="example.com"):
    entry_id = entity_id + "-observation"
    hostname = "mail." + domain
    with store.transaction() as db:
        db.execute(
            "INSERT INTO leads(id,domain,created_at,updated_at,attribution,attribution_entry_id) "
            "VALUES(?,?,?,?,?,?)",
            (entity_id, domain, now(), now(), "{}", entry_id),
        )
        db.execute("INSERT INTO domain_groups VALUES(?,?,?,?)", (domain, entity_id, entry_id, "{}"))
        db.execute("INSERT INTO hostnames VALUES(?,?)", (hostname, domain))
        db.execute(
            "INSERT INTO entries(id,lead_id,payload,ip,hostname,tag,version,root_domain) VALUES(?,?,?,?,?,?,?,?)",
            (
                entry_id,
                entity_id,
                json.dumps(
                    {
                        "root_domain": domain,
                        "ip": "8.8.8.8",
                        "hostname": hostname,
                        "tag": "eol-php",
                        "version": "7.3.25",
                    }
                ),
                "8.8.8.8",
                hostname,
                "eol-php",
                "7.3.25",
                domain,
            ),
        )
    return entity_id


def attempt(
    store,
    case_id,
    outcome,
    destination="security@example.com",
    occurred="2026-01-01T10:00:00Z",
    channel="email",
    report_id=None,
):
    with store.transaction() as db:
        db.execute(
            """INSERT INTO contact_attempts(id,case_id,report_id,occurred_at,recorded_at,channel,outcome,recipient,destination,notes,recorded_by,information_source)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uid(),
                case_id,
                report_id,
                occurred,
                now(),
                channel,
                outcome,
                "IT team",
                destination,
                "Synthetic activity",
                "Test analyst",
                "administrative",
            ),
        )


def report(store, case_id, entity_id):
    report_id = uid()
    with store.transaction() as db:
        db.execute(
            "INSERT INTO reports(id,lead_id,entity_id,case_id,revision,created_at,path) VALUES(?,?,?,?,?,?,?)",
            (report_id, entity_id, entity_id, case_id, 1, now(), "synthetic-report"),
        )
        db.execute(
            "UPDATE cases SET certified_report_id=?,stage='pending_notification' WHERE id=?",
            (report_id, case_id),
        )
    return report_id
