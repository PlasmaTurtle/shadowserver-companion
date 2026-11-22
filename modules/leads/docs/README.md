# Leads

Leads owns qualified lead queues, frontier/scope selection, eligibility policy
and safe lead export contracts. This guide maps maintenance work to those
responsibilities.

[Architecture](../../../docs/ARCHITECTURE.md) · [Leads issues](ISSUES.md) ·
[Analyst workflow](../../../docs/USER_GUIDE.md#4-review-leads-and-decide-what-deserves-outreach)

## Start here

| Maintenance area | Start here |
| --- | --- |
| Queue persistence and current frontier | [lead_queue.py](../components/lead_queue.py), [lead_frontier.py](../components/lead_frontier.py) |
| Provider eligibility policy | [provider_policy.py](../components/provider_policy.py) |
| Scoped record access and export | [repositories/lead_scopes.py](../components/repositories/lead_scopes.py), [services/lead_exports.py](../components/services/lead_exports.py) |
| Queue schema and stable identity | [lead_queue_migration.py](../databases/lead_queue_migration.py), [queue_identity.py](../helpers/queue_identity.py) |
| Qualified queue and investigation actions | [entity_leads.js](../static/entity_leads.js), [entity_leads_events.js](../static/entity_leads_events.js) |
| Pending-lead HTTP queries and decisions | [routes/queue.py](../components/routes/queue.py) |

## Boundary

The [required Accretion product contract](../../accretion/docs/PIPELINE.md#qualify)
has Qualify return an evidence-backed lead, Evaluate add urgency/priority, and
Associate find contacts and enrich entity information. Leads consumes the retained
website evidence through Investigations' `website_evidence.projection` API. The
queue and detail show that capture's thumbnail and open its actual working URL.
The image route verifies the retained original, preview and metadata hashes;
opening Leads never starts a browser capture. Case creation adopts the same
original and preview through Investigations' evidence API.

The queue offers separate links for the reported hostname, its root domain from
intake's shared domain parser and the destination actually captured. The saved
image shows its capture time and opens at its original resolution.

The CVE and End of life views use the active findings attached to each lead.
A mixed lead appears once in each applicable view and shares its review decision
across both. Search, status, finding type and ordering apply before pagination.
Old Known/New filters fall back to All. Starting, deferring or ignoring a lead
refreshes the same selection and advances to the next available lead. Starting
the final lead opens its notification. The lead dossier shows the canonical
entity's last delivery date and links to its completed-notification history.

Qualified JSON exports carry `website_evidence` references alongside the original
rows and attribution proof. References identify the capture, actual requested and
loaded URLs, capture time/status and original SHA-256. Case exports identify their
adopted evidence revision; later entity captures cannot replace it. Filesystem
paths and image bytes remain in the evidence owner and retained report package.

Entities' `ownership.association` owns hostname association and dated transfer
checks. Leads calls that API when queue registration needs current context; its
internal reexport preserves existing callers without duplicating ownership logic.

Leads consumes Accretion qualification and Entities/Attribution context. Starting
or adding to an investigation remains an explicit analyst action. Lead exports
retain complete scoped rows and their established safety checks; they do not
invent attribution.

Accretion supplies qualified, scored groups only after its Evaluate stage.
`register_group` persists the supplied intake score. Frontier selection never
scores. `preview_scope` reads the complete pending condition scope, including an
incoming qualified lead, before Accretion's Evaluate component ranks it. This
keeps earlier actionable findings in the evaluation while excluding handled or
ignored conditions. Each score records the fingerprint of the scope it evaluated.

Accretion registers each accepted group once after its evidence exists, within
the job-completion transaction. Its optional `association_context` is resolved
inside that same transaction before entity writes; it is never a cached result
from the earlier Evaluate snapshot. Ordinary registration callers resolve their
own association. Frontier reconciliation parses each candidate payload once per
transaction and reuses those entries for scope selection and retirement. Associate
rechecks the evaluated scope under its transaction before changing canonical
records, then publishes that same checked selection. A changed scope must return
through Evaluate; it cannot trigger hidden scoring inside Associate. Explicit
edits to already-qualified work use Accretion's `evaluation.evaluate_pending` API
before publishing the revised queue projection.
See the [funnel diagram and process inventory](../../accretion/docs/PIPELINE.md#funnel)
and [ISS023](../../accretion/docs/ISSUES.md#iss023-remove-repeated-funnel-work).

Recurrence, approved findings and handled state come from Accretion's canonical
observation memberships and finding workflow APIs. Leads does not maintain a
second source-summary or repeat-sighting table, and does not read or mutate Dark
Matter storage. Frontier selection consumes those canonical facts; dismissal
calls the finding owner's `ignore_findings` operation. Entity merges use
`merge_entity_scope` to merge canonical ownership once and return affected queue
IDs; the owning command then evaluates and publishes the revised pending scope.
Notification condition scope records handled findings through Investigations'
`case_conditions.pin`; pinning a score has no additional workflow side effect.

Entities owns the entity directory, dossier and profile editing. Leads consumes
its presentation helpers and the shell's supplied actions; it does not install
or maintain the dossier. Lead start/disposition handlers remain here, and UI owns
shared workspace navigation. Preserve existing action names when changing this
composition.

## Supporting folders

Use the [shared folder definitions](../../../docs/ARCHITECTURE.md#find-the-owner)
for placement. `databases/` owns the lead-queue migration. `helpers/queue_identity.py`
owns the stable queue ID used by migration, current intake and entity lifecycle
operations. Runtime callers do not import migration implementations for that helper.
Queue association, frontier qualification and export projection remain distinct
operations; similar record fields do not make those files interchangeable.

## Verification

Run checks from a configured source checkout, following
[Development](../../../docs/DEVELOPMENT.md#working-in-a-module). Start with the
affected tests; the complete module suite is:

```text
python -m pytest -q modules/leads/tests
```

`modules/leads/tests/test_lead_frontier_0991.py` covers frontier behavior and its
entity/contact context. Queue identity changes also affect Accretion intake and
Entities lifecycle callers, so verify those boundaries. Use
[project verification](../../../docs/DEVELOPMENT.md#verification) for frontend,
cross-module and browser checks.

## Maintenance and tracking

Follow the [maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow).
[Leads issues](ISSUES.md) owns planned module changes and completion criteria.
Update this guide when responsibilities change, preserving action names,
cancellation, scoped evidence and navigation contracts during presentation work.
