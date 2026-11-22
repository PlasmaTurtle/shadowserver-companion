# 0.12.1 Guided Setup verification

The November 22, 2026 Windows candidate is identified by the Git tag
`v0.12.1-rc.1`. This patch changes how Settings presents credentials that
are already available during onboarding. It uses the existing credential
stores, service APIs and workspace schema.

The focused Edge workflow opened setup with synthetic credential statuses,
showed completed cards when both keys were available and exercised manual setup
through a reload. It completed with no page errors or external requests. The
Settings DOM test also covered retaining a manual choice and saving one service
while keeping an unfinished entry for the other. The onboarding, software-update and release integration
selection passed 49 Python tests. The release checker, program map and bundled
What's New reader identified version 0.12.1 and its two changelog entries.

For the exact packaged bytes, use the installer and source digests in
`SHA256SUMS.txt` alongside the candidate assets. The earlier full regression
applies to [0.12.0](intake-review-2026-11-22.md).
[Windows acceptance](../../WINDOWS_ACCEPTANCE.md) and the
[launcher investigation](../../ISSUES.md#iss054-defender-quarantined-the-windows-launcher)
remain open.
