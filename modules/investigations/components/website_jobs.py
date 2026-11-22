"""Bounded viewport jobs; evidence attachment is a short guarded transaction."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
from urllib.parse import urlsplit

from .cases import Cases
from .image_evidence import metadata_path
from . import website_evidence
from modules.tools.components.network_identity import root_domain
from modules.workspace.components.primitives import now, uid
from .reviews.queries import SectionReviewQueries
from modules.tools.components.website_capture import capture_website, download_activity, web_url


class WebsiteCaptureJobs:
    def __init__(self, store, capture=None):
        self.store = store
        self.capture = capture or capture_website
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="companion-website")
        self.jobs = {}
        self.closed = False

    def scope(self, case_id):
        lead = Cases(self.store).view(case_id)
        if not lead:
            raise ValueError("Notification not found")
        hosts = []
        for entry in lead["entries"]:
            value = entry.get("source", {}).get("fields", {}).get("hostname") or entry.get(
                "hostname", ""
            )
            try:
                host = web_url("https://" + value).split("/")[2]
                if host not in hosts:
                    hosts.append(host)
            except (ValueError, TypeError):
                continue
        return lead, hosts

    def start(self, case_id, hostname):
        # Same lock order as workspace transfers: store, then job lock.
        with self.store.lock, self.lock:
            if self.closed or self.store.maintenance.is_set():
                raise ValueError(
                    "Website capture is unavailable while the workspace is closing or changing"
                )
            lead, hosts = self.scope(case_id)
            if hostname not in hosts:
                raise ValueError("Choose a hostname reported in this notification")
            with self.store.transaction() as db:
                Cases(self.store).require(db, case_id, editable=True)
                SectionReviewQueries(self.store).assert_editable(db, case_id, ("attribution",))
            active = [j for j in self.jobs.values() if j["state"] in ("queued", "running")]
            if same := next((j for j in active if j["case_id"] == case_id), None):
                return self.get(same["id"])
            if len(active) >= 2:
                raise ValueError("Two website captures are already queued or running")
            for key in [k for k, j in self.jobs.items() if j["state"] not in ("queued", "running")][
                :-20
            ]:
                self.jobs.pop(key, None)
            identity = uid()
            ports = {
                str(entry.get("source", {}).get("fields", {}).get("port", ""))
                for entry in lead["entries"]
                if entry.get("source", {}).get("fields", {}).get("hostname") == hostname
            }
            scheme = "http" if "80" in ports and "443" not in ports else "https"
            job = {
                "requested_url": web_url(scheme + "://" + hostname),
                "id": identity,
                "case_id": case_id,
                "lead_id": lead["id"],
                "hostname": hostname,
                "state": "queued",
                "created_at": now(),
                "message": "Queued",
                "cancel": threading.Event(),
            }
            self.jobs[identity] = job
            self.pool.submit(self._run, identity)
            return self.get(identity)

    def _run(self, identity):
        job = self.jobs[identity]
        with self.lock:
            job.update(state="running", message="Capturing website viewport")
        files = []
        committed = False
        metadata = {}
        outcome = {"state": "failed", "message": "Website capture did not finish"}
        try:
            png, result = self.capture(job["requested_url"], cancel_event=job["cancel"])
            if result.get("requested_url") != job["requested_url"]:
                raise ValueError("Capture provenance does not match the reported website request")
            metadata = website_evidence.capture_metadata(result)
            if job["cancel"].is_set():
                raise ValueError("Website capture cancelled")
            capture = website_evidence.prepare(
                self.store,
                png,
                metadata,
                root_domain=root_domain(urlsplit(job["requested_url"]).hostname),
            )
            # File writes remain outside the database lock and freeze never waits
            # on rendering/network. A competing freeze rejects the later attach.
            for key in ("path", "preview_path", "metadata_path"):
                files.append(self.store.path(capture[key]))
            caption = "Website viewport · " + job["hostname"]
            with self.store.transaction() as db:
                case = Cases(self.store).require(db, job["case_id"], editable=True)
                prior_version = case["version"]
                SectionReviewQueries(self.store).assert_editable(
                    db, job["case_id"], ("attribution",)
                )
                if job["cancel"].is_set() or self.store.maintenance.is_set():
                    raise ValueError("Capture cancelled before attachment")
                website_evidence.publish(db, capture)
                if website_evidence.is_usable_capture(
                    metadata
                ) and website_evidence.related_capture(metadata, capture["root_domain"]):
                    website_evidence.bind(
                        db, capture["id"], job["lead_id"], root_domain=capture["root_domain"]
                    )
                identity = website_evidence.attach(self.store, db, capture["id"], job["case_id"])
                files.append(self.store.path(metadata_path(identity)))
                db.execute(
                    "UPDATE cases SET draft=json_set(draft,'$.reviewed',json('false')),draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                    (now(), job["case_id"]),
                )
                self.store.log(
                    db,
                    "website_captured",
                    caption,
                    job["lead_id"],
                    job["case_id"],
                    metadata={
                        "capture": metadata,
                        "evidence_id": identity,
                        "sha256": capture["sha256"],
                    },
                )
            committed = True
            outcome = {
                "state": "completed",
                "message": {
                    "captured": "Viewport captured",
                    "partial": "Viewport captured with incomplete content",
                    "challenge": "Access challenge captured",
                    "login_required": "Login page captured",
                    "load_failed": "Page did not load successfully",
                }[metadata["capture_status"]],
                "evidence_id": identity,
                "capture": metadata,
                "prior_version": prior_version,
                "case_version": prior_version + 1,
            }
        except Exception as error:
            observations = {}
            failed_capture = getattr(error, "metadata", metadata)
            if (
                isinstance(failed_capture, dict)
                and failed_capture.get("requested_url", job["requested_url"])
                == job["requested_url"]
            ):
                observations = download_activity(failed_capture)
            outcome = {
                "state": "cancelled" if job["cancel"].is_set() else "failed",
                "message": str(error)[:500] or "Website capture failed",
                **observations,
            }
            # Keep a small immutable chronology entry; failed attempts never pose
            # as confirmed business pages or alter the notification draft.
            try:
                with self.store.transaction() as db:
                    self.store.log(
                        db,
                        "website_capture_failed",
                        outcome["message"],
                        job["lead_id"],
                        job["case_id"],
                        metadata={
                            "hostname": job["hostname"],
                            "capture_job": job["id"],
                            **observations,
                        },
                    )
            except Exception:
                pass
        finally:
            if not committed:
                for path in files:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        outcome.update(
                            state="failed",
                            message="Website capture was not attached. Temporary file cleanup failed; close the app and check file access before retrying.",
                        )
            with self.lock:
                # A terminal job is no longer considered busy by workspace
                # maintenance. Publish it only after attachment/cleanup settles.
                job.update(**outcome, finished_at=now())

    def get(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError("Capture job is unavailable; attached evidence remains saved")
            return deepcopy({k: v for k, v in self.jobs[identity].items() if k != "cancel"})

    def cancel(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError("Capture job not found")
            self.jobs[identity]["cancel"].set()
        return self.get(identity)

    def busy(self):
        with self.lock:
            return any(j["state"] in ("queued", "running") for j in self.jobs.values())

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                job["cancel"].set()
        self.pool.shutdown(wait=False, cancel_futures=True)
