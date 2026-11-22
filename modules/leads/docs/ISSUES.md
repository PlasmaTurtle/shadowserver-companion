# Leads issues

This tracker owns Leads maintenance work. Last reviewed: **2026-11-21**.
Use the [module guide](README.md) for current contracts and verification, and
the [project register](../../../docs/ISSUES.md) for shared work and the global
index. Follow the [issue lifecycle](../../../docs/ISSUES.md#maintaining-this-register)
when adding, resolving or deferring an item.

[ISS026 reuse work](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities)
includes provider policy's use of shared domain extraction. Leads retains provider
ranking and eligibility; generic suffix lookup no longer depends on intake.


Shared checks for this completed batch are recorded in the [November 21 validation](../../../docs/history/validation/maintenance-2026-11-21.md).
Individual entries retain their module benefit, scope and focused evidence.

## Register

| ID | Work | Status |
| --- | --- | --- |
| ISS007 | [Entity presentation in Leads](#iss007-entity-presentation-in-leads) | Resolved |

## ISS007 Entity presentation in Leads

**Owner:** Leads, coordinating with Entities.

Before this change, `modules/leads/static/entity_leads.js` mixed entity-detail
presentation with lead-queue behavior.

**Done when:** entity presentation has a clear Entities interface while Leads
retains queue and eligibility policy. Selection, scoped observations, action
names, cancellation, navigation and lead actions continue to behave consistently.

**Resolved 2026-11-21.** Entities owns the
directory/dossier, edits and lookup events. Leads retains qualification/start/
disposition presentation and consumes the supplied entity helpers. The Entities
interface runs without installing Leads; its disposer cancels pending lookups
and prevents late responses from updating an abandoned view. UI supplies shared
navigation and disposes every feature even if another disposer fails.

The affected DOM selection passes 44 suites; real Chromium navigation and Library
flows pass with no JavaScript errors or external requests. All 283 existing
action names and nine selected rendered/model outputs are preserved. Evidence
and the exact changed-file manifest are in the Codex workspace's
`validation/maintenance-batch-02/frontend-*` bundle. The local uncommitted change
is based on `efccc0a0f476bf83078b26694afa8fad0372047c`.

## Related work

These entries retain their status and completion evidence in the owning tracker:

- [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures).
- [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage).
