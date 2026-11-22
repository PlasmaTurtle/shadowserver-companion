# Windows installer reference

[Build quick start](README.md) · [Documentation](../../docs/README.md)


This directory packages **Shadowserver Eclipse**, using the version recorded in
`VERSION` and `RELEASE.json`, as a per-user NSIS installer for Windows 10/11 x64.
**Guided Setup** is the release name. The application retains its existing
Windows installation identity so updates continue to use the same records,
credentials and shortcuts.

The Windows package includes the CPython runtime pinned in `runtime-lock.json`
and the dependencies pinned in root `requirements-windows.txt`. No separate
Python, Node or Word installation is required to run the installed application.
Python Playwright includes its own Node driver in the locked Windows wheel.
Website capture uses installed Edge/Chrome; setup does not download a browser.
The offline installation self-test starts the bundled driver to detect missing
assets, while native screenshot acceptance remains a separate check.
The source ZIP remains a separate way to run the application with Python 3.14.
The source ZIP filename follows the current version and release name.

## Build

Use the project's Python 3.14 [development environment](../../docs/DEVELOPMENT.md#windows-ide-setup)
with pip and NSIS 3.09 or later on Windows or Linux. The builder's source checks
run in that environment; the packaged runtime is selected by `runtime-lock.json`.
From the source checkout:

```text
python tools/windows_installer/build.py
```

The default artifact name follows the current release metadata. When supplying
`--output PATH`, use the same application version, product and channel in the
filename. The [release workflow](../../docs/DEVELOPMENT.md#building-a-release)
covers version selection and handoff.
Use `--makensis PATH` if NSIS is not on PATH and `--build-dir PATH` to keep
intermediates outside the checkout. A locally extracted Linux NSIS toolchain
may require `NSISDIR` to identify its `share/nsis` directory.

The first build downloads the pinned embedded Python distribution and exact
Windows wheels. Subsequent builds can use `--offline` when the build directory's
`downloads` and `wheelhouse` are populated. `runtime-lock.json` records the
runtime URL and SHA-256; root `requirements-windows.txt` is the canonical package
version/hash lock. `tools/check_dependencies.py` derives the artifact inventory
from the approved wheels and verifies exact coverage; the builder uses the same
check for its staging directory. Refresh the generated source constraints with
`python tools/check_dependencies.py --write` after updating reviewed dependencies.
The application wheelhouse supplies the independent Attribution Module package.

The builder verifies these inputs, checks the release metadata, and produces
a payload inventory and uninstall list from the same files. The application
source is included in the installed `app` directory. The shared packaging policy
excludes working records, local databases, private captures, credentials and
development environments. Included examples use synthetic records.

Build output defaults to `build/windows-installer` and is excluded from source
release ZIPs. Setup itself does not download dependencies or execute downloaded
network content.

## Installation identity and updates

| Item | Existing Windows installation |
| --- | --- |
| Program directory | `%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter` |
| Working records | `%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data` |
| Demo records | Sibling `data-demo` folder |
| Application logs | Sibling `data-logs` folder |
| Working/demo ports | `8881` / `8882` |

The legacy directory names above remain unchanged for upgrade compatibility;
they are storage identifiers, not the public application name.

The installer uses HKCU, current-user shortcuts and
`RequestExecutionLevel user`. It retains the established internal edition
identity for upgrade compatibility; the public release name is supplied by
release metadata. The older standard and other comparison installations have
separate identities and are not automatically migrated.

Export and import through Settings when transferring records between supported
installations. Do not merge private folders or change the installed application's
workspace identity by passing a different edition's data path.

Before replacing program files, an isolated helper compares the prior and new
payload inventories. It removes only obsolete, unchanged package files. Modified
obsolete files stop the upgrade for review; unlisted files and working records
are retained. Unsafe paths, symbolic links and junctions are rejected.
Maintenance runs with a fresh minimal runtime staged from the new installer,
so a broken or missing old Python interpreter no longer blocks repair. Generated
Python bytecode and empty cache directories are removed. Cache-only residue from
an earlier uninstall and partial known payloads can be repaired when the native
installer registration, canonical app location or matching release metadata
establishes this application's identity. Unknown runtime code produces an
explicit error and is preserved; the helper never guesses that a shared Python
installation belongs to this app.

The installed application, Demo, scheduled runner and render workers retain a
running handle for their process lifetime. Maintenance holds the separate
start/install gate before checking for running processes and replacing files.
See the guarded-launch protocol below for ordering, repair and transition limits.

When working data exists, interactive installation defaults to retaining it.
The fresh-start choice requires a second confirmation whose default is No.
The isolated `workspace_data.py` helper targets only the allowlisted
installation's working data, pending transfer and managed restore points. It
preserves demo records and logs and rejects links/junctions before deleting
anything. Silent installation always retains data.

Uninstall removes generated Python caches before deleting its enumerated
program files and empty program directories. The cache cleanup and optional
scheduled-task removal use the staged runtime, so they do not depend on an intact
old interpreter. Working records and unrecognized user files remain. If payload
or bootstrap deletion is blocked, uninstall stops before removing its registry
identity. Required shortcut/registration cleanup also stops on failure while
retaining the self-contained `Uninstall.exe` for retry. That executable is removed
last; if its own deletion fails after registration cleanup, retry it directly.

## Guarded launch and maintenance

`bootstrap.nsi` is compiled separately into an immutable
`bootstrap/launch-<sha256>.exe`, outside the replaceable `app` and `runtime`
directories. Desktop, Demo, self-test, update restart and installed scheduled
actions enter through it. It acquires `StartInstall`, reads and validates
installation readiness, then creates an inherited `Running` handle before starting
Python. Only that handle is inherited by the child. Closing or killing the bootstrap
does not release the child's protection. Workspace's installed-child helper
extends the same contract to report workers before their interpreter starts.

The bootstrap waits at most five seconds for a busy install gate, then exits
with code 6. This expected maintenance race has no persistent dialog, so a waiting
launcher cannot indefinitely lock its own executable during removal. Other
interactive launch failures explain the repair needed; scheduled mode remains
headless. Overlong arguments are rejected rather than truncated.

`installer.nsi` coordinates this sequence with `upgrade_cleanup.py` under the
installer-held gate:

1. Validate both payload inventories, paths, compatibility and bootstrap ownership.
   Verify the optional task's ownership, journal its original settings and enabled
   intent, then disable it and verify no running or queued instances remain.
2. Withdraw `installation-ready.ini`, record the new bootstrap in
   `bootstrap-ledger.json`, and publish its verified bytes without replacing any
   existing executable. Prior owned launchers remain immutable for gate waiters.
3. Replace the payload. Require a written uninstaller, shortcuts and registration.
   Recheck every payload hash and restore the owned task through the new bootstrap.
4. Record the active bootstrap and atomically publish readiness last. Only then
   release the gate and permit restart.

Missing or interrupted readiness prevents entry into Python. Rerunning setup
repairs the known installation and resumes its task journal. Missing ledger
ownership can be recovered from the matching payload inventory; unknown actions,
changed owned launchers and unsafe paths stop maintenance without guessing.
The ledger allows 128 recorded launchers and rejects overflow before mutation.
It is an ownership record, not a signature or protection against another process
already running with the same user's permissions.

Uninstall validates and removes only the owned task, withdraws readiness, removes
the inventoried payload and then removes recorded bootstrap files. Its embedded
inventory also proves the current launcher if local metadata has been lost.
Removal waits up to eight seconds for launcher image locks; a persistent lock
retains ownership and registration for an explicit retry. Unknown files and
working records remain. Accretion owns the
[task transition contract](../../modules/accretion/docs/README.md).

**First-upgrade policy:** old shortcuts, old task actions and manual direct-Python
commands cannot retroactively acquire a pre-import guard. Close the application,
allow scheduled work to finish, and do not launch during the first upgrade to
this protocol. Setup migrates only recognized legacy task actions. Once installed,
use the managed shortcuts/task; manually invoking the installed interpreter is
outside this launch guarantee. Source-checkout commands keep their existing
behavior. [ISS015](../../modules/settings/docs/ISSUES.md#iss015-pre-registration-upgrade-race)
owns completion evidence; this protocol does not replace whole-release acceptance.

## Setup and update experience

The native wizard uses supported NSIS Modern UI 2 controls, Segoe UI, DPI-aware
layout and Eclipse artwork derived from the existing application icon. It shows
installation progress and opens the application after success. The integrated
first-run wizard collects API connections, agency/profile/jurisdiction and
optional scheduling; existing configured workspaces keep their settings.
Credentials are never entered into NSIS, saved in installer logs or passed on a
command line. The standard native text and control layout remain available to
Windows accessibility tools; the side artwork carries no exclusive instruction.

Verified in-app updates invoke the installer with `/UPDATE /RESTART`. This mode
always retains data, skips normal welcome/directory/data-choice/finish pages,
shows installation progress and errors, and waits up to 30 seconds for the app's
running mutex to close. The application first starts verified setup, then shuts
down gracefully after replying to the install request. Setup releases its file
replacement guard before restarting the normal desktop launcher. It is not a
silent `/S` installation, and a failed update never relaunches a partially
replaced program. Manual installation and uninstall still use their normal UI.

Artwork sources and reviewed BMP exports are in `assets/`. Only those exact
assets are allowlisted into source and installed distributions. No new branding,
agency seal or external image content is introduced.

## Runtime and scheduling

The launcher listens on `127.0.0.1` and opens the workspace in the default browser.
A repeat launch reopens a matching running workspace. Simultaneous launches
wait briefly for that matching session to become ready instead of starting a
second backend. Closing a browser tab does
not stop the backend; Ctrl+C in its console does. The Demo shortcut uses a
separate workspace and port.

The browser starts with a short-lived, single-use launcher credential. The
resulting local session is required for protected API operations. Repeat
launches use a Windows DPAPI-protected launcher credential to open a fresh
browser session. This is a local application; these mechanisms do not make it
a multi-user service or establish organizational security approval.

Schedules are opt-in in Shadowserver Data > API. While the backend is open,
it checks the saved schedule. **Enable closed-app runs** registers a current-user
Windows task that checks hourly while that user is signed in. The task uses
saved credentials and requires network access; it does not open a browser or
listen on an application port. Due Shadowserver runs continue through Accretion,
and reference schedules update the local NVD, EPSS and KEV stores. Recent dates
are rechecked for late reports and missed runs catch up when available.

The scheduled runner and interactive application share workspace ownership;
they must not write concurrently. Foreground startup requests a cooperative
handoff from an active scheduled run. If its current request has not finished,
the launcher reports that condition rather than forcing another writer to start.
The task is not a system service, does not run while the user is signed out,
and cannot retrieve data while the computer is off. Check scheduled-run status
and errors after configuration, updates and workstation-policy changes.

## Verification and release status

The builder produces an NSIS PE executable. Verify its extracted files against
`payload-manifest.json`, and run the application and Attribution Module tests
under Python 3.14. A compiled installer and passing Linux tests do not establish
native Windows behavior.

Version 0.9.96 was reported working on the user's Windows workstation. That is
a prior-version baseline, not an assertion that the current Guided Setup candidate has
completed its own native acceptance. The
[November 14 candidate record](../../docs/history/validation/VALIDATION_0120.md)
contains historical results for its identified build. Use
[Windows acceptance](../../docs/WINDOWS_ACCEPTANCE.md) for the checks required on
the exact current artifact, [ISS014](../../docs/ISSUES.md#iss014-current-version-windows-acceptance)
for tracked acceptance status, and [release metadata](../../RELEASE.json) for its
version and channel. Preserve the candidate designation until its release gate
is satisfied.

Windows acceptance should exercise a standard-user install, upgrade from the
prior version with records retained, normal and Demo launches, bundled
`--self-test`, report generation, backup/restore, relaunch and uninstall with
records retained. Exercise scheduled background operation and foreground
handoff separately, along with cancellation of an installation fresh start.
Record actual outcomes; do not substitute successful compilation for them.

For a focused native exclusion probe, run `verify_bootstrap.py` with a fresh
`--output` directory, `--makensis` and an existing Python 3.14 `--python-home`.
It uses a unique synthetic identity, exercises held-gate startup, inherited
handles, parent death and incomplete readiness, and retains source hashes and
results. It does not install the production edition or accept the complete app.

The installer is unsigned unless the distributor signs the final artifact with
an approved Authenticode certificate and timestamp. No publisher certificate
is supplied here. Follow the workstation's software-approval requirements;
do not weaken Windows or organizational security policies to install it.

## Build input references

- Python runtime and exact source URL: `runtime-lock.json`
- [Python embedded distribution documentation](https://docs.python.org/3.14/using/windows.html#the-embeddable-package)
- [NSIS documentation](https://nsis.sourceforge.io/Docs/)

Root `tools/release_policy.py` controls source and installed distribution
contents. Root `RELEASE.json` supplies the public release name and channel;
the builder keeps display metadata and numeric Windows versions consistent.

