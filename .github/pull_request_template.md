## Problem and resulting behavior

Describe the concrete problem and what changes for the user.

For an implementation over 50 authored lines, link the decision recorded before
implementation (or before line 51 if the scope grew). If custom code replaces an
established option, point reviewers to the evidence for that choice.

## Validation

List the exact checks run and their results. Identify skipped checks and remaining
Windows acceptance needs. For documentation-only changes, describe your review.

## Compatibility and release impact

Describe any changes to stored data, certified artifacts, dependencies, installation
or update behavior. Write "None" when this does not apply.

## Review checklist

- [ ] The diff is focused and contains no credentials, real casework or operational data.
- [ ] Tests and documentation reflect the changed behavior, where applicable.
- [ ] Changes to a module's behavior, interfaces or maintenance have an entry under `Unreleased` in its changelog.
- [ ] Source/module maps and dependency manifests were updated if affected.
- [ ] Partial verification and platform limits are stated accurately.
