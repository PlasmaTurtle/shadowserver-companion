"""Verify and enrich source records; fetching never adopts a revision into casework."""

from __future__ import annotations
import copy
import json
import re
import requests
from attribution.models import parse_json
from ..intelligence_models import CVERecord
from ..primitives import now
from ..repositories.sources import SourceRepository
from ..cve_intelligence import (
    validate_kev_catalog,
    extract_ssvc,
    ransomware,
    reference_records,
    structured_impacts,
)
from .adapters import _number, _empty, summarize, summarize_nvd
from .selection import finish_intelligence
from . import acquisition
from .acquisition import (
    SourceDeferred,
    SourceCancelled as SourceCancelled,
    NVD_URL,
    EPSS_URL,
    KEV_URL,
    cached_json as cached_json,
    capture_json,
)


def verify(store, cve_id, *, refresh=False, cancel_event=None, local_only=False) -> CVERecord:
    if local_only:
        from .local import local_record

        return local_record(store, cve_id, cancel_event=cancel_event)
    cve_id = cve_id.upper()
    if not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve_id):
        raise ValueError("Invalid CVE identifier")
    repository = SourceRepository(store)
    cached = repository.get("cve-reference:" + cve_id)
    try:
        prior = json.loads(cached["payload"]) if cached else None
        if prior and acquisition._intact(store, prior):
            acquisition.validate_reference_projection(store, cve_id, prior)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # A divergent mutable summary is a cache miss, never a last-good
        # fallback. Reacquisition creates a new revision without rewriting it.
        prior = None
    if prior and not refresh and acquisition._intact(store, prior):
        local = acquisition.catalog_record(store, cve_id)
        prior_source = next(
            (
                source
                for source in prior.get("sources", [])
                if source.get("transport") == "local_catalog"
            ),
            {},
        )
        local_changed = bool(local) and (
            not prior_source
            or local["source"].get("record_sha256") != prior_source.get("catalog_record_sha256")
        )
        ttl = (
            86400
            if prior.get("verification_status") in ("published", "rejected", "reserved")
            else 60
        )
        if not local_changed and acquisition._age(cached["retrieved_at"]) < ttl:
            result = {**prior, "from_cache": True}
            if prior_source:
                result.update(
                    from_catalog=True,
                    catalog_checked_at=local.get("catalog_checked_at") if local else None,
                    stale=local.get("catalog_stale", True) if local else True,
                )
            return result
    result = {
        **_empty(),
        "id": cve_id,
        "sources": [],
        "attempts": [],
        "acquisition": [],
        "errors": [],
        "checked_at": now(),
        "retrieved_at": None,
        "from_cache": False,
        "applicability": "Reported by source; recipient IT determines software applicability",
        "public_url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
    }
    errors = []
    providers = [
        ("NVD", NVD_URL + cve_id, f"https://nvd.nist.gov/vuln/detail/{cve_id}", summarize_nvd),
        (
            "CVE Program",
            f"https://cveawg.mitre.org/api/cve/{cve_id}",
            f"https://www.cve.org/CVERecord?id={cve_id}",
            summarize,
        ),
    ]
    for publisher, url, public_url, normalize in providers:
        acquisition._cancelled(cancel_event)
        attempted_at, source = now(), None
        try:
            body, source = acquisition._capture(
                store, url, publisher, public_url, cve_id, cancel_event=cancel_event
            )
            result["attempts"].append(source)
            result.update(
                retrieved_at=source["retrieved_at"],
                record_path=source["record_path"],
                body_sha256=source["sha256"],
                http_status=source["http_status"],
                revision_id=source["revision_id"],
                source=publisher,
                public_url=public_url,
            )
            result["sources"] = [source]
            status = source["http_status"]
            if source.get("transport") == "local_catalog":
                # Successful local extraction has no live HTTP response/status.
                status = 200
                result.update(
                    from_catalog=True,
                    catalog_checked_at=source.get("catalog_checked_at"),
                    stale=source.get("catalog_stale", True),
                )
            if status == 429:
                result.update(verification_status="deferred", retry_after=source["retry_after"])
                errors.append(
                    publisher
                    + ": rate limited; retry after "
                    + (source["retry_after"] or "the service budget resets")
                )
                result["acquisition"].append(
                    acquisition._record_attempt(
                        store,
                        publisher,
                        url,
                        attempted_at,
                        source,
                        outcome="rate_limited",
                        prior=prior,
                    )
                )
                continue
            if status == 404:
                result.update(state="NOT_FOUND", verification_status="not_found")
                errors.append(
                    publisher
                    + ": no public record returned; this does not establish an invalid identifier"
                )
                result["acquisition"].append(
                    acquisition._record_attempt(
                        store,
                        publisher,
                        url,
                        attempted_at,
                        source,
                        outcome="not_found",
                        prior=prior,
                    )
                )
                continue
            if status != 200:
                errors.append(f"{publisher}: HTTP {status}; refresh later")
                result["acquisition"].append(
                    acquisition._record_attempt(
                        store, publisher, url, attempted_at, source, prior=prior
                    )
                )
                continue
            if source.get("validation_error"):
                raise ValueError(source["validation_error"])
            raw = parse_json(body)
            summary = normalize(cve_id, raw)
            result.update(summary)
            if summary["verification_status"] == "not_found":
                errors.append(publisher + ": no public record returned")
                result["acquisition"].append(
                    acquisition._record_attempt(
                        store,
                        publisher,
                        url,
                        attempted_at,
                        source,
                        outcome="not_found",
                        prior=prior,
                    )
                )
                continue
            result["record"] = raw
            source.update(
                date_published=summary.get("date_published", ""),
                date_updated=summary.get("date_updated", ""),
            )
            result.update(
                ssvc_assessments=extract_ssvc(cve_id, raw, source),
                reference_records=reference_records(raw, source),
                impacts=structured_impacts(raw, source),
            )
            result["acquisition"].append(
                acquisition._record_attempt(
                    store, publisher, url, attempted_at, source, prior=prior
                )
            )
            if publisher != "NVD":
                result["fallback"] = True
                result["fallback_reason"] = "; ".join(errors)
            if result["verification_status"] != "published":
                errors.append(publisher + ": record is " + result["state"])
            break
        except SourceDeferred as error:
            result["verification_status"] = "deferred"
            errors.append(str(error))
            result["acquisition"].append(
                acquisition._record_attempt(
                    store, publisher, url, attempted_at, source, error, prior=prior
                )
            )
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ) as error:
            errors.append(publisher + ": " + str(error))
            result["acquisition"].append(
                acquisition._record_attempt(
                    store, publisher, url, attempted_at, source, error, prior=prior
                )
            )
    result["errors"] = ["; ".join(errors)] if errors else []
    # Failed refresh cannot destroy a last usable source revision or change its
    # retrieval date. Rejected/reserved responses, however, are authoritative.
    if (
        result["verification_status"] not in ("published", "rejected", "reserved")
        and prior
        and prior.get("verification_status") == "published"
        and acquisition._intact(store, prior)
    ):
        result = {
            **prior,
            "from_cache": True,
            "stale": True,
            "checked_at": result["checked_at"],
            "refresh_status": result["verification_status"],
            "refresh_errors": result["errors"],
            "refresh_attempts": result["attempts"],
            "refresh_acquisition": result["acquisition"],
        }
        acquisition._write_cache(store, "cve-refresh:" + cve_id, result)
        return result
    with store.transaction() as db:
        repository.save_reference(db, cve_id, result)
    return result


def _supplement(store, result, *, refresh=False, cancel_event=None):
    cve_id = result["id"]
    # A fallback already captured the full Program record; no duplicate request.
    if result.get("source") == "CVE Program" and result.get("record"):
        return
    if result.get("from_catalog") and not refresh:
        # The daily NVD record already retains its source assessments and affected
        # product data. A normal local retrieval does not initiate another request
        # for every CVE; explicit refresh may request the Program supplement.
        result["supplementary_status"] = "local_catalog"
        return
    key = "program:" + cve_id
    capture = None
    try:
        capture = capture_json(
            store,
            key,
            "https://cveawg.mitre.org/api/cve/" + cve_id,
            refresh=refresh,
            cancel_event=cancel_event,
        )
        raw, source = capture.data, capture.source
        summary = summarize(cve_id, raw)
        result.setdefault("supplementary_records", []).append({"source": source, "record": raw})
        if source:
            result["sources"].append(source)
        # Supplementary published data cannot promote an authoritative rejected
        # or reserved record. A newly observed Program rejection is retained as
        # a state conflict and blocks a normal published notification.
        if summary["state"] in ("REJECTED", "RESERVED") and result.get("state") == "PUBLISHED":
            result["state_conflict"] = {
                "primary_state": result["state"],
                "supplementary_state": summary["state"],
                "source_revision_id": source.get("revision_id"),
            }
            result.update(
                state=summary["state"],
                verification_status=summary["verification_status"],
                description="",
                cvss=None,
                cvss_assessments=[],
            )
            return
        if result.get("verification_status") != "published" or summary["state"] != "PUBLISHED":
            return
        result.setdefault("ssvc_assessments", []).extend(extract_ssvc(cve_id, raw, source))
        result.setdefault("reference_records", []).extend(reference_records(raw, source))
        result.setdefault("impacts", []).extend(structured_impacts(raw, source))
        # Keep every contributor's score rather than overwriting the NVD choice.
        for score in summary.get("cvss_assessments", []):
            score = {**score, "source_revision_id": source.get("revision_id")}
            if score not in result["cvss_assessments"]:
                result["cvss_assessments"].append(score)
        if not result.get("affected"):
            result["affected"] = summary.get("affected", [])
        for url in summary.get("references", []):
            if url not in result["references"]:
                result["references"].append(url)
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
        result["errors"].append("CVE Program supplementary data: " + str(error))
    finally:
        acquisition._append_acquisition(store, key, result, capture.state if capture else None)


def enrich(store, cve_id, *, refresh=False, cancel_event=None, local_only=False) -> CVERecord:
    if local_only:
        from .local import local_record

        return local_record(store, cve_id, cancel_event=cancel_event)
    acquisition._cancelled(cancel_event)
    result = copy.deepcopy(verify(store, cve_id, refresh=refresh, cancel_event=cancel_event))
    cve_id = result["id"]
    acquisition._cancelled(cancel_event)
    _supplement(store, result, refresh=refresh, cancel_event=cancel_event)
    for publisher, key, url in [
        ("FIRST EPSS", "epss:" + cve_id, EPSS_URL + cve_id),
        ("CISA KEV", "kev", KEV_URL),
    ]:
        acquisition._cancelled(cancel_event)
        capture = None
        try:
            capture = capture_json(store, key, url, refresh=refresh, cancel_event=cancel_event)
            raw, stamp, source = capture.data, capture.retrieved_at, capture.source
            current = acquisition.risk_current_state(store, key)
            current_matches = current and current.get("sha256") == source.get("catalog_feed_sha256")
            stale = (
                current["stale"]
                if current_matches
                else source.get("catalog_stale", False) or acquisition._age(stamp) > 172800
            )
            if key.startswith("epss:"):
                score = next((x for x in raw["data"] if x.get("cve") == cve_id), None)
                result.update(
                    epss=None,
                    epss_percentile=None,
                    epss_date=None,
                    epss_retrieved_at=stamp,
                    epss_availability="not_found" if score is None else "supplied",
                    epss_percentile_availability="not_found" if score is None else "not_supplied",
                    epss_model_version=source.get("model_version"),
                    epss_stale=stale,
                    epss_checked_at=current.get("last_success_at") if current_matches else stamp,
                )
                if score is not None:
                    result.update(
                        epss=_number(score["epss"], 1, "EPSS probability"),
                        epss_date=score.get("date"),
                        epss_percentile=_number(score["percentile"], 1, "EPSS percentile")
                        if score.get("percentile") is not None
                        else None,
                        epss_percentile_availability="supplied"
                        if score.get("percentile") is not None
                        else "not_supplied",
                    )
            else:
                validate_kev_catalog(raw)  # also validates older cached records
                entry = next((x for x in raw["vulnerabilities"] if x.get("cveID") == cve_id), None)
                result.update(
                    kev=entry is not None,
                    kev_date=raw["dateReleased"],
                    kev_details=entry,
                    kev_retrieved_at=stamp,
                    kev_catalog_version=raw["catalogVersion"],
                    kev_catalog_count=raw["count"],
                    kev_availability="supplied",
                    kev_catalog_complete=True,
                    kev_stale=stale,
                    kev_checked_at=current.get("last_success_at") if current_matches else stamp,
                    ransomware=ransomware(
                        entry, source.get("revision_id"), membership=entry is not None
                    ),
                    kev_catalog_metadata={k: v for k, v in raw.items() if k != "vulnerabilities"},
                )
            result["sources"].append(
                {"publisher": publisher, "url": url, "retrieved_at": stamp, **source}
            )
        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ) as error:
            result["errors"].append(publisher + ": " + str(error))
            result["epss_availability" if key.startswith("epss:") else "kev_availability"] = (
                "unavailable"
            )
            if key.startswith("epss:"):
                result["epss_percentile_availability"] = "unavailable"
        finally:
            acquisition._append_acquisition(store, key, result, capture.state if capture else None)
    return finish_intelligence(store, result)
