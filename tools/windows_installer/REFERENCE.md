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
The source ZIP remains a separate way to run the application with Python 3.14.
The source ZIP filename follows the current version and release name.

## Build

Use Python 3.12 or later with pip and NSIS 3.09 or later on Windows or Linux.
From the source checkout:

```text
python tools/windows_installer/build.py
```

The default artifact name follows the current release metadata. This release
produces `ShadowserverEclipse-0.12.0-guided-setup-rc-Setup-x64.exe`. Supply
`--output PATH` only when a specific destination is needed; its filename must
match the version, variant and channel rules checked by `tools/check_release.py`.
Use `--makensis PATH` if NSIS is not on PATH and `--build-dir PATH` to keep
intermediates outside the checkout. A locally extracted Linux NSIS toolchain
may require `NSISDIR` to identify its `share/nsis` directory.

The first build downloads the pinned embedded Python distribution and exact
Windows wheels. Subsequent builds can use `--offline` when the build directory's
`downloads` and `wheelhouse` are populated. `runtime-lock.json` records the
runtime URL and SHA-256; root `requirements-windows.txt` pins wheel hashes and
`wheelhouse-sha256.json` inventories the artifacts. The application wheelhouse
supplies the Attribution Module package.

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

An installation mutex prevents maintenance while the installed application,
Demo or a scheduled runner is using the program. A separate installation gate
also coordinates new launcher registration with replacement/uninstallation.
The direct shortcut loads Python/DLLs and early imports before that gate, so it
does not eliminate all launch/replacement races. Earlier launchers cannot
participate in it. Disable closed-app runs before
maintenance, stop the foreground consoles, and allow active background work to
finish or yield before retrying the installer.

When working data exists, interactive installation defaults to retaining it.
The fresh-start choice requires a second confirmation whose default is No.
The isolated `workspace_data.py` helper targets only the allowlisted
installation's working data, pending transfer and managed restore points. It
preserves demo records and logs and rejects links/junctions before deleting
anything. Silent installation always retains data.

Uninstall removes generated Python caches before deleting its enumerated
program files and empty program directories. The cache cleanup and optional
scheduled-task removal use the staged runtime, so they do not depend on an intact
old interpreter. Working records and unrecognized user files remain. If owned
file deletion is blocked, uninstall stops before removing its registry identity,
allowing the user to close the blocking process and retry.

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
a prior-version baseline, not an assertion that Guided Setup 0.12.0 has
completed its own native acceptance. See [application validation](../../VALIDATION.md),
[Windows acceptance](../../HOME_VALIDATION.md) and [release metadata](../../RELEASE.json) for the exact checks performed and
remaining checks for the current artifact. The release-candidate designation
must not be silently presented as a stable release.

Windows acceptance should exercise a standard-user install, upgrade from the
prior version with records retained, normal and Demo launches, bundled
`--self-test`, report generation, backup/restore, relaunch and uninstall with
records retained. Exercise scheduled background operation and foreground
handoff separately, along with cancellation of an installation fresh start.
Record actual outcomes; do not substitute successful compilation for them.

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

