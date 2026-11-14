"""Allow only the explicitly versioned 0.9.5 addressee correction in frozen copy."""

from pathlib import Path


def accepted_source_bytes():
    source = (Path(__file__).parents[1] / "workbench/approved_template.py").read_text()
    additions = {
        "ADDRESSEE_REVISION = 'addressee-2026-11-08-v2'\n": "",
        "ADDRESSEE = 'Principal Executive / IT Director'\nLEGACY_ADDRESSEE = 'Principle Executive / IT Director'": "ADDRESSEE = 'Principle Executive / IT Director'",
        "contact_name=ADDRESSEE if draft.get('addressee_revision') == ADDRESSEE_REVISION else LEGACY_ADDRESSEE,": "contact_name=ADDRESSEE,",
    }
    for addition, legacy in additions.items():
        assert source.count(addition) == 1
        source = source.replace(addition, legacy)
    return source.encode()
