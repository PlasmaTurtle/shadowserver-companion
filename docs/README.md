# Documentation

Use these guides for the current Shadowserver Eclipse application. Start with the
[project overview](../README.md) for capabilities and installation, or the
[user guide](USER_GUIDE.md) for the analyst workflow.

## Use Eclipse

| Task | Guide |
| --- | --- |
| Set up, import reports, review leads, prepare notifications, and record outreach | [User guide](USER_GUIDE.md) |
| Back up, restore, inspect, or recover a workspace | [Data management](DATA_MANAGEMENT.md) |
| Understand software update checks and distribution | [Software updates](SOFTWARE_UPDATES.md) |
| Troubleshoot or report a problem | [Support](../SUPPORT.md) |
| Understand security boundaries or report a vulnerability | [Security](../SECURITY.md) |

## Develop and maintain

| Task | Reference |
| --- | --- |
| Set up an environment, run checks, and build a candidate | [Development](../DEVELOPMENT.md) |
| Propose a change and prepare a pull request | [Contributing](../CONTRIBUTING.md) |
| Understand the application structure and contracts | [Architecture](../ARCHITECTURE.md) |
| Find the module that owns a behavior | [Module guide](MODULE_GUIDE.md) · [Interactive source map](program-map.html) |
| Review dependency pins, assets, and provenance | [Dependencies](../DEPENDENCIES.md) |
| Understand input validation and retained evidence | [Input validation](INPUT_VALIDATION.md) |
| Check Observatory behavior | [Observatory acceptance](OBSERVATORY_ACCEPTANCE.md) |
| Maintain GitHub checks, reviews, and release controls | [GitHub maintenance](GITHUB_MAINTENANCE.md) |

Component documentation stays beside its implementation:

- [Attribution Module](../components/attribution/README.md): setup, matching, CLI, and Python API.
- [Shadowserver Reports integration](../components/shadowserver_api/README.md): acquisition, receipts, and integration provenance.
- [Windows installer](../tools/windows_installer/README.md): build, installation identity, and acceptance.

## Review a release

| Question | Source of record |
| --- | --- |
| What version and release channel is this? | [Release metadata](../RELEASE.json) |
| What changed between versions? | [Changelog](../CHANGELOG.md) |
| What checks were recorded for the candidate, and what remains unverified? | [Validation evidence](../VALIDATION.md) |
| What must be exercised on a Windows workstation? | [Windows acceptance checklist](../HOME_VALIDATION.md) |
| Why was an earlier decision made? | [Historical records](history/README.md) |

Build evidence is specific to the recorded version and environment. It is not a
live CI status page or approval of later commits. A merged change is available in
the source branch; distributing it requires a separately built and validated release.

## Keep the documentation dependable

**One topic, one maintained home.** Put operating instructions in the user guide,
developer commands in Development, architectural contracts in Architecture or the
owning component reference, and release changes in the changelog. Link to these
homes instead of copying their content into the README or a new release log.

Update the relevant guide in the same change that alters behavior. Use current
interface labels and commands that work from the stated directory. Explain who a
page is for and distinguish instructions, verified results, and proposed work.

Put completed release narratives, audits, experiments, and dated validation records
in [history](history/README.md). Preserve their original scope and evidence; do not
silently rewrite a past result as current acceptance. An archived recommendation
is not automatically resolved or an active requirement. Carry confirmed current
requirements into the appropriate maintained guide before archiving their source.

Keep the root README short: purpose, supported platform, status, first steps, and
navigation. Keep component READMEs as entry points; detailed contracts belong in
their adjacent `REFERENCE.md`. Prefer useful headings and short task tables over
decorative badges or repeated feature inventories.

Before merging documentation changes, check local links and heading anchors,
compare version claims with release metadata, and check packaged copies as well as
GitHub. Distribution uses an explicit document allowlist; new pages and moves must
be included deliberately. Generated source maps are maintained by
`python tools/program_map.py --write`, not edited by hand.
