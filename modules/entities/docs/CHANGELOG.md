# Entities changelog

## Unreleased

## 0.12.0

- The entity directory and dossier show the completed-notification count and latest delivery date for the canonical entity. Merged identities share the history maintained by Investigations. [Notification history verification](../../../docs/history/validation/intake-review-2026-11-22.md#workflow-and-upgrade-evidence)
- The entity detail query reads the profile and its review summary in one database snapshot, so a concurrent contact edit cannot leave those views out of step. Accented place names are preserved on Windows. [Entity data ownership](README.md#boundary)
