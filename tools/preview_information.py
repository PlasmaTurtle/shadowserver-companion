"""Render synthetic, offline Information review specimens using production exporters."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "components" / "attribution" / "src"))

from tools.preview_attribution import specimen as attribution_specimen
from workbench.exhibit_rendering import capture_exhibit_masters, prepared_pages

# This fixture reproduces the historical Information review. Production
# report-family one-pagers are exercised by export_explainer_templates.py.
from workbench.information_model import PREVIOUS_REVISION as REVISION
from workbench.report_composition import compose
from workbench.report_renderers import render_docx, render_pdf


def specimen(extended=False, revision=REVISION):
    data = attribution_specimen("DNS")
    data["draft"]["information_revision"] = revision
    if extended:
        data["explainers"].append(
            {
                "id": "synthetic-review-guidance",
                "revision": 1,
                "title": "Example Additional Advisory",
                "body": "\n\n".join(
                    f"Example paragraph {i}. This synthetic advisory demonstrates how an additional selected explanation continues across pages. The saved paragraph remains intact in the report and source record. Its wording is a layout fixture and is not an approved notification paragraph."
                    for i in range(1, 11)
                ),
                "sources": "https://sources.example/advisory",
                "source_metadata": [
                    {
                        "url": "https://sources.example/advisory",
                        "publisher": "Example source (synthetic)",
                        "title": "Synthetic additional advisory",
                        "retrieved_at": "2026-11-07T18:00:00Z",
                    }
                ],
            }
        )
    data["composition"] = compose(data)
    capture_exhibit_masters(data["composition"])
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name, extended in (("Standard", False), ("Extended", True)):
        data = specimen(extended)
        model = next(e for e in data["composition"]["exhibits"] if e["type"] == "information")
        pages = prepared_pages(model)
        (args.output / f"{name}_Source.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        data["composition"]["sections"] = [
            n for n in data["composition"]["sections"] if n.get("exhibit_id") == "EX-INFORMATION"
        ]
        stem = args.output / f"Information_{name}"
        render_pdf(data, stem.with_suffix(".pdf"), args.output, draft=True)
        render_docx(data, stem.with_suffix(".docx"), args.output)
        for old in args.output.glob(stem.name + "_[0-9]*.svg"):
            old.unlink()
        for page in pages:
            (args.output / f"{stem.name}_{page.page.page}.svg").write_bytes(page.standalone_svg)
        results.append(
            {
                "scenario": name,
                "pages": len(pages),
                "revision": REVISION,
                "model_sha256": model["rendered_masters"]["model_sha256"],
                "pagination": [page.page.segments for page in pages],
            }
        )
    (args.output / "review.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(
        json.dumps([{k: v for k, v in r.items() if k != "pagination"} for r in results], indent=2)
    )


if __name__ == "__main__":
    main()
