# 0.9.86 — Focused performance pass

This updates the existing **Dark Matter** installation. Export a backup first
and keep **Retain existing data** selected. This remains an unsigned, unstable
comparison release; native Windows acceptance is pending. No GitHub upload is
part of this delivery.

## What changes

Four runtime files address measured bottlenecks without changing the interface:

- Known hostname and IP association uses indexed lookups instead of repeatedly
  scanning unrelated entities and observations. Shared-IP ambiguity still requires
  review; no attribution standard is relaxed.
- Pending Leads filters stored dispositions before building complete rows, reuses
  parsed source data and checks unassigned observations in bounded SQL batches.
  Assigned leads created through other workflows remain visible. Displayed
  observations are not truncated.
- A selected notification reads exploitation flags from its selected saved
  drafts, rather than loading every draft in the workspace.
- Workspace reuses one read-only connection for contact and held-history facts
  instead of reopening SQLite for every entity. Priority, sorting, holds and
  contact details retain their existing behavior.

The approved eclipse, drift, frost, Observatory, catalog fields, CVSS/EPSS/KEV,
capture, report generation and evidence protections are unchanged. The catalog
workload check did not justify an additional rewrite.

## Measured effect

On a synthetic Linux workspace with 10,000 entities and 80,000 observations,
five-call medians were:

| Operation | 0.9.85 | 0.9.86 |
|---|---:|---:|
| Workspace queue | 7.61 s | 0.85 s |
| Pending Leads | 1.11 s | 0.23 s |
| Associate 100 groups | 2.80 s | 2.40 ms |
| Selected notification flags | 103.64 ms | 1.43 ms |

These measure production backend paths, not end-to-end browser loading. All 21
operation/size comparisons returned identical normalized JSON and preserved
saved logical rows. See [the performance audit](PERFORMANCE_0986.md) for the
complete results, complexity, write/storage cost and measurement limits, and
[validation](../VALIDATION.md) for the release checks.

## Upgrade and rollback

Schema **11** adds two indexes: `entries_ip_owner` and
`hostnames_name_lower`. It does not change record columns or values. The existing
pre-migration backup and atomic migration remain in place. The local CVE catalog
does not need downloading again.

Older executables reject schema 11. To compare or return to 0.9.85, use a separate
copy of your **pre-upgrade backup**; installing an older executable over the
upgraded workspace is not a rollback. Preserve any work performed after upgrading
before attempting a rollback. [HOME_VALIDATION.md](../HOME_VALIDATION.md) lists
the focused workstation checks.
