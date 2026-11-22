"""Render offline notification Closing specimens through the production exporters."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "modules/attribution/components/engine/src"))

from modules.investigations.tools.preview_information import specimen as information_specimen
from modules.investigations.components.closing_page_model import REVISION
from modules.ui.components.exhibit_rendering import capture_exhibit_masters, prepared_pages
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_renderers import render_docx, render_pdf


def specimen(extended=False):
    data = information_specimen()
    data["draft"]["closing_revision"] = REVISION
    if extended:
        data["draft"]["resources"] += "\n" + "\n".join(
            f"https://resources.example/advisories/{i}/" + "synthetic-pagination-check-" * 5
            for i in range(1, 10)
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
        model = next(e for e in data["composition"]["exhibits"] if e["type"] == "closing")
        pages = prepared_pages(model)
        (args.output / f"{name}_Source.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        data["composition"]["sections"] = [
            n for n in data["composition"]["sections"] if n.get("exhibit_id") == model["id"]
        ]
        stem = args.output / f"Closing_{name}"
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
