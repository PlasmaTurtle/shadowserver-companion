"""Stable vulnerability-intelligence API; implementation has explicit owners.

Offline parsing: intelligence.adapters / intelligence.identifiers.
Provider I/O and caching: intelligence.acquisition.
Verification and enrichment: intelligence.service.
"""

from .intelligence.identifiers import identifiers as identifiers
from .intelligence.adapters import summarize as summarize, summarize_nvd as summarize_nvd
from .intelligence.acquisition import (
    SourceCancelled as SourceCancelled,
    SourceDeferred as SourceDeferred,
    cached_json as cached_json,
)
from .intelligence.service import verify as verify, enrich as enrich
