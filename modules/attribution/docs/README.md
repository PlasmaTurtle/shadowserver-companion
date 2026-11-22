# Attribution maintenance guide

Attribution owns registration/DNS evidence, analyst identity approvals,
group proof reuse, supplemental asset checks and the application's integration with
the standalone attribution engine. Use this guide for application maintenance;
the engine retains its independent package documentation.

[Module issues](ISSUES.md) · [Changelog](CHANGELOG.md) · [Architecture](../../../docs/ARCHITECTURE.md) ·
[Project maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow) ·
[Library selection](../../../docs/DEVELOPMENT.md#library-selection)

## Boundary

Evidence and analyst decisions remain distinct from automatic qualification and
report presentation. Preserve immutable endpoint evidence and the distinction
between unresolved, reviewed and automatically qualifying results. The
Investigations module owns the rendered Attribution report section.

The engine keeps its own package/version, source integrity, dependencies and
tests. Application adapters supply explicit engine inputs; the engine must not
import application modules.

### Qualification interface

`RegistrationAttribution(store, config, cancel_event=...)` owns the existing
engine lifetime. `qualify(group)` returns an `AttributionDecision` containing
`status`, `proof`, `result_id`, `attempts` and `coverage`. It does not reorder
source rows, change their fields, or store its result in mutable client state.
The application's Qualify stage owns website evidence and complete lead creation;
Attribution supplies only the attribution decision.

One accepted hostname/IP match covers the related group sharing that hostname
or root. Each coverage row records its original source location, hostname/IP,
relationship and original proof reference. A new address in the same group does
not demand a new lookup, and does not rewrite the original proof's address.
`coverage_covers(entries, proof)` checks a complete scope in linear time;
`coverage_matches(entry, proof)` checks one observation independently of report
display order. Ownership still belongs to Entities and is checked by Accretion
before work and at publication; attribution reuse never merges entities.

`attribution_reuse.reuse_attribution()` validates the exact stored result,
snapshot, captured record and policy before reusing a saved proof. Automatic
evidence has a seven-day reuse window. Manual evidence requires its actual
recorded analyst approval and current entity; embedded approval text is not
sufficient. `reuse_review()` evaluates compatible new partial evidence against
the existing recorded registrant approval. Both return the same decision contract.
Legacy proofs without immutable result references are not reusable.

The saved proof is checked before older approvals are enumerated. `EvidenceReader`
caches immutable evidence within one operation; mutable ownership, approvals and
job state are never cached. Accretion obtains an ownership token through Entities
before website or provider work and rechecks that bound owner after capture and
at publication. Ownership changes require qualification to restart; they cannot
silently bind an earlier owner's evidence to the new owner. The token includes
ownership episodes, so a transfer away and back is detected. Qualification no
longer scans historical endpoint findings to impose the per-address gate.

Case assets show whether support comes from the original matched address, the
group relationship or an additional individual lookup. Covered assets do not
enter the remaining-asset batch. An analyst can explicitly refresh an individual
asset through the existing API; adopting that evidence records new group
coverage for the case while preserving the entity's original proof.

Shutdown cancellation reaches RDAP request queues, authority pacing, retry waits
and the existing bounded HTTP capture, as well as DNS. An interrupted provider
return cannot publish a match. User pause remains an Accretion workflow decision,
distinct from shutting down an in-flight request.

The engine's `matching.normalize_domain` remains the canonical live DNS parser
for application adapters and Contact discovery. It uses the existing
[`idna` UTS46 implementation](https://github.com/kjd/idna#compatibility-mapping-uts-46).
Application display/report adapters share Tools' `comparison_address` for
IPv4-mapped equivalence, while keeping their existing return/error contracts.
The engine retains its own independently packaged IP parser; persisted ingestion
keys use the separate compatibility contracts documented by Accretion.

The engine's `bounded_http.stream_response()` provides managed incremental I/O
for Library bulk feeds. Library owns provider trust, retries, credentials and
publication; the engine owns response lifetime, total network budget, bounded
decoding and resolver admission. Existing `capture_response()` behavior remains
unchanged. See the [streaming contract](../components/engine/REFERENCE.md#bounded-streaming-http).

`components/api_models.py` owns the application's attribution-review request
model. It is separate from the independent engine's public models and can be
imported without Workspace initialization.

## North Carolina business-registration layout

Create an empty local copy of the state's published registration schema with
the project interpreter. Give it a new file outside the repository and the
casework database. For example, from the repository root on Windows:

```powershell
python -m modules.attribution.tools.create_nc_registry "$env:TEMP\nc-business-registration.sqlite3"
```

The command creates the 18 export tables in a new SQLite file and preserves any
existing destination. The [SQLite layout](../databases/nc_business_registration.sql)
uses the state's field names, including its spellings of `Citzenship`,
`DisolveDate` and `Desctription`. Text fields preserve leading zeros in display
identifiers and ZIP codes. Corporate identity is `Corporations.PItemId`.
`CorpNum` may repeat. Join `Corporations.EntityID` to `Names.EntityID` and use
`NTypeID=1` for the current NC legal name. A reservation or previous name alone
cannot establish a current legal identity. [Official export dictionary](https://www.sosnc.gov/documents/forms/Data_Subcriptions/Business_Registration_layout.pdf)

Keep the corporation's `OfficeAddressID` and `OfficeMailingID` separate from
addresses of its `AgentEntityID`. Use the provider's address types to identify
registered-office roles. `CorpOfficers` contains current officer records. An
officer or registered agent needs separate evidence before being treated as an
operating or technical contact. [Registered agent duties](https://www.sosnc.gov/divisions/business_registration/registered_agent_links)

The empty file supports schema inspection and local SQL queries. Verification of
weekly refresh, address role codes, candidate matching and entity enrichment
requires the authorized export tracked in [ISS056](ISSUES.md#iss056-north-carolina-business-registration-import).

## Source ownership

| Location | Maintained responsibility |
| --- | --- |
| [components/attribution_bridge.py](../components/attribution_bridge.py) | Application integration with the standalone engine |
| [components/attribution_approval.py](../components/attribution_approval.py), [attribution_approval_evidence.py](../components/attribution_approval_evidence.py), [attribution_reuse.py](../components/attribution_reuse.py) | Analyst approval evidence and authoritative group reuse; Accretion owns waiting-job reconciliation |
| [components/asset_attribution.py](../components/asset_attribution.py), [databases/asset_attribution_migration.py](../databases/asset_attribution_migration.py) | Supplemental case-asset lookups and their immutable application history schema |
| [components/engine/](../components/engine/) | Independently installable library, source, package metadata, tests, offline wheels and standalone launch/setup commands |
| `tools/Attribution.cmd` | Application-checkout launcher using the root development environment |
| [static/attribution.js](../static/attribution.js), `tests/` | Application presentation, delegated review handlers and integration regressions |

The engine's bundled wheels and launchers are required by its separate offline
distribution. They are not replacements for the application environment. Engine
database migrations stay with the library; application schema definitions live in
`databases/`. The adjacent `src/attribution/` tree is the maintained engine source.
The checkout launcher is source-only; installed users open Attribution in Eclipse.

`attribution.js::createHandlers(ctx)` supplies review clicks and form submissions
directly to UI's delegated event dispatcher. Workspace does not proxy those handlers.
Review payloads retain the selected result and evidence identity. See
[Workspace ISS029](../../workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation).

## Verification and maintenance

With the [project development environment](../../../docs/DEVELOPMENT.md#windows-ide-setup)
active, run from the repository root:

```text
python -m pytest -q modules/attribution/tests
python -m pytest -q modules/attribution/components/engine/tests
python tools/check_dependencies.py
```

The dependency check verifies engine source against its bundled wheel and the
application/standalone dependency inventories. Standalone engine source changes therefore
require a deliberate package, wheel and manifest update using the
[project dependency workflow](../../../docs/DEPENDENCIES.md#release-verification).
Use the shared [verification guide](../../../docs/DEVELOPMENT.md#verification)
for the affected application integrations and frontend checks.

Application fixtures use this module's `tests/support/` interfaces. Independent
engine fixtures live in `components/engine/tests/attribution_test_support/` and
must work with the standalone engine test command without the app's test harness.
Neither suite imports builders from another test or browser entry point.

Record module work in [ISSUES.md](ISSUES.md). Update the application contract here
and the standalone reference when a change crosses that boundary; retain earlier
validation results with their original version. Follow the shared
[documentation maintenance rules](../../../docs/README.md#keep-the-documentation-dependable).

## References

| Document | Scope |
| --- | --- |
| [Standalone engine](../components/engine/README.md) | Independent installation, CLI entry and component development |
| [Engine reference](../components/engine/REFERENCE.md) | Matching, retrieval, evidence, storage and Python API contracts |
| [Engine dependencies](../components/engine/DEPENDENCIES.md) | The engine's offline bundle; application locks remain at the repository root |
| [Engine validation](../components/engine/VALIDATION.md) | Historical component test records; not current application acceptance |
| [Windows acceptance](../../../docs/WINDOWS_ACCEPTANCE.md) | Current application workstation gate |
