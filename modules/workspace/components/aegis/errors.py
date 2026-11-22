"""Safe, dependency-free errors shared by input and execution boundaries."""


class InputValidationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SecurityExecutionError(InputValidationError):
    """A cancelled, expired, or capacity-limited security operation."""


class ContentScanError(InputValidationError):
    """A blocked/unavailable scan with a non-content, persistable receipt."""

    def __init__(self, code, message, receipt):
        super().__init__(code, message)
        self.receipt = receipt
