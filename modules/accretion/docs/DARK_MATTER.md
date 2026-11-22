# Dark Matter archive contract

[Module guide](README.md) · [Pipeline](PIPELINE.md) · [Report schemas](REPORT_SCHEMAS.md) · [Operations](OPERATIONS.md)

Dark Matter owns complete source-row retention, field normalization, outcome
history and archive queries. Its public interface is
[dark_matter.py](../components/dark_matter.py); storage lives in
[dark_matter_store.py](../components/dark_matter_store.py). Consumers call that
interface instead of building archive identities, SQL or private retention formats.

## Scope and identity

The archive accepts malformed identifiers, missing values, unsupported reports,
outside-region rows and unknown fields. It performs no admission, attribution,
website capture, scoring, contact discovery or canonical finding creation.
Observatory owns archive presentation; Leads and Investigations use canonical
Awareness for actionable findings and case history.

Each record is identified by original file SHA-256, sheet and row number. Different
reports of the same hostname/IP remain separate source occurrences. Reimporting
the same bytes and source position reuses normalization and appends decisions;
different original fields under an existing identity are rejected. Original
fields are never overwritten by a later decision. Source metadata retains import
membership and the original file path; each outcome retains its import ID.

All nonempty report rows enter the current intake archive, including candidates
awaiting qualification. Wholly empty spreadsheet padding is ignored. A container
failure without trustworthy row positions becomes one source-level record at row
zero, referencing the retained original file. Normal rows keep their real positions.

## Storage and transaction boundary

The independent `<workspace>/dark_matter.sqlite3` database contains `sources`,
`records`, `outcomes`, `observed_fields`, `delivered_events` and `archive_state`.
The owned schema is [dark_matter_schema.py](../databases/dark_matter_schema.py),
currently version 1. Common record selectors have indexes; arbitrary fields use
the retained JSON projections.

The workspace database contains only the durable `dark_matter_outbox` delivery
queue. The stage commits its own state and outbox entries together. Delivery
commits the archive first and acknowledges the workspace event afterward. Event
IDs make a crash between those commits safe to replay. This does not depend on
atomic commits across two SQLite WAL databases.

Workspace composes `store.dark_matter`, drains committed work at startup and after
transactions, and includes both archive and pending deliveries in backup/restore.
A delivery failure leaves pending work visible through `delivery_status`; it does
not turn an already committed business transaction into a rollback. Recovery and
workspace lifecycle belong to [Operations](OPERATIONS.md) and
[Workspace data management](../../workspace/docs/DATA_MANAGEMENT.md).

## Write APIs

| API | Contract |
| --- | --- |
| `prepare_batch(import_record, rows, *, stage="filter", outcome="rejected", reason="")` | Project and serialize source rows into immutable deliveries of at most 500 rows before reserving the workspace writer. Rows may carry their own report type, outcome and reason. |
| `enqueue_prepared(db, prepared)` | Enqueue those deliveries inside the caller's transaction; returns event IDs. |
| `enqueue_batch(db, import_id, rows, *, stage, outcome, reason)` | Convenience entry point when rows are already available inside a transaction. Large Filter results use the preparation API outside the writer. |
| `enqueue_outcome(db, import_id, entries, *, stage, outcome, reason="")` | Derive identities from existing source entries and enqueue one shared disposition. |
| `enqueue_outcomes(db, import_id, decisions, *, stage)` | Accept `(entry, outcome, reason)` tuples and group matching dispositions without copying or normalizing source fields again. |
| `drain(root, *, archive=None)` | Deliver committed events in sequence; acknowledge only successfully delivered events. |
| `DarkMatterStore.record_batch(source, rows, ...)` | Direct archive writer used by delivery and isolated callers; stores rows and decisions in one archive transaction. |
| `DarkMatterStore.record_outcome(record_ids, *, import_id, stage, outcome, ...)` | Append history to existing rows. A missing row is an error for unsuccessful outcomes; promotion of a never-archived row is an explicit no-op. |

Rows can be `SourceObservation`, `CandidateObservation` or the established
dictionary shape containing `source.sheet`, `source.row` and `source.fields`.
Direct `record_batch` source metadata requires `import_id` and a lowercase
SHA-256 digest (`sha256` or `source_sha256`); it also accepts name/path, report type,
schema version and acquisition metadata. Pipeline callers use the enqueue APIs so
they do not assemble this source descriptor themselves.

```python
from modules.accretion.components.dark_matter import prepare_batch, enqueue_prepared

deliveries = prepare_batch(
    imported, rejected_rows, stage="filter", outcome="rejected", reason="outside_jurisdiction"
)
with store.transaction() as db:
    enqueue_prepared(db, deliveries)
    # Commit the caller's matching import/job state in this same transaction.
```

Promotion is retained history, not deletion. `promoted`, `qualified`, `associated`
and `lead` outcomes mark a record as promoted. That marker is monotonic: a later
rejection does not put an already promoted source occurrence back into the
default archive selection. Use `include_promoted=True` to inspect those records.
Stage/outcome/reason strings are retained as supplied; `REASONS` supplies display
labels, including historical labels, rather than an exhaustive admission schema.

## Field normalization

[dark_matter_fields.py](../components/dark_matter_fields.py) owns normalization
version 1. The pinned inventory currently declares **177 reports and 746 field
names**; [Report schemas](REPORT_SCHEMAS.md) distinguishes this inventory from the
26 notification adapters. Storage does not depend on an adapter being enabled.

The archive keeps `raw_fields`, `normalized_fields` and per-field `errors`.
Known IP/hostname, port, ASN, timestamp, boolean and selected numeric fields get
cheap typed conversions. Ports must be 0–65535; ASNs 0–4294967295; coordinates
must be finite and within latitude/longitude bounds. Timestamps become UTC.
Known protocol/severity text is lowercased. Unreviewed values retain their meaning;
normalized strings may be trimmed, but software versions are not interpreted.

Malformed values keep their raw representation, receive a diagnostic and normalize
to null. Empty values normalize to null without a diagnostic; absent keys remain
absent. Dates/times use ISO text in the JSON-safe raw projection, and nonfinite
numbers use an explicit tagged representation. The original file remains the
byte-level source. There is no clipping of long values or dropping unknown columns.

`field_catalog(report_type=None)` combines pinned fields with observed extensions
and returns field types, known/unknown status, report membership, inventory digest
and normalization version. It describes storage; it cannot authorize qualification.

## Read APIs and filters

`query(filters=(), fields=None, sort="recorded_at", limit=25, offset=0,
include_promoted=False, q="")` returns items, total, pagination and outcome counts.
`get(record_id)` returns a complete record with ordered outcome history, or `None`.
`revision()` supports change detection. Reads open existing storage read-only.
`archive_counts(db)` and `delivery_status(db)` read diagnostics from their owning
archive and workspace snapshots respectively.

```python
page = store.dark_matter.query(
    filters=[
        {"field": "port", "op": "eq", "value": 443},
        {"field": "hostname", "op": "invalid"},
    ],
    fields=["hostname", "ip", "port"],
    limit=25,
)
```

Filters are ANDed. Operators are `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`,
`in`, `exists`, `missing` and `invalid`. `source` defaults to `normalized`; `raw`
selects original fields. `invalid` consults diagnostics. Normalized `missing`
excludes malformed fields, so invalid and absent/empty values remain distinguishable.
Values are bound parameters; unsupported operators and nonscalar values are rejected.

Limits are 32 predicates, 100 values per `in`, 300 characters per field/search term,
1000 selected field names and 1–100 rows per page. Selected fields restrict the
three field projections, not record metadata. Sort keys are the common record
columns defined by the component; `+` sorts ascending, while the default or `-`
sorts descending. `q` searches raw values, reason and source filename.

`facets(field, filters=(), limit=50, *, include_promoted=False)` counts common or
normalized field values, capped at 100 buckets. `iter_records(filters=(), *,
include_promoted=False, limit=100000)` streams complete records from one read
snapshot. Consumers should close a partially consumed iterator promptly.

## Verification

Run `python -m pytest -q modules/accretion/tests/test_dark_matter_store.py` for
storage identity, normalization, query and delivery contracts. Archive lifecycle,
rollback/restore and Observatory integration also have owner suites linked from
the [module verification guide](README.md). Historical refactor measurements and
acceptance evidence remain in [ISS025](ISSUES.md#iss025-isolate-complete-dark-matter-storage).
