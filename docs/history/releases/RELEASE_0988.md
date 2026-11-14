# 0.9.88 — Accretion intake calibration

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

The 2,000-record test bank exposed a distinction the first release did not handle
well enough: a mathematically consistent temperature can still rank an observation
that should never have entered the lead queue. This release corrects admission
before changing the provisional scoring weights.

## Domain validity replaces spreadsheet exclusions

The old `.com`-only and numeric-root filters are removed. A valid `.org`, `.net`,
`.gov`, or other recognized public suffix is not a lower-quality domain. Digits
in a valid registrable root or service label are not grounds for rejection.

Saved legacy settings and queued import configurations cannot silently restore
either exclusion. Original configuration values remain available as provenance.
Hostname syntax, registrable-domain validity, IP parsing, required evidence, supported report
profiles and jurisdiction remain the admission boundaries. Historical intake
decisions and certified evidence are preserved; reevaluation creates a new
decision under the current policy.

## Reject semantic junk before ranking

Accretion rejects malformed CVE-shaped tokens, including clipped, prefixed or
suffixed identifiers and non-ASCII identifier digits. Null, punctuation-only,
numeric and prose-only tags cannot stand in for a finding identifier. EOL and
non-CVE HTTP findings requiring software evidence reject placeholder versions.
A supplied critical label cannot turn meaningless source content into a lead.

Legitimate non-CVE service adapters and profile-specific version exceptions stay
supported. Valid unknown scanner condition identifiers and vendor release strings
remain available, and a valid CVE can still use the documented missing-catalog
fallback. An optional unknown banner does not invalidate a valid CVE row unless
an EOL finding independently requires software-version evidence. Known-exploitation
admission remains distinct from reported severity, and original source fields are
retained without invented corrections.

Placeholder-version checking scans separator-heavy strings in linear time and
retains only a bounded missing-marker suffix. Long vendor release strings do not
trigger repeated suffix normalization or lose their supported formats.

## Preserve DNS identity across normal imports

Uppercase and IDNA hostnames use the existing canonical DNS comparison when
matching attribution results, reviewing them, restoring backups and reading case
evidence history. A valid spelling difference no longer aborts a normal workbook
import. Exact canonical-domain and result-ID checks still reject unrelated
results; original source fields and saved group identities remain unchanged.

## Separate operational expectations from arithmetic

The test bank contains 1,000 intended-valid and 1,000 intended-invalid records.
Each case has an expectation recorded separately from the production scorer.
The comparison separates three outcomes:

1. **Admission:** whether the record should enter lead work and whether it did.
2. **Operational temperature:** the deliberately assigned outreach-priority band
   compared with the application's observed band. Rejected records have no
   temperature.
3. **Formula verification:** an independent calculation of the published weights,
   kept separate from the operational judgment. Correct arithmetic does not prove
   that the chosen weights produce the most useful priorities.

Semantic challenge cases are identified explicitly so policy gaps are not hidden
by choosing expectations that merely repeat the current code. Hostnames and
observations are synthetic; the NVD, CISA KEV and FIRST EPSS reference records are
captured official data. The user's workstation database was unavailable, so the
test uses an isolated database with the application's schema and a documented
reference subset. A real CVE is deliberately held out of local NVD/EPSS tables
to test missing-catalog behavior without inventing a fake valid identifier.

No synthetic hostname is resolved, visited or contacted. Attribution is isolated
from the scoring comparison. The bank is an operational regression and calibration
exercise, not proof that any real organization is affected.

| Bank outcome | 0.9.87 baseline | 0.9.88 corrected |
| --- | ---: | ---: |
| Intended-valid records admitted | 900 / 1,000 | 1,000 / 1,000 |
| Intended-invalid records rejected | 880 / 1,000 | 1,000 / 1,000 |
| False rejects | 100 | 0 |
| False accepts | 120 | 0 |

The baseline false accepts were 40 malformed CVE identifiers, 40 meaningless
finding tags and 40 placeholder EOL versions. Its false rejects were the 50-case
non-.com/IDNA cohort and 50 numeric business roots. Expectations were retained for
the corrected replay.

The corrected valid bank produces 50 Cool, 125 Warm, 575 Hot and 250 Blazing
records. Operational band expectations agree for 975 of 1,000 records. The other
25 repeat one versionless-critical scenario: CVE-2023-38545 is resolved, with
CVSS 9.8 and high captured EPSS. The application rates it Hot while the deliberately
conservative operational expectation is Warm. Hot is defensible here; this is one
calibration review point, not 25 separate scoring bugs.

All 1,000 admitted records agree with the independent implementation of the
published temperature rules. Quality and Urgency agree; 214 aggregate results
differ by one tenth because decimal and binary-float tie rounding differ. None
changes a temperature. The weights are intentionally unchanged in this correction.

## Existing behavior retained

Quality and Urgency remain separate 0–100 scores; their aggregate remains 50/50.
Cool, Warm, Hot and Blazing thresholds are unchanged. The saved policy, source
records and score explanations continue through Leads, notification scope and
certified output. Dark Matter still preserves usable observations outside lead
work without creating a review queue or claiming row-specific attribution.

Original files, stable row identities, supported adapters, contextual grouping,
explicit attribution, retry handling and historical packages remain protected.
Database schema 12 and runtime/dependency pins are unchanged.

## Verification and acceptance

The full regression passed 1,910 backend tests and 120 subtests, with one existing
deprecation warning. All 33 offline frontend suites, formatting, lint, syntax,
release identity and architecture checks passed. The completed bank and
upgrade/restore rehearsal are recorded in VALIDATION.md. The 0.9.87-to-0.9.88
rehearsal preserved 112 protected files, three historical reports,
15 section validations and all 15 historical download hashes in each upgraded and
restored workspace. The release remains Dark Matter Chaos unstable.
Native Windows installation/relaunch, actual Word pagination, installed browser
capture and workstation visual acceptance remain pending; offline tests do not
establish those results. Keep an exported backup for comparison and rollback.

