"""Embed a bundled OpenType font without changing the caller's font-family policy."""

from uuid import UUID


def embed_font(package, table, family, font_path, part_name, face, identifier):
    """Attach the same obfuscated font bytes and relationship used by Word exports."""
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml.ns import qn
    from lxml import etree

    guid = UUID(identifier)
    key = guid.bytes[::-1]
    raw = bytearray(font_path.read_bytes())
    for index in range(32):
        raw[index] ^= key[index % 16]
    part = Part(
        PackURI(part_name),
        "application/vnd.openxmlformats-officedocument.obfuscatedFont",
        bytes(raw),
        package,
    )
    rid = table.relate_to(part, RELATIONSHIP_TYPE.FONT)
    embed = etree.SubElement(family, qn("w:embed" + face))
    embed.set(qn("r:id"), rid)
    embed.set(qn("w:fontKey"), "{" + str(guid).upper() + "}")
