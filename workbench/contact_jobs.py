"""Finite, cancellable first-party contact lookups, with one automatic lookup per established entity."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import queue
import threading
import time

from .contact_discovery import ContactDiscovery, DiscoveryLimits
from .contact_discovery.engine import REVISION
from .contact_discovery.policy import approved_scope, approved_url
from .contact_records import ContactConflict, ContactRecords
from .contact_evidence import snapshot_path
from .primitives import now, uid

ACTIVE = ("queued", "running", "cancelling")


class ContactDiscoveryJobs:
    def __init__(self, store, discovery_factory=None):
        self.store = store
        self.records = ContactRecords(store)
        self.core_factory = discovery_factory or ContactDiscovery
        self.limits = DiscoveryLimits()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="companion-contacts")
        self.lock = threading.RLock()
        self.jobs = {}
        self.closed = False
        self.automatic_stop = threading.Event()
        self.automatic_thread = None
        # Workspaces have one process owner; a prior interrupted process has no live jobs.
        with self.store.transaction() as db:
            db.execute("DELETE FROM contact_discovery_locks")
            db.execute("UPDATE entity_contact_queue SET status='pending' WHERE status='running'")

    def start_automatic(self):
        if self.automatic_thread or self.closed:
            return
        self.automatic_thread = threading.Thread(
            target=self._automatic_loop, daemon=True, name="entity-contact-scheduler"
        )
        self.automatic_thread.start()

    def _automatic_loop(self):
        while not self.automatic_stop.is_set():
            try:
                for _ in range(25):
                    if (
                        self.automatic_stop.is_set()
                        or self.busy()
                        or self.automatic_once() is not None
                    ):
                        break
            except Exception:
                # Maintenance, startup and shutdown can temporarily own the DB.
                # The durable queue retains unfinished work for the next pass.
                pass
            self.automatic_stop.wait(2)

    def automatic_once(self):
        """Dispatch at most one background lookup; no retry storm or intake delay."""
        from .provider_policy import is_provider

        if (
            self.closed
            or self.busy()
            or (getattr(self.store, "maintenance", None) and self.store.maintenance.is_set())
        ):
            return None
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT q.entity_id,q.mode,l.domain FROM entity_contact_queue q JOIN leads l ON l.id=q.entity_id WHERE q.status='pending' AND l.merged_into IS NULL AND l.demo=0 ORDER BY q.updated_at,q.rowid LIMIT 1"
            ).fetchone()
            if not row:
                return None
            if (
                (is_provider(row["domain"]) and row["mode"] != "refresh")
                or (
                    row["mode"] == "initial"
                    and db.execute(
                        "SELECT 1 FROM contact_runs WHERE entity_id=? LIMIT 1", (row["entity_id"],)
                    ).fetchone()
                )
                or (row["mode"] == "missing" and self._has_contact(row["entity_id"], db))
            ):
                db.execute(
                    "UPDATE entity_contact_queue SET status='done',updated_at=? WHERE entity_id=?",
                    (now(), row["entity_id"]),
                )
                return None
            db.execute(
                "UPDATE entity_contact_queue SET status='running',updated_at=?,error='' WHERE entity_id=?",
                (now(), row["entity_id"]),
            )
        try:
            return self.start(row["entity_id"], refresh=row["mode"] != "initial", _automatic=True)
        except ContactConflict:
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE entity_contact_queue SET status='pending',updated_at=? WHERE entity_id=?",
                    (now(), row["entity_id"]),
                )
        except Exception:
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE entity_contact_queue SET status='failed',updated_at=?,error='Automatic contact lookup unavailable' WHERE entity_id=?",
                    (now(), row["entity_id"]),
                )
        return None

    def _has_contact(self, entity_id, db):
        from .contact_outcomes import directory_contact

        contact = directory_contact(self.store, entity_id, db)
        return bool(contact["email"] or contact["phone"] or contact["form"])

    def queue_directory(self, entity_id=None):
        """Durable work, dispatched sequentially by the existing background scheduler."""
        if self.closed or (
            getattr(self.store, "maintenance", None) and self.store.maintenance.is_set()
        ):
            raise ContactConflict("Contact discovery is temporarily unavailable")
        with self.store.transaction() as db:
            if entity_id:
                entity_id = self.records._entity(entity_id, db)
            clause = " AND id=?" if entity_id else ""
            rows = db.execute(
                "SELECT id FROM leads WHERE merged_into IS NULL AND demo=0" + clause,
                (entity_id,) if entity_id else (),
            ).fetchall()
            count = 0
            for row in rows:
                count += db.execute(
                    "INSERT INTO entity_contact_queue(entity_id,status,updated_at,error,mode) VALUES(?,'pending',?,'',?) ON CONFLICT(entity_id) DO UPDATE SET status='pending',updated_at=excluded.updated_at,error='',mode=excluded.mode WHERE entity_contact_queue.status NOT IN ('pending','running')",
                    (row["id"], now(), "refresh" if entity_id else "missing"),
                ).rowcount
        return {"queued": count, **self.directory_status()}

    def directory_status(self):
        counts = {
            r["status"]: r["n"]
            for r in self.store.all(
                "SELECT status,count(*) n FROM entity_contact_queue GROUP BY status"
            )
        }
        return {
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "failed": counts.get("failed", 0),
        }

    def busy(self):
        with self.lock:
            return any(job["state"] in ACTIVE for job in self.jobs.values())

    active = busy

    def state(self, entity_id):
        result = self.records.state(entity_id)
        with self.lock:
            active = next(
                (
                    job
                    for job in reversed(list(self.jobs.values()))
                    if result["entity_id"] in job["entity_ids"] and job["state"] in ACTIVE
                ),
                None,
            )
            result["active_job"] = self.get(active["id"]) if active else None
        return result

    def _cached(self, scope, include_www, source_url=None):
        row = self.store.one(
            "SELECT * FROM contact_runs WHERE entity_id=? AND root_domain=? ORDER BY rowid DESC LIMIT 1",
            (scope["entity_id"], scope["root_domain"]),
        )
        if not row or row["status"] not in ("relevant_found", "general_only", "not_found"):
            return None
        result = json.loads(row["payload"])
        if json.loads(row["scope"])["fingerprint"] != scope["fingerprint"]:
            return None
        if (
            result.get("discovery_revision") != REVISION
            or result.get("source_url", "") != (source_url or "")
            or set(result.get("aliases", [])) != set(approved_scope(scope["root_domain"])[1])
        ):
            return None
        for snapshot in result.get("snapshots", []):
            snapshot_path(self.store, row["id"], snapshot)
        age = datetime.now(timezone.utc) - datetime.fromisoformat(
            row["finished_at"].replace("Z", "+00:00")
        )
        return self.records._run(row) if 0 <= age.total_seconds() < 86400 else None

    def start(
        self,
        entity_id,
        root_domain=None,
        include_www=True,
        refresh=False,
        source_url=None,
        *,
        _automatic=False,
    ):
        with self.store.lock:
            scope = self.records.scope(entity_id, root_domain)
            if source_url:
                root, aliases = approved_scope(scope["root_domain"])
                source_url = approved_url(source_url, {root, *aliases})
            return self._enqueue(
                [scope], True, refresh, source_url=source_url, automatic=_automatic
            )

    def batch(self, entity_ids, include_www=True):
        identities = list(dict.fromkeys(entity_ids))
        if not identities or len(identities) > 25:
            raise ValueError("Select between one and 25 businesses for contact discovery")
        scopes, skipped = [], []
        with self.store.lock:
            for identity in identities:
                try:
                    entity_id = self.records._entity(identity)
                    scope = self.records.scope(entity_id)
                    if scope["entity_id"] not in {s["entity_id"] for s in scopes}:
                        scopes.append(scope)
                except (ValueError, OSError) as error:
                    skipped.append(
                        {"entity_id": identity, "status": "skipped", "reason": str(error)}
                    )
            # Missing/unusable routes need a fresh explicit lookup, not a cached
            # run that still contains the same bounced or changed contact.
            return self._enqueue(scopes, True, True, skipped)

    def _enqueue(self, scopes, include_www, refresh, skipped=(), source_url=None, automatic=False):
        with self.lock:
            if self.closed or (
                getattr(self.store, "maintenance", None) and self.store.maintenance.is_set()
            ):
                raise ContactConflict(
                    "Contact discovery is unavailable while the workspace is closing or changing"
                )
            active = [job for job in self.jobs.values() if job["state"] in ACTIVE]
            identities = [scope["entity_id"] for scope in scopes]
            if any(set(identities).intersection(job["entity_ids"]) for job in active):
                raise ContactConflict(
                    "Contact discovery is already running for a selected business"
                )
            if len(active) >= 4:
                raise ContactConflict("Four contact discovery jobs are already queued or running")
            identity = uid()
            job = {
                "id": identity,
                "state": "queued",
                "entity_ids": identities,
                "completed": 0,
                "total": len(scopes),
                "current_entity": None,
                "results": list(skipped),
                "error": "",
                "created_at": now(),
                "finished_at": None,
                "cancel": threading.Event(),
                "cached": False,
                "automatic": automatic,
            }
            with self.store.transaction() as db:
                actor = (
                    "Automatic discovery"
                    if automatic
                    else self.store.settings().get("analyst_name") or "Local operator"
                )
                for scope in scopes:
                    entity = scope["entity_id"]
                    db.execute(
                        "INSERT INTO contact_discovery_locks VALUES(?,?)", (entity, identity)
                    )
                    self.store.log(
                        db,
                        "contact_discovery_started",
                        f"{actor} requested contact discovery for {scope['root_domain']}; "
                        f"job {identity}; apex/www website pair; "
                        + (f"focused source {source_url}; " if source_url else "")
                        + f"limits {json.dumps(asdict(self.limits), sort_keys=True)}",
                        entity,
                    )
            for key in [key for key, old in self.jobs.items() if old["state"] not in ACTIVE][:-30]:
                self.jobs.pop(key)
            self.jobs[identity] = job
            self.pool.submit(self._run, identity, scopes, include_www, refresh, source_url)
            return self.get(identity)

    def _discover(self, scope, include_www, cancel, source_url=None):
        """The core owns no application files. A stalled injected core cannot hold a job open."""
        output = queue.Queue(maxsize=1)
        capture_cancel = threading.Event()

        def call():
            try:
                engine = self.core_factory()
                value = engine.discover(
                    scope["root_domain"],
                    aliases=approved_scope(scope["root_domain"])[1],
                    cancel_event=capture_cancel,
                    **({"source_url": source_url} if source_url else {}),
                )
                output.put((True, value))
            except Exception:
                output.put((False, "Contact lookup failed; no new contact details were applied"))

        worker = threading.Thread(target=call, daemon=True, name="contact-discovery-capture")
        worker.start()
        deadline = time.monotonic() + self.limits.timeout + 2
        while True:
            if cancel.is_set():
                capture_cancel.set()
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                capture_cancel.set()
                raise TimeoutError("Contact lookup exceeded its time budget")
            try:
                ok, value = output.get(timeout=min(0.1, remaining))
            except queue.Empty:
                continue
            if not ok:
                raise ValueError(value)
            return value

    def _run(self, identity, scopes, include_www, refresh, source_url=None):
        job = self.jobs[identity]
        terminal = "failed"
        try:
            with self.lock:
                job["state"] = "cancelling" if job["cancel"].is_set() else "running"
            for scope in scopes:
                if job["cancel"].is_set():
                    break
                with self.lock:
                    job["current_entity"] = scope["entity_id"]
                try:
                    current = self.records.scope(scope["entity_id"], scope["root_domain"])
                    if current["fingerprint"] != scope["fingerprint"]:
                        raise ContactConflict("Attribution changed while this lookup was queued")
                    cached = None if refresh else self._cached(scope, include_www, source_url)
                    result = cached or self._discover(scope, include_www, job["cancel"], source_url)
                    if job["cancel"].is_set() or result is None:
                        break
                    if not cached:
                        result = self.records.save_run(scope, result, asdict(self.limits))
                    if job["automatic"]:
                        self.records.automatic_default(scope["entity_id"])
                    item = {
                        "entity_id": scope["entity_id"],
                        "root_domain": scope["root_domain"],
                        "run_id": result["id"],
                        "status": result["status"],
                        "outcome": result.get("outcome", ""),
                        "next_step": result.get("next_step", ""),
                        "cached": bool(cached),
                    }
                    if result["status"] == "failed":
                        item["error"] = next(
                            (
                                issue.get("message", "Lookup failed")
                                for issue in result.get("issues", [])
                            ),
                            "Contact lookup failed",
                        )
                except Exception as error:
                    item = {
                        "entity_id": scope["entity_id"],
                        "root_domain": scope["root_domain"],
                        "status": "failed",
                        "error": str(error)
                        if isinstance(error, (ValueError, TimeoutError))
                        else "Contact evidence could not be saved",
                    }
                with self.lock:
                    job["results"].append(item)
                    job["completed"] += 1
                    job["cached"] = bool(job["results"]) and all(
                        item.get("cached", False) for item in job["results"]
                    )
            with self.lock:
                failures = [item for item in job["results"] if item["status"] == "failed"]
                terminal = (
                    "cancelled"
                    if job["cancel"].is_set()
                    else "failed"
                    if failures and len(failures) == len(scopes)
                    else "completed"
                )
                if failures:
                    job["error"] = failures[0]["error"]
        except Exception:
            with self.lock:
                terminal, job["error"] = "failed", "Contact discovery could not finish"
        finally:
            try:
                with self.store.transaction() as db:
                    for scope in scopes:
                        item = next(
                            (
                                item
                                for item in job["results"]
                                if item["entity_id"] == scope["entity_id"]
                            ),
                            {},
                        )
                        outcome = item.get("status", terminal)
                        db.execute(
                            "UPDATE entity_contact_queue SET status=?,updated_at=?,error=? WHERE entity_id=?",
                            (
                                "pending"
                                if terminal == "cancelled" and self.closed
                                else "failed"
                                if outcome in ("failed", "cancelled")
                                else "done",
                                now(),
                                item.get("error", ""),
                                scope["entity_id"],
                            ),
                        )
                        self.store.log(
                            db,
                            "contact_discovery_finished",
                            f"Contact discovery job {identity} for {scope['root_domain']}: {outcome}"
                            + (f"; reused run {item['run_id']}" if item.get("cached") else "")
                            + (f"; {item['error']}" if item.get("error") else ""),
                            scope["entity_id"],
                        )
                    db.execute("DELETE FROM contact_discovery_locks WHERE job_id=?", (identity,))
            finally:
                with self.lock:
                    job["state"] = terminal
                    job["current_entity"], job["finished_at"] = None, now()

    def get(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError("Contact discovery job not found; it may predate this session")
            return deepcopy({k: v for k, v in self.jobs[identity].items() if k != "cancel"})

    def cancel(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if not job:
                raise ValueError("Contact discovery job not found")
            if job["state"] in ACTIVE:
                job["cancel"].set()
                job["state"] = "cancelling"
            return self.get(identity)

    def close(self):
        self.automatic_stop.set()
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job["state"] in ACTIVE:
                    job["cancel"].set()
        if self.automatic_thread and self.automatic_thread is not threading.current_thread():
            self.automatic_thread.join(timeout=3)
        self.pool.shutdown(wait=True, cancel_futures=False)
