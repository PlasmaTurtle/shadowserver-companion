# Accretion issues

Module-owned maintenance work belongs here. Shared work is linked to its
canonical tracker so status and completion evidence have one maintained home.
Last reviewed: **2026-11-21**.

[Maintenance guide](README.md) · [Project issue index](../../../docs/ISSUES.md)

[ISS026 reuse audit](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities)
includes offline suffix extraction, identity compatibility and timestamp display.
Accretion retains admission, persisted identity and scheduling semantics.


Earlier maintenance-batch checks are recorded in the [November 21 validation](../../../docs/history/validation/maintenance-2026-11-21.md).
Individual entries retain their module benefit, scope and evidence for later changes.

## Register

| ID | Work | Status | Owner |
| --- | --- | --- | --- |
| ISS010 | [Legacy intake network path](#iss010-legacy-intake-network-path) | Resolved | Accretion; Attribution participates |
| ISS021 | [Enforce the intake funnel](#iss021-enforce-the-intake-funnel) | Resolved | Accretion; Leads, Attribution and Observatory participate |
| ISS023 | [Remove repeated funnel work](#iss023-remove-repeated-funnel-work) | Resolved | Accretion; Attribution and Leads participate |
| ISS024 | [Filter contracts and interruption](#iss024-filter-contracts-and-interruption) | Open | Accretion |
| ISS025 | [Isolate complete Dark Matter storage](#iss025-isolate-complete-dark-matter-storage) | Resolved | Accretion; Observatory, Leads and Workspace participate |
| ISS027 | [Qualify decisions and workflow](#iss027-qualify-decisions-and-workflow) | Open | Accretion; Attribution, Entities, Tools, Leads and Investigations participate |
| ISS031 | [Evaluate scoring matrix and active scope](#iss031-evaluate-scoring-matrix-and-active-scope) | Resolved | Accretion; Leads participates |
| ISS043 | [Associate scope and component boundaries](#iss043-associate-scope-and-component-boundaries) | Resolved | Accretion; Entities and Leads participate |
| ISS046 | [Typed Accretion handoffs](#iss046-typed-accretion-handoffs) | Resolved | Accretion; Attribution, Entities, Leads and Workspace participate |

## ISS046 Typed Accretion handoffs

**Resolved 2026-11-21.** The established stage order was stronger than
its code contracts: filtered rows were named leads, qualification held an opaque
group, and Association accepted a lead beside an unrelated score dictionary.
Report identity and the source/finding relationship depended on caller convention.
The improvement is to reject an invalid handoff before work or publication starts,
while retaining the existing source evidence and storage schema.

The current products are `Report`, `SourceObservation`, `CandidateObservation`,
`CandidateGroup`, `ReportCandidate`, `QualifiedLead`, `EvaluatedLead` and
`AssociationResult`. Filter returns typed report-bound candidates; Qualify alone
produces the evidence-backed lead. Evaluate returns the lead with an assessment
bound to its exact pending scope; Associate accepts that product and returns
publication references. The Report descriptor performs no database, browser or
provider work. Dark Matter remains an independent component API/database.

Constructors check source position and canonical IP, domain grouping, report
identity, supported admitted finding evidence, attribution coverage and retained
related website evidence. Source/profile metadata survives each handoff. Frozen
attributes and detached payloads prevent caller-owned inputs from changing an
existing product; downstream checks guard the remaining mutable source mappings.
Original findings are not destroyed during promotion. Only temporary candidate
processing state is released; source/archive/canonical history persists.

This pass removes the old prequalification type names and untyped preparation/
acceptance entry points without compatibility aliases. Job JSON and schema stay
unchanged. Automatic, manual/reconciled and explicit demonstration paths use the
same typed boundaries, with synthetic evidence labelled separately. Scoring
remains in Evaluate and contact discovery remains queued by Associate.

The baseline constructor accepted an arbitrary group object with empty attribution,
coverage, screenshot and findings. The new products reject that state, unrelated
report/evidence/score bindings, and source changes that contradict qualification.
Multi-report and multi-domain pending work for one entity remains supported;
the evaluated projection must contain the exact incoming qualified findings.
Evaluate orchestration moved out of IntakeService; the service shrank from 798
to 734 lines. New contracts use standard dataclasses and existing owner helpers.

The complete affected run exercised Accretion, Attribution, Entities and Leads,
plus changed Investigations/report, demo, release and module boundaries:
**1,410 passed, 132 subtests passed, 2 skipped**, with three invalid fixture
constructions rejected before their assertions. The fixtures were corrected to
use a registrable unknown root and include the current reported IP in raw source
fields; historical proof IPs and every ownership/provenance assertion remained
unchanged. Both complete affected files plus candidate contracts then passed
**60 tests**, covering all three failures. This verifies all **1,413 distinct test
cases** across the run and rerun; runtime hashes remained unchanged. One existing
Starlette/httpx deprecation warning remains.

Ruff lint/format passed for all 49 changed Python files. The program map passed
with 489 modules and no cycles or errors; local documentation links and baseline
line endings passed. No source/evidence schema or scoring policy changed.
Source snapshots, failing examples, exact commands/results, final hashes and the
review patch are retained in the task workspace's `domain-model-audit` directory.
See the [current funnel and product specification](PIPELINE.md#funnel).


### Documentation and final organization follow-up

The 704-line accumulated guide is replaced by a module index and focused current
specifications for pipeline products/stages, report schemas/admission, Dark Matter
and operations/recovery. Cross-module architecture/user guidance and inbound links
follow those owners. Historical vendored records retain their evidence; only their
navigation to current integration instructions changes. ISS024's current summary
now distinguishes delivered incident admission from the remaining detector policy.

The read-only ownership adapter is named `qualification_context.py`; old
`intake_reuse` imports are removed without an alias. Reader callers import their
intake owner directly, and the sample comparison tool accurately describes offline
structural checks versus the full live funnel. Workflow algorithms remain unchanged.
The capability endpoint now advertises its implemented live API selection feature,
separately from configured credentials, subscriptions or release acceptance; its
regression also exercises the actual connection/catalog/import path.

**Follow-up verification:** the complete Accretion suite and module-boundary checks
passed **831 tests and 132 subtests**, with two environment skips, in 151.87 seconds.
The focused acquisition/capability selection passed 90 tests; the reader/context
caller selection passed 44. These overlap the complete suite and are not a combined
unique count. One existing Starlette/httpx deprecation warning remains.

All 400 checked documentation links resolve; eight module documents are included
and byte-checked in both source and installed documentation staging. Documented
offline matrix, API demo and CLI help checks pass. Ruff lint/format passes for all
13 changed Python files, original line endings are preserved, and the regenerated
map passes with 489 modules and no cycles. Runtime source hashes stayed unchanged
during the complete run. Vendored runtime/provenance bytes are unchanged.

Exact commands, failing capability baseline, AST/source-equivalence evidence,
source snapshots and final review patch are retained in the task workspace's
`accretion-documentation-audit` directory. This is module/documentation verification,
not new live-account or native release acceptance. Larger service/store extraction
remains subject to an actual responsibility split rather than a line-count target.

## ISS043 Associate scope and component boundaries

**Resolved 2026-11-21.** Association formerly
admitted every sibling source condition even when Qualify/Evaluate excluded it.
Copying the full qualification into each admission event also produced truncated,
invalid JSON: a normal 12-host group generated twelve 4,000-character broken refs.
Contact disappearance used an obsolete engine-version branch, and discovery
ignored the qualified working website and never tried www after an apex failure.

The Associate component now delegates entity persistence, exact condition
admission, website binding, queue publication and archive outcomes to their owners.
Original rows and observed-only history remain complete; excluded and settled
conditions receive no new admission. Compact evidence references replace repeated
qualification bundles. The demo now explicitly evaluates before association.
Shared anchor selection preserves existing case/date rules without repeated JSON
parsing. Dark Matter closes excluded context instead of leaving it pending.

Contact refresh uses complete checked-source coverage, independent of an obsolete
revision constant. The bounded crawler reuses a retained HTTPS root/www starting
URL and falls back to its approved counterpart. Manual source-page checks retain
their single-page contract. HTTP/other subdomain seeds are tracked separately in
[ISS044](../../entities/docs/ISSUES.md#iss044-qualified-website-contact-scope).

Regression evidence includes excluded/settled findings, valid 12-host provenance,
current-engine removed/unvisited/incomplete contact sources, www fallback and
retained website/cache handoff. Original failures, source snapshots and exact
command logs are retained in the task workspace's `association-audit` directory.
See the [Associate contract and component map](PIPELINE.md#associate).

**Validation:** complete Accretion, Entities and Leads suites plus demo compatibility
passed **1,119 tests and 132 subtests** in 398.60 seconds; two Windows platform/privilege
checks skipped and one existing dependency warning remains. Ruff check/format,
changed-file whitespace and documentation links pass. All 21 changed Python
source/test files retained the hashes recorded before the complete run.

The program map passed with 473 modules and no cycles after this change. Subsequent
concurrent Library/Workspace edits introduced unrelated dependency-boundary failures
and stale generated maps; that snapshot's repository-wide check failed. Its
exact diagnostics are retained separately from the successful module run. Later
cycle-free validation is recorded under ISS046; this earlier failure is historical. No
allowlists or unrelated implementations were changed to conceal that failure.

The 293-line Association method moved out of the 1,077-line intake service into a
173-line coordinator and 157-line Entities persistence owner. Intake now has 798
lines. Runtime net growth is 149 lines; original line endings and existing source
bytes are preserved. This is local source verification, not release acceptance.

## ISS031 Evaluate scoring matrix and active scope

**Resolved 2026-11-21.** Evaluate previously let a
handled CVE on a mixed row influence the remaining scope, and selected conflicting
embedded CVE snapshots by row order. A newer withdrawal could also leave an older
reported-critical label contributing points. Supported compromise reports without a CVE
or severity label also received zero urgency.

The scorer now consumes the existing condition projection, selects the latest
whole captured CVE bundle deterministically, and versions its evaluation cache.
The shared report-profile predicate preserves independent findings while excluding
withdrawn-only rows from scoring, including stale eligibility on older observations.
Policy, local evidence reads, urgency candidates and score assembly have separate
owners. Existing public calls and ordinary scoring weights remain unchanged.
`report_bases` holds bounded values and explanations; the initial compromise base
contributes 10 urgency points at default weights, without stacking onto stronger
finding evidence. Profile overrides support targeted changes without workflow edits.
See the [Evaluate contract](PIPELINE.md#evaluate).

The real queue regression drops urgency **90 → 16** after ignoring the stronger
CVE while retaining original source tags. Six existing calibration scenarios retain
their scores, factors and ranking adjustments. The task workspace's `evaluate-audit`
contains the pre-change source, failing regressions, comparisons and command logs.

**Validation:** 751 tests and 132 subtests passed across the complete Accretion and
Leads suites in 236.20 seconds, with two platform/privilege skips. Ruff check/format,
local documentation links and program-map boundaries pass; no dependency cycles.
The original scorer shrank from 766 to 328 lines; the matrix, evidence and urgency
owners contain 153, 290 and 139 lines. Runtime net growth is 155 lines across six
files, preserving existing line endings and public APIs. This is local source
verification, not packaged-release acceptance. Concurrent Settings work is separate.

## ISS027 Qualify decisions and workflow

**Core implementation delivered 2026-11-21; performance follow-ups remain open.**
The application now executes **Filter → Qualify → Evaluate → Associate**.
Qualify returns one complete product containing actionable source findings,
authoritative attribution with explicit group coverage, and a functioning related
website with its retained screenshot. The
[runtime funnel and component contracts](PIPELINE.md#funnel)
describe the implemented sequence.

Implemented responsibilities:

- Entities owns current ownership and dated transfer checks. Qualify reads that
  context, explicit outreach holds and unsettled finding scope before browser or
  provider work. Its current-schema path performs no per-row schema probes.
  A stable owner/episode token is checked after capture, before Evaluate and in
  Associate's transaction. Transfers cannot move reused proof to a new owner;
  transfers away and back also invalidate the product. Five reproduced automatic,
  manual and reconciliation races now reject/defer without partial publication.
- Tools performs the full existing capture, including bounded fallback. A working
  login page passes; blank, challenge and error output does not. Investigations
  retains the original/preview/metadata, serves the Leads thumbnail and adopts
  the same image into cases. Every certified report requires the relevant intact
  screenshot, including compact reports. Workspace health and restore verify
  pre-case captures too. JSON lead exports include public capture references.
- Attribution owns proof validation, automatic/manual reuse and group coverage.
  Original source order and historical proof addresses remain unchanged. The
  alternate qualifier, recursive matcher and standalone spreadsheet runtime have
  been deleted; synthetic app tests now inject HTTP responses into the real engine.
- Evaluate alone calculates priority/urgency. Leads previews pending scope and
  publishes its evaluated fingerprint; Associate cannot trigger hidden scoring.
  Associate rechecks mutable ownership/holds/scope and commits the lead, findings,
  capture binding, job outcome and export obligation atomically. Contact discovery
  remains an Associate responsibility.
- Automatic, manual and saved-review reconciliation use the same complete product.
  Accretion owns job reconciliation; Attribution interprets evidence. Export failure
  leaves a durable repair obligation. Shutdown reaches browser and provider work,
  including pacing/retries; ordinary pause still finishes the current group.
- Existing supported compromised website/IoT profiles use their source incident as
  actionable evidence without inventing a CVE, version or severity. Additional
  report/schema/template families remain scoped under ISS024.

**Measured benefit:** a 64-new-row local qualification probe fell from 841 SQL
statements with 261 schema probes to 580 statements with **zero schema probes**,
preserving the same owner and 64 actionable findings. Failed local or website
gates make zero fresh attribution/scoring/association calls. The 640-group progress
probe fell from approximately 11.63 million summary VM steps to 7,600, with one
initial aggregate and transactional deltas thereafter. Pending payloads load one
at a time; broad endpoint-history recognition reads and recursive source copying
are gone. These are synthetic local measurements, not live-provider throughput.
The new required screenshot adds work: total 640-group fixture time increased
from 51.72 to 70.67 seconds, so this change does not claim an overall speedup.

**Verification:** purpose checks cover early exits, functioning login/fallback,
group reuse, original proof/coverage, same-byte screenshot adoption, manual and
reconciled publication, export repair, report inclusion and artifact tampering.
Native browser fixtures and rendered Leads/report output were inspected. Complete
affected module runs and final caller checks are retained under the Codex task's
`qualify-implementation/`; final counts and exact source hashes are recorded in its
validation manifest. Earlier failing runs remain preserved. This is source-level
verification; no live Shadowserver/provider run or release acceptance is claimed.

The final complete Accretion/Attribution/Entities selection passed **1,164 tests
and 132 subtests**, with two environment skips. Its two obsolete tests patched
Leads' former ownership resolver; they were retired after replacement by real
owner/episode queries and five actual transfer/publication races. The affected
files and replacements were checked again. The complete Leads/Investigations
selection passed **746 tests**, with four environment skips. Engine checks passed
190 tests, Tools 110 tests, and the complete Entities/Library/Observatory selection
806 tests before the final ownership-token extension. Those overlapping counts
are separate runs, not a unique total. Workspace/root fixture corrections, later
health/export checks, native output inspection, Ruff, dependency integrity and the
cycle-free program map are recorded with their exact scope in the manifest.

**Remaining performance work:** groups still run serially with one lazy client per
import. Existing per-capture/provider budgets and shutdown cancellation are active,
but there is no single resumable group deadline or worker-wide provider lifetime.
The review-list API still needs bounded summary paging. Independent-group overlap
must use the existing engine capability after those contracts are defined. A
separate-root website redirect remains an identity-review outcome; it is not
automatically treated as proof of a related business. None of these limitations
permits incomplete leads, speculative provider calls or missing report screenshots.

### Pre-implementation audit

The following audit records the earlier source and recommendations, including
items implemented above. It is retained as before-change evidence, not a current
runtime inventory.

**Evaluated and requirements clarified 2026-11-21.** Qualify must establish
an evidence-backed lead: valid group attribution, a functioning entity website
with retained screenshot, and supported actionable finding evidence. **Evaluate**
is the requested replacement name for the Urgency stage; it scores that lead.
Associate owns contact discovery and high-confidence entity enrichment.
The initial evaluation changed no application code or maintained tests.
Existing data compatibility is not required. The [step map](PIPELINE.md#qualify)
describes the implemented sequence; the recommendations below were not implemented
at the time of the audit. User-confirmed rules supersede earlier audit assumptions:
one valid hostname/IP match covers the related group sharing IP or hostname/root;
functioning login/admin pages count as usable; all attribution implementation and
proof/reuse functionality belongs to Attribution; obsolete legacy implementations
must be removed. Reuse established app tools/helpers and public component APIs.
The subsequent requirement for a screenshot in every report and a Leads thumbnail
supersedes the earlier load-only proposal: call the full existing capture tool,
retain its result once and reuse it through lead and report evidence interfaces.

**Baseline and reference:** working checkout based on
`efccc0a0f476bf83078b26694afa8fad0372047c`, following ISS025, on Windows/Python 3.14.
The independent reference is the funnel contract, explicit source/evidence scope,
recorded analyst authority, ordinary retry semantics and existing engine APIs.
The prior implementation and green tests are comparison evidence, not acceptance
criteria. Source snapshots and probes are under the Codex task's `qualify-audit/`.
Concurrent ISS026 shared-helper extraction was observed and reviewed separately;
the retained hashes identify the audited source. These results do not certify
that unrelated change set.

### Change first: decisions, validation and completion

1. **Apply the confirmed group-attribution rule consistently.** A fresh two-address group with
   one matching and one nonmatching IP qualifies after checking only the first;
   both rows become admitted. The same source rows after the first IP already
   has history become `no_match`, checking only the second. This also occurs when
   the second row is explicitly ineligible context. `intake_reuse.py:138` narrows
   to new endpoints, while `attribution_bridge.py:96` and the engine's first-match
   exit apply to the whole fresh group. Manual acceptance/reconciliation likewise
   select one proof and hand off every entry (`intake_service.py:716,1065`).
   The user's clarified rule validates group-wide attribution from one sufficient
   match. Remove the new-address-only restriction when a shared IP/hostname/root
   match already qualifies the group. Attribution should return the original
   proof plus explicit covered-source relationships, consistently for fresh,
   repeated, manual and reconciled work. Do not require independent attribution
   for every address or service port in that covered group. Keep entity ownership
   and merging separate from attribution coverage.
2. **Use one authoritative proof validator in Attribution.** Accretion's
   `_proof_matches` and Attribution's `_checked_proof` disagree. With real saved
   review evidence, deleting the recorded review causes `approved_proofs` to
   return nothing while recognition still trusts its embedded review. Changing
   the embedded record also passes recognition but fails the Attribution check.
   These controlled integrity cases demonstrate contract drift, not an ordinary
   UI revocation path. Resolve recorded decisions/current ownership and validate
   immutable result/snapshot bindings through one public owner API. Remove the
   no-result embedded-proof fallback (`intake_reuse.py:92`).
3. **Unify successful-decision publication and export recovery.** Manual accept
   commits the review and qualified work, then calls export without persisting
   the automatic worker's pending-export obligation (`intake_service.py:734–801`).
   A reproduced export failure reaches the caller even though acceptance committed;
   retrying the import then performs no repair export. Reconciliation has the
   same gap. Commit the obligation with the accepted decision and report/retry an
   export failure separately from the successful decision. Preserve atomic
   canonical/job publication and current-state checks.
4. **Connect shutdown cancellation and define the work budget.** The bridge opens
   the engine without the worker stop event. A synthetic RDAP response setting
   that event still permits DNS fallback; passing the existing event to the engine
   stops that next provider. The real intake path also scores and associates after
   shutdown is requested during a successful response. Wire the boundary and
   check shutdown before downstream work. RDAP pacing/capture/retries still need
   token propagation; module-level cancellation alone cannot interrupt them.
   The default 45-second budget renews for each provider/candidate, so it is not
   a group deadline. Define bounded, resumable group work and keep cancellation
   distinct from `no_match`. Preserve the UI's intentional **pause after current
   group** behavior rather than silently changing it to immediate cancellation.
5. **Add website capture and entity evidence before fresh attribution.** Qualify
   does not currently load reported hosts or roots. Call the full existing
   `Tools.capture_website` API, with bounded reported-host/fallback behavior and
   its rendering/screenshot implementation. A functioning login/admin page passes;
   no public company homepage is required. Preserve actual working URL, check time
   and fallback provenance, and use that URL for the lead's primary website action.
   Tie the captured site to the original attribution/domain relationship; a page
   or cross-domain redirect alone does not establish entity identity. Retain the
   screenshot with the qualified lead, show a thumbnail from that same artifact,
   and adopt it into the report without recapturing. Require screenshot presence
   and integrity in report readiness/certification. Current automatic inclusion
   excludes login captures, despite the accepted functioning-login rule.
   Neither host nor root usable means no active lead, fresh RDAP/DNS, score or
   association. Preserve retryable/blocked/tool-error outcomes accurately through
   Dark Matter. Saved attribution or manual identity approval cannot bypass this.
   Apply existing cheap local suppression/hold checks first through their owners;
   do not suppress new findings merely because an older finding was handled.

The existing Tools `capture_website` operation renders a PNG and waits for image,
font and video readiness. Its `load_page` currently stops on challenge/partial
outcomes as well as normal/login pages. A deterministic fake-CDP/virtual-clock
probe also showed a blank ready document consuming 95 of a 100-second budget,
with no root attempt. These are current control-flow observations, not browser
performance measurements. Reuse the full capture mechanics while correctly
interpreting usable/entity-related output and reserving fallback time; do not
copy the loader into Accretion or bolt on mandatory DNS/TCP/HEAD checks. The component mapping
and required sequence live in the [guide](PIPELINE.md#qualify).

The existing screenshot validation/hash/preview and report packaging code should
be reused. Current capture jobs and evidence rows require an existing canonical
entity/case, so Qualify needs a narrow pre-case lead capture/adoption boundary,
not a fabricated case or a second image-storage implementation. Report integrity
currently permits an empty evidence list; the every-report screenshot condition
must be enforced explicitly. The qualified product currently lacks website,
screenshot and actionable-finding evidence fields.

Report type is already retained as `normalized.profile.id` through Filter, jobs
and reporting. Compromised website/IoT profiles, narratives and explainers exist,
but default incident exclusion and severity admission still need review. Extend
supported schema/finding/template families incrementally under ISS024 and the
existing Investigations report machinery. Do not introduce a parallel template
engine or fabricate a CVE requirement for incident reports. A score is not proof
that a reported product/version is affected; preserve the source evidence and
the level of verification established by that report family.

### Remove redundant work and misplaced responsibilities

| Decision | Evidence and intended replacement |
| --- | --- |
| Remove the alternate application qualifier | `intake_service.py:436–460` uses the legacy `ValidatedLeads.qualify` for `lookup_factory`; shared app fixtures exercise it instead of production evidence/review behavior. Its matcher accepts a target domain solely in an excluded notice or unrelated URL path/query where the engine rejects it. Delete that implementation and obsolete tests enforcing it; test the production provider/module interface. Any retained command entry point delegates to the maintained Attribution implementation rather than preserving alternate matching semantics. |
| Replace broad history reads with a narrow ownership/history API | Recognition consumes two history facts but `awareness.recognize` fetches full observations, computes unused finding IDs and repeats ownership/schema work. Skip proof-history work once ownership establishes `new` or `review`. Batch relevant endpoint facts while preserving dates and ownership episodes. Validate the current schema at initialization; remove qualification-time legacy schema branches. Ownership resolution belongs behind Entities' API, not a Leads queue dependency. |
| Remove recursive entry copying from recognition | `intake_reuse.py:114` deep-copies every source/normalized payload using `asdict`; identity/provenance fields suffice. Keep original row identity and immutable payloads. |
| Make proof fallback lazy and reuse immutable reads within a run | Try the saved applicable proof first. Recognition currently materializes all accepted proofs before testing it. Reconciliation repeatedly reads identical immutable results/snapshots. Validate once per run, while still rechecking mutable job/owner state at commit. Remove the compacted-empty legacy payload accommodation once current source identity is explicit. |
| Separate service keys from proof keys | Port/protocol identify a reported service; RDAP attribution describes address/domain identity. A port-only change reruns evaluation and stores another result, although the provider cache prevents HTTP requests. Use evidence-specific identity keys; do not claim this currently saves a demonstrated network request. |
| Replace per-group full progress scans | Every completed group scans the import's jobs for completion and again for reuse. Maintain transactional status deltas or bounded summary refreshes; coalesce presentation-only updates. Keep authoritative completion recoverable. |
| Bound job and review loading | Worker `SELECT *` loads all pending payloads at once. `/api/reviews` also loads/decodes every waiting payload/result and sorts everything in Python. Page lightweight summaries; load full source/evidence for the active group or requested detail. |
| Move application reconciliation to Accretion | `attribution_reconciliation.py` owns imports/jobs SQL, progress, calls into Urgency/Associate and export. A cohesive Qualify workflow should own automatic, manual and reconciled transitions. Attribution retains proof interpretation, validation and recorded approval evidence. Avoid a generic workflow framework. |
| Return an explicit decision from the bridge | Mutable `client.result_id`, in-place row reordering and side-effected attempts hide outputs. Return status/reason, result/proof references, attempts, anchor and permitted scope. This is also a prerequisite for safe independent-group concurrency. |

### Measured costs and parallelism

Synthetic measurements are diagnostic single runs with no live provider calls;
concurrent checks and instrumentation affect elapsed times.

| Workload | Observed cost |
| --- | --- |
| Recognition, 1,024 repeated endpoint rows, new domain | 5,146 SQL statements, including 2,059 schema checks; about 0.25 s. |
| Recognition, 1,024 distinct endpoint rows, new domain | 19,468 SQL statements, including 8,197 schema checks and 1,024 unused finding-ID computations; about 0.86 s. |
| Recognition copy cost, 1,024 nested rows | About 0.056–0.102 s spent recursively copying complete payloads. |
| One already-valid manual proof | Four result reads and seven snapshot reads before reuse. |
| Accept one review and reconcile eight waiting four-row groups | Nine results read 119 times; two snapshots read 187 times; about 1.15 s excluding export, zero provider requests. |
| 40 / 160 / 640 no-match jobs, after Filter | About 3.00 / 11.40 / 51.72 s; 212 / 812 / 3,212 workspace connections. Only the provider client was stubbed; recognition, publication and archival ran. |
| Progress aggregates for those job counts | About 43,900 / 718,300 / 11,632,300 SQLite VM steps: quadratic summary work. Overall elapsed time in this range is dominated by additional costs and is not shown to be quadratic. |

The engine already supports `attribute_many(workers=1..4)` with bounded in-flight
work. Eight synthetic 40 ms independent lookups took 340 / 173 / 91 ms with
one / two / four workers and identical calls/results. Use that existing capability
after decision ownership, cancellation, group bounds and commit rechecks are
correct. Authority pacing and shared work constrain live gains; do not simply
thread the mutable bridge or add another scheduler.

Keep RDAP-first/DNS-fallback short-circuiting. Starting both providers speculatively
would spend work even when RDAP succeeds. The two public DNS resolver observations
already run concurrently. A deliberate worker-owned engine lifetime would also
preserve ordinary request spacing: an 80 ms configured interval measured 81 ms
within one client but 3 ms after client replacement. Persistent cache and 429
cooldown worked correctly. Lazy initialization for wholly reused/blocked groups
is useful separation, but a 2.02 ms median open cost is not a major speed finding.

### Keep and completion criteria

Keep immutable original/evidence identities, exact domain/result binding, bounded
automatic reuse, recorded manual decisions, registrant namespace/handle/name
checks, dated ownership-transfer protections, explicit refresh/dismissal,
duplicate-request coalescing, provider cache/cooldowns and the strict gate before
Urgency. Preserve manual status/result checks and reconciliation's
status/result/payload/owner checks. No ordinary duplicate-publication race was
demonstrated; checks across different consistency boundaries are necessary.

**Done when:** one declared qualification scope is enforced by automatic, manual
and reconciled paths under the confirmed group rule; Qualify returns a lead with
attribution, entity-site screenshot and supported finding evidence; the full
capture supplies the lead thumbnail and required report screenshot through one
retained artifact; its working URL is used by the UI and functioning login pages
pass; Evaluate owns urgency/priority and Associate owns contact/entity enrichment;
one authoritative validator resolves proof/approval facts;
equivalent cases follow that policy regardless of accidental row order or which
entry path runs; unresolved rows remain explainable through Dark Matter; shutdown
and group work are bounded; committed decisions survive export failures with a
durable repair obligation; history/progress work is bounded and measured; the
application uses one production qualification contract; and the step map, API,
focused purpose probes and complete affected verification are updated. Engine
source changes also require its package/wheel integrity workflow. No historical
data migration or compatibility shims are required.

**Audit verification:** 43 existing funnel/reuse/association tests and 45 existing
review/approval/reconciliation tests passed. The additional synthetic probes expose
the gaps above despite those 88 passing tests. `service_probe.py` uses the real
intake/bridge/engine with mock RDAP; `decisions_probe.py`,
`engine_boundary_probe.py`, `engine_matcher_probe.py`, `service_cost.py` and
`review_probe.py` retain reproducible inputs, results and scope limits. No live
Shadowserver or registration requests, application edits, release acceptance or
paid CI occurred. The follow-up `website_gate_probe.py/.json` documents the current
capture/loadability mismatch with synthetic CDP events and a virtual clock; the
new website gate had not yet been implemented at that audit baseline.

## ISS025 Isolate complete Dark Matter storage

**Resolved 2026-11-21.** Replaced the compact usable-row index with an
Accretion-owned complete archive and a single public write/query boundary.
User authorization explicitly permits removing old implementations without data
migration/backfill because this is a development application.

**Baseline:** the previous archive kept 20 selected fields, omitted malformed and
outside-region rows, shared its table with qualified recurrence/case state, and
required consumers to reconstruct canonical-looking records or reread source
files. The pinned inventory has 746 distinct fields. The synthetic coverage probe
stored 17 of those fields and excluded five of seven test rows. Original files
survived, but their fields were not searchable through the archive.

**Implemented scope:** independent `dark_matter.sqlite3`; immutable complete
source rows and separate stage history; typed field diagnostics and structured
queries/catalogue/facets; owner-controlled batch/outcome APIs; durable idempotent
outbox delivery; Workspace lifecycle integration; removal of the mixed table,
duplicate Leads memory, historical backfill and raw/canonical reconstruction;
Observatory field browser; cohesive Filter selection before full normalization.

**Completion contract:** malformed and unknown-field rows are queryable; each source row's
field normalization is reused; stage/consumer code has no archive SQL or custom
retention envelope; unqualified records never become canonical findings; replay
does not lose/duplicate decisions; backup/restore includes archive and pending
deliveries; UI field filtering works; relevant checks and before/after purpose
measurements are recorded. Test fixtures enforcing the old narrower purpose are
removed or rewritten around observable current behavior.

**Demonstrated benefit:** the archive now retains all 746 pinned field names,
unknown extensions and malformed/outside-region rows. Source identity, immutable
fields, normalized values and stage history belong to one component. Leads and
case workflow use canonical Awareness; Observatory calls the archive API without
reconstructing canonical identities. All-rejected 10,000-row input now creates
zero full observation envelopes instead of 10,000. Archive persistence uses bulk
identity checks and bounded writes; normalization is reused on reimport.

**Measured cost:** complete archival and durable delivery add work compared with
the old 20-field index. The same synthetic 10,000-row fixtures measured:

| Fixture | Previous total | New total | Previous longest workspace write | New longest workspace write |
| --- | --- | --- | --- | --- |
| Below threshold | 2.251 s | 3.387 s | 0.698 s | 0.010 s |
| Mixed eligibility | 2.417 s | 3.423 s | 0.798 s | 0.025 s |
| Accepted by Filter | 3.646 s | 4.501 s | 1.790 s | 0.151 s |

These are single instrumented Filter-only runs with synthetic input and no live
qualification; concurrent checks can affect timing. They demonstrate a shorter
main database write reservation, not faster total ingestion. A separate traced
3,000-row accepted fixture peaked at 28.04 MB versus 27.51 MB previously; it does
not establish process RSS or maximum-size capacity. Candidate counts and job
payload bytes are unchanged. The complete archive adds storage by design.

Task evidence is retained in the Codex task workspace under
`dark-matter-refactor/` and `dark-matter-audit/`, including the baseline,
`refactor-cost-final.json`, failed intermediate runs, browser evidence and final
source hashes. No existing-data migration or backfill was attempted.

**Validation:** Windows/Python 3.14, working checkout based on
`efccc0a0f476bf83078b26694afa8fad0372047c`; existing module reorganization and
unrelated concurrent Website changes were preserved. The complete affected
Accretion, Observatory, Entities, Leads, Workspace and Library suites plus
Workbench, schema, performance, module and demo integration checks produced
1,792 passes, 177 passing subtests and four skips in 648.40 seconds. Five failures
were stale verification: three spies targeted the old Filter owner, and two
canonical adversarial fixtures expected invented source archive rows. The tests
now observe persisted phase order and the actual owner, enforce zero catalog or
registry work for junk, and assert canonical unapproved evidence separately from
source retention. No application change was needed for those corrections.

The complete Accretion rerun then passed **718 tests and 144 subtests**, with two
skips, in 127.26 seconds. Together these runs verify **1,797 distinct backend
cases and 177 subtests**, with four skipped cases, against the settled application
source. The focused corrections also passed independently. Full `npm test`, Ruff,
the generated component map and new-line whitespace checks passed. The diagrams
render and all 192 checked guide links resolve.

Real Chromium checks with synthetic API responses verify malformed-row display,
numeric filtering, full original values and desktop/mobile rendering without
browser errors; real-store API integration is covered separately. Backup/replay,
rollback, field coverage and the before/after probes exercise the underlying
behavior. This is source-level validation, not release acceptance or live
Shadowserver/provider verification. Further finding-admission policy work remains
in ISS024.

## ISS024 Filter contracts and interruption

**Open, reviewed 2026-11-21.** Remaining work is independent HTTP detector/version
admission, incremental report/finding/template coverage and further measured
selection/memory refinements. Supported compromised website/IoT adapters already
admit their source incident without a CVE, software version or critical severity
label; `incident_review_required` remains only a historical display reason.
Critical/targeted admission settings stay in Filter; Evaluate owns urgency ranking.

ISS025 delivered archive ownership, survivor-only full normalization, explicit
projection/publication, interruption and strict CSV parsing. ISS027 delivered
website/screenshot qualification and supported incidents; ISS046 delivered typed
report/evidence handoffs. The [current Filter contract](PIPELINE.md#filter) and
[report schema/admission guide](REPORT_SCHEMAS.md) describe that implementation.
The original audit below preserves its earlier failures and proposed remedies;
items already delivered are not additional open requirements.
The audit used the current dirty checkout at
`efccc0a0f476bf83078b26694afa8fad0372047c`, including ISS021 and ISS023. This pass
was documentation only. ISS025 subsequently implemented items 2, 3 and 5,
the projection/publication portions of item 4, and strict CSV parsing. The
remaining work is detector admission policy and further measured selection
refinements; the original observations below are retained as baseline evidence.

Priority is driven by selection correctness and avoided work, not complete
validation of every upstream column.

1. **Correct finding-specific admission contracts.** The Vulnerable HTTP adapter
   requires a CVE or software version even for independent detector findings.
   A targeted `basic-auth` row produces zero jobs with `missing_version`; adding
   an unrelated version produces one. Review explicit detector kinds against
   upstream semantics and add expected candidate fixtures. Preserve intentional
   EOL/version, withdrawn-CVE, critical/KEV, targeted-reason and jurisdiction rules.
   Include mixed independent-condition/withdrawn-CVE fixtures; the audit shows
   such a synthetic tag is currently classified as CVE-only, without establishing
   that the exact combination occurs upstream.
   Define minimal contracts for all enabled families, including identity conflicts
   and meaningful malformed endpoint/time values. Missing unused optional fields
   are not automatically admission defects.
2. **Fix interruption and publication boundaries.** A stop/pause during the first
   of four rows still allows Filter/jobs to commit and a client to open. With no
   eligible groups, finalization overwrites `paused` with `done`. Check during
   bounded processing, before publication, against persisted state inside the
   completion transaction and before downstream initialization. Keep publication
   atomic and retries deterministic.
3. **Select before full normalization.** The 10,000-row all-reject fixture builds
   10,000 full envelopes; the mixed fixture builds 9,000 for rejected groups.
   Decide using lean candidate facts, retain context for selected groups, and
   normalize only their rows. A reduced rejected-row envelope preserved retained
   records exactly in the probe. Also skip product parsing whose result is
   immediately discarded for protocol/unspecified versions: all 48 tested
   envelopes across 12 profiles were unchanged.
4. **Reduce copying, memory and transaction work.** The all-candidate fixture
   expands 1.009 MB of CSV into 36.847 MB of job JSON; repeated profile/CVE facts
   account for 18.24 MB. Recursive dataclass copying takes 0.638 s inside a
   1.790 s completion transaction. Explicit projection preserved byte-identical
   JSON and reduced isolated copy/serialization median from 0.901 to 0.326 s.
   Prepare immutable payloads before publication, reuse parsed facts and establish
   working-memory/payload budgets. Shared persisted snapshots are a separate,
   compatibility-sensitive design decision, not a prerequisite for the small
   optimization. A traced 3,000-row fixture peaked at 27.5 MB of Python allocations;
   this does not establish process RSS or maximum-size capacity.
5. **Make responsibility boundaries explicit.** Approximately 254 inline lines
   mix row reading, policy, normalization, grouping, statistics and persistence.
   Give Filter one cohesive owner with read-candidates, select-groups and
   prepare-result operations. Keep lifecycle/transaction/handoff in the service.
   Reuse existing helpers; normalize legacy policy configuration once; avoid a
   generic framework or a file/function for every individual check. Prepare
   fixed report/header descriptors once and preserve mixed-report behavior.
6. **Align format handling and inexpensive exits.** Manual `DictReader` accepts
   an unterminated quoted field at EOF that API validation rejects. Share strict
   parsing behavior while preserving original bytes. Fixed report/mode policy
   can also make admission impossible before CVE/envelope work, as demonstrated
   by an RDP critical-mode fixture. Short-circuit only work that cannot affect
   admission, retained evidence, context or diagnostic reasons.
7. **Review the Qualify handoff separately.** Source order currently lets context
   IPs precede eligible evidence. Evaluate eligible-first candidate indices,
   preserving original row identities/order and context fallback; this is not
   Urgency scoring. Private-only groups create a job/client but make zero remote
   lookups, so lazy client setup offers overhead savings, not demonstrated network
   savings. Ownership/history decisions must remain in Qualify.

**Done when:** reviewed family/finding fixtures produce exact expected candidate
and context sets; interruption is bounded and preserves status; malformed CSV
behavior agrees; all-reject groups avoid full normalization; reduced serialization
preserves stored payloads; atomic rollback/empty completion/retry tests pass; and
the documented ownership boundaries are implemented. Record elapsed time, parser
and normalization calls, memory, payload bytes, transaction duration and downstream
candidate attempts for all-reject, mixed and all-accept fixtures. Preserve frozen
facts for selected context rows, raw source identity, eligibility reasons and the
strict Qualify-to-Urgency gate. No network schema retrieval, broad storage migration
or concurrency framework is required by this issue.

**Evidence:** task-local `filter-purpose-audit/admission_probe.py`,
`admission-results.json`, `cost_probe.py`, `cost_matrix.json`,
`reuse_experiments.py` and `reuse_experiments.json`; prior
`filter-structure-probe.py/.json`, `schema-malformed-quote.csv`,
`filter-csv-boundary-probe.json` and `filter-parallel-review.py/.json/.log`.
The admission audit exercised 26 adapters, 22 decision cases and nine isolated
imports. The cost matrix includes CSV/gzip/XLSX and 1,000 distinct CVEs, but remains
synthetic warm-storage evidence. Catalog reads cost about 0.003-0.030 s; the earlier
four-thread experiment was about 4% slower than serial. Remove unnecessary work
before adding concurrency. Existing application suites were not repeated for this
documentation-only review.

## ISS023 Remove repeated funnel work

Evaluate the actual processes in Filter, Qualify, Urgency and Associate, remove
repeated work, and document their entry requirements and exit paths in a funnel
diagram. Preserve the strict qualification gate established by ISS021.

**Done when:** each supported row gets one structural validation decision;
filename profile matching is reused without caching row-specific schema data;
qualification candidate selection is linear; Associate persists one final queue
registration per accepted group; completed empty imports do not repeat Filter;
and unsuccessful retries do not regenerate unchanged exports. Source evidence,
captured policy/catalog inputs, history reuse, current ownership checks, queue
scope reconciliation and atomic job completion must retain their contracts.

Baseline: the existing dirty checkout at
`efccc0a0f476bf83078b26694afa8fad0372047c`, including ISS021 and unrelated module
maintenance. The task workspace retains `cleanup-baseline/` and Git status.
The existing Windows/Python 3.14 test environment is reused; no schema, scoring
policy, existing caller contract, network-boundary or release-acceptance change
is intended.
One synthetic 128-row import performs 192 validation decisions, 4,515 filename
pattern checks and 128 endpoint normalizations, despite only 64 surviving rows
and one unique endpoint. Successful association registers its queue twice.

Verification: preserve failing focused regressions and before/after call counts,
then run the complete Accretion, Attribution and Leads module suites with
cross-module funnel/performance/request/demo checks once on the settled source.
Review the diagram against actual automatic, retry and manual-approval paths;
regenerate/check the program map and run lint/format checks on changed code.

**Resolved 2026-11-21.** Implemented bounded filename-identity reuse, one validation outcome per
supported row, one endpoint normalization per observation, set-based candidate
selection and committed Filter reuse for empty groups. Associate normalizes its
entries and admission metadata once, checks ownership in the write transaction,
and registers only the final qualified queue row. Frontier reconciliation reuses
each candidate's parsed payload and finding IDs within that transaction. Urgency
retains captured facts and its existing local-reference cache; unchanged scopes
reuse the initial score, while changed qualified scopes retain Leads' ranking.

The worker records pending exports in the job-completion transaction and clears
the marker after export succeeds. Failed-only retries and already-complete
imports skip unchanged exports; failed/interrupted exports and older interrupted
imports remain recoverable. No original source or attribution evidence is
discarded to achieve these reductions.

**Demonstrated benefit:** on the same 128-row fixture, filename pattern checks
fell from 4,515 to 35, validation decisions from 192 to 128 and endpoint
normalizations from 128 to 64; the single registry lookup was unchanged. Queue
registration fell from two calls to one per accepted group. Frontier candidate
reads fell from three to one for an unchanged scope and from five to two for a
two-candidate merge. Regression checks retain the changed-scope re-score and
prove transaction conflict rollback, stable evidence links and export recovery.

**Broader verification:** the complete five-module selection (Accretion,
Attribution, Leads, Observatory and Entities) plus performance, Workbench,
request-contract and demo checks completed with 1,348 passes, 144 passing
subtests, two skips and eight obsolete ownership-test assertions. All eight
failures reproduce against the preserved earlier strict-funnel source. The tests
expected canonical associations for deferred groups, before any Associate work.
Their alignment is verification debt: they now check raw retention and read-only
historical context before preserving their adversarial admission checks. It
requires no application change after that complete run.

The final complete Entities suite passed all **331 tests** after that test-only
alignment. Combined final coverage is **1,356 tests and 144 subtests passed**
across the affected suites and integration checks. The two skips were the
non-Windows credential check and a symlink fixture requiring unavailable Windows
privileges. Ruff passes all 13 changed Python files; the program map has no
errors or cycles, and diff whitespace checks pass. This is source-level
verification, not release acceptance.

The [funnel diagram and process inventory](PIPELINE.md#funnel)
describe each stage and its exits. The exact Mermaid source parsed and rendered
successfully; visual review found no clipping or overlap. All 105 checked local
documentation links/anchors passed. Task-local evidence includes the before/after
probes, failed initial ownership checks, `cleanup-change.patch`, and
`cleanup-validation.json` with exact source hashes and commands.

## ISS021 Enforce the intake funnel

Qualification must gate all downstream work: only successfully qualified groups
enter Urgency, and only ranked groups enter Associate. The previous pipeline
associated unapproved observations during Filter and scored failed, deferred and
review groups. Fresh attribution was also absent from the saved identity score.

**Done when:** rejected or unresolved groups perform no scoring, reference-draft
enrichment, canonical finding/entity association or lead registration; retries,
manual acceptance and review reconciliation pass the same gate. Original files
and bounded raw observation summaries remain available without downstream writes.
Successful groups use the established attribution when ranked, then atomically
commit their findings, lead and completed job. Progress reflects those outcomes.

Baseline: working checkout based on `efccc0a0f476bf83078b26694afa8fad0372047c`,
with existing uncommitted module reorganization preserved. Windows/Python 3.14
checks use synthetic workspaces and blocked external requests. The initial
52-test intake/reuse/awareness selection passed; an instrumented successful and
failed import both scored 64 and created unapproved findings before qualification.
Verification starts with `test_intake_funnel.py`, then the complete affected
module suites and frontend contracts. No hosted execution or schema change.

**Resolved 2026-11-21.** Unsuccessful qualification now stops before Urgency,
reference-draft enrichment, lead registration and canonical association. The same
gate covers retry, explicit analyst acceptance and saved-review reconciliation.
An empty filtered batch opens no attribution client. The successful identity is
available to initial scoring, and final association/job completion stays atomic.
Outcome updates identify exact source rows so filtered siblings retain their
exclusion reasons. Review reconciliation preserves an import's active, paused,
queued or failed lifecycle.

Raw summaries remain available through read-only projections. They preserve
original source bytes, exact approval boundaries, deduplicated physical counts,
selected software-version identity, retained detail links and indexed detail
performance. No source rows are promoted merely by opening a view. Intake policy
version 13 distinguishes new evaluations; the database schema is unchanged.

**Demonstrated benefit:** the instrumented no-match import changed from one score
and two association calls to zero of each. The matching import scores only after
qualification, with the established identity changing its fixture aggregate from
64 to 69. The 13 funnel cases cover failed/review/deferred outcomes, retries,
manual acceptance/dismissal, legacy reconciliation, empty filtered batches,
implicit registration scoring and preservation of filtered siblings.

**Validation:** the complete Accretion, Attribution, Leads and Observatory test
suites plus performance, Workbench, request-contract and demo integration checks
passed **1,009 tests and 144 subtests** in 313.11 seconds. Two checks were skipped:
the non-Windows credential error and a symlink fixture requiring unavailable
Windows privileges. The full portable frontend runner, Ruff, and generated
program-map checks passed. This is source-level validation, not release acceptance.
The task workspace retains original file backups, before/after traces, failed
intermediate runs, `final-affected-backend.log`, and `funnel-validation.json` with
the exact changed-source hashes and Windows/Python 3.14 environment.

## ISS010 Legacy intake network path

The network-adapter evidence below predates removal of the alternate intake CLI
under ISS027. It preserves that earlier implementation result; the current
[entry-point contract](PIPELINE.md#entry-points) has one application qualifier.

The standalone command and alternate qualifier were subsequently removed by
[ISS027](#iss027-qualify-decisions-and-workflow). The record below describes the
earlier transport-only maintenance, not a supported current command.

`modules/accretion/components/excel_intake.py` retains an older network path;
production qualification uses Attribution. Developer tools still call the CLI.

**Done when:** its supported callers and compatibility requirements are reviewed,
then the path is deliberately retired or migrated with CLI regression coverage.
Application imports must continue to respect the existing legacy-CLI boundary.

**Resolved 2026-11-21.** The application had no
runtime imports of the legacy CLI. Its two developer-tool consumers now import
pure intake models directly. The supported spreadsheet command remains, with
its network client reduced to an adapter over Attribution's maintained registry
transport. Legacy qualification, input bytes, output shape and exit codes remain
unchanged. The [command contract](PIPELINE.md#entry-points) records
the deliberate strict-validation, per-authority pacing, cooldown and total-budget
changes instead of implying complete legacy network-policy equivalence.

**Demonstrated benefit:** the saved baseline accepted a 2,162,857-byte RDAP
response; the updated command rejects it at the shared 2 MiB limit. A controlled
real-socket trickle took 0.793 seconds under the old 0.2-second idle timeout; the
new 0.4-second total budget returned in 0.408 seconds and the server observed
socket closure. These are synthetic measurements, not universal latency bounds.
Valid export and run-log bytes match under a controlled clock, and the original
workbook is unchanged. The network adapter shrank from 124 to 96 lines while
`LeadRuntime`, workbook discovery and atomic output remain AST-identical.

A follow-up memory review removed duplicate raw-response retention introduced
by the initial adapter. Across 40 synthetic IPs, retained duplicate receipt bytes
fell from 1,969,126 to zero after each lookup, open evidence stores from one to
zero, and cached traceback exceptions from ten to zero. Both versions retained
the same 40 requests, cache hits and legacy results. Per-IP SQLite initialization
added about 0.026 seconds to that in-process fixture batch; preserving the existing
public store contract was preferred over inventing a new transport/storage seam.

The Accretion/boundary selection passed 651 tests and 144 subtests, with two
skips. Two additional report checks initially lacked Poppler on PATH and passed
unchanged after correcting the environment. All three direct CLI/tool help
commands pass with the installed 0.2.7 engine and no PYTHONPATH override. Exact
commands, hashes, before/after probes and compatibility notes are in the Codex
workspace's `validation/maintenance-batch-02/iss010-*` bundle. The uncommitted
change is based on `efccc0a0f476bf83078b26694afa8fad0372047c`. After the memory
refinement, 48 focused tests and 29 subtests passed; real-socket bounds and exact
valid export/run-log comparisons passed again. The complete backend run includes
the settled implementation.

## Shared work and dependencies

| Canonical item | Accretion involvement |
| --- | --- |
| [ISS004 Workspace facades and models](../../workspace/docs/ISSUES.md#iss004-workspace-facades-and-models) | Own group-retry request validation |
| [ISS005 Workspace queue presentation](../../workspace/docs/ISSUES.md#iss005-workspace-queue-presentation) | Define the intake presentation interface used by Workspace |
| [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures) | Replace bare fixture imports in coordinated test maintenance |
| [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage) | Review intake/API/scheduling browser scripts and their setup |
| [ISS009 Explicit resource encoding](../../../docs/ISSUES.md#iss009-explicit-resource-encoding) | Preserve imported-report encoding semantics while reviewing source resources |
| [ISS011 Remaining service SQL](../../../docs/ISSUES.md#iss011-remaining-service-sql) | Preserve intake transactions and admission evidence during extraction |
| [ISS014 Current version Windows acceptance](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance) | Native scheduling, saved credentials, acquisition and foreground handoff |
| [ISS015 Pre-registration upgrade race](../../settings/docs/ISSUES.md#iss015-pre-registration-upgrade-race) | Owned task migration, disabled-task repair journal and guarded installed scheduler startup |

Use the [project tracking rules](../../../docs/ISSUES.md#maintaining-this-register)
when adding, resolving or deferring work. Keep protocol history and acceptance
records in their documented scope; they are not a second backlog.
