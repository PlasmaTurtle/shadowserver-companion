"""Independent contact-discovery trust-boundary regression tests.

All company pages and registration evidence in these tests are synthetic.
"""

from contextlib import closing

from dataclasses import asdict
from hashlib import sha256
import asyncio
import json
import socket
import sqlite3
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
from workbench.attribution_bridge import attribution_record
from workbench.cases import Cases
from workbench.primitives import now
from workbench.store import Store


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
    from workbench.contact_records import ContactRecords

    store = Store(tmp_path / "data")
    entity = attributed_entity(store)
    return store, ContactRecords(store), entity


def discover(records, result=None):
    store, contacts, entity = records
    contacts.save_run(contacts.scope(entity["id"]), result or contact_result())
    return contacts.state(entity["id"])["candidates"][0]


def test_scope_ownership_change_cannot_receive_inflight_result(records):
    store, contacts, entity = records
    scope = contacts.scope(entity["id"])
    attributed_entity(store, "other.example", "other")
    store.merge_entities(entity["id"], "other", 0, 0)
    with pytest.raises(ValueError):
        contacts.save_run(scope, contact_result())
    assert store.all("SELECT * FROM contact_runs") == []
    assert store.all("SELECT * FROM contact_candidates") == []


def test_corrupt_attribution_is_not_claimed_for_entity_website_contact_lookup(records):
    store, contacts, entity = records
    with closing(sqlite3.connect(store.root / "attribution.sqlite3")) as db, db:
        db.execute(
            "UPDATE snapshots SET body=? WHERE id=?", (b"corrupted", entity["response"].snapshot_id)
        )
    scope = contacts.scope(entity["id"])
    assert scope["basis"] == "entity_domain" and scope["attribution_ref"] is None
    assert all(root["attribution_ref"] is None for root in contacts.state(entity["id"])["roots"])


def test_confirmation_is_entity_scoped_and_revision_checked(records):
    store, contacts, entity = records
    candidate = discover(records)
    attributed_entity(store, "other.example", "other")
    with pytest.raises(ValueError):
        contacts.review("other", candidate["id"], "confirm", candidate["revision"])
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    with pytest.raises(ValueError):
        contacts.review(entity["id"], candidate["id"], "ignore", candidate["revision"])
    assert contacts.state(entity["id"])["candidates"][0]["decision"] == "confirmed"


def test_effective_manual_profile_contact_is_not_silently_replaced(records):
    store, contacts, entity = records
    case = Cases(store).create(entity["id"])
    with store.transaction() as db:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?)",
            (entity["id"], json.dumps({"contact_email": "manual@example.com"})),
        )
    candidate = discover(records)
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    candidate = contacts.state(entity["id"])["candidates"][0]
    before = store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    selected = contacts.use(
        Cases(store), case["case_id"], candidate["id"], before["version"], candidate["revision"]
    )
    assert selected["filled_fields"] == []
    assert store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],)) == before
    assert store.lead(entity["id"])["entity_profile"]["contact_email"] == "manual@example.com"


def test_explicit_contact_use_preserves_certified_draft_and_scope(records):
    store, contacts, entity = records
    case = Cases(store).create(entity["id"])
    with store.transaction() as db:
        db.execute("UPDATE cases SET stage='pending_notification' WHERE id=?", (case["case_id"],))
    candidate = discover(records)
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    candidate = contacts.state(entity["id"])["candidates"][0]
    before = store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    groups = store.all("SELECT * FROM case_groups WHERE case_id=?", (case["case_id"],))
    contacts.use(
        Cases(store), case["case_id"], candidate["id"], before["version"], candidate["revision"]
    )
    after = store.one("SELECT * FROM cases WHERE id=?", (case["case_id"],))
    assert after["contact_email"] == candidate["value"]
    for field in ("draft", "draft_revision", "certified_report_id", "stage"):
        assert after[field] == before[field]
    assert store.all("SELECT * FROM case_groups WHERE case_id=?", (case["case_id"],)) == groups


def test_previously_published_contact_remains_selectable_with_missing_source_status(records):
    store, contacts, entity = records
    case = Cases(store).create(entity["id"])
    candidate = discover(records)
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    contacts.save_run(contacts.scope(entity["id"]), contact_result(candidates=False))
    candidate = contacts.state(entity["id"])["candidates"][0]
    assert candidate["missing_from_latest"]
    assert candidate["decision"] == "confirmed"
    selected = contacts.use(
        Cases(store),
        case["case_id"],
        candidate["id"],
        case["case"]["version"],
        candidate["revision"],
    )
    assert selected["contact_plan"]["contact_email"] == candidate["value"]


def test_superseded_contact_capture_is_checked_during_restore(records):
    from workbench.workspace_data_contacts import validate_contact_data

    store, contacts, entity = records
    first = contact_result()
    contacts.save_run(contacts.scope(entity["id"]), first)
    contacts.save_run(contacts.scope(entity["id"]), contact_result(value="new@example.com"))
    validate_contact_data(store)
    captured = [
        p
        for p in (store.root / "evidence" / "contact-discovery").rglob("*")
        if p.is_file()
        and json.loads(p.read_bytes())["source"]["sha256"] == first["snapshots"][0]["sha256"]
    ]
    assert len(captured) == 1
    captured[0].write_bytes(b"altered old response")
    with pytest.raises(ValueError):
        validate_contact_data(store)
    with pytest.raises(ValueError):
        contacts.export(entity["id"])


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "2002:7f00:1::",
        "64:ff9b::7f00:1",
    ],
)
def test_mixed_public_private_dns_answer_is_rejected_whole(monkeypatch, address):
    from workbench.contact_discovery.transport import public_addresses

    answers = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (
            socket.AF_INET6 if ":" in address else socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            (address, 443),
        ),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: answers)
    with pytest.raises(ValueError):
        public_addresses("example.com")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com.evil.example/contact",
        "https://staff.example.com/contact",
        "https://example.com@evil.example/contact",
        "https://%65xample.com/contact",
        "https://example.com:444/contact",
        "http://example.com/contact",
        "https://example.com./contact",
        "https://example.com/contact?redirect=evil",
        "https://example.com\\@evil.example/contact",
    ],
)
def test_url_boundary_rejects_ambiguous_or_unapproved_sources(url):
    from workbench.contact_discovery.policy import approved_url

    with pytest.raises(ValueError):
        approved_url(url, {"example.com"})


def test_transport_pins_resolved_ip_and_verifies_original_hostname(monkeypatch):
    from workbench.contact_discovery.transport import _request

    calls, written = [], []
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    def resolver(host, port, **kwargs):
        calls.append(("resolve", host, port))
        return answers

    monkeypatch.setattr(socket, "getaddrinfo", resolver)

    class Writer:
        transport = None

        def __init__(self):
            self.transport = self

        def write(self, body):
            written.append(body)

        async def drain(self):
            pass

        def close(self):
            pass

        def abort(self):
            pass

    async def scenario():
        loop = asyncio.get_running_loop()

        async def connect(sock, address):
            calls.append(("connect", address))

        async def tls(*args, **kwargs):
            calls.append(("tls", kwargs["server_hostname"]))
            assert not args and "host" not in kwargs and "port" not in kwargs
            assert isinstance(kwargs["sock"], socket.socket)
            assert kwargs["ssl"].check_hostname
            assert kwargs["ssl"].verify_mode.name == "CERT_REQUIRED"
            reader = asyncio.StreamReader()
            reader.feed_data(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            reader.feed_eof()
            return reader, Writer()

        monkeypatch.setattr(loop, "sock_connect", connect)
        monkeypatch.setattr(asyncio, "open_connection", tls)
        response = await _request("https://example.com/contact", 1024)
        assert response.status_code == 200

    asyncio.run(scenario())
    assert calls == [
        ("resolve", "example.com", 443),
        ("connect", ("8.8.8.8", 443)),
        ("tls", "example.com"),
    ]
    assert b"GET /contact HTTP/1.1\r\nHost: example.com\r\n" in written[0]
    assert b"Cookie:" not in written[0] and b"Authorization:" not in written[0]


def test_page_global_security_heading_does_not_promote_general_contact():
    from workbench.contact_discovery.extract import parse_html

    page = """<body><h1>Security is our priority</h1><main>Our products</main>
    <a href="mailto:hello@example.com">Customer service</a></body>"""
    result = parse_html(page, "https://example.com/", {"example.com"})
    candidates = [c for c in result["candidates"] if c["value"] == "hello@example.com"]
    assert candidates
    assert all(c["purpose"] == "general" and not c["role"] for c in candidates)


def test_entity_export_includes_contact_history_without_altering_case_export(records):
    store, contacts, entity = records
    case = Cases(store).create(entity["id"])
    before = store.export_lead(entity["id"], case["case_id"])
    candidate = discover(records)
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    projection = store.export_lead(entity["id"])
    assert projection["contact_discovery"]["candidates"][0]["id"] == candidate["id"]
    assert projection["contact_discovery"]["candidates"][0]["decision"] == "confirmed"
    assert projection["contact_discovery"]["candidates"][0]["sources"]
    assert projection["contact_discovery"]["runs"][0]["attribution_ref"]
    assert store.export_lead(entity["id"], case["case_id"]) == before
    assert "contact_discovery" not in before


def test_confirmed_value_remains_bound_to_original_captured_candidate(records):
    from workbench.workspace_data_contacts import validate_contact_data

    store, contacts, entity = records
    case = Cases(store).create(entity["id"])
    candidate = discover(records)
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])
    saved = store.one("SELECT * FROM contact_candidates WHERE id=?", (candidate["id"],))
    payload = json.loads(saved["payload"])
    payload["value"] = "unpublished@unrelated.example"
    with store.transaction() as db:
        db.execute(
            "UPDATE contact_candidates SET payload=? WHERE id=?",
            (json.dumps(payload), candidate["id"]),
        )
    with pytest.raises(ValueError):
        contacts.use(
            Cases(store),
            case["case_id"],
            candidate["id"],
            case["case"]["version"],
            saved["revision"],
        )
    assert not Cases(store).view(case["case_id"])["case"]["contact_email"]
    with pytest.raises(ValueError):
        validate_contact_data(store)
    with pytest.raises(ValueError):
        contacts.export(entity["id"])


def test_backup_roundtrip_retains_contact_decisions_and_exact_derived_evidence(records, tmp_path):
    from workbench.workspace_data import export_workspace, unpack_workspace
    from workbench.contact_records import ContactRecords

    store, contacts, entity = records
    candidate = discover(records)
    contacts.review(entity["id"], candidate["id"], "ignore", candidate["revision"])
    expected = contacts.export_projection(entity["id"])
    bodies = {
        p.relative_to(store.root): p.read_bytes()
        for p in (store.root / "evidence" / "contact-discovery").rglob("*.contact.json")
    }
    assert bodies
    archive = export_workspace(store)
    try:
        replacement = tmp_path / "restored"
        unpack_workspace(archive, replacement)
        restored = Store(replacement)
        assert ContactRecords(restored).export_projection(entity["id"]) == expected
        for path, body in bodies.items():
            assert (replacement / path).read_bytes() == body
    finally:
        archive.unlink(missing_ok=True)


def test_historical_contact_excerpt_cannot_be_rewritten_in_evidence_export(records):
    from workbench.workspace_data_contacts import validate_contact_data

    store, contacts, entity = records
    candidate = discover(records)
    first_run = candidate["latest_run_id"]
    discover(records)
    row = store.one(
        "SELECT * FROM contact_sources WHERE candidate_id=? AND run_id=?",
        (candidate["id"], first_run),
    )
    sources = json.loads(row["payload"])
    sources[0]["excerpt"] = "This was never published by the website."
    with store.transaction() as db:
        db.execute(
            "UPDATE contact_sources SET payload=? WHERE candidate_id=? AND run_id=?",
            (json.dumps(sources), candidate["id"], first_run),
        )
    with pytest.raises(ValueError):
        validate_contact_data(store)
    with pytest.raises(ValueError):
        contacts.export(entity["id"])


@pytest.mark.parametrize("limited", [False, True])
def test_incomplete_discovery_never_asserts_prior_contact_disappeared(records, limited):
    from workbench.contact_discovery import ContactDiscovery, DiscoveryLimits

    _, contacts, entity = records
    candidate = discover(records)
    contacts.review(entity["id"], candidate["id"], "confirm", candidate["revision"])

    def fetch(url, **kwargs):
        if url.endswith("security.txt"):
            return {"status_code": 404, "headers": {}, "body": b""}
        if limited:
            return {
                "status_code": 200,
                "headers": {"content-type": "text/html"},
                "body": b"<p>other@example.com</p><p>security@example.com</p>",
            }
        return {
            "status_code": 200,
            "headers": {"content-type": "application/pdf"},
            "body": b"unsupported",
        }

    result = ContactDiscovery(fetcher=fetch, limits=DiscoveryLimits(max_candidates=1)).discover(
        "example.com"
    )
    assert result["status"] in ("partial", "failed")
    contacts.save_run(contacts.scope(entity["id"]), result)
    previous = next(
        c for c in contacts.state(entity["id"])["candidates"] if c["id"] == candidate["id"]
    )
    assert previous["decision"] == "confirmed"
    assert not previous["missing_from_latest"]


@pytest.mark.parametrize("oversize", [False, True])
def test_restored_contact_response_read_is_bounded_before_hashing(tmp_path, monkeypatch, oversize):
    from pathlib import Path
    from workbench.contact_evidence import MAX_CAPTURE_BYTES, snapshot_path

    store = Store(tmp_path / "data")
    folder = store.root / "evidence" / "contact-discovery" / "saved-run"
    folder.mkdir(parents=True)
    path = folder / "response.body.txt"
    body = b"x" * (MAX_CAPTURE_BYTES + int(oversize))
    path.write_bytes(body)
    snapshot = {"path": path.relative_to(store.root).as_posix(), "sha256": sha256(body).hexdigest()}
    original_open = Path.open
    reads = []

    class BoundedReader:
        def __init__(self, source):
            self.source = source

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.source.close()

        def read(self, size=-1):
            assert 0 < size <= MAX_CAPTURE_BYTES + 1
            reads.append(size)
            return self.source.read(size)

    def guarded_open(file, *args, **kwargs):
        opened = original_open(file, *args, **kwargs)
        return BoundedReader(opened) if file == path else opened

    monkeypatch.setattr(Path, "open", guarded_open)
    if oversize:
        with pytest.raises(ValueError, match="capture limit"):
            snapshot_path(store, "saved-run", snapshot)
    else:
        assert snapshot_path(store, "saved-run", snapshot) == path
    assert reads
