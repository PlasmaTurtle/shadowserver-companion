# Project maintenance rules

These rules apply to work throughout this repository. Read [DEVELOPMENT.md](DEVELOPMENT.md)
for commands and [HOME_VALIDATION.md](HOME_VALIDATION.md) for Windows release acceptance.

## Before choosing the workflow

At the start of a task, or when its environment changes, establish the relevant
constraints: exact source revision, available machines and target OS, installed
tools, network access, connector capabilities, permissions, execution limits and
cost budget. Reuse verified session facts and existing authorization. Record
unknowns instead of discovering basic limits through repeated failed runs.

Define the intended result, change scope, verification command and stop condition
before introducing automation. Research unfamiliar approaches using official
documentation and firsthand engineering reports; adapt them to this project's
resources. Use the project's workflow within tool permissions and safety controls.
A plugin's default recipe does not determine the project's architecture.

## Where work runs

1. **Do capable work in the current Codex environment first.** Inspect, edit, build,
   reproduce failures and run valid portable checks here. Do not use hosted CI as
   the first debugging environment for work that can be done locally.
2. **Use the connected Windows workstation for native Windows evidence.** Once it
   is available, run relevant native tests, installer checks and release acceptance
   there. Valid results for the exact revision are authoritative for the behavior
   tested, regardless of whether GitHub ran them. Until the workstation is connected,
   identify Windows-only verification that remains outstanding.
3. **Paid GitHub Actions usage has a zero budget.** GitHub supplies source control,
   collaboration and optional verification. Do not enable paid usage, raise spending
   limits, or select billable runners. Check available included usage and configured
   triggers before dispatching, retrying or publishing changes that start hosted
   work automatically. Account for push and pull-request triggers, not just manual
   runs. Stop hosted execution attempts at an exhausted cap;
   repeated retries or pushes cannot fix it. Avoid redundant hosted runs, including
   supported CI skips for documentation-only commits where appropriate.

## How failures are handled

4. **Classify the failure before editing.**
   - No executed steps: inspect the run annotation, usage cap, runner access and
     service availability. There is no application-test result yet.
   - Test-harness failure: repair the fixture, dependency setup or automation boundary.
   - Application failure: change application behavior only when evidence identifies
     an application defect.

   Record what is known and what evidence is missing. If the connector cannot expose
   the needed diagnostic, request that specific diagnostic early. Stop a retry loop
   when it produces no new evidence; resume after a relevant change or diagnostic.

5. **Preserve a known baseline and make the smallest supported change.** Do not add
   sharding, unrelated dependency upgrades or workflow redesign while diagnosing
   an unrelated failure. Keep the full, unsharded verifier as the standard baseline.
   Separate improvements from repairs so each result can be attributed to a change.
   Review the final diff against the original request before publishing it.

## What counts as validation

6. **Match checks to the change.** Reproduce the affected behavior and run focused
   checks first. Run the relevant complete suite once for a completed application
   change set. Repeat it only for changed behavior, a new failure or unresolved
   evidence. Documentation-only changes need content, link and formatting review,
   not the application suite.
7. **Keep reproducible evidence.** Record the revision and any uncommitted changes,
   operating system, relevant runtime/dependency versions, command, scope, result
   and skips. Reuse results only while that tested state remains applicable. A
   skipped job is not a pass; a partial run is not complete verification. A hosted
   infrastructure failure does not invalidate an otherwise valid local result.
   Report any repository merge-rule conflict separately; never fabricate a status.
8. **Make automated tests observable and noninteractive.** Use synthetic workspaces,
   record or stub interactive UI boundaries, retain test names and logs, and use
   bounded waits with stack diagnostics. Do not suppress real application behavior
   merely to accommodate an unattended runner.

A successful launch, a complete regression run and exact-version Windows release
acceptance establish different things. Report each accurately. Preserve the
existing release-identity, evidence-integrity and workstation-acceptance gates.
