# UI changelog

## Unreleased

## 0.12.1

- Initial appearance persistence sends only the theme, so incomplete or legacy
  profile values do not prevent startup from saving the preference.

## 0.12.0

- Keep keyboard focus on a command-palette result while delayed search results
  arrive. Reopening the palette immediately after closing it also preserves the
  new query. [ISS047](ISSUES.md#iss047-command-palette-reopen-lifecycle)
- Let Reload app restore the existing session and reopen the workspace after
  a connection failure. The error screen links to the local server health
  check and prompts users to check an interrupted write before repeating it.
  [ISS050](ISSUES.md#iss050-recovering-the-shell-after-a-lost-connection)
