"""Fail closed in the affected CPython/OpenSSL FIPS configuration.

CVE-2026-119170 affects 3.14.10 only when OpenSSL FIPS mode is enabled.
The bundled ordinary runtime is not a FIPS-validated distribution.
"""

import sys
import _hashlib


def validate_runtime():
    if sys.version_info[:3] == (3, 14, 10) and getattr(_hashlib, "get_fips_mode", lambda: 0)():
        raise RuntimeError(
            "This Python runtime cannot be used with OpenSSL FIPS mode (CVE-2026-119170). Use an application release with a corrected, approved runtime. FIPS mode has not been disabled."
        )
