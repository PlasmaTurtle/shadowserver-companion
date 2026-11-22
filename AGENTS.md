# Project maintenance rules

These rules apply to all modules, shared code and tools.

> Before writing more than 50 lines of non-domain logic—or any code implementing a standard protocol, parser, or security primitive—stop, name the established open-source library that solves it, and justify why a custom implementation is strictly necessary.

Record the decision in the owning issue and link the upstream evidence.
[Library selection](docs/DEVELOPMENT.md#library-selection)

- Work in the user's designated repository. Sync and verify changes made in another checkout.
  Preserve unrelated edits. If sync is blocked, provide a patch checked against the target.
- Read the module guide and issue before editing. Keep code, tests and assets with their
  owner. Put reusable runtime tools in `modules/tools/` and developer commands in root or module `tools/`.
  [Module ownership](docs/ARCHITECTURE.md#module-ownership-and-source-layout)
- Compare the real output with a working reference. If the reference succeeds and the
  implementation fails, revisit the approach before adding a workaround.
- Run focused checks first. Show the improvement to the module. Batch compatible build
  checks and skip builds for prose-only changes. [Maintenance workflow](docs/DEVELOPMENT.md#maintenance-workflow)
- Work locally and use Windows for native checks. The paid GitHub Actions budget is zero.
  [Execution policy](docs/DEVELOPMENT.md#maintenance-and-execution-policy)
- Update the owning module's `CHANGELOG.md` under `Unreleased` in the same commit.
  Bump the version and commit the inputs before handing off a changed installer or source
  release. [Release workflow](docs/DEVELOPMENT.md#building-a-release)
