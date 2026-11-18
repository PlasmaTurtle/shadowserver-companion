"""Self-contained exhibit gallery with one copy of each embedded font face.

The certified snapshot retains verified masters for exact standalone SVG/PDF
exports. The gallery is a separate, fully hashed portable viewing artifact.
"""

from html import escape
from pathlib import Path

from .exhibit_rendering import is_page_exhibit, prepared_pages, layout, svg
from .svg_resources import STYLE, FACE, without_webfonts


def export_gallery(content, folder, policy=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fonts, pages, artifacts = {}, [], []
    for exhibit in content.get("exhibits", []):
        masters = prepared_pages(exhibit) if is_page_exhibit(exhibit) else []
        rendered = (
            [(master.page, master.svg) for master in masters]
            if masters
            else [(page, svg(page)) for page in layout(exhibit, policy)]
        )
        for page, vector in rendered:
            vector = vector.replace(b"Companion Exhibit Sans", b"DejaVu Sans").replace(
                b"Companion CJK", b"Companion Noto Sans SC"
            )
            text = vector.decode("utf-8")
            for style in STYLE.findall(text):
                for face in FACE.findall(style):
                    fonts.setdefault(face, None)
            anchor = exhibit["id"].lower() + "-" + str(page.page)
            pages.append(
                '<section id="'
                + escape(anchor, quote=True)
                + '"><h2>'
                + escape(exhibit.get("title", exhibit["id"]))
                + f" · {page.page}</h2>"
                + without_webfonts(vector).decode("utf-8")
                + "</section>"
            )
            artifacts.append(
                {
                    "exhibit_id": exhibit["id"],
                    "page": page.page,
                    "format": "shared-gallery-v1",
                    "gallery": "exhibits/exhibit-gallery.html",
                    "anchor": anchor,
                    "purpose": "portable exhibit preview",
                }
            )
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:\">"
        "<title>Certified report exhibits</title><style>"
        + "\n".join(fonts)
        + "body{margin:0;background:#eee;font-family:sans-serif}header,section{max-width:800px;margin:24px auto;padding:24px;background:white}"
        "h1{font-size:22px}h2{font-size:16px}svg{display:block;width:100%;height:auto}"
        "@media print{body{background:white}header{display:none}section{break-after:page;margin:0;padding:0}h2{font-size:10px}}"
        "</style><header><h1>Certified report exhibits</h1><p>TLP:AMBER · Internal evidence.</p><p>Offline gallery. The complete reviewed masters remain in snapshot.json for standalone exports.</p></header>"
        + "".join(pages)
        + "</html>"
    )
    (folder / "exhibit-gallery.html").write_text(document, encoding="utf-8")
    return artifacts
