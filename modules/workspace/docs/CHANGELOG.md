# Workspace changelog

## Unreleased

## 0.12.0

- Use one date for a dashboard render so its heading, requests and due-date
  links agree when the workspace stays open across midnight. Workspace now
  owns the search, brief and queue routes. [ISS029](ISSUES.md#iss029-workspace-file-ownership-and-consolidation)
- Coordinate the schema 24 upgrade and backup restore. Verification from
  schemas 20 and 23 preserved historical reports and evidence, including a
  draft case's attachment. [Upgrade and restore evidence](../../../docs/history/validation/intake-review-2026-11-22.md#workflow-and-upgrade-evidence)

## 0.11.1

- Expose the current-work queue at `/api/workspace/queue`. The earlier
  `/api/today` URL continues to use the same handler.
