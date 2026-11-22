"""Caller-owned cancellation checks for shared synchronous rendering work."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_check: ContextVar[Callable[[], None] | None] = ContextVar("rendering_check", default=None)


def check_rendering() -> None:
    """Run the caller's checkpoint, preserving its exception and stop policy."""
    check = _check.get()
    if check is not None:
        check()


@contextmanager
def rendering_checks(check: Callable[[], None]) -> Iterator[None]:
    """Apply a checkpoint in this context and restore the previous one on exit.

    The caller owns deadlines, cancellation state and publication rules. Direct
    rendering outside a scope has no cancellation policy. Subprocess control
    remains with the launching caller; this scope does not cross process boundaries.
    """
    token = _check.set(check)
    try:
        yield
    finally:
        _check.reset(token)
