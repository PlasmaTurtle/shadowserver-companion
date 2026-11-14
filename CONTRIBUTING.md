# Contributing

Shadowserver Eclipse is a local Windows application. This repository contains
source, synthetic tests and release tooling; it is not a casework workspace.
[DEVELOPMENT.md](DEVELOPMENT.md) is the detailed development and release guide.

## Propose a change

Use a bug report for reproducible failures and a feature request for a concrete
workflow improvement. Keep each pull request focused on one problem. Work on a
branch, describe the behavior before and after the change, and include the checks
you actually ran. Explain skipped checks and remaining platform limitations.

Use fictional organizations, domains reserved for examples, and synthetic records
in reproductions. Never commit or attach API keys, browser session URLs, working
databases, real intake reports, case evidence, contact lists or workspace backups.
This applies to issue text, screenshots, logs and CI artifacts as well as source.
See [SECURITY.md](SECURITY.md) for security concerns and [SUPPORT.md](SUPPORT.md)
for troubleshooting.

## Set up and verify

Use Python 3.14 and Node.js for development. The installed application does not
require Node. From the repository root, create and activate a virtual environment,
then run:

```text
python -m pip install -r requirements-dev.txt
npm ci
npx playwright install chromium
python tools/verify.py --report verification.json
```

On Linux, Playwright may also need system browser libraries. The verifier uses an
isolated synthetic workspace. Never point a development run at installed casework.
For a fast iteration, run the relevant pytest files or frontend suite first, then
use the verifier before requesting release acceptance. A run with
`--skip-browser`, `--skip-backend` or `--only-browser` is partial verification;
report it as such. Documentation-only changes can use link and content review.

## Preserve the project contracts

- Use `docs/MODULE_GUIDE.md` and `docs/components.json` to find the owning module.
  Run `python tools/program_map.py --write` when changing owned source files,
  inspect the generated diff, then run `python tools/program_map.py --check`.
- Do not cosmetically edit `workbench/approved_template.py`; its exact bytes are
  protected by regression tests. Preserve existing certified evidence and history.
- Keep changes to dependencies consistent with the Windows pins, bundled wheels,
  hash manifests and component source manifests. A successful package install is
  not a release integrity check. Follow the security gate in `DEVELOPMENT.md`.
- Keep version and release-channel metadata synchronized. An automated CI pass
  does not establish native Windows acceptance or authorize stable promotion.
- Keep operational implementation details out of recipient-facing report text.

Do not add a license or redistribute third-party assets without confirming the
applicable rights and retained notices. Release publication follows the existing
release gates and version-specific workstation acceptance in
[HOME_VALIDATION.md](HOME_VALIDATION.md).
