"""Accretion: filter source rows, qualify their evidence, and rank outreach leads."""

from __future__ import annotations

from .intake.versions import entry_fields

import hashlib
import io
import json
import logging
import os
import tempfile
import threading
import time
from collections import Counter
from contextlib import closing, nullcontext
from dataclasses import asdict
from pathlib import Path

from workbench.intake import (
    read_entries as read_entries,
    restore_entry as restore_entry,
    EntryValidator,
    UnvalidatedEntry,
    ValidatedEntry,
    ValidatedLeads,
    WhoisRecord as WhoisRecord,
    WhoisLookupError as WhoisLookupError,
    is_empty_entry,
)
from .accretion import normalize_policy, vet_cves
from .store import Store
from .primitives import dump, now, uid
from .attribution_bridge import RegistrationAttribution, attribution_record, checked_result
from attribution import EvidenceStore
from .cve_sources import verify
from .intelligence.identifiers import identifiers
from .report_profiles import (
    resolve_profile,
    notification_eligibility,
    observation_envelope,
    inventory_metadata,
    PROFILE_VERSION,
)

LOG = logging.getLogger(__name__)
MAX_UPLOAD = 50 * 1024 * 1024
POLICY_VERSION = 12


class IntakeService:
    def __init__(self, store: Store, lookup_factory=None):
        self.store = store
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.lookup_factory = lookup_factory
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
            except ValueError, OSError:
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
                    from .attribution_reconciliation import reconcile_backlog

                    reconcile_backlog(self)
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
        from .intake_progress import accepted_patterns, catalog_readiness, publish

        item = self.store.one("SELECT * FROM imports WHERE id=?", (import_id,))
        if not item:
            return
        config = json.loads(item["config"])
        try:
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE imports SET status='running',stage='Reading workbook',error='' WHERE id=?",
                    (import_id,),
                )
            if not self.store.one("SELECT id FROM jobs WHERE import_id=? LIMIT 1", (import_id,)):
                config["catalog_at_scoring"] = catalog_readiness(self.store.root)
                publish(
                    self.store,
                    import_id,
                    config,
                    "filter",
                    "Reading source rows",
                    read_rows=0,
                    total_rows=None,
                )
                last_progress = time.monotonic()
                validator = EntryValidator(set(config["regions"]))
                structural, validated, rejected, count = [], [], Counter(), 0
                ignored_empty_rows = 0
                observation_outcomes = []
                profiles, eligibility_counts = {}, Counter()
                rejection_examples = {}
                with closing(
                    read_entries(self.store.path(item["path"]), config["sheet"])
                ) as reader:
                    for rows_seen, source in enumerate(reader, 1):
                        if rows_seen > 250000:
                            raise ValueError("Workbook exceeds the 250,000 row limit")
                        if is_empty_entry(source):
                            ignored_empty_rows += 1
                            continue
                        count += 1
                        source = UnvalidatedEntry(
                            item["name"], source.sheet, source.row, source.fields
                        )
                        profile = resolve_profile(
                            source.fields, item["name"], config.get("report_type", "auto")
                        )
                        profiles[profile["id"]] = profile
                        result = (
                            validator.validate_entry(source, profile=profile)
                            if profile["capability"] == "eligible"
                            else None
                        )
                        if result:
                            structural.append((result, profile))
                        else:
                            reason = (
                                "unsupported_report_profile"
                                if profile["capability"] != "eligible"
                                else validator.rejection_reason(source, profile=profile)
                            )
                            rejected[reason] += 1
                            observation_outcomes.append(
                                {
                                    "source": source,
                                    "disposition": "dark_matter",
                                    "reason": reason,
                                }
                            )
                            examples = rejection_examples.setdefault(reason, [])
                            if len(examples) < 5:
                                examples.append(
                                    {
                                        "sheet": source.sheet,
                                        "row": source.row,
                                        "hostname": str(source.fields.get("hostname") or "")[:253],
                                    }
                                )
                        if rows_seen % 256 == 0 and time.monotonic() - last_progress >= 0.5:
                            publish(
                                self.store,
                                import_id,
                                config,
                                "filter",
                                "Checking required fields and jurisdiction",
                                read_rows=count,
                                structural_passed=len(structural),
                                filtered_rows=sum(rejected.values()),
                            )
                            last_progress = time.monotonic()
                publish(
                    self.store,
                    import_id,
                    config,
                    "filter",
                    "Checking local CVE catalog",
                    read_rows=count,
                    total_rows=count,
                    structural_passed=len(structural),
                    filtered_rows=sum(rejected.values()),
                )
                # Filter first. One local lookup per distinct CVE across the
                # remaining rows avoids network calls and row-by-row catalog I/O.
                # No invalid or out-of-jurisdiction row reaches this stage.
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE imports SET stage='Accretion: vetting local CVEs' WHERE id=?",
                        (import_id,),
                    )
                if config.get("accretion_policy"):
                    config["accretion_scored_at"] = now()
                vetted = (
                    vet_cves(
                        self.store.root,
                        identifiers(e.source.fields.get("tag", "") for e, _ in structural),
                        as_of=config["accretion_scored_at"],
                    )
                    if structural and config.get("accretion_policy")
                    else {}
                )
                for result, profile in structural:
                    source = result.source
                    cve_ids = identifiers([source.fields.get("tag", "")])
                    row_catalog = {cve_id: vetted[cve_id] for cve_id in cve_ids if cve_id in vetted}
                    eligibility = notification_eligibility(
                        source.fields, profile, config, catalog_records=row_catalog
                    )
                    eligibility_counts[eligibility["reason"] or "eligible"] += 1
                    normalized = observation_envelope(
                        source,
                        profile,
                        eligibility,
                        source_sha256=item["sha256"],
                        acquisition={
                            key: value
                            for key, value in config.get("acquisition", {}).items()
                            if key not in {"receipt", "live_api_acceptance"}
                        },
                    )
                    normalized["accretion_cves"] = row_catalog
                    validated.append(
                        ValidatedEntry(result.source, result.ip, result.private_ip, normalized)
                    )
                groups = []
                all_groups = ValidatedLeads.group(validated)
                for group in all_groups:
                    # A critical observation opens a group. Other structurally valid
                    # observations in that group remain accurately labeled context.
                    if any(e.normalized["eligibility"]["eligible"] for e in group.entries):
                        groups.append(group)
                        for e in group.entries:
                            e.normalized["eligibility"]["included_as_context"] = not e.normalized[
                                "eligibility"
                            ]["eligible"]
                    else:
                        for e in group.entries:
                            reason = e.normalized["eligibility"]["reason"]
                            rejected[reason] += 1
                            examples = rejection_examples.setdefault(reason, [])
                            if len(examples) < 5:
                                examples.append(
                                    {
                                        "sheet": e.source.sheet,
                                        "row": e.source.row,
                                        "hostname": str(e.source.fields.get("hostname") or "")[
                                            :253
                                        ],
                                    }
                                )
                admitted_roots = {g.hostname for g in groups}
                for group in all_groups:
                    admitted = group.hostname in admitted_roots
                    for entry in group.entries:
                        observation_outcomes.append(
                            {
                                "source": entry.source,
                                "disposition": "lead" if admitted else "dark_matter",
                                "reason": "admitted"
                                if admitted
                                else entry.normalized["eligibility"]["reason"],
                                "normalized": entry.normalized,
                            }
                        )
                valid_count = sum(len(g.entries) for g in groups)
                config["report_profiles"] = list(profiles.values())
                config["profile_inventory"] = inventory_metadata()
                config["intake_stats"] = {
                    "accepted_patterns": accepted_patterns(groups),
                    "ignored_empty_rows": ignored_empty_rows,
                    "eligibility": dict(eligibility_counts),
                    "rejection_examples": rejection_examples,
                    "accretion": {
                        "name": "Accretion",
                        "phase_version": 2,
                        "structural_passed": len(structural),
                        "filtered_rows": count - valid_count,
                        "admitted_rows": valid_count,
                        "context_rows": sum(
                            not e.normalized["eligibility"]["eligible"]
                            for g in groups
                            for e in g.entries
                        ),
                        "leads": len(groups),
                        "cves_checked": len(vetted),
                        "cves_available": sum(r["status"] == "available" for r in vetted.values()),
                        "cves_missing": sum(r["status"] == "missing" for r in vetted.values()),
                        "cves_unavailable": sum(
                            r["status"] in {"invalid", "unavailable"} for r in vetted.values()
                        ),
                        "cves_rejected": sum(r["status"] == "rejected" for r in vetted.values()),
                        "kev_admitted_rows": sum(
                            e.normalized["eligibility"].get("admission_signal")
                            == "known_exploitation"
                            and e.normalized["eligibility"]["eligible"]
                            for e in validated
                        ),
                        "catalog_critical_rows": sum(
                            e.normalized["eligibility"]["admission_basis"] == "local_catalog_cvss"
                            and e.normalized["eligibility"]["admission_severity"] == "critical"
                            and e.normalized["eligibility"]["eligible"]
                            for e in validated
                        ),
                    },
                }
                config["intake_progress"].update(
                    phase="qualify",
                    detail="Checking attribution",
                    filter_complete=True,
                    admitted_rows=valid_count,
                    groups_total=len(groups),
                    updated_at=now(),
                )
                with self.store.transaction() as db:
                    from .dark_matter import record_observations

                    # Queue snapshots read their immutable policy/time from this
                    # import inside the same transaction that publishes its jobs.
                    db.execute("UPDATE imports SET config=? WHERE id=?", (dump(config), import_id))
                    retained_observations = record_observations(
                        db,
                        import_id,
                        item["sha256"],
                        observation_outcomes,
                        regions=config["regions"],
                    )
                    config["intake_stats"]["accretion"].update(
                        dark_matter_rows=retained_observations["dark_matter"],
                        discarded_rows=retained_observations["discarded"],
                    )
                    for group in groups:
                        from .lead_queue import register_group

                        register_group(
                            db, import_id, group.hostname, group.entries, intake_score={}
                        )
                        db.execute(
                            "INSERT INTO jobs(id,import_id,domain,payload) VALUES(?,?,?,?)",
                            (
                                uid(),
                                import_id,
                                group.hostname,
                                dump([asdict(e) for e in group.entries]),
                            ),
                        )
                    db.execute(
                        "UPDATE imports SET rows_read=?,valid_rows=?,rejected=?,groups_total=?,config=?,stage='Checking attribution' WHERE id=?",
                        (
                            count,
                            valid_count,
                            dump(dict(rejected)),
                            len(groups),
                            dump(config),
                            import_id,
                        ),
                    )
            publish(self.store, import_id, config, "qualify", "Checking attribution")
            client = (
                self.lookup_factory()
                if self.lookup_factory
                else RegistrationAttribution(self.store, config)
            )
            cve_records = {}
            with closing(client):
                for job in self.store.all(
                    "SELECT * FROM jobs WHERE import_id=? AND status='pending' ORDER BY rowid",
                    (import_id,),
                ):
                    status = self.store.one("SELECT status FROM imports WHERE id=?", (import_id,))[
                        "status"
                    ]
                    if status == "paused" or self.stop_event.is_set():
                        return
                    with self.store.transaction() as db:
                        db.execute(
                            "UPDATE imports SET message=? WHERE id=?", (job["domain"], import_id)
                        )
                    group = ValidatedLeads(
                        job["domain"], [restore_entry(e) for e in json.loads(job["payload"])]
                    )
                    from .intake_reuse import recognize_group

                    recognition = recognize_group(
                        self.store,
                        group,
                        evidence_store=getattr(getattr(client, "module", None), "store", None),
                        refresh=bool(job["refresh_requested"]),
                    )
                    result_id = None
                    if recognition["state"] == "review":
                        result, attribution = "deferred", None
                        group.attempts = [
                            {
                                "status": "association_conflict",
                                "message": recognition["basis"]
                                + "; review the business association and source observation dates before retrying.",
                            }
                        ]
                    elif recognition["attribution"]:
                        result, attribution = "qualified", recognition["attribution"]
                        group.entries.insert(0, group.entries.pop(recognition["anchor_index"]))
                        result_id = attribution.get("result_id")
                        group.attempts = [
                            {
                                "ip": attribution["ip"],
                                "method": "history",
                                "status": "matched",
                                "reason": "established_endpoint_reused",
                                "message": "Reused historical attribution for an unchanged endpoint; no fresh lookup claimed.",
                                **({"result_id": result_id} if result_id else {}),
                            }
                        ]
                    elif (
                        self.lookup_factory
                    ):  # Test/legacy adapter; production always uses the module.
                        selected = recognition["candidate_indices"]
                        candidate_group = (
                            ValidatedLeads(group.hostname, [group.entries[i] for i in selected])
                            if selected is not None
                            else group
                        )
                        qualified = candidate_group.qualify(client.lookup)
                        if candidate_group is not group:
                            group.attempts = candidate_group.attempts
                            if qualified:
                                anchor = candidate_group.entries[0]
                                group.entries.insert(
                                    0, group.entries.pop(group.entries.index(anchor))
                                )
                        attribution = asdict(qualified.whois[0]) if qualified else None
                        result = (
                            "qualified"
                            if qualified
                            else "deferred"
                            if any(a["status"] == "lookup_error" for a in group.attempts)
                            else "no_public_ip"
                            if all(a["status"] == "skipped_nonpublic" for a in group.attempts)
                            else "no_match"
                        )
                    else:
                        result, attribution = client.qualify(
                            group,
                            refresh=bool(job["refresh_requested"]),
                            candidate_indices=recognition["candidate_indices"],
                        )
                        result_id = client.result_id
                        if result == "review" and not job["refresh_requested"]:
                            from .attribution_approval import reusable_review

                            reused = reusable_review(
                                self.store, group, client.module.store, result_id
                            )
                            if reused:
                                attribution, anchor = reused
                                group.entries.insert(0, group.entries.pop(anchor))
                                result = "qualified"
                                group.attempts.append(
                                    {
                                        "ip": attribution["ip"],
                                        "method": "history",
                                        "status": "matched",
                                        "reason": "approved_registrant_reused",
                                        "message": "Reused the prior domain/registrant approval with this endpoint's own saved evidence.",
                                        "result_id": result_id,
                                        "source_result_id": attribution["review"]["result_id"],
                                    }
                                )
                    if job["refresh_requested"]:
                        group.attempts.append(
                            {
                                "method": "history",
                                "status": "refreshed",
                                "reason": "explicit_attribution_refresh",
                                "result_id": result_id,
                            }
                        )
                    publish(self.store, import_id, config, "urgency", "Ranking qualified evidence")
                    from .accretion import score_lead
                    from .lead_queue import association, register_group

                    with self.store.read_snapshot() as db:
                        score = score_lead(
                            [asdict(entry) for entry in group.entries],
                            root_domain=group.hostname,
                            association=association(
                                db, group.hostname, [asdict(entry) for entry in group.entries]
                            ),
                            policy=config.get("accretion_policy"),
                            as_of=config.get("accretion_scored_at") or item["created_at"],
                        )
                    records = []
                    if result == "qualified":
                        for cve_id in identifiers(
                            e.source.fields.get("tag", "") for e in group.entries
                        ):
                            if cve_id not in cve_records:
                                cve_records[cve_id] = verify(self.store, cve_id, local_only=True)
                        records = [
                            cve_records[c]
                            for c in identifiers(
                                e.source.fields.get("tag", "") for e in group.entries
                            )
                        ]
                    publish(
                        self.store,
                        import_id,
                        config,
                        "associate",
                        "Associating observations and findings",
                    )
                    # A crash must never publish an entity/finding while leaving
                    # its qualification job pending. Commit the interpretation,
                    # current work scope and job completion together.
                    with self.store.transaction() as db:
                        register_group(
                            db, import_id, group.hostname, group.entries, intake_score=score
                        )
                        if result == "qualified":
                            self.accept_group(
                                import_id, group, attribution, cve_records=records, db=db
                            )
                        else:
                            from .awareness import associate

                            for entry in group.entries:
                                associate(
                                    db,
                                    asdict(entry),
                                    import_id=import_id,
                                    source_sha256=item["sha256"],
                                    entity_id=recognition["entity_id"],
                                    admitted=False,
                                    reason="attribution_" + result,
                                    fallback=item["created_at"],
                                )
                        db.execute(
                            "UPDATE jobs SET status=?,attempts=?,attribution_result_id=?,refresh_requested=0,error=? WHERE id=?",
                            (
                                result,
                                dump(group.attempts),
                                result_id,
                                recognition["basis"]
                                + "; review the business association and source observation dates before retrying."
                                if recognition["state"] == "review"
                                else "",
                                job["id"],
                            ),
                        )
                        counts = db.execute(
                            "SELECT count(*) total, sum(status!='pending') done, sum(status='qualified') qualified FROM jobs WHERE import_id=?",
                            (import_id,),
                        ).fetchone()
                        db.execute(
                            "UPDATE imports SET groups_done=?,qualified=? WHERE id=?",
                            (counts["done"], counts["qualified"], import_id),
                        )
                        config.setdefault("intake_progress", {}).update(
                            associated_groups=counts["done"],
                            reused_groups=db.execute(
                                "SELECT count(*) FROM jobs WHERE import_id=? AND EXISTS "
                                "(SELECT 1 FROM json_each(jobs.attempts) WHERE "
                                "json_extract(value,'$.reason') IN ('established_endpoint_reused','approved_registrant_reused'))",
                                (import_id,),
                            ).fetchone()[0],
                        )
                    publish(
                        self.store, import_id, config, "qualify", "Checking remaining attribution"
                    )
            deferred = self.store.one(
                "SELECT count(*) n FROM jobs WHERE import_id=? AND status='deferred'", (import_id,)
            )["n"]
            with self.store.transaction() as db:
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
            publish(self.store, import_id, config, "associate", "Finalizing entity awareness")
            self.store.export_all()
            publish(self.store, import_id, config, "complete", "Intake complete")
        except Exception as error:
            LOG.exception("Import failed")
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE imports SET status='error',stage='Import failed',error=? WHERE id=?",
                    (str(error), import_id),
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
            records, group, attribution = [], None, None
            if decision == "accept":
                partials = result.get("partial_evidence", [])
                if type(evidence_index) is not int or not 0 <= evidence_index < len(partials):
                    raise ValueError("Select one saved partial match")
                evidence = partials[evidence_index]
                entries = [restore_entry(e) for e in json.loads(job["payload"])]
                index = int(evidence["details"]["entry_id"])
                if not 0 <= index < len(entries) or entries[index].ip != evidence["ip"]:
                    raise ValueError("Partial match does not identify an original observation")
                group = ValidatedLeads(job["domain"], entries)
                group.entries.insert(0, group.entries.pop(index))
                attribution = attribution_record(
                    evidence_store,
                    result_id,
                    job["domain"],
                    result["policy"],
                    evidence,
                    review=review,
                )
                records = [
                    verify(self.store, c, local_only=True)
                    for c in identifiers(e.source.fields.get("tag", "") for e in entries)
                ]
        with self.store.transaction() as db:
            current = db.execute(
                "SELECT status,attribution_result_id FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if current["status"] != "review" or current["attribution_result_id"] != result_id:
                raise ValueError("This group changed. Reload before saving your decision.")
            lead_id = (
                self.accept_group(job["import_id"], group, attribution, cve_records=records, db=db)
                if group
                else None
            )
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
                "UPDATE jobs SET status=? WHERE id=?",
                ("qualified" if lead_id else "dismissed", job_id),
            )
            from .attribution_reconciliation import refresh_import_summary

            refresh_import_summary(db, job["import_id"])
            self.store.log(
                db,
                "attribution_review",
                f"{'Accepted' if decision == 'accept' else 'Dismissed'} name-match attribution for {job['domain']}; evidence result {result_id}",
                lead_id,
            )
        reconciled = []
        if lead_id:
            from .attribution_reconciliation import reconcile_reviews

            try:
                reconciled = reconcile_reviews(self, job["domain"])
            except Exception:
                # The explicit decision is already committed. An unrelated
                # damaged sibling must not turn that success into a failed save.
                LOG.exception("Could not reconcile duplicate attribution reviews")
        self.store.export_all()
        return {"lead_id": lead_id, "review": review, "reconciled_jobs": reconciled}

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

    def accept_group(self, import_id, group, attribution, demo=False, cve_records=None, db=None):
        from workbench.intake import root_domain

        def belongs(entry):
            hostname = entry.source.fields["hostname"]
            # Reserved .example names in the isolated demonstration workspace
            # deliberately have no registrable public suffix.
            return root_domain(hostname) == group.hostname or (
                demo and (hostname == group.hostname or hostname.endswith("." + group.hostname))
            )

        if not group.entries or not all(belongs(e) for e in group.entries):
            raise ValueError("Every observation must belong to its domain group")
        if attribution["ip"] != group.entries[0].ip:
            raise ValueError("Attribution must identify the selected observation")
        stamp = now()
        with self.store.transaction() if db is None else nullcontext(db) as db:
            from .lead_queue import register_group

            pending_id = register_group(db, import_id, group.hostname, group.entries)
            pending = db.execute("SELECT * FROM lead_queue WHERE id=?", (pending_id,)).fetchone()
            if pending["association_state"] == "review":
                raise ValueError(
                    "Review the ownership association and observation dates before qualifying this group"
                )
            existing = (
                db.execute(
                    "SELECT * FROM leads WHERE id=? AND merged_into IS NULL",
                    (pending["entity_id"],),
                ).fetchone()
                if pending["entity_id"] and pending["association_state"] == "known"
                else None
            )
            if not existing:
                existing = db.execute(
                    "SELECT l.* FROM leads l JOIN domain_groups g ON g.entity_id=l.id WHERE lower(g.root_domain)=?",
                    (group.hostname.casefold(),),
                ).fetchone()
            lead_id = existing["id"] if existing else uid()
            source_hash = db.execute(
                "SELECT sha256 FROM imports WHERE id=?", (import_id,)
            ).fetchone()["sha256"]
            ids = [
                hashlib.sha256(
                    f"{source_hash}:{e.source.sheet}:{e.source.row}".encode()
                ).hexdigest()
                for e in group.entries
            ]
            if not existing:
                db.execute(
                    "INSERT INTO leads(id,domain,created_at,updated_at,attribution,attribution_entry_id,demo,company) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        lead_id,
                        group.hostname,
                        stamp,
                        stamp,
                        dump(attribution),
                        ids[0],
                        int(demo),
                        str(group.entries[0].source.fields["hostname"]),
                    ),
                )
            from .intake.identity import observed, signature

            prior_group = db.execute(
                "SELECT e.id,e.payload,g.root_domain FROM domain_groups g JOIN entries e ON e.id=g.attribution_entry_id WHERE lower(g.root_domain)=?",
                (group.hostname.casefold(),),
            ).fetchone()
            group_key = prior_group["root_domain"] if prior_group else group.hostname
            fresh_group = not prior_group or observed(asdict(group.entries[0]), stamp) >= observed(
                json.loads(prior_group["payload"]), ""
            )
            if (
                prior_group
                and db.execute(
                    "SELECT 1 FROM case_entries WHERE entry_id=? LIMIT 1", (prior_group["id"],)
                ).fetchone()
                and signature(json.loads(prior_group["payload"]))
                == signature(asdict(group.entries[0]))
            ):
                fresh_group = False
            from .ownership import available as ownership_available

            if ownership_available(db) and (
                fresh_group
                or not db.execute(
                    "SELECT 1 FROM entity_domain_associations WHERE root_domain=? AND entity_id=? AND attribution_entry_id IS NOT NULL",
                    (group_key, lead_id),
                ).fetchone()
            ):
                db.execute(
                    "INSERT INTO entity_domain_associations(root_domain,entity_id,attribution_entry_id,attribution) VALUES(?,?,?,?) ON CONFLICT(root_domain,entity_id) DO UPDATE SET attribution_entry_id=excluded.attribution_entry_id,attribution=excluded.attribution",
                    (group_key, lead_id, ids[0], dump(attribution)),
                )
            if fresh_group:
                db.execute(
                    "INSERT INTO domain_groups VALUES(?,?,?,?) ON CONFLICT(root_domain) DO UPDATE SET attribution_entry_id=excluded.attribution_entry_id,attribution=excluded.attribution WHERE domain_groups.entity_id=excluded.entity_id",
                    (group_key, lead_id, ids[0], dump(attribution)),
                )
            inserted = 0
            for entry_id, entry in zip(ids, group.entries):
                f = entry_fields(asdict(entry))
                cursor = db.execute(
                    "INSERT INTO entries(id,lead_id,import_id,payload,ip,hostname,tag,version,observed_at,root_domain) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                    (
                        entry_id,
                        lead_id,
                        import_id,
                        dump(asdict(entry)),
                        entry.ip,
                        str(f["hostname"]),
                        str(f["tag"]),
                        str(f.get("version") or ""),
                        str(f.get("timestamp") or ""),
                        group_key,
                    ),
                )
                inserted += cursor.rowcount
                db.execute(
                    "INSERT INTO hostnames(name,root_domain) VALUES(?,?) ON CONFLICT(name) DO NOTHING",
                    (str(f["hostname"]), group_key),
                )
            previous_primary = (
                db.execute(
                    "SELECT payload FROM entries WHERE id=?", (existing["attribution_entry_id"],)
                ).fetchone()
                if existing
                else None
            )
            fresh_primary = not previous_primary or observed(
                asdict(group.entries[0]), stamp
            ) >= observed(json.loads(previous_primary["payload"]), "")
            if (
                previous_primary
                and db.execute(
                    "SELECT 1 FROM case_entries WHERE entry_id=? LIMIT 1",
                    (existing["attribution_entry_id"],),
                ).fetchone()
                and signature(json.loads(previous_primary["payload"]))
                == signature(asdict(group.entries[0]))
            ):
                fresh_primary = False
            db.execute(
                "UPDATE leads SET attribution=?,attribution_entry_id=?,updated_at=?,new_observations=new_observations+? WHERE id=?",
                (
                    dump(attribution) if fresh_primary else existing["attribution"],
                    ids[0] if fresh_primary else existing["attribution_entry_id"],
                    stamp,
                    inserted
                    if existing and existing["status"] == "completed" and fresh_primary
                    else 0,
                    lead_id,
                ),
            )
            if inserted or cve_records:
                draft = json.loads(existing["draft"]) if existing else {}
                if existing:
                    draft["reviewed"] = False
                    draft["cve_reviewed"] = False
                records = {r["id"]: r for r in draft.get("cve_records", [])}
                records.update({r["id"]: r for r in cve_records or []})
                draft["cve_records"] = list(records.values())
                db.execute(
                    "UPDATE leads SET draft=?,draft_revision=draft_revision+? WHERE id=?",
                    (dump(draft), int(bool(existing)), lead_id),
                )
            if inserted:
                self.store.log(db, "observations", f"{inserted} observations added", lead_id)
            self.store.validate_attribution_entry(db, lead_id)
            from .registry_profile import seed_entity

            populated = seed_entity(db, lead_id, attribution)
            if populated:
                self.store.log(
                    db,
                    "entity_registry_details",
                    "Populated matched registration fields: " + ", ".join(populated),
                    lead_id,
                )
            if not demo:
                from .provider_policy import is_provider

                if not is_provider(group.hostname):
                    db.execute(
                        "INSERT OR IGNORE INTO entity_contact_queue(entity_id) VALUES(?)",
                        (lead_id,),
                    )
            # Qualification records findings; notification scope is an explicit action.
            # Associate commits event/finding membership after filtering, local
            # risk evaluation and attribution. Raw imports and old case scopes
            # remain immutable; recurring events add history without new work.
            from .awareness import associate

            for entry in group.entries:
                associate(
                    db,
                    asdict(entry),
                    import_id=import_id,
                    source_sha256=source_hash,
                    entity_id=lead_id,
                    admitted=True,
                    reason="qualified",
                    admission_authority={
                        "authority_kind": "analyst_qualification"
                        if attribution.get("review")
                        else "intake_qualification",
                        "authority_ref": str(
                            (attribution.get("review") or {}).get("id")
                            or attribution.get("result_id")
                            or pending_id
                        ),
                        "actor": str(
                            (attribution.get("review") or {}).get("reviewer") or "intake_pipeline"
                        ),
                        "evidence_ref": dump(
                            {
                                "attribution_result_id": attribution.get("result_id"),
                                "review": attribution.get("review"),
                                "qualified_queue_id": pending_id,
                            }
                        ),
                    },
                    fallback=stamp,
                )
            register_group(
                db, import_id, group.hostname, group.entries, entity_id=lead_id, qualified=True
            )
        return lead_id
