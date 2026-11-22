"""Cross-component acceptance checks for source-backed reports with screenshots."""

from tests.support.qualification import registry_factory

import hashlib
import io
import json
from modules.workspace.components import compact_json
import posixpath
import zipfile
from xml.etree import ElementTree

import pytest

from tests.support.workbench import app, client, import_rows, observations
from modules.workspace.components.store import Store
from modules.workspace.components.primitives import dump, now

from tests.support.acceptance import CVE, certify, open_case, review_case

DESCRIPTION = (
    "A boundary-checking error allows an authenticated user to read a "
    "restricted object when the documented configuration is enabled."
)


def source_record(store, description=DESCRIPTION):
    body = json.dumps(
        {
            "vulnerabilities": [
                {"cve": {"id": CVE, "descriptions": [{"lang": "en", "value": description}]}}
            ]
        }
    ).encode()
    digest = hashlib.sha256(body).hexdigest()
    relative = f"evidence/cve/{digest}.json"
    path = store.path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    record = {
        "id": CVE,
        "state": "PUBLISHED",
        "verification_status": "published",
        "description": description,
        "description_source": "CNA fixture via NVD",
        "publisher": "NVD",
        "source": "NVD",
        "retrieved_at": now(),
        "date_published": "2025-03-04T00:00:00Z",
        "date_updated": "2025-03-05T00:00:00Z",
        "public_url": f"https://nvd.nist.gov/vuln/detail/{CVE}",
        "record_path": relative,
        "body_sha256": digest,
        "cvss": None,
        "cvss_assessments": [],
        "epss": None,
        "kev": None,
        "references": [],
        "errors": [],
        "sources": [
            {
                "publisher": "NVD",
                "url": f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={CVE}",
                "public_url": f"https://nvd.nist.gov/vuln/detail/{CVE}",
                "retrieved_at": now(),
                "record_path": relative,
                "sha256": digest,
            }
        ],
    }
    with store.transaction() as db:
        db.execute(
            "INSERT OR REPLACE INTO cache VALUES(?,?,?)",
            ("cve-reference:" + CVE, dump(record), now()),
        )
    return record


def word_text(content, exhibit_id=None):
    """Read visible Word text and referenced SVG text, never image alt-text twice.

    Current exhibits are embedded vectors; native paragraphs alone omit their
    narrative. Selecting an exhibit also separates its recipient-facing quote
    from the deliberately complete source records in the appendix.
    """
    word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    drawing = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
    svg_blip = "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip"
    relationship = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    svg_text = "{http://www.w3.org/2000/svg}text"
    parts = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        relationships = ElementTree.fromstring(archive.read("word/_rels/document.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        for node in root.iter():
            if node.tag == word + "t" and exhibit_id is None:
                parts.append("".join(node.itertext()))
            elif node.tag == word + "drawing":
                metadata = node.find(".//" + drawing + "docPr")
                if exhibit_id is not None and (
                    metadata is None or metadata.attrib.get("title") != exhibit_id
                ):
                    continue
                for blip in node.iter(svg_blip):
                    target = posixpath.normpath("word/" + targets[blip.attrib[relationship]])
                    vector = ElementTree.fromstring(archive.read(target))
                    parts.extend("".join(text.itertext()) for text in vector.iter(svg_text))
    return " ".join(" ".join(parts).split())


def test_eol_report_retains_qualification_image_and_survives_schema_four_reopen(client, app):
    lead = review_case(
        client,
        open_case(client, app),
        narrative="This is a case-specific narrative retained verbatim.",
    )
    assert len(lead["evidence"]) == 1
    captured_website = lead["evidence"][0]
    assert captured_website["kind"] == "website" and captured_website["included"]
    report = certify(client, lead)
    folder = app.state.store.path(report["path"])
    before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    saved = compact_json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    assert saved["evidence"][0]["sha256"] == captured_website["sha256"]
    reopened = Store(app.state.store.root)
    assert reopened.one("PRAGMA user_version")["user_version"] >= 4
    assert reopened.package_available(report)
    assert before == {
        str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }
    assert client.get("/api/reports/" + report["id"] + "/pdf").content == before["notification.pdf"]
    text = word_text(before["notification.docx"])
    assert "began reviewing Shadowserver observations" in text
    assert "This is a case-specific narrative retained verbatim." not in text
    assert CVE not in text


def test_published_cve_with_retained_image_exports_offline_and_preserves_quotation(
    client, app, monkeypatch
):
    lead = open_case(client, app, CVE + ";test-product")
    record = source_record(app.state.store)
    lead = review_case(
        client,
        lead,
        cve_records=[record],
        narrative="Analyst narrative remains separate from the source quotation.",
    )
    assert len(lead["evidence"]) == 1
    assert lead["evidence"][0]["kind"] == "website" and lead["evidence"][0]["included"]

    def fail_network(*args, **kwargs):
        raise AssertionError("Rendering/certification must not fetch a live source")

    monkeypatch.setattr("requests.get", fail_network)
    preview = client.get(
        "/api/leads/" + lead["id"] + "/preview.pdf", params={"case_id": lead["case_id"]}
    )
    assert preview.status_code == 200, preview.text
    report = certify(client, lead)
    folder = app.state.store.path(report["path"])
    document = (folder / "notification.docx").read_bytes()
    text = word_text(document)
    assert DESCRIPTION in text
    assert word_text(document, "EX-VULNERABILITY").count(DESCRIPTION) == 1
    assert "began reviewing Shadowserver observations" in text
    data = compact_json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    # The CVE-only observation with no version is intentionally retained too.
    assert len(data["assets"]) == 4
    assert len(data["scope_source_entries"]) == 5
    assert data["observation_scope"]["excluded"] == 1
    assert {asset["ip"] for asset in data["assets"]} == {"1.1.1.1", "8.8.8.8", "9.9.9.9"}
    assert data["cves"] == [CVE]
    assert data["draft"]["cve_records"][0]["description"] == DESCRIPTION
    assert data["draft"]["cve_records"][0]["cvss"] is None
    assert data["draft"]["cve_records"][0]["epss"] is None
    assert data["draft"]["cve_records"][0]["kev"] is None
    for citation in data["composition"]["citations"]:
        if citation.get("record_path"):
            captured = folder / citation["record_path"]
            assert captured.is_file(), "Citation evidence must travel with the certified package"
            if citation.get("sha256"):
                assert hashlib.sha256(captured.read_bytes()).hexdigest() == citation["sha256"]


@pytest.mark.parametrize("action", ["fallback", "exclude"])
def test_unresolved_finding_requires_explicit_disposition_despite_website_screenshot(
    client, app, action
):
    lead = review_case(client, open_case(client, app, CVE))
    denied = client.post(
        "/api/leads/" + lead["id"] + "/finalize", params={"case_id": lead["case_id"]}
    )
    assert denied.status_code == 422
    decision = {
        "action": action,
        "reason": "The automated source was unavailable; the analyst recorded the disposition.",
    }
    if action == "fallback":
        decision.update(
            description=DESCRIPTION,
            publisher="Vendor security advisory",
            source_url=f"https://vendor.example/security/{CVE}",
            retrieved_at=now(),
            evidence_text=DESCRIPTION,
        )
    lead = review_case(client, lead, cve_dispositions={CVE: decision})
    report = certify(client, lead)
    folder = app.state.store.path(report["path"])
    data = compact_json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    assert data["draft"]["cve_dispositions"][CVE]["reason"] == decision["reason"]
    assert any(
        CVE in entry["source"]["fields"]["tag"]
        for group in data["qualified_lead"]["validated_leads"]
        for entry in group["entries"]
    )
    text = word_text((folder / "notification.docx").read_bytes())
    assert (DESCRIPTION in text) == (action == "fallback")


def test_pinned_draft_sources_and_explainers_survive_bank_update_and_later_scan(client, app):
    lead = open_case(client, app, CVE)
    original = source_record(app.state.store)
    lead = review_case(
        client,
        lead,
        cve_records=[original],
        narrative="Keep this analyst revision.",
        contact_name="Keep this recipient",
        selected_explainers=["attribution"],
    )
    prior_revision = lead["draft_revision"]
    prior_entry_ids = {entry["id"] for entry in lead["entries"]}
    prior_finding = app.state.store.one(
        "SELECT last_seen,workflow FROM awareness_findings WHERE condition=?", (CVE,)
    )
    pinned = lead["draft"]["explainer_snapshots"]
    selected = next(block for block in pinned if block["id"] == "attribution")
    response = client.put(
        "/api/explainers/attribution",
        json={
            "title": "Changed shared attribution block",
            "body": "Changed bank content must not replace saved draft text.",
            "sources": "https://www.arin.net/resources/registry/whois/",
            "expected_revision": selected["revision"],
        },
    )
    assert response.status_code == 200
    source_record(app.state.store, "A later source revision that was not adopted.")
    rows = observations()
    for row in rows:
        row.update(tag=CVE, version="7.3.26", timestamp="2026-12-03T00:00:00Z")
    # The real qualification gate stops already handled findings before
    # evaluation; a refreshed shared source must not change their case pin.
    import_rows(client, app, rows, "later-scan.csv")
    lead = client.get("/api/cases/" + lead["case_id"]).json()
    assert lead["draft"]["cve_records"][0]["description"] == DESCRIPTION
    assert (
        next(b for b in lead["draft"]["explainer_snapshots"] if b["id"] == "attribution")
        == selected
    )
    assert "began reviewing Shadowserver observations" in lead["draft"]["narrative"]
    assert lead["draft"]["contact_name"] == "Principal Executive / IT Director"
    assert lead["draft"]["reviewed"] is True
    assert lead["draft_revision"] == prior_revision
    assert {entry["id"] for entry in lead["entries"]} == prior_entry_ids
    # Already assigned conditions stop at the local qualification gate; their
    # later source rows remain in Dark Matter without rewriting the active case.
    assert client.get("/api/pending-leads").json() == []
    finding = app.state.store.one(
        "SELECT last_seen,workflow FROM awareness_findings WHERE condition=?", (CVE,)
    )
    assert finding == prior_finding and finding["workflow"] == "handled"
    archived = app.state.store.dark_matter.query(q="later-scan.csv")
    assert any(item["reason"] == "no_actionable_findings" for item in archived["items"])


def test_certified_package_unchanged_after_shared_content_refresh(client, app):
    lead = open_case(client, app, CVE)
    lead = review_case(client, lead, cve_records=[source_record(app.state.store)])
    report = certify(client, lead)
    folder = app.state.store.path(report["path"])
    before = {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }
    source_record(
        app.state.store, "New bank wording must not rewrite an already certified quotation."
    )
    response = client.put(
        "/api/explainers/cve",
        json={
            "title": "Updated CVE explainer",
            "body": "Updated wording.",
            "sources": "https://www.cve.org/",
            "expected_revision": client.get("/api/explainers/cve").json()["revision"],
        },
    )
    assert response.status_code == 200
    assert before == {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }
    current = client.get("/api/cases/" + lead["case_id"]).json()
    assert current["case"]["stage"] == "pending_notification"
    assert current["draft"]["cve_records"][0]["description"] == DESCRIPTION
    assert app.state.store.package_available(report)


def test_all_case_attribution_groups_render_from_saved_case_evidence(client, app):
    from tests.support.workbench import FakeRegistry

    first = open_case(client, app)

    class OtherRegistry(FakeRegistry):
        def lookup(self, ip):
            record = super().lookup(ip)
            return type(record)(
                record.ip,
                record.registry,
                record.source_url,
                record.retrieved_at,
                {**record.record, "contact": "support@another.com"},
            )

    app.state.intake.attribution_factory = registry_factory(OtherRegistry)
    import_rows(
        client,
        app,
        [{**observations()[0], "hostname": "mail.another.com", "ip": "8.8.4.4"}],
        "another.csv",
        start_notifications=False,
    )
    second = next(row for row in client.get("/api/leads").json() if row["id"] != first["id"])
    current = client.get("/api/cases/" + first["case_id"]).json()
    merged = client.post(
        "/api/entities/" + second["id"] + "/merge",
        json={
            "target_id": first["id"],
            "source_revision": second["draft_revision"],
            "target_revision": current["entity_revision"],
        },
    )
    assert merged.status_code == 200, merged.text
    unchanged = client.get("/api/cases/" + first["case_id"]).json()
    assert unchanged["entries"] == first["entries"]
    assert len(unchanged["domain_groups"]) == 1
    pending = client.get("/api/pending-leads").json()[0]
    added = client.post(
        "/api/pending-leads/" + pending["id"] + "/start",
        json={
            "expected_revision": pending["revision"],
            "case_id": first["case_id"],
            "expected_case_version": unchanged["case"]["version"],
        },
    )
    assert added.status_code == 200, added.text
    lead = client.get("/api/cases/" + first["case_id"]).json()
    assert len(lead["domain_groups"]) == 2
    # A later organization lookup must not rewrite already accepted case evidence.
    with app.state.store.transaction() as db:
        for group in lead["domain_groups"]:
            updated = dict(group["attribution"])
            updated["source_url"] = "https://example.com/a-newer-entity-lookup"
            db.execute(
                "UPDATE domain_groups SET attribution=? WHERE root_domain=?",
                (dump(updated), group["root_domain"]),
            )
    lead = review_case(client, lead)
    report = certify(client, lead)
    folder = app.state.store.path(report["path"])
    snapshot = compact_json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    assert len(snapshot["composition"]["attribution_groups"]) == 2
    assert {g["hostname"] for g in snapshot["composition"]["attribution_groups"]} == {
        "example.com",
        "another.com",
    }
    assert "a-newer-entity-lookup" not in json.dumps(snapshot["composition"]["attribution_groups"])
    text = word_text((folder / "notification.docx").read_bytes())
    assert "abuse@example.com" in text
    assert "support@another.com" in text
    assert "a-newer-entity-lookup" not in text


def test_new_case_does_not_inherit_unrelated_entity_cve_records(client, app):
    lead = open_case(client, app)
    closed = client.post(
        "/api/cases/" + lead["case_id"] + "/close",
        json={
            "expected_version": lead["case"]["version"],
            "disposition": "unable_to_contact",
            "conclusion": "Contact attempts concluded without delivery.",
            "closed_by": "Acceptance Analyst",
            "reviewed": True,
        },
    )
    assert closed.status_code == 200, closed.text
    unrelated = source_record(app.state.store)
    with app.state.store.transaction() as db:
        entity = db.execute("SELECT draft FROM leads WHERE id=?", (lead["id"],)).fetchone()
        projected = json.loads(entity["draft"])
        projected["cve_records"] = [unrelated]
        db.execute("UPDATE leads SET draft=? WHERE id=?", (dump(projected), lead["id"]))
    created = client.post(
        "/api/cases", json={"entity_id": lead["id"], "title": "Another EOL notification"}
    )
    assert created.status_code == 200, created.text
    assert created.json()["draft"]["cve_records"] == []
    assert all(CVE not in entry["source"]["fields"]["tag"] for entry in created.json()["entries"])
