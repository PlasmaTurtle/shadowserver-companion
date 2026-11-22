# Full build validation — November 21, 2026

**Status: full regression validation is not cleared.** The 0.12.0 Guided Setup
candidate retains two unexplained full-run runtime observations, tracked in
[ISS048](../../ISSUES.md#iss048-full-run-runtime-reliability). Candidate packaging
and artifact inspection do not turn those results into passing application
verification or complete [Windows acceptance](../../WINDOWS_ACCEPTANCE.md).

## Source and environment

Work ran in the actual Desktop repository. The working tree is uncommitted on
`efccc0a0f476bf83078b26694afa8fad0372047c`; that revision alone does not identify
the tested source. The external evidence bundle retains the original inventory,
each verification freeze and the final package-source manifest. Application and
browser source stayed unchanged after the successful nonbackend stages. Later
changes corrected test fixtures, verification prerequisites and documentation;
their focused checks and source deltas are retained.

Tools: Windows x64, Python 3.14.10 with the GIL enabled, Node 24.22.3, Playwright
1.62.1, Edge 158.0.4370.33, complete Poppler 26.09.0 and NSIS 3.13. Python runs
used `PYTHONUTF8=1`. No paid hosted CI ran. Workspaces and native probes were
synthetic; the user's installed application and operational records were not
replaced.

## Changes made during verification

- Fixed the native command-palette close/reopen race, with a deterministic browser
  reproduction and unchanged original search/focus/privacy assertions. The
  functional outcome belongs to
  [UI ISS047](../../../modules/ui/docs/ISSUES.md#iss047-command-palette-reopen-lifecycle).
- Added maintained Library browser coverage for explainer creation, two-window
  revision conflicts, retained drafts, comparison/rebase, restore, archive, usage
  and Activity. A case's pinned wording and citations remain unchanged throughout.
- Replaced the historical API snapshot's 413-line exception transformation with a
  reviewed current contract covering 180 paths and 77 schemas. Independent review
  preserved historical routes/models and meaningful constraints; transaction and
  stale-draft checks remain unchanged.
- Removed obsolete intake mocks, updated scanner fixtures for the approved
  hostname fallback, and used current typed qualification inputs and a real
  lightweight Catalog in caller tests. Existing rejection, preservation and
  admission assertions remain; related-site and attribution-order controls were
  strengthened. These are verification repairs, not runtime policy changes.
- Corrected the offline upgrade harness to permit native loopback IPC while
  rejecting other destinations. Added early checks for the documented Poppler
  utilities so missing test tools fail before a long verification run.
- Corrected formatting and packaged guidance for Backup & recovery and optional
  NVD keys. Release identity, dependency locks, approved report text, fonts and
  bundled resource bytes were preserved.

## Recorded results

| Check | Actual result and scope |
| --- | --- |
| Standard nonbackend stages | Release identity, module boundaries, formatting/lint, frontend syntax, all portable suites and all 17 routine browser scripts passed |
| Complete unsharded backend sweep | 3,738 collected: 3,702 passed, 14 failed, 22 skipped and 196 subtests passed in 2,118.24 seconds |
| Corrections after that sweep | Thirteen failures were stale fixtures; 69 complete website-evidence/qualification caller checks and 61 complete update-admission/update/lifecycle checks passed after correction |
| Remaining backend observation | One certification returned an SVG-resource integrity error; its cause is unresolved |
| Final diagnostic full-run attempt | No assertion failures before a native access violation at about 68%; process exit `0xC0000005`, without a completed JUnit result |
| Security gate | 476 passed, 10 skipped, 78 subtests; overlaps backend coverage |
| Dependency audit | 35 approved runtime wheels verified; 34 public Python packages and the npm lock reported no known advisories |
| Application upgrade and restore | Immutable schema-20 baseline to schema 23 preserved 3 historical reports, 15 validation records, 53 protected files and 15 legacy downloads |
| Isolated native bootstrap | All 8 cases passed; owned processes stopped and the working-record sentinel remained unchanged |

The 22 full-sweep skips comprise 16 Windows symlink-privilege cases, two compiler
cases without NSIS on that run's PATH, one Linux TCP case, one non-Windows error
case, an optional LibreOffice round-trip and a process-lifetime case whose native
Windows acceptance is separate. NSIS evidence comes from the explicit bootstrap
and candidate-build commands and their reports; it does not relabel skipped cases
as passes.

The original verifier stopped at a stale 16-script inventory assertion after
running all 17 browser scripts successfully. Its report remains failed. The
corrected inventory file passed all nine tests and 19 subtests. A subsequent
diagnostic backend attempt was intentionally stopped when the default Poppler
folder proved to lack `pdftotext` and `pdffonts`; the complete installed toolset
resolved those rendering-test failures without changing assertions.

The completed sweep above used the complete toolset. Its 13 stale-fixture
failures were corrected afterward. The later full run used an external,
failure-only diagnostic wrapper: it calls the original renderer, records an
SVG-integrity exception if raised and rethrows it unchanged. It does not suppress
checks, patch successful output or change native child commands. The one captured
exception before the crash belongs to an intentional corrupt-resource test that
passed. The crash prevented a complete suite result; it is not a successful rerun.

An isolated recovery case, its whole five-test file and a verified copy of the
exact failed workspace all passed. A bounded probe completed 100 app construction,
normal cleanup and garbage-collection cycles under Python's debug allocator.
Another completed 20 inline certifications on fresh verified copies of the failed
workspace, with normal cleanup, garbage collection and every integrity check active.
These results narrow the investigation; they do not establish a fix. Windows
recorded the native fault in `python314.dll`. No causal link between that crash
and the earlier SVG error has been established, and no speculative runtime change
or weakened integrity check was introduced.

The upgrade baseline is an earlier 0.12.0 candidate source distribution, not the
accepted 0.9.96 Windows release. Browser evidence includes a fresh catalog import
and exact scoped result counts, superseding the earlier Library batch's
retained-fixture-only integration limit. A full live multi-year provider import,
lost pre-history explainer wording and native release acceptance remain outside
this evidence.

## Commands and candidate artifacts

```text
python tools/verify.py --check-timeout 4500 --report <evidence>/verification-complete.json
python -m pytest -v --junitxml <evidence>/backend-accepted.xml
python <evidence>/run_backend_diagnostic.py
python modules/workspace/tools/verify_upgrade.py --baseline <immutable-schema-20-source> --current . --output <new-evidence-directory>
python tools/windows_installer/verify_bootstrap.py --output <new-evidence-directory> --makensis <NSIS-3.13> --python-home <Python-3.14.10-tools>
python tools/build_release.py <candidate-source-zip>
python tools/windows_installer/build.py --offline --build-dir <fresh-verified-cache> --makensis <NSIS-3.13> --output <candidate-installer>
```

The candidate destination is `dist/full-build-20261121/`. Its adjacent validation
record distinguishes application-test status from artifact-inspection status.
`artifact-verification.json` owns exact ZIP/installer hashes and checks source and
payload inventories, CRCs, extracted installer bytes, dependency/bootstrap identity,
privacy exclusions, documentation links, extracted-source imports and the actual
embedded runtime's offline self-test. Refer to that result before distributing
these exact artifacts; this document is not a substitute for a passing artifact
report.

The installer remains an unsigned candidate with no home confirmation. Extraction,
compilation and synthetic native checks do not accept the graphical installer or
uninstaller, real credentials, Word or display scaling. The actual installer is
not executed against the user's profile during this inspection.

## Evidence retention

The Codex task workspace's `validation/full-build-20261121/` retains original
failures, focused corrections, independent reviews, source hashes, full logs,
JUnit results where available, browser artifacts, advisory reports, upgrade and
native-bootstrap evidence, the preserved failed synthetic workspace, Windows
crash records and artifact-inspection results. Operational logs and diagnostic
wrappers remain outside maintained source and are not shipped. This record and
maintained tests are included in the source distribution.
