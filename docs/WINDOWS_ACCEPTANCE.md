# Guided Setup Windows acceptance

This checklist covers 0.12.1. The recorded earlier Windows baseline remains 0.9.96.
Automated Linux checks and cross-compilation do not confirm this release on Windows.

This checklist owns the manual acceptance steps. Track completion in
[ISS014](ISSUES.md#iss014-current-version-windows-acceptance), with the exact
source/build identity, installer SHA-256, Windows version, display scaling,
relevant application versions and a pass/fail/not-run outcome for each step.
Retain failures and limits with the record; mark acceptance only for the tested
artifact. [Observatory's checklist](../modules/observatory/docs/OBSERVATORY_ACCEPTANCE.md)
provides its detailed feature checks without replacing this release gate.

1. Close the application and wait for scheduled work to finish. Export a backup
   before upgrading. Install as a standard user with existing data retained;
   confirm normal startup, repeat launch and Demo isolation.
2. Open the Observatory entity map. Compare a known entity's marker and details
   with its saved profile. Several associated assets, findings or observations
   must not produce duplicate entity markers or inflate the primary entity count.
3. Confirm a complete supported saved U.S. city/state
   takes priority. Remove city/state in a synthetic profile and confirm placement
   falls back to city/state from the most recent associated IP/hostname report in
   the selected scope. Confirm its source, IP/hostname and date are explicit and
   the point is approximate Census geography, not raw IP coordinates or an address.
   Confirm a complete unsupported saved location remains unplaced. If the latest
   report lacks usable city/state, confirm an older report is not substituted.
4. Change filters and observation time range. Confirm the displayed evidence
   scope, counts, selection and details agree. Saved-profile geography stays current;
   report fallback follows the selected cutoff and shows its report date. Neither
   should imply a historical entity address. Unplaced entities stay discoverable.
5. Exercise clustered markers, zoom, pan, resize and selection on the workstation.
   Confirm each entity can be reached, selection persists or clears consistently,
   supporting records open correctly, and labels/tooltips remain readable at the
   normal Windows scaling and browser zoom levels.
6. Verify an existing certified report and its recorded history remain unchanged.
   Create and certify a new synthetic report and inspect PDF/DOCX rendering.
7. Verify desktop --self-test, backup/restore, scheduled-run handoff, relaunch and
   uninstall with records retained. Retain the existing native AMSI/security
   acceptance checks; do not disable workstation protection.
8. Record exact-version outcomes before stable promotion. The installer is unsigned.

## Added workflow acceptance

9. In Demo or another isolated synthetic workspace, import a case containing a public and private IP. Confirm the scope warning prevents certification, exclusion requires a reason, the recipient report omits the excluded finding, and internal source evidence remains available. Review a previously certified report with an anomalous row without altering its historical files.
10. Edit all Prepare outreach fields. Try close, Escape, navigation and tab close with unsaved changes. Save, restart, and confirm the exact text returns. Change a contact or verification route and review the context warning; verify stale windows cannot overwrite newer work. Copy only; do not send test messages.
11. Configure a synthetic agency/office and a name with no title. Read the cover, narrative, security text, closing text, reply address and verification route. Change Settings and confirm an existing draft stays pinned until explicit adoption.
12. Freeze sections, change entity details, and review/apply the adoption dialog. Confirm only affected sections reopen, the reason is retained, stale versions fail safely, and Workspace opens the correct next step.
13. Read single-CVE, EOL-only, multiple-CVE, long-name and omitted-appendix PDF/DOCX outputs. Check first action, product/version labels, references, page breaks and closing DRAFT labeling. Open DOCX in Word and check layout there.
14. Export and restore a workspace containing saved outreach and scoped observations. Confirm exact text, holds, closed records and prior certified PDFs survive restart. Repeat a prior finding and import a new finding for the same entity; confirm history is not conflated.

## Added Workspace Evolution acceptance

15. Open Settings → Workspace health. Start/cancel a scan, review each store and storage totals, and confirm unrelated editing remains usable. Review a cleanup estimate and verify only expired lookup pointers are removed; original captures and certified reports remain available.
16. In an isolated synthetic workspace, dismiss then restore a finding with a reason. Confirm the review lists affected work and a stale review cannot overwrite a newer decision. Transfer a hostname and an entire domain between two businesses; old cases retain their owner, the new business needs its own attribution, and old dismissed/delivered work does not suppress new-owner findings.
17. Choose Compact for a new synthetic notification before section validation. Read its PDF and DOCX in native Word, open the internal complete report and exhibit gallery, and verify citations and appendix handling. Full remains the default; changing edition after review requires reopening affected sections.
18. Start a report render and edit unrelated administrative work. Confirm the app stays responsive; a change to the same case or its reviewed evidence prevents publication. Check restart recovery after an interrupted render.
19. With the app closed, exercise documented offline check, backup restore and compaction on a synthetic copy. Confirm a verified checkpoint is preserved and a damaged/future-schema workspace can be inspected without normal startup. Never use destructive fault injection on operational data.

## Guided Setup acceptance

20. Install as a standard user at 100%, 150% and 200% display scaling. Read the welcome, progress and finish pages; verify Eclipse icons in shortcuts and Windows Apps. Continue directly to setup without administrator rights.
21. In a new synthetic workspace, finish setup with manual imports and no API keys. Choose an agency, custom organization and a name without a title. Exit midway and restart; completed steps must persist. Test keyboard navigation, Escape, unsaved-change prompts and narrow browser windows.
22. With authorized test credentials, connect APIs, choose a jurisdiction and review the report choices. Recognized other-state subscriptions must be absent. Change jurisdiction after saving a schedule; stale requests must fail visibly until corrected. Verify national/custom scope remains clearly described.
23. Enable signed-in, closed-app acquisition with saved Windows credentials; verify Task Scheduler registration, status, actual execution and foreground handoff. Session-only credentials must not enable closed-app retrieval. Disable and re-enable without losing saved selections.
24. Open Settings, edit then cancel/leave each relevant section, and verify save/error/dirty states. Reopen guided setup and What’s New. Confirm the version notice appears once per installed version and remains available manually.
25. In an isolated installation, complete normal uninstall/reinstall, leave generated Python caches, and simulate a missing old interpreter. Repair must use the new installer runtime, preserve records and unrelated Python, and stop with an actionable message on unknown files or locked deletions. Exercise overlapping managed launches, interrupted replacement, missing local ownership metadata and task-action migration using the [guarded-launch protocol](../tools/windows_installer/REFERENCE.md#guarded-launch-and-maintenance). Verify no Python startup before the install gate is released, no launch with incomplete readiness, and recovery of the task's original enabled intent. Respect the explicit first-upgrade policy for older direct launchers.
26. After a compatible update is published to an accessible distribution feed, check, download, review and install it. Verify checksum failure and a running report prevent handoff, launch failure unlocks the current app, successful handoff retains records and restarts, and the new version’s notice appears. Never publish a test update merely to satisfy this checklist.
27. Record exact installer SHA-256 and outcomes before promotion. This candidate remains unsigned; portable tests and NSIS compilation do not replace these Windows checks.
