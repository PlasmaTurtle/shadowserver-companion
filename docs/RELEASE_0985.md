# 0.9.85 — Orbital cockpit and website evidence

This updates the existing **Dark Matter** installation. Keep **Retain existing
data** selected. It remains an unsigned, unstable comparison release. No GitHub
upload is part of this delivery.

## Visible changes

- The approved eclipse now drifts through a 144-second pan, shallow zoom and small
  roll, with registered corona light and flowing data paths. The supplied artwork
  is 2048 × 1152; it is not represented as a native 4K asset.
- Dark frosted backing separates information from the exposed scene. Dense rows
  remain more opaque. The palette and status colors stay consistent; generated
  recipient documents keep their existing formatting.
- **Drift on/off** remembers the preference. Reduced motion, hidden tabs, light
  mode and the Observatory suspend ambient animation. One outer frost layer per
  view avoids repeatedly blurring nested tables and panels.
- In a notification's **Attribution** section, choose a reported hostname and use
  **Capture website**. The result is a 1440 × 900 viewport. Existing screenshot
  attachment remains available in a collapsed disclosure.
- Capture runs separately from save/freeze/render. A completed image cannot alter
  a section frozen during acquisition. Unsaved narrative is preserved when the
  new evidence arrives.

## Capture evidence

A fresh installed Microsoft Edge or Google Chrome session renders the public
page. It follows public redirects; no normal browser profile, credentials or
third-party screenshot service is used. Port-80-only observations start with
HTTP; other reported hostnames start with HTTPS. Certificate failures do not
cause a silent HTTP downgrade.

The original PNG bytes, requested/final URL, UTC timestamp, title, viewport,
HTTP status, acquisition outcome and SHA-256 are retained. Exact originals use a
safe `.original.bin` storage/transport name; the thumbnail is a separate PNG.
Selected images and their provenance travel through the existing notification
snapshot and readable evidence package. Captured URL/time are read-only;
caption and inclusion remain editable while their section is open.

An ordinary captured viewport is included by default. Partial, login, challenge
and failed-page images retain their status and begin excluded. This is a visual
reference, not an automated assertion of business ownership. If a browser is
unavailable or workstation policy blocks automation, the job reports that result
and manual attachment remains available.

## Security and stability

See [the audit](AUDIT_0985.md) and [executed validation](../VALIDATION.md).
The pass adds input byte ceilings before parsing, recorded preview integrity
checks, off-event-loop image decoding, bounded capture processes and complete
worker cleanup even on abnormal lifespan exit. It keeps all existing local
catalog, CVSS/EPSS/KEV, root-DNS, source-adoption and report protections.

The CPython 3.14.10/OpenSSL FIPS configuration affected by CVE-2026-119170 is
rejected at startup. FIPS is not disabled. An approved corrected runtime is
required for that configuration.

## Workstation acceptance still required

The build host cannot establish native Windows installation/upgrade behavior,
enterprise Edge automation policy, Windows process-job behavior, or GPU frame
cost. Browser protocol tests use a synthetic peer; scene lifecycle tests use an
offline DOM model. Neither is reported as a real browser capture or GPU profile.
Use the demo first to judge appearance and capture a suitable public hostname
before relying on the new capture workflow. Historical report bytes remain intact.
