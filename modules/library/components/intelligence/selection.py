"""Complete and retain a normalized intelligence revision from captured evidence."""

from ..repositories.sources import SourceRepository
from ..cve_intelligence import (
    ADAPTER_VERSION,
    SELECTION_POLICY,
    extract_ssvc,
    select_ssvc,
    ransomware,
    reference_records,
    structured_impacts,
    stable_id,
    signal_labels,
)


def finish_intelligence(store, result, *, db=None, retain=True):
    """Complete the same adapter fields for publisher and local-only snapshots."""
    cve_id = result["id"]
    result.setdefault("ransomware", ransomware(None, membership=result.get("kev")))
    if result.get("kev") is None:
        result["ransomware"]["availability"] = result.get("kev_availability", "unavailable")
    # Existing saved 0.6.0 primary records get source-linked adapter fields too.
    if result.get("record") and result.get("verification_status") == "published":
        source = next(
            (s for s in result["sources"] if s.get("revision_id") == result.get("revision_id")), {}
        )
        for key, extractor in [
            ("ssvc_assessments", extract_ssvc),
            ("reference_records", reference_records),
            ("impacts", structured_impacts),
        ]:
            extracted = (
                extractor(cve_id, result["record"], source)
                if key == "ssvc_assessments"
                else extractor(result["record"], source)
            )
            existing = result.setdefault(key, [])
            for item in extracted:
                if item not in existing:
                    existing.append(item)
    selected = select_ssvc(result.get("ssvc_assessments", []))
    result["selected_ssvc_assessment_id"] = selected["id"] if selected else None
    result["ssvc_availability"] = (
        "supplied"
        if selected
        else ("not_supplied" if result.get("verification_status") == "published" else "unavailable")
    )
    result["ssvc_selection_policy"] = SELECTION_POLICY
    result["intelligence_adapter_version"] = ADAPTER_VERSION
    result["signal_labels"] = signal_labels(result)
    # Immutable shared bank revision. Cases select/copy it explicitly; no case
    # draft or certification is mutated by this retrieval operation.
    identity = {
        k: v
        for k, v in result.items()
        if k
        not in (
            "checked_at",
            "from_cache",
            "acquisition",
            "refresh_acquisition",
            "refresh_attempts",
            "refresh_errors",
            "provider_outcomes",
            "errors",
            "stale_sources",
        )
    }
    result["intelligence_revision_id"] = stable_id("intelligence-", identity)
    if not retain:
        return result
    if db is None:
        with store.transaction() as connection:
            SourceRepository(store).publish_intelligence(connection, cve_id, result)
    else:
        SourceRepository(store).publish_intelligence(db, cve_id, result)
    return result
