# 0.9.81 Chaos validation

Chaos is an experimental comparison edition. It remains unstable, with its own
installation and data namespace. This record distinguishes executed automated
checks from workstation acceptance still pending. The prior release's record is
preserved in docs/VALIDATION_098.md.

## Verification environment

Python 3.14.10, the existing pinned dependencies, Node 24 and Playwright 1.62.1
were used on Linux. Browser checks use Debian Chromium headless shell 150 with
host-required no-zygote/single-process flags; the application does not require
those flags. Local fixture servers and browsers run in the same process tree.
No runtime dependency upgrade is included. No GitHub push was performed.

Final aggregate counts and individual results are in the accompanying validation
bundle. The verification report explicitly records native_windows_acceptance=false.

## Executed checks

- Cross-record search: bound/escaped queries, bounded result groups, read-only
  behavior, minimal result DTOs, empty titles, recent results, keyboard selection,
  stale/debounced request handling, disposal, focus return and direct entity,
  Library and import-detail destinations. Search text and tokens are not persisted.
- Workspace: lightweight saved-state overview avoids report-file integrity reads.
  Integrity checks remain on file access/export. Leads filters, counts, sorting,
  40-row display pagination, escaping and route restoration are exercised.
- Eclipse: exact source-derived graph relations, provenance, all five lenses,
  date cutoffs, map placement, undated/unplaced records, bounded output, empty/error
  states and navigation. A synthetic 147-row/39-endpoint/six-entity browser fixture
  exercises Field, Atlas and Pulse without external traffic. Decorative stars
  never enter record counts or relationships.
- Observatory projection benchmark: 30,000 synthetic rows and 15,000 distinct
  endpoints projected in 1.41 seconds on this host, producing 595,075 bytes with
  300 displayed nodes, 240 edges and 24 connection cards. This measurement excludes
  database/source parsing and browser rendering; it is not an end-to-end latency
  claim. Truncated nodes/edges are reported. The underlying source loader still
  reads full workspaces; extremely large source sets need separate validation.
- Contacts: fax suppression, recruiting/media/department classification, focused
  URL boundaries, duplicate routes with preserved provenance, source excerpts,
  known-contact reuse and blank-only autocomplete. Real-browser checks cover
  desktop/mobile and light/dark presentations, without live network traffic.
- Contact replay: eleven domains use retained, SHA-256-checked public-page
  captures. Wasabi's security/support addresses remain available while fax
  numbers are removed; JB Hunt retains product support and restricts recruiting.
  This is an offline replay, not a new live-site run. Blocked, absent and incomplete
  results are retained, including missing replay pages. No completeness claim is
  made about contact discovery or current public contact details.
- Evidence reader: local search/filtering, keyboard controls, stable record links,
  source summaries, no-JavaScript fallback, mobile layout and local hash checking,
  including a deliberately changed file. The reader makes no automatic network
  requests. The clean synthetic sample contains 30 files and 27 readable records.
- Recipient output: the representative PDF text and DOCX document.xml match the
  0.9.8 specimen. Native PDF and LibreOffice DOCX conversion both remain nine pages,
  with three appendix pages. This does not establish Microsoft Word layout.
- Section freezes: existing content-only freeze regression remains in the full
  suite. Chaos does not reintroduce rendering when a section is frozen.
- Copied workspace compatibility: opening a synthetic 0.9.8 workspace and restoring
  its backup into another folder preserves historical record fields, 109 protected
  files, all 15 checked historical download hashes per phase, and all 15 historical
  frozen-section states. Original source/report bytes remain unchanged.
- Edition isolation: source/installed launchers reject the standard installed
  workspace path; installer identities, directories, registry, mutex, shortcuts,
  logs, restore points and ports are separate. Synthetic cross-edition overlay and
  reset safeguards pass. Both NSIS editions compile with warnings treated as errors.

## Remaining workstation acceptance

Native Windows installation/launch/side-by-side operation, native credential
storage, desktop Word, real screen-reader behavior and issued Shadowserver API
credentials remain untested for this edition. The installer is unsigned.
See HOME_VALIDATION.md for a short comparison procedure. Automated passage and
cross-platform installer compilation do not promote Chaos to a stable release.
