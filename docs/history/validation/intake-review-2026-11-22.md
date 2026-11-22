# Intake and lead review on November 22, 2026

This record covers the Windows source checkout based on `c86a7cd` and the
changes tested for the 0.12.0 candidate. It complements the
[earlier full build](full-build-2026-11-21.md).

## Boundaries checked

- **ACC-01–07 and ASC-01–03.** Accretion owns input identity and qualification.
  Associate owns deconfliction by entity, registered domain and exact hostname.
  See the [pipeline](../../../modules/accretion/docs/PIPELINE.md).
- **LEAD-01–06, INV-01–02 and ENT-01.** Leads presents stored evidence and
  review queues. Investigations supplies delivery history. Entities resolves
  business identity after merges. See the [Leads guide](../../../modules/leads/docs/README.md).
- **ATTR-01–03 and ENT-02–03.** The published NC business-registration layout
  defines the local schema. The state supplies the weekly extract to authorized
  recipients. Source-file ingestion, refresh and application of matched records
  depend on access and inspection of a representative extract.
  [Attribution ISS056](../../../modules/attribution/docs/ISSUES.md#iss056-north-carolina-business-registration-import)
- **ARCH-01–04.** The eleven application modules and shared Tools already have
  source, resource and test owners. The component registry identifies shared
  infrastructure and the standalone Attribution engine. After the behavior change,
  five pending-lead HTTP handlers moved from Entities to Leads and the saved
  screenshot handler moved to Investigations. The 182 OpenAPI paths and all
  schemas compared equal before and after the move. See the [architecture](../../ARCHITECTURE.md).

## Workflow and upgrade evidence

- Three isolated workspaces reached the same qualification outcome for equivalent
  workbook, manual API and scheduled API observations. Repeating the same delivery
  reused its import. CSV and workbook originals retained independent provenance and
  produced one active lead, one domain association and one canonical finding.
- In Edge, an exact-host referral excluded one of two hosts sharing the same root.
  Re-uploading the source left one import and one queued lead. Its saved capture
  opened at full resolution. After certification, simulated delivery and closure,
  the original lead showed one completed notification. The recipient PDF contained
  the admitted host and omitted the excluded hostname and the internal referral.
- Reversing the host order exposed a second defect. A lead could retain the first
  host's screenshot after Associate had excluded that host. Qualification now
  chooses evidence for surviving observations and Associate rechecks its scope
  before publication. Case creation and previews use that admitted capture.
  With the referred host first, the certified case contained one observation on
  the surviving host and its matching screenshot. The ten-page PDF, Word export
  and recipient manifest omitted the excluded host and internal referral.
- A whole-domain referral allowed its group through qualification and evaluation
  and published zero leads. A separate history fixture with two completed cases
  and one pending report displayed two notifications, including after entity merges.
- A new end-of-life finding for a business with a do-not-contact case reused the
  saved screenshot and registration. Qualify and Evaluate each recorded one
  group. Associate recorded the case ID and hold reason, published zero leads
  and archived the source rows. The closed case kept its version and finding
  history. The earlier test had expected the hold to run before qualification.
- The schema-23 source was exported from `c86a7cd`. The original upgrade harness
  assumed exactly three evidence records, while that version seeded four, including
  one for a draft case. The harness now requires website evidence for every
  reported case and verifies each original digest and preview. It preserves an
  already reviewed case snapshot and checks the legacy projection when adding one.
  The schema-24 upgrade and separate backup restore both preserved all 90
  protected files, three reports, four attached evidence records and fifteen
  section validations. All fifteen historical download responses matched the
  recorded bytes. A separate upgrade from schema 20 and restore preserved
  all 53 protected files.

## Build checks

The local toolchain used Windows x64, CPython 3.14.10, Microsoft Edge 158 and
Poppler 26.09.0. The dependency check verified all 35 approved wheels. The Python
advisory check and npm lock audit reported zero known vulnerabilities at check
time. The security and citation gate completed 479 tests and 78 subtests with
ten skips. Its results overlap the main regression suite.

The full application gate passed all 25 checks on Windows with
`python tools/verify.py --check-timeout 4500 --report <evidence>/verified-candidate.json`.
This included 17 Edge browser workflows and one uninterrupted backend and
Attribution run. Of 3,791 tests, 3,769 passed and 22 skipped. All 196 subtests
passed. The one warning was the existing Starlette test-client deprecation.
The backend run took 37 minutes 8 seconds. Earlier checks exposed direct
notification-history SQL in a service. The Investigations repository now
owns that query and serves a page of entities in one database read. The release
commands are `python tools/build_release.py <source-zip>` and
`python tools/windows_installer/build.py --offline --build-dir <build-cache>
--makensis <nsis> --output <installer>`.

For this run, `dist/final-backlog-20261122/validation-status.json` records the
application result and package inspection separately. The adjacent SHA-256
file identifies the local artifacts. Independent source inspection compares
the ZIP inventory and contents with the frozen checkout and checks the
manifest, documentation links and extracted application. The detailed logs
and evidence are under the task workspace's
`validation/final-backlog-20261122/`.

During the offline Windows build, real-time Defender detected the freshly
compiled launcher at 01:07:25 Eastern and quarantined it at 01:07:29.
The build stopped before hashing the launcher or assembling the installer.
Installer inspection and installed-runtime acceptance remain pending. The
event IDs and detection details are recorded in
[ISS054](../../ISSUES.md#iss054-defender-quarantined-the-windows-launcher).
