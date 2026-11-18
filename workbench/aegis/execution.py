"""Bounded daemon execution for native security providers.

A timed-out native call cannot safely be interrupted. It retains its occupied
slot until it really finishes, so repeated timeouts cannot accumulate workers.
There is no unbounded work queue and no fallback to calling inline.
"""

from concurrent.futures import Future, TimeoutError as FutureTimeout
import math
import queue
import threading
import time

from .errors import SecurityExecutionError


class SecurityExecutor:
    def __init__(self, *, capacity=2, max_timeout=3.0):
        if type(capacity) is not int or not 1 <= capacity <= 4:
            raise ValueError("Security execution capacity must be between one and four")
        if (
            isinstance(max_timeout, bool)
            or not isinstance(max_timeout, (int, float))
            or not math.isfinite(max_timeout)
            or max_timeout <= 0
        ):
            raise ValueError("Security execution timeout must be finite and positive")
        self.max_timeout = float(max_timeout)
        self._slots = threading.BoundedSemaphore(capacity)
        self._jobs = queue.Queue(maxsize=capacity)
        for index in range(capacity):
            threading.Thread(
                target=self._worker, name=f"security-native-{index}", daemon=True
            ).start()

    def _worker(self):
        while True:
            future, function = self._jobs.get()
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(function())
                    except BaseException as error:
                        future.set_exception(error)
            finally:
                # Release references to inspected content before waiting again.
                future = function = None
                self._slots.release()
                self._jobs.task_done()

    @staticmethod
    def _cancelled(cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            raise SecurityExecutionError("security_cancelled", "Security scanning was cancelled")

    def run(self, function, *, timeout=None, cancel_event=None):
        budget = self.max_timeout if timeout is None else timeout
        if (
            isinstance(budget, bool)
            or not isinstance(budget, (int, float))
            or not math.isfinite(budget)
            or budget <= 0
        ):
            raise SecurityExecutionError(
                "security_timeout", "Security scanning exceeded its time budget"
            )
        budget = min(float(budget), self.max_timeout)
        deadline = time.monotonic() + budget
        self._cancelled(cancel_event)
        while True:
            self._cancelled(cancel_event)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SecurityExecutionError(
                    "security_capacity", "Security scanning capacity is occupied"
                )
            if self._slots.acquire(timeout=min(remaining, 0.025)):
                break
        try:
            self._cancelled(cancel_event)
            if time.monotonic() >= deadline:
                raise SecurityExecutionError(
                    "security_timeout", "Security scanning exceeded its time budget"
                )
        except BaseException:
            self._slots.release()
            raise
        future = Future()
        try:
            self._jobs.put_nowait((future, function))
        except BaseException:
            self._slots.release()
            raise
        try:
            while True:
                self._cancelled(cancel_event)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SecurityExecutionError(
                        "security_timeout", "Security scanning exceeded its time budget"
                    )
                try:
                    result = future.result(timeout=min(remaining, 0.025))
                except FutureTimeout:
                    # A worker may itself raise TimeoutError. Do not keep
                    # waiting on a completed exceptional future in that case.
                    if future.done():
                        raise
                    continue
                self._cancelled(cancel_event)
                if time.monotonic() > deadline:
                    raise SecurityExecutionError(
                        "security_timeout", "Security scanning exceeded its time budget"
                    )
                return result
        finally:
            future.cancel()


_executor = None
_executor_lock = threading.Lock()


def bounded_security_call(function, *, timeout=None, cancel_event=None):
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = SecurityExecutor(capacity=2, max_timeout=3.0)
        executor = _executor
    return executor.run(function, timeout=timeout, cancel_event=cancel_event)
