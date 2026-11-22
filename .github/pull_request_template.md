## Problem and resulting behavior

Describe the concrete problem and what changes for the user.

For more than 50 lines of non-domain logic, or any implementation of a standard
protocol, parser, or security primitive, link the owning issue's library decision.
It should name the library evaluated and justify any custom implementation.

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
