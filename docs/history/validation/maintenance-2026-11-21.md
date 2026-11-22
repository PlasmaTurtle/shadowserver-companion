# Maintenance validation — November 21, 2026

This record covers the coordinated maintenance batch on the reorganized Eclipse
0.12.0 candidate. It records checks for this source state; the canonical
[issue register](../../ISSUES.md) and module trackers own current status and
functional outcomes. [Windows acceptance](../../WINDOWS_ACCEPTANCE.md) remains
a separate exact-artifact release gate.

## Source and environment

The working tree is uncommitted on
`efccc0a0f476bf83078b26694afa8fad0372047c`. The Git revision alone does not identify
this batch: the saved baseline and final file hashes in the task evidence bundle
identify the actual files. The baseline already contained the module/documentation
reorganization and resolved UI rendering-deadline extraction.

Checks run locally on Windows with Python 3.14.10, Node 24.22.3, the locked
Playwright 1.62.1/Prettier 3.6.2 toolset, Poppler 26.09.0 and portable NSIS 3.13.
The full verifier uses `PYTHONUTF8=1`; explicit encoding checks separately use
`PYTHONUTF8=0`. Attribution 0.2.7 is rebuilt from the reviewed engine source with
its wheel hash updated in both distribution inventories. Other runtime and
development dependency pins are unchanged. No paid hosted CI is used.

All application data and native fault probes are synthetic. Native probes use
isolated directories and uniquely named process/task identities. They do not
replace the user's installed app, run live provider credentials, publish an
update or accept native Word/display behavior.

## Combined validation

The initial standard verifier passed release identity, module boundaries, Python
and frontend format/lint, the portable frontend runner and all 16 routine browser
scripts. Its backend stopped at a historical NSIS source assertion after 207
passes, five skips and 11 subtests. The test still expected forward-slash paths,
which the native Windows compiler had rejected. Related shortcut/cleanup ordering
assertions were updated to preserve their safety checks around the corrected
installer. The complete affected selection then passed 79 tests with four skips.

The full unsharded backend rerun passed: **3,277 tests and 207 subtests**, with
**17 skips**, one existing Starlette/httpx deprecation warning and no failures,
in **1,667.05 seconds**. It collected 3,294 tests. The 17 skips comprise 13 Windows
symlink-privilege cases, one Linux TCP regression, one non-Windows error case,
one optional LibreOffice round-trip and one POSIX parent-watchdog case. Native
Windows parent/child lifetime is separately exercised by the bootstrap probes.

The initial failed verifier report is retained unchanged. Its passed frontend and
browser checks remain applicable: only two Python test files and documentation
changed afterward, with no production change. Updated test lint/format checks
passed. Issue-level checks and before/after evidence remain at the canonical
issue entries; passing an individual test is not the batch completion claim.

The recorded commands use the configured Python environment with Poppler, NSIS and
the existing test Chromium available:

```text
python tools/verify.py --check-timeout 4500 --report verification.json
python -m pytest -v --junitxml backend-final.xml
python tools/windows_installer/build.py --offline --build-dir <verified-cache> --makensis <portable-makensis> --output <candidate-installer>
python tools/build_release.py <candidate-source-zip>
```

The browser catalog contains routine, focused and deliberate manual checks.
The standard verifier executes all routine groups; additional focused/manual
evidence is recorded separately and does not change its completeness semantics.

The combined evidence covers every standard check, using the successful complete
backend rerun and unchanged frontend/browser results; it is not presented as one
successful verifier invocation. `combined-validation.json` records that
reconciliation and the individual skip reasons. Four additional focused browser
groups and the package-shell/evidence-reader checks also passed. Their fixture
generation, manual scope and results remain separate from routine coverage.

The candidate installer and source ZIP are built into
`dist/maintenance-2026-11-21/`. Their adjacent verification record owns exact
artifact hashes and checks the extracted installer bytes, source/payload
inventories, documentation links and packaged runtime imports. Generated build
outputs are excluded from source distributions. This does not promote the
candidate or establish complete Windows release acceptance.

## Native and scope evidence

Nine native launcher cases and seven real Task Scheduler integration cases pass.
They cover startup exclusion before Python, inherited process lifetime, partial
installation refusal, task migration and interrupted-install repair. A separate
native cleanup probe verifies locked-shortcut failure, successful retry and
already-absent registration. All owned synthetic tasks/processes are removed and
retained sentinels are unchanged. These are scoped probes; the integration emulates
NSIS payload copy/delete and does not accept the full installer wizard.

Independent scope review found no unexplained production change or loss of
original Python tests. The two retired Contacts browser scripts have explicit
replacement coverage. All 109 protected baseline files remain byte-identical,
including approved wording, fonts, schemas, retained historical documents and
unchanged dependency/release pins. The internal engine wheel replacement is
deliberate and separately verified. Module guides own interface/lifecycle
contracts; canonical trackers distinguish functional gains, maintenance debt,
the read-route audit and deferred abstractions.

## Evidence retention

The Codex task workspace retains `validation/maintenance-batch-02/`: immutable
baseline archives, issue source manifests, before/after probes, commands, JUnit
logs, browser artifacts, native-source snapshots and artifact hash reports.
This operational bundle is outside the repository and is not shipped in the
application. The source ZIP retains maintained tests and this concise record.

Native bootstrap and Task Scheduler results establish only the behavior actually
exercised. Compilation, synthetic native probes and browser verification cannot
complete ISS014's Word, display-scaling, real credential and home-confirmation
steps. Deferred abstractions remain deferred where no concrete consumer or
transactional improvement justifies their cost.
