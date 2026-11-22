# Module reorganization validation

This record covers source relocation into the eleven named module folders. It
does not grant release approval or assert native installer acceptance.

## Baseline and scope

- Downloaded source version: 0.12.0, Guided Setup release candidate.
- Local baseline: `efccc0a0f476bf83078b26694afa8fad0372047c`.
- The downloaded source is preserved by that local Git baseline. The module
  reorganization is an uncommitted working-tree change after the baseline; the
  continued availability of the original Downloads folder is not assumed.
- Scope: source/resource/test ownership, imports, filesystem and browser asset
  paths, test discovery, architecture inventory, packaging, and developer docs.
- Database schema versions, operational data, credentials, approved wording,
  release identity, and acceptance records are outside this relocation's scope.

## Environment and baseline evidence

Baseline environment captured on 2026-11-18 UTC; work resumed on 2026-11-20.

| Item | Recorded value |
| --- | --- |
| Operating system | Windows 10, build 19045 |
| Python | 3.14.10, isolated repository `.venv` |
| Node.js / npm | 24.22.3 / 11.19.1 |
| Browser tooling | Playwright 1.62.1; Chromium and Headless Shell 151.0.7922.34, build 1234 |
| PDF tooling | Poppler 26.09.0, including `pdftotext`, `pdftoppm`, `pdffonts`, `pdfinfo` |
| Runtime/development dependencies | Existing project pins; Attribution 0.2.6 installed editable |

| Baseline command | Scope | Result |
| --- | --- | --- |
| `npm test` | Existing registered frontend DOM suites | Passed all 63 suites |
| `python -m pytest --collect-only -q` | Backend and Attribution test discovery | 3,059 tests collected in 13.42 seconds; no collection errors |

The backend baseline above is collection only, not an executed backend regression
pass. It reported one existing Starlette/httpx deprecation warning. Local logs
are retained in the outer workspace `validation/` directory as
`baseline-frontend.log`, `baseline-backend-collection.log`, and `environment.json`.
These local paths are not release assets.

## Reorganized working-tree verification

Evidence below covers the uncommitted module-reorganization working tree after
`efccc0a`, with checks performed on 2026-11-20/21 UTC. The complete backend run
finished and is not fully green: three website-capture expectation mismatches
remain after the relocation-specific corrections. All three reproduce in a fresh,
unmodified baseline snapshot. Baseline results above are separate from these
current-layout checks.

| Check | Current result | Local evidence |
| --- | --- | --- |
| Frontend module contracts | All 63 registered DOM suites passed | `frontend-modules.log` |
| Frontend syntax and formatting | `npm run lint` and Prettier check passed | `frontend-syntax.log`, `frontend-format.log` |
| Python formatting and lint | Ruff format/check passed for 577 Python files | Final source-check output; formatting logs retained in `validation/` |
| Ownership and import graph | 417 source files; eleven modules plus the project node; zero cycles; all 17 existing boundary rules retained | Generated `docs/program-map.json` and architecture checks |
| Browser workflows | All six registered suites passed across the core, Observatory, and setup groups with `PYTHONUTF8=1` | Reports detailed below |
| Static-asset exposure and favicon | 11 tests passed | `module-assets.log` |
| Direct browser-fixture entry points | Ten `--help` commands passed | `fixture-entrypoints.log` |
| Maintenance metadata checks | Seven tests passed after path/ownership expectation corrections | `modular-maintenance-recheck.log` |
| Dependency and preserved-source integrity | Approved template and vendored source bytes preserved; historical Shadowserver patches retain their original target through `patch_location` | Dependency integrity reports and package proof below |
| Complete backend regression | Raw run: 14 failed, 3,048 passed, 9 skipped; 159 subtests passed. Targeted recheck: 3 failed, 2 passed, 9 skipped; details below | `modular-backend-utf8.log`, `modular-backend.xml`, `modular-failures-recheck.log`, `modular-failures-recheck.xml` |

Local log names in this record are relative to the outer workspace `validation/`
directory unless a repository path is shown. Logs are not release assets.

### Browser evidence and corrected fixture setup

The four core checks passed in `modular-browser-utf8.json`:

- `modules/workspace/tests/test_local_session_browser_072.cjs`
- `modules/ui/tests/test_frontend_browser_070.cjs`
- `modules/ui/tests/test_frontend_accessibility_070.cjs`
- `modules/workspace/tests/test_frontend_workspace_080.cjs`

That combined UTF-8 browser attempt then stopped because the relocated Observatory
fixture could not import the shared `test_workbench` helper. Its report correctly
remains failed/incomplete. After correcting the fixture import path,
`modular-browser-observatory.json` and `modular-browser-setup.json` each passed their
registered suite. Together these reports cover all six browser suites; they do
not constitute a successful single full-verifier report or native installation
acceptance.

Earlier attempts in the default Windows text-encoding environment exposed an
existing implicit resource-decoding issue with cp1252. Development checks use
`PYTHONUTF8=1`, matching the existing CI configuration. Making each UTF-8 repository
resource read explicit is a separate targeted follow-up; this source relocation
does not claim to fix that pre-existing encoding behavior. See the PowerShell
setup in [Development](../../DEVELOPMENT.md#windows-ide-setup).

### Backend results, baseline failures, and filesystem capability

The complete unsharded backend run finished with this exact pytest summary:

```text
14 failed, 3048 passed, 9 skipped, 1 warning, 159 subtests passed in 1565.24s (0:26:05)
```

Evidence is in `modular-backend-utf8.log` and `modular-backend.xml`. Its 14 failures
comprised nine symlink-fixture capability failures, two stale maintenance metadata
expectations, and the three website-capture mismatches described below. The
maintenance checks were corrected and seven focused checks passed. The final
`--lf` recheck recorded:

```text
3 failed, 2 passed, 9 skipped, 29 deselected, 1 warning in 9.70s
```

That recheck is retained in `modular-failures-recheck.log` and
`modular-failures-recheck.xml`. The two corrected maintenance cases passed; all
nine previously failing symlink fixtures explicitly skipped for WinError 1314.
These are separate observed runs. Their counts are not combined into an invented
final full-suite total or reported as a complete regression pass. Collection
reported 3,070 tests; the complete-run summary also reports subtests, so the raw
pytest accounting is retained exactly rather than normalized by this document.

The remaining failures are:

- `modules/investigations/tests/test_website_capture_0985.py::test_truthful_page_classification[info3-200-True-2-partial]`
- `modules/investigations/tests/test_website_browser_0985.py::test_capture_driver_fulfills_public_page_and_cleans_process[blocked]`
- `modules/investigations/tests/test_website_browser_0985.py::test_capture_driver_fulfills_public_page_and_cleans_process[unavailable]`

A fresh `git archive` of `efccc0a0f476bf83078b26694afa8fad0372047c`, with no source
edits, reproduced exactly those three failures across the original two selectors
and all their parameter cases: **3 failed, 5 passed**. The command, environment,
log, and AST comparisons are recorded in `baseline-capture-tests.json` and
`baseline-capture-tests.log`. The capture implementation and affected assertions
were not changed to make this reorganization pass.

The classification case supplies a blocked-request count to the boolean
`document_failed` argument, producing `load_failed` where the test expects
`partial`. The other two cases expect a CDP `Fetch.failRequest` command even though
the existing preflight content scan rejects the input before a browser/CDP peer
exists. A separate Investigations refactor should align the classifier cases with
that parameter and split preflight rejection from rejection after browser startup.
Preserve fail-closed scanning and review partial-page classification independently;
do not change security behavior simply to satisfy these expectations.

Thirteen symlink-dependent tests use the shared `create_test_symlink` fixture
helper. It skips only when Windows raises WinError 1314 while creating the fixture;
other errors still fail. Application security checks and assertions are unchanged.
These security cases are unexecuted on a host without symlink-creation capability,
not passes. The full run's nine original skips included four already guarded
symlink fixtures plus environment-specific checks: NSIS compilation, Linux TCP
restart behavior, a non-Windows credential-adapter case, optional LibreOffice
round-trip, and the POSIX orphan watchdog. The nine additional capability skips in
the final recheck are reported separately above. `symlink-fixture-update.json`
identifies those nine updated fixtures.

### Source inventory and preserved bytes

`modular-source-inventory.json` accounts for 934 original files. The generated
archive output `release-manifest.json` is the one intentionally removed original
file; it is recreated by packaging. The immutable subset contains 105 files
verified byte-identical to the baseline.

The recorded source/configuration/asset inventory digest is:

```text
7c3df01921751e70a35bb968bdb9332b642611319ce7382d02c423703fadc46f
```

One-time move maps and migration scripts are retained outside the repository in
`validation/migration-records/`. They are audit material, not runtime dependencies
or distributed application code.

### Source archive and copied payload

The local packaging proof passed. Its exact commands, exit codes, artifact hash,
and limitations are recorded in
`packaging-20261121T040927Z/final-evidence.json`.

| Artifact/check | Result |
| --- | --- |
| Source archive | 1,041 ZIP members; 1,040 manifest hashes checked |
| Archive SHA-256 | `0863e8c6fa8a16bbf8124541dc24377c02fbd653bab0c4dc16a2d0b783fb4a8e` |
| Copied installed payload | 581 files |
| Extracted archive architecture and dependency checks | Passed |
| Extracted app, Excel intake, and Attribution CLI `--help` | All three passed |
| Payload import origins | Confirmed application and Attribution imports resolve inside the packaged payload |
| Approved template bytes | Exact preservation verified; SHA-256 `fcb2d2143887b7a775c4b81845d4ec1160cebac94ee679ca2eb38a43c5c4570b` |
| Payload offline runtime check | Direct, noninteractive `desktop.runtime_self_test()` passed |

The first desktop `--self-test` harness attempt reached its Windows completion
dialog and was stopped; the direct noninteractive function call supplies the
completed runtime evidence. Packaging used development Python 3.14.10. It did not
compile NSIS, install/uninstall the app, publish an artifact, or upgrade real data.
The archive hash identifies that packaging checkpoint; subsequent documentation
and test-only updates may change checkout bytes without changing that archive.

### Setup and documentation

The editable library was reinstalled successfully on 2026-11-20 using:

```text
.venv/Scripts/python.exe -m pip install --no-deps -e modules/attribution/components/engine
```

The cached Playwright executable was present. Documentation review checked 86
Markdown files for UTF-8 readability, nonempty content, and local link targets;
no missing targets remained at that check. Historical review prose remains intact.
One database-audit document has rebased link destinations with an explicit
historical-source note. The filesystem check did not validate heading anchors or
external availability.

No hosted GitHub run was used for this evidence; the paid hosted budget remains
zero. Real-data upgrades, native installation/uninstallation, native document
layout, and the exact-version Windows acceptance checklist remain separate work
unless explicitly exercised and recorded.
