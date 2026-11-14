# Validation · Shadowserver Companion 0.9.6 · UNSTABLE

Executed November 10, 2026, against synthetic Linux workspaces using Python
3.14.10. This is the explainer update based on the delivered 0.9.5 UI refinement.
It remains unstable pending exact-build Windows acceptance. Historical 0.9.5
validation is retained in docs/VALIDATION_095.md.

## Automated regression

All **1,213 collected backend tests** have passing results across the broad
shards and focused reruns. The initial four shards ran 1,175 tests: 1,164 passed
and 11 failed; 29 subtests passed. The final affected regression passed
**220 tests**, including all 11 earlier failures. New checks added after the
broad collection are included in the reconciled coverage. Any final footer
checks appear separately in coverage-completion.xml. This is reconciled coverage,
not one uninterrupted full-suite run. Original failure logs and passing reruns
are retained in the validation evidence archive.

Most initial failures were obsolete synthetic fixtures or assertions: explicit
source identity is now required, and historical layout fixtures must pin their
historical revision. One exposed a real draft-save error after excluding the
last CVE: an unsupported severity string caused HTTP 422. The draft now uses a
valid severity value while preserving the complete source-severity summary.
The approved legacy template source remains unchanged.

New checks exercise exact source and filename matching, friendly aliases,
IPv4/IPv6 page reuse, deliberate incident/exposure scope choices, optional
sender titles, immutable explainer selection, explicit adoption, source-backed
EOL snippets, generic lifecycle fallback, CVE exclusion, duplicate-condition
merging without asset loss, and legacy layout preservation. Fresh synthetic
demo rows explicitly identify their source; the no-network demo test verifies
that the HTTP one-pager and PHP snippet are pinned for all five leads.

All **18 frontend module suites** pass, along with Python Ruff format/lint,
frontend Prettier/syntax, release identity, and architecture checks: 17
components, 219 owned modules, no dependency cycles. The 34 pinned Windows
dependency artifacts remain unchanged and are integrity-checked by the builders.

The tooling report intentionally uses skip-backend and skip-browser because
backend checks are recorded separately and interactive browser checks could
not run here. Its complete:false field is not represented as a complete browser
or workstation verification.

## Report workflow and document checks

Independent review passed ten distinct manual-import/offline-API-receipt
scenarios, with 12 successful complete certification runs including corrected
scope-choice reruns. Preview and freeze operations completed, citations resolved,
and already certified PDF hashes survived changes to the live explainer bank.
A mixed HTTP/incident case was additionally verified to reject freeze until the
explicit targeted-outreach narrative was selected. This did not broaden the
default critical-only import policy.

Focused EOL checks certify HTTP and Exchange reports with no CVEs. Final visual
review used actual production renderer subprocesses with external networking
blocked, a name-only sender and the appendix omitted. HTTP observations with
two PHP versions and two IPs produce one lifecycle card with both versions and
assets retained; Exchange produces its own lifecycle card. Both include
technical explanations and citations, preserve the row-date-plus-one narrative,
and retain pinned content after the live bank changes. The EOL-only footer is
neutral; it does not imply a published CVE or score. No CVE is inferred from an
old-looking version or an EOL tag.

The Information template collection was rendered from production layouts and
visually reviewed: **11 pages** (the common page and ten report-family pages),
with 28 clickable reference links. Text bounds, source links, page count,
justification and absence of mockup copy were checked. Additional synthetic
full-report reviews covered EOL HTTP, Exchange, RDP and Compromised Website.
These checks do not substitute for Microsoft Word or native Windows rendering.

## Upgrade and recovery

Unmodified 0.9.5 created an isolated synthetic workspace with three certified
reports and 15 frozen section reviews. Opening it with 0.9.6 and reopening its
backup in another folder both passed. Protected database rows, saved settings,
review status and report/source files remained unchanged. Each path verified
15 historical download hashes. The upgrade check was repeated after technical
snippet pinning was integrated. No user database was used.

## Distribution and limits

The source ZIP and Windows installer are built from allowlisted application
files and synthetic fixtures. Distribution evidence records the artifact hashes,
archive integrity, and extracted installer payload parity. The installer uses
the pinned official Python 3.14.10 x64 runtime and unchanged offline wheels.
It remains unsigned.

Interactive Chromium checks were attempted but blocked by this host's Unix
socket restriction: process_singleton_posix reported socket() failed with
Operation not permitted. No interactive browser pass is claimed for this build.
The final frontend module tests passed. Native Windows fresh installation,
retain-data upgrade, reset, desktop Microsoft Word rendering and live API
account behavior remain untested. The prior 0.9.5 endurance measurements are
historical and were not repeated for this release. HOME_VALIDATION.md contains
the workstation checklist.

The API work remains an offline receipt handoff; no live account connection,
automated pull, scan or notification delivery was performed. See
docs/RELEASE_096.md for report-family priorities and the four-snippet EOL scope.

TLP:AMBER
