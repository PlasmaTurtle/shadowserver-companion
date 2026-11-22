# Project maintenance rules

These rules apply throughout the repository. Read the complete
[maintenance and execution policy](docs/DEVELOPMENT.md#maintenance-and-execution-policy)
and [maintenance workflow](docs/DEVELOPMENT.md#maintenance-workflow) before changing
source. This file is the agent entrypoint; Development owns shared policy and commands.

## Before choosing the workflow

Establish scope, environment, verification and stop condition; reuse verified
session facts and authorization. Follow the
[workflow prerequisites](docs/DEVELOPMENT.md#before-choosing-the-workflow).

## Established implementations and reference behavior

Before starting any implementation expected to exceed 50 authored lines, research
the established options and record the choice in the owning issue. If smaller
work grows, record the decision before writing line 51. Count one capability
across files, commits and delegated work. This applies to every module and
shared tooling. To write a custom replacement, show the specific gap in the
best established option and why a thin integration cannot meet the need.
Follow the [framework decision rule](docs/DEVELOPMENT.md#framework-decisions-for-work-over-50-lines).

Compare real inputs and outputs with the working reference. Revisit the choice
when fixes accumulate or the reference succeeds where the implementation fails.
See the [reference-behavior policy](docs/DEVELOPMENT.md#established-implementations-and-reference-behavior).

## Where work runs

Use the local repository designated by the user as the delivery target. When
working in a separate checkout, sync the verified changes into that repository
and check its working tree before reporting delivery. Preserve unrelated local
edits. If workspace permissions block the sync, report the exact target and
provide a patch verified against its current working tree.

Work locally first and use available Windows workstations for native evidence.
**Paid GitHub Actions usage has a zero budget.** Check all hosted triggers and
included usage; do not enable paid runs, raise caps or retry exhausted budgets.
Follow the [execution policy](docs/DEVELOPMENT.md#where-work-runs).

## How failures are handled

Classify infrastructure, harness, application and approach failures before editing.
Preserve evidence, stop uninformative retries and remove obsolete workarounds.
Do not introduce unrelated upgrades or sharding during diagnosis. Follow the
[failure policy](docs/DEVELOPMENT.md#how-failures-are-handled).

## What counts as validation

Demonstrate a material, observable improvement to the module's purpose. Passing
tests alone is not success; test-only repairs are verification debt. Do not weaken
checks to pass. Use focused checks first, batch compatible smaller issues into one
final integration/build run, and avoid builds for prose-only changes. Retain actual
results and limits under the [validation policy](docs/DEVELOPMENT.md#what-counts-as-validation)
and [verification matrix](docs/DEVELOPMENT.md#maintenance-workflow).

Record completed module changes in `modules/<owner>/docs/CHANGELOG.md` under
`Unreleased` in the same commit. Use those entries for the root release notes.
Before handing off an installer or source release with changed contents, advance
the application version and commit the release inputs. Follow the
[release versioning workflow](docs/DEVELOPMENT.md#building-a-release).

## Source ownership

Follow [module ownership](docs/ARCHITECTURE.md#module-ownership-and-source-layout).
Keep implementation, tests, assets and interfaces with their owner, contracts in
the module guide and status in one canonical issue. Global interfaces need explicit
consumers and dependency direction; do not create unstructured helper collections.
Use consistent composition/lifecycle contracts and compare simpler alternatives.

Reusable runtime tools belong in `modules/tools/`; callers own workflow, UI and
persistence. Root `tools/` and module `tools/` hold developer commands. Follow the
[tool input/output contract](modules/tools/docs/README.md#boundary-and-public-interface)
and [reuse audit](modules/tools/docs/TOOL_AUDIT.md). Compare inputs, results, failures
and real callers before extraction; remove superseded implementations in the same
migration. Relocation must not silently change saved data, schemas, approved wording
or business behavior.
