# Shadowserver Eclipse 0.10.1 Analyst Workflow validation

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

November 13, 2026. Unsigned release candidate; native Windows acceptance is not
claimed. The recorded earlier Windows baseline remains 0.9.96. Main schema is 16.

## Executed checks

| Check | Result |
|---|---|
| Complete backend/Attribution regression | **2814 passed, 1 skipped, 3 failed; 151 subtests passed**, 899.71s. All three failures were subsequently corrected and rerun as described below; this is not an all-pass full-run claim. |
| Final artifact guard and adjacent paths | **38 passed + 3 passed** after the guard: row/package binding, modern/legacy identities, case workflows, backup/restore, recovery, availability and contact handoff. |
| Final historical compatibility correction | **34 passed** after the final fix, covering both original historical-editor failures, the corrected recipient-scope assertion, snapshot binding/digest/path rejection and full-package integrity boundaries. |
| Portable frontend | **57 registered suites passed**, including actual module/controller, DOM/Canvas, stale response, scope, outreach and sender tests. Final tooling reran them after formatting. |
| Security gate | **383 passed and 78 subtests passed**, plus exact dependency verification and advisory scan. These overlap the complete backend suite and are not additional unique tests. |
| Dependency integrity/advisories | All **34 pinned wheel artifacts** and vendored source checks passed; **33 public Python packages**, zero reported advisories. Public package names/versions only; no case data sent. |
| Cohesion/tooling | Python lint/format, frontend format/syntax, release identity and component boundaries pass. Generated map: **340 owned modules, 21 components, no cycles or boundary errors**. |
| Protected content | `workbench/approved_template.py` bytes unchanged from 0.10.0 baseline. Existing certified files retained unchanged. |

The final independent review found that a saved modern analyst report could accept
an identityless legacy manifest. The last guard now requires full identity based
on the saved certification origin while retaining genuine legacy compatibility.
The complete suite also exposed two historical-editor regressions caused by
requiring rendered files to inspect an independently valid snapshot. A separate
snapshot reader now retains strict identity, safe-path and digest checks while
full delivery/export still requires the complete package. The third failure was
an obsolete four-recipient-row assertion: the corrected test checks three included
rows, all four retained source rows, and the explicit private-row exclusion.
All three original failures and added boundary checks passed in the final
34-test correction run. The full run began before these final changes;
it is reported with those later checks rather than represented as an all-pass
full-suite execution of the final tree.

The backend skip is the environment's default-path NSIS availability test; the
release installer is separately compiled with the explicitly located compiler and
its extracted payload verified. Existing Starlette/httpx deprecation and Node VM
module warnings are recorded, not suppressed. No runtime dependency upgrade is
part of this release. Known-advisory checks do not establish native-code, CPython,
AMSI, FIPS or unlimited security coverage.

## Actual synthetic analyst day

The final authenticated local HTTP replay made **163 requests**, with **six expected
422/409 rejections and zero unexpected statuses**. It exercised initial import,
duplicate suppression, saved-profile and latest-report map locations, private-IP
scope exclusion, partial frozen-section reopening, sender identity, contact research,
saved outreach, stale revisions, copy guards, restart, certification, sent versus
delivered outcomes, bounce/no-answer/hold, preview, closure, restore and later intake.
External providers and case data were synthetic. No real outreach was sent and no
remediation was independently verified.

Two notifications were certified through production HTTP: Harbor 10 pages and
Ridgeview EOL 9 pages; both closing preview and final closure were one page. Every
page was read. Recipient PDF/DOCX omit the excluded private row; the internal reader
retains its original source, reason, analyst and timestamp. Recipient archives
contain PDF + manifest; archived PDFs match their certified files. Eight notification
layout variants, long/short closing variants and both packaged examples were rendered
and compared. DOCX was independently rendered with **LibreOffice**, not Microsoft Word.
No notification element exceeded its page bounds; internal links and raw appendix
record counts were preserved. Details are in `docs/history/design/ANALYST_WORKFLOW_0101.md`.

## Database, upgrade and recovery

- Read-only integrity/foreign-key/ownership audits passed on fresh, restored,
  upgraded schema-16 and retained schema-15 synthetic databases; their bytes were
  unchanged by inspection.
- The schema 15→16 upgrade preserved case rows and **167 retained files** exactly.
- The workday's staged restore and restart preserved five compared tables and
  **88 protected files**; later intake did not change those historical files.
- Following the database fixes and analyst-origin identity guard, a fresh current backup
  restored **three cases, all 42 main tables and 90 protected files** exactly.
  Both historical PDFs downloaded with original hashes; two restored report
  packages and one closure validated; integrity/FK checks passed. The test bridge
  was stopped cleanly. A separate final HTTP smoke after the historical-view correction verified both historical editors, both PDF hashes and Workspace.
- Confirmed fixes cover consistent case snapshots, linear scope counts, excluded
  CVE delivery coverage, artifact identity/digest binding, captured-source projection
  binding, shared risk freshness and future-schema read gates.
- The condition-specific membership admission defect remains **OPEN**. A measurement
  approved for one CVE can inflate another CVE's approved history after later approval.
  Its deliberately failing reproduction remains outside release test paths and is
  included as known-defect evidence, not counted as a passing test. The conservative
  migration proposal is in `docs/history/reviews/DATABASE_AUDIT_0101.md` and the companion audit.

The query audit measured 500/1,000/2,500-row scopes, 1k/5k cases, up to 50k observations
and 100k source revisions. It found valid existing indexes and WAL behavior, plus
follow-up work for planner statistics, bulk queue projections, direct Observatory
details and narrower invalidation. Wall times are shared-machine measurements, not
capacity guarantees. SQLite replacement is not justified by the evidence.

## Packaging and acceptance limits

Source and installer builders enforce release identity, dependencies and current
component-map integrity. The companion package evidence records archive CRC, all
source-manifest hashes, extracted installer payload hashes, sizes and SHA-256.
Successful compilation/extraction is not Windows installation or execution.

Python validation runtime: **3.14.10, SQLite 3.53.1, Linux x86-64**. Windows desktop
startup, actual browser interaction/DPI/keyboard/accessibility, native AMSI and
Credential Manager, scheduling, retained-data upgrade/uninstall and Microsoft Word
rendering remain exact-version acceptance work in `HOME_VALIDATION.md`. Browser
access to the isolated test server was unavailable; portable production-controller
replay and authenticated HTTP testing do not establish visual browser acceptance.

The existing entity map remains entity-based. Complete saved city/state takes
precedence; incomplete profiles use the newest associated IP/hostname report in the
selected scope, with provenance. Approximate regional Census placement is not street
geocoding, nationwide coverage or historical address reconstruction.

No operational workspace was audited, no GitHub push occurred, and no historical
report was rewritten. Stable promotion requires acceptance of this exact version.

