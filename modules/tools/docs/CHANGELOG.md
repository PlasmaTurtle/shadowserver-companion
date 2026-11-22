# Tools changelog

## Unreleased

## 0.12.0

- Capture the reported hostname first, using the browser's native navigation
  for redirects, cookies, scripts and media. If the reported site fails to
  load, try its main site. Return the requested URL, final URL and fallback
  outcome with the image. [ISS020](ISSUES.md#iss020-reported-host-loading-and-redirects)
- Deny website downloads before opening a capture target. Return a reported
  attempt's time and browser outcome, including when a render is interrupted.
  [ISS055](ISSUES.md#iss055-website-capture-permitted-file-downloads)
- Give callers shared implementations for offline domain parsing, IP address
  comparison, HTTP Retry-After parsing and atomic file writes.
