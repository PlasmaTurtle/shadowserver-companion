"""Qualify filtered observations into a lead with three retained evidence pillars.

Local exclusions precede browser work. A functioning, related website precedes
fresh attribution. This component never scores, discovers contacts or creates
canonical entities; those are Evaluate and Associate responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from time import monotonic

from modules.attribution.components.attribution_bridge import RegistrationAttribution
from modules.tools.components.website_capture import (
    CaptureBrowserStartupError,
    capture_website,
    download_activity,
    WebsiteLoadError,
    web_url,
)
from modules.investigations.components import website_evidence

from . import awareness
from .deconfliction import exact_host_entries, url_hostname
from .intake.domains import registry_address
from .intake_filter import IntakeInterrupted
from .intake.records import observation_payload
from .qualified_lead import QualifiedLead
from .report import ReportCandidate
from .qualification_context import recognize_group
from .website_identity import rejection_reason as website_rejection

GROUP_WEBSITE_SECONDS = 110


@dataclass(frozen=True, slots=True)
class QualificationDecision:
    status: str
    reason: str
    attempts: tuple = ()
    evidence: dict = field(default_factory=dict)
    result_id: str | None = None
    lead: QualifiedLead | None = None

    def __post_init__(self):
        if self.status not in {
            "qualified",
            "dismissed",
            "deferred",
            "no_public_ip",
            "no_match",
            "review",
        }:
            raise ValueError("Unknown qualification outcome")
        if self.lead is not None and not isinstance(self.lead, QualifiedLead):
            raise TypeError("A qualification outcome can carry only a QualifiedLead")
        if (self.status == "qualified") != (self.lead is not None):
            raise ValueError("Only a qualified decision may carry a QualifiedLead")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("A qualification decision requires a reason")
        if self.lead is not None and self.evidence != self.lead.evidence():
            raise ValueError("Qualification decision evidence must describe its lead")

    def defer(self, reason, message):
        """Retain evidence when a mutable local gate changes before publication."""
        return replace(
            self,
            status="deferred",
            reason=reason,
            lead=None,
            attempts=self.attempts
            + ({"method": "local", "status": "deferred", "reason": reason, "message": message},),
        )


def local_scope(store, group):
    """Read current ownership and applicable work exclusions through their owners."""
    recognition = recognize_group(store, group)
    if recognition["state"] == "review":
        return recognition, (), "association_conflict"
    entries = [observation_payload(entry) for entry in group.observations]
    with store.read_snapshot() as db:
        findings = awareness.actionable_scope(db, entries, entity_id=recognition["entity_id"])
    if not findings:
        return recognition, (), "no_actionable_findings"
    if not any(
        (address := registry_address(entry.ip)).is_global and not address.is_multicast
        for entry in group.observations
    ):
        return recognition, (), "no_public_ip"
    return recognition, tuple(findings), None


def complete_lead(
    store, candidate: ReportCandidate, attribution, coverage, evidence
) -> QualifiedLead:
    """Complete automatic or reviewed evidence without recapturing a saved page."""
    website = website_evidence.get(store, evidence["website"]["id"])
    lead = QualifiedLead(
        candidate,
        attribution,
        tuple(coverage),
        website,
        tuple(evidence["findings"]),
        evidence["ownership_token"],
    )
    if reason := website_rejection(website["capture"], candidate.group.root_domain):
        raise ValueError("The saved page cannot establish business identity: " + reason)
    return lead


def prior_website_attempts(attempts):
    """Retain bounded download observations per reported host when replacing a job's attempts."""
    by_host = {}
    for attempt in attempts:
        host = attempt.get("hostname")
        if not host or attempt.get("method") != "website" or "download_activity" not in attempt:
            continue
        observed = download_activity(attempt).get("download_activity")
        if not observed:
            continue
        if host in by_host:
            previous = by_host[host]
            observed = download_activity(
                {
                    "download_activity": {
                        "attempts": previous["attempts"] + observed["attempts"],
                        "truncated": previous["truncated"] or observed["truncated"],
                    },
                }
            )["download_activity"]
        by_host[host] = observed
    return [
        {
            "method": "website",
            "hostname": host,
            "status": "previous_capture",
            "download_activity": activity,
        }
        for host, activity in by_host.items()
    ]


class Qualifier:
    """One import's lazy attribution client; no provider opens before the site gate."""

    def __init__(self, store, config, cancel_event, *, attribution_factory=None, capture=None):
        self.store = store
        self.config = config
        self.cancel_event = cancel_event
        self.attribution_factory = attribution_factory or RegistrationAttribution
        self.capture = capture or capture_website
        self.client = None

    def close(self):
        if self.client is not None:
            self.client.close()

    def checkpoint(self):
        if self.cancel_event.is_set():
            raise IntakeInterrupted()

    def website(
        self,
        group,
        *,
        owner=None,
        refresh=False,
        resume_host=None,
        candidate_indices=None,
        referral_status=None,
    ):
        attempts, attempted_urls = [], set()
        hosts = list(
            dict.fromkeys(
                entry.source.fields["hostname"].strip().lower().rstrip(".")
                for index, entry in enumerate(group.observations)
                if candidate_indices is None or index in candidate_indices
            )
        )
        first = hosts.index(resume_host) if resume_host in hosts else 0
        deadline = monotonic() + GROUP_WEBSITE_SECONDS

        def page_check(page):
            if reason := website_rejection(page, group.root_domain):
                return reason
            destination = url_hostname(page.get("final_url"))
            if referral_status is not None:
                if destination not in referral_status:
                    with self.store.read_snapshot() as db:
                        referral_status[destination] = bool(
                            next(exact_host_entries(db, [destination]), None)
                        )
                if referral_status[destination]:
                    return "website_deconflicted_destination"
            return None

        for host in hosts[first:]:
            self.checkpoint()
            if monotonic() >= deadline:
                attempts.append(
                    {
                        "method": "website",
                        "hostname": host,
                        "status": "work_limit",
                        "reason": "website_budget_exhausted",
                    }
                )
                return None, attempts, "website_budget_exhausted"
            requested_url = web_url("https://" + host + "/")
            if owner and not refresh:
                saved = website_evidence.recent_for_host(
                    self.store,
                    owner,
                    requested_url,
                    since=datetime.now(timezone.utc) - timedelta(days=1),
                )
                if saved and not page_check(saved["capture"]):
                    attempts.append(
                        {
                            "method": "website",
                            "hostname": host,
                            "status": "reused",
                            "capture_id": saved["id"],
                            "captured_at": saved["captured_at"],
                            "requested_url": requested_url,
                            "final_url": saved["final_url"],
                        }
                    )
                    return saved, attempts, None
            try:
                png, metadata = self.capture(
                    requested_url,
                    cancel_event=self.cancel_event,
                    skip_urls=frozenset(attempted_urls),
                    require_usable=True,
                    page_check=page_check,
                    deadline=deadline,
                )
            except WebsiteLoadError as error:
                self.checkpoint()
                attempted_urls.update(error.attempted_urls)
                attempts.append(
                    {
                        "method": "website",
                        "hostname": host,
                        "status": "load_failed",
                        "message": str(error),
                        "attempts": error.metadata.get("attempts", []),
                        **download_activity(error.metadata),
                    }
                )
                for attempt in error.metadata.get("attempts", []):
                    if attempt.get("outcome") == "rejected":
                        attempts[-1]["reason"] = attempt["reason"]
                continue
            except (OSError, ValueError, TimeoutError) as error:
                self.checkpoint()
                if monotonic() >= deadline:
                    attempts.append(
                        {
                            "method": "website",
                            "hostname": host,
                            "status": "work_limit",
                            "reason": "website_budget_exhausted",
                            **download_activity(getattr(error, "metadata", {})),
                        }
                    )
                    return None, attempts, "website_budget_exhausted"
                attempts.append(
                    {
                        "method": "website",
                        "hostname": host,
                        "status": "tool_error",
                        "message": str(error)[:500],
                        **download_activity(getattr(error, "metadata", {})),
                    }
                )
                # A broken browser/tool cannot be repaired by trying every host.
                return (
                    None,
                    attempts,
                    (
                        "capture_browser_startup"
                        if isinstance(error, CaptureBrowserStartupError)
                        else "website_capture_error"
                    ),
                )
            self.checkpoint()
            if metadata.get("requested_url") != requested_url:
                attempts.append(
                    {
                        "method": "website",
                        "hostname": host,
                        "status": "tool_error",
                        "message": "Capture provenance does not match the reported website request",
                    }
                )
                return None, attempts, "website_capture_error"
            attempted_urls.update(metadata.get("attempted_urls", []))
            status = metadata.get("capture_status", "load_failed")
            related = website_evidence.related_capture(metadata, group.root_domain)
            attempts.append(
                {
                    "method": "website",
                    "hostname": host,
                    "status": status,
                    "requested_url": metadata.get("requested_url"),
                    "final_url": metadata.get("final_url"),
                    "redirects": metadata.get("redirects", []),
                    "attempts": metadata.get("attempts", []),
                    **download_activity(metadata),
                }
            )
            identity_reason = (
                page_check(metadata) if website_evidence.is_usable_capture(metadata) else None
            )
            if website_evidence.is_usable_capture(metadata) and related and not identity_reason:
                return (
                    website_evidence.retain(
                        self.store, png, metadata, root_domain=group.root_domain
                    ),
                    attempts,
                    None,
                )
            if identity_reason:
                attempts[-1]["reason"] = identity_reason
        reason = next((a["reason"] for a in attempts if a.get("reason")), "website_unavailable")
        return None, attempts, reason

    def qualify(
        self, candidate: ReportCandidate, *, refresh=False, resume_host=None
    ) -> QualificationDecision:
        from modules.attribution.components.attribution_reuse import reuse_attribution, reuse_review
        from modules.entities.components.ownership import (
            OwnershipChanged,
            check_qualification_context,
        )

        if not isinstance(candidate, ReportCandidate):
            raise TypeError("Qualify requires a report candidate")
        group = candidate.group
        self.checkpoint()
        recognition, findings, reason = local_scope(self.store, group)
        if reason:
            status = (
                "dismissed"
                if reason == "no_actionable_findings"
                else "no_public_ip"
                if reason == "no_public_ip"
                else "deferred"
            )
            return QualificationDecision(
                status,
                reason,
                ({"method": "local", "status": reason, "message": recognition["basis"]},),
            )
        # Choose evidence from admissible sources before network work. Associate
        # still owns the decision and checks current referrals at commit time.
        hosts = [
            entry.source.fields["hostname"].casefold().rstrip(".") for entry in group.observations
        ]
        with self.store.read_snapshot() as db:
            referred = {row["identifier"] for row in exact_host_entries(db, hosts)}
        admissible = {
            item["entry_index"] for item in findings if hosts[item["entry_index"]] not in referred
        }
        selected = admissible if referred and admissible else None
        website, attempts, reason = self.website(
            group,
            owner=recognition["entity_id"],
            refresh=refresh,
            resume_host=resume_host,
            candidate_indices=selected,
            # A fully referred group can still qualify before Associate excludes it.
            referral_status={host: host in referred for host in hosts} if admissible else None,
        )
        evidence = {
            "version": 1,
            "root_domain": group.root_domain,
            "website": website,
            "findings": list(findings),
            "ownership_token": recognition["ownership_token"],
        }
        if reason:
            return QualificationDecision(
                "dismissed" if reason in {"website_parked", "website_unidentified"} else "deferred",
                reason,
                tuple(attempts),
                evidence,
            )
        self.checkpoint()
        try:
            with self.store.read_snapshot() as db:
                check_qualification_context(
                    db,
                    group.root_domain,
                    [observation_payload(entry) for entry in group.observations],
                    recognition["ownership_token"],
                )
        except OwnershipChanged as error:
            return QualificationDecision(
                "deferred", "ownership_changed", tuple(attempts), evidence
            ).defer("ownership_changed", str(error))
        if self.client is None:
            self.client = self.attribution_factory(
                self.store, self.config, cancel_event=self.cancel_event
            )
        decision = None
        if recognition["state"] == "known" and selected is None:
            decision = reuse_attribution(
                self.store,
                group,
                self.client.module.store,
                entity_id=recognition["entity_id"],
                saved_proof=recognition.get("saved_proof"),
                refresh=refresh,
            )
        if selected is not None:
            decision = self.client.qualify(group, refresh=refresh, candidate_indices=selected)
        elif decision is None:
            decision = self.client.qualify(group, refresh=refresh)
        if decision.status == "review" and not refresh and selected is None:
            decision = (
                reuse_review(self.store, group, self.client.module.store, decision.result_id)
                or decision
            )
        self.checkpoint()
        attempts.extend(decision.attempts)
        if refresh:
            attempts.append(
                {
                    "method": "history",
                    "status": "refreshed",
                    "reason": "explicit_attribution_refresh",
                    "result_id": decision.result_id,
                }
            )
        if decision.status != "qualified":
            return QualificationDecision(
                decision.status,
                "attribution_" + decision.status,
                tuple(attempts),
                evidence,
                decision.result_id,
            )
        lead = complete_lead(self.store, candidate, decision.proof, decision.coverage, evidence)
        return QualificationDecision(
            "qualified", "qualified", tuple(attempts), lead.evidence(), decision.result_id, lead
        )
