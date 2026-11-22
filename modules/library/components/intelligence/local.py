"""Immutable notification sources from the local reference catalog only.

No provider requests or nested workspace transactions. A new case can retain
its exact source selections in the same transaction as its observation scope.
"""

import re
from contextlib import nullcontext
from copy import deepcopy

from attribution.models import parse_json
from ..cve_intelligence import ransomware, validate_kev_catalog
from modules.workspace.components.primitives import now
from ..repositories.sources import SourceRepository
from .selection_identity import selection_key
from . import acquisition
from .adapters import _empty, _number, summarize_nvd


def _risk(result, store, key, public_url, *, captures):
    # Share acquisition and interpretation of one consistent local snapshot.
    # Each selected CVE retains its own result and the same captured source proof.
    if key not in captures:
        captured = acquisition._capture_local_risk(store, key, public_url)
        if captured is None:
            captures[key] = None
        else:
            body, source = captured
            raw = parse_json(body)
            entries = None
            if key == "kev":
                validate_kev_catalog(raw)
                entries = {item["cveID"]: item for item in raw["vulnerabilities"]}
            captures[key] = raw, source, entries
    captured = captures[key]
    if captured is None:
        result["epss_availability" if key.startswith("epss:") else "kev_availability"] = (
            "unavailable"
        )
        return
    raw, source, entries = captured
    stamp = source["retrieved_at"]
    if key.startswith("epss:"):
        score = next((v for v in raw["data"] if v.get("cve") == result["id"]), None)
        result.update(
            epss=None,
            epss_percentile=None,
            epss_date=None,
            epss_retrieved_at=stamp,
            epss_availability="supplied" if score else "not_found",
            epss_percentile_availability="not_supplied" if score else "not_found",
            epss_model_version=source.get("model_version"),
            epss_stale=source.get("catalog_stale", True),
        )
        if score:
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
        entry = deepcopy(entries.get(result["id"]))
        result.update(
            kev=entry is not None,
            kev_date=raw["dateReleased"],
            kev_details=entry,
            kev_retrieved_at=stamp,
            kev_catalog_version=raw["catalogVersion"],
            kev_catalog_count=raw["count"],
            kev_availability="supplied",
            kev_catalog_complete=True,
            kev_stale=source.get("catalog_stale", True),
            ransomware=ransomware(entry, source.get("revision_id"), membership=entry is not None),
            kev_catalog_metadata=deepcopy({k: v for k, v in raw.items() if k != "vulnerabilities"}),
        )
    result["sources"].append(dict(source))


def local_record(store, cve_id, *, db=None, cancel_event=None, captures=None):
    """Select the locally available record; absence never causes an API fallback."""
    from .selection import finish_intelligence

    cve_id = str(cve_id).upper()
    if not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve_id):
        raise ValueError("Invalid CVE identifier")
    acquisition._cancelled(cancel_event)
    public_url = "https://nvd.nist.gov/vuln/detail/" + cve_id
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
        "local_only": True,
        "public_url": public_url,
        "applicability": "Reported by source; recipient IT determines software applicability",
    }
    captured = acquisition._capture_catalog(store, cve_id, public_url)
    if captured is None:
        result.update(local_catalog_missing=True)
        result["errors"].append(
            "Missing or unusable local catalog record. Update the catalog in Library; "
            "no external request was made."
        )
    else:
        body, source = captured
        raw = parse_json(body)
        result.update(summarize_nvd(cve_id, raw, source))
        source.update(
            date_published=result.get("date_published", ""),
            date_updated=result.get("date_updated", ""),
        )
        result.update(
            record=raw,
            record_path=source["record_path"],
            body_sha256=source["sha256"],
            revision_id=source["revision_id"],
            retrieved_at=source["retrieved_at"],
            http_status=None,
            source="NVD",
            from_catalog=True,
            catalog_checked_at=source.get("catalog_checked_at"),
            stale=source.get("catalog_stale", True),
            sources=[source],
            attempts=[source],
        )
    captures = {} if captures is None else captures
    for key, public in (
        ("epss:" + cve_id, "https://www.first.org/epss/"),
        ("kev", "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"),
    ):
        acquisition._cancelled(cancel_event)
        try:
            _risk(result, store, key, public, captures=captures)
        except (ValueError, KeyError, TypeError, OSError) as error:
            result["errors"].append("Local risk data unavailable: " + type(error).__name__)
            result["epss_availability" if key.startswith("epss:") else "kev_availability"] = (
                "unavailable"
            )
    with nullcontext(db) if db is not None else store.transaction() as connection:
        result = finish_intelligence(
            store, result, db=connection, retain=not result.get("local_catalog_missing")
        )
        repository = SourceRepository(store)
        repository.put(connection, selection_key(result), result, immutable=True)
    return result


def initial_records(store, ids, existing, db, *, preserve_existing=False):
    """New notifications select current local records; extensions keep selections."""
    prior = (
        {item["id"]: item for item in existing if item.get("id") in ids}
        if preserve_existing
        else {}
    )
    captures = {}
    return [
        prior[cve_id] if cve_id in prior else local_record(store, cve_id, db=db, captures=captures)
        for cve_id in sorted(ids)
    ]
