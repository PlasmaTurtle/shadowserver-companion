"""Valid domains do not depend on suffix or absence of digits."""

import json

import pytest

from test_accretion_intake import Registry, report, row
from test_workbench import app, client
from workbench.intake import EntryValidator, UnvalidatedEntry
from workbench.intake_service import IntakeService
from workbench.store import Store


DOMAINS = (
    "example.org",
    "business.net",
    "agency.gov",
    "school.edu",
    "business.co.uk",
    "business123.com",
    "123business.org",
    "mail2.business123.net",
    "xn--bcher-kva.de",
    "example.xn--p1ai",
)


@pytest.mark.parametrize("hostname", DOMAINS)
def test_valid_domains_pass_even_when_legacy_flags_are_true(hostname):
    source = UnvalidatedEntry("report.csv", "CSV", 2, row(hostname=hostname))
    assert EntryValidator({"North Carolina"}).validate_entry(source)
    assert EntryValidator(
        {"North Carolina"}, com_only=True, exclude_numeric_roots=True
    ).validate_entry(source)


@pytest.mark.parametrize(
    "hostname",
    (
        "not a hostname",
        "-bad.org",
        "bad_.net",
        "localhost",
        "bad..com",
        "example.123",
        "example.notarealregistrysuffix",
        "example.xn--",
    ),
)
def test_hostname_syntax_and_public_suffix_checks_remain(hostname):
    source = UnvalidatedEntry("report.csv", "CSV", 2, row(hostname=hostname))
    assert EntryValidator({"North Carolina"}).rejection_reason(source) == "invalid_hostname"


def test_old_queued_policy_flags_do_not_filter_valid_records(tmp_path):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(store, lookup_factory=Registry)
    original = report([row(hostname=hostname, severity="critical") for hostname in DOMAINS])
    identifier = intake.enqueue("scan-http_vulnerable.csv", original)["id"]
    saved = store.one("SELECT config,path FROM imports WHERE id=?", (identifier,))
    old_config = json.loads(saved["config"])
    old_config.update(com_only=True, exclude_numeric_roots=True)
    with store.transaction() as db:
        db.execute("UPDATE imports SET config=? WHERE id=?", (json.dumps(old_config), identifier))
    intake.process(identifier)
    finished = store.one("SELECT * FROM imports WHERE id=?", (identifier,))
    assert finished["status"] == "done", finished["error"]
    assert finished["valid_rows"] == len(DOMAINS)
    assert json.loads(finished["rejected"]) == {}
    assert json.loads(finished["config"])["com_only"] is True
    assert store.path(saved["path"]).read_bytes() == original


def test_old_settings_neither_apply_nor_change_new_import_identity(tmp_path):
    store = Store(tmp_path / "workspace")
    intake = IntakeService(store, lookup_factory=Registry)
    original = report([row(hostname="business123.org", severity="critical")])
    first = intake.enqueue("scan-http_vulnerable.csv", original)
    for legacy_value in (True, False):
        settings = store.settings()
        settings.update(com_only=legacy_value, exclude_numeric_roots=legacy_value)
        with store.transaction() as db:
            db.execute("UPDATE settings SET value=? WHERE key='profile'", (json.dumps(settings),))
        assert "com_only" not in store.settings()
        assert "exclude_numeric_roots" not in store.settings()
        repeated = intake.enqueue("scan-http_vulnerable.csv", original)
        assert repeated["duplicate"] and repeated["id"] == first["id"]
    snapshot = json.loads(
        store.one("SELECT config FROM imports WHERE id=?", (first["id"],))["config"]
    )
    assert "com_only" not in snapshot and "exclude_numeric_roots" not in snapshot


def test_legacy_settings_payload_keys_are_accepted_but_ignored(client):
    response = client.put(
        "/api/settings",
        json={"regions": ["North Carolina"], "com_only": True, "exclude_numeric_roots": True},
    )
    assert response.status_code == 200
    assert "com_only" not in response.json()
    assert "exclude_numeric_roots" not in response.json()
