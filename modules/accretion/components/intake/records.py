"""Source observations and filtered candidates; no lookup, scoring or persistence."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time
from ipaddress import ip_address

from modules.tools.components.network_identity import extract_domain

from .domains import HOSTNAME, root_domain


def json_default(value: object) -> str:
    if isinstance(value, (date, datetime, datetime_time)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__} to JSON")


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """An unmodified provider row, including malformed values for Dark Matter."""

    workbook: str
    sheet: str
    row: int
    fields: dict[str, object]

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "fields", deepcopy(self.fields))

    def validate(self) -> None:
        """Check row structure while preserving malformed provider field values."""
        if not isinstance(self.workbook, str) or not isinstance(self.sheet, str):
            raise TypeError("Observation source labels must be strings")
        if type(self.row) is not int or self.row < 0:
            raise ValueError("Observation source row must be a nonnegative integer")
        if not isinstance(self.fields, dict) or any(
            not isinstance(key, str) for key in self.fields
        ):
            raise TypeError("Observation fields must be a dictionary with string keys")


def is_empty_entry(entry: SourceObservation) -> bool:
    """A wholly empty row is spreadsheet padding, not a failed observation.

    Inspect every source column so an incomplete row with only optional data is
    still validated and accounted for. Numeric zero and False are actual data.
    """
    return all(
        value is None or (isinstance(value, str) and not value.strip())
        for value in entry.fields.values()
    )


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    """A structurally admitted observation; Filter owns eligibility policy."""

    source: SourceObservation
    ip: str
    private_ip: bool
    normalized: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "normalized", deepcopy(self.normalized))

    def validate(self) -> None:
        """Check source consistency without copying or rerunning Filter policy."""
        if not isinstance(self.source, SourceObservation):
            raise TypeError("Candidate observation requires a source observation")
        self.source.validate()
        if not isinstance(self.ip, str) or not isinstance(self.source.fields.get("ip"), str):
            raise TypeError("Candidate observation requires a reported IP address")
        address = ip_address(self.ip)
        if self.ip != address.compressed or address != ip_address(self.source.fields["ip"]):
            raise ValueError("Candidate IP must be canonical and match the source address")
        if type(self.private_ip) is not bool:
            raise TypeError("Candidate private-IP marker must be a boolean")
        if not isinstance(self.normalized, dict) or any(
            not isinstance(key, str) for key in self.normalized
        ):
            raise TypeError("Candidate metadata must be a dictionary with string keys")


def observation_payload(observation: CandidateObservation) -> dict[str, object]:
    """Project the established saved shape without recursively copying evidence."""
    source = observation.source
    return {
        "source": {
            "workbook": source.workbook,
            "sheet": source.sheet,
            "row": source.row,
            "fields": source.fields,
        },
        "ip": observation.ip,
        "private_ip": observation.private_ip,
        "normalized": observation.normalized,
    }


@dataclass(frozen=True, slots=True)
class CandidateGroup:
    """Nonempty observations for one domain; not yet a qualified lead.

    Membership is fixed at construction. Report binding belongs to the workflow
    product, while Filter owns public-domain admission. Reserved synthetic domains
    can still use this grouping contract without pretending to pass Filter.
    """

    root_domain: str
    observations: tuple[CandidateObservation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        self.validate()

    def validate(self) -> None:
        """Recheck member structure and domain scope without copying source trees."""
        if not isinstance(self.root_domain, str) or not HOSTNAME.fullmatch(self.root_domain):
            raise ValueError("Candidate group requires a root domain")
        extracted = extract_domain(self.root_domain)
        if (
            extracted.suffix
            and extracted.top_domain_under_public_suffix.casefold() != self.root_domain.casefold()
        ):
            raise ValueError("Candidate group domain must be a registrable root")
        if not self.observations:
            raise ValueError("Candidate group requires observations")
        root = self.root_domain.casefold()
        for observation in self.observations:
            if not isinstance(observation, CandidateObservation):
                raise TypeError("Candidate group accepts only candidate observations")
            observation.validate()
            hostname = observation.source.fields.get("hostname")
            if not isinstance(hostname, str) or not HOSTNAME.fullmatch(hostname):
                raise ValueError("Candidate observation requires a hostname")
            observed_root = extract_domain(hostname).top_domain_under_public_suffix
            belongs = (
                observed_root.casefold() == root
                if observed_root
                else hostname.casefold() == root or hostname.casefold().endswith("." + root)
            )
            if not belongs:
                raise ValueError("Candidate observation belongs to a different root domain")

    @classmethod
    def group(cls, observations: Iterable[CandidateObservation]) -> list[CandidateGroup]:
        groups: dict[str, list[CandidateObservation]] = {}
        for observation in observations:
            if not isinstance(observation, CandidateObservation):
                raise TypeError("Candidate grouping accepts only candidate observations")
            hostname = observation.source.fields.get("hostname")
            if not isinstance(hostname, str) or not HOSTNAME.fullmatch(hostname):
                raise ValueError("Candidate observation requires a hostname")
            domain = root_domain(hostname)
            groups.setdefault(domain, []).append(observation)
        return [cls(domain, tuple(members)) for domain, members in groups.items()]
