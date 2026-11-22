# Attribution changelog

## Unreleased

## 0.12.0

- Qualification can reuse verified registration evidence across related observations. Each covered observation retains its hostname, IP address and original proof reference. Reuse of a manual decision requires the recorded analyst approval for the current entity. [Qualification interface](README.md#qualification-interface)
- Added a command to create an empty SQLite database matching North Carolina’s published 18-table business-registration layout. The schema keeps names, contact roles and office addresses distinct. Import and matching against weekly records still depend on an authorized extract. [Registry import status](ISSUES.md#iss056-north-carolina-business-registration-import)
