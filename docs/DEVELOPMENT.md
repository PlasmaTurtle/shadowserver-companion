# Development and verification

**0.12.1 — Guided Setup.** Develop from a source checkout or the extracted
source archive, not the installed directory. `RELEASE.json` separates version,
release channel, review name, accepted Windows baseline and current-version
acceptance. Tests and packaging never manufacture workstation confirmation.

The internal `chaos` / `dark_matter` identifiers retain the existing application,
workspace and credential namespace for safe upgrades. They are compatibility
identifiers, not product language or a permanent restriction on stable promotion.
The legacy standalone Chaos identity remains separate.

For documentation ownership and historical records, see the
[documentation index](README.md). Start with [Module ownership](ARCHITECTURE.md#module-ownership-and-source-layout)
before choosing a file for a targeted refactor. Track known problems, verification
gaps and planned refactors in the [issue register](ISSUES.md).

## Contributing

This repository contains source, synthetic tests and release tooling, not a
casework workspace. Use bug reports for reproducible failures and feature requests
for concrete workflow improvements. Work on a branch and keep each pull request
focused on one problem, describing before/after behavior, actual checks, skips and
platform limitations. Link the canonical project or module issue ID instead of
maintaining another copy of its status.

Use fictional organizations, example domains and synthetic records. Never commit
or attach API keys, browser session URLs, working databases, real source reports,
case evidence, contact lists or backups. This applies to screenshots, logs, issue
text and CI artifacts as well as source. Use [Security](../SECURITY.md) for private
vulnerability reporting and [Support](USER_GUIDE.md#support-and-troubleshooting)
for troubleshooting.

Keep operational implementation details out of recipient-facing reports. Do not
add a license or redistribute third-party assets without confirming the applicable
rights and retained notices. Update the owning guide and canonical issue with the
change; follow [documentation ownership](README.md#keep-the-documentation-dependable)
when moving pages or changing links and distribution allowlists. Setup, protected
assets, verification and release requirements are maintained below.

## Maintenance workflow

Use this sequence before the next refactor and for subsequent maintenance. The
[documentation hub](README.md#module-documentation-and-tracking) links each
module's guide, issue tracker and changelog.

1. **Choose the issue and owner.** Read the owning module's guide and tracker.
   Record a reproducible problem or a concrete refactor goal, affected callers,
   and the material improvement to the module's purpose. Define observable
   before-and-after criteria for capability, reliability or maintainability.
   Project-wide work belongs in the project tracker;
   module work belongs in that module's tracker. Keep one canonical issue entry.
2. **Establish the baselines.** Record the source revision and uncommitted changes,
   environment and existing failures. Compare representative inputs with a working
   reference using [established implementations](#established-implementations-and-reference-behavior).
   Use synthetic cases for reproducible faults and actual outputs for integration,
   rendering or network behavior. Identify the expected result and verification
   command before editing; preserve the original failing examples. Apply the
   [library selection rule](#library-selection) before writing non-domain logic
   over 50 lines or implementing a standard protocol, parser, or security primitive.
3. **Bound the change.** Identify public interfaces, transaction ownership,
   evidence/resource bytes and compatibility paths that must survive. A move,
   policy change and data migration are distinct changes; do not silently combine
   them. Cross-module work names a primary owner and the affected interfaces.
   Keep application-specific integration with the owner and reuse the selected
   implementation through its supported interface.
4. **Implement one reviewable responsibility.** Keep source, module tests and
   resources with their owner. Update the owning guide when a contract or command
   changes. Link common instructions instead of copying them into each module.
5. **Verify the affected contracts.** Use the matrix below and the module's checks.
   Classify failures using the [failure policy](#how-failures-are-handled).
   If patches accumulate or tests pass without the intended outcome, return to the
   reference comparison before adding another workaround. Verify actual output
   against the intended behavior as well as the tests. Explain independently
   justified fixture/expectation corrections; do not tune tests to the implementation.
   Preserve failed/incomplete evidence; an unrelated existing failure is neither
   a new regression nor a passing result.
   Compatible smaller issues may share one final integration/build run once each
   has passed its module checks. Keep individual scopes and evidence reviewable,
   freeze the combined source state before the full run, and investigate failures
   against the affected module baseline rather than rerunning everything blindly.
6. **Close the record.** Review the final diff, update the canonical issue's
   status and retain the completion date, change reference, demonstrated module
   benefit, commands/results and remaining limits. Passing checks alone does not
   establish the improvement. Identify verification-only repairs as supporting
   work without claiming a module enhancement. For a change to module behavior,
   interfaces or maintenance, add a short bullet under `## Unreleased` in the
   owning module's `docs/CHANGELOG.md` in the same commit. Say what changed and
   why it matters. Link an issue when the reader needs its evidence. Record a
   shared change with its owner. Add a caller entry only if its own behavior changed.
   Update the project issue index when ownership changes.
   Release acceptance remains a separate step.

| Change scope | Verification to retain |
| --- | --- |
| Documentation only | Content and scope review, local links and anchors, documented path/command checks, and source/installed document inclusion when packaging changes |
| Owned source or file relocation | Relevant module regressions and caller checks; regenerate and check the program map; applicable lint/format checks |
| Completed application behavior change | Focused checks first, then the relevant complete suite once on the final change set; frontend/browser checks when those boundaries change |
| Persistence, evidence, backup or release inputs | Affected integrity/restore/upgrade tests and dependency/package gates in addition to behavior checks |
| Release candidate promotion | Exact-version [Windows acceptance](WINDOWS_ACCEPTANCE.md), release identity and retained build evidence |

This matrix selects work; it does not certify checks that were skipped. Do not
rerun an unchanged application suite for prose-only edits or repeat a successful
run without a new change, failure or unresolved concern. Keep temporary run logs
outside maintained guides. Dated evidence records state the source, environment,
command, result, skips and relevant artifact hashes.

## Maintenance and execution policy

These rules apply to human and automated maintenance. `AGENTS.md` is the
source-checkout entrypoint for agents; this guide owns the complete policy.

### Before choosing the workflow

Establish the relevant revision and uncommitted changes, available environment,
tools, network access, permissions, execution limits and cost budget. Reuse verified
session facts and existing authorization; record unknowns instead of repeatedly
probing known limits. Define the intended outcome, scope, verification and stop
condition before automating. Start with reproducible commands and ordinary working
examples; a plugin recipe does not determine the architecture. Work within tool
permissions and safety controls. Track useful outcomes and resource use, not retries.

### Established implementations and reference behavior

Prefer native platform capabilities or maintained libraries for common tasks,
with thin application integration. Before replacing a transport, scheduler,
parser, retry system or other general mechanism, demonstrate the requirement the
established implementation cannot meet. Record the basis for a custom replacement
in the owning issue. Follow the [library selection rule](#library-selection).

Compare the existing failure with an independent working reference: official
documentation, a working example or an explicit domain rule. Use representative
inputs and the same environment where practical. Existing source and tests are
evidence, not the definition of correct behavior. For screenshot work, compare
ordinary browser navigation and inspect the images; a saved PNG alone does not
prove the page rendered.

Reevaluate before adding another workaround when ordinary inputs fail, fixes
accumulate, the reference succeeds or tests pass without the intended outcome.
Simplify or replace the failing approach and remove obsolete workarounds. Sunk
cost and a green test suite do not justify custom machinery.

Apply the user's current direction and update superseded guidance. Inherited
agent-written restrictions and audit conclusions are not permanent requirements.
Establish working end-to-end behavior with normal platform defaults first, then
assess security, data and performance improvements against concrete needs and
ordinary functionality. Do not invent controls that defeat the feature's purpose.

### Library selection

Before writing more than 50 lines of non-domain logic, research the established
open-source library for the job. For any code implementing a standard protocol,
parser, or security primitive, do this before the first line, even inside domain
code. Calling a library's supported API does not itself implement the primitive.

Non-domain logic is code that could serve another application, such as browser
automation, retries or file handling. Lead qualification and notification counting
are domain rules. Count new or rewritten non-domain lines for one capability
across files, contributors and commits, including delegated work. Plan the
comparison up front when the size is predictable. If scope grows, stop before
the 51st non-domain line.

Record a dated decision in the owning module's issue, or the project issue for
shared work. Link it in the pull request. Reuse a prior decision if its evidence
still applies.

- Name the established library and version, including an applicable standard
  library. Link official documentation or upstream source for the capability.
- State the requirement and use the supported API when it satisfies it. If a
  limitation is uncertain, exercise the library on a representative input and
  record the command, environment and observed result.
- Before choosing custom code, including a replacement for a library already
  in use, show why configuration or a thin adapter cannot meet the requirement.
  Identify exactly which part must be custom. Passing tests for the custom code
  alone cannot establish a limitation in the library.

### Where work runs

- Do capable work locally first; hosted CI is not the initial debugging environment.
- Use the connected Windows workstation for native evidence. Results for the exact
  revision are authoritative for the behavior tested, whether or not GitHub ran
  them. Identify unavailable native checks explicitly.
- **Paid GitHub Actions usage has a zero budget.** Do not enable paid usage, raise
  spending limits or select billable runners. Check included usage and all triggers,
  including push and pull-request triggers, before starting hosted work. Stop at an
  exhausted cap; retries cannot fix it. Avoid redundant runs and use supported
  documentation-only CI skips where appropriate.

### How failures are handled

Classify failures before editing: infrastructure or runner access, test harness,
application defect, or an approach that fails where the established reference
works. A run that executes no tests supplies no application-test result. Preserve
known evidence, identify what is missing and request a specific diagnostic when
needed. Stop retries that produce no new information.

Choose the simplest coherent repair. A source snapshot supports comparison and
recovery; it does not require preserving a defective approach. Do not introduce
unrelated upgrades, sharding or workflow redesign during diagnosis. Keep the full,
unsharded verifier as the baseline, separate improvements from repairs, and review
the final diff against the request.

### What counts as validation

Use the [maintenance workflow and verification matrix](#maintenance-workflow) to
demonstrate a material improvement to the owning module and select checks. Test-only
repairs are verification debt, not a module enhancement. Do not weaken assertions,
substitute easier inputs, mock away assessed behavior, relabel failures or change
limits merely to pass. Correct stale expectations or fixtures only with independent
evidence and explain the correction. Inspect the actual output or completed workflow.

Record the tested source state, environment, relevant tool versions, command,
scope, result and skips. Reuse results only while that state remains applicable.
Skips are not passes, partial runs are not complete verification, and launch,
regression and native release acceptance establish different things. Report
merge-rule conflicts separately; never fabricate a status. Keep tests synthetic,
observable and noninteractive, with bounded waits and diagnostics. Preserve
release-identity, evidence-integrity and workstation-acceptance gates.

## Feature names

The [Workspace naming contract](../modules/workspace/docs/README.md#feature-names)
defines current-work terminology and the retained compatibility alias.

## Working in a module

Feature code and its tests/assets live in `modules/<owner>/`. Registered owners
and folder purposes are defined in [Architecture](ARCHITECTURE.md#module-ownership-and-source-layout). Root `tests/` contains
cross-module checks and shared harnesses. Root `conftest.py` patches `requests.get`
and the selected Library transport hooks, and supplies a synthetic native scanner.
It is not a process-wide network sandbox; tests using other transports need their
own controlled endpoints or fixtures.

Reusable fixture builders live under `modules/<owner>/tests/support/`; genuinely
shared application composition and project harnesses live under `tests/support/`.
Import their explicit package paths instead of another `test_*.py` or browser
fixture entry point. Related builders share a cohesive topic module; versioned
test filenames are not fixture interfaces. Root helpers use `tests.*` imports.
The standalone engine owns its separate `attribution_test_support` package.

The reviewed HTTP surface is `tests/fixtures/http-contract.json` in the source checkout.
Its contract test compares every route and schema without a growing list of
historical exceptions. Review intentional API changes against the owning module's
contract before updating this fixture. Capture only `paths` and `components` from
`create_app(..., worker=False).openapi()` using a disposable workspace. Pair schema
compatibility with direct behavior checks for revision conflicts, authentication
and transaction rollback.

The filename guard still rejects duplicate direct Python filenames across root
and module test folders, ignoring case for Windows and allowing `__init__.py`
and `conftest.py`. Default pytest collection can still prepend those directories;
explicit support imports do not require an import-mode change. Nested support
packages are namespaced. Configured application import paths are just the project
root and the standalone engine source, including for directly executed browser
fixtures; do not reintroduce every test directory into `sys.path`.

Run a focused backend test from the repository root, for example:

```text
python -m pytest -q modules/leads/tests
python tools/program_map.py --write
python tools/program_map.py --check
```

`python -m pytest` uses the project configuration to collect the module tests as
well as root integration checks and the standalone Attribution suite. `npm test`
uses the root frontend runner to select the registered module DOM suites. The
full verifier remains the project-wide acceptance command; a focused pass is
partial evidence.

The frontend runner compares its ordered DOM-suite registry with recursively
discovered `test_*.cjs` files in root and module test folders. A missing, duplicate
or stale registration fails before the suites run. Browser scripts are excluded
by the `*_browser*.cjs` naming convention plus the two existing accessibility and
Workspace browser-suite exceptions. Register portable suites in
`tests/run_frontend.cjs`; use the browser convention for feature browser checks
and document their fixture/setup command in the owning module guide. Browser
discovery does not add a script to `tools/verify.py` automatically. Its browser
catalog records each script's routine or focused disposition and rejects missing,
duplicate and stale entries. Inspect it with `python tools/verify.py --list-browser`.
Keep fixture and scope instructions in that catalog, and link to it from module
guides rather than duplicating a changing registry. Reuse `tests/browser_wait.cjs`
for bounded asynchronous API polling; a returned Promise is not evidence that a
browser predicate became true. Preserve timeout diagnostics and last observed state.

## Windows IDE setup

Open the folder containing `run.py`, `pyproject.toml` and `docs/` in your IDE.
In PowerShell, from that folder:

```powershell
$env:PYTHONUTF8 = '1'
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .\modules\attribution\components\engine
npm ci
npx playwright install chromium
```

Set `PYTHONUTF8` before starting Python in each development/test PowerShell
session, including a new terminal after setup. This matches the existing CI
configuration and makes full verification reproducible. Repository resources and
fixtures with a UTF-8 contract now use explicit encoding; the focused cp1252
regressions in [ISS009](ISSUES.md#iss009-explicit-resource-encoding) protect those
readers. Imported reports and system/protocol text retain their own encoding
rules. This does not claim the complete verifier has been accepted with UTF-8
mode disabled, or change installed-app input decoding.

PDF regression tests also require Poppler's `pdftotext`, `pdftoppm`, `pdffonts`
and `pdfinfo` on `PATH`. On Ubuntu, install `poppler-utils` with apt. On Windows,
install Poppler with `choco install poppler --yes --no-progress` or use an existing
Poppler installation and add its `bin` directory to `PATH`. These are developer
test tools; the installed application does not require them. CI installs and
checks them before running the regression suite.
The canonical verifier checks all four before starting a run that includes backend
tests and records an actionable failure if any are missing.

Select `.venv\Scripts\python.exe` as the IDE interpreter. Editable Attribution
installation makes local library edits visible to development runs. Release
builds still verify the library source against its bundled wheel and will reject
unreleased library changes. The Guided Setup release retains the pinned runtime dependency set; the API module is vendored with its source manifest.

VS Code: use **Companion: isolated synthetic demo** under Run and Debug (F5).
It launches on port 8880 with data under `build/ide-demo`. The default test task
runs the full verifier; other tasks regenerate the program map or run backend
tests. The supplied task and debug configurations set `PYTHONUTF8=1` explicitly;
terminal commands still require the session setting above. Test Explorer uses the
repository's pytest configuration. These files are optional; the equivalent
command in any IDE terminal is:

```powershell
.\.venv\Scripts\python.exe run.py --demo --data-dir build/ide-demo --port 8880
```

The debug configuration never selects an installed workspace. Launchers
also reject `%LOCALAPPDATA%\OutreachWorkbench\data`.
Close another demo on port 8880 before starting it. Avoid pointing development
runs at live records; use a complete workspace copy for upgrade/recovery work.
No format-on-save rule is enabled: approved_template.py must retain its bytes.

Before using the `python` verification commands below, activate the environment
with `.\.venv\Scripts\Activate.ps1`, or use `.\.venv\Scripts\python.exe` explicitly.

### Portable checks on another operating system

Windows remains the supported application platform. Portable development checks
require host-native packages; the bundled Windows wheels cannot be reused. Create
a Python 3.14 environment on that host:

```sh
export PYTHONUTF8=1
python3.14 -m venv .venv
. .venv/bin/activate
```

Run the dependency-installation commands above with `python` in place of the
Windows interpreter path and `./modules/attribution/components/engine` as the
editable package path. The npm/Playwright commands are unchanged. Install the host
browser libraries and Poppler as described above. These checks do not establish
support for another desktop platform.

## Verification

Use Python 3.14 and a supported Node.js installation for development. Node is only
needed for source checks and browser tests; the installed application needs neither
Node nor a remote asset service.

Complete [Windows IDE setup](#windows-ide-setup) or
[portable-check setup](#portable-checks-on-another-operating-system) first, including the UTF-8 setting
and development/browser dependencies. From the repository root, run:

```text
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

## Complete CI verification

When hosted execution is available and used, GitHub Actions runs one complete
verification job on Ubuntu and one on Windows.
Each job installs its dependencies and runs the source checks, the routine browser
groups registered in `tools/verify.py`, and the complete Python and standalone
Attribution suite in collection order. Tests are not partitioned into shards.
The final **CI result** succeeds only when both operating systems finish
successfully. This describes the hosted
workflow's status; it does not make GitHub the authority over valid workstation
test results. The browser catalog distinguishes additional focused checks and
their required setup; their presence under a module's `tests/` does not include
them in complete verification.

To run the same checks locally:

```text
python tools/check_dependencies.py --output dependency-integrity.json
python tools/verify.py --check-timeout 4500 --report verification.json
```

The full job has a 90-minute limit, with a 75-minute limit for each verifier
subprocess, allowing the entire Windows backend suite to run in one process.
CI retains `verification.json`, the backend JUnit report and the dependency
integrity report. Test output names each test, and pytest prints all thread
stacks when a test takes more than two minutes. This diagnostic does not skip
the test or change its result.

For focused debugging, run a specific pytest module or use the verifier's
`--only-browser --browser-suite <group>` options; `--list-browser` shows maintained
group names, scenario scope and focused setup requirements. These are partial
runs and do not replace complete verification. Use the failed job's operating
system when reproducing platform-specific behavior. Jobs that fail before
starting a runner have no application test logs; check the GitHub run annotation
for the startup failure rather than treating them as test failures.

A complete CI pass still does not replace exact-version native Windows release
acceptance on a workstation.

## Source configuration

Library's [source configuration](../modules/library/docs/README.md#source-configuration)
documents optional catalog credentials and initial seeding.

## Contact discovery verification

Use the Entities [contact discovery verification](../modules/entities/docs/README.md#contact-discovery-verification)
instructions for synthetic backend and browser coverage.

## Application feature checks

Use each [module guide](README.md#module-documentation-and-tracking) for its
focused suites and behavior-specific fixtures. The root `tests/` directory owns
cross-module integration and release checks. Select additional caller tests from
the program map when a change crosses a module boundary.

Command-palette fixture setup and the real-browser flow are maintained in
[UI verification](../modules/ui/docs/README.md#command-palette-browser-verification).

## Upgrade and backup compatibility

Workspace owns the [upgrade and backup compatibility harness](../modules/workspace/docs/README.md#upgrade-and-backup-compatibility).
Run it before releasing changes that cross persisted-record or backup boundaries;
its synthetic application checks do not replace installer acceptance.

## Building a release

Before handing off a changed installer or source release, choose a version
greater than the last one handed off. Use a patch increment for fixes, a minor
increment for compatible features, and a major increment for breaking changes.
Group related commits in one release. The updater compares the three numeric
version components and the release channel. Two candidates at the same version
appear identical to it.

Review the [module changelogs](README.md#module-documentation-and-tracking)
alongside any project-wide changes. From the repository root, compare the
working tree with the previous release tag to see the module entries together.

```text
git diff <previous-release-tag> -- ":(glob)modules/*/docs/CHANGELOG.md"
```

In each affected module, move the entries included in this release from
`## Unreleased` to `## X.Y.Z`. Keep pending entries under `Unreleased` and
keep that heading ready for the next change. Use the shipped entries to write
the user-facing highlights in the root `CHANGELOG.md`, which feeds What's New.
Update those notes, `VERSION` and `RELEASE.json` together. Build the source
archive and installer from the same committed inputs.
Record the Git commit and each artifact's SHA-256 with the handoff. When
publishing a release, tag that commit. A diagnostic retry with unchanged inputs
can keep its version and record a separate build receipt.

These PowerShell commands build the Guided Setup candidate.

```powershell
$version = (Get-Content -Raw VERSION).Trim()
python tools/build_release.py "shadowserver-eclipse-$version-guided-setup-rc-windows.zip"
python tools/windows_installer/build.py --build-dir PATH_TO_BUILD_CACHE
```

The installer build requires NSIS and the runtime in its pinned lock. Both source
and installer use canonical `requirements-windows.txt` pins and hashes to verify
the bundled wheels; artifact inventories are derived from those verified files.
`requirements-constraints.txt` is a generated public-package projection. After a
deliberate lock change, run `python tools/check_dependencies.py --write`; the
normal read-only check rejects stale constraints. See [Dependencies](DEPENDENCIES.md)
for source/standalone alignment and the complete dependency update contract.
The installer runtime is pinned separately in `tools/windows_installer/runtime-lock.json`.
Use `--offline` once the runtime/download cache is populated.

Both builders run `tools/check_release.py`. Root `VERSION` supplies the application
version, including `modules.__version__`; `RELEASE.json` must bind its channel and
acceptance metadata to that same version. The private npm package configures
developer tooling and does not duplicate the application version. Candidate filenames must include `rc` or `candidate`;
current product filenames use Shadowserver Eclipse. The legacy internal namespace
is retained for safe upgrades. Stable promotion still requires acceptance of that
exact version; an accepted earlier Windows baseline does not satisfy that gate.
The original standalone Chaos edition keeps its historical isolation rules.
The numeric installer version stays compatible with Windows and prior inventories.

Never package a workspace directly. Both builders use the shared explicit release
allowlist; source fixtures must be synthetic. The actual supported platform, test
interpreter patch version, unsigned status and native Windows acceptance limits
belong in a dated record under `docs/history/validation/` for each release.
Keep its source/build identity explicit and link it from the documentation index;
the [Windows checklist](WINDOWS_ACCEPTANCE.md) retains the outstanding native checks.

## Security release gate

Install `pip-audit==2.10.1` into a separate audit environment or the development
environment. With the application test environment active, run:

```text
python tools/security_gate.py --audit-python PATH_TO_AUDIT_PYTHON --output NEW_QA_DIRECTORY
```

The gate verifies canonical wheel hashes, pins, standalone/application alignment
and bundled Attribution source bytes; it then audits exact public package
versions and runs the selected security/citation boundary regressions, including
session, capture, import, admission and restore coverage. The suite patterns in
`tools/security_gate.py` define the selection. Incomplete
advisory scans fail the gate. Only public package names/versions are sent; no
case workspace is opened. Run the complete `tools/verify.py` checks and upgrade
harness as well. Both release builders enforce offline dependency integrity.
Known-advisory scans do not cover all native codecs or establish Windows/FIPS
acceptance. Each release must retain those limits in its dated validation record.

## Component navigation and boundaries

Use [Architecture](ARCHITECTURE.md#where-to-make-the-next-change) to choose the
owning layer and inspect transaction, lifecycle and import contracts. The
[program map](program-map.html) and its [registry](components.json)
show literal imports and test targets. Regenerate the map after source changes
as described under [Working in a module](#working-in-a-module).

Provider test doubles are documented in [Library](../modules/library/docs/README.md#provider-verification);
review command ownership in [Investigations](../modules/investigations/docs/README.md#review-command-ownership);
frontend event/lifecycle rules in [UI](../modules/ui/docs/README.md#interaction-lifecycle).
Run `tests/test_maintenance_075.py` and the full frontend runner when
changing these boundaries. Use the source checkout/archive for verification;
the installed application intentionally omits developer test fixtures.
