"""Lossless separation of generated SVG artwork and embedded webfont faces."""

import re

STYLE = re.compile(r"<defs><style>(.*?)</style></defs>", re.S)
FACE = re.compile(r"@font-face\s*\{[^}]*\}", re.S)


def without_webfonts(vector):
    """Only strip generated font definitions, preserving SVG geometry."""
    text = vector.decode("utf-8")
    return STYLE.sub(
        lambda match: "<defs><style>" + FACE.sub("", match[1]) + "</style></defs>", text
    ).encode("utf-8")
