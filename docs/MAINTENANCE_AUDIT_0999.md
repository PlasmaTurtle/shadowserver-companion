# Shadowserver Eclipse Maintenance Audit

November 13, 2026 · Staff Principal Engineer review · 0.9.99 Maintenance Review release candidate

## Executive summary

**Structural health: 6 out of 10 for the recovered checkpoint.** This is an engineering judgment, not a statistical reliability score. The application has credible foundations: explicit component boundaries, transactional repositories, preserved evidence, immutable certification artifacts, hash-locked Windows dependencies, and extensive focused tests. The main weakness is the gap between those controls and end-to-end release confidence, followed by avoidable work on shared workflow paths. A framework rewrite or service decomposition would add risk without addressing the demonstrated problems.

The maintenance pass corrects specific build, validation, restore, dependency and interaction defects. It does not erase the remaining scaling and Windows acceptance gaps. The release remains a candidate. Stable promotion requires version-specific workstation evidence.

### Three risks most capable of undermining the product

1. **Incomplete source handoff, unreliable release evidence and untested native boundaries.** The recovered verifier could write success after an exceptional exit, and the cumulative installer source did not compile with NSIS. Both defects were reproduced and fixed. The connected GitHub main branch still contains only its initial VERSION file, so it cannot rebuild the current application or provide current source history. Native install/upgrade, AMSI, scheduled handoff, rendering and retained-data uninstall remain acceptance work. See R1, R4 and Packaging.
2. **A growing workload can monopolize core workflows.** Queue search projects all eligible leads, report rendering holds the workspace writer lock, and intake materializes several full-size working sets. These are documented code paths, not measured production outages. See A2–A4. The bounded lead-selection query fix improves one immediate cost but does not solve all three.
3. **Recovery and cancellation need stronger hostile-input boundaries.** Closing snapshots lacked the report snapshot's decode preflight, artifact inventory verification allocated whole files, and bulk reference streams do not enforce a hard wall-clock deadline. Restore validation and streaming artifact hashing are corrected; the transport redesign remains open. See Security.

### Scope and provenance

The audit covers the five requested pillars: dependency and supply chain health; architecture and code quality; testing and reliability; developer experience and CI/CD; security and configuration hygiene. It evaluates operational friction and maintainability over the next 12–24 months.

The baseline was reconstructed from the delivered 0.9.98 Windows source archive and the November 13 cumulative Field source checkpoint. All 72 changed/new files matched the checkpoint's before/after SHA-256 manifest before integration. That checkpoint already contains pending attribution and NVD corrections. It was not treated as a finished installer. The separate Attribution/NVD checkpoint was retained for comparison, not applied a second time.

The application contains 242 Python modules under workbench, about 53,932 lines before the final bounded edits, and 43 frontend scripts. The ownership map now verifies 329 owned modules across 21 components with no declared import cycles. Largest/change-concentrated modules and the 72-file patch set guided review. **The connected GitHub default branch was checked read-only:** its only commit, 2103cfc36829e3014681299bf8a1285063702449, contains only VERSION (0.9.7). No current application commit history exists there, so size and patch membership remain churn proxies. That complete tree contains no workflow files; Actions reports zero runs and the branch reports no protection or required checks. Organization-level policy and other repositories were not audited. These findings come from repository evidence, not absence of .github in the release ZIP.

Locations are relative to the application root in the delivered source ZIP. Findings explicitly label original baseline locations where an edit shifted lines; other locations refer to the final reviewed tree. Tests use synthetic workspaces; no production case directory was opened. A passing test is evidence for its stated contract, not proof of universal safety.

## Prioritized remediation roadmap

| Window | Work | Acceptance criterion | Status |
|---|---|---|---|
| Immediate under 1 day | Fail-closed verifier and bounded child checks | Interrupt, unexpected exception and timeout cannot emit passed/complete | Implemented |
| Immediate under 1 day | Restore closing snapshot preflight and streamed inventory hashes | Malformed/oversized snapshots fail before startup recovery; artifact hashes stream and package metadata reads are capped | Implemented |
| Immediate under 1 day | Batch lead scope reads | 1,201 requested IDs use three selection queries while preserving order and assigned/missing ID semantics | Implemented |
| Immediate under 1 day | Bound shared frontend reads | Default GET/HEAD timeout, explicit long deadlines and mutation behavior preserved | Implemented |
| Immediate under 1 day | Source dependency consistency | Contradictory pins, directives and missing mandatory references fail before packaging | Implemented |
| Immediate under 1 day | Repair installer hooks and asset allowlist | NSIS compilation succeeds; approved favicon bytes survive source and installed packaging | Implemented |
| Tactical 1 to 5 days | Lock development and build tooling | Fresh Windows/Linux setup resolves the same qualified tools and build backend | Open |
| Tactical 1 to 5 days | Page queue results before projection | 1k/10k-entity fixtures project a bounded page with identical sort/search semantics | Open |
| Tactical 1 to 5 days | Absolute transport deadline and current browser acceptance profiles | Slow headers/body and cancellation meet a measured budget; each browser profile has explicit pass/fail/skip | Open |
| Tactical 1 to 5 days | Restore current source to Git and establish CI; qualify dependency patches | Verified source commit, required checks, controlled workflow permissions and release artifact provenance | Open |
| Strategic over 1 week | Snapshot then render outside writer lock | Concurrent edits cannot publish stale certification; failure injection preserves atomic recovery | Open |
| Strategic over 1 week | Stage and resume large intake in bounded batches | Measured peak memory and pause latency at 1k/50k/250k rows; atomic promotion | Open |
| Strategic over 1 week | Automated Windows upgrade and retained-data acceptance | Install, upgrade, restore, scheduling, native security and uninstall evidence tied to exact artifact hashes | Open |
| Strategic over 1 week | Extract Observatory request and paging state | Existing mount/destroy, selection and cancellation contracts pass through incremental extraction | Open |

Estimates are engineering planning ranges, not commitments or evidence that each architectural change fits this maintenance release.

## Detailed findings by pillar

The following sections preserve the evidence, impact, remediation and counterevidence for each finding. Cross-references avoid treating the same verifier defect as separate independent risks.


## Dependency, supply-chain, and developer-experience audit

Audit date: 2026-11-13. Baseline: delivered 0.9.98 source plus the hash-verified cumulative Field checkpoint. Source paths below are relative to the application root. A read-only GitHub inspection confirmed that the connected repository contains only the initial 0.9.7 VERSION file, not this application source; the current application audit therefore uses recovered release files and build tools. Final source references use the modified tree unless identified as baseline.

### Assessment

The dependency foundation is substantially better than an unpinned prototype: 34 wheel artifacts have SHA-256 locks, the standalone Attribution module is checked against the application's copies, and its bundled Python source is compared byte-for-byte. The fresh advisory run in `build/security-audit/dependencies.json`, checked 2026-11-13T19:02:34Z, covered all 33 public Python packages and returned zero advisories; the internal package is deliberately reviewed as source. This does not cover CPython, native codec vulnerabilities, npm development packages, or runtime exploitability.

There is no evidence of an end-of-life Python baseline or multiple-major framework lag. CPython 3.14 is supported through October 2030; the official release schedule places 3.14.11 on December 1, 2026. The pinned 3.14.10 is a current supported maintenance release, although conditional runtime advisories still need tracking. FastAPI has newer patch releases, not an established EOL condition.

### Findings

#### DEP-01 — Medium — Source requirements escaped the distribution integrity check — Fixed

**Location:** baseline `tools/check_dependencies.py:77-105`; source contract `requirements.txt:1-13`. Remediation now at `tools/check_dependencies.py:77-109`; regressions `tests/test_dependency_manifest_0999.py:16-64`.

**Evidence:** `verify()` previously checked Windows wheels/requirements, constraints, and attribution version/source, but never opened `requirements.txt`. Consequently, an altered direct requirement, extra package/index, dropped constraints reference, or switch away from local attribution could pass this gate. A conflicting direct pin can break a fresh source setup even while the Windows package passes integrity checks.

**Impact:** the documented development setup can diverge from the tested installer; maintainers discover that mismatch late, during environment creation or platform testing.

**Remediation applied:** verify each direct pin against the locked wheel inventory; require the constraints include and local Attribution source; reject duplicates, unpinned dependencies, unknown requirement directives and unexpected public copies of the internal package. No dependency versions changed. The parser intentionally accepts the repository's current simple format; adding markers/extras/includes requires an explicit checker update.

**Validation:** five new tests exercise positive and negative manifests; combined with existing dependency/security tests, 12 tests and 11 subtests pass on CPython 3.14.10. Offline lock integrity passes across all 34 wheels. Ruff lint and formatting checks pass.

**Limit:** this verifies existing direct requirements and mandatory references; it is not static import analysis and cannot prove that a removed direct dependency is no longer needed by application code.

#### DEP-02 — Medium — Development/build-tool resolution remains partly floating — Open

**Location:** `requirements-dev.txt:1-4`; `components/attribution/pyproject.toml:1-3`; `DEVELOPMENT.md:16-22,53-59`; `requirements-constraints.txt:1-34`.

**Evidence:** direct pytest/ruff versions are pinned, but their full dependency closure is not locked. Attribution's isolated build requirement is `setuptools>=77` with no upper bound or artifact hash. The documented `pip install -r requirements-dev.txt` therefore does not fully specify the development/build environment, even though application runtime versions are pinned.

**Impact:** a clean developer or future CI environment can obtain a different build backend/test dependency set without a repository change. Reproducing environment-specific failures becomes harder over the next 12–24 months.

**Remediation:** maintain a separate platform-appropriate development/tooling lock, including build backends and hashes; record the installer/build toolchain; regenerate deliberately and verify with a clean-environment job. Keep these dependencies out of the installed application. Estimate: 1–3 days to implement and qualify Windows/Linux setup.

**Counterevidence:** Windows runtime distribution already uses hash-locked wheels and `--no-index --require-hashes` (`tools/setup_environment.py:80-88`, `tools/windows_installer/build.py:251-278`). This finding is about development/build reproducibility, not an unlocked production package set.

#### DEP-03 — Medium, conditional — CPython advisories are outside the wheel audit — Tracked, not fixed

**Location:** `tools/windows_installer/runtime-lock.json:2-6`; `DEPENDENCIES.md:39-50`; `tools/check_dependencies.py:140-189,209`.

**Evidence:** runtime is pinned to CPython 3.14.10. Python's official advisory identifies CVE-2026-119170 as a 3.14.10 regression affecting users of OpenSSL FIPS mode only. CVE-2026-116566 concerns embedded NULs passed to address resolution. The project already documents both; this audit does not establish FIPS use or an application path bypassing its NUL guards.

**Impact:** a passing Python-package advisory result must not be promoted to an assurance about the interpreter/native runtime or federal workstation compliance. This is a release-acceptance constraint, not evidence of a currently exploitable application defect.

**Remediation:** retain explicit runtime advisory review alongside each release; qualify the next official fixed Windows runtime when published; keep FIPS/compliance claims out of release metadata until actually established. Do not downgrade the interpreter merely to avoid one conditional advisory. Version 3.14.11 is scheduled for December 1, not assumed available today.

#### DX-01 — Medium — Unbounded verification child processes — Fixed by reliability workstream

**Location:** baseline `tools/verify.py:54-67` used `subprocess.run` without timeout. Current `tools/verify.py:40-49,65-77` adds a positive configurable `--check-timeout` and explicit failure recording.

**Impact:** a hung test/browser child previously prevented the gate from finishing, writing its report, and reaching enclosing cleanup. Default per-check budget is now 1800 seconds; legitimate slower checks can opt into a larger bound. Reliability workstream separately fixes false success reports on interruption and owns the associated tests.

### Dependency drift reviewed without inflating severity

| Component | Local evidence | Primary-source check | Judgment |
|---|---|---|---|
| CPython 3.14.10 | `runtime-lock.json:2-6` | Python release page and PEP 745 | Supported; track conditional advisories and next maintenance release. |
| FastAPI 0.162.0 | `requirements.txt:2` | Official release notes list 0.162.5 sync cleanup fix and 0.162.7 async yield cleanup fix; 0.162.6 drops Python 3.10 | Qualify current patch release tactically. No `Depends(...)` use was found in application routes/API, so those cleanup notes do not establish an observed resource leak here. |
| Playwright 1.62.1 | `package.json:15`, `package-lock.json:32-66` | Official notes include 1.63 | Development-only minor drift; upgrade with browser baselines, not as a production emergency. |
| dnspython 2.9.2 | `requirements-windows.txt:8` | Maintainer advisory fixes GHSA-45c3-73f7-pv4m in 2.9.0 | Already above the fixed version; bounded parser regression passes. |

### Counterevidence and scope limits

- **The connected repository is a stale bootstrap, not the current codebase.** A read-only GitHub check confirmed default branch `main` at `2103cfc36829e3014681299bf8a1285063702449` (2026-11-10T21:43:37Z). Its complete recursive tree contains only `VERSION`, whose text is `0.9.7`. The commit has no parents, the recent-commits endpoint returns only that commit, and no current application churn can be reconstructed from it. The branch API reports `protected:false`, no required status checks; Actions runs report `total_count:0`, and commit statuses are empty. There are no workflow files in that inspected default-branch tree. The separate workflows-list endpoint is unsupported by the connector, so no workflow inventory beyond the tree/runs is claimed. These are repository facts, not assumptions from the release ZIP. `.github` is also excluded by `tools/release_policy.py:35-48`, so its absence in a ZIP alone would not have established any of this. Restore the verified current source and establish CI in a separate authorized repository-write step; this inspection made no writes, clone, push or settings changes.
- **No claim that dependency closure is currently broken.** The lightweight inventory parser reads Name/Version but not full Requires-Dist constraints (`tools/check_dependencies.py:63-71`). A synthetic wheel requiring a nonexistent package passed that inventory helper, but the actual Windows installer invokes pip's resolver with exact hashes (`tools/windows_installer/build.py:251-278`). A target-platform metadata closure check would improve early diagnostics; the downstream resolver is meaningful counterevidence against labeling this an unguarded shipping defect.
- **No automatic dependency upgrade performed.** Current security scan is clean for its stated package scope; changing runtime wheels adds qualification work and is not needed to fix the manifest gate.
- The current archive contains licenses/provenance for bundled wheels, fonts, D3 and map data (`DEPENDENCIES.md:12,54-64`). No unsupported license-violation finding was made.
- No current native Windows installer acceptance, code-signing identity, or enterprise CI policy can be inferred from Linux tests.

### Primary sources checked

1. Python 3.14.10: <https://www.python.org/downloads/release/python-31410/>
2. Python 3.14 schedule/support: <https://peps.python.org/pep-0745/>
3. Python support table: <https://www.python.org/downloads/>
4. Python FIPS advisory: <https://mail.python.org/archives/list/security-announce@python.org/thread/PXVTTOBPUMFJSSUXN6XCS7FC5DZOSZXK/>
5. Python address-resolution advisory: <https://mail.python.org/archives/list/security-announce@python.org/thread/HCHE62VYTPYI6WOPJQDWUBR4CINBPSM7/>
6. FastAPI release notes: <https://fastapi.tiangolo.com/release-notes/>
7. Playwright release notes: <https://playwright.dev/docs/release-notes>
8. dnspython maintainer advisory: <https://github.com/rthalley/dnspython/security/advisories/GHSA-45c3-73f7-pv4m>
9. pip repeatable installs: <https://pip.pypa.io/en/stable/topics/repeatable-installs/>
10. pip secure installs: <https://pip.pypa.io/en/stable/topics/secure-installs/>

### Workstream roadmap

- **Immediate (<1 day):** landed source-manifest gate; landed verifier timeout via reliability workstream; preserve exact advisory scan and interpreter limitations in release evidence.
- **Tactical (1–5 days):** qualify FastAPI patch updates against session/upload/error-handling regressions; lock development/build dependencies; restore current source to version control and establish required CI checks after separately authorized repository writes. The current GitHub default branch contains only the bootstrap VERSION file.
- **Strategic (>1 week):** automate Windows upgrade/rollback and installed-package smoke acceptance; bind signed release provenance, toolchain inventory and test reports to the exact shipped payload; schedule deliberate runtime/codec advisory maintenance.

## Architecture and core workflow maintenance audit

Scope: recovered Eclipse 0.9.98 with the verified cumulative Field checkpoint. No Git history was present. File size, centrality and membership in the 72-file cumulative checkpoint are **churn proxies**, not measured commit frequency. Findings below use current source line numbers; the one fixed issue also identifies its original recovered location.

### Assessment and counterevidence

The system is a modular local application, not an unstructured monolith. `ARCHITECTURE.md:47–69` identifies separate input, evidence, repository, review, rendering and certification responsibilities. Actual code corroborates important guarantees: `workbench/workspace.py:61–84` supplies read snapshots and caller-owned write transactions; `workbench/services/certification.py:97–131` preserves stage/rename/commit ordering; `workbench/report_operations.py:47–93` defines deadline and irreversible-publication boundaries. Existing regression suites include repeat-sighting retention, merge safety and case scope tests (`tests/test_lead_frontier_0991.py:28–60`). A rewrite or microservice split is not justified by this audit.

### A1 — Medium — Per-observation reads extended the lead-assignment writer transaction — fixed

**Location before fix:** `workbench/lead_queue.py:347–351` queried `case_entries` once per requested observation, and `:365–369` queried each retained observation again for root grouping. Both occurred under the writer transaction, established at original `:342`.

**Operational impact:** A lead with 1,201 observations needed 1,201 membership SELECTs and potentially 1,201 more root lookups before the actual scope writes. These are local SQLite calls, not network trips; the problem is avoidable repeated statement execution under the global writer lock. This does not change overall O(N) scope work and was not proven to be the dominant end-to-end bottleneck.

**Remediation implemented:** `workbench/lead_queue.py:158–171` batches membership and root retrieval in groups of 500. `:364–377` uses the result for both new-case IDs and existing-case root grouping. Ordering is preserved, consumed observations are omitted, and IDs that no longer exist cannot enter case scope. No schema or report-content migration.

**Verification:** `tests/test_lead_scope_batching.py` contains three passing unittest tests. A 1,201-ID scope crossing both batch boundaries executes three SELECTs; tests cover source order, three roots, assigned IDs on boundaries, an empty scope and missing observations. Command: `.venv/bin/python -m unittest tests.test_lead_scope_batching -v` (3 tests, 0.007 s). After obtaining Python 3.14.10, `build/qa-env/bin/python -m pytest tests/test_lead_scope_batching.py tests/test_lead_queue_098.py tests/test_lead_frontier_0991.py -q` passed all 32 tests in 21.71 seconds. Ruff passed for both changed files. One existing Starlette TestClient/httpx deprecation warning remains. An earlier Python 3.12 collection attempt was incompatible with the application's Python 3.14 syntax; it was superseded by this target-runtime run.

### A2 — Medium — Queue search fully projects the queue before filtering — open

**Location:** `workbench/lead_queue.py:287–310`. The SELECT fetches every eligible row and its JSON payload; `_project` runs for all rows before `q` is evaluated in Python. `_project`, at `:208–229`, parses payloads and separately reads the job, import, entity and pending-state data; `_awareness_scope` (`:174–200`) aggregates associated history.

**Operational impact:** Even a search returning one lead pays for all current leads, all their JSON decoding and multiple queries per row. No pagination or response size bound exists at this layer. A growing jurisdiction creates work proportional to the full queue for each refresh/search. This is structurally demonstrated; no latency threshold or production workspace size is claimed.

**Counterevidence:** SQL already excludes superseded and suppressed queue rows, and frontier reconciliation keeps only current qualified work per entity. `read_snapshot()` makes the result consistent and does not acquire SQLite's writer lock. These substantially reduce the risk compared with scanning complete historical imports.

**Exact remediation:** Add indexed searchable summary fields for root/entity/IP/finding terms and a stable cursor `(aggregate, observation_day, created_at, id)`. Select a bounded page of IDs before payload projection, and batch job/import/entity summary reads for those IDs. Preserve complete detail/export paths and accurate total counts. Add a scale test with 1k/10k entities requiring bounded projection count for a page and equivalent sort/search semantics. Tactical, 1–5 days.

### A3 — Medium — Report rendering holds the workspace-wide write lock — open, deliberate consistency tradeoff

**Location:** `workbench/services/certification.py:21` holds `store.lock` across snapshot capture and `prepare_package` at `:76`; the lock is released only after publication. All mutations take the same lock in `workbench/workspace.py:73–84`. `workbench/report_operations.py:252` sets a default 110-second operation deadline.

**Operational impact:** While a large report is rendering, unrelated intake publication, entity edits and other transactional writes wait on the same Python lock. Moving rendering to a child process makes it cancellable but does not release this lock. This can create apparent application stalls during a core workflow; the lock duration depends on actual report size and renderer performance.

**Counterevidence:** Keeping the lock ensures source content cannot change between validation and certification, and the existing subprocess deadline/cancellation mechanism prevents unbounded healthy-worker rendering. Read-only SQLite snapshot paths remain available. Removing this lock without replacing the consistency contract would be a regression.

**Exact remediation:** Pin an immutable complete report snapshot and case/review revisions under a short lock; render outside the write lock; reacquire it, verify revisions and evidence fingerprints, then publish only if unchanged. Treat mismatch as a safe retry, never overwrite reviewed content. Preserve rename/commit recovery behavior, and failure-inject edits, cancellation and process death at each phase. Strategic, >1 week; do not fold into a quick maintenance patch.

### A4 — Medium — Intake is streamed from disk but materialized across several full in-memory phases — open

**Location:** `workbench/intake_service.py:331–333` accumulates structural, validated and observation outcome lists; `:339–341` allows 250,000 rows; `:445–449` builds validated records and complete grouped leads; `:537–576` persists all observation outcomes and jobs in one transaction. Pause/stop is checked only at qualification-job boundaries (`:588–596`), after these stages. `close()` waits only two seconds (`:252–256`).

**Operational impact:** A valid large file may expand into several simultaneous Python object graphs and serialized job payloads, then hold the writer transaction for its entire publication. A pause or shutdown requested during filtering cannot interrupt that loop promptly. The code proves lack of bounded working sets/cancellation checkpoints; it does not establish a measured out-of-memory failure.

**Counterevidence:** The manual upload path has a 50-MiB upload limit (`:45`, `:63–65`) and 250k-row cap; CVEs are vetted once per distinct identifier (`:401–418`) rather than via repeated network requests; final publication is atomic and startup requeues interrupted imports (`workbench/workspace.py:43`). These controls are valuable and must be retained.

**Exact remediation:** Stage normalized rows in an import-owned temporary SQLite table in bounded batches; retain original bytes and provenance; perform grouped qualification from indexed staged data; atomically promote the complete import with a commit marker. Add stop/pause checks at bounded row and group intervals with explicit resumable status. Measure peak RSS and cancellation latency at 1k, 50k and 250k rows before setting acceptance budgets. Strategic, >1 week.

### Maintenance priority

1. Immediate: retain the batch scope fix; its 32-test queue/frontier integration run passed on Python 3.14.10. Include it in the final release regression run.
2. Tactical: bounded queue projection and indexed search, with performance budgets.
3. Strategic: short-lock certification and staged/resumable intake; these alter crash/consistency protocols and need dedicated migration/failure-injection work.

## Reliability and frontend maintenance audit

Scope: reconstructed 0.9.98 Windows source plus the hash-verified cumulative Field checkpoint, followed by the bounded corrections below. Source tree: `shadowserver-eclipse/`. This review ran production-module regression tests and syntax checks; it does not claim native Windows or live-browser execution. No Git history was recovered, so current module size and checkpoint edits are proxies for complexity/churn, not measured commit churn.

### Findings

#### R1 — High — Interrupted verification could emit successful evidence — FIXED

Baseline evidence: `tools/verify.py:146-165` caught only `OSError` and `RuntimeError`, then unconditionally constructed `passed: failure is None` and `complete: failure is None and ...` in `finally`. A `KeyboardInterrupt`, `ImportError`, or malformed-JSON `ValueError` bypassed the handler, leaving `failure` unset. The script could write a report claiming success while Python still exited exceptionally. This is a release-evidence integrity defect, not a claim that an affected installer was actually released.

Impact: a review or automated reader trusting the JSON result can accept an interrupted check sequence. Large test counts do not mitigate a verifier that misreports completion.

Correction: `tools/verify.py:88-90,169-195` now sets an explicit completion flag only after execution reaches the end, records unexpected exceptions and interruption as failures, returns 130 for Ctrl+C, and fails closed even if an uncaught control-flow exception reaches `finally`. `tests/test_verification_failure_reporting_0999.py:13-85` injects interrupt, import failure, malformed response, fatal `SystemExit`, child timeout, and successful partial execution.

Falsification: normal nonzero child exits were already handled correctly, and `--skip-browser` / `--skip-backend` were already marked incomplete. The defect concerns exceptional termination outside those existing paths; the fix preserves the partial-run behavior.

#### R2 — Medium — Shared reads could strand loading states and coalesced polling — FIXED

Baseline evidence: `static/modules/shared.js:134-161` created a timeout only when an individual caller supplied `timeoutMs`. Bootstrap at `static/modules/navigation.js:277` and imports polling at `static/modules/navigation.js:346` did not. The navigation poll sets `polling = true` at line 330 and resets it only after the awaited request settles at lines 355-356. A stalled GET therefore prevents subsequent polls indefinitely and can leave the current page waiting indefinitely.

Impact: stalled local-service reads can look like an application freeze, requiring a navigation or reload to escape. This is a fault-path problem, not a demonstrated frequent workstation failure.

Correction: `static/modules/shared.js:134-142` now defaults GET/HEAD reads to 30 seconds. Explicit preview/report deadlines remain honored; submitted mutations retain caller-defined deadlines. `tests/test_navigation_cancellation_0994.cjs:155-173` injects an aborted stalled read, asserts timeout classification and timer cleanup, and verifies that a 120-second explicit deadline survives. Existing assertions also preserve caller cancellation, stale response rejection, and uncancelled submitted jobs.

Falsification: contact discovery, asset attribution and report operations already supplied explicit deadlines; Observatory view/source requests have separate timeout handling. This fix covers the remaining shared GET calls and does not replace those protections. It does not impose a global 30-second mutation deadline.

#### R3 — Medium — A hung verification subprocess could block the gate indefinitely — FIXED, with process-tree limit

Baseline evidence: `tools/verify.py:56` called `subprocess.run` without `timeout`; the browser readiness wait did have a 45-second deadline, so readiness was not the defect. `tests/run_frontend.cjs:57-66` synchronously launches each module suite, and a suite retaining a timer or hanging transport could prevent the higher-level verifier from finishing.

Correction: `tools/verify.py:39-49,61-77` now provides a positive `--check-timeout` with a 1800-second default, records the timed-out check and returns failure rather than continuing. `tests/test_verification_failure_reporting_0999.py:35-52` verifies the configured value is forwarded, a timeout is recorded, and no subsequent check runs. `DEVELOPMENT.md:68-73` documents the behavior.

Residual limit: this is a deadline on the directly spawned process, not a portable Windows Job Object/POSIX process-group cleanup implementation. A subprocess that spawns its own detached child could leave that descendant running; use runner job cleanup or add platform process-tree ownership before treating this as a full orphan-process guarantee. Direct `npm test` does not acquire the verifier's deadline.

#### R4 — High release risk — Native acceptance remains separate from portable success — OPEN

Evidence: `tools/verify.py:192` explicitly records `native_windows_acceptance: False`. `HOME_VALIDATION.md:3-10` distinguishes prior Windows evidence from this release and requires retained-data install, repeated launch, Demo isolation, report inspection, AMSI, backup/restore, scheduling, and uninstall checks. `DEVELOPMENT.md:87-107,118-138` requires dedicated synthetic fixtures for specialized contact/navigation browser flows; these are not all implied by the generic verifier's five browser suites at `tools/verify.py:146-152`.

Impact: a passing Python/portable DOM gate does not establish native installation behavior, workstation rendering, or all specialized browser interactions. This is not evidence of a defect in those paths; it is the most consequential remaining confidence gap for a Windows desktop product handling preserved reports.

Remediation: require version-specific Windows acceptance evidence before stable promotion. Automate install/upgrade/retained-data/uninstall tests in an isolated Windows VM; map dedicated browser fixtures into named acceptance profiles with explicit pass/skip status. Keep the manual report-appearance review where automation does not establish readability. Do not bulk-register obsolete historical browser scripts without adapting them to current contracts.

Falsification: the code and documentation already acknowledge these limits; this is not an accusation of hidden missing coverage or an assertion that all browser tests are absent.

#### R5 — Medium strategic debt — Observatory controller combines transport, state, views and interaction — OPEN

Evidence: `static/eclipse_controller.js` is 1,758 lines. The same mount closure owns request state and cancellation (`:90-106`), data hydration (`:107-120`), field pagination controls (`:501-520`), source loading (`:1276` onward), action dispatch (`:1530-1550`), geography loading (`:1725-1740`), and teardown (`:1741-1756`). This is an unusually broad change surface for a feature still receiving Field checkpoint changes.

Impact: modifying pagination or selection requires reasoning about shared mutable state across transport, rendering and navigation. Over 12–24 months this raises regression and review cost; size alone is not an active correctness failure.

Remediation: extract request lifecycle into a small owner with revision/cancellation contracts, then extract Field paging state and source-detail presentation. Preserve public mount/destroy behavior and the existing actual-controller tests. Do not rewrite the framework or split by arbitrary line count.

Falsification: model, scene and navigation-state modules already exist; this is not a wholly monolithic frontend. Teardown aborts requests, clears timers and destroys the scene. The portable suite explicitly checks cancellation, exact return state, pagination, rendering depth and reduced motion. Those are useful seams for incremental extraction.

### Verification performed

- `node tests/run_frontend.cjs`: all 51 registered suites passed on the recovered baseline and again after the shared-read change. Logs: `frontend-audit.log`, `frontend-audit-fixed.log`.
- `node tests/check_frontend_syntax.cjs`: owned frontend scripts passed.
- `build/qa-env/bin/python -m pytest -q tests/test_verification_failure_reporting_0999.py`: 7 passed (0.37 seconds on initial focused run).
- `build/qa-env/bin/python -m ruff check tools/verify.py tests/test_verification_failure_reporting_0999.py`: passed.
- `build/qa-env/bin/python -m ruff format --check tools/verify.py tests/test_verification_failure_reporting_0999.py`: 2 files already formatted.
- Combined verification is recorded in the final validation section.

Follow-up from the combined run: the historical HTTP contract assertion failed on exactly one unenumerated compatible addition: `/api/eclipse/observations/{observation_id}` GET's optional `intake` query parameter, restricted to `""` or `"dark_matter"` with default `""`. The Field source-detail implementation intentionally supports this selection context. `tests/test_api_structure_071.py:347-366` now asserts the exact optional parameter contract before comparing the remaining schema to the old baseline; it does not ignore arbitrary parameters. `tests/test_observatory_dark_detail.py:78-88` verifies that ordinary, unscoped requests retain approved membership and source fields. Focused verification of both files: **11 passed**, one existing Starlette/httpx deprecation warning; lint and format checks passed. No production change was required for this failure.

### Suggested sequencing

Immediate (<1 day): ship R1–R3 with regression evidence; preserve an explicit release-candidate status until R4's version-specific acceptance completes.

Tactical (1–5 days): consolidate current browser acceptance into named fixture profiles and archive superseded scripts; add a real hung-process cleanup regression using a child process rather than only injected timeout exceptions.

Strategic (>1 week): automated Windows upgrade/rollback/retained-data acceptance and incremental Observatory controller separation under the existing behavioral tests.

## Packaging findings

### High fixed NSIS hook collision prevented the next Windows installer build

- Scope: verified cumulative Field checkpoint, before this maintenance correction.
- Evidence: `tools/windows_installer/installer.nsi` declared `.onGUIInit` at original line 216 and `un.onGUIInit` at original line 424 while importing MUI2 and generating its callbacks through `MUI_LANGUAGE`. NSIS 3.11-1 compilation failed with `Function named ".onGUIInit" already exists`.
- Mechanism verified in compiler's own MUI2 `Interface.nsh:289-319`: MUI2 declares those callbacks and provides `MUI_CUSTOMFUNCTION_GUIINIT` and `MUI_CUSTOMFUNCTION_UNGUIINIT` extension hooks.
- Impact: source-only tests could pass but the current checkpoint could not produce a Windows installer. Earlier checkpoint documentation had accurately disclosed that NSIS compilation was skipped; this is not a claim that a previously delivered installer had this error.
- Remediation applied: register named hook functions before `MUI_LANGUAGE` at current `tools/windows_installer/installer.nsi:52-55`; functions are now `PublishInstallerWindow` at line 220 and `un.PublishInstallerWindow` at line 428.
- Validation: `tests/test_installer_single_instance_0998.py:67-78` asserts the extension-hook contract; existing compile test at lines 83-119 ran with NSIS available. Before fix: 1 failed, 3 passed. After fix: all 4 passed, including actual PE compilation.
- Residual: compilation establishes syntax/linkage only. Duplicate-window focus, install/upgrade, locks, records retention, AMSI and scheduled-job handoff still need native Windows acceptance.

### Build cache provenance

- Runtime: the exact official Python 3.14.10 embedded x64 ZIP referenced by `tools/windows_installer/runtime-lock.json`, SHA-256 `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159`, downloaded and verified against the pinned lock.
- 34 wheelhouse files verified against `wheelhouse-sha256.json` and staged unchanged for the offline installer build.
- NSIS 3.11-1 compiled locally; all operations target synthetic build directories. No installed production application or case data is accessed.

## Security, configuration and operational resilience audit

Reviewed source: recovered 0.9.98 plus all 72 hash-verified cumulative Field checkpoint files. Locations below refer to the maintained tree after this audit's changes unless explicitly marked baseline. No production data, Windows workstation, publisher signing identity or live external source was used.

### Findings

#### SEC-1 — Medium — Restore accepted unreadable closing-record snapshots (fixed)

Baseline `workbench/workspace_data.py:329–347` preflighted notification snapshots before constructing `Store`, but closing records at baseline lines 385–389 received only manifest/hash checks. `workbench/services/recovery.py:75–91` could decode an orphan closing snapshot before any closing-model size check. Correct bytes according to a manifest are not proof that the application can interpret the model.

Reproduction: three complete, hash-consistent synthetic packages with `[]`, an invalid `case_id` shape and an unknown compact storage format all passed `validate_workspace`. A fourth test proved an oversized orphan closing snapshot reached `Store` before preflight. These four assertions failed on the baseline; valid legacy and compact controls passed. Operational consequence: the backup could be labeled verified despite an unreadable closing record; an orphan could also bypass the 256 MiB notification snapshot preflight. This is a restore correctness and resource-boundary defect, not evidence of code execution or existing lost records.

Remediation implemented: shared bounded legacy/compact decoder in `workbench/workspace_data.py:286–299`; closing scalar/collection and case-identity checks at lines 322–338; recorded plus orphan closure preflight at lines 354–380, before `Store` construction. Older schemas without `case_closures` remain supported. No source report or certified snapshot bytes are rewritten. Regression coverage: `tests/test_closure_backup_validation_0999.py`.

#### SEC-2 — Medium — Package integrity verification allocated complete artifacts (fixed for inventory verification)

Baseline `workbench/package_integrity.py:85–89` read a complete artifact before hashing it, and the inventory loop called that helper for every declared member. `workbench/workspace_data.py:25–27` accepts archives up to 2 GiB compressed / 8 GiB expanded, so a large, valid PDF could cause a correspondingly large allocation during restore or ordinary availability checks. The byte limits on JSON snapshots do not bound PDF/document allocation.

Remediation implemented: `workbench/package_integrity.py:148–154` hashes each artifact with `hashlib.file_digest` over a file stream; it preserves path checks, SHA-256 semantics, required members and operation-scoped verification caching. `tests/test_package_verification_streaming_0999.py` checks an approximately 10.5 MiB synthetic artifact, forbids whole-artifact `Path.read_bytes`, and verifies a subsequent mutation is still rejected. Export routines that explicitly need returned bytes retain their existing API; this change does not claim all exports now stream.

Follow-up remediation implemented: `workbench/package_integrity.py:93–102` supplies a shared 20 MiB package-manifest reader, checking file size before opening and reading no more than cap + 1 bytes to detect concurrent growth. Inventory uses it at line 130; closing recovery at `workbench/services/recovery.py:83`, legacy migration at `workbench/case_migration.py:19` and historical notification views at `workbench/services/notification_views.py:99` share the same limit. Focused regressions cover rejection before opening an oversized body, growth after stat, skipped oversized orphan recovery without modifying its bytes and successful normal recovery. The 20 MiB policy matches the existing outer backup-manifest allowance.

Remaining scope: byte-returning `read_member` export consumers still allocate the selected PDF/document and certain live snapshot readers allocate whole snapshots. These changes bound package metadata and artifact **verification** and provide restore snapshot preflight; they do not establish a blanket memory bound across every export or on-disk data consumer. Streaming export is a separate tactical improvement.

#### SEC-3 — Medium — Bulk reference-feed cancellation and deadlines depend on chunk delivery (open)

`workbench/cve_catalog/transport.py:158–168` uses Requests connect/read idle timeouts; lines 214–218 check cancel and the 900-second total budget only after a 128 KiB `iter_content` chunk is returned. `workbench/cve_catalog/risk.py:67–75,99–109` repeats that pattern with a 300-second budget. A provider or proxy that continuously trickles bytes can hold a body read without producing a complete chunk; header reads precede those deadline checks entirely. `workbench/cve_catalog/risk_manager.py:180–185` joins the daemon worker for one second after setting its cancellation flag, without ensuring the blocking request stopped.

Bounded local reproduction, using the real NVD chunk iterator with its HTTP request redirected to a loopback synthetic server: a 60-byte body delivered over 0.6 seconds observed cancellation 0.57 seconds after the flag was set, only when the body completed. Details: `transport_cancel_reproduction.json`. This demonstrates where cancellation is observed; indefinite slow-stream behavior is inferred from the blocking loop and idle timeout, not from running an indefinite test.

Impact: a reference update can remain busy and postpone retry/shutdown cleanup despite a pause request. Saved reference records remain protected by staged/atomic publication; no corruption was demonstrated. This issue does not apply to the separate attribution `bounded_http` async deadline implementation or the IP-pinned contact transport.

Remediation (1–5 days): adopt a streaming transport with one absolute deadline covering connection, headers and body plus cancellation that closes the async request, while retaining bounded chunk memory, native resolver policy, environment proxy support and atomic promotion. Reuse the concepts in `components/attribution/src/attribution/bounded_http.py`, not its whole-body buffering for bulk feeds. Verify slow headers, byte trickles, cancellation, DNS saturation, proxies and saved-feed preservation. Smaller chunks or a Requests idle timeout alone do not prove a hard total deadline. The security documentation has now been clarified to distinguish bounded attribution capture from bulk-feed behavior; the transport fix remains open.

### Falsification and existing protections

- No unauthenticated case-API exposure was found: `workbench/api.py:195–215` applies launcher-created sessions and origin/write-token checks; `workbench/local_session.py:63–102` bounds session counts, expires tokens server-side and consumes launch tokens once. Host/path cookie scoping remains an explicitly documented trusted-localhost limitation, not an application sandbox.
- No ordinary company-URL SSRF bypass was established: `workbench/contact_discovery/policy.py:81–141` restricts scope, scheme, port and query semantics; `workbench/contact_discovery/transport.py:275–287` resolves public addresses, connects the validated address and preserves hostname TLS verification.
- Restore does not simply overwrite live casework. `workbench/workspace_data.py:210–255` journals the staged replacement, verifies before and after rename, rolls back when replacement verification fails and deletes old data only after replacement validation. `export_workspace` exercises actual restore verification on an isolated copy at lines 492–498.
- Credentials are not ordinary workspace settings: NVD uses the Windows vault/session abstraction (`workbench/cve_catalog/credentials.py:26–96`), and launcher credentials use per-user DPAPI on Windows (`workbench/local_session.py:105–171`). No claim of native DPAPI testing is made from Linux.
- Unsigned Windows distribution and storage relying on managed-device permissions/encryption are explicit release assumptions (`SECURITY.md:124–130`), not newly discovered application encryption failures. Publisher signing and workstation acceptance belong on the release roadmap; the source audit cannot manufacture either.

### Validation and changed files

Before the manifest-cap follow-up: focused package/export/backup run 35 passed; focused source-security run 22 passed. After the final manifest-cap changes: 22 focused package/closure/snapshot/legacy-schema upgrade tests passed in 46.48 seconds (`build/security-focused-final.log`). An overlapping broader case-heavy run was stopped to avoid duplicate rendering load and is not claimed as a completed pass. Changed-file Ruff check passed; regenerated program map verified 329 owned modules, zero cycles and zero errors. Existing FastAPI/Starlette TestClient emitted a deprecation warning; it was not a security regression. Combined suite and release results appear below.

Changed files: `workbench/package_integrity.py`; `workbench/workspace_data.py`; `workbench/services/recovery.py`; `workbench/case_migration.py`; `workbench/services/notification_views.py`; generated `docs/program-map.json` and `docs/program-map.html`; `tests/test_closure_backup_validation_0999.py`; `tests/test_package_verification_streaming_0999.py`; `tests/test_security_sources_072.py`.

The existing trickle test had a demonstrated timing failure: its 250 ms total budget expired before a cold HTTP/TLS client contacted the synthetic server, so it tested client startup instead of slow response headers. Its budget is now one second, still below the two-second socket idle timeout; it continues asserting both timely deadline failure and that the request reached the server (`tests/test_security_sources_072.py:77–87`). This does not change production timeout behavior.

## DX3 — High — Canonical repository cannot reproduce the current application — Open

Read-only GitHub evidence identifies main at commit `2103cfc36829e3014681299bf8a1285063702449`. Its complete recursive tree contains only `VERSION:1` with value 0.9.7, no source files and no workflow files; the commit has no parents. Actions reports zero runs and main reports no branch protection or required checks. This is a handoff and release-reproducibility gap: a new developer cannot obtain the current application or its change history from that repository. Saved release packages provide recovery, but not commit-level review or automated regression enforcement.

Remediation: import the verified release source into version control, review the complete initial tree, add pinned Linux/Windows verification jobs and require checks before merging release changes. Preserve exact release/payload hashes in tagged release evidence. No repository writes occurred in this audit. The complete read-only responses are included in the evidence archive.

## DX packaging addition P2 — Medium — Approved assets silently omitted — Fixed

Baseline `tools/release_policy.py:164–180` allowed only selected static extensions and the single cosmic PNG. The cumulative checkpoint added `static/favicon.png` and `static/favicon.ico`, but the source builder filters every file through `distributable()` at `tools/build_release.py:31–38`; the installer uses the same policy. Therefore the new raster/icon assets were dropped despite existing in the source checkpoint. SVG remained included; this was not a complete favicon outage.

The fix explicitly allowlists those two names at current `tools/release_policy.py:179–184`, plus the Field review and audit documents at `:142–143`. It does not broadly permit arbitrary image attachments. `tests/test_release_privacy_070.py` now compares all three favicon payload bytes and rejects unreviewed PNG/ICO files. This repairs release completeness and prevents a repeated integration mistake without expanding the privacy surface indiscriminately.


## Combined validation and release decision

The delivered candidate integrates the earlier Field/Observatory, attribution approval and NVD recovery work with the maintenance corrections. Version is 0.9.99; public name is Maintenance Review; existing installation identity and data paths are retained. No public dependency version changed, no GitHub push was performed, and no production workspace was opened.

- Security gate: 381 tests and 78 subtests passed; all 34 wheel artifacts passed integrity checks, and the fresh advisory scan covered 33 public Python packages with zero reported advisories. Scope excludes the interpreter and native codecs.
- Portable frontend: all 51 suites passed, together with syntax and formatting checks.
- Architecture and Python checks: 329 owned modules, 21 components, no known import cycles; Python lint and formatting passed.
- Upgrade and backup restore from actual 0.9.98 source: 114 protected files unchanged, 3 reports and 15 section validations preserved, and 15 legacy downloads verified in both upgrade and restore phases.
- Browser verifier: attempted with system Chromium; failed at browser startup because this execution environment denies the required singleton socket. Its JSON correctly records passed=false, complete=false. No browser or Windows acceptance is claimed.
- Final metadata allocation follow-up: 22 package/closure/snapshot/legacy-schema upgrade tests passed after the shared 20 MiB reader was introduced. The full-suite run had already collected tests before this last patch; it is not presented as a single green run of every final edit.
- Full backend/Attribution run: **2,643 passed, 1 failed, 151 subtests passed, 0 skipped** in 1,029.15 seconds. The one failure was the stale optional-intake contract assertion; its 11-test API/dark-detail follow-up passed. The final verifier-budget change passed seven tests. The original failing run and follow-up results are retained separately; no single all-green full run is implied.
- NSIS installer compilation and extracted-payload verification are recorded in the companion validation archive. The source archive is verified member-by-member against its generated SHA-256 manifest.

The candidate remains unsigned. Native Windows install/upgrade/AMSI/scheduling/report appearance checks remain required before stable promotion. Existing favorable baseline records were not reinterpreted as acceptance of 0.9.99.

### Evidence index

The validation archive includes the full test log and JUnit result, targeted corrections, frontend results, package advisory JSON, failed browser report, synthetic upgrade summary, source reconstruction hashes, installer payload verification and this audit. It omits synthetic case databases and large generated case reports because the machine-readable checks already record the preservation results.

This audit does not certify that every path is defect-free. It establishes the listed corrections and a concrete, evidence-based backlog for the remaining work.

