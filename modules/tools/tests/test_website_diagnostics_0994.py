"""Bounded native-browser failure descriptions without credential disclosure."""

import socket
import ssl
import pytest

from modules.tools.components.website_capture.diagnostics import (
    network_error,
    navigation_error,
)


def test_safe_diagnostics_do_not_disclose_exception_urls():
    secret = "https://user:secret@example.com/?token=private"
    assert network_error(socket.gaierror(secret)) == "DNS resolution failed"
    assert (
        network_error(ssl.SSLCertVerificationError(secret)) == "TLS certificate validation failed"
    )
    assert network_error(TimeoutError(secret)) == "Network request timed out"
    assert "secret" not in network_error(ValueError(secret))
    message = navigation_error(
        {"result": {"errorText": "net::ERR_BLOCKED_BY_CLIENT " + secret}}, "DNS resolution failed"
    )
    assert "net::ERR_BLOCKED_BY_CLIENT" in message and "DNS resolution failed" in message
    assert "secret" not in message
    assert network_error(ValueError(message)) == message
    missing_browser = "Website capture needs Microsoft Edge or Google Chrome installed. Manual attachment is still available."
    assert network_error(ValueError(missing_browser)) == missing_browser


@pytest.mark.parametrize(
    "message",
    [
        "Website navigation timed out",
        "Website navigation did not finish before its timeout",
        "Website viewport was still loading at the capture timeout",
        "net::ERR_NAME_NOT_RESOLVED",
        "Website resource returned HTTP 404",
        "Website capture cancelled",
        "Capture browser could not start",
        "Capture browser could not complete Page.navigate",
        "Website could not be loaded: Website navigation timed out",
    ],
)
def test_native_messages_remain_actionable(message):
    assert network_error(ValueError(message)) == message


def test_nested_navigation_failure_cannot_expose_credentials():
    secret = "https://user:password@example.com/?token=secret"
    nested = "Website could not be loaded: " + secret
    assert "password" not in network_error(ValueError(nested))
    message = navigation_error({"result": {"errorText": "net::ERR_FAILED"}}, secret)
    assert "ERR_FAILED" in message and "secret" not in message
