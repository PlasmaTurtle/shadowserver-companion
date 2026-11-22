# Investigations changelog

## Unreleased

- Retired the open-case KEV query used solely by Library’s automatic comparison.
- Updated the presentation of newly selected Library explanations to use factual descriptions of the evidence.

## 0.12.1

- Select the new Library condition explanations using retained report identity, tags and qualifying fields. Render configuration and exposure guidance with its own wording and preserve previously selected editions.
- Expose a compact read of known-exploitation evidence retained by open notifications for Library's automatic comparison.

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
