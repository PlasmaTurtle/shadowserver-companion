"""Small immutable public values; raw identifiers are deliberately non-public."""
from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
import json

from .errors import ConfigurationError


def _date_range(start, end):
    if type(start) is not date or type(end) is not date or end < start:
        raise ConfigurationError("Supply an ordered pair of calendar dates.")
    if (end - start).days > 365:
        raise ConfigurationError("A single operation may cover at most 366 days.")


@dataclass(frozen=True, repr=False)
class Credentials:
    api_key: str
    secret: str

    def __post_init__(self):
        if not isinstance(self.api_key, str) or not self.api_key.strip() or not isinstance(self.secret, str) or not self.secret.strip():
            raise ConfigurationError("An API key and secret are required.")

    def __repr__(self):
        return "Credentials(api_key=<redacted>, secret=<redacted>)"


@dataclass(frozen=True)
class ReportSelection:
    start: date
    end: date
    subscriptions: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    limit: int = 1000

    def __post_init__(self):
        _date_range(self.start, self.end)
        if type(self.limit) is not int or not 1 <= self.limit <= 10000:
            raise ConfigurationError("Catalog limit must be between 1 and 10000.")
        for name in ("subscriptions", "types"):
            items = getattr(self, name)
            if isinstance(items, str) or not isinstance(items, (list, tuple)) or any(not isinstance(x, str) or not x.strip() for x in items):
                raise ConfigurationError("Report selectors must be lists of nonempty strings.")
            object.__setattr__(self, name, tuple(dict.fromkeys(items)))


@dataclass(frozen=True)
class ReportDescriptor:
    filename: str
    subscription: str
    report_type: str
    report_date: str
    download_id: str = field(repr=False)
    metadata: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def logical_id(self):
        parts = [self.subscription, self.report_type, self.report_date, self.filename]
        return sha256(json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()

    @property
    def source_fingerprint(self):
        return sha256(self.download_id.encode("utf-8")).hexdigest()

    def public_dict(self):
        return {"filename": self.filename, "subscription": self.subscription,
                "report_type": self.report_type, "report_date": self.report_date,
                "logical_id": self.logical_id, "source_fingerprint": self.source_fingerprint}


@dataclass(frozen=True)
class CatalogResult:
    reports: tuple[ReportDescriptor, ...]
    completeness: str
    reasons: tuple[str, ...] = ()

    def public_dict(self):
        return {"reports": [r.public_dict() for r in self.reports],
                "completeness": self.completeness, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class QuerySpec:
    start: date
    end: date
    scope: dict
    filters: dict = field(default_factory=dict)
    page_size: int = 100
    max_pages: int = 10
    max_records: int = 1000
    sort: str = "ascending"
    facet: str | None = None

    def __post_init__(self):
        _date_range(self.start, self.end)
        if not isinstance(self.scope, dict) or not self.scope or not set(self.scope) <= {"geo", "asn", "domain", "ip"}:
            raise ConfigurationError("Query scope requires geo, asn, domain or ip.")
        if not isinstance(self.filters, dict) or set(self.filters) & set(self.scope):
            raise ConfigurationError("Query filters must not override scope.")
        if any(v is None or isinstance(v, bool) or not isinstance(v, (str, int)) or (isinstance(v, str) and not v.strip()) for v in self.scope.values()):
            raise ConfigurationError("Query scope values must be nonempty strings or integers.")
        for name, maximum in (("page_size", 1000), ("max_pages", 100), ("max_records", 10000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ConfigurationError(f"{name} is outside its supported range.")
        if self.sort not in ("ascending", "descending"):
            raise ConfigurationError("Query sort must be ascending or descending.")
        if self.facet is not None and (not isinstance(self.facet, str) or not self.facet.strip()):
            raise ConfigurationError("Facet must be a field name.")
        # Freeze caller mutations at the boundary without coercing field values.
        try:
            object.__setattr__(self, "scope", json.loads(json.dumps(self.scope, allow_nan=False)))
            object.__setattr__(self, "filters", json.loads(json.dumps(self.filters, allow_nan=False)))
        except (ValueError, TypeError):
            raise ConfigurationError("Query values must be JSON compatible.") from None


@dataclass(frozen=True)
class QueryResult:
    records: tuple[dict, ...]
    completeness: str
    pages: int
    reasons: tuple[str, ...] = ()

    def public_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DownloadReceipt:
    path: str
    original_filename: str
    subscription: str
    report_type: str
    report_date: str
    retrieved_at: str
    size_bytes: int
    sha256: str
    source_fingerprint: str
    logical_id: str
    schema_reference: str | None = None
    validation: str = "csv_valid"
    reused: bool = False

    def public_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class SyncResult:
    status: str
    downloaded: int
    reused: int
    failed: int
    receipts: tuple[DownloadReceipt, ...]
    checkpoint: str | None
    reasons: tuple[str, ...] = ()

    def public_dict(self):
        return asdict(self)
