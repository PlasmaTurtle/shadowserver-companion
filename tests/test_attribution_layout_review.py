"""Lossless attribution pagination and clear, non-color-only evidence status."""

from copy import deepcopy

from workbench import approved_template as approved
from workbench.attribution_layout import (
    layout_attribution,
    card_rows,
    BLUE,
    RED,
    BLACK,
    BOTTOM,
    PAGE_WIDTH,
    PAGE_HEIGHT,
)
from workbench.unicode_fonts import width as text_width


def model():
    return {
        "id": "EX-ATTRIBUTION",
        "narrative": approved.ATTRIBUTION,
        "company": "Harbor Example Health, P.A.",
        "items": [
            {
                "label": "harborhealth.example",
                "method_label": "Exact domain in registration record",
                "supported": True,
                "reported_ip": "192.0.2.14",
                "corroborated_value": "192.0.2.0 – 192.0.2.255",
                "corroborated_label": "Covering network",
                "explanation": "The saved registration record contains harborhealth.example. The reported IP is within its recorded network range.",
                "matched_field": "/entities/0/vcardArray/1/3/3",
                "matched_value": "security@harborhealth.example",
                "source_name": "Synthetic registry",
                "source_url": "https://sources.example/rdap/192.0.2.14",
                "citations": [1],
                "validated_at": "2026-11-07T14:31:00Z",
                "validated_by": "Attribution Module",
                "retrieved_at": "2026-11-07T14:30:00Z",
                "reported_asset_count": 70,
                "supporting_attribution_count": 1,
            }
        ],
    }


def all_text(pages):
    return " ".join(e[3] for p in pages for e in p.elements if e[0] == "text")


def verify_bounds(pages):
    for page in pages:
        assert page.width == PAGE_WIDTH and page.height == PAGE_HEIGHT
        for e in page.elements:
            if e[0] == "text":
                _, x, baseline, text, size, bold, color = e
                assert size >= 10 and color == BLACK
                assert 0 <= baseline <= PAGE_HEIGHT
                assert 0 <= x <= PAGE_WIDTH
                assert (
                    x + text_width(text, "ExhibitSans-Bold" if bold else "ExhibitSans", size)
                    <= PAGE_WIDTH + 0.01
                )
            elif e[0] == "rect":
                _, x, top, width, height, _ = e
                assert x >= 0 and top >= 0 and x + width <= PAGE_WIDTH + 0.01
                assert top + height <= PAGE_HEIGHT
        for segment in page.segments:
            if "height" in segment:
                assert segment["top"] + segment["height"] <= BOTTOM + 0.01


def test_ordinary_card_and_approved_paragraph_are_whole_and_lossless():
    data = model()
    before = deepcopy(data)
    pages = layout_attribution(data)
    text = all_text(pages)
    assert " ".join(approved.ATTRIBUTION.split()) in text
    assert text.count("This notification is based on an internet-facing system") == 1
    assert text.count("harborhealth.example") >= 3
    assert "1 supporting association / 70 reported IP addresses" in text
    assert "Validated: 2026-11-07T14:31:00Z" in text
    assert "Retrieved: 2026-11-07T14:30:00Z" in text
    assert "Validated by: Attribution Module" in text
    assert any(e[0] == "rect" and e[-1] == BLUE for p in pages for e in p.elements)
    assert not any(e[0] == "rect" and e[-1] == RED for p in pages for e in p.elements)
    segments = [s for p in pages for s in p.segments if s["kind"] == "association"]
    assert len(segments) == 1 and segments[0]["complete"]
    assert data == before
    verify_bounds(pages)


def test_missing_validation_time_is_explicit_and_does_not_use_retrieval_time():
    data = model()
    data["items"][0].update(
        validated_at=None,
        validated_by=None,
        review_required=True,
        timestamp_note="Validation time was not recorded.",
    )
    pages = layout_attribution(data)
    text = all_text(pages)
    assert "Needs review" in text and "Association supported" not in text
    assert "Validated: Not recorded" in text and "Validated by: Not recorded" in text
    assert "Validation time was not recorded." in text
    assert any(e[0] == "rect" and e[-1] == RED for p in pages for e in p.elements)
    verify_bounds(pages)


def test_unsupported_association_uses_review_status_and_zero_support():
    data = model()
    data["items"][0].update(
        supported=False,
        supporting_attribution_count=0,
        explanation="The reported IP is outside the recorded network.",
    )
    pages = layout_attribution(data)
    assert "Needs review" in all_text(pages)
    assert "0 supporting associations / 70 reported IP addresses" in all_text(pages)
    assert not any(e[0] == "rect" and e[-1] == BLUE for p in pages for e in p.elements)
    verify_bounds(pages)


def test_long_ipv6_hostname_and_source_url_wrap_inside_their_columns():
    data = model()
    item = data["items"][0]
    item.update(
        label="long-network-service-name." * 8 + "example.com",
        reported_ip="2001:db8:1234:5678:90ab:cdef:1234:5678",
        corroborated_value="2001:db8:1234:5678:0000:0000:0000:0000 – 2001:db8:1234:5678:ffff:ffff:ffff:ffff",
        source_url="https://sources.example/registry/entity/" + "a" * 400,
        matched_field="/entities/0/" + "nested_path/" * 40,
    )
    pages = layout_attribution(data)
    text = all_text(pages).replace(" ", "")
    for key in ("label", "source_url"):
        assert item[key].replace(" ", "") in text
    # Reading order alternates evidence columns. Recover each visible column
    # independently so wrapped IPv6 strings are checked without interleaving.
    columns = {}
    for page in pages:
        for e in page.elements:
            if e[0] == "text" and e[4] == 11 and e[5]:
                columns.setdefault(e[1], []).append(e[3])
    column_texts = ["".join(values).replace(" ", "") for values in columns.values()]
    for key in ("reported_ip", "corroborated_value"):
        assert any(item[key].replace(" ", "") in value for value in column_texts)
    assert item["matched_field"] not in all_text(
        pages
    )  # Technical pointer remains in the model/appendix.
    verify_bounds(pages)


def test_thousand_word_detail_continues_without_duplication_or_omission():
    data = model()
    data["items"][0]["review_note"] = " ".join(f"DetailWord{n:04}" for n in range(1000))
    pages = layout_attribution(data)
    text = all_text(pages)
    assert len(pages) > 2
    assert "Attribution — continued" in text
    assert "Association 1 — continued" in text
    for n in range(1000):
        assert text.count(f"DetailWord{n:04}") == 1
    assert text.count("This notification is based on an internet-facing system") == 1
    verify_bounds(pages)


def test_oversized_narrative_keeps_all_words_before_association():
    data = model()
    data["narrative"] = " ".join(f"NarrativeWord{n:04}" for n in range(900))
    pages = layout_attribution(data)
    text = all_text(pages)
    for n in range(900):
        assert text.count(f"NarrativeWord{n:04}") == 1
    assert text.index("NarrativeWord0899") < text.index("Association 1")
    verify_bounds(pages)


def test_many_associations_keep_source_references_local_and_number_continuations():
    data = model()
    data["items"] = [
        {**data["items"][0], "citations": [n], "label": f"domain{n}.example"} for n in range(1, 5)
    ]
    pages = layout_attribution(data)
    assert len(pages) >= 4
    for n in range(1, 5):
        assert all_text(pages).count(f"domain{n}.example") == 1
    for page in pages:
        assoc = [s["id"] for s in page.segments if s["kind"] == "association"]
        refs = next(s["values"] for s in page.segments if s["kind"] == "page_citations")
        assert refs == sorted(set(assoc))
    verify_bounds(pages)


def test_empty_attribution_still_has_a_reviewable_page():
    data = {"id": "EX-ATTRIBUTION", "items": []}
    pages = layout_attribution(data)
    assert len(pages) == 1
    assert "No supporting association is recorded" in all_text(pages)
    assert "Attribution review is required" in all_text(pages)
    verify_bounds(pages)


def test_business_registration_note_is_retained_once():
    data = model()
    data["business_registration_note"] = (
        "Business-registration information reviewed by the analyst; supporting details are recorded with the case."
    )
    pages = layout_attribution(data)
    assert all_text(pages).count(data["business_registration_note"]) == 1
    verify_bounds(pages)
