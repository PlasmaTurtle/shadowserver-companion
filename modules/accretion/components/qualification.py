"""Qualify filtered observations into a lead with three retained evidence pillars.

Local exclusions precede browser work. A functioning, related website precedes
fresh attribution. This component never scores, discovers contacts or creates
canonical entities; those are Evaluate and Associate responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from modules.attribution.components.attribution_bridge import RegistrationAttribution
from modules.tools.components.website_capture import capture_website, WebsiteLoadError, web_url
from modules.investigations.components import website_evidence
from modules.investigations.components.outreach_policy import entity_hold

from . import awareness
from .intake.domains import registry_address
from .intake_filter import IntakeInterrupted
from .intake.records import observation_payload
from .qualified_lead import QualifiedLead
from .report import ReportCandidate
from .qualification_context import recognize_group


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
        hold = entity_hold(db, recognition["entity_id"])
        if hold:
            return recognition, (), "outreach_" + hold["state"]
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
    return QualifiedLead(
        candidate,
        attribution,
        tuple(coverage),
        website,
        tuple(evidence["findings"]),
        evidence["ownership_token"],
    )


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

    def website(self, group):
        attempts, seen_hosts, attempted_urls = [], set(), set()
        for entry in group.observations:
            host = str(entry.source.fields["hostname"]).strip().lower().rstrip(".")
            if host in seen_hosts:
                continue
            seen_hosts.add(host)
            self.checkpoint()
            requested_url = web_url("https://" + host + "/")
            try:
                png, metadata = self.capture(
                    requested_url,
                    cancel_event=self.cancel_event,
                    skip_urls=frozenset(attempted_urls),
                    require_usable=True,
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
                    }
                )
                continue
            except (OSError, ValueError, TimeoutError) as error:
                self.checkpoint()
                attempts.append(
                    {
                        "method": "website",
                        "hostname": host,
                        "status": "tool_error",
                        "message": str(error)[:500],
                    }
                )
                # A broken browser/tool cannot be repaired by trying every host.
                return None, attempts, "website_capture_error"
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
                    "attempts": metadata.get("attempts", []),
                }
            )
            if website_evidence.is_usable_capture(metadata) and related:
                return (
                    website_evidence.retain(
                        self.store, png, metadata, root_domain=group.root_domain
                    ),
                    attempts,
                    None,
                )
            if website_evidence.is_usable_capture(metadata) and not related:
                attempts[-1]["reason"] = "website_identity_review"
        reason = (
            "website_identity_review"
            if any(a.get("reason") == "website_identity_review" for a in attempts)
            else "website_unavailable"
        )
        return None, attempts, reason

    def qualify(self, candidate: ReportCandidate, *, refresh=False) -> QualificationDecision:
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
        website, attempts, reason = self.website(group)
        evidence = {
            "version": 1,
            "root_domain": group.root_domain,
            "website": website,
            "findings": list(findings),
            "ownership_token": recognition["ownership_token"],
        }
        if reason:
            return QualificationDecision("deferred", reason, tuple(attempts), evidence)
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
        if recognition["state"] == "known":
            decision = reuse_attribution(
                self.store,
                group,
                self.client.module.store,
                entity_id=recognition["entity_id"],
                saved_proof=recognition.get("saved_proof"),
                refresh=refresh,
            )
        if decision is None:
            decision = self.client.qualify(group, refresh=refresh)
        if decision.status == "review" and not refresh:
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
