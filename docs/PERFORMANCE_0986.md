# 0.9.86 — Performance and resource audit

November 11, 2026 · America/New_York · Compared with delivered 0.9.85.

The release makes four measured backend changes. It preserves the application's
experience, full evidence and existing features. It does not introduce a new
storage architecture, cache invalidation scheme, reduced visual quality or
truncated results for minor efficiency gains.

## Measured results

Production paths were exercised against 500, 2,500 and 10,000 synthetic entities,
each with eight observations and one saved notification. Timings below are the
median of five calls at **10,000 entities / 80,000 observations** on the same
Linux host, CPython 3.14.10 and SQLite 3.53.1.

| Operation | 0.9.85 | 0.9.86 | Improvement |
|---|---:|---:|---:|
| Workspace queue | 7,607.53 ms | 852.09 ms | 8.93× |
| Pending Leads | 1,113.64 ms | 225.96 ms | 4.93× |
| Associate 100 groups | 2,801.18 ms | 2.40 ms | 1,166.63× |
| One entity's notification list | 103.64 ms | 1.43 ms | 72.63× |
| Navigation counts | 1,646.19 ms | 601.44 ms | 2.74× |
| All Leads | 1,123.49 ms | 712.25 ms | 1.58× |
| Entity list (unchanged control) | 1,341.18 ms | 1,381.21 ms | No improvement claimed |

The large association ratio reflects removal of repeated scans of unrelated
history. It is not a claim that the entire importer or application is 1,166×
faster. The entity list was not optimized; the approximately 3% difference at
this size is reported, not concealed or treated as evidence of a general gain.

### Scaling check

Each cell is **0.9.85 → 0.9.86**, in milliseconds; five-call medians.

| Operation | 500 entities | 2,500 entities | 10,000 entities |
|---|---:|---:|---:|
| Associate 100 groups | 98.70 → 2.90 | 588.51 → 2.27 | 2,801.18 → 2.40 |
| Pending Leads | 44.75 → 10.70 | 258.60 → 72.44 | 1,113.64 → 225.96 |
| One entity's notification list | 4.36 → 1.34 | 23.35 → 1.24 | 103.64 → 1.43 |
| Workspace queue | 382.85 → 43.79 | 1,894.65 → 185.98 | 7,607.53 → 852.09 |

All **21 operation/size comparisons** returned identical normalized JSON.
Every repeated and instrumented result matched its operation's hash. Hashes of
all saved table rows, including row identifiers, matched between versions and
before/after read measurements. These are strong fixture-specific preservation
checks, not a proof for every possible workspace.

## What changed and why

| Path | Previous work | New work and bounds |
|---|---|---|
| Hostname/IP association | For each incoming group, scan unrelated domain/hostname and observation history. | Split root and hostname branches into indexable lookups; add expression and covering indexes. For a fixed number of lookup keys, work depends on index search and actual matches rather than all retained history. |
| Pending Leads | Project every disposition; repeatedly decode payloads and check observations with individual SQL calls. | Filter stored dispositions before projection, reuse parsed source data, and check pending existence in batches of at most 500 identifiers. All displayed observations remain present. |
| Selected notification flags | Read and deserialize every saved draft, including unrelated entities. | Read only selected case IDs in bounded batches. An all-case view still includes every selected case. |
| Workspace contacts/history | Open and close a SQLite connection per entity, repeatedly discarding its page cache. | Reuse one read-only snapshot for these facts. The overall queue remains proportional to its input and keeps its sorting, priorities, holds and details. |

For Q fixed-size association requests, H stored hostnames and E observations,
the eliminated scans grow roughly with Q × (H + E). Indexed lookups instead
depend on Q × (log H + log E), plus matching rows and small union/deduplication
work. Actual results can still be large for shared infrastructure.

For C saved cases and S selected cases, draft retrieval changes from processing
all C drafts to approximately S indexed lookups plus the selected draft bytes.
The queue changes primarily reduce wasted work and SQL round trips; they do not
make an unbounded list O(1). Hashing and exporting complete evidence remain
proportional to the bytes processed, as required for integrity and completeness.

At the largest fixture, Pending Leads executes **13,340 SQL statements instead
of 200,004**, including traced connection/transaction statements. Association
keeps 603 statements but falls from approximately 60,006,000 SQLite VM steps to
15,000. The query count alone would have missed that improvement. Query plans
confirm indexed root/hostname searches and the covering IP index.

## Write and storage cost

The two new indexes occupy **3,133,440 bytes (2.99 MiB)** on the 80,000-observation
fixture: 2,818,048 bytes for the IP/owner index and 315,392 bytes for the lowercase
hostname index. The database grows from 229,875,712 to 233,009,152 bytes, about
**1.36%**. Indexes are a measured tradeoff, not free performance.

Five committed 1,000-row batches on disposable clones spanned 1,000 existing
entities, with SHA-256 observation IDs like production. Median commit-inclusive
insertion times were:

| Rows inserted per transaction | 0.9.85 | 0.9.86 | Added median time |
|---|---:|---:|---:|
| 1,000 observations | 60.50 ms | 70.29 ms | 9.78 ms |
| 1,000 hostnames | 2.83 ms | 3.70 ms | 0.86 ms |

WAL, foreign keys and `synchronous=FULL` were retained. Row counts, foreign-key
checks and SQLite integrity passed. These are local synthetic index-write
measurements, not end-to-end importer throughput or native Windows disk latency.
The earlier hot-key pilot was replaced by this broader final probe. The bounded
write/storage cost is acceptable for the measured read gains; no durability or
evidence checks were weakened.

## Memory

A separate traced-heap probe for one entity's notification list at 10,000 saved
drafts fell from **82,014,168 bytes to 11,084 bytes**. This measures temporary
Python allocations during that call, including the removed deserialization of
unrelated drafts. It is not total application memory and excludes native SQLite
allocations. Main-run peak RSS includes fixture setup in the baseline and is not
used for an overall memory reduction claim.

## Local catalog findings

No catalog code changed. A separate synthetic workload exercised ingestion,
indexing, exact retrieval, prefix/description search, Critical/KEV product
summaries and field density at 10,000, 50,000 and 200,000 records.

At 200,000 records, median timings were **0.63 ms** for exact CVE retrieval,
**1.93 ms** for prefix search, **2.61 ms** for description search, **25.74 ms**
for Critical CVEs, **105.18 ms** for Critical products, **24.97 ms** for KEV
products and **111.58 ms** for field density. SQLite integrity passed.

These fictional records contain one affected product/version, one CVSS
assessment, a weakness and sparse NVD-embedded KEV data. They do not reproduce
every shape in the real catalog, and this is not a live EPSS/CISA synchronization
benchmark. The fixture's product cardinality is 2,000. It supports retaining the
existing indexed design; it does not establish latency for arbitrary real-world
catalogs. Streaming acquisition, batched writes, complete reference fields,
atomic risk snapshots and evidence hash checks remain intact.

## Preservation and verification

- Four runtime implementation files changed, plus release identity. All 63
  static assets and all catalog module sources are byte-identical to 0.9.85.
  Dependency pins and wheel hashes are unchanged.
- Dedicated regressions cover external workflow assignment of pending/deferred/
  dismissed leads, 1,001 observations crossing the SQL batch boundary, 1,001
  selected drafts, empty selection and bounded association work against 10,000
  unrelated entities. No wall-clock threshold is imposed in unit tests.
- The actual 0.9.85-to-0.9.86 upgrade and restore rehearsal preserved 109 protected
  files, three report packages, 15 validations, saved logical records and every
  one of the 15 historical download hashes in each phase.
- Schema 11 adds only two indexes with the existing pre-migration backup and
  atomic migration. Older executables reject schema 11; rollback requires a
  pre-upgrade backup. See RELEASE_0986.md and HOME_VALIDATION.md.
- VALIDATION.md and the companion validation archive record final automated
  checks. The installer remains unsigned and unstable. No native Windows,
  real-browser, enterprise-policy, Word-layout or GPU acceptance is inferred.

## Method and practical limits

Fixtures contain no real targets. Network calls are blocked during application
read measurements. The same saved workspaces are cloned for the upgraded runs.
Direct repository operations are measured directly; API operations also include
their production response serialization. JSON comparison serialization and SQL
instrumentation run outside the timed interval. These are backend measurements,
not click-to-paint timings.

Raw JSON records all five samples, first-call timing, CPU time, SQL counts,
approximate VM steps, response hashes, platform, code hashes and database size.
No OS page-cache flush was performed, so first calls are not described as truly
cold disk reads. Repetitions in one process mostly measure warmed operation.
There is no claim of statistical confidence, production traffic coverage, native
Windows latency, GPU frame rate or reduced live-provider latency.

Run `python tools/benchmark_0986.py --workspace <new-synthetic-folder> --groups
10000 --repeats 5 --output <results.json>` with the pinned developer environment.
Use `--root <baseline-source-folder>` for 0.9.85; `--measure-memory` adds a
separate allocation probe. Existing directories without this harness's own
fixture marker are rejected. Never point it at a working workspace.

The validation archive includes final paired JSON, the comparison, query plans,
write-cost and catalog probe scripts/results. Fixture databases and synthetic
source datasets are excluded from the distributables.

## Technical references

- SQLite query planning: https://www.sqlite.org/queryplanner.html
- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
- SQLite optimizer overview: https://www.sqlite.org/optoverview.html

These explain index/search behavior; the performance conclusions above come
from the actual measurements and query plans for this application.
