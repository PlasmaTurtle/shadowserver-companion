# Shadowserver Eclipse

**0.12.0 — Guided Setup**

A local Windows application for turning reported internet exposures into qualified
outreach: identify the organization, examine the evidence, prepare a notification,
and retain a consistent record of the work.

Start with the [User Guide](docs/USER_GUIDE.md) for setup, the analyst workday,
notification and delivery steps, Observatory, backup, and troubleshooting.

For source work, see [Contributing](CONTRIBUTING.md),
[Development](DEVELOPMENT.md), [Support](SUPPORT.md), and
[Security reporting](SECURITY.md#reporting-a-vulnerability).
Repository maintenance and release controls are described in
[GitHub maintenance](docs/GITHUB_MAINTENANCE.md).

## Install or update

Run `ShadowserverEclipse-0.12.0-guided-setup-rc-Setup-x64.exe`,
then choose **Continue to setup**. Guided setup covers API connections, your agency
identity and jurisdiction, and optional schedules. Manual imports remain available,
and unfinished setup can be resumed from Settings. The per-user installer includes
Python and its runtime dependencies. It does not require administrator privileges,
a separate Python installation, Node, or Microsoft Word.

This updates the existing installation. The program remains under
`%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter`; working records remain
under `%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data`. Updates retain records
by default, and uninstall retains them. Legacy DarkMatter folder names remain storage identifiers so existing records and
saved credentials stay in place. This release retains schema 20 and stores setup progress with the existing settings.
Original imports, case content and certified reports are not rewritten. Upgrades
from older releases still apply the earlier database migrations; do not open a
workspace with an application older than its database schema.

Keep the application's console open while using it; closing a browser tab leaves
the backend running. Reopen the desktop shortcut to obtain a fresh browser session.
Press Ctrl+C in the console to stop. Before an upgrade, close the app and allow
any scheduled work to finish. The launcher and installer coordinate running-instance registration and later
backend startup. Python and its DLLs load before that gate, so it is not complete
protection against launching during replacement. Do not launch during setup; an
older launcher also cannot honor the new gate.

Use **Settings → Backup & recovery** to export a checked workspace copy. Restoring
one replaces the current workspace after staging and restart. Retain a backup
before upgrading; do not open an upgraded workspace with an older application.
Separate historical Companion and Chaos installations keep their own data folders.
They are not searched, merged, or copied automatically.

The operator has confirmed 0.9.96 works on Windows. This Guided Setup package
is a **release candidate**: its current automated results are in `VALIDATION.md`,
and version-specific Windows checks are in `HOME_VALIDATION.md`. Prior-version
acceptance is recorded separately from acceptance of changed code.

## Connect data

1. Add your NVD key in **Settings → API connections**.
2. In **Library**, download the catalog. Initial seeding uses compressed annual NVD
   feeds; subsequent API updates use the configured key. CVSS, affected products and
   versions are retained, with CISA KEV and EPSS reference data alongside them.
3. In **Data → API**, add your account key and secret, select subscribed
   reports and dates, then import. **Files** also accepts supported report files.
4. Configure schedules when regular acquisition is wanted. Scheduled imports run
   the complete Accretion pipeline, with status and failures available for review.

On Windows, remembered API credentials use the current user's Credential Manager.
Session-only credentials stay in memory. Credentials are excluded from workspace
backups and release packages. A source deployment may also supply `NVD_API_KEY`.
Local catalog reading works without an active API connection; downloads and updates
require the configured access. Incomplete catalog coverage remains visible during
intake so priority scores are not mistaken for complete assessments.

Optional Windows scheduling can run with the app closed while the current user is
signed in. It does not run while the machine is off or the user is signed out.
Missed checks, late reports and interrupted work use the existing catch-up logic.
Scheduled startup failures are recorded outside the working data folder.

## Work through the application

| View | Purpose |
| --- | --- |
| Workspace | Current work, follow-ups and recent activity |
| Leads | Qualified opportunities, ranked by internal priority |
| Entities | Organizations, contacts, associated domains, assets and history |
| Attribution | Review identity associations and the evidence supporting them |
| Investigations | Workspace notification cases: build reports, manage delivery and close work |
| Data | Import report files, use the API and follow intake progress |
| Observatory | Explore Field, Atlas, Pulse and Records |
| Library | Search local CVEs, products, versions, risk references and explainers |
| Activity / Settings | Work history, connections, configuration and recovery |

**Workspace** is the current name of the view formerly labeled **Today**. Its
priority queue and next-action guidance are parts of Workspace, not additional
features or separate destinations.

Accretion recognizes prior observations before qualification and commits associations
at the end. Reimporting the same source does not add density. Genuine repeat sightings
extend existing findings without repeatedly creating new outreach. A shared IP can
support multiple organizations without proving common ownership.

New qualification history records approval for each exact finding and observation.
Approval for one condition cannot approve another condition from the same source.
Older aggregate qualification and case decisions remain intact; where the exact
historical approval cannot be proven, its provenance is labeled unavailable.
Original evidence and certified reports are preserved. The migration and database
upgrades are described in `docs/WORKSPACE_EVOLUTION_0110.md`.

Contact suggestions show the published route and supporting source. Prepare outreach saves the subject, message and call outline per case. Close/navigation guards protect unsaved edits, and changes to recipients, report revisions or verification details require review before copying. Copying preparation does not send a message or record delivery.

Press **Ctrl+K** or use **Search & jump** to find entities, investigations, leads,
source files and Library entries. Search reads saved records and does not initiate
outside intelligence lookups.

## Eclipse Observatory

The entity map represents known organizations in the selected evidence. Each canonical entity contributes
one marker, even when it has several associated hosts, assets, findings or repeated
observations. Entities are the primary count; assets and findings describe their
supporting exposure, while observations retain source and timing provenance.

A complete saved entity city/state takes placement priority. When those profile
fields are missing, the map uses city/state from the most recent associated
IP/hostname report in the selected evidence scope. Placement remains an approximate
Census representative point, never raw IP coordinates or an exact street address.
The details identify the location source and, for reported placement, its IP/hostname
and report date. The bundled place lookup covers North Carolina and South Carolina.

A complete but unsupported saved city/state remains unplaced. If the latest selected
report lacks usable city/state, the map does not guess from an older report. These
entities remain accessible in the unplaced directory.

Observation time filters select supporting evidence. Saved entity location reflects
the current profile; reported fallback location follows the selected report cutoff
and displays its date. This is not a historical reconstruction of an organization's
physical address. Repeated observations do not become extra entities.

The Field, Pulse and Records retain their distinct analytical roles. Reported
network geography and a Field object's visual arrangement do not establish an
organization's physical location, common ownership or network traffic. Source
provenance remains available from supporting records.

## Notifications and evidence

Review observation scope before certification. Non-public or invalid network addresses require an explicit exclusion and reason; they cannot be presented as public exposures. Excluded observations remain in the internal record and do not appear in recipient finding counts, CVE lists, exposure narratives or delivery coverage.

New notifications pin the sending organization, office, name, optional title and reply details. Settings changes do not silently rewrite active reports. Review and adopt an update explicitly. Entity details have an atomic adoption review that lists changed fields and reopens only affected frozen sections with a recorded reason.

New notifications use reported CVEs already present in the local catalog. Missing
records are shown rather than silently fetched from publishers in the builder.
Freeze saves and locks a section; explicit preview and certification render it.
Reopening a section records the change without replacing earlier certified packages.

Recipient documents contain the notification and selected appendix. Internal priority
uses a discreet colored marker, not a recipient-facing temperature label. The
**internal evidence package** additionally contains source records, work history,
priority context and an offline `Evidence_Record.html` reader. Send the intended
recipient document rather than the entire internal package by default.

Contact discovery saves derived contact facts and provenance instead of complete
webpage bodies. New routine evidence exports omit legacy raw contact pages explicitly.
Existing certified files remain unchanged; full workspace backups remain archival
transfers and can include historical evidence.

Saved hashes support file consistency and provenance. They do not independently
prove who created a record or establish the truth of a reported finding.

## Source, security and verification

For source use, extract `shadowserver-eclipse`, install 64-bit Python
3.14, run `Setup.cmd`, then `Start Workbench.cmd`. `Start Demo.cmd` opens separate
synthetic records. Developer setup and checks are in `DEVELOPMENT.md`.

See `docs/WORKSPACE_EVOLUTION_0110.md` for this release,
`docs/ANALYST_WORKFLOW_0101.md` for the previous workflow improvements, and
`docs/OBSERVATORY_ENTITY_MAP_0100.md` for map behavior, `SECURITY.md` for the security boundary
and distribution limitations, and `docs/program-map.html` for source ownership.
The installed application binds to loopback, uses launcher-issued browser sessions,
and keeps its assets local. The installer is unsigned; artifact hashes verify
consistency, not publisher identity. Release packages exclude working databases,
credentials and private exports.

## Workspace Evolution

Settings now includes a background **Workspace health** check and a preview of safe
lookup cleanup. Offline recovery can inspect a damaged workspace without normal
startup; see `docs/DATA_MANAGEMENT.md`. Original evidence and certified packages
are never cleanup candidates.

Entities supports reviewed ownership transfers and reasoned restoration of dismissed
findings. A transfer preserves the original business’s cases and dated evidence;
the new owner needs its own attribution review and new work. Legacy qualification
that cannot be tied to an exact retained source is explicitly marked unavailable.

New reports offer **Full** and **Compact** recipient editions. Full remains the default.
Compact focuses the recipient pages while the internal package retains a separate
complete report and source evidence. Existing certified report files stay unchanged.
