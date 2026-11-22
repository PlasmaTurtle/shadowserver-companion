# Shadowserver Eclipse

**From reported exposure to documented outreach.**

Shadowserver Eclipse is a local Windows application for analysts who turn
internet exposure reports into vulnerability notifications. Import reports,
qualify leads, research organizations, prepare evidence-backed notifications,
and record outreach in one workspace. Observatory provides exposure context;
Library keeps local vulnerability and risk references.

[User guide](docs/USER_GUIDE.md) · [Documentation](docs/README.md) ·
[Development and contributions](docs/DEVELOPMENT.md) ·
[Support](docs/USER_GUIDE.md#support-and-troubleshooting)

> **0.12.1 — Guided Setup · Release candidate**
>
> The installer is unsigned. Exact-version Windows installation, update and
> desktop acceptance remain outstanding. See the [release notes](CHANGELOG.md)
> and [Windows acceptance checklist](docs/WINDOWS_ACCEPTANCE.md).

## Get started on Windows

1. Run `ShadowserverEclipse-0.12.1-guided-setup-rc-Setup-x64.exe`.
   The per-user installer includes Python and application dependencies;
   operating the app does not require a separate Python installation or Microsoft Word.
2. Open **Shadowserver Eclipse** and complete guided setup: API connections,
   identity and jurisdiction, then optional retrieval schedules. Manual imports
   are available without API credentials.
3. Follow the [first-start guide](docs/USER_GUIDE.md#2-set-up-and-open-your-workday).
   For practice, use **Shadowserver Eclipse Demo** and confirm the sample-data banner.

The browser is the interface to the local application. Keep its console open
while working; closing a browser tab does not stop the backend. Press **Ctrl+C**
in the console to stop it.

### Run from source

Install 64-bit Python 3.14, run `Setup.cmd`, then `Start Workbench.cmd`.
`Start Demo.cmd` uses a separate synthetic workspace. Use
[Development](docs/DEVELOPMENT.md#windows-ide-setup) for developer dependencies,
verification and [contribution expectations](docs/DEVELOPMENT.md#contributing).
Windows is the supported application platform.

## Work with retained evidence

Analyst review connects findings, attribution and outreach. A reported exposure
does not itself prove compromise, a shared IP does not prove ownership, and
preparing a message does not send it. Saved records remain local; external
lookups and updates require connectivity and any applicable provider access.

Review recipient reports and internal evidence packages before sharing. Follow
[report review and export](docs/USER_GUIDE.md#8-review-the-report-and-certify-it) and
[backup, updates and recovery](docs/USER_GUIDE.md#14-protect-your-work-and-end-the-day)
before distributing records or upgrading. See [Security](SECURITY.md) for trust
boundaries and [private vulnerability reporting](SECURITY.md#reporting-a-vulnerability).

The [documentation hub](docs/README.md) links module ownership, maintenance guides,
issue trackers and release evidence. [Recent changes](CHANGELOG.md) describe the
current release line; older entries are retained in documentation history.
