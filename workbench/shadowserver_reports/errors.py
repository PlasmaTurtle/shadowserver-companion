"""Public failures contain safe messages, never upstream response bodies or URLs."""


class ShadowserverError(Exception):
    code = "shadowserver_error"

    def public_dict(self):
        return {"error": self.code, "message": str(self)}


class ConfigurationError(ShadowserverError):
    code = "configuration_error"


class AuthenticationError(ShadowserverError):
    code = "authentication_error"


class AuthorizationError(ShadowserverError):
    code = "authorization_error"


class ProtocolError(ShadowserverError):
    code = "protocol_error"


class TransportError(ShadowserverError):
    code = "transport_error"


class DownloadError(ShadowserverError):
    code = "download_error"


class IncompleteError(ShadowserverError):
    code = "incomplete_error"


class Cancelled(ShadowserverError):
    code = "cancelled"


class DeadlineExceeded(ShadowserverError):
    code = "deadline_exceeded"


class BudgetExceeded(ShadowserverError):
    code = "budget_exceeded"


class StorageError(ShadowserverError):
    code = "storage_error"
