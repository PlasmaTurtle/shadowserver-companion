"""Find reported CVE identifiers without importing providers or persistence."""

import re

CVE = re.compile(r"(?<![a-z0-9-])CVE-\d{4}-\d{4,}(?![a-z0-9-])", re.I)


def identifiers(tags):
    return sorted({m.upper() for tag in tags for m in CVE.findall(str(tag))})
