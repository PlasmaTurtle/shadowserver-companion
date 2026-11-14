"""Case-owned outreach drafts. Preparing/copying never sends or records delivery."""

from datetime import datetime
import hashlib
import json

from .contact_records import ContactConflict
from .primitives import now

FIELDS = ("subject", "message", "call_outline")
MAX_CONTEXT_BYTES = 256 * 1024
CONTEXT_LABELS = {
    "report": "Certified report",
    "contact": "Selected contact route",
    "recipient": "Contact plan",
    "research": "Contact research",
    "policy": "Outreach decision",
    "generated": "Sender, entity or verification details",
}


def _context(data, case):
    route = data.get("contact") or {}
    return {
        "report": data.get("report"),
        "contact": {
            key: route.get(key)
            for key in ("kind", "value", "usable", "unusable", "missing_from_latest")
        },
        "recipient": data.get("contact_plan")
        or {
            key: case.get(key, "")
            for key in ("contact_name", "contact_role", "contact_email", "contact_phone")
        },
        "research": {
            "source": data.get("source_explanation", ""),
            "warnings": data.get("warnings", []),
        },
        "policy": {
            key: data.get("outreach_policy", {}).get(key)
            for key in ("state", "reason", "review_on")
        },
        "generated": {key: data[key] for key in FIELDS},
    }


def _encoded(context):
    return json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def validate_saved_preparation(row):
    """Validate stored bytes without rejecting legitimately stale context."""
    if not isinstance(row["case_id"], str) or not row["case_id"]:
        raise ValueError("Outreach preparation has no case identity")
    if not isinstance(row["revision"], int) or row["revision"] < 1:
        raise ValueError("Outreach preparation revision is invalid")
    for key, limit in (
        ("subject", 1000),
        ("message", 20000),
        ("call_outline", 10000),
        ("updated_by", 300),
    ):
        if not isinstance(row[key], str) or len(row[key]) > limit:
            raise ValueError("Outreach preparation text is invalid")
    if (
        not isinstance(row["context_json"], str)
        or len(row["context_json"].encode()) > MAX_CONTEXT_BYTES
    ):
        raise ValueError("Outreach preparation context exceeds its limit")
    try:
        stamp = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        context = json.loads(row["context_json"])
    except (TypeError, ValueError, AttributeError, RecursionError) as error:
        raise ValueError("Outreach preparation metadata is invalid") from error
    if stamp.tzinfo is None or not isinstance(context, dict) or set(context) != set(CONTEXT_LABELS):
        raise ValueError("Outreach preparation context is invalid")
    if not isinstance(context.get("generated"), dict) or set(context["generated"]) != set(FIELDS):
        raise ValueError("Outreach preparation generated context is invalid")
    if any(not isinstance(context["generated"][key], str) for key in FIELDS):
        raise ValueError("Outreach preparation generated text is invalid")
    if any(
        not isinstance(context[key], dict) for key in ("contact", "recipient", "research", "policy")
    ):
        raise ValueError("Outreach preparation context shape is invalid")
    if context["report"] is not None and not isinstance(context["report"], dict):
        raise ValueError("Outreach preparation report context is invalid")
    if any(
        value is not None and not isinstance(value, (str, bool))
        for value in context["contact"].values()
    ) or any(not isinstance(value, str) for value in context["recipient"].values()):
        raise ValueError("Outreach preparation contact context is invalid")
    research = context["research"]
    if (
        not isinstance(research.get("source"), str)
        or not isinstance(research.get("warnings"), list)
        or any(not isinstance(value, str) for value in research["warnings"])
    ):
        raise ValueError("Outreach preparation research context is invalid")
    if any(
        value is not None and not isinstance(value, str) for value in context["policy"].values()
    ):
        raise ValueError("Outreach preparation policy context is invalid")
    if context["report"] is not None and (
        set(context["report"]) != {"id", "revision", "url"}
        or not isinstance(context["report"]["revision"], int)
        or context["report"]["revision"] < 1
        or any(not isinstance(context["report"][key], str) for key in ("id", "url"))
    ):
        raise ValueError("Outreach preparation report identity is invalid")
    if hashlib.sha256(_encoded(context).encode()).hexdigest() != row["context_hash"]:
        raise ValueError("Outreach preparation context failed its integrity check")
    return True


def preparation(store, records, case_id):
    """Return current context alongside saved text; never overwrite a saved draft."""
    with store.lock:
        data = records.handoff(case_id)
        case = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
        context = _context(data, case)
        context_hash = hashlib.sha256(_encoded(context).encode()).hexdigest()
        saved = store.one("SELECT * FROM outreach_preparations WHERE case_id=?", (case_id,))
        if saved:
            validate_saved_preparation(saved)
        previous = json.loads(saved["context_json"]) if saved else context
        changes = [
            label for key, label in CONTEXT_LABELS.items() if previous.get(key) != context[key]
        ]
        editable = case["stage"] != "closed"
        # Contact research can precede certification. The generated message and
        # handoff blockers distinguish that from offering a certified report.
        copy_blockers = []
        if not editable:
            copy_blockers.append("This case is closed. Start a new notification for new outreach.")
        if data.get("outreach_policy", {}).get("state", "active") != "active":
            copy_blockers.append("Review the outreach hold before copying a message.")
        if not (data.get("contact") or {}).get("usable"):
            copy_blockers.append("Choose a usable contact route before copying a message.")
        if data.get("scope_warning"):
            copy_blockers.append(data["scope_warning"]["message"])
        if changes:
            copy_blockers.append(
                "Review the changed context and save this preparation before copying."
            )
        return {
            **data,
            "context_hash": context_hash,
            "context_changes": changes,
            "preparation_stale": bool(changes),
            "preparation_editable": editable,
            "copy_allowed": not copy_blockers,
            "copy_blockers": copy_blockers,
            "generated": {key: data[key] for key in FIELDS},
            "preparation": {
                "revision": saved["revision"] if saved else 0,
                **{key: saved[key] if saved else data[key] for key in FIELDS},
                "context_hash": saved["context_hash"] if saved else context_hash,
                "updated_at": saved["updated_at"] if saved else None,
                "updated_by": saved["updated_by"] if saved else None,
            },
        }


def _check(current, expected_revision, expected_context):
    if current["preparation"]["revision"] != expected_revision:
        raise ContactConflict(
            "This outreach draft changed in another window. Reload the saved draft before saving again; your edits are retained."
        )
    if current["context_hash"] != expected_context:
        raise ContactConflict(
            "The report, contact or outreach context changed. Refresh context and review it before continuing; your edits are retained."
        )


def save_preparation(
    store,
    records,
    case_id,
    *,
    expected_revision,
    expected_context,
    reviewed_context=False,
    reset=False,
    **fields,
):
    # Reserve the writer before reading context, including across app processes.
    # Read projections use separate connections but see the committed state held
    # stable by this transaction until the new preparation is committed.
    with store.transaction() as db:
        current = preparation(store, records, case_id)
        _check(current, expected_revision, expected_context)
        if not current["preparation_editable"]:
            raise ContactConflict("Closed cases cannot change their outreach preparation.")
        if current["preparation_stale"] and not reviewed_context:
            raise ContactConflict(
                "Review the changed recipient, report and outreach context before saving."
            )
        values = current["generated"] if reset else fields
        for key, limit in (("subject", 1000), ("message", 20000), ("call_outline", 10000)):
            if not isinstance(values.get(key), str) or len(values[key]) > limit:
                raise ValueError("Outreach preparation text is missing or exceeds its limit")
        case = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
        context = _context(current, case)
        if len(_encoded(context).encode()) > MAX_CONTEXT_BYTES:
            raise ValueError("Outreach preparation context exceeds its limit")
        actor = store.settings().get("analyst_name", "").strip()
        db.execute(
            """INSERT INTO outreach_preparations
                   (case_id,revision,subject,message,call_outline,context_json,context_hash,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET
                   revision=excluded.revision,subject=excluded.subject,message=excluded.message,
                   call_outline=excluded.call_outline,context_json=excluded.context_json,
                   context_hash=excluded.context_hash,updated_at=excluded.updated_at,updated_by=excluded.updated_by""",
            (
                case_id,
                expected_revision + 1,
                *(values[key] for key in FIELDS),
                _encoded(context),
                current["context_hash"],
                now(),
                actor,
            ),
        )
        store.log(
            db,
            "outreach_preparation_reset" if reset else "outreach_preparation_saved",
            "Reset outreach preparation to current generated wording"
            if reset
            else "Saved outreach preparation",
            case["entity_id"],
            case_id,
            metadata={"preparation_revision": expected_revision + 1},
        )
    return preparation(store, records, case_id)


def copy_preparation(store, records, case_id, *, expected_revision, expected_context):
    """Recheck the route and current report immediately before a clipboard action."""
    with store.lock:
        current = preparation(store, records, case_id)
        _check(current, expected_revision, expected_context)
        if not expected_revision:
            raise ContactConflict("Save this outreach preparation before copying it.")
        if current["copy_blockers"]:
            raise ContactConflict(" ".join(current["copy_blockers"]))
        saved = current["preparation"]
        if not saved["subject"].strip() or not saved["message"].strip():
            raise ValueError("Enter a subject and message before copying.")
        return {
            "case_id": case_id,
            "revision": saved["revision"],
            "text": f"Subject: {saved['subject']}\n\n{saved['message']}",
            "call_outline": saved["call_outline"],
        }
