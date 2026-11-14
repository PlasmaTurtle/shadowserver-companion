# GitHub repository audit — 2026-11-14

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Repository: `PlasmaTurtle/shadowserver-companion` (private).
Baseline: `844c950ac2b063c18c06aca71fd7666114e7df64`, Eclipse 0.12.0 candidate.
Scope: GitHub automation, contributor workflow, repository hygiene, ownership,
release practices and observable settings. This is not a new application-security
assessment or Windows deployment acceptance.

## Findings and changes

| Priority | Baseline evidence | Resolution |
| --- | --- | --- |
| High | No `.github/workflows/` entries in the baseline Git tree; `tools/verify.py:96` already defines release, boundary, formatting and regression gates. | Added CI invoking the existing complete verifier on Linux and Windows, plus wheel/source integrity. No checks are ignored to manufacture a pass. |
| High | `tools/check_dependencies.py` provides exact bundled-version advisory checks but no scheduled GitHub caller existed. No Dependabot configuration existed. | Added scheduled/change-triggered Python and npm advisory checks and grouped weekly dependency proposals. Python wheel/constraint/hash alignment remains mandatory. |
| High | `SECURITY.md:3` began technical boundary documentation without a vulnerability reporting route. | Added a private-contact reporting process, synthetic reproduction guidance and truthful support limits. No invented mailbox or response SLA. |
| Medium | Root `.gitignore` covered caches, databases and logs but omitted `.env` and private-key files. `.gitattributes` omitted `.whl` and `.ico`. | Added local credential/output ignore patterns and explicit binary rules. Ignore rules do not remove existing Git history or replace secret scanning. |
| Medium | No contributor/support entry points, issue forms, PR template or code-owner file existed. | Added focused forms, contributor/support guides, PR evidence checklist and `@PlasmaTurtle` ownership. Enforcement is not claimed. |
| Medium | `DEVELOPMENT.md:3` still identified 0.11.1; its build examples used the previous release filenames. | Updated current development heading and build filenames to 0.12.0 Guided Setup. Preserved historical validation statements. |
| Low | `GITHUB_PUSH_TEST.txt` was a two-line upload diagnostic with no application code. | Removed from the current tree; Git history preserves it. |
| Medium | Rulesets API returned HTTP 403 requiring GitHub Pro or public visibility; branch-protection read returned an integration permission error. | Documented controls and exact constraints in `GITHUB_MAINTENANCE.md`. No visibility or paid-plan change. Protection remains unverified, not asserted absent. |

New workflow controls: full-SHA official action references; read-only contents
permission; checkout credentials not persisted; no application secrets; hosted
ephemeral runners; bounded runtime; cancellation of superseded runs; summary-only
artifacts with 14-day retention. Windows checkout disables newline conversion to
preserve the bytes covered by existing component/template checks.

The README links to the new guides. `tools/release_policy.py` includes
`CONTRIBUTING.md` and `SUPPORT.md` in the existing explicit allowlist so source
archives retain those links. GitHub automation stays repository-only. Existing
wheelhouses, lockfiles, third-party notices and protected report bytes are retained.

## Validation

- Baseline source snapshot matched every corresponding remote blob; the only
  remote-only file was the upload diagnostic listed above.
- Action references resolved against the official Actions repositories.
- `actionlint 1.7.12` passed both workflows (embedded shell/Python linters disabled;
  no embedded scripts need those optional tools). Download SHA-256 matched the
  official release checksum.
- YAML parsing, issue-form structure, field identifiers and local Markdown links
  checked. No generated contact address or nonexistent label was added.
- Ruff 0.14.3: all 527 Python files formatted; lint passed.
- Prettier 3.6.2: frontend/test formatting passed; frontend syntax passed.
- `npm test`: all 63 frontend suites passed.
- Release identity, offline wheel/source integrity and module map checks passed
  (21 components, 373 owned modules).
- Release privacy and installer lifecycle tests: 17 passed.
- Full backend execution was still running when this audit commit was prepared.
  Hosted Linux/Windows CI and advisory-service results must be read in Actions;
  configuration validation is not a claim that those runs succeeded.

## Remaining decisions and limits

See [GitHub maintenance](../../GITHUB_MAINTENANCE.md) for the change/release workflow and
administrator settings. Account settings, alert enablement, secret scanning and
branch enforcement could not be changed through the available integration; the
browser settings route required sign-in. No paid security service was enabled.

No application license was present and none was selected automatically. The
owner must decide distribution rights and branding before broader publication.
Checked-in Windows wheels are intentional offline build inputs, not an excuse
to commit subsequent generated installers. No release, tag, signing claim,
external notification or project board was created by this audit.

These controls improve source maintenance. They do not replace operator review,
current-version workstation acceptance, or existing candidate release gates.

