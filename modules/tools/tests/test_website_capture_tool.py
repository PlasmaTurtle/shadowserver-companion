"""Reusable website-capture URL, browser-default and outcome contracts."""

import pytest

from modules.tools.components.website_capture import browser, web_url
from modules.tools.components.website_capture.browser import classify_page


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://example.com:invalid/",
        "https:///missing-host",
        "https://example.com\\@localhost/",
        "https://example.com/\r\nHost:evil",
        "data:text/html,hello",
    ],
)
def test_capture_url_policy(url):
    with pytest.raises(ValueError):
        web_url(url)


def test_query_and_fragment_policy():
    assert (
        web_url("https://example.com/path?a=2&b=3#section")
        == "https://example.com/path?a=2&b=3#section"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8080/",
        "http://[::1]:8080/",
        "https://localhost/",
        "https://example.com:8881/",
    ],
)
def test_native_browser_urls_are_not_restricted_by_old_transport(url):
    assert web_url(url) == url


@pytest.mark.parametrize(
    "executable,channel",
    [
        ("C:/Program Files/Microsoft/Edge/Application/msedge.exe", "msedge"),
        ("C:/Program Files/Google/Chrome/Application/chrome.exe", "chrome"),
    ],
)
def test_installed_browsers_use_supported_playwright_channels(monkeypatch, executable, channel):
    monkeypatch.setattr(browser, "find_browser", lambda: executable)
    assert browser.browser_options() == {"channel": channel}


def test_explicit_browser_executable_is_an_opt_in_override():
    assert browser.browser_options("C:/fixture/chromium.exe") == {
        "executable_path": "C:/fixture/chromium.exe"
    }


@pytest.mark.parametrize(
    "info,code,loaded,document_failed,status",
    [
        ({"url": "https://example.com/", "text": "Example business"}, 200, True, False, "captured"),
        (
            {"url": "https://example.com/", "text": "Verify you are human"},
            200,
            True,
            False,
            "challenge",
        ),
        (
            {"url": "https://example.com/login", "text": "Sign in", "password": True},
            200,
            True,
            False,
            "login_required",
        ),
        ({"url": "https://example.com/", "text": "Example business"}, 200, False, False, "partial"),
        (
            {"url": "https://example.com/", "text": "Example business"},
            200,
            True,
            True,
            "load_failed",
        ),
        ({"url": "https://example.com/", "text": ""}, 200, True, False, "partial"),
        ({"url": "chrome-error://chromewebdata/", "text": ""}, None, False, False, "load_failed"),
        ({"url": "https://example.com/login", "text": ""}, 401, True, False, "partial"),
        ({"url": "https://example.com/login", "text": "Error"}, 500, True, False, "load_failed"),
        (
            {"url": "https://example.com/login", "text": "Sign in", "password": True},
            200,
            True,
            True,
            "load_failed",
        ),
    ],
)
def test_truthful_page_classification(info, code, loaded, document_failed, status):
    assert classify_page(info, code, loaded, document_failed) == status
