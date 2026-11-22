# 0.12.0 — Guided Setup

- Review CVE and end-of-life findings in separate views of the same lead. Open the reported host or its root site, enlarge the saved screenshot and continue to the next lead after a decision.
- Qualify the page actually reached and reuse recent verified captures. Associate records internal notification history and external referrals with separate exact-host and whole-domain scopes.
- Apply the same qualification rules to workbook uploads, manual API imports and scheduled imports. Reimporting a report preserves one lead. Data shows how many source rows passed Filter, how many domain groups reached each later stage, and why a group stopped.
- Rank leads by their outstanding findings. Resolved findings and withdrawn CVEs no longer inflate priority. Qualified government sites receive a preference in the review queue.
- Search complete imported rows in the Dark Matter archive, including malformed and out-of-region rows, and inspect their intake decisions. Observatory counts each source row once when it also appears as a case observation.
- When a referral excludes one hostname, keep the eligible sibling's findings and screenshot together through lead review and report certification.
- Count a notification once, on its first recorded delivery. Leads and Entities show the same count and last delivery date, including after case revision and entity merges.
- Start with guided setup for API connections, agency identity and jurisdiction, then optional automatic acquisition. Resume unfinished setup and keep API secrets in the existing credential services.
- Organize Settings around identity, jurisdiction, connections, automation, report defaults, data and software. Support agency presets, a custom agency and a name without a title.
- Filter recognized state-specific API subscriptions by the saved jurisdiction. Revalidate catalog requests and scheduled imports when scope changes; retain clearly labeled national and custom account subscriptions.
- Give Observatory national city lookup and a saved-jurisdiction map context while preserving entity identity and location provenance.
- Modernize the Windows installer with Eclipse artwork, clearer progress and a direct handoff to setup. Repair app-owned Python residue using a fresh installer runtime, including when the previous interpreter is missing or damaged.
- Add in-app release checks, verified installer downloads, an explicit install-and-restart action and versioned What’s New. Updates retain the workspace and wait for active work to finish.
- Make catalog downloads stop during stalled headers or trickling responses, enforce transfer and decoded-size limits, and retain completed data after cancellation.
- Search local CVEs, products and explainers together in Library. Save named research views in the workspace and keep their filters through a catalog refresh. A failed sync shows the last success and leaves downloaded records available.
- Compare and restore explainer revisions with their citations, recover a draft after a conflicting edit, and see which cases use the wording. Reviewing a source change preserves the text already certified in a report.
- Use the same NVD severity assessment in Library and intake. Product searches include versions that become affected later in a published range, and unfiltered catalog pages load faster.
- Download NVD's public annual feeds and run incremental updates without an API key. A key is still required for a full catalog download through the API.
- Keep entity profiles and review summaries consistent during concurrent updates, preserve accented place names on Windows, and clean up pending lookups and upload listeners when views close.
- Preserve keyboard focus when asynchronous command-palette results update.
- Recover a disconnected view with Reload app. Connection errors link to the local server health check and distinguish an interrupted read from a write whose outcome needs checking.
- Restore consistent case and lead completion after interrupted certification, while retaining stale packages as history and preserving certified file bytes.
- Capture the reported website first and fall back to its main site after a load failure. Use native Edge/Chrome loading for redirects, cookies, API requests, images and video; remove the custom request broker and resource restrictions. Wait for the visible page and preserve original/final URL, fallback and screenshot provenance.
- Block site-initiated downloads during capture. When the browser reports an attempt, retain its time and outcome without saving the file.
- Guard installed Python startup before file replacement, retain launch protection across child processes, and keep interrupted upgrades repairable with their original scheduling intent.
- Organize application code, tests and documentation by module. Shared runtime tools own reusable operations such as website capture, and Investigations owns the resulting case evidence.
- Add a tool to create an empty local database from North Carolina's published business-registration schema. Loading the weekly data and matching businesses still require authorized source data.
- Keep this build a release candidate. Native Windows acceptance and publication of compatible update assets remain separate release steps.

# 0.11.1 — Workspace naming consistency

- Align documentation, source module/function names, UI helpers/styles, tests and benchmarks with Workspace. Its priority queue is part of the existing feature.
- Use `/api/workspace/queue` in the app and API documentation. Keep `/api/today` only as a hidden compatibility alias to the same handler.
- Preserve queue behavior, schema 20, stored records, report wording and dependency pins.

# 0.11.0 — Workspace Evolution

- Add append-only finding/observation qualification events and explicit legacy-unknown provenance without erasing known historical qualification or case disposition.
- Strengthen case/section ownership and JSON constraints; separate immutable evidence revisions from replaceable lookups and bind certified artifacts to saved manifest digests.
- Add reviewed ownership transfers and reasoned finding reactivation. Preserve recorded ownership and prevent a new business from inheriting prior notification/dismissal status or attribution approval.
- Batch Workspace priority-queue contact/case reads, scope Observatory details, maintain incremental analytical summaries with reconciliation, index current source selection, and bound planner maintenance.
- Add background workspace health, safe cleanup estimates, independent offline recovery and controlled compaction with verified checkpoints.
- Add an explicit compact recipient edition and shared package resources; full remains default and compact packages retain a separate complete report.
- Render reports outside the workspace write lock and recheck case revisions, review identities and source integrity before publication.
- Keep capture jobs busy until cleanup finishes, and use indexed root-domain ownership lookups as unrelated history grows.
- Preserve the approved template, historical files, installation/data identity and dependency pins. Exact-version native Windows acceptance remains outstanding.

# Earlier releases

See the [consolidated changelog before 0.11](docs/history/releases/CHANGELOG_PRE_0.11.md)
for 0.10.1 and earlier. Historical release claims retain their original scope.
