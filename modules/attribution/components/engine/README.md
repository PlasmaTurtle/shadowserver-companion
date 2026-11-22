# Attribution Module

Review the association between a reported IP address and an organization's domain,
with a saved record of the evidence behind the result.

Eclipse uses this Python component for attribution. It can also run independently
through its CLI or Python API. The current component version is **0.2.8**, as
recorded in [package metadata](pyproject.toml).

## What it provides

- RDAP registration lookups followed by DNS association checks.
- Separately identified Google and Cloudflare DNS observations, with visible
  agreement, disagreement, and incomplete results.
- Explicit match, review, no-match, incomplete, deferred, and ineligible outcomes.
- SQLite history, cached responses, and a printable HTML evidence export.

A match is evidence of an association under the configured policy. It does not
independently prove asset ownership or confirm a vulnerability. Source observations
remain available for analyst review.

## Start on Windows

For the complete Eclipse application, use the [application setup guide](../../../../docs/USER_GUIDE.md).
To use this component on its own:

1. Install Python **3.11 or newer**.
2. Keep this directory intact, including its bundled `wheelhouse`.
3. Run **Setup.cmd** to create a local environment and install the bundled packages.
4. Run **Attribution.cmd** for an interactive lookup, or open PowerShell here:

```powershell
.\Attribution.cmd --help
.\Attribution.cmd history
```

Setup uses the bundled wheels without PyPI access. Live attribution needs network
access to the public registry and DNS services. The module does not scan the
reported hosts.

## Make and review a lookup

Use the interactive launcher to provide the intended root domain and candidate IPs.
The caller supplies the registrable root domain; the component does not derive it
by removing hostname labels. Keep reported hostnames when available.

The [command reference](REFERENCE.md#command-line) covers individual checks,
batches, exports, offline cache use, return codes, and time limits. The
[Python API](REFERENCE.md#python-api) covers integration and resource ownership.

Exports retain the candidate list, decision, attempts, response evidence, and file
hashes. Open `evidence.html` to review a saved export. Hashes detect changed bytes;
they are not a digital signature or independent proof of the underlying finding.

## Develop and verify

From this component directory, with Python available:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use synthetic responses. [Component validation history](VALIDATION.md)
records earlier version checks; consult [application validation](../../../../docs/history/validation/VALIDATION_0120.md)
for current Eclipse results and remaining Windows acceptance.

## Reference

| Topic | Read |
| --- | --- |
| Matching, retrieval, storage, exports, provider interfaces | [Technical reference](REFERENCE.md) |
| Bundled package inventory | [Dependencies](DEPENDENCIES.md) |
| Application contributor workflow | [Development](../../../../docs/DEVELOPMENT.md) |
| Documentation navigation | [Documentation index](../../docs/README.md) |
