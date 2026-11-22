"""Stable public entry points for the report pipeline.

Implementation lives in focused modules. Existing callers keep these imports;
finalize resolves the public snapshot/render functions at call time so test and
application dependency substitution remains explicit and compatible.
"""

from .report_drafts import (
    CVE,
    INTRO,
    NEXT_STEPS,
    LIMITATION,
    RESOURCES,
    attribution_summary,
    default_draft,
    hydrated_draft,
    readiness,
)
from .report_snapshot import snapshot
from .report_renderers import render_pdf, render_docx
from .report_certification import certify_report
from .report_package import PackageRenderers

__all__ = [
    "CVE",
    "INTRO",
    "NEXT_STEPS",
    "LIMITATION",
    "RESOURCES",
    "attribution_summary",
    "default_draft",
    "hydrated_draft",
    "readiness",
    "snapshot",
    "render_pdf",
    "render_docx",
    "finalize",
]


def finalize(store, lead_id, case_id=None):
    """Certify using the same public snapshot and render functions as preview."""
    return certify_report(
        store,
        lead_id,
        case_id,
        build_snapshot=snapshot,
        renderers=PackageRenderers(pdf=render_pdf, docx=render_docx),
    )
