"""Versioned document presentation, independent of browser appearance.

These small JSON contracts are pinned in the case draft and certified snapshot.
Changing an application preference never rewrites historical report bytes.
"""

from copy import deepcopy
import hashlib
import json
from modules.investigations.components.report_contracts import DocumentPolicy

RENDERER_VERSION = "0.7.0"
HANDLING = {
    "label": "TLP:AMBER",
    "standard_version": "2.0",
    "policy_version": "1",
    "foreground": "#FFC000",
    "background": "#000000",
    "minimum_font_pt": 12,
    "source_restrictions": [],
    "guidance_url": "https://www.first.org/tlp/",
    "sharing": "Share on a need-to-know basis within the receiving organization and its clients. Source-specific additional restrictions remain applicable.",
}
PROFILES = {
    "companion": {
        "id": "companion",
        "version": "1",
        "name": "Companion",
        "palette": {
            "primary": "#245DAD",
            "confirmation": "#245DAD",
            "adverse": "#B42318",
            "accent": "#7564C4",
            "ink": "#000000",
            "paper": "#FFFFFF",
        },
        "provenance": "Shadowserver Companion application profile; no agency endorsement implied.",
    },
    "usss": {
        "id": "usss",
        "version": "1",
        "name": "USSS",
        "palette": {
            "primary": "#002d61",
            "confirmation": "#002d61",
            "adverse": "#B42318",
            "accent": "#b4a471",
            "beast_black": "#010101",
            "lincoln_blue": "#002d61",
            "detail_blue": "#5f88b0",
            "centurion_gold": "#b4a471",
            "legacy_gold": "#d5cca8",
            "ink": "#000000",
            "paper": "#FFFFFF",
        },
        "provenance": "User-supplied digital palette. Approved only for specified mission-related activities; use outside those parameters or without explicit HQ OPA approval is prohibited. Profile selection does not confer approval.",
        "notes": [
            "Supplied hex values govern digital rendering.",
            "Centurion Gold supplied RGB 193,168,113 differs from hex #b4a471 (180,164,113).",
            "Beast Black supplied RGB 0,0,0 differs from hex #010101.",
        ],
    },
}


def document_policy(settings) -> DocumentPolicy:
    return {
        "brand_profile": deepcopy(PROFILES[settings.get("brand_profile", "companion")]),
        "print_policy_version": "1",
        "renderer_version": RENDERER_VERSION,
        "paragraph_alignment": "justify",
        "handling": deepcopy(HANDLING),
    }


def presentation_catalog(settings):
    return {
        "profiles": deepcopy(list(PROFILES.values())),
        "document_policy": document_policy(settings),
        "handling_policy": deepcopy(HANDLING),
    }


def source_restrictions(draft, extra_sources=None):
    """Keep source restrictions separate from the workspace sharing default."""
    found = {}

    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    key
                    in (
                        "source_restrictions",
                        "additional_restrictions",
                        "tlp",
                        "tlp_label",
                        "handling_label",
                    )
                    and item
                ):
                    values = item if isinstance(item, list) else [item]
                    for text in values:
                        raw = (
                            text
                            if isinstance(text, str)
                            else json.dumps(text, sort_keys=True, ensure_ascii=False)
                        )
                        if raw.strip().upper() in (
                            "TLP:AMBER",
                            "AMBER",
                            "TLP:CLEAR",
                            "CLEAR",
                            "TLP:WHITE",
                            "WHITE",
                            "TLP:GREEN",
                            "GREEN",
                        ):
                            continue
                        identity = hashlib.sha256(
                            (path + "/" + key + ":" + raw).encode()
                        ).hexdigest()[:20]
                        found[identity] = {
                            "id": identity,
                            "path": path + "/" + key,
                            "restriction": raw,
                        }
                elif key != "handling_dispositions":
                    walk(item, path + "/" + key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + "/" + str(index))

    walk(
        {
            "cve_records": draft.get("cve_records", []),
            "source_restrictions": draft.get("source_restrictions", []),
            "case_sources": extra_sources or [],
        },
        "",
    )
    return list(found.values())


def handling_issues(draft, extra_sources=None):
    # Source exclusions must remove the selected material. Merely typing a
    # disposition cannot widen a source's sharing boundary.
    return [
        "Selected source has an additional sharing restriction: "
        + item["restriction"]
        + ". Remove it from this recipient package or obtain and record a compatible source."
        for item in source_restrictions(draft, extra_sources)
    ]


def mark_attribution_bundle(folder):
    """Mark a generated app export; captured response bytes stay untouched."""
    from pathlib import Path

    folder = Path(folder)
    page = folder / "evidence.html"
    body = page.read_text(encoding="utf-8")
    css = """<style>
    .companion-tlp{color:#FFC000!important;background:#000!important;font:700 12pt Arial,sans-serif;padding:4pt 7pt;display:inline-block}
    .companion-tlp-top,.companion-tlp-bottom{text-align:right;margin:10px 0}
    h2{color:#002d61}mark{background:#dbeafe}.status{background:#eaf2ff;border-color:#96b2db}
    @media print{@page{margin:22mm 14mm}body{color:#000!important}body *{color:#000!important}.companion-tlp{color:#FFC000!important;background:#000!important;print-color-adjust:exact;-webkit-print-color-adjust:exact}.companion-tlp-top{position:fixed;top:-17mm;right:0}.companion-tlp-bottom{position:fixed;bottom:-17mm;right:0}}
    </style>"""
    top = '<div class="companion-tlp-top"><span class="companion-tlp">TLP:AMBER</span></div>'
    bottom = '<div class="companion-tlp-bottom"><span class="companion-tlp">TLP:AMBER</span></div>'
    page.write_text(
        body.replace("</head>", css + "</head>", 1)
        .replace("<body>", "<body>" + top, 1)
        .replace("</body>", bottom + "</body>", 1),
        encoding="utf-8",
    )
    (folder / "handling.json").write_text(json.dumps(HANDLING, indent=2), encoding="utf-8")
    (folder / "HANDLING.txt").write_text(
        "TLP:AMBER\n\n" + HANDLING["sharing"] + "\n" + HANDLING["guidance_url"] + "\n",
        encoding="utf-8",
    )
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["handling"] = deepcopy(HANDLING)
    for name in ("evidence.html", "handling.json", "HANDLING.txt"):
        manifest["files"][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
