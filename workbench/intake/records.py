"""Complete source rows and legacy-compatible grouped lead contracts. No network I/O."""

from __future__ import annotations
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as datetime_time
from .domains import DOMAIN_TOKEN, root_domain, registry_address


def json_default(value: object) -> str:
    if isinstance(value, (date, datetime, datetime_time)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__} to JSON")


@dataclass(frozen=True, slots=True)
class UnvalidatedEntry:
    workbook: str
    sheet: str
    row: int
    fields: dict[str, object]


def is_empty_entry(entry: UnvalidatedEntry) -> bool:
    """A wholly empty row is spreadsheet padding, not a failed observation.

    Inspect every source column so an incomplete row with only optional data is
    still validated and accounted for. Numeric zero and False are actual data.
    """
    return all(
        value is None or (isinstance(value, str) and not value.strip())
        for value in entry.fields.values()
    )


@dataclass(frozen=True, slots=True)
class ValidatedEntry:
    source: UnvalidatedEntry
    ip: str
    private_ip: bool
    normalized: dict[str, object] = field(default_factory=dict)


class WhoisLookupError(Exception):
    """An unavailable or invalid registry response, separate from no match."""


@dataclass(frozen=True, slots=True)
class DomainMatch:
    root_domain: str
    matched_domain: str
    field: str
    value: str


@dataclass(frozen=True, slots=True)
class WhoisRecord:
    ip: str
    registry: str
    source_url: str
    retrieved_at: str
    record: dict[str, object]
    protocol: str = "RDAP"

    def find_domain(self, domain: str) -> DomainMatch | None:
        """Match a complete domain or its subdomain in returned string values."""

        def strings(value: object, path: str):
            if isinstance(value, str):
                yield path, value
            elif isinstance(value, dict):
                for key, child in value.items():
                    yield from strings(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    yield from strings(child, f"{path}[{index}]")

        for path, value in strings(self.record, "record"):
            for token in DOMAIN_TOKEN.finditer(value):
                found = token.group().lower()
                if found == domain or found.endswith("." + domain):
                    return DomainMatch(domain, found, path, value)
        return None


@dataclass(frozen=True, slots=True)
class WhoisEvidence:
    ip: str
    registry: str
    source_url: str
    retrieved_at: str
    protocol: str
    attribution: DomainMatch
    record: dict[str, object]

    @classmethod
    def from_record(cls, record: WhoisRecord, match: DomainMatch) -> WhoisEvidence:
        return cls(
            ip=record.ip,
            registry=record.registry,
            source_url=record.source_url,
            retrieved_at=record.retrieved_at,
            protocol=record.protocol,
            attribution=match,
            record=record.record,
        )


@dataclass(slots=True)
class ValidatedLeads:
    """All surviving observations for one root domain."""

    hostname: str
    entries: list[ValidatedEntry] = field(default_factory=list)
    attempts: list[dict[str, object]] = field(default_factory=list, repr=False)

    @classmethod
    def group(cls, entries: Iterable[ValidatedEntry]) -> list[ValidatedLeads]:
        groups: dict[str, ValidatedLeads] = {}
        for entry in entries:
            domain = root_domain(entry.source.fields["hostname"])
            if not domain:
                raise ValueError(f"No root domain for {entry.source.fields['hostname']!r}")
            if domain not in groups:
                groups[domain] = cls(domain)
            groups[domain].entries.append(entry)
        return list(groups.values())

    def qualify(self, lookup_whois: Callable[[str], WhoisRecord | None]) -> QualifiedLeads | None:
        self.attempts.clear()
        checked: set[str] = set()
        for index, entry in enumerate(self.entries):
            address = registry_address(entry.ip)
            ip = address.compressed
            if ip in checked:
                continue
            checked.add(ip)
            if not address.is_global or address.is_multicast:
                self.attempts.append({"ip": ip, "status": "skipped_nonpublic"})
                continue
            try:
                result = lookup_whois(ip)
                if result is not None and registry_address(result.ip) != address:
                    raise WhoisLookupError("Registry result belongs to a different IP")
            except WhoisLookupError as error:
                self.attempts.append({"ip": ip, "status": "lookup_error", "error": str(error)})
                continue
            match = result.find_domain(self.hostname) if result is not None else None
            if match is None:
                self.attempts.append({"ip": ip, "status": "no_match"})
                continue
            self.attempts.append({"ip": ip, "status": "matched"})
            # Move the existing row. Preserve every other observation and its order.
            self.entries.insert(0, self.entries.pop(index))
            return QualifiedLeads(
                hostname=self.hostname,
                validated_leads=[self],
                whois=[WhoisEvidence.from_record(result, match)],
            )
        return None


@dataclass(slots=True)
class QualifiedLeads:
    """One notification's parent object, including all rows and one attribution."""

    hostname: str
    validated_leads: list[ValidatedLeads]
    whois: list[WhoisEvidence]

    def to_dict(self) -> dict[str, object]:
        if not self.validated_leads or not self.validated_leads[0].entries or not self.whois:
            raise ValueError("A qualified lead must contain entries and WHOIS evidence")
        first = self.validated_leads[0].entries[0]
        if registry_address(first.ip) != registry_address(self.whois[0].ip):
            raise ValueError("Entry [0] must correspond to WHOIS evidence [0]")
        if self.whois[0].attribution.root_domain != self.hostname:
            raise ValueError("WHOIS attribution must match the lead's root domain")
        return {
            "hostname": self.hostname,
            "validated_leads": [
                {"hostname": group.hostname, "entries": [asdict(e) for e in group.entries]}
                for group in self.validated_leads
            ],
            "whois": [asdict(evidence) for evidence in self.whois],
        }

    @staticmethod
    def to_json(leads: Iterable[QualifiedLeads]) -> str:
        return (
            json.dumps(
                [lead.to_dict() for lead in leads],
                default=json_default,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            + "\n"
        )
