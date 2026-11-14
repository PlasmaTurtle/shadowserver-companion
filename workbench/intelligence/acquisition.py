"""Capture provider bytes, provenance, request budgets and immutable cache revisions.

Uses the shared bounded transport; never edits a notification case or report.
"""

import copy
import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import requests
import httpx
from attribution.bounded_http import capture_response as _response_get, CaptureCancelled
from attribution.http import retry_delay
from ..aegis.json import strict_json_loads
from ..aegis.text import parse_media_type, decode_bounded_text
from ..primitives import now, uid
from ..repositories.sources import SourceRepository
from .. import __version__
from ..cve_intelligence import ADAPTER_VERSION, extract_ssvc, reference_records, structured_impacts
from .adapters import summarize, summarize_nvd, _validate_risk_response

MAX_RESPONSE = 2 * 1024 * 1024
CAPTURE_BUDGET = 20.0
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId="
EPSS_URL = "https://api.first.org/data/v1/epss?cve="
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_rate_lock = threading.Lock()
_next_nvd = {}
_feed_locks = {}


class SourceCancelled(Exception):
    """Cancelled during acquisition; completed captured evidence is kept."""


def _cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise SourceCancelled("Source retrieval cancelled between requests")


class SourceDeferred(ValueError):
    """The source's retry window is still active; do not send another request."""


def _age(stamp):
    try:
        return (
            datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        ).total_seconds()
    except (TypeError, ValueError, AttributeError):
        return float("inf")


def _intact(store, record):
    path = record.get("record_path")
    if not path:
        return False
    try:
        return hashlib.sha256(store.path(path).read_bytes()).hexdigest() == (
            record.get("body_sha256") or record.get("sha256")
        )
    except (ValueError, OSError):
        return False


def _wait_for_nvd(store, cancel_event=None):
    # Reserve per-workspace slots before sleeping, then use the shared NVD
    # gate so catalog and report retrieval share the authenticated budget.
    from ..cve_catalog.credentials import NVDKeys

    authenticated = bool(NVDKeys(store.root).get())
    interval = 2.0 if authenticated else 6.1
    key = str(store.db)
    with _rate_lock:
        current = time.monotonic()
        ready = max(current, _next_nvd.get(key, current))
        if ready - current > 6.2:
            raise SourceDeferred("NVD request budget is occupied; refresh later")
        _next_nvd[key] = ready + interval
    delay = ready - current
    if delay:
        if cancel_event is not None:
            cancel_event.wait(delay)
            _cancelled(cancel_event)
        else:
            time.sleep(delay)
    # The background catalog delta and per-record fallback share the same
    # in-process public API allowance; local catalog reads never enter it.
    from ..cve_catalog import pace_nvd
    from ..cve_catalog.transport import CatalogCancelled

    try:
        if authenticated:
            pace_nvd(cancel_event, authenticated=True)
        else:
            pace_nvd(cancel_event)
    except CatalogCancelled as error:
        raise SourceCancelled(str(error)) from error


def _validate_source_url(url, publisher):
    # Constructed identifiers only. Public reference URLs are never fetched here.
    prefixes = {
        "NVD": NVD_URL,
        "CVE Program": "https://cveawg.mitre.org/api/cve/",
        "FIRST EPSS": EPSS_URL,
    }
    if publisher == "CISA KEV" and url == KEV_URL:
        return
    prefix = prefixes.get(publisher)
    if prefix and isinstance(url, str) and url.startswith(prefix):
        identifier = url[len(prefix) :]
        if re.fullmatch(r"CVE-\d{4}-\d{4,}", identifier):
            return
    raise ValueError("Source destination is outside the approved provider endpoints")


def catalog_record(store, cve_id):
    """Read the reference sidecar without creating one for an unused provider."""
    if not (Path(str(store.root) + "-reference") / "nvd").is_dir():
        return None
    try:
        from ..cve_catalog import Catalog

        value = Catalog(store.root).get(cve_id)
        if (
            isinstance(value, dict)
            and isinstance(value.get("cve"), dict)
            and isinstance(value.get("source"), dict)
        ):
            return value
        return None
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        # An unavailable reference cache does not remove the existing API fallback.
        return None


def _capture_catalog(store, cve_id, public_url):
    record = catalog_record(store, cve_id)
    if not record:
        return None
    try:
        raw = {"vulnerabilities": [{"cve": record["cve"]}]}
        summarize_nvd(cve_id, raw)
        provenance = record["source"]
        retrieved_at = provenance["retrieved_at"]
        url = provenance["url"]
        if not retrieved_at or not url:
            return None
        body = json.dumps(raw, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    stamp, revision = now(), uid()
    relative = f"evidence/cve/{cve_id}-{revision}.json"
    path = store.path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    source = {
        "publisher": "NVD",
        "title": f"NVD {cve_id} — local catalog extract",
        "url": url,
        "public_url": public_url,
        "retrieved_at": retrieved_at,
        "extracted_at": stamp,
        "sha256": hashlib.sha256(body).hexdigest(),
        "record_path": relative,
        "revision_id": revision,
        "http_status": None,
        "retry_after": "",
        "adapter_version": ADAPTER_VERSION,
        "transport": "local_catalog",
        "network_request": False,
        "acquisition_kind": "catalog_extract",
        "record_format": "NVD record wrapped locally for the existing adapter",
        "catalog_source": copy.deepcopy(provenance),
        "catalog_record_sha256": provenance.get("record_sha256"),
        "catalog_last_modified": record.get("last_modified"),
        "catalog_checked_at": record.get("catalog_checked_at"),
        "catalog_stale": record.get("catalog_stale", True),
    }
    return body, source


def risk_fingerprint(store, key):
    if not (Path(str(store.root) + "-reference") / "nvd" / "risk.sqlite3").is_file():
        return None
    try:
        from ..cve_catalog.risk import RiskStore

        return RiskStore(store.root).fingerprint(key)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return None


def risk_current_state(store, key):
    if not (Path(str(store.root) + "-reference") / "nvd" / "risk.sqlite3").is_file():
        return None
    provider = "epss" if key.startswith("epss:") else "kev" if key == "kev" else None
    if provider is None:
        return None
    try:
        from ..cve_catalog.risk import RiskStore

        return RiskStore(store.root).status()[provider]
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return None


def _capture_local_risk(store, key, public_url):
    if not risk_fingerprint(store, key):
        return None
    try:
        from ..cve_catalog.risk import RiskStore

        extracted = RiskStore(store.root).extract(key)
        if not extracted:
            return None
        raw, origin = extracted["data"], extracted["source"]
        _validate_risk_response(key, raw)
        if not origin.get("url") or not origin.get("retrieved_at"):
            return None
        body = json.dumps(raw, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return None
    revision, extracted_at = uid(), now()
    relative = f"evidence/risk/{revision}.json"
    path = store.path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body, {
        "publisher": origin["publisher"],
        "title": origin["publisher"] + " — local catalog extract",
        "url": origin["url"],
        "public_url": public_url,
        "retrieved_at": origin["retrieved_at"],
        "extracted_at": extracted_at,
        "sha256": hashlib.sha256(body).hexdigest(),
        "record_path": relative,
        "revision_id": revision,
        "http_status": None,
        "retry_after": "",
        "adapter_version": ADAPTER_VERSION,
        "transport": "local_catalog",
        "network_request": False,
        "acquisition_kind": "catalog_extract",
        "catalog_source": copy.deepcopy(origin),
        "catalog_feed_sha256": origin["sha256"],
        "catalog_record_sha256": extracted["record_sha256"],
        "catalog_stale": extracted["stale"],
        "score_date": origin.get("score_date"),
        "model_version": origin.get("model_version"),
        "record_format": "Complete KEV catalog"
        if key == "kev"
        else "EPSS score wrapped locally for the existing adapter",
    }


def validate_capture_body(body, publisher, *, cve_id="", url=""):
    """Validate a provider record before retention or reuse in a new package.

    No content is made trustworthy by its extension or a matching digest. The
    complete response must be UTF-8 JSON with the requested provider's schema.
    This deliberately preserves valid JSON extension fields and published text.
    """
    if not isinstance(body, (bytes, bytearray)) or not 0 < len(body) <= 8 * 1024 * 1024:
        raise ValueError("Source response has an invalid size or byte representation")
    try:
        # JSON's network representation is UTF-8. Do not let the decoder infer
        # UTF-16/32 or accept HTML stored under a JSON filename.
        raw = strict_json_loads(body, max_bytes=8 * 1024 * 1024, require_object=True)
        identifier = cve_id or (
            url.rsplit("=", 1)[-1] if publisher == "FIRST EPSS" else url.rsplit("/", 1)[-1]
        )
        if publisher == "NVD":
            if not re.fullmatch(r"CVE-\d{4}-\d{4,}", identifier):
                raise ValueError("Source CVE identifier is missing or invalid")
            summarize_nvd(identifier, raw)
        elif publisher == "CVE Program":
            if not re.fullmatch(r"CVE-\d{4}-\d{4,}", identifier):
                raise ValueError("Source CVE identifier is missing or invalid")
            summarize(identifier, raw)
        elif publisher == "FIRST EPSS":
            if not re.fullmatch(r"CVE-\d{4}-\d{4,}", identifier):
                raise ValueError("Source CVE identifier is missing or invalid")
            _validate_risk_response("epss:" + identifier, raw)
        elif publisher == "CISA KEV":
            _validate_risk_response("kev", raw)
        else:
            raise ValueError("Source publisher is not supported for retained provider records")
    except UnicodeError as error:
        raise ValueError("Source response is not UTF-8 JSON") from error
    except (TypeError, KeyError, AttributeError, RecursionError) as error:
        raise ValueError("Source response does not match the provider schema") from error
    return raw


def retained_provider_data(store, source, publisher, *, cve_id=""):
    """Read provider data from the same verified bytes named by its proof."""
    expected = source.get("body_sha256") or source.get("sha256")
    if not source.get("record_path") or not expected:
        raise ValueError("Saved provider response has no verifiable capture")
    with store.path(source["record_path"]).open("rb") as stream:
        body = stream.read(8 * 1024 * 1024 + 1)
    if hashlib.sha256(body).hexdigest() != expected:
        raise ValueError("Saved provider response failed its integrity check")
    return validate_capture_body(body, publisher, cve_id=cve_id)


def retained_risk_data(store, key, source):
    if key.startswith("epss:"):
        publisher, identifier = "FIRST EPSS", key.partition(":")[2]
    elif key.startswith("program:"):
        publisher, identifier = "CVE Program", key.partition(":")[2]
    elif key == "kev":
        publisher, identifier = "CISA KEV", ""
    else:
        raise ValueError("Unknown captured provider key")
    return retained_provider_data(store, source, publisher, cve_id=identifier)


def validate_reference_projection(store, cve_id, record):
    """A reusable normalized summary must still agree with its captured source."""
    publisher = record.get("source")
    if record.get("id") != cve_id or publisher not in {"NVD", "CVE Program"}:
        raise ValueError("Saved CVE summary has an invalid provider or identifier")
    raw = retained_provider_data(store, record, publisher, cve_id=cve_id)
    source = next(
        (
            item
            for item in record.get("sources", [])
            if item.get("record_path") == record["record_path"]
        ),
        {},
    )
    expected = record.get("body_sha256") or record.get("sha256")
    source_digest = source.get("body_sha256") or source.get("sha256")
    if source_digest and source_digest != expected:
        raise ValueError("Saved CVE summary differs from its source proof")
    if source.get("revision_id") and source["revision_id"] != record.get("revision_id"):
        raise ValueError("Saved CVE summary differs from its source revision")
    normalize = summarize_nvd if publisher == "NVD" else summarize
    claims = normalize(cve_id, raw)
    claims.update(
        record=raw,
        cvss_version=claims.get("cvss_version"),
        cvss_source=claims.get("cvss_source"),
        vector=claims.get("vector"),
        ssvc_assessments=extract_ssvc(cve_id, raw, source),
        reference_records=reference_records(raw, source),
        impacts=structured_impacts(raw, source),
    )
    modern = source.get("adapter_version") == ADAPTER_VERSION
    # Older summaries may omit newer derived fields and use earlier provenance
    # labels. Present factual fields must agree; immutable case snapshots are
    # never passed through this mutable-reference validator.
    legacy_optional = {
        "description_source",
        "description_contributor",
        "date_published",
        "date_updated",
        "ssvc_assessments",
        "reference_records",
        "impacts",
    }
    for key, value in claims.items():
        if not modern and key in {"epss", "epss_percentile", "kev"}:
            continue
        if not modern and (key not in record or key in legacy_optional):
            continue
        if json.dumps(record.get(key), sort_keys=True, allow_nan=False) != json.dumps(
            value, sort_keys=True, allow_nan=False
        ):
            raise ValueError("Saved CVE summary differs from its retained provider response")


def _response_metadata(headers):
    """Only bounded, typed protocol metadata belongs in a rejected capture."""
    normalized = {str(name).lower(): str(value) for name, value in headers.items()}
    try:
        media, _ = parse_media_type(normalized.get("content-type", ""))
    except ValueError:
        media = ""
    retry_after = normalized.get("retry-after", "").strip()
    if len(retry_after) > 128 or any(ord(c) < 32 or ord(c) > 126 for c in retry_after):
        retry_after = ""
    if retry_after and not re.fullmatch(r"[0-9]{1,10}", retry_after):
        try:
            retry_after = parsedate_to_datetime(retry_after).isoformat()
        except (TypeError, ValueError, OverflowError):
            retry_after = ""
        else:
            # retry_delay expects an HTTP date, so retain only the canonical
            # successfully parsed header rather than untrusted free-form text.
            from email.utils import format_datetime

            retry_after = format_datetime(datetime.fromisoformat(retry_after))
    return media, retry_after


def _capture(store, url, publisher, public_url, cve_id="", limit=MAX_RESPONSE, cancel_event=None):
    _cancelled(cancel_event)
    _validate_source_url(url, publisher)
    if publisher == "NVD" and cve_id:
        local = _capture_catalog(store, cve_id, public_url)
        if local is not None:
            return local
    backoff_key = "source-backoff:" + publisher
    backoff = SourceRepository(store).get(backoff_key)
    if backoff:
        until = json.loads(backoff["payload"]).get("retry_at")
        if until and _age(until) < 0:
            raise SourceDeferred(publisher + ": retry window ends " + until)
    if publisher == "NVD":
        _wait_for_nvd(store, cancel_event)
    from ..cve_catalog.credentials import NVDKeys

    key = NVDKeys(store.root).get() if publisher == "NVD" else ""
    started = time.monotonic()
    try:
        response = _response_get(
            url,
            timeout=httpx.Timeout(10, connect=5),
            budget=CAPTURE_BUDGET,
            limit=limit,
            cancel_event=cancel_event,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "ShadowserverCompanion/" + __version__,
                **({"apiKey": key} if key else {}),
            },
        )
    except CaptureCancelled as error:
        raise SourceCancelled(str(error)) from error
    except httpx.HTTPError as error:
        # Never publish proxy credentials or unrestricted transport exception URLs.
        raise ValueError(f"Source request failed: {type(error).__name__}") from error
    with response:
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > limit or time.monotonic() - started > CAPTURE_BUDGET:
                raise ValueError("Source response exceeded its size or time budget")
        stamp, revision = now(), uid()
        relative = (
            f"evidence/cve/{cve_id}-{revision}.json" if cve_id else f"evidence/risk/{revision}.json"
        )
        content_type, retry_after = _response_metadata(response.headers)
        source = {
            "publisher": publisher,
            "title": f"{publisher} {cve_id}".strip(),
            "url": url,
            "public_url": public_url,
            "retrieved_at": stamp,
            "sha256": hashlib.sha256(body).hexdigest(),
            "record_path": "",
            "revision_id": revision,
            "http_status": response.status_code,
            "retry_after": retry_after,
            "content_type": content_type,
            "captured_bytes": len(body),
            "response_retention": "metadata-only",
            "adapter_version": ADAPTER_VERSION,
        }
        if response.status_code == 429 or (response.status_code == 503 and source["retry_after"]):
            retry_at = datetime.now(timezone.utc) + timedelta(
                seconds=max(1, retry_delay(source["retry_after"], default=60.0))
            )
            _write_cache(store, backoff_key, {"retry_at": retry_at.isoformat()})
        try:
            if response.status_code != 200:
                raise ValueError("Unsuccessful HTTP response body was not retained")
            if content_type.split(";", 1)[0].strip().lower() not in {
                "application/json",
                "application/cve+json",
                "application/problem+json",
            }:
                raise ValueError("Source response does not declare a supported JSON media type")
            declared_type = next(
                (str(v) for k, v in response.headers.items() if str(k).lower() == "content-type"),
                "",
            )
            decode_bounded_text(
                bytes(body),
                declared_type,
                allowed_media={
                    "application/json",
                    "application/cve+json",
                    "application/problem+json",
                },
                allowed_charsets={"utf-8", "utf8", "us-ascii", "ascii"},
                max_bytes=limit,
            )
            validate_capture_body(body, publisher, cve_id=cve_id, url=url)
        except ValueError as error:
            source["validation_error"] = str(error)
            # Retain source hash and retrieval outcome only. Rejected bytes must
            # never reach an evidence file, cache, report snapshot or package.
            return b"", source
        path = store.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        source.update(record_path=relative, response_retention="validated-provider-json")
        return bytes(body), source


def _write_cache(store, key, value):
    with store.transaction() as db:
        SourceRepository(store).put(db, key, value)


def _outcome(source=None, error=None):
    if isinstance(error, SourceDeferred):
        return "rate_limited"
    if source is None:
        return "unavailable"
    if source.get("transport") == "local_catalog":
        return "invalid_response" if error else "success"
    status = source.get("http_status")
    if status == 429:
        return "rate_limited"
    if status == 404:
        return "not_found"
    if status != 200:
        return "unavailable"
    return "invalid_response" if error else "success"


def _record_attempt(
    store, publisher, url, attempted_at, source=None, error=None, outcome=None, prior=None
):
    """A request attempt and a captured response are deliberately distinct."""
    item = {
        "id": uid(),
        "publisher": publisher,
        "url": url,
        "attempted_at": attempted_at,
        "completed_at": now(),
        "outcome": outcome or _outcome(source, error),
        "source_snapshot_id": source.get("revision_id")
        if source and source.get("record_path")
        else None,
        "last_usable_snapshot_id": prior.get("revision_id") if prior else None,
        "error": str(error) if error else None,
    }
    if source:
        item["response"] = copy.deepcopy(source)
        if source.get("transport") == "local_catalog":
            item.update(url=source["url"], transport="local_catalog", network_request=False)
    with store.transaction() as db:
        SourceRepository(store).record_attempt(db, item)
    return item


@dataclass(frozen=True)
class CapturedSource:
    """One acquisition's data and provenance, retained across later refreshes."""

    data: dict
    retrieved_at: str
    source: dict
    state: dict


def cached_json(store, key, url, *, refresh=False, cancel_event=None):
    """Compatibility API returning the original (JSON, retrieval timestamp) pair."""
    capture = capture_json(store, key, url, refresh=refresh, cancel_event=cancel_event)
    return capture.data, capture.retrieved_at


def capture_json(store, key, url, *, refresh=False, cancel_event=None):
    # A store-wide lock coalesces concurrent KEV requests. Forced refreshes are
    # also coalesced for a minute, so a batch of CVEs refreshes one shared feed.
    lock_key = (str(store.db), key)
    with _rate_lock:
        lock = _feed_locks.setdefault(lock_key, threading.Lock())
    deadline = time.monotonic() + 20.0
    while not lock.acquire(timeout=0.05):
        _cancelled(cancel_event)
        if time.monotonic() >= deadline:
            raise SourceDeferred("Source response is already being retrieved; retry later")
    try:
        _cancelled(cancel_event)
        raw, stamp = _cached_json(store, key, url, refresh=refresh, cancel_event=cancel_event)
        # Capture the proof before releasing this provider/key lock. Enrichment
        # must not look up a newer "current proof" after using these bytes.
        state = SourceRepository(store).risk_state(key)
        source = json.loads(state["risk-proof"]["payload"]) if state["risk-proof"] else {}
        return CapturedSource(raw, stamp, source, state)
    finally:
        lock.release()


def _cached_json(store, key, url, *, refresh=False, cancel_event=None):
    repository = SourceRepository(store)
    state = repository.risk_state(key)
    cached, proof_row = state["risk"], state["risk-proof"]
    proof = json.loads(proof_row["payload"]) if proof_row else None
    intact = bool(cached and proof)
    cached_raw = None
    if intact:
        try:
            # The mutable lookup projection cannot supply facts under another
            # response's proof, even when its JSON still has a valid shape.
            cached_raw = retained_risk_data(store, key, proof)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # A pre-0.7 capture may lack completeness evidence. Its raw bytes
            # remain historical evidence, but it cannot answer a new lookup.
            intact = False
    ttl = 86400 if not refresh else (60 if key == "kev" else 0)
    local_hash = risk_fingerprint(store, key)
    local_changed = bool(local_hash) and local_hash != (proof or {}).get("catalog_feed_sha256")
    if (
        intact
        and not local_changed
        and (local_hash and not refresh or _age(proof["retrieved_at"]) < ttl)
    ):
        return cached_raw, proof["retrieved_at"]
    if key.startswith("epss:"):
        publisher, public_url = "FIRST EPSS", "https://www.first.org/epss/"
    elif key.startswith("program:"):
        publisher, public_url = (
            "CVE Program",
            "https://www.cve.org/CVERecord?id=" + key.split(":", 1)[1],
        )
    else:
        publisher, public_url = (
            "CISA KEV",
            "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
        )
    attempted_at, source = now(), None
    try:
        local = _capture_local_risk(store, key, public_url)
        if local is not None:
            body, source = local
        else:
            body, source = _capture(
                store,
                url,
                publisher,
                public_url,
                limit=8 * 1024 * 1024 if key == "kev" else MAX_RESPONSE,
                cancel_event=cancel_event,
            )
        if source["http_status"] != 200 and source.get("transport") != "local_catalog":
            raise ValueError(
                f"HTTP {source['http_status']}; retry after {source['retry_after'] or 'the service recovers'}"
            )
        if source.get("validation_error"):
            raise ValueError(source["validation_error"])
        raw = strict_json_loads(body, max_bytes=8 * 1024 * 1024, require_object=True)
        _validate_risk_response(key, raw)
        if key.startswith("program:"):
            summary = summarize(key.split(":", 1)[1], raw)
            source.update(
                date_published=summary.get("date_published"),
                date_updated=summary.get("date_updated"),
            )
        elif key == "kev":
            source["catalog_version"] = raw["catalogVersion"]
            source["date_released"] = raw["dateReleased"]
            source["catalog_count"] = raw["count"]
            source["catalog_complete"] = True
        attempt = _record_attempt(store, publisher, url, attempted_at, source, prior=proof)
        with store.transaction() as db:
            repository.save_risk(db, key, raw, source, attempt)
        return raw, source["retrieved_at"]
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
        attempt = _record_attempt(
            store, publisher, url, attempted_at, source, error, prior=proof if intact else None
        )
        _write_cache(store, "risk-attempt:" + key, attempt)
        _write_cache(
            store,
            "risk-refresh:" + key,
            {
                "status": attempt["outcome"],
                "error": str(error),
                "checked_at": attempt["completed_at"],
                "attempt": attempt,
            },
        )
        if not intact:
            raise
        return cached_raw, proof["retrieved_at"]


def _proof(store, key):
    return SourceRepository(store).payload("risk-proof:" + key)


def _append_acquisition(store, key, result, state=None):
    if state is None:
        state = SourceRepository(store).risk_state(key)
    row = state["risk-attempt"]
    if row:
        item = json.loads(row["payload"])
        if item["id"] not in {v["id"] for v in result.setdefault("acquisition", [])}:
            result["acquisition"].append(item)
    failed = state["risk-refresh"]
    if failed:
        item = json.loads(failed["payload"])
        result.setdefault("provider_outcomes", {})[key] = item
        if state["risk-proof"]:
            result.setdefault("stale_sources", []).append(key)
    else:
        result.setdefault("provider_outcomes", {})[key] = {"status": "success"}
