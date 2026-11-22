"""Offline, source-preserving chronology for a certified notification package.

Retrieving a registry response is not a validation decision. These events retain
separate clocks, and old records with no decision clock remain explicitly undated.
This module neither consults current settings nor performs network requests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer


SECTION_LABELS = {
    "introduction": "Introduction",
    "vulnerabilities": "Vulnerabilities",
    "attribution": "Attribution",
    "information": "Information",
    "closing": "Closing",
}


def _text(value):
    return "" if value is None else str(value)


def _clock(value):
    """Return a recorded aware instant only; never infer a missing timezone."""
    if not value:
        return None, "not_recorded"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError):
        return None, "invalid"
    if parsed.tzinfo is None:
        return None, "timezone_not_recorded"
    try:
        return parsed.astimezone(timezone.utc), "recorded"
    except (ValueError, OverflowError):
        return None, "invalid"


def _event(
    source_kind,
    action,
    created_at,
    *,
    source_id=None,
    actor=None,
    actor_kind=None,
    reason="",
    detail="",
    section_key=None,
    revision=None,
    context=None,
    label=None,
):
    instant, status = _clock(created_at)
    event = {
        "source_kind": source_kind,
        "source_id": source_id,
        "action": action,
        "label": label or action.replace("_", " ").capitalize(),
        "created_at": created_at or None,
        "timestamp_utc": instant.isoformat().replace("+00:00", "Z") if instant else None,
        "timestamp_status": status,
        "actor": actor or None,
        "actor_kind": actor_kind if actor else None,
        "reason": reason or "",
        "detail": detail or "",
        "section_key": section_key,
        "revision": revision,
        "context": context or {},
    }
    raw = json.dumps(event, sort_keys=True, ensure_ascii=False, default=str)
    event["id"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return event


def _proofs(lead):
    groups = lead.get("domain_groups") or []
    proofs = [
        (group.get("root_domain"), group["attribution"])
        for group in groups
        if isinstance(group.get("attribution"), dict) and group["attribution"]
    ]
    if not proofs and isinstance(lead.get("attribution"), dict) and lead["attribution"]:
        proofs = [(lead.get("domain"), lead["attribution"])]
    if not proofs:
        proofs = [
            (p.get("attribution", {}).get("root_domain", lead.get("domain")), p)
            for p in lead.get("qualified_lead", {}).get("whois", [])
            if isinstance(p, dict)
        ]
    # Multiple linked groups can point to the same captured result. Keep the
    # domain associations without duplicating its retrieval or decision events.
    unique = {}
    for domain, proof in proofs:
        identity = json.dumps(proof, sort_keys=True, ensure_ascii=False, default=str)
        item = unique.setdefault(identity, {"proof": proof, "domains": set()})
        if domain:
            item["domains"].add(domain)
    return [(item["proof"], sorted(item["domains"])) for _, item in sorted(unique.items())]


def build_chronology(lead, section_history, certification=None):
    """Return JSON-ready events in UTC order, with undated events at the end.

    ``created_at`` retains the source value; ``timestamp_utc`` is only populated
    for an aware ISO timestamp. ``timestamp_status`` distinguishes not recorded,
    invalid, and timezone-not-recorded values. Unknown actors are JSON null.
    Inputs are never mutated. Identical repeated records are deduplicated;
    source IDs and domain context keep distinct records distinguishable.
    """
    events = []
    for record in lead.get("history", []):
        actor, reason, detail = (
            record.get("actor"),
            record.get("reason", ""),
            record.get("detail", ""),
        )
        context = {"case_id": record.get("case_id") or lead.get("case_id")}
        if record.get("action") == "observation_scope_changed":
            try:
                decision = json.loads(detail)
            except (TypeError, ValueError):
                decision = {}
            if isinstance(decision, dict) and decision.get("decision") in {"include", "exclude"}:
                ids = decision.get("entry_ids", [])
                actor, reason = decision.get("actor"), decision.get("reason", "")
                verb = "Excluded from" if decision["decision"] == "exclude" else "Included in"
                detail = f"{verb} the recipient report: {len(ids)} observation(s). Original source evidence retained."
                if decision.get("reopened_sections"):
                    detail += (
                        " Reopened sections: " + ", ".join(decision["reopened_sections"]) + "."
                    )
                context["scope_decision"] = decision
        events.append(
            _event(
                "case_history",
                record.get("action", "activity"),
                record.get("created_at"),
                source_id=record.get("id"),
                actor=actor,
                actor_kind="analyst"
                if record.get("action") == "observation_scope_changed" and actor
                else record.get("actor_kind"),
                reason=reason,
                detail=detail,
                section_key=record.get("section_key"),
                revision=record.get("revision"),
                context=context,
            )
        )

    for proof, domains in _proofs(lead):
        evidence = proof.get("evidence") or {}
        attribution = proof.get("attribution") or {}
        review = proof.get("review") or {}
        context = {
            "root_domains": domains,
            "ip": proof.get("ip"),
            "source": proof.get("registry") or evidence.get("source_name"),
            "source_url": proof.get("source_url") or evidence.get("source_url"),
            "protocol": proof.get("protocol"),
            "result_id": proof.get("result_id"),
            "snapshot_id": proof.get("snapshot_id") or evidence.get("snapshot_id"),
            "body_sha256": proof.get("body_sha256"),
            "matched_domain": attribution.get("matched_domain"),
            "matched_field": attribution.get("field"),
            "matched_value": attribution.get("value"),
        }
        events.append(
            _event(
                "attribution",
                "source_retrieved",
                proof.get("retrieved_at") or evidence.get("retrieved_at"),
                source_id=context["snapshot_id"],
                context=context,
                detail="Saved source response used for attribution.",
                label="Attribution source retrieved",
            )
        )
        # An analyst acceptance and the module's earlier evaluation are two
        # decisions. A review timestamp must never become the module's clock.
        evaluated_at = proof.get("evaluated_at") or evidence.get("evaluated_at")
        if not evaluated_at and proof.get("result_id"):
            for summary in lead.get("attribution_summaries", []):
                details = summary.get("details") or {}
                if (
                    details.get("result_id") == proof["result_id"]
                    and details.get("snapshot_id") == context["snapshot_id"]
                    and summary.get("root_domain") in domains
                ):
                    evaluated_at = details.get("evaluated_at")
                    break
        if not evaluated_at and not review:
            evaluated_at = proof.get("validated_at")
        automatic_action = "attribution_evaluated" if review else "attribution_validated"
        events.append(
            _event(
                "attribution",
                automatic_action,
                evaluated_at,
                source_id=proof.get("result_id"),
                actor="Attribution Module" if evaluated_at else None,
                actor_kind="system" if evaluated_at else None,
                context=context,
                detail=(
                    "Automatic evaluation retained for analyst review."
                    if review
                    else "Automatic attribution decision linked to this notification."
                ),
                label="Attribution evaluated" if review else "Attribution validated",
            )
        )
        if review:
            decision = review.get("decision")
            label = {
                "accept": "Attribution accepted by analyst",
                "dismiss": "Attribution dismissed by analyst",
            }.get(decision, "Attribution reviewed by analyst")
            events.append(
                _event(
                    "attribution_review",
                    "attribution_review",
                    review.get("reviewed_at"),
                    source_id=review.get("id"),
                    actor=review.get("reviewer"),
                    actor_kind="analyst" if review.get("reviewer") else None,
                    reason=review.get("note", ""),
                    context={**context, "decision": decision},
                    label=label,
                )
            )

    for record in section_history or []:
        key = record.get("section_key")
        action = record.get("action", "activity")
        section = SECTION_LABELS.get(key, _text(key))
        events.append(
            _event(
                "section_history",
                action,
                record.get("created_at"),
                source_id=record.get("id"),
                actor=record.get("actor"),
                actor_kind=record.get("actor_kind"),
                reason=record.get("reason", ""),
                detail=record.get("detail", ""),
                section_key=key,
                revision=record.get("revision"),
                context={
                    k: record[k]
                    for k in (
                        "validation_id",
                        "dependency_hash",
                        "snapshot_hash",
                        "content_hash",
                        "draft_revision",
                    )
                    if k in record
                },
                label=(section + " - " + action.replace("_", " ")).strip(" -"),
            )
        )

    certification = certification if certification is not None else lead.get("certification")
    if certification:
        events.append(
            _event(
                "certification",
                "report_certified",
                certification.get("certified_at"),
                source_id=certification.get("report_id"),
                actor=certification.get("certified_by"),
                actor_kind="analyst" if certification.get("certified_by") else None,
                revision=certification.get("revision"),
                label="Notification report certified",
                detail="Final report certification recorded for this package.",
                context={"case_id": lead.get("case_id") or lead.get("notification_id")},
            )
        )

    unique = {event["id"]: event for event in events}
    # ISO strings with fractional seconds do not sort correctly beside whole
    # seconds; compare parsed instants, and use deterministic tie-breakers.
    end = datetime.max.replace(tzinfo=timezone.utc)
    source_order = {
        "case_history": 0,
        "attribution": 1,
        "attribution_review": 2,
        "section_history": 3,
        "certification": 4,
    }
    return sorted(
        unique.values(),
        key=lambda e: (
            _clock(e["created_at"])[0] or end,
            source_order[e["source_kind"]],
            _text(e["source_id"]),
            e["action"],
            e["id"],
        ),
    )


def _display_time(event):
    instant, status = _clock(event.get("created_at"))
    if instant:
        return (
            instant.strftime("%Y-%m-%d %H:%M:%S")
            + ("." + f"{instant.microsecond:06}" if instant.microsecond else "")
            + " UTC"
        )
    if status == "not_recorded":
        return "Timestamp not recorded"
    return _text(event.get("created_at")) + (
        " (timezone not recorded)"
        if status == "timezone_not_recorded"
        else " (invalid recorded timestamp)"
    )


def render_work_log(data, events, pdf_path):
    """Render the supplied historical records without live lookups or settings."""

    class EventStart(KeepTogether):
        """Keep the event label and clock with its first two detail lines."""

        def wrap(self, width, height):
            result = super().wrap(width, height)
            if self._content and isinstance(self._content[-1], Paragraph):
                body = self._content[-1]
                self._H -= max(0, body.wrap(width, height)[1] - 2 * body.style.leading)
            return result

    font_root = Path(__file__).resolve().parents[3] / "modules/ui/fonts"
    for name, file in (
        ("WorkLogSans", "DejaVuSans.ttf"),
        ("WorkLogSans-Bold", "DejaVuSans-Bold.ttf"),
    ):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_root / file)))
    ink, muted = colors.black, colors.black
    styles = {
        "title": ParagraphStyle(
            "WorkLogTitle",
            fontName="WorkLogSans-Bold",
            fontSize=20,
            leading=25,
            spaceAfter=12,
            textColor=ink,
        ),
        "heading": ParagraphStyle(
            "WorkLogHeading",
            fontName="WorkLogSans-Bold",
            fontSize=10,
            leading=14,
            spaceBefore=14,
            spaceAfter=4,
            keepWithNext=True,
            textColor=ink,
        ),
        "body": ParagraphStyle(
            "WorkLogBody",
            fontName="WorkLogSans",
            fontSize=9,
            leading=13,
            spaceAfter=5,
            splitLongWords=True,
            textColor=ink,
        ),
        "meta": ParagraphStyle(
            "WorkLogMeta",
            fontName="WorkLogSans",
            fontSize=8,
            leading=11.5,
            spaceAfter=5,
            splitLongWords=True,
            textColor=muted,
        ),
    }

    def paragraph(value, style="body"):
        # All values are literal source text. No links, markup, or image tags
        # from a source record are executable in this internal document.
        from modules.ui.components.unicode_fonts import markup

        return Paragraph(markup(_text(value), styles[style].fontName), styles[style])

    case_id = _text(data.get("case_id") or data.get("notification_id"))
    company = (
        data.get("draft", {}).get("company")
        or data.get("entity_name")
        or data.get("company")
        or data.get("domain")
        or "Business not recorded"
    )
    revision = data.get("report_revision", data.get("revision"))
    if revision is None:
        revision = data.get("certification", {}).get("revision")
    flow = [
        paragraph("Work log & certification chronology", "title"),
        paragraph(company),
        paragraph("Shadowserver Notification: " + (case_id or "Not recorded"), "meta"),
    ]
    metadata = []
    if data.get("domain"):
        metadata.append("Domain: " + _text(data["domain"]))
    if revision is not None:
        metadata.append("Report revision: " + _text(revision))
    if data.get("draft_revision") is not None:
        metadata.append("Draft revision: " + _text(data["draft_revision"]))
    if metadata:
        flow.append(paragraph(" | ".join(metadata), "meta"))
    flow += [
        Spacer(1, 8),
        paragraph("Internal work record", "heading"),
        paragraph(
            "Source retrieval, attribution decisions, section reviews, and final certification are recorded separately. "
            "Times are shown in UTC when a timezone was recorded. Undated or invalidly dated records appear at the end; "
            "missing times and authors are not inferred.",
            "meta",
        ),
    ]
    if not events:
        flow.append(paragraph("No activity records were available for this package."))
    for index, event in enumerate(events, 1):
        title = event.get("label") or _text(event.get("action")).replace("_", " ").capitalize()
        if event.get("revision") is not None:
            title += " | Revision " + _text(event["revision"])
        event_flow = [paragraph(f"{index:02d}  {title}", "heading")]
        actor = event.get("actor") or "Not recorded"
        event_flow.append(paragraph(_display_time(event) + " | Actor: " + actor, "meta"))
        if event.get("reason"):
            event_flow.append(paragraph("Reason / review note: " + _text(event["reason"])))
        if event.get("detail"):
            event_flow.append(paragraph(event["detail"]))
        context = event.get("context") or {}
        for key, label in (
            ("root_domains", "Domain groups"),
            ("ip", "IP"),
            ("source", "Source"),
            ("source_url", "Source record"),
            ("matched_field", "Matching field"),
            ("matched_value", "Matching value"),
            ("result_id", "Attribution result"),
            ("snapshot_id", "Source snapshot"),
            ("body_sha256", "Source SHA-256"),
            ("validation_id", "Section validation"),
            ("dependency_hash", "Section dependency SHA-256"),
            ("snapshot_hash", "Section snapshot SHA-256"),
            ("content_hash", "Section content SHA-256"),
        ):
            value = context.get(key)
            if value:
                event_flow.append(
                    paragraph(
                        label
                        + ": "
                        + (", ".join(map(str, value)) if isinstance(value, list) else _text(value)),
                        "meta",
                    )
                )
        flow.append(EventStart(event_flow[:3]))
        flow.extend(event_flow[3:])

    def decorate(canvas, doc):
        from modules.ui.components.print_policy import decorate_pdf

        decorate_pdf(
            canvas,
            doc,
            left_text="SHADOWSERVER COMPANION | INTERNAL WORK LOG",
            footer_text="Notification " + (case_id[:36] or "Not recorded"),
            font="WorkLogSans",
            priority=data.get("intake_score"),
        )

    target = Path(pdf_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(
        str(target),
        pagesize=(612, 792),
        leftMargin=50,
        rightMargin=50,
        topMargin=62,
        bottomMargin=64,
        title="Internal notification work log",
        author=_text(data.get("certification", {}).get("certified_by")),
    ).build(flow, onFirstPage=decorate, onLaterPages=decorate)
    return target
