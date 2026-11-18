"""Bounded first-party contact discovery; never sends or submits messages."""

from .engine import ContactDiscovery, DiscoveryLimits
from .extract import candidate_key
from .transport import FetchResponse

__all__ = ["ContactDiscovery", "DiscoveryLimits", "FetchResponse", "candidate_key"]
