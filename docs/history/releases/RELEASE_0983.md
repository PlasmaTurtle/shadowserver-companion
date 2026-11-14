# 0.9.83 — Local CVE Library

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Dark Matter gains a searchable local copy of the public NVD CVE catalog. One bulk
download supplies the historical records; daily API updates bring in both new and
modified records, including rejections. The current source feeds measured about
236 MiB compressed and 2.72 GiB of uncompressed JSON on November 10, 2026. These
figures change as NVD grows and are not the final SQLite database size.

## Library

Open Library and start the catalog download once. Import runs in the background;
completed years are retained if it is interrupted. Search and record details read
the local catalog. Existing report explainers remain available in Library.

Daily updates become enabled when the download starts. The app checks when an
update is due while it is running, and catches up on the next launch after being
closed. A closed application or sleeping computer cannot run its in-app updater.
Sync now, cancellation and the daily-update control remain available in Library.
No NVD API key is required. This is independent of the Shadowserver API key.

## Source integrity

The initial import verifies NVD's published SHA-256 hashes of the uncompressed
annual feeds. Incremental synchronization uses modification dates, pagination
and bounded catch-up windows. An unsuccessful page or feed does not advance its
completion checkpoint. NVD request pacing applies across the catalog and direct
NVD lookups in the same application process.

NVD reference lookups consult the local catalog first. Selected records still
produce immutable evidence snapshots with the original source, retrieval date,
record hash and catalog provenance. Catalog updates do not change frozen reports
or adopt new source revisions into investigations. Other providers, including
FIRST EPSS, CISA KEV and CVE Program supplements, retain their own retrieval rules.

The full catalog is reference information. Its entries are not automatically
counted as observed vulnerabilities, attributed to entities or added to cases.
NVD ingestion can trail CVE Program publication; unpublished reserved records
are not part of this public catalog.

## Installation and storage

0.9.83 upgrades the existing Dark Matter installation and retains its ports and
workspace identity. Keep Retain existing data selected. 0.9.8 and 0.9.81 remain
separate installations. The 0.9.82 startup hotfix is retained.

The rebuildable catalog lives beside the working workspace in
`data-reference/nvd/catalog.sqlite3`; a source workspace uses its own corresponding
`<workspace>-reference` directory. It is excluded from working-record backups.
Evidence snapshots selected into reports remain inside those backups. Initial
import needs additional temporary disk space for decompression and transactions.
The application installer does not embed the multi-gigabyte public database.

## Sources

- [NVD bulk feeds](https://nvd.nist.gov/vuln/data-feeds)
- [NVD CVE API](https://nvd.nist.gov/developers/vulnerabilities)
- [NVD development guidance](https://nvd.nist.gov/developers/start-here)
- [NIST information-use notices](https://www.nist.gov/copyrights-disclaimers)

This product uses data from the NVD API but is not endorsed or certified by the NVD.

See VALIDATION.md for executed results and remaining acceptance. Native Windows
execution is not established by Linux tests or installer compilation.

