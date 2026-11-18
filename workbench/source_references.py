"""Explicit retained-source references; no provider or filesystem access."""

from copy import deepcopy


def cve_response_sources(record):
    """Only explicit captured-response locations, never arbitrary nested paths.

    Source attempts without a response have no source bytes/hash to manufacture.
    Failed response attempts retain metadata and hashes, never their original
    webpage/error bodies. Legacy paths are checked before any content is reused.
    """
    yield record
    for key in ("sources", "source_snapshots", "attempts", "refresh_attempts"):
        for source in record.get(key, []):
            if isinstance(source, dict) and (
                source.get("record_path") or source.get("response_retention") == "metadata-only"
            ):
                yield source
    for item in record.get("supplementary_records", []):
        if isinstance(item, dict) and isinstance(item.get("source"), dict):
            yield item["source"]
    for key in ("acquisition", "refresh_acquisition"):
        for attempt in record.get(key, []):
            if not isinstance(attempt, dict):
                continue
            response = attempt.get("response")
            if not isinstance(response, dict) or not (
                response.get("record_path") or response.get("response_retention") == "metadata-only"
            ):
                continue
            outcome = {
                name: deepcopy(attempt[name])
                for name in (
                    "id",
                    "outcome",
                    "attempted_at",
                    "completed_at",
                    "error",
                    "source_snapshot_id",
                    "last_usable_snapshot_id",
                )
                if name in attempt
            }
            yield {
                **response,
                "acquisition_outcomes": [outcome],
                "source_status": "captured_response"
                if attempt.get("outcome") == "success"
                else "captured_failed_response",
            }
