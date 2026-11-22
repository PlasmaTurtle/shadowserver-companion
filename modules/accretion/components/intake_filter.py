"""Cheap report selection, followed by preparation of surviving domain groups.

Source retention is an output decision, never a second validation pipeline.
The service owns lifecycle/publication; Dark Matter owns archive interpretation.
"""

from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
import time

from .intake.files import read_entries
from .intake.records import SourceObservation, CandidateObservation, CandidateGroup, is_empty_entry
from .intake.validation import EntryValidator
from .intake.domains import root_domain
from .accretion import vet_cves
from .intake_progress import accepted_patterns, catalog_readiness, publish
from .report_profiles import (
    resolve_profile,
    notification_eligibility,
    observation_envelope,
    inventory_metadata,
)
from modules.library.components.intelligence.identifiers import identifiers
from modules.workspace.components.primitives import now
from .report import Report, ReportCandidate


class IntakeInterrupted(Exception):
    """The caller requested pause/shutdown; no result should be published."""


@dataclass(slots=True)
class RowCandidate:
    entry: CandidateObservation
    profile: dict
    domain: str
    cves: list
    eligibility: dict = field(default_factory=dict)
    catalog: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FilterResult:
    report: Report
    outcomes: list
    rows_read: int
    valid_rows: int
    rejected: dict
    config_updates: dict
    candidates: tuple[ReportCandidate, ...]

    def __post_init__(self):
        if not isinstance(self.report, Report):
            raise TypeError("Filter result requires its Report")
        candidates = tuple(self.candidates)
        if any(
            not isinstance(value, ReportCandidate) or value.report != self.report
            for value in candidates
        ):
            raise ValueError("Filter candidates must belong to the result report")
        object.__setattr__(self, "candidates", candidates)

    @property
    def group_count(self):
        return len(self.candidates)


def _reject(examples, counts, source, reason):
    counts[reason] += 1
    sample = examples.setdefault(reason, [])
    if len(sample) < 5:
        sample.append(
            {
                "sheet": source.sheet,
                "row": source.row,
                "hostname": str(source.fields.get("hostname") or "")[:253],
            }
        )


def _read_candidates(store, report, config, checkpoint):
    validator = EntryValidator(set(config["regions"]))
    candidates, outcomes, profiles = [], [], {}
    rejected, examples = Counter(), {}
    count = ignored = 0
    last_progress = time.monotonic()
    with closing(read_entries(store.path(report.path), config["sheet"])) as reader:
        for rows_seen, row in enumerate(reader, 1):
            if rows_seen > 250000:
                raise ValueError("Report exceeds the 250,000 row limit")
            if rows_seen % 256 == 1:
                checkpoint()
            if is_empty_entry(row):
                ignored += 1
                continue
            count += 1
            source = SourceObservation(report.name, row.sheet, row.row, row.fields)
            profile = resolve_profile(source.fields, report.name, config.get("report_type", "auto"))
            profiles[profile["id"]] = profile
            entry, reason = (
                validator.validate_with_reason(source, profile=profile)
                if profile["capability"] == "eligible"
                else (None, "unsupported_report_profile")
            )
            if entry:
                candidates.append(
                    RowCandidate(
                        entry,
                        profile,
                        root_domain(source.fields["hostname"]),
                        identifiers([source.fields.get("tag", "")]),
                    )
                )
            else:
                _reject(examples, rejected, source, reason)
                outcomes.append(
                    {
                        "source": source,
                        "report_type": profile["id"],
                        "outcome": "rejected",
                        "reason": reason,
                    }
                )
            if rows_seen % 256 == 0 and time.monotonic() - last_progress >= 0.5:
                publish(
                    store,
                    report.id,
                    config,
                    "filter",
                    "Checking report candidates",
                    read_rows=count,
                    structural_passed=len(candidates),
                    filtered_rows=sum(rejected.values()),
                )
                last_progress = time.monotonic()
    checkpoint()
    return candidates, outcomes, profiles, rejected, examples, count, ignored


def _select_groups(store, candidates, config, checkpoint):
    # Snapshot context CVEs too: a later retry must not see a different catalog.
    vetted = (
        vet_cves(
            store.root,
            sorted({cve for candidate in candidates for cve in candidate.cves}),
            as_of=config["accretion_scored_at"],
        )
        if candidates and config.get("accretion_policy")
        else {}
    )
    groups, eligibility_counts = {}, Counter()
    for index, candidate in enumerate(candidates):
        if index % 256 == 0:
            checkpoint()
        candidate.catalog = {cve: vetted[cve] for cve in candidate.cves if cve in vetted}
        candidate.eligibility = notification_eligibility(
            candidate.entry.source.fields,
            candidate.profile,
            config,
            catalog_records=candidate.catalog,
        )
        eligibility_counts[candidate.eligibility["reason"] or "eligible"] += 1
        groups.setdefault(candidate.domain, []).append(candidate)
    return groups, vetted, eligibility_counts


def _prepare_groups(report, config, candidates_by_domain, outcomes, rejected, examples, checkpoint):
    groups = []
    acquisition = {
        key: value
        for key, value in config.get("acquisition", {}).items()
        if key not in {"receipt", "live_api_acceptance"}
    }
    processed = 0
    for domain, candidates in candidates_by_domain.items():
        selected = any(candidate.eligibility["eligible"] for candidate in candidates)
        entries = []
        for candidate in candidates:
            if processed % 256 == 0:
                checkpoint()
            processed += 1
            source = candidate.entry.source
            reason = "pending_qualification" if selected else candidate.eligibility["reason"]
            outcomes.append(
                {
                    "source": source,
                    "report_type": candidate.profile["id"],
                    "outcome": "pending" if selected else "rejected",
                    "reason": reason,
                }
            )
            if not selected:
                _reject(examples, rejected, source, reason)
                continue
            candidate.eligibility["included_as_context"] = not candidate.eligibility["eligible"]
            normalized = observation_envelope(
                source,
                candidate.profile,
                candidate.eligibility,
                source_sha256=report.sha256,
                acquisition=acquisition,
            )
            normalized["accretion_cves"] = candidate.catalog
            entries.append(
                CandidateObservation(
                    source, candidate.entry.ip, candidate.entry.private_ip, normalized
                )
            )
        if selected:
            groups.append(CandidateGroup(domain, entries))
    return groups


def filter_report(store, report: Report, config, checkpoint) -> FilterResult:
    """Return a complete publication result; no jobs or archive rows are written."""
    if not isinstance(report, Report):
        raise TypeError("Filter requires a Report")
    checkpoint()
    readiness = catalog_readiness(store.root)
    publish(store, report.id, config, "filter", "Reading source rows", read_rows=0, total_rows=None)
    candidates, outcomes, profiles, rejected, examples, count, ignored = _read_candidates(
        store, report, config, checkpoint
    )
    publish(
        store,
        report.id,
        config,
        "filter",
        "Checking local CVE catalog",
        read_rows=count,
        total_rows=count,
        structural_passed=len(candidates),
        filtered_rows=sum(rejected.values()),
    )
    if config.get("accretion_policy"):
        config["accretion_scored_at"] = now()
    grouped, vetted, eligibility_counts = _select_groups(store, candidates, config, checkpoint)
    groups = _prepare_groups(report, config, grouped, outcomes, rejected, examples, checkpoint)
    valid = sum(len(group.observations) for group in groups)
    selected = [entry for group in groups for entry in group.observations]
    stats = {
        "accepted_patterns": accepted_patterns(groups),
        "ignored_empty_rows": ignored,
        "eligibility": dict(eligibility_counts),
        "rejection_examples": examples,
        "accretion": {
            "name": "Accretion",
            "phase_version": 3,
            "structural_passed": len(candidates),
            "filtered_rows": count - valid,
            "admitted_rows": valid,
            "context_rows": sum(
                not entry.normalized["eligibility"]["eligible"] for entry in selected
            ),
            "leads": len(groups),
            "cves_checked": len(vetted),
            "cves_available": sum(record["status"] == "available" for record in vetted.values()),
            "cves_missing": sum(record["status"] == "missing" for record in vetted.values()),
            "cves_unavailable": sum(
                record["status"] in {"invalid", "unavailable"} for record in vetted.values()
            ),
            "cves_rejected": sum(record["status"] == "rejected" for record in vetted.values()),
            "kev_admitted_rows": sum(
                candidate.eligibility.get("admission_signal") == "known_exploitation"
                and candidate.eligibility["eligible"]
                for candidate in candidates
            ),
            "catalog_critical_rows": sum(
                candidate.eligibility["admission_basis"] == "local_catalog_cvss"
                and candidate.eligibility["admission_severity"] == "critical"
                and candidate.eligibility["eligible"]
                for candidate in candidates
            ),
            "dark_matter_rows": len(outcomes),
            "discarded_rows": 0,
        },
    }
    candidates = tuple(ReportCandidate(report, group) for group in groups)
    checkpoint()
    return FilterResult(
        report,
        outcomes,
        count,
        valid,
        dict(rejected),
        {
            "catalog_at_scoring": readiness,
            "accretion_scored_at": config.get("accretion_scored_at"),
            "report_profiles": list(profiles.values()),
            "profile_inventory": inventory_metadata(),
            "intake_stats": stats,
        },
        candidates,
    )
