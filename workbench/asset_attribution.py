"""Bounded supplemental asset checks; report and frozen section bytes are untouched."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import sqlite3
from contextlib import ExitStack
import json
import threading

from attribution import AttributionModule, CandidateIP, EvidenceStore, Settings
from attribution.matching import domain_equal_or_below, normalize_domain
from attribution.rdap import eligible_ip, normalize_ip

from .attribution_bridge import checked_result
from .attribution_display import attribution_summaries
from .primitives import now, uid

MAX_ASSETS = 1000
ACTIVE = ("queued", "running", "cancelling")


def _key(entry):
    try:
        host = normalize_domain(entry["source"]["fields"]["hostname"])
        root = normalize_domain(entry["root_domain"])
        ip = normalize_ip(entry["ip"])
        if not domain_equal_or_below(host, root) or not eligible_ip(ip):
            return None
        return root, host, ip
    except KeyError, TypeError, ValueError:
        return None


def case_assets(store, case_id):
    """Read one case scope, never the entity's newer observations or attribution."""
    with store.read_snapshot() as db:
        case = db.execute("SELECT id,entity_id FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise ValueError("Notification case not found")
        entries = [
            {**json.loads(row["payload"]), "id": row["id"], "root_domain": row["root_domain"]}
            for row in db.execute(
                """SELECT e.* FROM case_entries ce JOIN entries e ON e.id=ce.entry_id
                  JOIN case_groups cg ON cg.case_id=ce.case_id AND cg.root_domain=e.root_domain
                  WHERE ce.case_id=? ORDER BY ce.rowid""",
                (case_id,),
            )
        ]
        groups = [
            {**dict(row), "attribution": json.loads(row["attribution"])}
            for row in db.execute("SELECT * FROM case_groups WHERE case_id=?", (case_id,))
        ]
        saved = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM case_asset_attributions WHERE case_id=? ORDER BY rowid", (case_id,)
            )
        ]
    return dict(case), entries, groups, saved


def asset_state(store, case_id):
    case, entries, groups, saved = case_assets(store, case_id)
    by_id = {entry["id"]: entry for entry in entries}
    latest, supported = {}, set()
    selected = {
        group["root_domain"]: by_id.get(group["attribution_entry_id"], {}) for group in groups
    }
    groups_by_root = {group["root_domain"]: group for group in groups}
    for summary in attribution_summaries(store, {"entries": entries, "domain_groups": groups}):
        proof = groups_by_root.get(summary["root_domain"], {}).get("attribution", {})
        intact = True
        if proof.get("result_id"):
            try:
                path = store.root / "attribution.sqlite3"
                if not path.is_file():
                    raise ValueError("Saved attribution database is unavailable")
                with EvidenceStore(path) as original_store:
                    original = checked_result(
                        original_store, proof["result_id"], summary["root_domain"]
                    )
                    _verify_snapshots(original_store, original)
            except OSError, sqlite3.Error, ValueError, KeyError:
                intact = False
        if intact and summary.get("supported") and summary.get("validated_ip"):
            original_key = _key(selected.get(summary["root_domain"], {}))
            for entry in entries:
                key = _key(entry)
                if key and (key[0], key[2]) == (summary["root_domain"], summary["validated_ip"]):
                    if summary["method"] != "dns" or key == original_key:
                        supported.add(key)
    with ExitStack() as stack:
        evidence_store, unavailable = None, None
        if saved:
            try:
                path = store.root / "attribution.sqlite3"
                if not path.is_file():
                    raise ValueError("Saved attribution database is unavailable")
                evidence_store = stack.enter_context(EvidenceStore(path))
            except (OSError, sqlite3.Error, ValueError) as error:
                unavailable = str(error)
        for record in saved:
            entry = by_id.get(record["entry_id"], {})
            key = _key(entry)
            if key:
                latest[key] = record
                if record["status"] == "matched":
                    try:
                        if unavailable:
                            raise ValueError(unavailable)
                        result = checked_result(
                            evidence_store, record["result_id"], record["root_domain"]
                        )
                        _check_candidate(result, entry)
                        _verify_snapshots(evidence_store, result)
                        supported.add(key)
                    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
                        latest[key] = {
                            **record,
                            "status": "evidence_unavailable",
                            "error": str(error),
                        }
    rows = []
    for entry in entries:
        key = _key(entry)
        lookup = latest.get(key)
        rows.append(
            {
                "entry_id": entry["id"],
                "eligible": key is not None,
                "supported": key in supported,
                "status": "matched"
                if key in supported
                else lookup["status"]
                if lookup
                else "not_checked"
                if key
                else "nonpublic_or_invalid",
                "latest_lookup": lookup,
            }
        )
    remaining = {_key(entry) for entry in entries if _key(entry) not in supported} - {None}
    return {
        "case_id": case["id"],
        "assets": rows,
        "remaining": len(remaining),
        "batch_limit": MAX_ASSETS,
    }, entries


def saved_result(store, lookup_id):
    record = store.one("SELECT * FROM case_asset_attributions WHERE id=?", (lookup_id,))
    if not record:
        raise ValueError("Saved asset lookup not found")
    _, entries, _, _ = case_assets(store, record["case_id"])
    entry = next((entry for entry in entries if entry["id"] == record["entry_id"]), None)
    if not entry:
        raise ValueError("Saved asset is outside this notification case")
    if not (store.root / "attribution.sqlite3").is_file():
        raise ValueError("Saved attribution database is unavailable")
    with EvidenceStore(store.root / "attribution.sqlite3") as evidence_store:
        result = checked_result(evidence_store, record["result_id"], record["root_domain"])
        _check_candidate(result, entry)
        _verify_snapshots(evidence_store, result)
        records = {
            e["snapshot_id"]: evidence_store.snapshot(e["snapshot_id"]).record()
            for e in result.get("evidence", []) + result.get("partial_evidence", [])
        }
        snapshots = {
            e["snapshot_id"]: evidence_store.snapshot(e["snapshot_id"]).metadata()
            for e in result.get("evidence", []) + result.get("partial_evidence", [])
        }
    return {**record, "result": result, "records": records, "snapshots": snapshots}


def _verify_snapshots(evidence_store, result):
    snapshot_ids = {
        identity
        for attempt in result.get("attempts", [])
        for identity in attempt.get("snapshot_ids", [])
    }
    for evidence in result.get("evidence", []) + result.get("partial_evidence", []):
        snapshot_ids.add(evidence["snapshot_id"])
        snapshot_ids.update(evidence.get("supporting_snapshot_ids", []))
    for identity in snapshot_ids:
        snapshot = evidence_store.snapshot(identity)
        if hashlib.sha256(snapshot.body).hexdigest() != snapshot.body_sha256:
            raise ValueError("Saved attribution response failed its integrity check")


def _check_candidate(result, entry):
    if _key(entry) is None:
        raise ValueError("Saved asset is no longer eligible for attribution")
    candidates = result.get("candidates", [])
    if len(candidates) != 1 or candidates[0] != {
        "entry_id": entry["id"],
        "ip": _key(entry)[2],
        "hostname": _key(entry)[1],
    }:
        raise ValueError("Saved lookup does not identify this original asset")
    if result["status"] == "matched" and (
        result.get("matched_entry_id") != entry["id"]
        or result.get("matched_ip") != _key(entry)[2]
        or not result.get("evidence")
    ):
        raise ValueError("Saved attribution does not identify this original asset")


class AssetAttributionJobs:
    def __init__(self, store, module_factory=None):
        self.store = store
        self.module_factory = module_factory or AttributionModule.open
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="companion-assets")
        self.lock = threading.RLock()
        self.jobs = {}

    def busy(self):
        with self.lock:
            return any(job["status"] in ACTIVE for job in self.jobs.values())

    def state(self, case_id):
        result, _ = asset_state(self.store, case_id)
        with self.lock:
            result["job"] = next(
                (
                    self.get(job["id"])
                    for job in reversed(list(self.jobs.values()))
                    if job["case_id"] == case_id
                ),
                None,
            )
        return result

    def start(self, case_id, entry_id=None):
        state, entries = asset_state(self.store, case_id)
        statuses = {row["entry_id"]: row for row in state["assets"]}
        if entry_id is not None and entry_id not in statuses:
            raise ValueError("Asset is outside this notification case")
        selected, seen = [], set()
        for entry in entries:
            status, key = statuses[entry["id"]], _key(entry)
            if entry_id is not None and entry_id != entry["id"]:
                continue
            if not key or key in seen or (entry_id is None and status["supported"]):
                continue
            seen.add(key)
            selected.append(entry)
        if not selected:
            raise ValueError("No remaining public assets are eligible for attribution")
        if len(selected) > MAX_ASSETS:
            raise ValueError(
                f"A batch supports up to {MAX_ASSETS:,} distinct assets; select individual assets in this case"
            )
        with self.lock:
            active = [job for job in self.jobs.values() if job["status"] in ACTIVE]
            if any(job["case_id"] == case_id for job in active):
                raise ValueError("Attribution is already running for this notification")
            if len(active) >= 4:
                raise ValueError("Four asset attribution jobs are already queued or running")
            for old in [key for key, job in self.jobs.items() if job["status"] not in ACTIVE][:-20]:
                self.jobs.pop(old, None)
            identity = uid()
            self.jobs[identity] = {
                "id": identity,
                "case_id": case_id,
                "status": "queued",
                "created_at": now(),
                "total": len(selected),
                "completed": 0,
                "current_asset": None,
                "results": [],
                "errors": [],
                "cancel": threading.Event(),
            }
            self.pool.submit(self._run, identity, selected, entry_id is not None)
            return self.get(identity)

    def _run(self, identity, entries, refresh):
        job = self.jobs[identity]
        with self.lock:
            job.update(status="running", started_at=now())
        try:
            config = self.store.settings()
            settings = Settings(
                timeout=config["timeout"], retries=config["retries"], interval=config["interval"]
            )
            with self.module_factory(
                self.store.root / "attribution.sqlite3",
                settings=settings,
                cancel_event=job["cancel"],
            ) as module:
                for entry in entries:
                    if job["cancel"].is_set():
                        break
                    key = _key(entry)
                    with self.lock:
                        job["current_asset"] = {"hostname": key[1], "ip": key[2]}
                    try:
                        result = module.attribute(
                            key[0], [CandidateIP(entry["id"], key[2], key[1])], refresh=refresh
                        )
                        saved = checked_result(module.store, result.result_id, key[0])
                        _check_candidate(saved, entry)
                        record = {
                            "id": uid(),
                            "case_id": job["case_id"],
                            "entry_id": entry["id"],
                            "result_id": result.result_id,
                            "root_domain": key[0],
                            "status": result.status,
                            "created_at": now(),
                        }
                        with self.store.transaction() as db:
                            current = db.execute(
                                "SELECT 1 FROM case_entries WHERE case_id=? AND entry_id=?",
                                (job["case_id"], entry["id"]),
                            ).fetchone()
                            if not current:
                                raise ValueError("Asset is no longer in this notification")
                            db.execute(
                                "INSERT INTO case_asset_attributions VALUES(?,?,?,?,?,?,?)",
                                tuple(record.values()),
                            )
                            entity = db.execute(
                                "SELECT entity_id FROM cases WHERE id=?", (job["case_id"],)
                            ).fetchone()
                            self.store.log(
                                db,
                                "asset_attribution",
                                f"Asset attribution {result.status}: {key[1]} / {key[2]}; lookup {result.result_id}",
                                entity["entity_id"],
                                job["case_id"],
                            )
                        with self.lock:
                            job["results"].append(record)
                    except Exception as error:
                        if not job["cancel"].is_set():
                            with self.lock:
                                job["errors"].append({"entry_id": entry["id"], "error": str(error)})
                    with self.lock:
                        job["completed"] += 1
            with self.lock:
                job["status"] = "cancelled" if job["cancel"].is_set() else "completed"
        except Exception as error:
            with self.lock:
                job["errors"].append({"error": str(error)})
                job["status"] = "cancelled" if job["cancel"].is_set() else "failed"
        finally:
            with self.lock:
                job.update(finished_at=now(), current_asset=None)

    def get(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError(
                    "Attribution job is unavailable; completed lookups remain saved with the assets"
                )
            return deepcopy(
                {key: value for key, value in self.jobs[identity].items() if key != "cancel"}
            )

    def cancel(self, identity):
        with self.lock:
            self.get(identity)
            job = self.jobs[identity]
            if job["status"] in ACTIVE:
                job["cancel"].set()
                job["status"] = "cancelling"
            return self.get(identity)

    def close(self):
        with self.lock:
            for job in self.jobs.values():
                job["cancel"].set()
        self.pool.shutdown(wait=False, cancel_futures=True)


def adopt_attribution(store, lookup_id, expected_revision):
    """Explicitly select saved exact evidence for one editable case domain group."""
    from .attribution_bridge import attribution_record
    from .cases import Cases
    from .primitives import dump
    from .reviews.queries import SectionReviewQueries

    lookup = saved_result(store, lookup_id)
    result = lookup["result"]
    if result["status"] != "matched":
        raise ValueError("Only a saved exact match can be used for report attribution")
    with EvidenceStore(store.root / "attribution.sqlite3") as evidence_store:
        evidence = result["evidence"][0]
        snapshot = evidence_store.snapshot(evidence["snapshot_id"])
        if hashlib.sha256(snapshot.body).hexdigest() != snapshot.body_sha256:
            raise ValueError("Saved attribution response failed its integrity check")
        record = attribution_record(
            evidence_store, result["result_id"], lookup["root_domain"], result["policy"], evidence
        )
    with store.transaction() as db:
        case = Cases(store).require(db, lookup["case_id"], editable=True)
        if case["draft_revision"] != expected_revision:
            raise ValueError("This draft changed. Reload before selecting attribution")
        group = db.execute(
            "SELECT * FROM case_groups WHERE case_id=? AND root_domain=?",
            (lookup["case_id"], lookup["root_domain"]),
        ).fetchone()
        if not group:
            raise ValueError("Asset domain is outside this notification")
        primary = db.execute(
            "SELECT root_domain FROM case_groups WHERE case_id=? ORDER BY rowid LIMIT 1",
            (lookup["case_id"],),
        ).fetchone()
        sections = ["attribution"]
        if (
            primary["root_domain"] == group["root_domain"]
            and group["attribution_entry_id"] != lookup["entry_id"]
        ):
            sections.append("vulnerabilities")
        SectionReviewQueries(store).assert_editable(db, lookup["case_id"], sections)
        db.execute(
            "UPDATE case_groups SET attribution_entry_id=?,attribution=? WHERE case_id=? AND root_domain=?",
            (lookup["entry_id"], dump(record), lookup["case_id"], lookup["root_domain"]),
        )
        draft = json.loads(case["draft"])
        draft["reviewed"] = False
        db.execute(
            "UPDATE cases SET draft=?,draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
            (dump(draft), now(), lookup["case_id"]),
        )
        store.log(
            db,
            "asset_attribution_selected",
            f"Selected attribution for {lookup['root_domain']}; lookup {result['result_id']}",
            case["entity_id"],
            lookup["case_id"],
        )
    store.export_lead(case["entity_id"], lookup["case_id"])
    return {"case_id": lookup["case_id"], "result_id": result["result_id"]}
