"""Product outreach joins keep CVE scope, source identity and case evidence intact."""

from copy import deepcopy
import socket
from types import SimpleNamespace

import pytest
import requests

from modules.library.components.catalog_outreach import (
    CatalogOutreach,
    decorate_observations,
    decorate_product_selection,
    matches_scope,
    reported_cves,
)
from modules.library.components.cve_catalog import Catalog
from modules.observatory.components.eclipse import Eclipse
from modules.library.components.cve_catalog.risk import RiskStore
from modules.observatory.components.observatory_intelligence import project
from modules.observatory.tests.support.observations import observation, snapshot
from tests.support.workbench import app, client, import_rows, observations, ready

from modules.library.tests.support.catalog_outreach import (
    CRITICAL_KEV,
    HIGH_KEV,
    OTHER_CRITICAL_KEV,
    PRODUCT,
    reported_rows,
    seed_catalog,
)


def make_outreach(root, catalog, rows):
    decorate_observations(root, rows)
    return CatalogOutreach(
        SimpleNamespace(snapshot=lambda: snapshot(deepcopy(rows))), SimpleNamespace(catalog=catalog)
    )


def test_critical_kev_requires_one_same_reported_cve(tmp_path):
    seed_catalog(tmp_path / "working", tmp_path)
    rows = decorate_observations(tmp_path / "working", reported_rows())
    split = next(row for row in rows if row["id"] == "split-risk")
    assert split["kev"] is True and split["catalog_severity"] == "CRITICAL"
    assert matches_scope(split, "critical") and matches_scope(split, "kev")
    assert not matches_scope(split, "critical_kev")
    result = project(snapshot(rows), intelligence="critical_kev")
    actual = {value for node in result["graph"]["nodes"] for value in node["observation_ids"]}
    assert "first" in actual and "wrong-product" in actual
    assert "split-risk" not in actual and "rejected" not in actual


def test_product_scope_cannot_borrow_priority_from_another_product(tmp_path):
    root = tmp_path / "working"
    seed_catalog(root, tmp_path)
    rows = decorate_observations(root, reported_rows())
    data = decorate_product_selection(root, snapshot(rows), PRODUCT)
    unrelated = next(row for row in rows if row["id"] == "wrong-product")
    assert matches_scope(unrelated, "critical_kev")
    assert not matches_scope(unrelated, "critical_kev", product=True)
    result = project(data, product_id=PRODUCT, intelligence="critical_kev")
    assert result["counts"]["selected_rows"] == 3
    assert result["counts"]["entities"] == 2
    assert all("wrong-product" not in node["observation_ids"] for node in result["graph"]["nodes"])


def test_product_ransomware_scope_requires_a_matching_product_cve(tmp_path):
    root = tmp_path / "working"
    seed_catalog(root, tmp_path)
    rows = decorate_observations(root, reported_rows())
    data = decorate_product_selection(root, snapshot(rows), PRODUCT)
    for row in rows:
        for finding in row["catalog_findings"]:
            if finding["id"] in {OTHER_CRITICAL_KEV, CRITICAL_KEV}:
                finding["risk"]["kev"]["entry"]["knownRansomwareCampaignUse"] = "Known"
                row["ransomware_known"] = True
    assert project(data, intelligence="ransomware")["counts"]["selected_rows"] == 4
    result = project(data, product_id=PRODUCT, intelligence="ransomware")
    assert result["counts"]["selected_rows"] == 3
    assert all("wrong-product" not in node["observation_ids"] for node in result["graph"]["nodes"])


def test_exact_identifier_join_and_pagination_keep_full_distinct_counts(tmp_path):
    root = tmp_path / "working"
    catalog = seed_catalog(root, tmp_path)
    rows = reported_rows()
    outreach = make_outreach(root, catalog, rows)
    first = outreach.observations(cve_id=CRITICAL_KEV, limit=1)
    second = outreach.observations(cve_id=CRITICAL_KEV, limit=1, offset=1)
    assert first["total"] == second["total"] == 3
    assert first["counts"] == second["counts"]
    assert first["counts"]["endpoints"] == 2
    assert first["counts"]["entities"] == 2
    assert first["counts"]["pending_entities"] == 1
    assert first["counts"]["notified_entities"] == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert first["items"][0]["matched_cves"] == [CRITICAL_KEV]
    assert first["items"][0]["entity_url"] == "#entity/entity-beta"
    assert all(row["id"] != "prefix" for row in outreach.observations(cve_id=CRITICAL_KEV)["items"])
    assert reported_cves(
        {"tag": CRITICAL_KEV.lower() + ";" + CRITICAL_KEV, "reported_cves": [HIGH_KEV]}
    ) == sorted([HIGH_KEV, CRITICAL_KEV])


def test_product_name_candidates_are_separate_from_reported_cves(tmp_path):
    root = tmp_path / "working"
    catalog = seed_catalog(root, tmp_path)
    outreach = make_outreach(root, catalog, reported_rows())
    result = outreach.observations(product_id=PRODUCT, scope="critical_kev")
    reported = [row for row in result["items"] if row["finding_kind"] == "reported"]
    assert {row["id"] for row in reported} == {"first", "return", "other-entity"}
    candidate = next(row for row in result["items"] if row["id"] == "product-only")
    assert candidate["finding_kind"] == "product_candidate"
    assert candidate["matched_cves"] == []
    assert "unresolved" in candidate["basis"]
    assert result["counts"]["reported"] == 3
    assert result["counts"]["product_candidates"] == len(result["items"]) - 3


def test_cve_scope_cannot_borrow_priority_from_another_reported_cve(tmp_path):
    root = tmp_path / "working"
    catalog = seed_catalog(root, tmp_path)
    outreach = make_outreach(root, catalog, reported_rows())
    assert outreach.observations(cve_id=HIGH_KEV, scope="critical")["total"] == 0
    assert outreach.observations(cve_id=HIGH_KEV, scope="critical_kev")["total"] == 0
    result = outreach.observations(cve_id=HIGH_KEV, scope="kev")
    assert {row["id"] for row in result["items"]} == {"split-risk", "wrong-product"}
    assert all(row["matched_cves"] == [HIGH_KEV] for row in result["items"])


def test_observatory_cve_identifier_is_exact_and_case_insensitive():
    result = project(snapshot(reported_rows()), cve=CRITICAL_KEV.lower())
    assert result["counts"]["selected_rows"] == 3
    assert all("prefix" not in node["observation_ids"] for node in result["graph"]["nodes"])


def test_missing_or_corrupt_reference_store_preserves_core_observations(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Local observation join attempted network or DNS")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    root = tmp_path / "working"
    rows = reported_rows()
    original = deepcopy(rows)
    decorate_observations(root, rows)
    assert not Catalog(root).db.exists()
    assert not RiskStore(root).db.exists()
    assert len(rows) == len(original)
    assert all(row["tag"] == prior["tag"] for row, prior in zip(rows, original))
    assert all(row["catalog_findings"] == [] for row in rows)
    catalog = Catalog(root)
    catalog.folder.mkdir(parents=True)
    catalog.db.write_bytes(b"unavailable reference catalog")
    RiskStore(root).db.write_bytes(b"unavailable risk catalog")
    assert len(decorate_observations(root, rows)) == len(original)
    assert project(snapshot(rows))["counts"]["selected_rows"] == len(rows)


def test_readonly_outreach_api_preserves_casework_and_evidence(client, app, tmp_path, monkeypatch):
    import_rows(client, app, [{**observations()[0], "ip": "8.8.8.8"}])
    entity = client.get("/api/leads").json()[0]["id"]
    frozen = ready(client, entity)
    catalog = seed_catalog(app.state.store.root, tmp_path)
    import_rows(
        client,
        app,
        [
            {
                **observations()[0],
                "ip": "8.8.8.8",
                "tag": CRITICAL_KEV,
                "product": "Mail Gateway",
                "version": "1.0",
            },
            {
                **observations()[0],
                "ip": "8.8.8.8",
                "tag": CRITICAL_KEV,
                "product": "Mail Gateway",
                "version": "1.0",
                "timestamp": "2026-11-05 01:02:03",
            },
        ],
        name="catalog-observations.csv",
    )
    before = app.state.store.one("SELECT * FROM cases WHERE id=?", (frozen["case_id"],))
    reviews = app.state.store.all(
        "SELECT * FROM section_validations WHERE case_id=?", (frozen["case_id"],)
    )
    evidence = {
        str(path): path.read_bytes()
        for path in (app.state.store.root / "evidence").rglob("*")
        if path.is_file()
    }
    assert evidence, "Fixture must contain preserved screenshot evidence"
    calls = list(app.state.fake.calls)

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only catalog outreach performed acquisition")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    urls = [
        "/api/eclipse",
        "/api/eclipse?product_id=" + PRODUCT,
        "/api/eclipse/intelligence?product_id=" + PRODUCT + "&intelligence=critical_kev",
        "/api/cve-catalog/products?scope=critical_kev",
        "/api/cve-catalog/products/" + PRODUCT,
        "/api/cve-catalog/products/" + PRODUCT + "/observations?scope=critical_kev&limit=1",
        "/api/cve-catalog/records/" + CRITICAL_KEV + "/observations?limit=1",
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, (url, response.text)
    assert catalog.product_cve_ids(PRODUCT, scope="critical_kev") == {CRITICAL_KEV}
    assert app.state.store.one("SELECT * FROM cases WHERE id=?", (frozen["case_id"],)) == before
    assert (
        app.state.store.all(
            "SELECT * FROM section_validations WHERE case_id=?", (frozen["case_id"],)
        )
        == reviews
    )
    assert {
        str(path): path.read_bytes()
        for path in (app.state.store.root / "evidence").rglob("*")
        if path.is_file()
    } == evidence
    assert app.state.fake.calls == calls


@pytest.mark.parametrize(
    "url",
    [
        "/api/eclipse?product_id=not-a-product",
        "/api/eclipse/intelligence?product_id=not-a-product",
        "/api/cve-catalog/products/not-a-product/observations",
        "/api/cve-catalog/records/not-a-cve/observations",
        "/api/cve-catalog/products/" + PRODUCT + "/observations?scope=invalid",
        "/api/cve-catalog/records/" + CRITICAL_KEV + "/observations?limit=0",
    ],
)
def test_invalid_outreach_selections_rejected_before_snapshot(client, app, monkeypatch, url):
    monkeypatch.setattr(
        Eclipse,
        "snapshot",
        lambda self, **_: pytest.fail("Invalid selection read workspace observations"),
    )
    response = client.get(url)
    assert response.status_code in (400, 422), response.text


def test_explicit_normalized_product_pairs_match_without_inventing_cves(tmp_path):
    catalog = seed_catalog(tmp_path / "workspace", tmp_path)
    row = observation(
        "multiple-products",
        tag="eol-http",
        product="nginx; mail_gateway",
        product_versions=[
            {"product": "nginx", "version": "1.20"},
            {"product": "mail_gateway", "version": "1.0"},
        ],
    )
    original = {"observations": [row]}
    selected = decorate_product_selection(tmp_path / "workspace", deepcopy(original), PRODUCT)
    assert selected["observations"][0]["catalog_product_id"] == PRODUCT
    assert selected["observations"][0]["catalog_product_cves"] == []
    outreach = CatalogOutreach(
        SimpleNamespace(snapshot=lambda: deepcopy(original)), SimpleNamespace(catalog=catalog)
    )
    result = outreach.observations(product_id=PRODUCT)
    assert result["total"] == 1
    assert result["items"][0]["finding_kind"] == "product_candidate"
    assert result["items"][0]["matched_cves"] == []
