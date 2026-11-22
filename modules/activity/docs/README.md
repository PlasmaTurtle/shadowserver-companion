# Activity

Activity owns activity routes, work-log projections and exports, and browser
activity presentation. This guide covers how to maintain those views without
changing the originating events.

[Module issues](ISSUES.md) · [Changelog](CHANGELOG.md) · [Architecture](../../../docs/ARCHITECTURE.md) ·
[Maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow) ·
[Framework decisions over 50 lines](../../../docs/DEVELOPMENT.md#framework-decisions-for-work-over-50-lines)

## Start here

| Responsibility | Start here |
| --- | --- |
| Case chronology and PDF work-log export | [work_log.py](../components/work_log.py) |
| Bounded application activity stream | [routes/activity.py](../components/routes/activity.py) |
| Stream presentation and delegated search handling | [activity.js](../static/activity.js), [activity_events.js](../static/activity_events.js) |

## Boundary

The module presents recorded work and produces its work-log output. Each
originating domain remains responsible for recording its event in the correct
transaction. Activity must not infer or manufacture missing case chronology.

`work_log.py` builds case chronology and its PDF export. `routes/activity.py`
queries the bounded application activity stream. The browser page renders that
stream; `activity_events.js` registers its search form with the shared event
dispatcher. The case export and application stream intentionally select and
present different records.

`activity.js::install(ctx)` also registers the reusable `activities(items)` markup
used by Workspace's dashboard. Activity owns that chronology presentation; callers
select the records. See [Workspace ISS029](../../workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation).

Keep event selection and formatting distinct from persistence and generic document
rendering. UI owns shared fonts and geometry; the originating module owns event
semantics and retention.

## Verification

Use the [project development setup](../../../docs/DEVELOPMENT.md#windows-ide-setup).
From the repository root:

```text
python -m pytest -q modules/activity/tests
```

Use the [project verification guide](../../../docs/DEVELOPMENT.md#verification)
for shared shell, integration and browser checks. `test_activity_095.py` covers the
application stream, while `test_work_log_050.py` covers case chronology and its
export. A change to recorded event meaning also needs the originating domain's
tests; an Activity projection pass alone does not verify the event writer.

## Maintenance and tracking

Record confirmed module work in [Activity issues](ISSUES.md). Follow the
[project maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow),
review the event-producing callers, and update this guide if selection, output
or retention contracts change.
