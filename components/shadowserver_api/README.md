# Shadowserver Reports integration

Acquire subscribed Shadowserver reports with their original bytes and a separate
record of when and how each file was retrieved.

Eclipse vendors the client in [workbench/shadowserver_reports](../../workbench/shadowserver_reports).
This directory keeps integration provenance, local patches, and earlier component
records. It is not a separately installable SDK distribution. This is an
independent integration, not an official Shadowserver SDK.

## Use it in Eclipse

Configure your key and secret through the application's API connections, then use
**Data → API** to discover the reports available to your account and select an
import. Follow the [user guide](../../docs/USER_GUIDE.md) for setup and scheduling.
The service determines access from the account's subscriptions; application
configuration cannot grant additional entitlements.

The acquisition client preserves report files and receipts. Eclipse's surrounding
application handles intake, qualification, scheduling, and analyst review.
Successful acquisition does not certify a vulnerability or establish attribution.

## Try the source demo

Set up the repository's Python environment using [DEVELOPMENT.md](../../DEVELOPMENT.md).
From the repository root, with that environment active:

```text
python -m workbench.shadowserver_reports --help
python -m workbench.shadowserver_reports demo --output build/api-demo
```

The demo uses synthetic reports, makes no network requests, and reads no
credentials. Use a new output directory to reproduce the original new/reused-file
counts. The old standalone wheel commands belong to the
[historical reference](REFERENCE.md); that wheel is not included in this directory.

## Integration status

The vendored client identifies itself as **0.1.2**. The
[source manifest](source-manifest.json) records the exact integrated files and
local changes, including CSV validation independent of MIME labels and bounded
CSV prefix validation. These changes are local integration revisions, not an
upstream release.

The earlier 0.9.89 application integration recorded live authentication,
discovery, a complete CSV download, and queued intake handoff. That dated evidence
does not establish current-version or native Windows acceptance. Consult
[application validation](../../VALIDATION.md) and
[Windows acceptance](../../HOME_VALIDATION.md) for current release requirements.
The standalone [live acceptance checklist](LIVE_ACCEPTANCE.md) is historical and
must not be treated as an up-to-date statement that Eclipse lacks API integration.

## Develop and verify

With the repository development environment active, run the component fixture
suite from the repository root:

```text
python -m pytest -q tests/shadowserver_api_module
```

Keep source changes, patch records, and `source-manifest.json` synchronized. Preserve
the distinction between signed API requests and unsigned report downloads; never
serialize credentials or usable download capabilities into logs or receipts.

## Reference

| Topic | Read |
| --- | --- |
| CLI contracts, synchronization, receipts, queries, and protocol sources | [Standalone reference and integration history](REFERENCE.md) |
| Vendored source hashes and patch provenance | [Source manifest](source-manifest.json) |
| Original standalone execution record | [Validation record](VALIDATION.json) |
| Application data handling | [Data management](../../docs/DATA_MANAGEMENT.md) |
| Repository documentation | [Documentation index](../../docs/README.md) |
