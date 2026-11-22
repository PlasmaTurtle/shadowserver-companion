# Investigations changelog

## Unreleased

## 0.12.0

- Count a case once on its first recorded delivery or acknowledgement. Leads,
  Entities and Associate can read the same count and last delivery date after
  a revision or case closure. [Notification history](README.md#completed-notifications)
- Attach the screenshot approved for the observations that enter a case. If a
  referral excludes a sibling hostname, the surviving findings keep their own
  screenshot through certification and recipient export.
- Recover the case and lead completion states together after an interrupted
  certification. Recovery preserves the original package bytes and leaves
  later unassigned findings available for review. [ISS019](ISSUES.md#iss019-interrupted-certification-state)
