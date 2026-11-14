# 0.9.92 — Accretion, entity directory and API setup

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Accretion now shows the current report moving through Filter, Qualify and Urgency,
with row counts, attribution progress and saved temperature totals. Import history
is collapsed below the controls. Recent patterns summarize exclusions, admitted
products and locations across the latest evaluation of up to 20 original files.

Both Files and API import views warn prominently when the local CVE catalog is
missing, incomplete, unavailable or overdue for an update. Each intake retains its
catalog readiness at scoring. Downloading the catalog later does not relabel old
scores as fully informed. Reimporting the same file after the catalog changes
permits a fresh evaluation; original files and historical notifications remain intact.
This is a warning, not a hard import block: EOL and report-supported findings remain usable.

Eligible ISP-owned domains are retained and receive a 90% outreach-ranking reduction.
Quality, CVSS, KEV and other factual risk data do not change. The saved score explains
the adjustment. Customer domains hosted on ISP addresses do not receive this penalty.
Historical exclusions are not silently resurrected; explicitly re-evaluate the original
report if those findings are wanted.

Entity identity can be initialized from the organization containing the exact matched
RDAP field. Each filled name/address field retains its source URL, retrieval time,
JSON pointer and evidence identifiers. Existing manual details and notification
snapshots are preserved. DNS association alone does not turn a network provider's
registration into a customer's company identity.

Entity overview puts the primary domain, mailing address, contact card and original/
latest observation dates before the connection graph and analytical findings. The
entity directory shows names, addresses and actual email/phone/form information.
It uses specific information-gap labels instead of generic approval tasks. A business
name, mailing address and usable email or telephone are sufficient to remove the
entity review reminder; this does not claim recipient confirmation or delivery.

One Find all control queues missing-contact checks. Complete routes are skipped;
per-entity Refresh contacts deliberately queues another search. These searches use
the existing single-worker background service, retain manual contact choices and
finish without holding up intake. Directory contact reads run in bounded parallel
batches and update individual cells. Navigation discards stale responses, keeps
forms intact, and shows immediate opening feedback.

Database schema 14 adds registry field provenance and contact queue modes. An upgrade
backup is created before migration. Use the application backup before changing
installed versions; do not open a schema-14 workspace with an older executable.
The release remains unstable pending the workstation acceptance checks.

NVD and Shadowserver are first-class API connections. Shadowserver Data opens on
the API tab; Files remains available. Settings presents both connection states and
the NVD key control. Windows Credential Manager keeps saved keys outside working
records and backups. NVD credentials are sent only in the API request header, never
in evidence URLs or browser persistence.

The initial full CVE download now uses the authenticated NVD API with 2,000-record
pages, bounded response sizes and one shared, conservatively paced request budget.
Completed pages and their resume cursor commit together. Cancellation or network
failure preserves completed pages. Invalid or repeated pagination cannot mark the
catalog ready; shifted coverage restarts its page check without deleting stored
CVEs. Daily last-modified updates use the same key and retain the existing catalog.
The complete collection is not downloaded again for routine updates. Previously
completed feed-based catalogs migrate directly to keyed incremental updates.

