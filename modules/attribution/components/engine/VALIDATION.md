# Attribution Module 0.2.4 validation

> **Historical record.** This component record covers earlier versions. See [application validation](../../../../docs/history/validation/VALIDATION_0120.md) for candidate evidence; the component version is recorded in [pyproject.toml](pyproject.toml).

Validated on 2026-11-11 using Python 3.14.10 on Linux.

- All 139 standalone attribution tests passed after extracting the shared bounded Google Public DNS query path.
- `GooglePublicDnsProvider.resolve_addresses` captures A and AAAA results without requiring an IP candidate or asserting attribution. It retains the validated CNAME chain, original response bytes, source URL, retrieval time, and SHA-256.
- Thirteen application integration tests additionally cover PSL root derivation, background execution, TTL/cooldown reuse, independent entities sharing a root cache, omitted nonpublic addresses, failed-refresh retention, malformed responses, corrupt optional summaries, response integrity, and unchanged entity/report records.
- The Windows locks and both wheel inventories contain the same rebuilt 0.2.4 artifact. `tools/check_dependencies.py` checks every bundled Python source byte against the wheel.
- Actual-browser synthetic-provider acceptance passed at desktop and mobile widths, including automatic initial lookup, cache reuse after reopening, and manual refresh.

Physical Windows execution and a live candidate-domain DNS call were not performed for this component update. Google Public DNS is identified as a public recursive resolver; root DNS supplements do not establish ownership or historical exposure.

## Previous 0.2.3 validation

Validated on 2026-11-08 using Python 3.14.9 on Linux.

- 139 standalone automated tests passed, including 29 new mocked Google Public DNS tests. All network fixtures run in process; no live candidate DNS lookups were performed.
- Exact response bytes, SHA-256, HTTPS query URL, JSON Pointer, export integrity, original cache retrieval timestamp, and legacy workstation evidence preservation are checked.
- Tests reject mismatched questions, unrelated address answers, conflicting/looped CNAMEs, wrong address families, truncated responses, disabled DNSSEC validation, duplicate JSON keys, oversized responses, HTTP redirects/errors, and DNS service failures.
- Positive cache TTLs, forward-confirmed PTR boundaries, rate-limit cooldowns, active-request cancellation and the total operation deadline are verified.
- The 0.2.3 wheel and both Windows locks/manifests are rebuilt together; source-to-wheel alignment is verified by `tools/check_dependencies.py`.

Windows execution and a live Google Public DNS call remain unverified in this update. The provider is a named public recursive resolver, not an authoritative server for each reported domain. Saved prior workstation evidence is retained with its original provenance.

## Earlier 0.2.1 migration validation

Validated on 2026-11-06 using Python 3.12 on Linux.

- 111 automated tests passed, including the existing RDAP/DNS/word-review/evidence tests and 13 new database/history checks.
- Migration from schema 1 to schema 2 preserves raw response bytes, response metadata, full result JSON and IDs. Tests cover backups, idempotent reopening, malformed legacy records, rollback, and future-version rejection.
- Result columns cannot disagree with saved JSON. Filtered history and CLI selection use the new metadata; query plans use the domain/status indexes.
- An actual earlier evidence database upgraded with all 36 captured responses and 24 complete results unchanged.
- The rebuilt wheel is installed and exercised offline in a clean environment. Bundled wheel hashes are verified.

The result JSON remains schema version 2. Physical Windows execution and workstation DNS/proxy configuration remain unverified. Synthetic network tests and cached-response migration checks do not establish fresh attribution for any business.

