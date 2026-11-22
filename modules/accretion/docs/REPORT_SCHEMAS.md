# Report schemas and admission

[Module guide](README.md) · [Filter](PIPELINE.md#filter) · [Evaluate](PIPELINE.md#evaluate) · [Dark Matter](DARK_MATTER.md)

Accretion uses two separate contracts: an inventory of Shadowserver report fields
for retention and diagnostics, and explicit notification adapters that decide
whether a row is worth qualification. A field being known does not make a report
eligible, and report eligibility does not prove attribution, website identity or
urgency. Those belong to the later [pipeline stages](PIPELINE.md).

## Pinned provider inventory

[shadowserver-reports.json](../schemas/shadowserver-reports.json) contains **177
report definitions and 746 distinct field names**. Its
[metadata](../schemas/shadowserver-reports.meta.json) records publisher, source
URL, retrieval date, commit and SHA-256. The current pin is commit
`80f11a5a47b28ae27b15ca42ddb54d0a227f8f94`, retrieved November 12, 2026.

[report_profiles.inventory()](../components/report_profiles.py) checks the bundled
bytes against that digest before caching them. Runtime processing uses the local
pin; it does not fetch schemas from the network. `inventory_metadata()` reports
the digest, counts and current adapter version (`0.9.92-2`).

This upstream inventory lists available fields, not universally required fields.
Optional missing columns and unknown extensions are diagnostic information, not
automatic reasons to reject a row. Dark Matter preserves all supplied fields.
The notification contract below determines the smaller set needed for intake.

## Report identity and supported adapters

`resolve_profile(fields, filename="", configured_type="auto")` selects identity
in this order: explicit import setting, row `report_type`, recognized filename.
Known report names/aliases normalize to canonical IDs. HTTP-like columns alone
never turn an unknown file into a Vulnerable HTTP report. A generic filename
therefore needs row identity or a deliberate profile selection.

Each profile records its ID/name, selection basis, inventory digest/commit,
declared fields, capability, adapter version, observation kind, version semantics,
endpoint roles and missing/unknown-column diagnostics. An unimplemented or
unclassified profile has `capability="retained"`; implemented adapters use
`capability="eligible"`. This means eligible for admission policy, not yet a lead.

`supported_profiles()` currently returns **26 canonical IDs**:

| IDs/family | Observation kind | Version meaning | Normal admission mode |
| --- | --- | --- | --- |
| `scan_http_vulnerable`, `scan6_http_vulnerable` | Vulnerability | Software; CVE or version required | Critical or targeted |
| `scan_smtp_vulnerable`, `scan6_smtp_vulnerable`, `scan_exchange`, `scan6_exchange` | Vulnerability | Software | Critical or targeted |
| `scan_badsecrets`, `scan6_badsecrets` | Weak secret | Unspecified | Critical or targeted |
| `scan_isakmp`, `scan6_isakmp` | Vulnerability | Protocol | Critical or targeted |
| `scan_mongodb`, `scan6_mongodb` | Exposure | Software | Critical or targeted |
| `scan_http`, `scan6_http` | Exposure | Software | Targeted |
| `scan_rdp`, `scan6_rdp`, `scan_msrpc`, `scan6_msrpc`, `scan_gtp` | Exposure | Protocol | Targeted |
| `population_isakmp`, `population6_isakmp`, `population_ntrip` | Exposure | Protocol | Targeted |
| `compromised_website`, `compromised_website6`, `compromised_iot`, `compromised_iot6` | Compromise indicator | Software | Supported incident exception described below |

Except for Vulnerable HTTP's CVE-or-version rule, adapters require a version only
for EOL findings. `population_ntrip` checks `ntrip_version` before `version`.
An EOL finding always needs actual software-version evidence; a protocol revision
cannot satisfy it. The adapter dictionary is the executable authority for these
details and the place to extend support.

## Cheap structural admission

[EntryValidator](../components/intake/validation.py) requires nonempty `tag`,
`hostname`, `ip` and `region`. It checks configured jurisdiction, finding/version
semantics, hostname syntax/public-suffix identity and IP syntax in that order.
Regions match the configured set case-insensitively. A hostname must have a valid
registrable public suffix. Valid IPv4 and IPv6 source addresses retain their
original text alongside the canonical address; public-IP qualification happens
later, before network work.

[Finding validation](../components/intake/findings.py) accepts machine-readable
scanner condition IDs, valid CVE IDs and supported EOL tag/list forms. It rejects
arbitrary prose, absent markers and malformed CVE-shaped identifiers; a valid CVE
cannot hide a malformed second one. Unknown scanner condition names are not
rejected merely because the local catalog lacks an explanation.

Version checks preserve vendor build strings and release names. They reject
missing/placeholder values such as `unknown` and `PHP/unknown`; they do not impose
SemVer or invent a software version from protocol evidence. The remaining
Vulnerable HTTP independent-detector/version question is explicitly open in
[ISS024](ISSUES.md#iss024-filter-contracts-and-interruption).

Structural rejection reasons include `missing_required_value`,
`outside_jurisdiction`, `missing_version`, `placeholder_version`,
`malformed_cve_identifier`, `unsupported_finding`, `invalid_hostname` and
`invalid_ip`. Unsupported adapters stop with `unsupported_report_profile` before
catalog, browser or attribution work. Every nonempty rejected source row remains
available through Dark Matter.

## Eligibility policy, not urgency scoring

`notification_eligibility(fields, profile, config, *, catalog_records=None)`
combines supported profile, source severity, vetted local CVE facts and outreach
mode. It never writes a severity value into the original source.

- Critical mode admits reported critical findings, qualifying local critical CVSS
  evidence, or vetted known exploitation. Complete local catalog coverage can
  lower as well as raise CVE-only admission; incomplete coverage cannot establish
  that an unknown finding is minor.
- Only vetted local records linked by reported CVE IDs contribute CVSS/KEV.
  Arbitrary source columns named CVSS or KEV do not bypass admission.
- Targeted mode (`outreach_mode="targeted"`, or the retained `critical_only=False`
  configuration) requires a nonempty `targeted_reason`. Targeted-only exposure
  profiles do not enter ordinary critical-mode outreach.
- Supported compromise indicators may enter critical mode without a CVE, software
  version or critical severity label. Targeted mode still requires its reason.
  Their modest urgency base is applied only in Evaluate.
- Withdrawn-only CVE rows are excluded. Independently supported EOL, exposure,
  weak-secret and compromise evidence can survive associated CVE withdrawal.

Eligibility exclusions include `targeted_profile_review_required`,
`targeted_reason_required`, `withdrawn_cve_only`, `unknown_severity` and
`below_critical`. A structurally valid sibling of an eligible row remains context
under the same root domain. Its own `eligible` flag stays false and
`included_as_context` becomes true; it gains no actionable admission by grouping.

## What crosses the handoff

Filter builds full `observation_envelope` values only for selected groups.
`normalized.profile` carries report identity and schema semantics;
`normalized.eligibility` carries the decision and its basis;
`normalized.accretion_cves` retains the vetted snapshot used for admission and
later scoring. Original source fields stay separate.

The envelope also records source digest/position identity, acquisition provenance,
service endpoint, scan timestamp, CVE references, version source fields and
explicitly parsed product/version pairs. Protocol/unspecified versions skip
software-product parsing. An unpaired bare version is not attached to every
product named in a tag. Qualified findings retain their exact report type and
source row; they do not become an untyped hostname-only lead.

## Adding or changing report support

1. Establish the canonical report identity and source field meaning from the
   provider contract. If updating the bundled inventory, update its provenance
   metadata and matching digest together; do not silently replace the runtime pin.
2. Add the explicit adapter in `report_profiles.py`: observation kind, version
   semantics/fields, minimal version requirement and admission mode. Change
   `PROFILE_VERSION` when adapter behavior changes so retained provenance and
   import deduplication distinguish the new contract.
3. Define the actual condition evidence using existing finding/version helpers.
   If semantics need a new rule, change that owner deliberately; optional columns
   should not become mandatory merely because the inventory lists them.
4. Check the corresponding Library explanation and Investigations report coverage.
   Use the existing [report explainer selector](../../investigations/components/report_explainers.py)
   and [Library guide](../../library/docs/README.md); adapter eligibility alone does
   not create a report template or prove that explanation coverage is complete.
5. Add ordinary, rejected, context-sibling and schema-preservation fixtures. Include
   withdrawn/unknown CVE cases when relevant and a complete qualification/report
   case for a newly supported finding family. Assert source bytes and report type
   survive, not merely that a helper returns true.
6. Add urgency policy only through [Evaluate's scoring matrix](PIPELINE.md#evaluate).
   A new report base does not require editing Filter, Qualify or Associate.

The existing checks live in `test_intake_profiles_070.py`,
`test_intake_profiles_096.py`, `test_intake_versions_0990.py`,
`test_qualified_lead_contract.py` and `test_accretion_reports.py` under
`modules/accretion/tests/` in the source checkout. Run the full module suite for a
completed adapter behavior change, plus affected report/Library tests; follow the
[shared verification policy](../../../docs/DEVELOPMENT.md#maintenance-workflow).
