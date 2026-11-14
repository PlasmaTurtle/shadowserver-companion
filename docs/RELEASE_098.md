# 0.9.8 release changes

0.9.8 separates entities, incoming leads and notification work, removes page
rendering from section freezes, and makes final evidence readable offline.

- Workspace owns notification/report/delivery/closing workflow. Leads and Entities
  have independent routes and records; legacy links resolve to their owner.
- Schema 10 adds an independent lead queue and pinned case identity. Imports do
  not automatically create notifications. Shared/conflicting IP associations
  remain unresolved, and entity merges do not consolidate existing cases.
- Entity/contact edits preserve existing report reviews. Report identity updates
  are deliberate; historical artifacts remain byte-preserved.
- Freeze records content and locks editing. Explicit preview/certification owns
  rendering. Earlier review hashes remain readable without rewriting history.
- The compact appendix groups observations and omits empty categories. The full
  synthetic specimen reduces from 22 to three appendix pages with distinct links
  retained; originals and all imported fields remain in the internal record.
- Evidence_Record.html provides consistent readable summaries, expandable
  technical records, chronology, screenshots, contact sources and raw-file hashes.
- Contact results show findings first, reuse known contacts and allow immediate
  blank-field autocomplete. Larger bounded captures retain intact partial results.
- Shadowserver Data includes Files/API. The pinned standalone API source feeds
  original reports and receipts through shared intake with deduplication and
  cancellation. Credentials stay outside workspace records.
- Navigation and interface wording use Workspace, Entities, Leads, Attribution,
  Shadowserver Data, Eclipse Observatory and Library.

Runtime dependencies remain pinned. The release remains unstable pending native
Windows acceptance; live Shadowserver account verification awaits credentials.
See ../VALIDATION.md for executed checks and ../HOME_VALIDATION.md for the
workstation acceptance list. Prior recipient wording and explainers are retained.
