# 0.9.93 — Data navigation hotfix

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

The sidebar uses `#data`. The API-default change in 0.9.92 rendered the API view
correctly, then the router attempted to initialize the absent file drop zone.
That null-element error replaced the completed view with an error screen.
The explicit `#data?tab=api` route skipped that initialization and worked.

Upload handlers now initialize only when the rendered view contains the drop
zone. The binding function also safely handles an absent element. This removes
the conflicting assumptions about the default tab.

The regression test exercises the real router, Data renderer and upload binding
for the sidebar/default route, explicit API and Files tabs, legacy Imports link,
unknown-tab fallback and return navigation. It reproduces the error before the
fix and passes afterward, including a file-drop handoff to the importer.

All 0.9.92 functionality is retained. Database schema 14, intake policy, catalog,
credentials, dependency pins, artwork and report generation are unchanged.

