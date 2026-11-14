# Development and verification

**0.12.0 — Guided Setup.** Develop from a source checkout or the extracted
source archive, not the installed directory. `RELEASE.json` separates version,
release channel, review name, accepted Windows baseline and current-version
acceptance. Tests and packaging never manufacture workstation confirmation.

The internal `chaos` / `dark_matter` identifiers retain the existing application,
workspace and credential namespace for safe upgrades. They are compatibility
identifiers, not product language or a permanent restriction on stable promotion.
The legacy standalone Chaos identity remains separate.

## Feature names

Use **Workspace** for the current-work area in interface text, documentation,
source identifiers, test descriptions and release notes. Its priority queue,
investigation views and notification/report actions belong to that same area;
do not describe its former name as an additional feature or module. Use
`workspace_queue` and `/api/workspace/queue` for the priority-queue implementation.
The old **Today** name is allowed only in explicit historical or compatibility
notes, including the hidden `/api/today` alias to the same handler. Ordinary date
wording and date APIs keep their normal meaning. This rule does not rename other
application areas such as Leads, Entities, Attribution, Library or Observatory.

## Windows IDE setup

Open the folder containing `run.py`, `pyproject.toml` and `docs/` in your IDE.
In PowerShell, from that folder:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .\components\attribution
npm ci
npx playwright install chromium
```

PDF regression tests also require Poppler's `pdftotext`, `pdftoppm`, `pdffonts`
and `pdfinfo` on `PATH`. On Ubuntu, install `poppler-utils` with apt. On Windows,
install Poppler with `choco install poppler --yes --no-progress` or use an existing
Poppler installation and add its `bin` directory to `PATH`. These are developer
test tools; the installed application does not require them. CI installs and
checks them before running the regression suite.

Select `.venv\Scripts\python.exe` as the IDE interpreter. Editable Attribution
installation makes local library edits visible to development runs. Release
builds still verify the library source against its bundled wheel and will reject
unreleased library changes. The Guided Setup release retains the pinned runtime dependency set; the API module is vendored with its source manifest.

VS Code: use **Companion: isolated synthetic demo** under Run and Debug (F5).
It launches on port 8880 with data under `build/ide-demo`. The default test task
runs the full verifier; other tasks regenerate the program map or run backend
tests. Test Explorer uses the repository's pytest configuration. These files are
optional; the equivalent command in any IDE terminal is:

```powershell
.\.venv\Scripts\python.exe run.py --demo --data-dir build/ide-demo --port 8880
```

The debug configuration never selects an installed workspace. Launchers
also reject `%LOCALAPPDATA%\OutreachWorkbench\data`.
Close another demo on port 8880 before starting it. Avoid pointing development
runs at live records; use a complete workspace copy for upgrade/recovery work.
No format-on-save rule is enabled: approved_template.py must retain its bytes.

## Verification

Use Python 3.14 and a supported Node.js installation for development. Node is only
needed for source checks and browser tests; the installed application needs neither
Node nor a remote asset service.

Create and activate a Python virtual environment, then run from the repository root:

```text
python -m pip install -r requirements-dev.txt
npm ci
npx playwright install chromium
python tools/verify.py --report verification.json
```

The command checks Python formatting/lint, frontend formatting/syntax and frontend
module suites, then starts an isolated synthetic workspace for browser workflow
and accessibility checks. Backend and standalone Attribution regressions run after
browser acceptance so UI failures surface early. It removes the synthetic workspace
and terminates its test server on completion or failure; it does not open your working
case directory. Browser installation may require OS libraries on Linux.

Ubuntu CI grants user-namespace access to the exact installed Playwright executable
through an AppArmor profile, then selects it with `CHROMIUM_EXECUTABLE`. The Observatory
browser test keeps its Chromium sandbox enabled. See Chromium's
[AppArmor guidance](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md)
when configuring a Linux developer workstation.

`CHROMIUM_EXECUTABLE` can select an already installed test browser.
`--skip-browser` and `--skip-backend` are explicit partial-run options; the JSON
result marks these runs incomplete. Each child check has a 1800-second deadline;
use `--check-timeout SECONDS` for a slower workstation. Timeouts, interrupted runs,
and unexpected verifier errors produce failed, incomplete reports. Test dependencies are development-only and are
not included in the application runtime. The Python fixture-import lint exceptions
are restricted to tests; the independent Attribution source keeps its own package
configuration and is not reformatted by the root project.

The approved template file is excluded from formatting deliberately. Its bytes are
protected by regression tests. Do not edit it as a cosmetic cleanup.

## Contact discovery verification

Backend tests inject synthetic website responses into the real discovery engine,
job service, review and contact-plan flow. They do not look up live businesses:

```text
python -m pytest -q tests/test_contact_discovery_090.py tests/test_contacts_store_090.py tests/test_contacts_api_090.py tests/test_contacts_invariants_090.py tests/test_contacts_end_to_end_090.py
```

The dedicated contact browser test uses a separate synthetic server in addition
to the standard browser checks. Start it from the project root in one terminal,
using a workspace directory that does not already exist:

```text
python tests/contacts_browser_fixture_090.py --workspace build/contact-browser-090 --port 8899
```

In a second PowerShell terminal at the project root:

```powershell
$env:CONTACT_BROWSER_FIXTURE = "build/contact-browser-090/browser.json"
node tests/test_contacts_browser_090.cjs
```

Stop the fixture server with Ctrl+C after the run. Its metadata contains a
single-use local test launcher URL; create a new synthetic workspace for a fresh
run. `CONTACT_SCREENSHOTS` optionally selects an output folder. The fixture
supplies fictional company pages locally; the test rejects external browser
requests and verifies that simply opening the contact area does not start a
website lookup.

## Application feature checks

Run the focused suites without accessing live providers:

```text
python -m pytest -q tests/test_chaos_isolation_0981.py tests/test_search_workspace_0981.py tests/test_observatory_intelligence_0981.py tests/test_observatory_api_0981.py tests/test_evidence_workspace_0981.py tests/test_contact_extract_0981.py tests/test_contact_engine_0981.py tests/test_contacts_0981.py
node --experimental-vm-modules tests/test_command_palette_ui_0981.cjs
```

For the real command-palette browser flow, start a fresh synthetic navigation
fixture in one terminal:

```text
python tests/navigation_browser_fixture_098.py --workspace build/palette-browser-0981 --port 8908
```

In a second PowerShell terminal:

```powershell
$env:NAVIGATION_FIXTURE = "build/palette-browser-0981/browser.json"
node tests/test_command_palette_browser_0981.cjs
```

Set `CHROMIUM_EXECUTABLE` if using an existing browser instead of Playwright's
installed Chromium. Stop the fixture afterward. Its launcher metadata is local
synthetic session material, not release documentation. The test blocks external
browser HTTP requests and checks entity/source/Library navigation, focus return
and absence of search queries or authentication tokens from browser persistence.
Other specialized browser suites describe their explicit fixture variables in
the test files; they are not all implied by the generic verifier's browser step.

Keep search and the Workspace brief on read-only saved-record projections. They
must not hash/open report packages or fetch intelligence. Eclipse views consume
retained observation/provenance data and preserve displayed coverage limits.
The portable evidence reader is an internal package artifact; changing its
presentation must not rewrite certified history or recipient documents.

## Upgrade and backup compatibility

Keep an unmodified 0.9.8 source release in a separate folder and run:

```text
python tools/verify_upgrade.py --baseline PATH_TO_098_SOURCE --current . --output PATH_TO_NEW_QA_FOLDER
```

The output must be a new directory. The harness creates synthetic records using
the old code, then opens them and restores their backup using the current code.
It checks case relationships, recorded history and every protected artifact byte.
This is application compatibility testing, not a Windows installer test. For a
manual comparison, export from the baseline and import the copy into a separate
Shadowserver Eclipse workspace;
never point both editions at the same working directory.

## Building a release

```text
python tools/build_release.py shadowserver-eclipse-0.12.0-guided-setup-rc-windows.zip
python tools/windows_installer/build.py --build-dir PATH_TO_BUILD_CACHE --output ShadowserverEclipse-0.12.0-guided-setup-rc-Setup-x64.exe
```

The installer build requires NSIS and the runtime in its pinned lock. Both source
and installer use root `requirements-windows.txt` and `wheelhouse-sha256.json`.
The installer runtime is pinned separately in `tools/windows_installer/runtime-lock.json`.
Use `--offline` once the runtime/download cache is populated.

Both builders run `tools/check_release.py`. Versions must agree across Python,
npm metadata and RELEASE.json. Candidate filenames must include `rc` or `candidate`;
current product filenames use Shadowserver Eclipse. The legacy internal namespace
is retained for safe upgrades. Stable promotion still requires acceptance of that
exact version; an accepted earlier Windows baseline does not satisfy that gate.
The original standalone Chaos edition keeps its historical isolation rules.
The numeric installer version stays compatible with Windows and prior inventories.

Never package a workspace directly. Both builders use the shared explicit release
allowlist; source fixtures must be synthetic. The actual supported platform, test
interpreter patch version, unsigned status and native Windows acceptance limits
belong in `VALIDATION.md` for each release.

## Security release gate

Install `pip-audit==2.10.1` into a separate audit environment or the development
environment. With the application test environment active, run:

```text
python tools/security_gate.py --audit-python PATH_TO_AUDIT_PYTHON --output NEW_QA_DIRECTORY
```

The gate verifies canonical wheel hashes, pins, standalone/application alignment
and bundled Attribution source bytes; it then audits exact public package
versions and runs the targeted 0.7.2 security/citation regressions. Incomplete
advisory scans fail the gate. Only public package names/versions are sent; no
case workspace is opened. Run the complete `tools/verify.py` checks and upgrade
harness as well. Both release builders enforce offline dependency integrity.
Known-advisory scans do not cover all native codecs or establish Windows/FIPS
acceptance. Each release must retain those limits in VALIDATION.md.

## Component navigation and boundaries

Open `docs/program-map.html` for source-level navigation; `docs/MODULE_GUIDE.md`
identifies which area owns each type of change. Ownership and allowed imports
live in `docs/components.json`.

```text
python tools/program_map.py --write
python tools/program_map.py --check
```

Regenerate after changing owned source files, then inspect the diff. Both release
builders and `tools/verify.py` reject stale maps or disallowed dependencies. This
is a static import check; dynamic frontend action calls and SQL relationships
remain covered by explicit contracts and regression tests. The map is developer
documentation and runs entirely offline. Use the source ZIP for verification;
the installed edition intentionally omits developer test fixtures.

Test doubles for provider HTTP now target
`workbench.intelligence.acquisition._response_get`. Offline provider fixture tests
can import `workbench.intelligence.adapters` without application initialization.
Public consumers can continue using `workbench.cve_sources.verify/enrich` and
`workbench.intake`; the old `excel_intake` model imports are compatibility aliases.

Section commands live in `workbench/services/reviews.py`; projections/freeze guards
in `workbench/reviews/queries.py`; deterministic fingerprints in `reviews/policy.py`;
and append-only writes in `repositories/reviews.py`. Lower-level code must not
import the compatibility `section_validation` facade. Repositories never commit
review writes: the command service owns the connection and transaction.

Store is the compatibility composition point. Workspace can be imported and used
without loading report/case commands. Recovery is explicit in Store startup,
after migrations/defaults and before callers start background jobs. Existing
callers can keep their Store/Cases/reporting/closing/SectionReviews imports.

For 0.7.5 maintenance, `Cases` keeps workflow policy while `repositories/cases.py`
owns SQL scope/contact operations. EntityRepository and SourceRepository use the
same caller-owned transaction convention. Use `Workspace.read_snapshot()` for
related read-only projections; use the existing command transaction for reads that
must see uncommitted changes. Do not issue network requests inside either scope.

Frontend interaction changes start in `editor_events.js`, `workflow_events.js`,
`queues_events.js` or `settings_events.js`. Export handlers rather than adding a
second document listener. `events.js` rejects duplicate action/form names, and
`createApplication().destroy()` is the cleanup boundary for delegated listeners
and app polling. Existing backend commands continue independently after teardown.

The official SQLite, Python and MDN references and the transaction-mode rationale
are linked in `ARCHITECTURE.md`. Run `tests/test_maintenance_075.py` and the full
frontend runner when changing these boundaries.
