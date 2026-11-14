# Shadowserver Eclipse

**From reported exposure to documented outreach.**

Shadowserver Eclipse is a local Windows application for analysts who turn
internet exposure reports into vulnerability notifications. Bring source reports,
organization research, vulnerability references, report preparation, and follow-up
into one workspace, with the evidence behind each decision kept in view.

[User guide](docs/USER_GUIDE.md) · [Documentation](docs/README.md) ·
[Contribute](CONTRIBUTING.md) · [Get help](SUPPORT.md)

> **Current version: 0.12.0 — Guided Setup · Release candidate**
>
> The installer is unsigned. This build still needs final installation, update,
> and desktop checks on Windows. An earlier working version does not verify this build.
> See [validation evidence](VALIDATION.md) and the
> [Windows acceptance checklist](HOME_VALIDATION.md).

## What you can do

| Stage | How Eclipse supports the work |
| --- | --- |
| Bring in reports | Import supported files or retrieve subscribed Shadowserver reports, with optional schedules. |
| Qualify the work | Review findings, attribution evidence, jurisdiction, and outreach priority before opening a case. |
| Understand the organization | Keep entities, domains, assets, contacts, and prior work together. |
| Prepare a notification | Build consistent reports with vulnerability explanations, citations, and a selected evidence appendix. |
| Follow through | Prepare contact wording, record delivery and follow-ups, and document the case outcome. |
| Explore the context | Use Observatory for retained exposure patterns and Library for local CVE and risk references. |

Analyst review connects these stages. A reported finding does not itself prove
compromise, a shared IP does not prove ownership, and preparing an outreach
message does not send it. Original observations and previously certified reports
remain part of the retained record.

## Get started on Windows

Have the 0.12.0 candidate installer? Follow these steps. To work from the repository,
[run from source](#run-from-source).

1. Run `ShadowserverEclipse-0.12.0-guided-setup-rc-Setup-x64.exe`.
   The per-user installer includes Python and the application dependencies;
   operating the app does not require a separate Python installation or Microsoft Word.
2. Open **Shadowserver Eclipse** and complete guided setup: API connections,
   identity and jurisdiction, then optional retrieval schedules. Choose manual
   imports if you are starting without API credentials.
3. Follow the [first-start guide](docs/USER_GUIDE.md#2-set-up-and-open-your-workday).
   For practice, open the **Shadowserver Eclipse Demo** shortcut and confirm the
   sample-data banner before exploring.

The browser is the interface to the local application. Keep its console open
while working; closing a browser tab does not stop the backend. Press **Ctrl+C**
in the console to stop it.

### Run from source

Install 64-bit Python 3.14, run `Setup.cmd`, then
`Start Workbench.cmd`. `Start Demo.cmd` uses a separate synthetic workspace.
For development dependencies and test commands, follow [Development](DEVELOPMENT.md).
Windows is the supported application platform.

## Keep your records under your control

The application runs on your computer and opens a local interface in your browser.
Saved records and downloaded references remain available locally; external lookups,
report acquisition, and
reference updates require connectivity. API access depends on your provider
credentials and subscriptions. On Windows, remembered API credentials use the
current user's Credential Manager.

Recipient reports and internal evidence packages serve different purposes.
Review the intended output before sharing; internal packages contain additional
source records and work history. See the
[report review and export guide](docs/USER_GUIDE.md#8-review-the-report-and-certify-it)
and [security boundaries](SECURITY.md).

**Before updating:** export a checked backup from **Settings → Backup & recovery**,
let active work finish, and stop the application. Do not launch it during setup or
open an upgraded workspace with an older application. See
[backup, updates, and recovery](docs/USER_GUIDE.md#14-protect-your-work-and-end-the-day)
for the full procedure.

## Find the right documentation

| I want to… | Start here |
| --- | --- |
| Learn the analyst workflow | [User guide](docs/USER_GUIDE.md) |
| Find a feature or technical reference | [Documentation hub](docs/README.md) |
| Set up a development environment | [Development](DEVELOPMENT.md) |
| Propose or contribute a change | [Contributing](CONTRIBUTING.md) |
| Understand what changed | [Changelog](CHANGELOG.md) |
| Review release readiness | [Validation](VALIDATION.md) · [Windows acceptance](HOME_VALIDATION.md) |
| Troubleshoot or report a problem | [Support](SUPPORT.md) |
| Report a security issue | [Security reporting](SECURITY.md#reporting-a-vulnerability) |
