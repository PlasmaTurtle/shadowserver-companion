"""Bundled typefaces for page exhibits embedded in Word."""

from uuid import UUID
from .vector_layout import FONT_ROOT


def embed_report_fonts(doc, *, include_cjk=False):
    """The exact bundled report font travels with Word; no workstation install."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.part import Part
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.opc.packuri import PackURI
    from lxml import etree

    package = doc.part.package
    table = next(p for p in package.iter_parts() if str(p.partname) == "/word/fontTable.xml")
    root = etree.fromstring(table.blob)
    existing = {str(p.partname) for p in package.iter_parts()}
    families = {}
    typefaces = [
        ("DejaVu Sans", "DejaVuSans.ttf", "Regular", "75ee12d1-24a7-49ec-ab5e-a598e52e86c9"),
        ("DejaVu Sans", "DejaVuSans-Bold.ttf", "Bold", "f1bbd53a-65b8-4d79-a63f-9976511fdb3a"),
        ("DejaVu Serif", "DejaVuSerif.ttf", "Regular", "ab13e088-9a31-4c19-b69c-d7c3a16088bd"),
    ]
    if include_cjk:
        typefaces.append(
            (
                "Companion Noto Sans SC",
                "NotoSansSC-Regular.ttf",
                "Regular",
                "82156389-4e28-4821-8bce-cdf0b2ed44c0",
            )
        )
    for family_name, name, face, identifier in typefaces:
        partname = "/word/fonts/" + (
            "CompanionNotoSansSC.odttf" if name == "NotoSansSC-Regular.ttf" else name + ".odttf"
        )
        if partname in existing:
            continue
        if family_name not in families:
            family = next((f for f in root if f.get(qn("w:name")) == family_name), None)
            if family is None:
                family = etree.SubElement(root, qn("w:font"))
                family.set(qn("w:name"), family_name)
            families[family_name] = family
        family = families[family_name]
        guid = UUID(identifier)
        key = guid.bytes[::-1]
        raw = bytearray((FONT_ROOT / name).read_bytes())
        for i in range(32):
            raw[i] ^= key[i % 16]
        part = Part(
            PackURI(partname),
            "application/vnd.openxmlformats-officedocument.obfuscatedFont",
            bytes(raw),
            package,
        )
        rid = table.relate_to(part, RELATIONSHIP_TYPE.FONT)
        embed = etree.SubElement(family, qn("w:embed" + face))
        embed.set(qn("r:id"), rid)
        embed.set(qn("w:fontKey"), "{" + str(guid).upper() + "}")
    table._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if doc.settings.element.find(qn("w:embedTrueTypeFonts")) is None:
        doc.settings.element.append(OxmlElement("w:embedTrueTypeFonts"))
