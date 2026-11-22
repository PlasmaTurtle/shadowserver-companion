# Observatory changelog

## Unreleased

## 0.12.1

- Supplied Library with workspace counts for CVEs and product or service labels found in retained observations, including available archived source rows.

## 0.12.0

- Added nationwide city lookup and used the workspace's saved jurisdiction for
  map context. Entity locations retain the source used to place them.
- Count each imported row once when it appears in both a finding and the Dark
  Matter archive. Separate source rows still count independently even when they
  report the same IP address and CVE.
  [Observation counting](ISSUES.md#iss045-duplicate-canonical-and-archive-observations)
