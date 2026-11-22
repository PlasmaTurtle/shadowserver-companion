"""Read product statements from an explicitly acquired Red Hat CVE response."""

import copy
import json
import threading
from concurrent.futures import Future

import requests

from .intelligence import acquisition, redhat
from .repositories.sources import SourceRepository

_active_refreshes = {}
_refresh_lock = threading.Lock()


def read_redhat(store, cve_id, *, offset=0, limit=25):
    cve_id = redhat.identifier(cve_id)
    if not 0 <= offset <= 500000 or not 1 <= limit <= 100:
        raise ValueError("Vendor statement page is outside its allowed range")
    state = SourceRepository(store).risk_state("redhat:" + cve_id)
    return _view(store, cve_id, state, offset=offset, limit=limit)


def _view(store, cve_id, state, *, offset=0, limit=25):
    attempt = json.loads(state["risk-attempt"]["payload"]) if state["risk-attempt"] else None
    last_attempt = None
    if attempt:
        last_attempt = {
            name: attempt.get(name) for name in ("outcome", "attempted_at", "completed_at", "error")
        }
        last_attempt["http_status"] = attempt.get("response", {}).get("http_status")
        last_attempt["retry_after"] = attempt.get("response", {}).get("retry_after") or None
    result = {
        "cve_id": cve_id,
        "publisher": redhat.PUBLISHER,
        "source_url": redhat.source_url(cve_id),
        "public_url": redhat.PORTAL + cve_id,
        "status": "unavailable" if attempt else "not_retrieved",
        "retrieved_at": None,
        "revision_id": None,
        "sha256": None,
        "published_at": None,
        "stale": None,
        "last_attempt": last_attempt,
        "publisher_statement": None,
        "statements": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "error": None,
    }
    if state["risk-proof"] is None:
        return result
    try:
        source = json.loads(state["risk-proof"]["payload"])
        immutable = SourceRepository(store).payload("risk-version:" + source["revision_id"])
        if immutable.get("source") != source:
            raise ValueError("Saved source metadata differs from its captured revision")
        raw = acquisition.retained_risk_data(store, "redhat:" + cve_id, source)
        value = redhat.record(cve_id, raw)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        result.update(status="unavailable", error="Saved Red Hat response could not be verified")
        return result
    total, statements = redhat.product_page(value, offset, limit)
    result.update(
        status="available",
        retrieved_at=source["retrieved_at"],
        revision_id=source["revision_id"],
        sha256=source["sha256"],
        published_at=value.public_date,
        stale=bool(attempt and attempt["outcome"] != "success")
        or acquisition._age(source["retrieved_at"]) >= 86400,
        publisher_statement=value.statement
        if value.statement and value.statement.strip()
        else None,
        statements=statements,
        total=total,
    )
    return result


def refresh_redhat(store, cve_id):
    cve_id = redhat.identifier(cve_id)
    key = (str(store.db), cve_id)
    future = Future()
    with _refresh_lock:
        active = _active_refreshes.setdefault(key, future)
    if active is not future:
        return copy.deepcopy(active.result())
    try:
        result = _refresh(store, cve_id)
        future.set_result(copy.deepcopy(result))
        return result
    except BaseException as error:
        future.set_exception(error)
        raise
    finally:
        with _refresh_lock:
            del _active_refreshes[key]


def _refresh(store, cve_id):
    try:
        capture = acquisition.capture_json(
            store, "redhat:" + cve_id, redhat.source_url(cve_id), refresh=True
        )
    except (ValueError, requests.RequestException) as error:
        # A first failed fetch or timeout waiting on another request has no new proof.
        result = read_redhat(store, cve_id)
        if result["status"] == "not_retrieved":
            result["status"] = "unavailable"
        result["error"] = str(error)
        return result
    return _view(store, cve_id, capture.state)
