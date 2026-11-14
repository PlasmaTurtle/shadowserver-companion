TLP:AMBER

# Security scope and release assurance

## Reporting a vulnerability

Do not place credentials, real hostnames/IPs, case records, source reports,
workspace databases, or exploit details in an ordinary issue or pull request.
This repository is private, but its collaborators and automation can still read
issue bodies, attachments and build logs.

Report suspected vulnerabilities to the repository maintainer, **@PlasmaTurtle**,
through an existing approved private contact channel. If you do not already have
one, open a minimal issue asking for a private reporting route, without technical
details or attachments. A dedicated security mailbox and GitHub private reporting
feature have not been configured or verified; do not assume they are available.

Once the channel is agreed, provide the affected version, security boundary,
impact, and a minimal synthetic reproduction. Replace real identifiers and use
dummy credentials. Coordinate disclosure and remediation with the maintainer;
there is no published response-time or long-term support commitment.

## Version support

Use `VERSION`, `RELEASE.json` and `VALIDATION.md` for the current candidate and its
acceptance limits. Development and fixes target the current source line; older
releases do not have a promised security backport schedule. Automated repository
checks do not establish Windows workstation acceptance or authorize deployment.

## Application security boundaries

Shadowserver Eclipse is a local, single-analyst application. The security
boundary includes untrusted imported fields, external registration/intelligence
responses, browser origins, local HTTP clients and files selected for export.
It does not protect casework from a compromised Windows account that
can already read or rewrite the application and workspace.

The browser session cookie is restricted to the API path, expires server-side,
and is HttpOnly and SameSite=Strict. Browser cookies are scoped by host and path,
not TCP port. Other web services on the same loopback host remain part of the
trusted workstation environment; this is not a sandbox between mutually
untrusted localhost web applications. Native clients without a launcher-issued
credential cannot obtain the session or read case APIs.

## Input Validation: 0.9.98

Aegis (`workbench/aegis/`) provides the shared input-security primitives.
Remote response validation precedes evidence persistence. Contact discovery retains
allowlisted plain-text contact extracts and source metadata, not webpage bodies.
Rejected or unsupported registry/provider responses retain hashes and bounded
metadata without raw content. New routine exports explicitly omit historical raw
contact pages without changing certified records on disk. Source-response hashes
and derived-artifact hashes are separate facts.

Windows contact acquisition also requires a successful local AMSI scan before
static extraction. A blocked/error/unavailable result prevents extraction; there
is no raw-file fallback or scan bypass. The application integrates with the local
provider; it does not implement its own antivirus engine or guarantee that every
syntactically valid response is benign. Context-specific
output escaping remains required. The separate browser screenshot subsystem can
execute permitted remote page scripts; on Windows, each intercepted response is
scanned before rendering and a blocked/unavailable scan aborts the entire capture.
Static contact extraction does not execute scripts. Full archival backups
retain their existing preservation semantics and may contain historical raw evidence.
See `docs/INPUT_VALIDATION.md` for contracts, references and the tested boundaries.

## Professional Review: 0.9.96

This pass strengthens installation/start coordination, authenticated startup reuse,
windowless scheduler diagnostics, NVD credential replacement, and producer/consumer
shutdown order. It does not relax the local API/session boundary or source-capture
restrictions. The targeted security gate now includes later boundary, capture,
privacy and restore suites instead of selecting only the original 0.7.2 tests.

The previous 0.9.95 Windows release was accepted by the operator. Current-version
automated checks are recorded in VALIDATION.md; new Windows behavior remains a
separate acceptance record. Candidate status is explicit. Internal legacy edition
and folder names preserve upgrade/data/credential identity and are not a security
or stability designation.

The installer and launcher gate covers registration and later backend startup in
cooperating versions from 0.9.96 onward. Python/DLL loading and early imports precede
it; this leaves a pre-registration race if the app is launched during file replacement.
Full exclusion requires a bootstrap outside that replaceable runtime or version-staged
installation. Close running instances before upgrading and do not launch during setup.
An older launcher cannot honor the new gate. Existing running-instance checks remain.

Saved NVD and Shadowserver credentials use Windows Credential Manager; the desktop
relaunch credential uses per-user DPAPI. Logging redacts credential-shaped fields,
but logs are still local operational records and are excluded from diagnostic
exports. Report hashes verify file consistency, not independent authorship.

## 0.9.85 audit and remediation

See `docs/history/reviews/AUDIT_0985.md` for source review, scanner triage, regression evidence and
remaining acceptance limits. Request bytes are bounded before JSON parsing and
multipart spooling. New screenshot previews are hashed at acquisition and checked
before viewing, certification and backup restoration. Legacy evidence without a
recorded preview hash retains its original-byte and certified-package checks.

Website capture accepts only a reported hostname from the selected notification.
It starts a fresh installed browser profile, retains sandbox and TLS validation,
denies downloads and sends all page GETs through public-address validation and
IP-pinned HTTP(S) sockets. A private deny-only loopback proxy catches browser
requests outside interception; it never forwards. No normal browser cookies,
credentials, proxy authentication, POSTs or local/private targets are supplied.
Each job allows 160 requests, 4 MiB per resource, 24 MiB total, ten document
navigations and a 35-second acquisition budget with bounded cleanup. Windows
capture processes use a 1.5 GiB/32-process kill-on-close job. OS DNS calls use a
bounded daemon pool; a stalled resolver cannot create unlimited threads.

The new capture driver is validated with synthetic protocol/transport tests.
Real installed Edge, Windows job behavior and enterprise policy acceptance remain
unverified on this Linux build host. Incomplete, challenge and login pages retain
truthful status and are excluded from notification inclusion by default.

CPython advisory CVE-2026-119170 affects 3.14.10 in OpenSSL FIPS mode. Startup now
rejects that specific configuration; it does not turn FIPS off or claim FIPS
validation. The bundled ordinary runtime remains 3.14.10 with verified vendor
bytes. A corrected, approved runtime is still required for FIPS deployments.

## 0.7.2 remediation scope

The base 0.7.1 audit identified a vulnerable DNS dependency, public acquisition of
the local API write token, unsafe screenshot original extensions in exports and
a response deadline checked only after a large body chunk. This release addresses
those paths and associated citation integrity. Validation results are recorded
in VALIDATION.md; that file distinguishes actual checks from acceptance limits.

Historical certified source evidence remains byte-preserved. New source retention
follows the validated provider and derived-contact policies above. Re-encoded screenshot previews
are for presentation. Transport-safe names do not establish that a supplied file
is trustworthy. Historical certified packages remain unchanged on disk.

For older report ZIPs, screenshot originals receive a `.bin` suffix only in the
downloaded transport. `certified-manifest.json` retains the old manifest bytes;
`export-manifest.json` records each delivered hash and maps old names to safe
names. The preserved snapshot retains the original names. Use the mapping when
verifying those certified hashes. This transport download is not a workspace
restore archive; the backup feature remains the restoration mechanism.

Source rendering must operate from the selected captured revisions, with a
report claim pointing to the source that supplied it. Missing optional scores
remain unavailable. An explicitly referenced source revision that is absent or
inconsistent requires review before certification. A failed refresh must not
change the timestamp of a prior successful response or silently replace the
record selected for a certified notification.

## Workstation and distribution limits

- The Windows installer is unsigned. No publisher certificate or signing key
  was supplied; release hashes are integrity checks, not publisher authentication.
- Workspace databases, evidence and backups rely on Windows permissions and
  managed-device storage protection. The application does not add encryption
  to every case file or backup.
- Native Windows account isolation, DPAPI behavior, permissions, installer
  upgrade/uninstall and desktop Word/PDF acceptance require workstation testing.
- Embedded CPython remains pinned to the verified vendor runtime. The audit's
  conditional FIPS and embedded-NUL runtime advisories must be tracked; no claim
  of FIPS validation is made. Do not downgrade past other fixes blindly.
- Bounded attribution HTTP acquisition cancels its sockets at the response deadline.
  Native OS DNS resolution preserves workstation resolver policy but cannot be
  forcibly interrupted. At most two resolver jobs/threads are outstanding;
  cancelled requests do not create unlimited workers. If both OS calls stall,
  subsequent resolution fails promptly until a slot becomes available.
  Bulk NVD/EPSS/KEV feeds currently use idle timeouts and check total budgets and
  cancellation between delivered chunks. A slow header or byte-trickling response
  can delay cancellation; those paths do not yet guarantee a hard total deadline.
- Upgrades remove only obsolete program files recorded in the previous payload
  inventory whose bytes still match that inventory. Modified obsolete files
  stop the upgrade; unlisted files and working records are retained. Incidental
  legacy writes on read routes remain follow-up hardening work.
- Local hashes, timestamps and configured analyst identity support record
  consistency and chronology; they are not an independently signed attestation.
- Software updates are explicit and restricted to the compiled release source.
  Metadata cannot change that source or supply a shell command. The installer
  must match the installation identity, allowed channel, release version, size
  and SHA-256 values from both the manifest and release asset metadata. Keys for
  Shadowserver and NVD are never reused for software distribution. See
  `docs/SOFTWARE_UPDATES.md` for the trust boundary, publication prerequisites
  and failure recovery. These integrity checks do not provide publisher signing.

TLP:AMBER

