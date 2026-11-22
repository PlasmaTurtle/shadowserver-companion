"""Public Accretion archive API. Storage never qualifies or associates evidence."""

from .dark_matter_store import (
    DarkMatterStore as DarkMatterStore,
    enqueue_batch as enqueue_batch,
    enqueue_outcome as enqueue_outcome,
    enqueue_outcomes as enqueue_outcomes,
    prepare_batch as prepare_batch,
    enqueue_prepared as enqueue_prepared,
    drain as drain,
    archive_counts as archive_counts,
    delivery_status as delivery_status,
)

REASONS = {
    "superseded": "Replaced by a newer qualified finding",
    "unchanged_reported": "Finding already belongs to a notification",
    "ignored": "Ignored for outreach",
    "provider_out_of_scope": "Internet provider outside current outreach scope",
    "below_critical": "Below the critical outreach threshold",
    "unknown_severity": "Severity not established",
    "non_com_root_excluded": "Historical suffix filter (removed)",
    "numeric_root_excluded": "Historical numeric-root filter (removed)",
    "unsupported_report_profile": "Report type outside the supported outreach profiles",
    "missing_version": "Required version evidence absent",
    "placeholder_version": "Required version is a placeholder, not an observed release",
    "malformed_cve_identifier": "Malformed reported CVE identifier",
    "unsupported_finding": "Source tag does not identify a finding",
    "incident_review_required": "Incident finding outside proactive outreach",
    "targeted_profile_review_required": "Outside the selected outreach mode",
    "targeted_reason_required": "Targeted outreach reason absent",
    "api_narrative_date_review_required": "Historical narrative-date gate (removed)",
}
