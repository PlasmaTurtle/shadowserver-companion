"""Filesystem capabilities used by synthetic security fixtures."""

import sys

import pytest


def create_test_symlink(link, target, *, target_is_directory=False):
    """Skip only when Windows cannot create the fixture without added privileges."""
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as error:
        if sys.platform == "win32" and getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows host cannot create test symlinks (WinError 1314)")
        raise
