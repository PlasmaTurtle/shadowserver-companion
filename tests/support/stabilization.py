"""Reusable synthetic stabilization fixtures and builders."""

import hashlib


def protected_state(store):
    tables = (
        "cases",
        "case_entries",
        "case_groups",
        "reports",
        "section_validations",
        "section_events",
        "contact_attempts",
        "case_closures",
    )
    return {
        "tables": {table: store.all(f"SELECT * FROM {table} ORDER BY rowid") for table in tables},
        "files": {
            file.relative_to(store.root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for directory in ("originals", "evidence", "reports", "closures")
            for file in (store.root / directory).rglob("*")
            if file.is_file()
        },
    }
