"""Build and publish the internal closing report, then advance its case."""

import hashlib
import json
import shutil
from copy import deepcopy
from ..cases import Cases
from ..primitives import now, uid
from ..presentation import document_policy
from ..report_operations import publication
from ..report_execution import prepare_closing


def closing_data(store, case_id, values):
    lead = Cases(store).view(case_id)
    case = lead["case"]
    if case["stage"] == "closed":
        raise ValueError("This case already has a finalized closing report")
    if case["version"] != values["expected_version"]:
        raise ValueError("This case changed. Reload before closing.")
    if values["disposition"] == "notified" and not case["delivered_at"]:
        raise ValueError("Record successful delivery before closing as notified")
    if case["delivered_at"] and values["disposition"] != "notified":
        raise ValueError("This case records successful delivery; use the notified disposition")
    data = {
        "schema_version": 1,
        "case_id": case_id,
        "entity_id": lead["id"],
        "business": lead["company"] or lead["domain"],
        "title": case["title"],
        "opened_at": case["created_at"],
        "delivered_at": case["delivered_at"],
        "created_at": now(),
        "closed_by": values["closed_by"],
        "disposition": values["disposition"],
        "conclusion": values["conclusion"],
        "profile": store.settings(),
        "document_policy": document_policy(store.settings()),
        "reports": lead["reports"],
        "attempts": lead["attempts"],
        "events": lead["history"],
    }
    if isinstance(lead.get("intake_score"), dict) and lead["intake_score"]:
        data["intake_score"] = deepcopy(lead["intake_score"])
    return data


def close_case(store, case_id, values, *, render_closing):
    if values["reviewed"] is not True:
        raise ValueError("Review the closing report before finalizing it")
    with store.lock:
        data = closing_data(store, case_id, values)
        closure_id = uid()
        relative = f"closures/{case_id}/{closure_id}"
        target = store.path(relative)
        temporary = target.parent / (".build-" + closure_id)
        temporary.mkdir(parents=True)
        try:
            prepare_closing(data, temporary, fallback=render_closing)
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            (temporary / "snapshot.json").write_bytes(raw)
            hashes = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in temporary.iterdir()
            }
            (temporary / "manifest.json").write_text(
                json.dumps(
                    {
                        "case_id": case_id,
                        "closure_id": closure_id,
                        "expected_version": values["expected_version"],
                        "files": hashes,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            with publication():
                temporary.rename(target)
                with store.transaction() as db:
                    case = Cases(store).require(db, case_id, values["expected_version"])
                    if case["stage"] == "closed":
                        raise ValueError("Case already closed")
                    db.execute(
                        "INSERT INTO case_closures VALUES(?,?,?,?,?,?,?,?)",
                        (
                            closure_id,
                            case_id,
                            data["created_at"],
                            data["closed_by"],
                            data["disposition"],
                            data["conclusion"],
                            relative,
                            hashlib.sha256(raw).hexdigest(),
                        ),
                    )
                    from ..artifact_registry import register_artifact

                    register_artifact(db, store.root, "closure", closure_id)
                    db.execute(
                        "UPDATE cases SET stage='closed',closed_at=?,disposition=?,next_action='',follow_up_date=NULL,version=version+1,updated_at=? WHERE id=?",
                        (data["created_at"], data["disposition"], now(), case_id),
                    )
                    store.log(
                        db,
                        "case_closed",
                        "Finalized internal closing report: " + data["disposition"],
                        case["entity_id"],
                        case_id,
                    )
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            shutil.rmtree(target, ignore_errors=True)
            raise
        return store.one("SELECT * FROM case_closures WHERE id=?", (closure_id,))
