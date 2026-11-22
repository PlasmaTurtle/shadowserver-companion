"""Cancellation and total time budgets for one catalog transfer, including retries."""

import math
import time


class CatalogCancelled(ValueError):
    pass


class CatalogDeadlineExceeded(ValueError):
    """A whole transfer exhausted its budget; retrying cannot renew that budget."""


def cancelled(event):
    if event is not None and event.is_set():
        raise CatalogCancelled("Catalog update cancelled")


def transfer_deadline(seconds):
    if not math.isfinite(seconds) or seconds <= 0:
        raise CatalogDeadlineExceeded("Catalog transfer time budget exhausted")
    return time.monotonic() + seconds


def remaining(deadline, cancel_event=None):
    cancelled(cancel_event)
    value = deadline - time.monotonic()
    if not math.isfinite(value) or value <= 0:
        raise CatalogDeadlineExceeded(
            "Catalog download exceeded its total time budget. Completed records are retained."
        )
    return value


def wait(seconds, *, cancel_event=None, deadline=None):
    cancelled(cancel_event)
    if deadline is not None:
        seconds = min(seconds, remaining(deadline, cancel_event))
    if cancel_event is None:
        time.sleep(seconds)
    else:
        cancel_event.wait(seconds)
    cancelled(cancel_event)
    if deadline is not None:
        remaining(deadline, cancel_event)
