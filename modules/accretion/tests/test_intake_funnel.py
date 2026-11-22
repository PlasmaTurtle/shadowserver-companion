"""Qualification gates every downstream Accretion action, including retries."""

from tests.support.qualification import capture_website

import json

import httpx
import pytest
from attribution import AttributionModule, EvidenceStore, RdapProvider, Settings

from modules.accretion.components import (
    accretion,
    awareness,
    intake_progress,
    evaluation,
)
from modules.accretion.components.intake_service import IntakeService
from modules.accretion.tests.support.intake import report, row, seed
from modules.accretion.components import intake_filter as filtering
from modules.attribution.components import attribution_bridge
from modules.leads.components import lead_queue
from modules.workspace.components.store import Store


@pytest.fixture
def funnel(tmp_path, monkeypatch):
    store = Store(tmp_path / "workspace")
    seed(store.root)
    state = {"outcome": "qualified", "phase": None, "events": [], "scores": []}

    def server(request):
        url = str(request.url)
        if "data.iana.org" in url:
            body = {"services": [[["0.0.0.0/0"], ["https://rdap.arin.net/registry/"]]]}
        elif state["outcome"] == "deferred":
            raise httpx.ConnectError("Synthetic registry outage", request=request)
        else:
            ip = url.rsplit("/", 1)[-1]
            props = [["fn", {}, "text", "Example Medical Center"]]
            if state["outcome"] == "no_match":
                props = [["fn", {}, "text", "Unrelated Corporation"]]
            elif state["outcome"] == "qualified":
                props.append(["email", {}, "text", "support@" + state.get("domain", "example.com")])
            body = {
                "objectClassName": "ip network",
                "handle": "SYNTHETIC-NETWORK",
                "startAddress": ip,
                "endAddress": ip,
                "entities": [
                    {
                        "objectClassName": "entity",
                        "handle": "SYNTHETIC-REGISTRANT",
                        "roles": ["registrant"],
                        "vcardArray": ["vcard", props],
                    }
                ],
            }
        return httpx.Response(
            200,
            headers={"content-type": "application/rdap+json"},
            stream=httpx.ByteStream(json.dumps(body).encode()),
        )

    def open_module(path, settings=None, cancel_event=None):
        evidence = EvidenceStore(path)
        provider = RdapProvider(
            evidence, Settings(interval=0, retries=0), transport=httpx.MockTransport(server)
        )
        module = AttributionModule(evidence, providers=[provider])
        module._owns_store = True
        module._owned = [provider]
        return module

    monkeypatch.setattr(attribution_bridge.AttributionModule, "open", open_module)
    intake = IntakeService(store, capture=capture_website)
    original_publish = intake_progress.publish
    original_qualify = attribution_bridge.RegistrationAttribution.qualify
    original_score = accretion.score_lead
    original_evaluate = evaluation.evaluate_scope
    original_verify = evaluation.verify
    original_associate = awareness.associate
    original_accept = intake.associate_lead
    original_register = lead_queue.register_group

    def publish(*args, **kwargs):
        state["phase"] = args[3]
        return original_publish(*args, **kwargs)

    def qualify(*args, **kwargs):
        state["events"].append("qualify_start")
        result = original_qualify(*args, **kwargs)
        state["events"].append("qualify_" + result.status)
        return result

    def score(*args, **kwargs):
        assert state["phase"] == "evaluate", "Scoring escaped the Evaluate stage"
        state["events"].append("score")
        result = original_score(*args, **kwargs)
        return result

    def evaluate(*args, **kwargs):
        result = original_evaluate(*args, **kwargs)
        state["scores"].append(result.payload())
        return result

    def verify(*args, **kwargs):
        state["events"].append("verify")
        return original_verify(*args, **kwargs)

    def associate(*args, **kwargs):
        assert state["phase"] == "associate", "Association escaped the Associate stage"
        state["events"].append("associate")
        return original_associate(*args, **kwargs)

    def accept(*args, **kwargs):
        state["events"].append("accept")
        return original_accept(*args, **kwargs)

    def register(*args, **kwargs):
        state["events"].append("register")
        return original_register(*args, **kwargs)

    monkeypatch.setattr(intake_progress, "publish", publish)
    monkeypatch.setattr(attribution_bridge.RegistrationAttribution, "qualify", qualify)
    monkeypatch.setattr(accretion, "score_lead", score)
    monkeypatch.setattr(evaluation, "evaluate_scope", evaluate)
    monkeypatch.setattr(evaluation, "verify", verify)
    monkeypatch.setattr(awareness, "associate", associate)
    monkeypatch.setattr(intake, "associate_lead", accept)
    monkeypatch.setattr(lead_queue, "register_group", register)
    return store, intake, state


def ingest(funnel):
    store, intake, _ = funnel
    queued = intake.enqueue("scan_http_vulnerable.csv", report([row()]))
    intake.process(queued["id"])
    imported = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert imported["status"] != "error", imported["error"]
    return imported, store.one("SELECT * FROM jobs WHERE import_id=?", (queued["id"],))


def assert_stopped(store, state):
    assert not {"score", "verify", "associate", "accept", "register"}.intersection(
        state["events"]
    ), state["events"]
    assert state["scores"] == []
    assert store.dark_matter.query(include_promoted=True)["total"] == 1
    for table in (
        "lead_queue",
        "leads",
        "awareness_assets",
        "awareness_findings",
        "awareness_observations",
    ):
        assert store.one("SELECT count(*) n FROM " + table)["n"] == 0, table


@pytest.mark.parametrize("outcome", ["no_match", "deferred", "review"])
def test_unsuccessful_qualification_stops_every_downstream_stage(funnel, outcome):
    store, _, state = funnel
    state["outcome"] = outcome
    imported, job = ingest(funnel)
    assert job["status"] == outcome
    assert imported["status"] == ("needs_retry" if outcome == "deferred" else "done")
    assert_stopped(store, state)


def test_no_filter_survivors_never_open_qualification_or_later_stages(funnel, monkeypatch):
    store, intake, state = funnel

    def forbidden(*args, **kwargs):
        raise AssertionError("No filtered groups survived to invoke downstream work")

    monkeypatch.setattr(
        "modules.accretion.components.qualification.RegistrationAttribution", forbidden
    )
    monkeypatch.setattr(store, "export_all", forbidden)
    original = report([row(region="Virginia")])
    queued = intake.enqueue("scan_http_vulnerable.csv", original)
    intake.process(queued["id"])
    imported = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert imported["status"] == "done", imported["error"]
    assert imported["groups_total"] == 0
    assert json.loads(imported["rejected"]) == {"outside_jurisdiction": 1}
    assert store.path(imported["path"]).read_bytes() == original
    assert state["events"] == []
    for table in ("jobs", "lead_queue", "awareness_assets", "awareness_findings"):
        assert store.one("SELECT count(*) n FROM " + table)["n"] == 0


def test_success_orders_qualification_ranking_and_association(funnel):
    store, _, state = funnel
    imported, job = ingest(funnel)
    assert job["status"] == "qualified"
    events = state["events"]
    assert events.index("qualify_qualified") < events.index("score")
    assert events.index("score") < events.index("accept") < events.index("associate")
    assert events.index("score") < events.index("register")
    assert len(state["scores"]) == 1
    score = state["scores"][0]
    assert next(f for f in score["factors"]["quality"] if f["id"] == "entity")["value"] == 1.0
    queued = store.one("SELECT * FROM lead_queue WHERE import_id=?", (imported["id"],))
    assert queued["qualified"] == 1 and queued["entity_id"]
    assert json.loads(queued["intake_score"]) == score
    assert store.one("SELECT sum(admitted) n FROM awareness_observations")["n"] == 1


def test_dismissing_review_does_not_run_downstream_work(funnel, monkeypatch):
    store, intake, state = funnel
    state["outcome"] = "review"
    _, job = ingest(funnel)

    def forbidden(*args, **kwargs):
        raise AssertionError("Dismissing unqualified work must not export downstream artifacts")

    monkeypatch.setattr(store, "export_all", forbidden)
    result = intake.review_group(job["id"], job["attribution_result_id"], None, "dismiss")
    assert result["lead_id"] is None
    assert store.one("SELECT status FROM jobs WHERE id=?", (job["id"],))["status"] == "dismissed"
    assert_stopped(store, state)


def test_completed_import_does_not_export_again_without_new_associations(funnel, monkeypatch):
    store, intake, state = funnel
    imported, _ = ingest(funnel)
    exports = []
    monkeypatch.setattr(store, "export_all", lambda: exports.append("export"))
    state["events"].clear()

    intake.process(imported["id"])

    current = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    assert current["status"] == "done", current["error"]
    assert state["events"] == []
    assert exports == []


def test_retry_recovers_export_after_association_has_committed(funnel, monkeypatch):
    store, intake, state = funnel
    exports = []

    def export():
        exports.append("export")
        if len(exports) == 1:
            raise OSError("Synthetic export publication failure")

    monkeypatch.setattr(store, "export_all", export)
    queued = intake.enqueue("scan_http_vulnerable.csv", report([row()]))
    intake.process(queued["id"])
    imported = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert imported["status"] == "error"
    assert "Synthetic export publication failure" in imported["error"]
    assert (
        store.one("SELECT status FROM jobs WHERE import_id=?", (queued["id"],))["status"]
        == "qualified"
    )
    state["events"].clear()

    intake.retry(queued["id"])
    intake.process(queued["id"])

    current = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert current["status"] == "done", current["error"]
    assert exports == ["export", "export"]
    assert state["events"] == []
    assert len(state["scores"]) == 1


def test_restart_recovers_export_committed_with_qualification(funnel, monkeypatch):
    store, intake, state = funnel

    class InterruptedWorker(BaseException):
        pass

    def interrupted_export():
        raise InterruptedWorker()

    monkeypatch.setattr(store, "export_all", interrupted_export)
    queued = intake.enqueue("scan_http_vulnerable.csv", report([row()]))
    with pytest.raises(InterruptedWorker):
        intake.process(queued["id"])
    imported = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert imported["status"] == "done"
    assert json.loads(imported["config"])["intake_progress"]["exports_pending"]
    assert (
        store.one("SELECT status FROM jobs WHERE import_id=?", (queued["id"],))["status"]
        == "qualified"
    )
    state["events"].clear()
    exports = []
    resumed_store = Store(store.root)
    resumed = IntakeService(resumed_store, capture=capture_website)
    monkeypatch.setattr(resumed_store, "export_all", lambda: exports.append("export"))

    resumed.process(queued["id"])

    current = resumed_store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert current["status"] == "done", current["error"]
    assert not json.loads(current["config"])["intake_progress"]["exports_pending"]
    assert exports == ["export"]
    assert state["events"] == []
    assert len(state["scores"]) == 1


@pytest.mark.parametrize("retry_outcome", ["no_match", "qualified"])
def test_mixed_import_exports_only_when_retry_associates_new_work(
    funnel, monkeypatch, retry_outcome
):
    store, intake, state = funnel
    outcomes = {"example.com": "qualified", "example.net": "no_match"}
    original_qualify = attribution_bridge.RegistrationAttribution.qualify

    def qualify(client, group, **kwargs):
        state["domain"] = group.root_domain
        state["outcome"] = outcomes[group.root_domain]
        return original_qualify(client, group, **kwargs)

    monkeypatch.setattr(attribution_bridge.RegistrationAttribution, "qualify", qualify)
    exports = []
    monkeypatch.setattr(store, "export_all", lambda: exports.append("export"))
    queued = intake.enqueue(
        "scan_http_vulnerable.csv",
        report([row(), row(hostname="mail.example.net", ip="9.9.9.9")]),
    )
    intake.process(queued["id"])
    imported = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert imported["status"] == "done", imported["error"]
    assert imported["qualified"] == 1
    assert exports == ["export"]
    sibling = store.one(
        "SELECT * FROM jobs WHERE import_id=? AND domain='example.net'", (queued["id"],)
    )
    assert sibling["status"] == "no_match"
    prior_score = store.one(
        "SELECT intake_score FROM lead_queue WHERE import_id=? AND root_domain='example.com'",
        (queued["id"],),
    )["intake_score"]
    state["events"].clear()
    state["scores"].clear()
    exports.clear()
    outcomes["example.net"] = retry_outcome

    intake.retry_group(sibling["id"], sibling["attribution_result_id"])
    intake.process(queued["id"])

    current = store.one("SELECT * FROM imports WHERE id=?", (queued["id"],))
    assert current["status"] == "done", current["error"]
    assert (
        store.one("SELECT status FROM jobs WHERE id=?", (sibling["id"],))["status"] == retry_outcome
    )
    assert (
        store.one(
            "SELECT intake_score FROM lead_queue WHERE import_id=? AND root_domain='example.com'",
            (queued["id"],),
        )["intake_score"]
        == prior_score
    )
    if retry_outcome == "qualified":
        assert exports == ["export"]
        assert len(state["scores"]) == 1
        assert state["events"].count("associate") == 1
        assert current["qualified"] == 2
    else:
        assert exports == []
        assert state["scores"] == []
        assert not {"score", "verify", "associate", "accept", "register"}.intersection(
            state["events"]
        )
        assert current["qualified"] == 1


def test_queue_persistence_never_runs_implicit_scoring(funnel, monkeypatch):
    store, intake, state = funnel
    fields = row()
    imported = intake.enqueue("scan_http_vulnerable.csv", report([fields]))
    entries = [{"source": {"fields": fields}, "normalized": {}}]

    def forbidden(*args, **kwargs):
        raise AssertionError("Queue persistence must not invoke Accretion scoring")

    monkeypatch.setattr(accretion, "score_lead", forbidden)
    with store.transaction() as db:
        queue_id = lead_queue.register_group(db, imported["id"], "example.com", entries)
    queued = store.one("SELECT * FROM lead_queue WHERE id=?", (queue_id,))
    assert json.loads(queued["intake_score"]) == {}
    assert queued["qualified"] == 0
    assert state["scores"] == []


@pytest.mark.parametrize("resume", ["retry", "review"])
def test_resume_scores_once_from_captured_policy_and_cve_evidence(funnel, monkeypatch, resume):
    store, intake, state = funnel
    state["outcome"] = "deferred" if resume == "retry" else "review"
    imported, job = ingest(funnel)
    assert_stopped(store, state)
    config = json.loads(imported["config"])
    payload = job["payload"]
    seed(store.root, score=4.0)
    settings = store.settings()
    settings["accretion_priority_cities"] = ["Burnsville"]
    monkeypatch.setattr(store, "settings", lambda: dict(settings))

    def forbidden(*args, **kwargs):
        raise AssertionError("Qualification resume must not re-vet captured CVE evidence")

    monkeypatch.setattr(filtering, "vet_cves", forbidden)
    state["outcome"] = "qualified"
    if resume == "retry":
        intake.retry(imported["id"])
        intake.process(imported["id"])
    else:
        intake.review_group(job["id"], job["attribution_result_id"], 0, "accept")
    current = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    assert current["status"] == "done", current["error"]
    assert store.one("SELECT status FROM jobs WHERE id=?", (job["id"],))["status"] == "qualified"
    assert store.one("SELECT payload FROM jobs WHERE id=?", (job["id"],))["payload"] == payload
    assert len(state["scores"]) == 1
    score = state["scores"][0]
    assert score["policy"] == config["accretion_policy"]
    assert score["cves"][0]["cvss"] == 9.8
    assert score["policy"]["priority_cities"] == []
    assert next(f for f in score["factors"]["quality"] if f["id"] == "entity")["value"] == 1.0
    assert json.loads(store.one("SELECT intake_score FROM lead_queue")["intake_score"]) == score
    intake.process(imported["id"])
    assert len(state["scores"]) == 1


def test_waiting_review_replaces_unqualified_queue_score_when_reconciled(funnel):
    store, intake, state = funnel
    state["outcome"] = "review"
    _, first_job = ingest(funnel)
    second = intake.enqueue(
        "scan_http_vulnerable.csv", report([row(timestamp="2026-11-12 10:00:00")])
    )
    intake.process(second["id"])
    waiting = store.one("SELECT * FROM jobs WHERE import_id=?", (second["id"],))
    assert waiting["status"] == "review"
    assert state["scores"] == []
    # An injected score on unqualified work cannot replace Evaluate after admission.
    legacy_score = {"aggregate": 1, "quality": 1, "urgency": 1, "temperature": "cool"}
    with store.transaction() as db:
        legacy_queue_id = lead_queue.register_group(
            db,
            second["id"],
            "example.com",
            json.loads(waiting["payload"]),
            intake_score=legacy_score,
        )
    seed(store.root, score=4.0)
    result = intake.review_group(first_job["id"], first_job["attribution_result_id"], 0, "accept")
    assert waiting["id"] in result["reconciled_jobs"]
    assert len(state["scores"]) == 2
    assert store.one("SELECT count(*) n FROM attribution_reviews")["n"] == 1
    saved = store.one("SELECT * FROM lead_queue WHERE id=?", (legacy_queue_id,))
    assert saved["qualified"] == 1
    score = json.loads(saved["intake_score"])
    assert score != legacy_score and score == state["scores"][1]
    assert score["cves"][0]["cvss"] == 9.8
    assert next(f for f in score["factors"]["quality"] if f["id"] == "entity")["value"] == 1.0
    assert (
        store.one("SELECT status FROM jobs WHERE id=?", (waiting["id"],))["status"] == "qualified"
    )


@pytest.mark.parametrize("outcome", ["qualified", "no_match", "dismiss"])
def test_group_outcome_does_not_rewrite_filtered_sibling(funnel, outcome):
    store, intake, state = funnel
    state["outcome"] = "review" if outcome == "dismiss" else outcome
    original = report([row(), row(tag="eol-php", version="")])
    imported = intake.enqueue("scan_http_vulnerable.csv", original)
    intake.process(imported["id"])
    saved = store.one("SELECT * FROM imports WHERE id=?", (imported["id"],))
    assert saved["status"] == "done", saved["error"]
    assert json.loads(saved["rejected"]) == {"missing_version": 1}
    job = store.one("SELECT * FROM jobs WHERE import_id=?", (imported["id"],))
    payload = json.loads(job["payload"])
    assert len(payload) == 1
    assert payload[0]["source"]["fields"]["tag"] == "CVE-2026-12345"
    if outcome == "dismiss":
        assert job["status"] == "review"
        intake.review_group(job["id"], job["attribution_result_id"], None, "dismiss")
    else:
        assert job["status"] == outcome
    archived = store.dark_matter.query(
        filters=[{"field": "import_id", "value": imported["id"]}], include_promoted=True
    )["items"]
    filtered = next(record for record in archived if record["raw_fields"]["tag"] == "eol-php")
    assert (filtered["outcome"], filtered["reason"]) == ("rejected", "missing_version")
    first = next(record for record in archived if record["raw_fields"]["tag"] == "CVE-2026-12345")
    if outcome == "qualified":
        assert (first["outcome"], first["reason"]) == ("promoted", "qualified")
        assert len(state["scores"]) == 1
        assert state["events"].count("associate") == 1
        assert store.one("SELECT count(*) n FROM awareness_observations")["n"] == 1
        assert store.one("SELECT id FROM awareness_findings WHERE condition LIKE 'eol%'") is None
    else:
        reason = "attribution_dismissed" if outcome == "dismiss" else "attribution_no_match"
        assert first["reason"] == reason and not first["promoted"]
        assert not {"score", "verify", "associate", "accept", "register"}.intersection(
            state["events"]
        )
        assert store.one("SELECT count(*) n FROM lead_queue")["n"] == 0
        assert store.one("SELECT count(*) n FROM awareness_observations")["n"] == 0
    assert store.path(saved["path"]).read_bytes() == original
