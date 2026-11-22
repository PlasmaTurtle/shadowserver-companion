"""Produce synthetic recipient appendix and revised resource-page review files."""

from pathlib import Path
from copy import deepcopy
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "modules/attribution/components/engine/src"))

from modules.investigations.tools.preview_closing import specimen as closing_specimen
from modules.investigations.components.appendix_view import REVISION
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_renderers import render_pdf, render_docx
from modules.ui.components.exhibit_rendering import capture_exhibit_masters, prepared_pages


def specimen(extended=False, capture=True):
    data = closing_specimen()
    data["draft"]["appendix_revision"] = REVISION
    if extended:
        entry = data["qualified_lead"]["validated_leads"][0]["entries"][0]
        entry["source"]["fields"].update(
            {
                "unknown/field": 0,
                "empty_text": "",
                "null_value": None,
                "empty_list": [],
                "empty_object": {},
                "enabled": False,
                "long_response": " ".join(
                    f"Recorded response sentence {i} remains intact across continuation pages."
                    for i in range(1, 65)
                ),
            }
        )
    data["composition"] = compose(data)
    if capture:
        capture_exhibit_masters(data["composition"])
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for old in args.output.glob("EX-APPENDIX-*.svg"):
        old.unlink()
    data = specimen()
    (args.output / "Standard_Source.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    content = data["composition"]
    start = next(
        i for i, n in enumerate(content["sections"]) if n.get("exhibit_id") == "EX-CLOSING"
    )
    content["sections"] = content["sections"][start:]
    render_pdf(data, args.output / "Appendices_Standard.pdf", args.output, draft=True)
    render_docx(data, args.output / "Appendices_Standard.docx", args.output)
    closing = deepcopy(data)
    closing["composition"]["sections"] = [
        n for n in content["sections"] if n.get("exhibit_id") == "EX-CLOSING"
    ]
    render_pdf(closing, args.output / "Resources_Revised.pdf", args.output, draft=True)
    # Only the expanded observation appendix is repeated in the stress specimen.
    extended = specimen(True)
    (args.output / "Extended_Source.json").write_text(
        json.dumps(extended, indent=2), encoding="utf-8"
    )
    guide = next(e for e in extended["composition"]["exhibits"] if e["id"] == "EX-APPENDIX-INDEX")
    guide.pop("rendered_masters", None)
    guide["directory"] = [d for d in guide["directory"] if d["section"] == "A"]
    guide["description"] = (
        "This synthetic continuation example contains the reported-observation appendix only. It tests long source text and explicitly retained empty values."
    )
    extended["composition"]["sections"] = [
        {"kind": "exhibit", "exhibit_id": "EX-APPENDIX-INDEX", "section_owner": "information"},
        {"kind": "page_break", "section_owner": "introduction"},
        {"kind": "exhibit", "exhibit_id": "EX-APPENDIX-A", "section_owner": "introduction"},
    ]
    observation = next(e for e in extended["composition"]["exhibits"] if e["id"] == "EX-APPENDIX-A")
    extended["composition"]["appendix_navigation"]["anchors"] = [
        "companion-appendix",
        "appendix-A",
        *[r["id"] for r in observation["records"]],
    ]
    render_pdf(extended, args.output / "Appendices_Extended.pdf", args.output, draft=True)
    render_docx(extended, args.output / "Appendices_Extended.docx", args.output)
    results = []
    for model in content["exhibits"]:
        if not model["id"].startswith("EX-APPENDIX-"):
            continue
        pages = prepared_pages(model)
        for page in pages:
            (args.output / f"{model['id']}_{page.page.page}.svg").write_bytes(page.standalone_svg)
        results.append(
            {"id": model["id"], "pages": len(pages), "records": len(model.get("records", []))}
        )
    (args.output / "review.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
