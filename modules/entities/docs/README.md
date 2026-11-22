# Entities

Entities owns business profiles, entity validation/review, ownership and
lifecycle, contact discovery/evidence, contact outcomes and entity history.
This guide describes where to maintain that behavior and which contracts to keep.

[Architecture](../../../docs/ARCHITECTURE.md) · [Entities tracking](ISSUES.md) ·
[Analyst workflow](../../../docs/USER_GUIDE.md#5-keep-organization-records-accurate)

## Start here

| Maintenance area | Start here |
| --- | --- |
| Entity mutations and caller-owned persistence | [services/entities.py](../components/services/entities.py), [repositories/entities.py](../components/repositories/entities.py), [qualified group persistence](../components/repositories/association.py) |
| Profile validation and review | [entity_review.py](../components/entity_review.py) |
| Ownership transfer and lifecycle | [ownership.py](../components/ownership.py) |
| Bounded website lookup and extraction | [contact_discovery/](../components/contact_discovery) |
| Contact jobs and retained results | [contact_jobs.py](../components/contact_jobs.py), [contact_records.py](../components/contact_records.py) |
| Contact candidate and retained-source validation | [contact_validation.py](../components/contact_validation.py) |
| Contact and lifecycle schema | [databases/](../databases/) |
| Contact presentation | [contacts.js](../static/contacts.js) |
| Directory, dossier and editing | [entities.js](../static/entities.js), [entities_events.js](../static/entities_events.js) |
| Request validation and consistent entity reads | [api_models.py](../components/api_models.py), [services/queries.py](../components/services/queries.py) |

## Boundary

Entities owns current organization/contact records. Attribution supplies identity
evidence; Investigations explicitly adopts changes into existing cases. Entity
merges and transfers preserve case ownership history, review guards and
caller-owned transactions. Discovery is bounded and does not send messages.

`ownership.association(db, root, entries)` resolves current hostname ownership
and historical/undated transfer review in a caller-owned snapshot. Shared IPs
never identify an entity. `ownership.qualification_context` adds the current
entity's saved Attribution proof reference; Attribution validates that evidence.
Accretion's local gate delegates to this API before website capture or providers,
and Evaluate/Associate recheck ownership under their own snapshots/transactions.
The returned `ownership_token` binds entity/state and active hostname ownership
episodes, independently of Attribution proof changes. Captured qualification
retains this token. `check_qualification_context` returns the current association
tuple only when it still matches; otherwise it raises `OwnershipChanged` and
requires a fresh qualification. A transfer away and back changes the episode,
so returning to the same entity cannot silently reuse evidence from the interval.

These current-Workspace APIs use the schema initialized by Workspace and do not
probe table or column availability per source row. Existing `context` and
`entry_context` share the same dated replay/transfer algorithm; their explicit
`schema_ready` path is used by current qualification and actionable finding scope.
Historical migration callers retain their compatibility check. Leads consumes
this owner API; it does not implement an alternative association resolver.

Contact scope and source URLs use Attribution's `normalize_domain` for UTS46
DNS identity, including Unicode names and one terminal root dot. For example,
`faß.de` normalizes to `xn--fa-hia.de`, consistent with the entity's attribution,
and remains distinct from `fass.de`; Greek final sigma likewise retains its
UTS46 identity (`βόλος.gr` becomes `xn--nxasmm1c.gr`). Contact-specific
public-host, HTTPS and approved-company rules remain in `contact_discovery/policy.py`; identity
normalization does not widen those rules or rewrite saved contact records.

[Tools network identity](../../tools/components/network_identity.py) owns the
offline private-suffix-aware PSL lookup and mapped-IP comparison. Entity DNS
requires an actual registrable root; ownership/lifecycle use the explicit
`root_domain` fallback contract. Contacts retains its tenant-boundary rule.

`entity_view(workspace, repository, entity_id)` owns the entity detail query. It
uses one read snapshot for the profile and completeness summary, so a concurrent
contact update cannot combine an older profile with a newer review status.
Mutations continue to use their existing caller-owned transactions.

The module owns profile/review/rename/merge request models. They can be imported
without initializing Workspace or other application modules. Entity place names
are read explicitly as UTF-8 from Observatory's bundled geography resource;
operating-system text defaults must not change valid names.

Browser `install(ctx)` returns the directory/dossier actions registered with the
shell. The legacy `leadTable` and `leadsPage` action names remain compatible, but
their implementation is owned here. `createHandlers(ctx)` owns edits, filters
and lookup events; its `dispose()` cancels pending lookup timers and invalidates
late responses. Installation itself starts no requests or listeners.

## Association and automatic enrichment

[Accretion Associate](../../accretion/docs/PIPELINE.md#associate) calls
`repositories.association.record_group` inside its guarded publication transaction.
Entities owns entity/domain anchors and retained observation rows; Accretion owns
canonical finding admission. `contact_queue.queue_initial` requests initial contact
work without restarting existing jobs. Registry field seeding preserves manual
values and field-review history.

`contact_website.starting_url` verifies a retained website through Investigations
and supplies an eligible HTTPS apex/www crawl seed. `start_url` keeps ordinary
bounded link discovery; `source_url` remains a focused single-page lookup. A failed
homepage may try its approved counterpart within existing budgets. Contact absence
requires complete coverage of every previously cited source; unvisited or unreadable
sources preserve the existing candidate. HTTP/other subdomain seeds remain
[ISS044](ISSUES.md#iss044-qualified-website-contact-scope).

## Contact validation

`contact_validation.validate_candidate(store, row)` and
`validate_contact_data(store, entity_id=None, *, allow_unavailable_legacy=False, evidence_factory=EvidenceStore)`
own contact candidate, review and captured-source consistency checks. ContactRecords
uses the same owner for review and export; Workspace invokes it during backup/restore
and health inspection. The historical `allow_unavailable_legacy` option remains
explicit rather than weakening ordinary contact validation.

Workspace health supplies its read-only evidence factory to avoid creating or
migrating an Attribution database during inspection. Backup validation uses the
isolated staged workspace. Entities defines contact meaning; Workspace owns
inspection budgets, transaction/lifecycle policy and whether a replacement proceeds.
Shared representation/scanning rules remain in
[Input validation](../../../docs/INPUT_VALIDATION.md). Ownership consolidation is
tracked in [Workspace ISS029](../../workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation).

## Supporting folders

Use the [shared folder definitions](../../../docs/ARCHITECTURE.md#find-the-owner)
for placement. Contact and ownership-lifecycle migrations live in `databases/`;
working records stay outside the source tree. Contact discovery's transport,
extraction, policy and persistence remain separate because they enforce different
boundaries. Case-owned saved outreach presentation lives in
[Investigations](../../investigations/static/outreach_preparation.js).

## Verification

Run checks from a configured source checkout, following
[Development](../../../docs/DEVELOPMENT.md#working-in-a-module). Start with the
affected tests; the complete module suite is:

```text
python -m pytest -q modules/entities/tests
```

For profile review and ownership changes, start with `test_entity_review_080.py`
and `test_entity_lifecycle_0110.py` in `modules/entities/tests/`. Contact-specific
commands are below. Use [project verification](../../../docs/DEVELOPMENT.md#verification)
for frontend, cross-module and registered browser checks.

`test_entity_query_consistency.py` exercises a concurrent contact update during
detail projection. `test_entity_resource_encoding.py` checks accented place names
under a non-UTF-8 default; `test_entities_interface.cjs` exercises the owned
directory/dossier interface independently of Leads installation.

## Maintenance and tracking

Follow the [maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow).
[Entities tracking](ISSUES.md) records module-owned work and links to shared
presentation and test work. Keep current profile/contact behavior and lifecycle
commands explicit; changes to presentation must preserve historical ownership
and case-adoption semantics.

## Contact discovery verification

Backend tests inject synthetic website responses into the real discovery engine,
job service, review and contact-plan flow. They do not look up live businesses.

Run the contact workflow checks with:

```text
python -m pytest -q modules/entities/tests/test_contact_discovery_090.py modules/entities/tests/test_contacts_store_090.py modules/entities/tests/test_contacts_api_090.py modules/entities/tests/test_contacts_invariants_090.py modules/entities/tests/test_contacts_end_to_end_090.py
```

The routine contact group covers retained evidence, handoff and current contact
presentation. The focused lifecycle group checks request admission, cancellation
and navigation polling with the same synthetic provider fixture:

```text
python tools/verify.py --only-browser --browser-suite contacts --report build/contact-browser.json
python tools/verify.py --only-browser --browser-suite contacts-lifecycle --report build/contact-lifecycle-browser.json
```

The verifier creates and closes each fresh fixture, supplies current launcher
authentication and blocks external requests. The maintained script/setup catalog
is `python tools/verify.py --list-browser`; see
[browser registration](../../../docs/DEVELOPMENT.md#working-in-a-module).
`contacts_browser_fixture_090.py` remains the shared provider/data fixture;
the old 090/095 browser scripts are retired. Historical contact outcome policy
remains covered by the owning backend and portable UI suites. Direct fixture
metadata contains local test session material, not release documentation.
