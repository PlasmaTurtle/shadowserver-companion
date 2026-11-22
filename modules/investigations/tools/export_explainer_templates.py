"""Export the recipient Information pages using the production page renderer.

This is an offline content-bank collection, with no case or business data.
An incident case uses the evidence-aware common-page clause documented in the
release guide; the collection starts with the standard common page.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from reportlab.pdfgen.canvas import Canvas
from modules.ui.components.exhibit_rendering import ExhibitFlowable
from modules.investigations.components.information_layout import layout_information
from modules.investigations.components.information_pages import build_information_pages
from modules.ui.components.print_policy import draw_tlp
from modules.investigations.components.report_composition import Citations
from modules.library.resources.report_explainer_data import BANK
from modules.workspace.components.release import load_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--qa", type=Path)
    args = parser.parse_args()
    order = (
        "vulnerable_http",
        "smtp_vulnerable",
        "exchange",
        "isakmp_vulnerable",
        "badsecrets",
        "open_mongodb",
        "accessible_rdp",
        "accessible_msrpc",
        "compromised_website",
        "compromised_iot",
    )
    # Bank insertion order is authoritative for any family added or renamed.
    keys = [key for key in order if key in BANK]
    keys.extend(key for key in BANK if key not in keys)
    pages = [deepcopy(BANK[key]) for key in keys]
    for page in pages:
        page["source_report_types"] = page["report_types"]
    model = build_information_pages(
        {"draft": {"report_explainer_snapshots": pages}, "explainers": []}, Citations()
    )
    standard = build_information_pages(
        {"draft": {"report_explainer_snapshots": []}, "explainers": []}, Citations()
    )
    model["pages"][0] = standard["pages"][0]
    rendered = layout_information(model)
    assert len(rendered) == 1 + len(BANK)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(args.output), pagesize=(612, 792), pageCompression=1)
    product = load_release()["app_name"]
    canvas.setTitle(product + " - Information and Report Explainers")
    canvas.setAuthor(product)
    checks = []
    for index, page in enumerate(rendered, 1):
        left = (612 - page.width) / 2
        ExhibitFlowable(page).drawOn(canvas, left, 71)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(left, 759, "INFORMATION PAGES")
        canvas.drawString(left, 34, "Reference preview | No case or agency profile")
        canvas.drawCentredString(306, 20, f"{index} of {len(rendered)}")
        draw_tlp(canvas, 612 - left, 758)
        draw_tlp(canvas, 612 - left, 31)
        canvas.showPage()
        checks.append(
            {
                "page": index,
                "id": model["pages"][index - 1]["id"],
                "links": sum(s.get("kind") == "link" for s in page.segments),
                "segments": page.segments,
            }
        )
    canvas.save()
    if args.qa:
        args.qa.parent.mkdir(parents=True, exist_ok=True)
        args.qa.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "pages": len(rendered)}))


if __name__ == "__main__":
    main()
