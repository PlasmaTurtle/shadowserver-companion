"""Bounded capture failure descriptions without URLs, credentials or page text."""

import re
import socket
import ssl

from ..aegis import ContentScanError


def network_error(error):
    if isinstance(error, ContentScanError):
        return (
            "Windows antimalware protection blocked website content"
            if error.code == "content_scan_blocked"
            else "Windows antimalware scanning was unavailable; website capture stopped"
        )
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
    text = str(error)
    allowed = (
        "Website address is not public; request blocked",
        "Website capture cancelled",
        "Website resource exceeded its size limit",
        "Website resource exceeded its decoded size limit or was incomplete",
        "Request blocked by capture limits",
        "Capture byte budget exceeded",
        "Unsupported website compression",
        "Invalid website response",
        "Invalid website headers",
        "Ambiguous website headers",
        "Only public HTTP or HTTPS websites can be captured",
        "Website capture uses standard HTTP and HTTPS ports",
    )
    return text if text in allowed else "Website response could not be processed"


def navigation_error(response, document_error=""):
    code = re.search(
        r"\bnet::ERR_[A-Z0-9_]+\b", str(response.get("result", {}).get("errorText", ""))
    )
    details = [code.group(0)] if code else ["Browser navigation command failed"]
    if document_error:
        details.append(document_error)
    return "Website navigation failed: " + "; ".join(details)
