"""The browser can load module assets without exposing adjacent source files."""

import re
from urllib.parse import urljoin

import pytest

from tests.support.workbench import app, client


def test_shell_and_cross_module_imports_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assets = re.findall(r'(?:src|href)="(/modules/[^"?#]+)', page.text)
    assert "/modules/ui/static/main.js" in assets
    assert "/modules/observatory/static/eclipse.css" in assets
    for asset in assets:
        response = client.get(asset)
        assert response.status_code == 200, asset
        assert response.content, asset

    main = client.get("/modules/ui/static/main.js")
    assert "javascript" in main.headers["content-type"]
    assert "./app.js" in main.text
    composition_url = "/modules/ui/static/app.js"
    composition = client.get(composition_url)
    assert composition.status_code == 200
    imports = re.findall(r"from\s+['\"]([^'\"]+\.js)['\"]", composition.text)
    cross_module = [target for target in imports if target.startswith("../../")]
    assert cross_module
    for target in cross_module:
        asset = urljoin(composition_url, target)
        response = client.get(asset)
        assert response.status_code == 200, asset
        assert "javascript" in response.headers["content-type"], asset


@pytest.mark.parametrize(
    "path",
    [
        "/modules/workspace/components/api.py",
        "/modules/ui/__init__.py",
        "/modules/ui/tests/test_frontend_070.cjs",
        "/modules/attribution/components/engine/pyproject.toml",
        "/modules/ui/static/%2e%2e/components/unicode_fonts.py",
        "/modules/ui/static/..%2fcomponents/unicode_fonts.py",
        "/modules/ui/static/%2e%2e/%2e%2e/workspace/components/api.py",
    ],
)
def test_static_mounts_do_not_expose_source_or_allow_traversal(client, path):
    assert client.get(path).status_code == 404
