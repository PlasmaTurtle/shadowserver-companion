# Attribution issues

Module-owned maintenance work belongs here. Last reviewed: **2026-11-22**.

[Maintenance guide](README.md) · [Project issue index](../../../docs/ISSUES.md)

## Module work

### ISS056 North Carolina business-registration import

**Status:** Awaiting authorized subscription or agency access and a representative
weekly extract. Attribution owns acquisition, refresh and matching. Entities
owns applying reviewed matches to current profiles. This is an application
integration separate from the standalone attribution engine.

The state describes weekly CSV files, distributes a dictionary with the
subscription, and publishes a relational layout. The published layout includes
corporations, legal and historical names, contacts linked by role, addresses,
filings and status lookups. The November 22 schema check created all 18 tables
in a fresh SQLite file. Two synthetic profiles shared a display number without
collision, and each legal name, agent, officer and office address remained
independently addressable. The [module guide](README.md#north-carolina-business-registration-layout)
includes the command and field mapping. [State data description](https://www.sosnc.gov/online_services/data_subscriptions/about_the_data) · [Subscription fees](https://www.sosnc.gov/fees/by_title/_data_subscriptions?area=Divisions)

**Next deliverable.** Compare a licensed sample and its delivery dictionary
with the local layout, including filenames, encoding, headers, type codes,
source date and complete-snapshot semantics. Refresh an indexed snapshot
atomically, preserve its source date and status, and demonstrate identical
reimports and removal of withdrawn source rows. Keep the previous valid
snapshot available on failure. Public interactive searches are for individual
use. [State bulk-access guidance](https://www.sosnc.gov/online_services/search)

**Acceptance.** Verify supported, ambiguous and absent matches on representative
business IDs, legal names and addresses. Display the specific source record
and snapshot. Prefill missing entity fields only for a supported match, retain
manually supplied values, and exercise the existing case-snapshot adoption
workflow. Verify the separate meanings of principal address, registered address,
registered agent and operating contact against the sample before mapping them.

## Shared work and dependencies

| Canonical item | Attribution involvement |
| --- | --- |
| [ISS027 Qualify decisions and workflow](../../accretion/docs/ISSUES.md#iss027-qualify-decisions-and-workflow) | Own explicit group decisions, authoritative proof reuse/coverage and cancellation; Accretion owns workflow/reconciliation |
| [ISS026 Reusable tools and duplicate capabilities](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities) | Compare DNS/IP identity contracts and preserve independent engine packaging; existing HTTP/DNS reuse is already established. |
| [ISS004 Workspace facades and models](../../workspace/docs/ISSUES.md#iss004-workspace-facades-and-models) | Own application review-request validation independently of the engine API |
| [ISS016 Bulk feed deadlines and cancellation](../../library/docs/ISSUES.md#iss016-bulk-feed-deadlines-and-cancellation) | Own the additive managed stream, bounded resolver and engine package/lock integrity |
| [ISS010 Legacy intake network path](../../accretion/docs/ISSUES.md#iss010-legacy-intake-network-path) | Review engine input and compatibility needs before migrating legacy callers |
| [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures) | Keep application fixtures separate from standalone engine tests |
| [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage) | Review application attribution browser checks and their fixtures |
| [ISS014 Current version Windows acceptance](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance) | Record current application evidence separately from historical engine validation |

Use the [project tracking rules](../../../docs/ISSUES.md#maintaining-this-register).
Update a shared item's canonical record rather than copying its status here.
