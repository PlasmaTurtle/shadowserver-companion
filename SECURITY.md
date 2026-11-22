TLP:AMBER

# Security scope and release assurance

This policy owns vulnerability reporting, version support and the application's
trust boundaries. Implementation contracts live in the owning guides linked below;
dated audits are [historical evidence](docs/history/README.md), not current acceptance.

## Reporting a vulnerability

Do not put credentials, real hostnames/IPs, case records, source reports, databases
or exploit details in ordinary issues or pull requests. This private repository's
collaborators and automation can still read attachments and logs.

Contact the repository maintainer, **@PlasmaTurtle**, through an existing approved
private channel. If none is available, open a minimal issue asking for a private
reporting route, without technical details or attachments. A dedicated security
mailbox and GitHub private reporting have not been configured or verified.

Provide the affected version, boundary, impact and a minimal synthetic reproduction
with dummy identifiers and credentials. Coordinate disclosure and remediation with
the maintainer; no response-time or long-term support commitment is published.

## Version support

Fixes target the current source line. Older releases have no promised backport
schedule. `VERSION` and `RELEASE.json` identify the release; the
[Windows acceptance checklist](docs/WINDOWS_ACCEPTANCE.md) defines native release
acceptance. Recorded checks apply only to their stated source and environment.
Automated repository checks do not authorize deployment or establish workstation
acceptance. See [Development's security gate](docs/DEVELOPMENT.md#security-release-gate)
and [dependency/runtime review](docs/DEPENDENCIES.md) for release verification.

## Application security boundaries

Eclipse is a local, single-analyst application. Imported fields, provider responses,
browser origins, local HTTP clients and exported files cross security boundaries.
The application does not protect casework from a compromised Windows account that
can already read or rewrite its files. Workspace records and backups rely on
Windows permissions and managed-device storage protection; not every file is
encrypted by the application.

The browser session cookie is API-path restricted, expires server-side, and uses
HttpOnly and SameSite=Strict. Cookies are scoped by host and path, not TCP port;
other services on the same loopback host remain part of the trusted workstation.
Native clients require a launcher-issued credential. Saved NVD and Shadowserver
credentials use Windows Credential Manager; desktop relaunch uses per-user DPAPI.
Logs redact credential-shaped fields but remain local operational records and
are excluded from diagnostic exports.

## Input validation and retention

[Input validation](docs/INPUT_VALIDATION.md) owns provider parsing, bounded input,
contact scanning and retention contracts. Static contact acquisition on Windows
requires a successful local AMSI scan and does not execute scripts. It retains
validated contact extracts and metadata, not webpage bodies. Historical certified
records remain preserved; full archival backups can contain legacy raw evidence.
Validation and output escaping do not establish that external content is harmless.

[Website capture](modules/tools/docs/README.md#website-loading-and-capture) uses
native Edge/Chrome in a fresh temporary profile, with normal scripts, networking,
sandbox and TLS behavior. Browser resources do not pass through the application's
contact scanner or an application-imposed public-address gate. HTTP(S) syntax
validation and screenshot classification are not a malware or destination-trust
verdict. [Investigations](modules/investigations/docs/README.md#website-loading-and-capture)
owns qualification and report inclusion; functioning related login/admin pages
can qualify. Browser loading and caller admission are separate contracts.

[Evidence retention and transport](modules/investigations/docs/README.md#evidence-retention-and-transport)
owns original bytes, preview integrity, captured source revisions and historical
export compatibility. Local hashes, timestamps and analyst identity support
consistency and chronology; they are not independent authorship or signed attestation.

## Startup and distribution limits

Managed installed launches and render workers use the
[installer's guarded-launch protocol](tools/windows_installer/REFERENCE.md#guarded-launch-and-maintenance).
Interrupted installations remain inert until repaired. Older launchers and direct
interpreter commands cannot honor the pre-import guard: close existing instances,
finish scheduled work and avoid launching during the first upgrade. Use managed
shortcuts and tasks afterward. Cooperative locks and hash inventories do not
protect against arbitrary code with the same user's filesystem permissions.

The installer is unsigned. Release hashes verify integrity, not publisher identity.
[Software updates](modules/settings/docs/SOFTWARE_UPDATES.md) documents the fixed
release source, installation identity, channel/version/hash checks and recovery.
API provider keys are not distribution credentials. Native account isolation,
DPAPI, installer upgrade/uninstall and Word/PDF behavior require exact-version
Windows testing. Runtime pinning and conditional advisory/FIPS limits remain in
[Dependencies](docs/DEPENDENCIES.md); an old audit is not a current advisory scan.

TLP:AMBER
