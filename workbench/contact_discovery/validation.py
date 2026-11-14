"""Contact-specific media policy over the shared external-text validation gate."""

from ..aegis.errors import InputValidationError
from ..aegis.text import decode_bounded_text
from .policy import DiscoveryError, MAX_PAGE_BYTES


def decode_response_text(body, content_type, *, security_source=False, partial=False):
    """Validate transient contact text before static extraction, never storage.

    Complete security.txt requires plain text; website discovery accepts HTML
    and XHTML. The engine separately rejects incomplete security.txt records.
    """
    permitted = {"text/plain"} if security_source else {"text/html", "application/xhtml+xml"}
    try:
        return decode_bounded_text(
            body,
            content_type,
            allowed_media=permitted,
            max_bytes=MAX_PAGE_BYTES,
            partial=partial,
        )
    except InputValidationError as error:
        raise DiscoveryError(error.code, str(error)) from None
