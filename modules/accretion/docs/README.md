# Accretion module guide

Accretion is the application's **Data** module. It acquires Shadowserver reports,
retains their original rows, and runs **Filter → Qualify → Evaluate → Associate**
to produce actionable leads. Qualify requires source findings, authoritative
attribution and a functioning related website with its screenshot. Scoring and
contact work begin only at their owning later stages.

## Documentation map

| Task | Maintained specification |
| --- | --- |
| Understand the funnel, typed products, gates, scoring and publication | [Pipeline and domain contracts](PIPELINE.md) |
| Understand supported reports or add an adapter/finding family | [Report schemas and admission](REPORT_SCHEMAS.md) |
| Archive invalid/context rows or query complete original fields | [Dark Matter component contract](DARK_MATTER.md) |
| Operate imports, reviews, retries, acquisition and schedules | [Operations and recovery](OPERATIONS.md) |
| Review unresolved work and dated implementation evidence | [Module issues](ISSUES.md) |

The guides describe current behavior. The issue register separates delivered work
from open policy/performance questions and historical audit evidence. Shared
maintenance, environment and release rules remain in
[Development](../../../docs/DEVELOPMENT.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

## Boundary

Accretion owns intake decisions, progress, stage orchestration, captured policy,
source profiles, scoring, canonical admission and the Dark Matter archive API.
The Report descriptor contains source identity; it does not own a browser,
provider session or every downstream collection.

| Collaborator | Contract |
| --- | --- |
| [Workspace](../../workspace/docs/README.md) | Application composition, primary database/transactions, workspace lifecycle, backups and outbox delivery |
| [Attribution](../../attribution/docs/README.md) | RDAP/DNS matching, retained proof, analyst approval interpretation and group coverage/reuse |
| [Tools](../../tools/docs/README.md) | Shared identity helpers and full browser capture; no consuming workflow/database ownership |
| [Investigations](../../investigations/docs/README.md) | Outreach holds, screenshot integrity/retention, case adoption, report explanations, readiness and certified evidence |
| [Library](../../library/docs/README.md) | Local CVE/risk facts and reference content; acquisition remains separate from intake scoring |
| [Entities](../../entities/docs/README.md) | Ownership/episodes, entity/domain persistence, matched registry enrichment and contact work |
| [Leads](../../leads/docs/README.md) | Pending finding scope, queue consolidation and lead exports |
| [Observatory](../../observatory/docs/README.md) | Archive/canonical presentation and filtering through owner APIs |
| [Settings and UI](../../settings/docs/README.md) | Saved preferences, guided setup and the composed browser shell |

Original report files, full source rows and canonical finding history survive
promotion. Dark Matter has its own database and public API; other stages do not
build custom archive storage. Database paths in `databases/` are source definitions,
not live workspace data. Workspace coordinates their migrations and transactions.

## Source ownership

| Responsibility | Files |
| --- | --- |
| Report/source/candidate products and readers | [report.py](../components/report.py), [intake/](../components/intake/) |
| Filter selection and result preparation | [intake_filter.py](../components/intake_filter.py), [report_profiles.py](../components/report_profiles.py) |
| Qualified product, local gates, capture and attribution calls | [qualified_lead.py](../components/qualified_lead.py), [qualification.py](../components/qualification.py), [qualification_context.py](../components/qualification_context.py) |
| Evaluate product, scope binding and ranking | [evaluated_lead.py](../components/evaluated_lead.py), [evaluation.py](../components/evaluation.py), [scoring_matrix.py](../components/scoring_matrix.py), [scoring_evidence.py](../components/scoring_evidence.py), [scoring_urgency.py](../components/scoring_urgency.py), [accretion.py](../components/accretion.py) |
| Associate publication | [association.py](../components/association.py), [awareness.py](../components/awareness.py), [awareness_admission.py](../components/awareness_admission.py), [awareness_identity.py](../components/awareness_identity.py) |
| Import lifecycle, reviews and export recovery | [intake_service.py](../components/intake_service.py), [qualification_reconciliation.py](../components/qualification_reconciliation.py), [intake_progress.py](../components/intake_progress.py) |
| Complete source archive | [dark_matter.py](../components/dark_matter.py), [store](../components/dark_matter_store.py), [fields](../components/dark_matter_fields.py), [schema](../databases/dark_matter_schema.py) |
| Acquisition, receipts and account jurisdiction | [api_acquisition.py](../components/api_acquisition.py), [api_import.py](../components/api_import.py), [api_jurisdiction.py](../components/api_jurisdiction.py) |
| Vendored acquisition client and provenance | [shadowserver_reports/](../components/shadowserver_reports/), [shadowserver_api/](../components/shadowserver_api/) |
| Saved schedules and Windows handoff | [scheduling.py](../components/scheduling.py), [windows_schedule.py](../components/windows_schedule.py), [schedule_handoff.py](../components/schedule_handoff.py) |
| HTTP and browser integration | [routes/](../components/routes/), [api_models.py](../components/api_models.py), [static/](../static/) |
| Inventory, synthetic examples and developer checks | [schemas/](../schemas/), [resources/](../resources/), [tools/](../tools/), `tests/` in the source checkout |

`qualification_context.py` is a small read-only adapter to Entities, not another
attribution/reuse engine. Shared suffix/IP comparison comes from Tools; admission
still owns public-suffix, jurisdiction and finding policy. Consumers import the
reader/model owner directly instead of using IntakeService as a utility facade.

Browser `intake.install(ctx)` supplies upload/import/progress actions to the shell;
it does not install Workspace. Dropzone binding is idempotent, and the event
owner's `dispose()` removes listeners. Repeated rendering must not duplicate
uploads. The [source map](../../../docs/program-map.html) shows actual imports,
public symbols and related checks.

## Verification

Use the [project development environment](../../../docs/DEVELOPMENT.md#windows-ide-setup)
and run from the repository root:

```text
python -m pytest -q modules/accretion/tests
python tools/program_map.py --check
```

Select focused checks by the contract being changed, then follow the
[shared verification policy](../../../docs/DEVELOPMENT.md#maintenance-workflow).
For a completed pipeline behavior change, include affected Attribution, Entities,
Leads and Investigations callers. Tests must prove useful decisions and retained
evidence, not merely reproduce the implementation.

| Contract | Representative checks |
| --- | --- |
| Typed source/evidence/score handoffs | `test_candidate_contract.py`, `test_report_contract.py`, `test_qualified_product.py`, `test_evaluated_lead_contract.py` |
| Filter correctness and avoided work | `test_filter_boundary.py`, `test_intake_filter_efficiency.py`, profile/version tests |
| Stage ordering, review/retry and publication | `test_intake_funnel.py`, `test_qualified_lead_contract.py`, `test_qualification_ownership_races.py`, `test_intake_association_cleanup.py` |
| Source archival and normalization | `test_dark_matter_store.py`; Workspace `test_dark_matter_lifecycle.py` and Observatory archive tests |
| Scoring matrix, projections and queue behavior | `test_accretion_scoring.py`, `test_accretion_queue.py`; Leads `test_frontier_evaluation_contract.py` |
| Acquisition and scheduling | `test_api_acquisition_routes_098.py`, vendored client fixtures and scheduling tests |
| Browser composition and API flow | `test_intake_interface.cjs`; the project verifier's `api` browser suite |

The named tests are supplied in the source checkout under their owning module's
`tests/` directory. Pure calibration, API demo,
CLI and browser commands are in [Operations](OPERATIONS.md#develop-and-verify).
Native Task Scheduler/credential/release acceptance remains a separate Windows
check. Record performance with input mix, normalization/provider counts, elapsed
time, working memory, payload/archive size and transaction duration; test counts
or moving data to another file alone do not establish a speed improvement.

## Remaining work

[ISS024](ISSUES.md#iss024-filter-contracts-and-interruption) retains independent
HTTP detector/version policy and incremental family/template expansion.
[ISS027](ISSUES.md#iss027-qualify-decisions-and-workflow) retains group deadline,
provider lifetime, measured overlap and review-paging work. Contact crawl scope is
owned separately by [Entities ISS044](../../entities/docs/ISSUES.md#iss044-qualified-website-contact-scope).
These do not relax the current evidence gates. See the canonical issues for
criteria and evidence rather than treating an earlier audit as current behavior.
