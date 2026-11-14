# 0.9.94 — Canonical awareness

This release replaces downstream reconstruction with a committed intake model:
Entity → assets → findings → source observations. Early recognition only looks
up history. Qualification reuses applicable, intact historical evidence and checks
new or conflicting endpoints. Associate commits the result and queue changes in
one transaction.

## Identity and retention

A finding identifies an asset, an individual CVE or other condition, and relevant
service scope. Version, severity, geography, source filename and ownership labels
are attributes rather than permanent finding identity. Each source observation
can support several findings; that does not multiply its density. Reordered or
repackaged duplicate measurements consolidate independently of source-file hashes.
Source provenance and original import bytes remain available separately.

Approved admission survives queue retirement, notification and closure. Dark
Matter contains usable unadmitted observations with reasons. Shared IPs do not
merge ownership. Unknown assets remain representable. New or changed unqualified
endpoints do not replace the approved representative of a known finding.

The current queue retains one entity work item, with the latest-day evidence for
its unhandled findings and distinct endpoints. Older observations remain history.
Already handled conditions do not reappear in a new report merely because a row
also contains a new CVE. Per-case condition scope preserves the original source
row and does not modify previously created or certified cases.

## Observatory and Entities

Counts distinguish findings, affected assets, source observations and distinct
observation days. Entity/unresolved-asset density uses deduplicated source events:
≤50 normal; 51–200 yellow; 201–1,000 red; >1,000 purple. Density and internal outreach
temperature are separate. Admitted and linked dark-matter contributions remain
visible separately. Repeated sightings update observation history without making
another new finding or lead.

Entities accept manually associated domains and hostnames for aliases/rebrands,
with ownership-conflict checks. Directory and dossier projections use canonical
counts and expose source history separately. City/state choices use the bundled
national Census place catalog; mailing addresses remain free text. Email/phone
validation checks syntax and plausibility, not deliverability.

Google and Cloudflare resolver results are concurrent, separately sourced and
cached. Disagreement is retained; unavailable evidence is incomplete rather than
fabricated agreement. Resolver agreement alone is not an ownership assertion.

## Reports and responsiveness

New notifications select available matching local CVE records with immutable
extracts and provenance. Missing local records remain visible. Notification CVE
retrieval does not silently call publishers. Reopening one section preserves
unsaved changes in other sections and existing snapshots. Attribution capture
is no longer blocked by an unrelated frozen Closing section. Capture diagnostics
retain safe DNS/TLS/timeout/navigation details and public-only network controls.

Different notifications start at Introduction. Leaving a view aborts obsolete
reads and detaches its polling/render work. Server-owned imports, catalog updates
and submitted operations remain independent.

## Catalog and scheduled acquisition

Initial catalog population uses every compressed NVD annual 2.0 feed, with
checksum verification, per-year checkpoints, full raw records and the existing
product/risk indexes. API updates cover modifications after the oldest imported
snapshot, with overlap and resumable checkpoints. Already complete catalogs are
reused. Download, decompression, parsing, indexing and storage timing are exposed.

Saved schedules cover NVD, EPSS, KEV and selected Shadowserver report families.
A scheduled report run is successful only after its Accretion imports finish.
Lookback overlap catches late reports; bounded date windows catch up after missed
runs. Errors and partial outcomes remain visible. Reference-update failure does
not block report intake when a complete usable catalog already exists.

Optional Windows Task Scheduler integration runs under the current signed-in
user without placing API credentials in task arguments. It does not open a
browser. A foreground launch requests cooperative handoff; the scheduled process
retains its workspace lock until workers stop. The default workspace task is
removed on uninstall. Signed-out operation is not supported by this task mode.

## Migration and validation

Schema 15 adds canonical tables and backfills from retained evidence. It does not
rewrite original imports, case membership, entity snapshots, frozen section JSON
or generated report packages. Missing or changed historical originals produce
migration warnings instead of invented observation counts. Existing pre-upgrade
restore/backup protections remain in place.

See root VALIDATION.md for the actual automated and live results, including
platform limitations. This release remains unstable pending Windows acceptance.
