"""Bounded native-browser failure descriptions without URLs or page content."""

import re
import socket
import ssl

_GENERIC = "Website capture could not be completed"
_NATIVE_MESSAGES = {
    "Website capture cancelled",
    "Website capture timed out",
    "Website navigation timed out",
    "Website navigation did not finish before its timeout",
    "Website viewport was still loading at the capture timeout",
    "Some visible images or video could not be displayed",
    "Website fonts did not finish loading",
    "Navigation timed out",
    "No rendered page was available",
    "No loaded page was available",
    "Capture browser did not become ready in time",
    "Capture browser could not start",
    "Website capture needs Microsoft Edge or Google Chrome installed. Manual attachment is still available.",
    "Capture browser disconnected",
    "Capture browser closed",
    "Browser navigation command failed",
    "Browser resource request failed",
    "Browser handshake failed",
    "Invalid browser handshake",
    "Invalid capture browser endpoint",
    "Invalid local capture endpoint",
    "Invalid browser frame",
    "Invalid browser message",
    "Invalid fragmented browser message",
    "Could not create an isolated capture process job",
    "Workstation policy prevented capture process isolation",
    "DNS resolution failed",
    "TLS certificate validation failed",
    "TLS negotiation failed",
    "Network request timed out",
    "TCP connection refused",
    "Network connection blocked by workstation policy",
}


def _message(text, depth=0):
    if text in _NATIVE_MESSAGES:
        return text
    if re.fullmatch(
        r"(?:Website (?:resource )?returned HTTP [45][0-9]{2}|net::ERR_[A-Z0-9_]{1,100})", text
    ):
        return text
    if re.fullmatch(r"Capture browser could not complete [A-Za-z]{1,32}\.[A-Za-z]{1,64}", text):
        return text
    if depth >= 2:
        return None
    for prefix in (
        "Website could not be loaded: ",
        "Capture browser startup failed: ",
        "Capture browser page setup failed: ",
    ):
        if text.startswith(prefix):
            return prefix + (_message(text[len(prefix) :], depth + 1) or _GENERIC)
    navigation = re.fullmatch(
        r"Website navigation failed: (net::ERR_[A-Z0-9_]{1,100}|Browser navigation command failed)(?:; (.*))?",
        text,
    )
    if navigation:
        detail = navigation.group(2)
        return (
            "Website navigation failed: "
            + navigation.group(1)
            + ("; " + (_message(detail, depth + 1) or _GENERIC) if detail else "")
        )
    return None


def network_error(error):
    message = _message(str(error))
    if message:
        return message
    if isinstance(error, socket.gaierror):
        return "DNS resolution failed"
    if isinstance(error, ssl.SSLCertVerificationError):
        return "TLS certificate validation failed"
    if isinstance(error, ssl.SSLError):
        return "TLS negotiation failed"
    if isinstance(error, TimeoutError):
        return "Network request timed out"
    if isinstance(error, ConnectionRefusedError):
        return "TCP connection refused"
    if isinstance(error, PermissionError):
        return "Network connection blocked by workstation policy"
    if isinstance(error, OSError):
        return "Network connection failed" + (f" (OS {error.errno})" if error.errno else "")
    return _GENERIC


def navigation_error(response, document_error=""):
    code = re.search(
        r"\bnet::ERR_[A-Z0-9_]{1,100}\b", str(response.get("result", {}).get("errorText", ""))
    )
    details = [code.group(0)] if code else ["Browser navigation command failed"]
    if document_error:
        details.append(_message(document_error) or _GENERIC)
    return "Website navigation failed: " + "; ".join(details)
