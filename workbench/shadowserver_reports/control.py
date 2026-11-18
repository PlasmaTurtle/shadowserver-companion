"""One operation budget follows a request through every nested action."""
import math
import threading
import time

from .errors import BudgetExceeded, Cancelled, ConfigurationError, DeadlineExceeded


class Operation:
    def __init__(self, timeout=120, max_requests=100, max_bytes=1024**3, cancel_event=None):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ConfigurationError("Operation timeout must be a finite positive number.")
        if type(max_requests) is not int or max_requests < 1 or type(max_bytes) is not int or max_bytes < 1:
            raise ConfigurationError("Operation budgets must be positive integers.")
        self.deadline = time.monotonic() + timeout
        self.max_requests = max_requests
        self.max_bytes = max_bytes
        self.requests = 0
        self.bytes_received = 0
        self.cancel_event = cancel_event or threading.Event()
        self._lock = threading.Lock()

    def check(self):
        if self.cancel_event.is_set():
            raise Cancelled("Operation cancelled.")
        if time.monotonic() >= self.deadline:
            raise DeadlineExceeded("Operation deadline exceeded.")

    def remaining(self):
        self.check()
        return max(0.001, self.deadline - time.monotonic())

    def request(self):
        self.check()
        with self._lock:
            if self.requests >= self.max_requests:
                raise BudgetExceeded("Operation request budget exhausted.")
            self.requests += 1

    def consume_bytes(self, count):
        self.check()
        if type(count) is not int or count < 0:
            raise ConfigurationError("Byte count must be a nonnegative integer.")
        with self._lock:
            if self.bytes_received + count > self.max_bytes:
                raise BudgetExceeded("Operation byte budget exhausted.")
            self.bytes_received += count

    def wait(self, seconds):
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise ConfigurationError("Wait duration must be finite and nonnegative.")
        if seconds >= self.remaining():
            raise DeadlineExceeded("Retry delay exceeds the operation deadline.")
        self.cancel_event.wait(seconds)
        self.check()
