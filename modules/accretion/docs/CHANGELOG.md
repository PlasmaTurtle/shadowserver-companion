# Accretion (Data) changelog

## Unreleased

## 0.12.1

- Targeted intake retains Settings' reviewed agency authority alongside its
  reason. A changed authority creates a distinct import decision without rewriting
  prior imports. [Settings validation](../../settings/docs/ISSUES.md#iss060-validated-profiles-and-agency-authority)

## 0.12.0

- Workbook, manual API and scheduled API imports now share qualification rules. Reimporting a report reuses its source identity. Data shows source-row counts separately from domain groups qualified, evaluated and published. [Intake workflow verification](../../../docs/history/validation/intake-review-2026-11-22.md#workflow-and-upgrade-evidence)
- Qualify checks the final page after redirects, rejects parked pages and unidentified login screens, and reuses recent verified captures. Evaluate scores outstanding findings and gives qualified government sites the existing agency preference.
- Associate records outreach holds and external referrals with the matched identifier and reference. An exact-host referral excludes that host while preserving eligible sibling findings and their evidence. [Associate](PIPELINE.md#associate)
- Dark Matter now keeps original source rows, including malformed and out-of-region rows, with a separate record of their intake decisions.
