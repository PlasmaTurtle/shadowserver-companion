"""Raw compound URL fields remain literal records without misleading hyperlinks."""

from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
import pytest
from reportlab.pdfgen.canvas import Canvas

from workbench.appendix_layout import AppendixLayout
from workbench.appendix_renderers import add_docx_appendix_page
from workbench.exhibit_rendering import ExhibitFlowable


@pytest.mark.parametrize("method", ["fields", "compact_fields"])
@pytest.mark.parametrize("alignment", [None, "justify"])
@pytest.mark.parametrize(
    "compound",
    [
        "https://vendor.example/releases ; https://advisory.example/notice ; https://nvd.nist.gov/",
        "https://vendor.example/releases;https://advisory.example/notice",
        "https://vendor.example/releases additional source text",
    ],
)
def test_source_url_autolinks_preserve_text_and_historical_policy(method, alignment, compound):
    single = "https://nvd.nist.gov/vuln/detail/CVE-2026-0001"
    model = {"id": "EX-APPENDIX", "paragraph_alignment": alignment}
    group = {
        "path": "/details",
        "fields": [
            {"label": "Source URLs", "path": "/sources", "text": compound, "value_type": "string"},
            {"label": "Reference", "path": "/reference", "text": single, "value_type": "string"},
        ],
    }
    original = deepcopy(group)
    layout = AppendixLayout(model)
    layout.current_record = {"id": "record"}
    layout.current_group = group
    getattr(layout, method)(group)
    layout.finish()
    assert group == original
    page = layout.pages[0]
    visible = "".join(element[3] for element in page.elements if element[0] == "text")
    assert "".join(compound.split()) in "".join(visible.split())
    expected = {single} if alignment == "justify" else {single, compound}
    assert {segment["url"] for segment in page.segments if segment["kind"] == "link"} == expected

    stream = BytesIO()
    canvas = Canvas(stream, pagesize=(page.width, page.height), invariant=1)
    ExhibitFlowable(page).drawOn(canvas, 0, 0)
    canvas.save()
    pdf = stream.getvalue()
    assert single.encode() in pdf
    assert (compound.encode() in pdf) == (alignment is None)

    document = Document()
    add_docx_appendix_page(document, SimpleNamespace(page=page))
    urls = {
        relation.target_ref
        for relation in document.part.rels.values()
        if relation.reltype == RELATIONSHIP_TYPE.HYPERLINK
    }
    assert urls == expected
