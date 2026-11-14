# 0.9.81 Chaos release changes

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Chaos is an unstable comparison edition of Shadowserver Companion. It builds on
0.9.8's independent Entities and Leads, content-only freezes, compact appendix and
readable evidence packages. The work concentrates on finding records quickly,
understanding reported connections and making internal evidence easier to inspect.

## Compare without replacing 0.9.8

The Windows edition uses **Shadowserver Companion Chaos** shortcuts and a separate
installed-app identity. Program files live under
`%LOCALAPPDATA%\Programs\ShadowserverCompanionChaos`; working data, demo records,
logs, pending transfers and restore points use the separate
`%LOCALAPPDATA%\ShadowserverCompanionChaos` namespace. Ports 8879/8880 allow the
normal edition's working/demo sessions on 8877/8878 to remain open.

Chaos setup and uninstall check the separate install location. Upgrade cleanup
rejects cross-edition program inventories, and a fresh start targets only its own
data. Source archives extract under `shadowserver-companion-chaos` and use Chaos's
ports by default. Launchers identify the edition and refuse the normal installed
data directory as an explicit workspace.

For a comparison, export a backup from 0.9.8 Settings, import it in Chaos Settings,
and restart Chaos when prompted. The copy is checked before replacement. There is
no search for private folders, automatic migration from the other installation or
synchronization of later edits. Retain the original export and normal workspace.

## Workspace, Leads and Search & jump

Workspace opens with a focused work item, due follow-ups, stage counts and saved
activity. Its overview reads workflow records without opening or hashing report
packages. Current local-date filters keep the due count and work list aligned.
Leads adds ready, known-entity, new-entity and unresolved-match views, sorting and
paging. Starting a notification remains explicit.

Ctrl+K opens a keyboard-driven command palette. Search entities, notifications,
incoming leads, source filenames and Library explanations, including associated
hostnames, IPs and reported findings. Results provide short summaries and open the
record's own route. `>` searches navigation commands. Changing a query invalidates
old results; closing or destroying the interface cancels outstanding UI work.
Search is bounded and read-only, does not request external intelligence and does
not save its queries in browser storage.

## Eclipse Observatory

| View  | What it shows                                                                              |
| ----- | ------------------------------------------------------------------------------------------ |
| Field | A selectable graph of endpoints and identifiers recorded together                          |
| Atlas | Reported coordinates or approximate city areas, with unplaced observations still available |
| Pulse | Dated local observations and returning identifiers, with undated records retained          |

Five lenses organize these views: **Finding, Shared IP, Organization, Service and
Version**. Search, entity/network/status/intelligence filters and date controls
narrow the selection. The Records view and inspector expose supporting rows,
source dates, recorded attribution and links to original files and existing work.
Coverage limits and unavailable originals remain visible.

Edges describe co-occurrence in preserved rows. Shared infrastructure does not
establish common ownership or compromise. First-seen/returning dates describe the
local scan history; missing days are not negative scans or proof of remediation.
Workflow overlays describe current saved work. Graph layout is presentation, not
additional evidence; bounded examples are not the complete support set.

## Contact findings

Contact values are presented first, with their purpose, copy/fill controls and
expandable source detail. Security and useful technical-referral contacts can be
shown together. Known contacts remain available without another website request;
blank-field autocomplete remains immediate and preserves typed values.

Fax and recruitment/HR detection is more specific. New extraction avoids treating
fax numbers as voice routes, while retained historical fax/recruitment evidence
remains accessible and is excluded from routine suggestions. Unavailable, partial
and incomplete searches stay distinguishable. No message is sent and no mandatory
verification step is added.

## Internal evidence workspace

New internal packages extend `Evidence_Record.html` with local search, category
filters, keyboard access and collapsible detail. The file index accepts explicitly
selected files or an extracted folder and compares SHA-256 hashes locally. It
reports matches, changed files and files not selected; nothing is uploaded.
The ordinary records and original links remain readable when scripting is disabled.

The check compares bytes with the saved index. It does not establish authorship,
and the reader itself remains covered by the final package manifest. Keep the
package folder intact. Historical certified packages are not rewritten to add the
new reader, and recipient exports remain separate from internal evidence.

## Continuity and acceptance

- Section freeze still locks content without rendering; explicit preview and
  certification own page generation. Historical reviews and packages retain their
  original records and bytes.
- The 0.9.8 appendix and existing recipient PDF/DOCX presentation remain in place.
  Chaos's interface and internal reader changes do not introduce a new recipient layout.
- Schema 10, pinned report identity, explicit entity-detail adoption, receipt-backed
  API intake and the existing dependency pins remain in place.
- The live Shadowserver account, native Windows install/credential behavior and
  live contact-site checks have not been accepted for this build. Automated and
  synthetic browser results are reported separately in [VALIDATION.md](../../../VALIDATION.md).
- `edition: chaos` and `channel: unstable` remain explicit. Chaos cannot be promoted
  to stable in place. Version 0.8.0 remains the last accepted stable release.

Use [HOME_VALIDATION.md](../../../HOME_VALIDATION.md) for the comparison checklist and
[DEVELOPMENT.md](../../../DEVELOPMENT.md) to reproduce checks. This release does not claim
complete production validation, native Windows acceptance or publisher signing.

