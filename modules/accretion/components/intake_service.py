"""Accretion: filter source rows, qualify their evidence, and rank outreach leads."""

from __future__ import annotations

from .intake_filter import filter_report, IntakeInterrupted
from .intake.records import SourceObservation
from .report import Report, ReportCandidate
from .qualified_lead import QualifiedLead
from .evaluated_lead import EvaluatedLead
from .association import AssociationResult
from .intake.files import SourceFormatError
from .dark_matter import prepare_batch, enqueue_prepared, enqueue_outcome, enqueue_batch

import hashlib
import io
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

from modules.accretion.components.intake import CandidateGroup, restore_observation
from .accretion import normalize_policy
from modules.workspace.components.store import Store
from modules.workspace.components.primitives import dump, now, uid
from modules.attribution.components.attribution_bridge import (
    attribution_record,
    checked_result,
)
from attribution import EvidenceStore
from modules.accretion.components.report_profiles import (
    resolve_profile,
    PROFILE_VERSION,
)

LOG = logging.getLogger(__name__)
MAX_UPLOAD = 50 * 1024 * 1024
POLICY_VERSION = 14


class IntakeService:
    def __init__(self, store: Store, *, attribution_factory=None, capture=None):
        self.store = store
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.attribution_factory = attribution_factory
        self.capture = capture
        self.last_scan = 0
        self.review_backlog_checked = False
        self.inbox_seen = {}

    def enqueue(self, name, content):
        if not content or len(content) > MAX_UPLOAD:
            raise ValueError("Report must be between 1 byte and 50 MiB")
        return self.enqueue_stream(name, io.BytesIO(content), max_bytes=MAX_UPLOAD)

    def enqueue_stream(self, name, stream, *, max_bytes=MAX_UPLOAD, acquisition=None):
        """Bounded original-file publication; downloaded is distinct from imported."""
        name = Path(name.replace("\\", "/")).name
        extension = ".csv.gz" if name.lower().endswith(".csv.gz") else Path(name).suffix.lower()
        if extension not in (".xlsx", ".xlsm", ".csv", ".csv.gz"):
            raise ValueError("Upload an .xlsx, .xlsm, .csv, or .csv.gz report")
        config = self.store.settings()
        from .intake_progress import catalog_readiness

        config["catalog_at_import"] = catalog_readiness(self.store.root)
        # Every import retains the exact scoring policy used on entry. Replays
        # under a changed policy produce a new import fingerprint.
        config["accretion_policy"] = normalize_policy(
            {
                **(config.get("accretion_policy") or {}),
                "priority_cities": config.get("accretion_priority_cities", []),
                "priority_products": config.get("accretion_priority_products", []),
            }
        )
        if acquisition is not None:
            from .api_import import receipt_acquisition, MAX_API_DOWNLOAD

            acquisition = receipt_acquisition(acquisition.get("receipt"))
            receipt = acquisition["receipt"]
            if name != receipt["original_filename"]:
                raise ValueError("Report filename does not match its API receipt")
            max_bytes = min(max_bytes, MAX_API_DOWNLOAD)
            config["report_type"] = receipt["report_type"]
        else:
            acquisition = {"kind": "manual_file"}
        acquisition["imported_at"] = now()
        config["acquisition"] = acquisition
        if acquisition.get("receipt"):
            config["acquisition_receipts"] = [acquisition]
        handle, temporary_name = tempfile.mkstemp(
            prefix=".intake-", dir=self.store.root / "originals"
        )
        temporary = Path(temporary_name)
        try:
            size, hasher = 0, hashlib.sha256()
            with os.fdopen(handle, "wb") as output:
                while chunk := stream.read(min(1024 * 1024, max_bytes - size + 1)):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError(
                            f"Report exceeds the {max_bytes // (1024 * 1024)} MiB download limit"
                        )
                    hasher.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if not size:
                raise ValueError("Report cannot be empty")
            digest = hasher.hexdigest()
            if acquisition.get("receipt") and (
                size != receipt["size_bytes"] or digest != receipt["sha256"]
            ):
                raise ValueError("Downloaded report bytes do not match the API receipt")
            return self._publish_original(name, temporary, extension, digest, config)
        finally:
            temporary.unlink(missing_ok=True)

    def _publish_original(self, name, temporary, extension, digest, config):
        acquisition = config["acquisition"]
        policy = dump(
            {
                "regions": sorted(config["regions"]),
                "sheet": config["sheet"],
                "version": POLICY_VERSION,
                "accretion_policy": config.get("accretion_policy"),
                "critical_only": config.get("critical_only", True),
                "outreach_mode": config.get("outreach_mode", "critical"),
                "targeted_reason": config.get("targeted_reason", ""),
                "report_type": config.get("report_type", "auto"),
                "profile_version": PROFILE_VERSION,
                "catalog_revision": {
                    key: config["catalog_at_import"].get(key)
                    for key in ("total", "bootstrap_complete", "last_success_at")
                },
                "filename_profile": resolve_profile({}, name, config.get("report_type", "auto"))[
                    "id"
                ],
                "acquisition_kind": acquisition["kind"],
            }
        )
        fingerprint = hashlib.sha256((digest + policy).encode()).hexdigest()
        with self.store.transaction() as db:
            if getattr(self.store, "maintenance", None) and self.store.maintenance.is_set():
                raise ValueError("Intake is paused while a data change is staged")
            existing = db.execute(
                "SELECT id,config,status FROM imports WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if existing:
                if acquisition.get("receipt"):
                    saved = json.loads(existing["config"])
                    receipts = saved.setdefault("acquisition_receipts", [])
                    if acquisition["receipt_sha256"] not in {
                        r.get("receipt_sha256") for r in receipts
                    }:
                        if len(receipts) >= 1000:
                            raise ValueError(
                                "This import already retains 1,000 distinct acquisition receipts"
                            )
                        receipts.append(acquisition)
                        db.execute(
                            "UPDATE imports SET config=? WHERE id=?", (dump(saved), existing["id"])
                        )
                return {
                    "id": existing["id"],
                    "duplicate": True,
                    "downloaded": bool(acquisition.get("receipt")),
                    "imported": existing["status"] == "done",
                }
            relative = f"originals/{digest}{extension}"
            path = self.store.path(relative)
            if path.exists():
                with path.open("rb") as original:
                    if hashlib.file_digest(original, "sha256").hexdigest() != digest:
                        raise ValueError(
                            "Previously retained original has changed; restore it before retrying"
                        )
            else:
                temporary.replace(path)
            import_id = uid()
            db.execute(
                "INSERT INTO imports(id,fingerprint,sha256,name,path,created_at,config) VALUES(?,?,?,?,?,?,?)",
                (import_id, fingerprint, digest, name, relative, now(), dump(config)),
            )
            self.store.log(db, "import", f"Added {name}")
        self.wake.set()
        return {
            "id": import_id,
            "duplicate": False,
            "downloaded": bool(acquisition.get("receipt")),
            "imported": False,
        }

    def scan_inbox(self):
        added = 0
        for path in sorted((self.store.root / "inbox").iterdir()):
            if (
                not path.is_file()
                or path.name.startswith("~$")
                or not path.name.lower().endswith((".xlsx", ".xlsm", ".csv", ".csv.gz"))
            ):
                continue
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            if self.inbox_seen.get(path.name) == signature or time.time() - stat.st_mtime < 2:
                continue
            try:
                if stat.st_size > MAX_UPLOAD:
                    raise ValueError("Inbox report exceeds the 50 MiB limit")
                content = path.read_bytes()
                if path.stat().st_mtime_ns != stat.st_mtime_ns:
                    continue
                added += not self.enqueue(path.name, content)["duplicate"]
                self.inbox_seen[path.name] = signature
            except (ValueError, OSError):
                LOG.exception("Could not import inbox file %s", path.name)
        return added

    def reevaluate(self, import_id):
        """Replay the retained original using current policy, without deleting history."""
        item = self.store.one("SELECT * FROM imports WHERE id=?", (import_id,))
        if not item:
            raise ValueError("Import not found")
        config = json.loads(item["config"])
        acquisition = config.get("acquisition", {})
        with self.store.path(item["path"]).open("rb") as original:
            if hashlib.file_digest(original, "sha256").hexdigest() != item["sha256"]:
                raise ValueError("Retained original has changed; restore it before re-evaluation")
            original.seek(0)
            if acquisition.get("kind") == "shadowserver_api_receipt":
                from .api_import import MAX_API_DOWNLOAD

                return self.enqueue_stream(
                    item["name"], original, max_bytes=MAX_API_DOWNLOAD, acquisition=acquisition
                )
            return self.enqueue_stream(item["name"], original)

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="intake-worker", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                if getattr(self.store, "maintenance", None) and self.store.maintenance.is_set():
                    self.wake.wait(timeout=2)
                    self.wake.clear()
                    continue
                if not self.review_backlog_checked:
                    from .qualification_reconciliation import (
                        reconcile_backlog,
                    )

                    reconcile_backlog(self)
                    self.export_pending()
                    self.review_backlog_checked = True
                if time.monotonic() - self.last_scan > 30:
                    if self.store.settings()["watch_inbox"]:
                        self.scan_inbox()
                    self.last_scan = time.monotonic()
                item = self.store.one(
                    "SELECT id FROM imports WHERE status='queued' ORDER BY created_at LIMIT 1"
                )
                if item:
                    self.process(item["id"])
                    continue
            except Exception:
                LOG.exception("Intake worker failed")
            self.wake.wait(timeout=2)
            self.wake.clear()

    def retry(self, import_id):
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
            if not row:
                raise ValueError("Import not found")
            if row["status"] in ("running", "queued"):
                return
            config = json.loads(row["config"])
            current = self.store.settings()
            config.update({key: current[key] for key in ("timeout", "retries", "interval")})
            db.execute(
                "UPDATE jobs SET status='pending',error='' WHERE import_id=? AND status='deferred'",
                (import_id,),
            )
            db.execute(
                "UPDATE imports SET status='queued',stage='Queued',error='',config=? WHERE id=?",
                (dump(config), import_id),
            )
        self.wake.set()

    def process(self, import_id):
        from .intake_progress import publish

        item = self.store.one("SELECT * FROM imports WHERE id=?", (import_id,))
        if not item:
            return
        config = json.loads(item["config"])
        report = Report.from_record(item)
        try:
            self._checkpoint(import_id)
            with self.store.transaction() as db:
                self._checkpoint(import_id, db)
                db.execute(
                    "UPDATE imports SET status='running',stage='Reading workbook',error='' WHERE id=?",
                    (import_id,),
                )
            self._checkpoint(import_id)
            if not config.get("intake_progress", {}).get("filter_complete"):
                result = filter_report(
                    self.store, report, config, lambda: self._checkpoint(import_id)
                )
                config.update(result.config_updates)
                archived = prepare_batch(
                    {**item, "config": config}, result.outcomes, stage="filter"
                )
                config.setdefault("intake_progress", {}).update(
                    phase="qualify",
                    detail="Checking attribution",
                    filter_complete=True,
                    admitted_rows=result.valid_rows,
                    groups_total=result.group_count,
                    updated_at=now(),
                )
                job_rows = [
                    (uid(), import_id, candidate.group.root_domain, dump(candidate.payload()))
                    for candidate in result.candidates
                ]
                self._checkpoint(import_id)
                with self.store.transaction() as db:
                    self._checkpoint(import_id, db)
                    db.execute("UPDATE imports SET config=? WHERE id=?", (dump(config), import_id))
                    enqueue_prepared(db, archived)
                    db.executemany(
                        "INSERT INTO jobs(id,import_id,domain,payload) VALUES(?,?,?,?)",
                        job_rows,
                    )
                    db.execute(
                        "UPDATE imports SET rows_read=?,valid_rows=?,rejected=?,groups_total=?,config=?,stage='Checking attribution' WHERE id=?",
                        (
                            result.rows_read,
                            result.valid_rows,
                            dump(result.rejected),
                            result.group_count,
                            dump(config),
                            import_id,
                        ),
                    )
                # Prepared Filter trees are no longer needed once publication
                # is durable; qualification loads only its saved job payloads.
                del result, archived, job_rows
            self._checkpoint(import_id)
            from .qualification import Qualifier
            from modules.entities.components.ownership import OwnershipChanged

            # Only IDs are queued in memory; each payload is read when its group
            # starts. The provider is opened lazily after the local/site gates.
            with self.store.transaction() as db:
                counts = db.execute(
                    "SELECT COALESCE(sum(status!='pending'),0) done,COALESCE(sum(status='qualified'),0) qualified FROM jobs WHERE import_id=?",
                    (import_id,),
                ).fetchone()
                db.execute(
                    "UPDATE imports SET groups_done=?,qualified=? WHERE id=?",
                    (counts["done"], counts["qualified"], import_id),
                )
                config.setdefault("intake_progress", {})["associated_groups"] = counts["qualified"]
            pending_ids = self.store.all(
                "SELECT id FROM jobs WHERE import_id=? AND status='pending' ORDER BY rowid",
                (import_id,),
            )
            cve_records = {}
            export_pending = bool(config.get("intake_progress", {}).get("exports_pending"))
            with closing(
                Qualifier(
                    self.store,
                    config,
                    self.stop_event,
                    attribution_factory=self.attribution_factory,
                    capture=self.capture,
                )
            ) as qualifier:
                for pending in pending_ids:
                    self._checkpoint(import_id)
                    job = self.store.one("SELECT * FROM jobs WHERE id=?", (pending["id"],))
                    if job is None or job["status"] != "pending":
                        continue
                    publish(self.store, import_id, config, "qualify", "Qualifying " + job["domain"])
                    candidate = ReportCandidate.restore(
                        report, job["domain"], json.loads(job["payload"])
                    )
                    group = candidate.group
                    decision = qualifier.qualify(candidate, refresh=bool(job["refresh_requested"]))
                    evaluated = None
                    if decision.lead is not None:
                        try:
                            evaluated = self.evaluate_lead(
                                decision.lead, config=config, cve_cache=cve_records
                            )
                        except OwnershipChanged as error:
                            decision = decision.defer("ownership_changed", str(error))
                    # Pause intentionally finishes the current group. Shutdown
                    # cancels it, including a provider that returned after stop.
                    self._shutdown_checkpoint()
                    with self.store.transaction() as db:
                        current = db.execute(
                            "SELECT * FROM jobs WHERE id=?", (job["id"],)
                        ).fetchone()
                        if (
                            not current
                            or current["status"] != "pending"
                            or current["payload"] != job["payload"]
                        ):
                            continue
                        self._shutdown_checkpoint()
                        if decision.lead is not None:
                            try:
                                self.associate_lead(evaluated, db=db)
                            except OwnershipChanged as error:
                                decision = decision.defer("ownership_changed", str(error))
                        if decision.lead is None:
                            enqueue_outcome(
                                db,
                                import_id,
                                group.observations,
                                stage="qualify",
                                outcome=decision.status,
                                reason=decision.reason,
                            )
                        db.execute(
                            "UPDATE jobs SET status=?,attempts=?,attribution_result_id=?,qualification=?,refresh_requested=0,error=? WHERE id=?",
                            (
                                decision.status,
                                dump(decision.attempts),
                                decision.result_id,
                                dump(decision.evidence),
                                "" if decision.lead else decision.reason,
                                job["id"],
                            ),
                        )
                        export_pending = export_pending or decision.lead is not None
                        reused = decision.lead is not None and any(
                            a.get("method") == "history" and a.get("status") == "matched"
                            for a in decision.attempts
                        )
                        progress = config.setdefault("intake_progress", {})
                        progress.update(
                            exports_pending=export_pending,
                            associated_groups=progress.get("associated_groups", 0)
                            + int(decision.lead is not None),
                            reused_groups=progress.get("reused_groups", 0) + int(reused),
                        )
                        # Increment once with the guarded transition; no repeated
                        # full job/JSON scans as the import grows.
                        from .intake_progress import preserve_export_obligation

                        preserve_export_obligation(db, import_id, config)
                        db.execute(
                            "UPDATE imports SET groups_done=groups_done+1,qualified=qualified+?,config=? WHERE id=?",
                            (int(decision.lead is not None), dump(config), import_id),
                        )
            deferred = self.store.one(
                "SELECT count(*) n FROM jobs WHERE import_id=? AND status='deferred'", (import_id,)
            )["n"]
            self._checkpoint(import_id)
            with self.store.transaction() as db:
                self._checkpoint(import_id, db)
                pending = db.execute(
                    "SELECT count(*) FROM jobs WHERE import_id=? AND status='pending'", (import_id,)
                ).fetchone()[0]
                review = db.execute(
                    "SELECT count(*) FROM jobs WHERE import_id=? AND status='review'", (import_id,)
                ).fetchone()[0]
                db.execute(
                    "UPDATE imports SET status=?,stage='Finished',message=? WHERE id=?",
                    (
                        "queued" if pending else "needs_retry" if deferred else "done",
                        f"{pending} groups queued; {review} awaiting review; {deferred} need a retry"
                        if pending or review or deferred
                        else "All groups processed",
                        import_id,
                    ),
                )
                self.store.log(db, "import_complete", f"Processed {item['name']}")
            if export_pending:
                self.export_pending()
            config.setdefault("intake_progress", {})["exports_pending"] = False
            publish(self.store, import_id, config, "complete", "Intake complete")
        except IntakeInterrupted:
            return
        except Exception as error:
            LOG.exception("Import failed")
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE imports SET status='error',stage='Import failed',error=? WHERE id=?",
                    (str(error), import_id),
                )
                if not config.get("intake_progress", {}).get("filter_complete") and isinstance(
                    error, SourceFormatError
                ):
                    # A malformed container has no trustworthy row map. Archive
                    # its source-level failure and preserve the original bytes.
                    enqueue_batch(
                        db,
                        import_id,
                        [
                            SourceObservation(
                                item["name"],
                                config.get("sheet", ""),
                                0,
                                {"source_error": str(error)},
                            )
                        ],
                        stage="filter",
                        outcome="rejected",
                        reason="invalid_report_format",
                    )

    def _checkpoint(self, import_id, db=None):
        if self.stop_event.is_set():
            raise IntakeInterrupted()
        state = (
            db.execute("SELECT status FROM imports WHERE id=?", (import_id,)).fetchone()
            if db is not None
            else self.store.one("SELECT status FROM imports WHERE id=?", (import_id,))
        )
        if state is None or state["status"] == "paused":
            raise IntakeInterrupted()

    def _shutdown_checkpoint(self):
        if self.stop_event.is_set():
            raise IntakeInterrupted()

    def evaluate_lead(self, lead: QualifiedLead, *, config=None, cve_cache=None) -> EvaluatedLead:
        """Evaluate's typed product is the sole input to Associate."""
        from .evaluation import evaluate_lead

        return evaluate_lead(
            self.store,
            lead,
            checkpoint=self._shutdown_checkpoint,
            config=config,
            cve_cache=cve_cache,
        )

    def review_group(self, job_id, result_id, evidence_index, decision, note=""):
        """Apply an explicit decision to the current saved result; no new lookup."""
        job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise ValueError("Hostname group not found")
        if job["status"] != "review" or not result_id or result_id != job["attribution_result_id"]:
            raise ValueError("This group changed. Reload its attribution before reviewing it.")
        if decision not in ("accept", "dismiss"):
            raise ValueError("Choose accept or dismiss")
        with EvidenceStore(self.store.root / "attribution.sqlite3") as evidence_store:
            result = checked_result(evidence_store, result_id, job["domain"])
            if result["status"] != "review":
                raise ValueError("The saved result is not a review candidate for this group")
            review = {
                "id": uid(),
                "result_id": result_id,
                "evidence_index": evidence_index,
                "decision": decision,
                "reviewer": self.store.settings()["analyst_name"] or "Local analyst",
                "note": note,
                "reviewed_at": now(),
            }
            lead = None
            if decision == "accept":
                partials = result.get("partial_evidence", [])
                if type(evidence_index) is not int or not 0 <= evidence_index < len(partials):
                    raise ValueError("Select one saved partial match")
                evidence = partials[evidence_index]
                entries = [restore_observation(e) for e in json.loads(job["payload"])]
                index = int(evidence["details"]["entry_id"])
                if not 0 <= index < len(entries) or entries[index].ip != evidence["ip"]:
                    raise ValueError("Partial match does not identify an original observation")
                group = CandidateGroup(job["domain"], entries)
                attribution = attribution_record(
                    evidence_store,
                    result_id,
                    job["domain"],
                    result["policy"],
                    evidence,
                    review=review,
                )
                from .qualification import complete_lead, local_scope
                from modules.attribution.components.attribution_bridge import group_coverage

                recognition, findings, reason = local_scope(self.store, group)
                if reason:
                    raise ValueError("Qualification cannot complete: " + reason)
                saved = json.loads(job["qualification"])
                saved["findings"] = list(findings)
                saved["ownership_token"] = recognition["ownership_token"]
                report = Report.from_record(
                    self.store.one("SELECT * FROM imports WHERE id=?", (job["import_id"],))
                )
                candidate = ReportCandidate(report, group)
                lead = complete_lead(
                    self.store, candidate, attribution, group_coverage(group, attribution), saved
                )
        evaluated = self.evaluate_lead(lead) if lead else None
        with self.store.transaction() as db:
            current = db.execute(
                "SELECT status,attribution_result_id FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if current["status"] != "review" or current["attribution_result_id"] != result_id:
                raise ValueError("This group changed. Reload before saving your decision.")
            lead_id = self.associate_lead(evaluated, db=db).entity_id if evaluated else None
            db.execute(
                "INSERT INTO attribution_reviews VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    review["id"],
                    job_id,
                    result_id,
                    evidence_index,
                    decision,
                    review["reviewer"],
                    note,
                    review["reviewed_at"],
                    lead_id,
                ),
            )
            db.execute(
                "UPDATE jobs SET status=?,qualification=? WHERE id=?",
                (
                    "qualified" if lead_id else "dismissed",
                    dump(lead.evidence()) if lead else job["qualification"],
                    job_id,
                ),
            )
            if not lead_id:
                enqueue_outcome(
                    db,
                    job["import_id"],
                    json.loads(job["payload"]),
                    stage="qualify",
                    outcome="dismissed",
                    reason="attribution_dismissed",
                )
            from .qualification_reconciliation import (
                refresh_import_summary,
            )

            refresh_import_summary(db, job["import_id"], exports_pending=bool(lead_id))
            self.store.log(
                db,
                "attribution_review",
                f"{'Accepted' if decision == 'accept' else 'Dismissed'} name-match attribution for {job['domain']}; evidence result {result_id}",
                lead_id,
            )
        reconciled = []
        if lead_id:
            from .qualification_reconciliation import reconcile_reviews

            try:
                reconciled = reconcile_reviews(self, job["domain"])
            except Exception:
                # The explicit decision is already committed. An unrelated
                # damaged sibling must not turn that success into a failed save.
                LOG.exception("Could not reconcile duplicate attribution reviews")
        export_error = None
        if lead_id:
            try:
                self.export_pending()
            except (OSError, ValueError) as error:
                LOG.exception("Accepted review awaits export repair")
                export_error = str(error)
        return {
            "lead_id": lead_id,
            "review": review,
            "reconciled_jobs": reconciled,
            "export_error": export_error,
        }

    def export_pending(self):
        """Publish and acknowledge obligations under the established writer lock."""
        with self.store.lock:
            if not self.store.one(
                "SELECT 1 FROM imports WHERE json_extract(config,'$.intake_progress.exports_pending')=1 LIMIT 1"
            ):
                return
            self.store.export_all()
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE imports SET config=json_set(config,'$.intake_progress.exports_pending',json('false')) WHERE json_extract(config,'$.intake_progress.exports_pending')=1"
                )

    def retry_group(self, job_id, result_id):
        """Retry a review/no-match group explicitly, with its old result retained."""
        with self.store.transaction() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job["status"] not in (
                "review",
                "no_match",
                "deferred",
                "no_public_ip",
                "dismissed",
            ):
                raise ValueError("This group cannot be retried in its current state")
            latest = job["attribution_result_id"]
            if latest != result_id:
                raise ValueError("This group changed. Reload before retrying.")
            db.execute(
                "UPDATE jobs SET status='pending',error='',refresh_requested=1 WHERE id=?",
                (job_id,),
            )
            db.execute(
                "UPDATE imports SET status='queued',stage='Queued',error='' WHERE id=?",
                (job["import_id"],),
            )
        self.wake.set()

    def associate_lead(self, evaluated: EvaluatedLead, *, db=None) -> AssociationResult:
        """Publish Evaluate's product through the Associate component."""
        from .association import associate_lead

        self._shutdown_checkpoint()
        return associate_lead(self.store, evaluated, db=db)
