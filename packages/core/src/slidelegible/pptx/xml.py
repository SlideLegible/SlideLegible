"""Namespaces and a hardened XML parser for OOXML parts."""

from __future__ import annotations

from lxml import etree

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "ahyp": "http://schemas.microsoft.com/office/drawing/2018/hyperlinkcolor",
}

A = f"{{{NS['a']}}}"
P = f"{{{NS['p']}}}"
R = f"{{{NS['r']}}}"

# Extension URI used by PowerPoint to let a hyperlink keep its run color.
HLINK_COLOR_EXT_URI = "{A12FA001-AC4F-418D-AE19-62706E023703}"

_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    huge_tree=False,
    remove_blank_text=False,
    load_dtd=False,
)


def parse_xml(data: bytes) -> etree._Element:
    """Parse an OOXML part with entity expansion and network access disabled."""
    return etree.fromstring(data, parser=_PARSER)


def serialize_xml(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def local(tag: object) -> str:
    """Return an element's local name (``'solidFill'`` for ``{ns}solidFill``)."""
    text = str(tag)
    return text.rsplit("}", 1)[-1]


def child(el: etree._Element | None, path: str) -> etree._Element | None:
    if el is None:
        return None
    found = el.find(path, NS)
    return found


def children(el: etree._Element | None, path: str) -> list[etree._Element]:
    if el is None:
        return []
    return list(el.findall(path, NS))


def int_attr(el: etree._Element | None, name: str, default: int | None = None) -> int | None:
    if el is None:
        return default
    value = el.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
