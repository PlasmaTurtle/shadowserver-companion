# Validation · Shadowserver Companion 0.9.5 · UNSTABLE

Initial functional validation was executed November 8, 2026 (America/New_York),
with final records also dated November 9 UTC. A subsequent UI refinement pass
has separate results below. This document describes synthetic Linux checks.
Version 0.8.0 remains the last user-accepted stable release; no native Windows,
live-business or live Shadowserver API acceptance is inferred.

## Initial 0.9.5 automated regression

All **1,050 collected backend tests** were covered by five broad shards and final
focused reruns. The broad run covered 1,036 nodes: 1,033 passed and three failures
were corrected. Two checks needed to allow the separately pinned addressee
correction while continuing to verify all other approved template source bytes;
one exposed SQL outside a repository and was fixed in the implementation.
The final focused run passed 111 tests, including those three and all 0.9.5
regressions. Fourteen additional tests were added after the broad collection.
This is reconciled coverage, not one uninterrupted 1,050-test run. The broad run
also passed 29 subtests. Original failure logs remain in the evidence package
alongside passing reruns so their resolution can be inspected.

All **15 frontend module suites**, four established real-browser suites and
11 new browser check groups (five contact, six workflow) passed. The new browser
runs recorded zero page errors and zero external requests. They exercised the
real local application against synthetic website responses. Python Ruff
format/lint, frontend Prettier/syntax, release identity and program architecture
checks passed: 17 components, 210 owned modules, no dependency cycles.

`final-tooling.json` intentionally records backend/browser checks as skipped:
those checks were executed separately and are reconciled in `final-validation.json`.
The toolkit's `complete: false` is not represented as a single full verification.

These results describe the initial 0.9.5 implementation. The complete backend
coverage and endurance run were not repeated for the subsequent UI refinement
pass; its frontend/browser checks are documented separately below.

## Subsequent UI refinement

This pass changes static JavaScript, CSS, HTML and frontend tests. It does not
change Python business logic, schemas or the document-generation implementation.
All **18 frontend VM suites** and **22 targeted backend tests** passed. These are
separate checks, not an additional full-backend or report-endurance run.

A Linux Chromium interaction run passed seven groups covering
startup/appearance persistence through actual settings PUT requests, named
dialog focus and Escape return, keyboard tabs, unsaved-edit navigation guards,
the mobile navigation drawer and entity/case deep links. The workflow review
also checked the Workspace priority queue (labeled Today in this build), Entities,
Contact and Activity at desktop and mobile sizes with synthetic local data. These runs recorded no page errors or external
requests.

The final layout run passed **66 route/viewport checks**: 11 views at widths of
320, 390, 720, 1,024, 1,280 and 1,440 CSS pixels. Automated geometry scans found
no document or element overflow and no undersized visible controls under the
scan's criteria; the run recorded no page errors. Eight contact browser groups
also passed against the final CSS. The combined runner passed all six stages:
five browser suites plus the 66-view layout capture. A workspace-control test
was adjusted to open the new deletion disclosure before using its button. The
first-launch appearance test runs first on the fresh fixture, before other
suites save appearance settings. Capture labels that refer to zoom describe
reduced viewport simulation, not actual browser zoom.

Native Windows interaction, screen-reader use and actual browser zoom remain
untested. The review used [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) and the
[WAI-ARIA APG modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)
as design references. This is not an accessibility conformance audit or a claim
of WCAG conformance. Exact-build checks remain in `HOME_VALIDATION.md`.

## Initial report endurance and storage

The clean production-subprocess run passed **50 preview/reopen/closing-freeze
cycles**, two application restarts and final certification with 60 retained
validation records. Earlier certified bytes remained unchanged. Runtime source
and inventory remained unchanged throughout that run. Within the initial
backend validation sequence, the only subsequent runtime edit was formatting
in `workbench/routes/reports.py`; parsed AST equivalence and before/after hashes
are recorded in `final-format-equivalence.json`. The later UI changes described
above are outside that source comparison; the endurance run was not repeated
for them.

| Measurement | Synthetic Linux result |
| --- | ---: |
| Preview p95 | 2.178 seconds |
| Closing-section freeze p95 | 3.934 seconds |
| Case read p95 | 0.951 seconds |
| Whole endurance run | 448.292 seconds |
| Peak sampled parent + renderer RSS | 562,274,304 bytes |
| Final snapshot with full validation history | 26,283,006 bytes |

Summed RSS can double-count shared pages. These measurements describe this
fixture and host; they do not predict all Windows workloads. Case API output
still includes about 2.6 MB of legacy SVG material, leaving room for optimization.

Three retained synthetic snapshots became **89.52–90.12% smaller**, with exact
logical round trips and unchanged original files. Fifteen section-validation
models became **65.25% smaller** in the serialization measurement. New records
use the compact envelope; historical certified files are never rewritten merely
to achieve these savings. Encoder and decoder share the 128 MiB unique-string,
2 GiB logical-string and depth limits; renderer exchange is bounded at 256 MiB.

## Upgrade and recovery

Unmodified **0.8.0 and 0.9.0** each created an isolated synthetic workspace with
three certified reports, 15 validations and 341 protected files. Direct opening
with 0.9.5/schema 9 and reopening a backup restored into a different directory
both passed for each baseline. Protected database rows, saved settings, frozen
review displays and report/source bytes were preserved. Each path verified 15
historical download hashes. Clean acceptance fixtures ran in isolated temporary
directories and were removed after their result metadata was retained.

Backup tests additionally cover checksums, reference integrity, compact/legacy
snapshot decoding, malformed archives, symmetric export/restore limits,
verified restore points, damaged-current-data recovery, startup migrations,
link/junction protection and data-operation exclusion during active report work.

## Distribution and acceptance limits

The source and installer builders enforce release identity, pinned dependencies,
architecture and program-file allowlists. Separate distribution evidence records
actual artifact hashes, extracted payload parity, compile results and source
checks. The Windows x64 installer uses pinned Python 3.14.10; automated backend
tests used Linux Python 3.14.9. The 34 pinned dependency artifacts are unchanged.

The installer is **unsigned**. Native Windows fresh install, retain-data upgrade,
reset, long-running report generation and desktop Microsoft Word acceptance are
still pending, as are screen-reader and actual browser-zoom checks. Live business
discovery and live API account behavior were not tested. `HOME_VALIDATION.md`
gives the workstation checklist. `RELEASE.json` remains unstable with no 0.9.5
workstation confirmation.

See `docs/RELEASE_095.md` for shipped behavior and explicitly deferred work.
Historical 0.9.0 and 0.8.0 validation notes are preserved in
`docs/VALIDATION_090.md`; their counts and observations are historical.

TLP:AMBER
