"""Aegis: shared input and antimalware boundaries, using only the standard library."""

from .antimalware import (
    scan_buffer,
    scan_text,
    scan_contact_text,
    validate_scan_receipt,
    scan_unavailable,
)
from .errors import ContentScanError, InputValidationError, SecurityExecutionError
from .execution import SecurityExecutor, bounded_security_call
from .json import strict_json_decoder, strict_json_loads
from .text import parse_media_type, decode_bounded_text

__all__ = [
    "scan_buffer",
    "scan_text",
    "scan_contact_text",
    "validate_scan_receipt",
    "scan_unavailable",
    "ContentScanError",
    "InputValidationError",
    "SecurityExecutionError",
    "SecurityExecutor",
    "bounded_security_call",
    "strict_json_decoder",
    "strict_json_loads",
    "parse_media_type",
    "decode_bounded_text",
]
