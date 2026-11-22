# Entities tracking

This tracker owns Entities maintenance work. Last reviewed: **2026-11-22**.
Use the [module guide](README.md) for current contracts and verification, and
the [project register](../../../docs/ISSUES.md) for shared work and the global
index. Follow the [issue lifecycle](../../../docs/ISSUES.md#maintaining-this-register)
when adding, resolving or deferring an item.

## Module work

| ID | Work | Status |
| --- | --- | --- |
| ISS044 | [Qualified website contact scope](#iss044-qualified-website-contact-scope) | Open |
| ENT-01 | [Canonical notification history](../../investigations/docs/README.md#completed-notifications) across linked leads and merged entities | Implemented |

## ISS044 Qualified website contact scope

Qualify can retain a functioning HTTP or related non-www subdomain website, while
contact discovery currently authorizes only HTTPS on the approved apex/www pair.
[ISS043](../../accretion/docs/ISSUES.md#iss043-associate-scope-and-component-boundaries)
reuses retained captures within that existing contract and adds bounded counterpart
fallback. Other qualified URLs still use apex/www discovery and may miss contacts.

**Done when:** an explicitly retained related hostname and HTTP origin can seed
contact discovery through the owning scope, transport, extraction and saved-evidence
validation APIs. Preserve exact-host authorization, tenant boundaries, redirect and
request budgets, contact provenance and focused single-page rechecks. Do not bypass
those shared contracts in Accretion or silently widen a root to every subdomain.


## Related work

These entries retain their status and completion evidence in the owning tracker:

- [ISS027 Qualify decisions and workflow](../../accretion/docs/ISSUES.md#iss027-qualify-decisions-and-workflow) owns the current ownership API, transfer-bound qualification token and removal of repeated schema probes.

- [ISS026 Reusable tools and duplicate capabilities](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities) covers shared suffix extraction and identity comparison; Entities retains contact eligibility and entity scope.

- [ISS004 Workspace facades and models](../../workspace/docs/ISSUES.md#iss004-workspace-facades-and-models) covers owned request validation and consistent entity detail snapshots.
- [ISS005 Workspace queue presentation](../../workspace/docs/ISSUES.md#iss005-workspace-queue-presentation) covers the owned entity directory interface.
- [ISS007 Entity presentation in Leads](../../leads/docs/ISSUES.md#iss007-entity-presentation-in-leads) covers dossier ownership and lookup teardown.
- [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures) covers fixtures imported by other module tests.
- [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage) covers registration of focused contact-browser checks.
- [ISS009 Explicit resource encoding](../../../docs/ISSUES.md#iss009-explicit-resource-encoding) covers valid accented place names under Windows text defaults.
