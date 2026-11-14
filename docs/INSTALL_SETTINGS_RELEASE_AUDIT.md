# Installation, setup and Settings release audit

Scope: the 0.12.0 guided-setup release. This audit separates code and synthetic
acceptance from native Windows installation and real account validation.

## Existing foundations retained

- `workbench/api.py::local_boundary` requires the local launch session and
  same-origin mutation boundary. Setup and software-update routes must remain
  behind it; they must not become public bootstrap exceptions.
- `workbench/api_acquisition.py::configure` and
  `workbench/cve_catalog/credentials.py` store saved keys in the current user's
  Windows Credential Manager. Session-only replacement removes the prior saved
  account. Credential values must never enter profile JSON, browser persistence,
  scheduler arguments or update metadata.
- `workbench/routes/shadowserver_api.py::schedule_background` requires saved
  Windows credentials for selected closed-app services.
- `workbench/windows_schedule.py::task_xml` uses the current user's interactive
  token, least privilege and an hourly trigger. The process applies the actual
  saved schedule; it is not a machine service that runs after sign-out.
- `workbench/scheduling.py` records completion only after intake completes and
  distinguishes partial failures from successful downloads. A UI must not
  advertise a downloaded report as a completed import.
- `run.py::workspace_session` and `workbench/schedule_handoff.py` protect workspace
  ownership during foreground/background handoff and recovery.

## Acceptance matrix

| Area | Required result | Evidence |
| --- | --- | --- |
| First-run setup | Empty identity opens guided setup; optional API keys can be skipped explicitly; all three steps are reviewed before completion. | New setup backend and browser checks. |
| Existing workspace | A usable saved identity is retained and does not trigger a forced fresh-install flow. Setup can be reopened intentionally. | Setup service tests and browser reload. |
| Identity and agency | Agency presets fill identity fields only. They do not grant API access or infer national jurisdiction. Optional title stays blank cleanly. | Setup profile validation and browser fields. |
| Credentials | Password fields clear after successful submission; neither keys nor secrets appear in browser storage, status payloads or inline errors. | Synthetic credential/browser checks and existing credential tests. |
| Jurisdiction | Incompatible recognized state subscriptions are absent from selectors and rejected on the server, including stale catalog/import/schedule selections. National and unknown scopes remain accurately described. | Jurisdiction service tests and synthetic browser catalog. |
| Automation | Disabled/manual use remains valid. Enabled schedules name their source scope. Closed-app work requires durable credentials and a registered current-user task. | Scheduler and background-route tests; Windows task registration remains native acceptance. |
| Settings | Organization, jurisdiction, connections, automation, report defaults, recovery and software are findable. Unsaved edits are retained on failures and protected on navigation. | Portable module tests and browser walkthrough. |
| Updates | Missing publication, offline/error, current, available and staged states remain distinct. Install requires verified edition/version/asset integrity and explicit action. | Update service tests; native handoff still requires Windows acceptance. |
| What's New | Local installed-version notes are readable, dismissible and reopenable; onboarding takes precedence on a first launch. | Update module/browser tests. |
| Uninstall/reinstall | App-owned runtime/cache files are removed safely; damaged old Python is not needed for repair; working data and shared Python are not deleted. | Installer cleanup tests and NSIS compilation; native cycles remain Windows acceptance. |

## Test environment and commands

The target Python environment is `.venv314/bin/python` (CPython 3.14.10), created
from `/home/agent/.local/bin/python3.14` with `requirements-dev.txt` installed.
Chromium is `/usr/bin/chromium`; Playwright is the repository's development
dependency. NSIS is available from the conversation's build-tools directory.
Wine is not installed. NSIS compilation and static/portable cleanup tests are
not native Windows acceptance.

Focused pre-change foundations passed on target Python:

```sh
.venv314/bin/python -m pytest -q \
  tests/test_settings_profiles.py \
  tests/test_api_acquisition_routes_098.py \
  tests/test_scheduling_0994.py \
  tests/test_scheduled_runtime_0996.py
```

Result: 53 passed. The sole warning was the upstream Starlette/httpx test-client
deprecation, not a failed application check.

The new browser fixture must always use a fresh, explicit temporary workspace:

```sh
.venv314/bin/python tests/setup_release_browser_fixture.py --workspace /tmp/eclipse-setup-acceptance
SETUP_BROWSER_FIXTURE=/tmp/eclipse-setup-acceptance/browser.json \
  CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/test_setup_release_browser.cjs
```

Its synthetic Shadowserver service offers `US-NC`, `US-SC`, `united-states` and
`agency-custom`. No real API account or installer is exercised. Final results
are recorded below after integration.

## Integrated checks completed

- CPython 3.14.10: 67 focused tests passed across
  `test_setup_release_integration_0120.py`, `test_api_jurisdiction_0120.py`,
  `test_software_updates_0120.py`, `test_update_admission_0120.py`, and
  `test_installer_lifecycle_0120.py`. A separate run of
  `test_onboarding_0120.py` passed all 8 tests. These are specific recorded runs;
  later additions and the complete release result belong in `VALIDATION.md`.
- The real-app integration checks exercise all ten new setup/software routes
  through the existing launcher-session, CSRF and same-origin boundaries.
  Unauthenticated or cross-origin attempts cannot start a connection, change
  setup, or launch an update.
- The integrated workflow completes manual setup, configures a synthetic signed
  API connection, saves an NC schedule, changes jurisdiction to SC, verifies
  immediately scoped choices and blocked stale schedule/catalog requests, then
  restarts the application services. Identity, schedule and seen release notes
  persist; session-only keys do not. Profile saving preserves unrelated settings.
- `npm test` passed the complete portable frontend suite, including the newly
  registered jurisdiction, onboarding and software-update UI checks in
  `tests/run_frontend.cjs`.
- The new Playwright scenario is registered in `tools/verify.py` after the five
  existing demo browser suites. It uses a separate fresh synthetic workspace,
  bounded startup, per-check timeouts and guaranteed process cleanup. Syntax,
  lint and formatting checks passed for the new fixture/test and runner changes.

**Browser acceptance remains blocked in this environment.** Chromium exits
before opening a page because its process-singleton Unix socket returns
`Operation not permitted`. The parent and independent QA agent reproduced the
same launch failure. No screenshot, rendered layout, keyboard walk-through or
real browser pass is claimed for this revision. The new scenario is available
to execute on a host that permits Chromium's normal local process communication.

## Cross-application findings

The setup record is versioned under `workspace_setup` in the existing settings
table. It does not require a database schema upgrade. Provider keys remain in
the credential services and are absent from settings/profile records. The
existing SQLite workspace and ownership model remains appropriate for this
single-user local application; setup does not introduce a second store of case
identity or jurisdiction.

`APIAcquisition.scope_changed` invalidates dependent selections after a saved
profile change. The scheduler checks current jurisdiction when configuring and
running, so stale values are not merely hidden in the browser. Known state
subscriptions are constrained; national and unclassified subscriptions remain
selectable with an explicit scope notice because their opaque account names
cannot establish a precise state. Source-row intake still provides the final
jurisdiction check.

Installer review covered `upgrade_cleanup.py::generated_caches`,
`repair_without_inventory`, `uninstall` and `cleanup`. Cleanup is restricted to
the application's program/runtime roots, excludes protected workspace paths,
rejects symlinks/reparse points, and completes ownership/preflight checks before
removing caches. A recognized partial installation can be repaired without
executing its damaged interpreter. Unknown code is retained and causes an
actionable stop rather than a guessed recursive deletion. The staged maintenance
runtime is independent of the installed runtime. Shared system Python is outside
this cleanup policy.

The update installer waits for the running application's lifetime mutex,
acquires the installation gate, retains workspace data, and restarts only after
successful installation. A failed payload copy leaves data intact and supports
rerunning the installer; this is repair behavior, not an atomic rollback of
program files. Older incompatible schemas and downgrades are rejected. The
update service also rechecks the staged installer's digest immediately before
launch, checks edition/channel/installation identity, and requires an explicit
installation action after download.

**Live software delivery still needs a release distribution decision.** The
configured source repository is private and its release listing is empty. An
anonymous installed client cannot retrieve private GitHub releases. The current
service exposes an unavailable/unpublished status instead of claiming the app
is current. Before shipping working remote delivery, provide a public
artifact-only release channel or a deliberately designed authenticated update
service, then publish the matching installer and verified manifest. No
repository visibility or publication change was performed. See
`docs/SOFTWARE_UPDATES.md` for the exact publishing contract.

## Native Windows release gate

Before a production release, execute fresh install, upgrade with retained data,
repair of a damaged bundled runtime, uninstall/reinstall, and cancellation on a
supported Windows workstation. Verify that shared Python and unrelated files
survive, app-owned caches do not block reinstall, the task is removed cleanly,
the protected credentials have the intended retention behavior, and the updater
closes the owning application before handing off to the verified installer.
Exercise DPI scaling, keyboard navigation and installation paths containing
spaces. Keep this gate separate from Linux browser acceptance and synthetic
update-feed tests.

## Complete backend regression

The final collected inventory contains **3,046 test nodes across 223 files**.
All have passing evidence after the corrections below, with no missing or
unresolved nodes. The original four shards also recorded **151 passing
subtests**. This is complete shard coverage followed by targeted correction
runs, not a claim that one unsharded command passed without findings.

The initial inventory contained 3,045 nodes. Files were assigned round-robin to
four concurrent processes. Each process retained normal configured collection
order and used file-based deselection, preserving the attribution component's
existing fixture imports.

| Run | Initial result |
| --- | --- |
| Shard 1 | 824 passed |
| Shard 2 | 731 passed; 9 failed |
| Shard 3 | 682 passed; 1 skipped |
| Shard 4 | 798 passed |

The findings were resolved and rechecked:

- The uninstall confinement test now recognizes the exact new fail-fast
  control block while still checking every file/directory target. Its complete
  test file passed all 14 tests.
- A DNS status read could pair a newly completed job with the previous cache
  snapshot. Status now reports completion coherently. The 65-test follow-up
  passed, including a new deterministic barrier regression; that additional
  test brings the final inventory to 3,046.
- Seven startup-readiness fixtures were updated for the application's real
  software-update shutdown callback. All seven passed with production wiring
  retained.
- The NSIS smoke test initially skipped because the compiler was outside
  `PATH`. Repeating it with the available compiler and `NSISDIR` passed.

`build/verification-0120-backend.json` maps every final test node to its passing
run, retains the original failure/skip history, and references copied JUnit and
log evidence under `build/verification-0120-backend/`. Browser and native Windows
acceptance remain explicitly false in that report.
