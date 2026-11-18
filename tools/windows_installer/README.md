# Windows installer

Build the per-user Windows 10/11 x64 installer for Shadowserver Eclipse.
The package includes Python and the runtime dependencies; users do not need
separate Python, Node.js, or Microsoft Word installations.

**Installing Eclipse?** Start with the [application guide](../../docs/USER_GUIDE.md).
This directory is for maintainers building and validating the installer.

## Build from source

Use a complete source checkout with Python **3.12 or later**, pip, and
**NSIS 3.09 or later**. The builder supports Windows or Linux hosts; a successful
build on either host does not establish Windows runtime acceptance.

Run from the repository root:

```text
python tools/windows_installer/build.py
```

The output name follows [VERSION](../../VERSION) and
[RELEASE.json](../../RELEASE.json). The current candidate is
`ShadowserverEclipse-0.12.0-guided-setup-rc-Setup-x64.exe`.

Useful build options:

| Option | Purpose |
| --- | --- |
| `--output PATH` | Set the artifact destination; the name must satisfy release rules. |
| `--build-dir PATH` | Choose the working build directory. |
| `--makensis PATH` | Select NSIS when it is not on `PATH`. |
| `--offline` | Reuse the pinned runtime and wheels after the build cache is populated. |

The first build needs download access. Setup on the user's computer uses the
packaged payload and does not download dependencies. The
[build reference](REFERENCE.md#build) explains pins, hashes, inventory, and caching.

## Preserve installation identity

Updates retain the established installation and data locations:

| Contents | Location |
| --- | --- |
| Program | `%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter` |
| Working records | `%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data` |

These legacy folder names preserve upgrade compatibility. Export a backup before
maintenance, close the application, and allow scheduled work to finish. Do not
launch the application while setup replaces files. Uninstall retains working
records; silent installation and in-app updates retain them as well.

See [installation and update behavior](REFERENCE.md#installation-identity-and-updates)
for cleanup boundaries, data choices, locking, and recovery rules.

## Validate before distributing

The current release is a **candidate**, and the supplied installer build is
unsigned unless a distributor signs the final artifact. Prior Windows acceptance
of 0.9.96 does not establish acceptance of the current version.

Use [VALIDATION.md](../../VALIDATION.md) for recorded results and
[HOME_VALIDATION.md](../../HOME_VALIDATION.md) for the workstation checklist.
Exercise install, upgrade, launch, report generation, backup/restore, scheduling,
and uninstall with retained records. Compilation alone does not complete these checks.

## Reference

| Topic | Read |
| --- | --- |
| Installer behavior, update mode, scheduling, and acceptance | [Technical reference](REFERENCE.md) |
| Pinned Python runtime | [Runtime lock](runtime-lock.json) |
| Distribution contents | [Release policy](../release_policy.py) |
| Application update protocol | [Software updates](../../docs/SOFTWARE_UPDATES.md) |
| Development and release process | [Development](../../DEVELOPMENT.md) |
