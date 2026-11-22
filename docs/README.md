# Documentation

Use the [maintenance workflow](DEVELOPMENT.md#maintenance-workflow) before changing
code, then read the owning module's guide, tracker and changelog below. The
[project overview](../README.md) covers installation and capabilities; the
[user guide](USER_GUIDE.md) covers analyst work.

## Use Eclipse

| Task | Guide |
| --- | --- |
| Set up, import reports, review leads, prepare notifications, and record outreach | [User guide](USER_GUIDE.md) |
| Back up, restore, inspect, or recover a workspace | [Data management](../modules/workspace/docs/DATA_MANAGEMENT.md) |
| Understand software update checks and distribution | [Software updates](../modules/settings/docs/SOFTWARE_UPDATES.md) |
| Troubleshoot or report a problem | [Support](USER_GUIDE.md#support-and-troubleshooting) |
| Understand security boundaries or report a vulnerability | [Security](../SECURITY.md) |

## Develop and maintain

Each project document has one maintained responsibility. Keep module-specific
implementation and issue detail in its module, and link it from this index.

| Responsibility | Maintained home |
| --- | --- |
| Product overview, first start and navigation | [Root README](../README.md) |
| Maintenance policy, execution/cost constraints, environment, verification and release commands | [Development](DEVELOPMENT.md) |
| Contribution and review expectations | [Contributing](DEVELOPMENT.md#contributing) |
| Application contracts, module ownership and dependency direction | [Architecture](ARCHITECTURE.md) |
| Project-wide issues and index of module-owned work | [Project issue register](ISSUES.md) |
| Find the layer that owns a behavior | [Change navigation](ARCHITECTURE.md#where-to-make-the-next-change) · [Interactive source map](program-map.html) |
| Dependency locks, bundled assets, licenses and provenance | [Dependencies](DEPENDENCIES.md) |
| Shared response validation, scanning and retained-evidence contracts | [Input validation](INPUT_VALIDATION.md) |
| Security reporting, trust boundaries and limitations | [Security](../SECURITY.md) |
| GitHub-specific collaboration, workflow configuration and administration | [GitHub maintenance](GITHUB_MAINTENANCE.md) |
| Exact-version workstation acceptance | [Windows checklist](WINDOWS_ACCEPTANCE.md) |
| Product highlights shown in the app's What's New view | [Release changelog](../CHANGELOG.md) |
| Dated plans, audits and verification evidence | [History](history/README.md) |

## Module documentation and tracking

The guide describes the module's contracts and verification. The tracker records
problems, status and evidence. The changelog records completed changes under
`Unreleased` until they ship under an application version. Add the entry in the
same change as the implementation. See [Building a release](DEVELOPMENT.md#building-a-release)
for how module entries feed the product changelog. All modules use the same
[library selection rule](DEVELOPMENT.md#library-selection)
and keep the evidence in the owning issue.

| Module | Maintenance guide | Issue tracker | Changelog |
| --- | --- | --- | --- |
| Workspace | [Guide](../modules/workspace/docs/README.md) | [Issues](../modules/workspace/docs/ISSUES.md) | [Changes](../modules/workspace/docs/CHANGELOG.md) |
| Investigations | [Guide](../modules/investigations/docs/README.md) | [Issues](../modules/investigations/docs/ISSUES.md) | [Changes](../modules/investigations/docs/CHANGELOG.md) |
| Observatory | [Guide](../modules/observatory/docs/README.md) | [Issues](../modules/observatory/docs/ISSUES.md) | [Changes](../modules/observatory/docs/CHANGELOG.md) |
| Entities | [Guide](../modules/entities/docs/README.md) | [Issues](../modules/entities/docs/ISSUES.md) | [Changes](../modules/entities/docs/CHANGELOG.md) |
| Leads | [Guide](../modules/leads/docs/README.md) | [Issues](../modules/leads/docs/ISSUES.md) | [Changes](../modules/leads/docs/CHANGELOG.md) |
| Attribution | [Guide](../modules/attribution/docs/README.md) | [Issues](../modules/attribution/docs/ISSUES.md) | [Changes](../modules/attribution/docs/CHANGELOG.md) |
| Accretion (Data) | [Guide](../modules/accretion/docs/README.md) | [Issues](../modules/accretion/docs/ISSUES.md) | [Changes](../modules/accretion/docs/CHANGELOG.md) |
| Library | [Guide](../modules/library/docs/README.md) | [Issues](../modules/library/docs/ISSUES.md) | [Changes](../modules/library/docs/CHANGELOG.md) |
| Settings | [Guide](../modules/settings/docs/README.md) | [Issues](../modules/settings/docs/ISSUES.md) | [Changes](../modules/settings/docs/CHANGELOG.md) |
| Activity | [Guide](../modules/activity/docs/README.md) | [Issues](../modules/activity/docs/ISSUES.md) | [Changes](../modules/activity/docs/CHANGELOG.md) |
| UI | [Guide](../modules/ui/docs/README.md) | [Issues](../modules/ui/docs/ISSUES.md) | [Changes](../modules/ui/docs/CHANGELOG.md) |
| Tools | [Guide](../modules/tools/docs/README.md) | [Issues](../modules/tools/docs/ISSUES.md) | [Changes](../modules/tools/docs/CHANGELOG.md) |

Component documentation stays beside its implementation:

- [Attribution Module](../modules/attribution/components/engine/README.md): setup, matching, CLI, and Python API.
- [Shadowserver Reports integration](../modules/accretion/docs/OPERATIONS.md#shadowserver-reports-integration): acquisition, receipts, and integration provenance.
- [Windows installer](../tools/windows_installer/README.md): build, installation identity, and acceptance.

## Review a release

| Question | Source of record |
| --- | --- |
| What version and release channel is this? | [Release metadata](../RELEASE.json) |
| What changed between versions? | [Recent changes](../CHANGELOG.md) · [Earlier changelog](history/releases/CHANGELOG_PRE_0.11.md) |
| What checks were recorded for the November 14 candidate build, and what remained unverified? | [Dated candidate evidence](history/validation/VALIDATION_0120.md) |
| What did the full build after module maintenance and Library repairs establish? | [November 21 full-build results and limits](history/validation/full-build-2026-11-21.md) |
| What must be exercised on a Windows workstation? | [Windows acceptance checklist](WINDOWS_ACCEPTANCE.md) |
| Why was an earlier decision made? | [Historical records](history/README.md) |

Build evidence is specific to the recorded version and environment. It is not a
live CI status page or approval of later commits. A merged change is available in
the source branch; distributing it requires a separately built and validated release.

## Keep the documentation dependable

**One topic, one maintained home.** Put operating instructions in the user guide,
developer commands in Development, architectural contracts in Architecture or the
owning module guide, outstanding problems and planned work in their canonical
project or module issue tracker, and completed module changes in that module's
changelog. The root changelog summarizes the highlights for users.

Update the relevant guide in the same change that alters behavior. Use current
interface labels and commands that work from the stated directory. Explain who a
page is for and distinguish instructions, verified results, and proposed work.

Put completed release narratives, audits, experiments, and dated validation records
in [history](history/README.md). Preserve their original scope and evidence; do not
silently rewrite a past result as current acceptance. An archived recommendation
is not automatically resolved or an active requirement. Carry confirmed current
requirements into the appropriate maintained guide before archiving their source.

Delete superseded or duplicate guidance once any unique current contract has a
maintained home. Archive material that retains useful historical evidence; do
not archive every discarded paragraph. Preserve required licenses, provenance,
supported compatibility instructions and relevant validation records. When
removing a document, update inbound links, indexes and distribution allowlists
in the same change.

Keep the root README short: purpose, supported platform, status, first steps, and
navigation. Each module maintains `docs/README.md`, `docs/ISSUES.md` and
`docs/CHANGELOG.md`. Keep ownership, contracts and verification in the guide.
Add a separate runbook, reference or checklist when it serves a distinct task.
Standalone libraries retain their independent package documentation.

Before a refactor, check the module guide, canonical issue and affected caller
contracts. Afterward, update the changed contract or command and the issue's
evidence in the same change. A bug, design rule, operating instruction and past
test result have different homes; moving a file does not resolve its issue.

Before merging documentation changes, check local links and heading anchors,
compare version claims with release metadata, and check packaged copies as well as
GitHub. Distribution uses an explicit document allowlist; new pages and moves must
be included deliberately. Generated source maps are maintained by
`python tools/program_map.py --write`, not edited by hand.
