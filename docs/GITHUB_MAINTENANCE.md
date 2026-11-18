# GitHub maintenance

This is the private source repository for Shadowserver Eclipse. Keep operational
records, credentials and installed workspaces out of GitHub, including issue
attachments and Actions logs. Repository visibility is not a casework boundary.

## Change and review workflow

1. Open a concise bug or feature issue with a synthetic reproduction and acceptance
   criteria. Security reports follow [SECURITY.md](../SECURITY.md).
2. Create a short-lived branch and a focused pull request. Link the issue using
   `Fixes #number` when the change resolves it. Record actual test results and limits.
3. Review the diff and CI results. Dependency changes must pass the exact bundled
   wheel and source integrity gate, not just install successfully.
4. Merge after review, then remove the completed branch. Prefer a squash merge for
   one coherent change unless individual commits are useful history.

`@PlasmaTurtle` is the code owner. CODEOWNERS records ownership; it does not itself
prevent merging. A sole maintainer cannot approve their own pull request, so do
not require an unavailable second reviewer and then routinely bypass the rule.

For the current project size, issues plus a milestone for the next candidate are
sufficient. If a GitHub Project is used, use Backlog, Ready, In progress, In review
and Done statuses, with one owner and observable acceptance criteria per item.
Keep the issue or milestone as the source of truth rather than maintaining a second progress log in Markdown.

## Automated checks

The [CI workflow](https://github.com/PlasmaTurtle/shadowserver-companion/blob/main/.github/workflows/ci.yml)
is the source of truth for runner selection and triggers. At this documentation
revision it runs the complete `tools/verify.py` on Ubuntu 24.04 and Windows 2025 with
Python 3.14, Node 24 and Chromium. It also checks bundled wheel/source integrity.
The verifier covers release identity, module boundaries, formatting, lint, backend
regressions, frontend contracts and its registered synthetic browser suites.
It is not the complete manual workstation/installer acceptance procedure.

Source identity, module-map drift, formatting, lint and frontend contracts run
before downloading Chromium. This preflight writes `verification-preflight.json`
with `complete: false`; only the subsequent full run can record complete
verification. Fix stale generated maps with `python tools/program_map.py --write`
and commit both generated outputs with the source change. The workflow checks
these outputs; it never silently regenerates them to hide repository drift.

The workflow uses read-only repository permissions, full commit action pins,
ephemeral hosted runners, no persisted checkout credential, cancellation of
superseded runs, and a 60-minute job ceiling. It preserves source line endings
because component manifests and approved report templates depend on exact bytes.
Only verification/dependency summaries are retained, for 14 days; no workspace,
database, browser profile, screenshot bundle or raw server log is uploaded.

The dependency-security workflow checks exact bundled Python versions and npm
development dependencies each Monday and on relevant changes. npm findings at
high or critical severity fail its check. The Python gate fails on findings or
incomplete scans. These checks contact package/advisory services and do not
establish the safety of the embedded interpreter or every native codec.

Dependabot proposes weekly grouped updates. Review each proposal; automatic
merging is not enabled. Python updates often require a coordinated refresh of
`requirements-constraints.txt`, `requirements-windows.txt`, both wheelhouses and
their hash/source manifests. Never weaken the integrity gate to accept an isolated
version bump. Actions updates must preserve full SHA pins.

If a check fails, reproduce its command and fix the cause. Record an existing
failure explicitly; do not turn mandatory checks into `continue-on-error` steps.
The dependency workflow uses path filters and should not be a universally
required check, because it intentionally does not run on every pull request.

## Settings requiring repository administration

Repository administration and available controls depend on the account plan and
integration permissions. Check the actual settings before treating a control as
enforced. The [November 14 repository audit](history/reviews/GITHUB_REPOSITORY_AUDIT_2026_11_14.md)
records the access limitations observed during setup; it is not a live settings inventory.
The following are recommendations, **not a claim that these controls are enabled**:

- When the repository plan supports protection, require a pull request, resolved
  review conversations, and the relevant passing checks on `main`. Establish a
  repeatable Windows application check before requiring it. Linux tool execution
  does not make Linux a supported application platform. Select exact check names
  from the current workflow rather than copying names from an old audit. Block
  force pushes and branch deletion, with an appropriate sole-maintainer policy.
- Enable automatic deletion of merged branches and keep squash merging available.
- Set the default Actions token to read-only, disable workflow PR approval, and
  restrict permitted actions to reviewed publishers/actions with full SHA pins.
- Review Dependabot alerts and security updates, the dependency graph, and secret
  scanning/push protection where the private-repository plan permits them.
- Enable private vulnerability reporting if available, or publish an approved
  security contact route. Do not invent an address or a response commitment.
- Review collaborator access periodically. Do not change visibility or buy an
  account upgrade merely to activate a repository control.

## Releases and distribution

Keep generated installers and release ZIPs in GitHub Releases or approved
distribution storage, rather than adding each build to Git history. The checked-in
wheelhouses are deliberate inputs to the offline Windows installation and hash
gate; they are not removed as generic binary clutter. Third-party license notices
remain with their assets and wheels.

Before creating a release tag, follow [DEVELOPMENT.md](../DEVELOPMENT.md), the
security gate, and [HOME_VALIDATION.md](../HOME_VALIDATION.md). Match `VERSION`,
`RELEASE.json`, package metadata, filenames and changelog. Publish a candidate as
a prerelease, include checksums, actual validation evidence and signing status,
and promote only after acceptance of that exact version. CI does not publish,
sign, tag, or promote releases automatically.

No application license was added. Rights to distribute the application and use
agency branding require an explicit owner decision before broader publication.
Keep that decision separate from third-party notices already present.

## References

- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
- [Workflow dependency lockfiles](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)
- [Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
- [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

Full SHA pins are used here. A generated Actions dependency lockfile can be
evaluated later; it must be generated and verified with GitHub's supported tooling,
not handwritten as an apparent guarantee of provenance.


## Documentation maintenance

Use the [documentation index](README.md) to find the maintained home for each
topic. Put dated audits and execution evidence in [history](history/README.md);
record ongoing work in issues and milestones rather than appending session logs
to setup or architecture guides. Keep README navigation and packaged copies in
sync when adding or moving documentation.
