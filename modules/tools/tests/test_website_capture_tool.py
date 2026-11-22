"""Reusable website-capture URL, browser-default and outcome contracts."""

import threading
import time
from unittest.mock import Mock, call

import pytest

from modules.tools.components.website_capture import WebsiteLoadError, navigation, web_url
from modules.tools.components.website_capture.browser import browser_arguments, classify_page


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


def test_top_level_download_tries_next_candidate_without_rendering_a_file():
    client = Mock()
    client.call.return_value = {"isDownload": True, "errorText": "net::ERR_ABORTED"}
    metadata = {"attempts": [], "attempted_urls": []}
    with pytest.raises(WebsiteLoadError, match="Website offered a file download"):
        navigation.load_page(
            "https://localhost/file",
            open_page=lambda: client,
            deadline=time.monotonic() + 60,
            cancel_event=threading.Event(),
            metadata=metadata,
            classify=classify_page,
        )
    assert client.call.call_args_list == [
        call("Page.navigate", {"url": "https://localhost/file"}),
        call("Page.navigate", {"url": "http://localhost/file"}),
    ]
    assert all(attempt["outcome"] == "load_failed" for attempt in metadata["attempts"])


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


def test_browser_preserves_sandbox_and_has_no_user_profile():
    args = browser_arguments("msedge.exe", "/temporary/profile")
    assert "--user-data-dir=/temporary/profile" in args
    assert not any(
        arg.startswith(
            ("--proxy", "--host-resolver", "--disable-gpu", "--disable-quic", "--disable-features")
        )
        for arg in args
    )
    assert "--remote-debugging-address=127.0.0.1" in args
    assert not {
        "--no-sandbox",
        "--disable-web-security",
        "--ignore-certificate-errors",
        "--remote-allow-origins=*",
    } & set(args)


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
