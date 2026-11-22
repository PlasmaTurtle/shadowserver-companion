"""Reusable synthetic finding explanation fixtures and builders."""


def item():
    return {
        "label": "eol-php",
        "detail": "PHP/5.6.29",
        "finding_type": "eol",
        "exposure_count": 2,
        "observation_scope": "website.example.com; 192.0.2.4 and 192.0.2.5",
        "technical_explanation": {
            "id": "eol-php",
            "revision": "fixture",
            "title": "PHP outside normal support",
            "body": "The reported PHP branch has reached the end of normal vendor support. A functioning website does not establish that its software is maintained.",
            "limitations": "A lifecycle finding is not a CVE or evidence that every later vulnerability affects this installation.",
            "review": "Confirm the installed branch and any separately maintained vendor support, then assess an upgrade or replacement with the service owner.",
            "source_citations": [3, 8],
        },
    }
