"""Targeted OOXML edits written to a new package; unrelated parts are copied byte-for-byte."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from lxml import etree

from ..color import RGB
from ..errors import UnsafeModification
from ..model import FillTarget, ScrimAnchor
from .package import PptxPackage
from .xml import HLINK_COLOR_EXT_URI, NS, A, P, local, parse_xml, serialize_xml

FILL_TAGS = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}
_RPR_BEFORE_FILL = {"ln"}
_SPPR_BEFORE_FILL = {"xfrm", "custGeom", "prstGeom"}
_TCPR_BEFORE_FILL = {"lnL", "lnR", "lnT", "lnB", "lnTlToBr", "lnBlToTr", "cell3D"}


@dataclass(frozen=True)
class SetRunColor:
    part: str
    run_path: str
    color: RGB
    hyperlink: bool = False


@dataclass(frozen=True)
class SetFill:
    target: FillTarget
    color: RGB


@dataclass(frozen=True)
class InsertScrim:
    anchor: ScrimAnchor
    color: RGB
    alpha: float
    label: str


Operation = SetRunColor | SetFill | InsertScrim


def _solid_fill(color: RGB, alpha: float | None = None) -> etree._Element:
    fill = etree.Element(f"{A}solidFill")
    clr = etree.SubElement(fill, f"{A}srgbClr", val=color.hex)
    if alpha is not None and alpha < 1:
        etree.SubElement(clr, f"{A}alpha", val=str(int(round(alpha * 100_000))))
    return fill


def _replace_fill(container: etree._Element, fill: etree._Element, before: set[str]) -> None:
    for el in list(container):
        if local(el.tag) in FILL_TAGS:
            container.remove(el)
    index = 0
    for i, el in enumerate(container):
        if local(el.tag) in before:
            index = i + 1
    container.insert(index, fill)


def _set_run_color(run: etree._Element, color: RGB, hyperlink: bool) -> None:
    r_pr = run.find("a:rPr", NS)
    if r_pr is None:
        r_pr = etree.Element(f"{A}rPr")
        run.insert(0, r_pr)
    _replace_fill(r_pr, _solid_fill(color), _RPR_BEFORE_FILL)
    if hyperlink:
        hlink = r_pr.find("a:hlinkClick", NS)
        if hlink is not None:
            ext_lst = hlink.find("a:extLst", NS)
            if ext_lst is None:
                ext_lst = etree.SubElement(hlink, f"{A}extLst")
            if not any(e.get("uri") == HLINK_COLOR_EXT_URI for e in ext_lst.findall("a:ext", NS)):
                ext = etree.SubElement(ext_lst, f"{A}ext", uri=HLINK_COLOR_EXT_URI)
                etree.SubElement(
                    ext, f"{{{NS['ahyp']}}}hlinkClr", nsmap={"ahyp": NS["ahyp"]}, val="tx"
                )


def _set_background(c_sld: etree._Element, color: RGB) -> None:
    old = c_sld.find("p:bg", NS)
    if old is not None:
        c_sld.remove(old)
    bg = etree.Element(f"{P}bg")
    bg_pr = etree.SubElement(bg, f"{P}bgPr")
    bg_pr.append(_solid_fill(color))
    etree.SubElement(bg_pr, f"{A}effectLst")
    c_sld.insert(0, bg)


def _set_shape_fill(sp: etree._Element, color: RGB) -> None:
    sp_pr = sp.find("p:spPr", NS)
    if sp_pr is None:
        sp_pr = etree.Element(f"{P}spPr")
        nv = sp.find("p:nvSpPr", NS)
        sp.insert(list(sp).index(nv) + 1 if nv is not None else 0, sp_pr)
    _replace_fill(sp_pr, _solid_fill(color), _SPPR_BEFORE_FILL)


def _set_cell_fill(tc: etree._Element, color: RGB) -> None:
    tc_pr = tc.find("a:tcPr", NS)
    if tc_pr is None:
        tc_pr = etree.Element(f"{A}tcPr")
        tx = tc.find("a:txBody", NS)
        tc.insert(list(tc).index(tx) + 1 if tx is not None else 0, tc_pr)
    _replace_fill(tc_pr, _solid_fill(color), _TCPR_BEFORE_FILL)


def _next_shape_id(root: etree._Element) -> int:
    ids = [0]
    for el in root.iter(f"{P}cNvPr"):
        try:
            ids.append(int(el.get("id", "0")))
        except ValueError:
            continue
    return max(ids) + 1


def _scrim_shape(shape_id: int, op: InsertScrim) -> etree._Element:
    a = op.anchor
    sp = etree.Element(f"{P}sp")
    nv = etree.SubElement(sp, f"{P}nvSpPr")
    etree.SubElement(nv, f"{P}cNvPr", id=str(shape_id), name=op.label)
    etree.SubElement(nv, f"{P}cNvSpPr")
    etree.SubElement(nv, f"{P}nvPr")
    sp_pr = etree.SubElement(sp, f"{P}spPr")
    xfrm = etree.SubElement(sp_pr, f"{A}xfrm")
    etree.SubElement(xfrm, f"{A}off", x=str(a.off_x), y=str(a.off_y))
    etree.SubElement(xfrm, f"{A}ext", cx=str(a.ext_cx), cy=str(a.ext_cy))
    geom = etree.SubElement(sp_pr, f"{A}prstGeom", prst="rect")
    etree.SubElement(geom, f"{A}avLst")
    sp_pr.append(_solid_fill(op.color, op.alpha))
    ln = etree.SubElement(sp_pr, f"{A}ln")
    etree.SubElement(ln, f"{A}noFill")
    return sp


def apply_operations(package: PptxPackage, operations: list[Operation]) -> bytes:
    """Apply operations to fresh copies of the affected parts and build a new package."""
    roots: dict[str, etree._Element] = {}
    resolved: list[tuple[Operation, etree._Element]] = []

    def root_for(part: str) -> etree._Element:
        if part not in roots:
            roots[part] = parse_xml(package.parts[part])
        return roots[part]

    # Resolve every element first so insertions cannot shift later paths.
    for op in operations:
        if isinstance(op, SetRunColor):
            part, path = op.part, op.run_path
        elif isinstance(op, SetFill):
            part, path = op.target.part, op.target.path
        else:
            part, path = op.anchor.part, op.anchor.shape_path
        root = root_for(part)
        el = root if path == "." else root.find(path)
        if el is None:
            raise UnsafeModification("target_missing", f"Cannot locate {path} in {part}")
        resolved.append((op, el))

    for op, el in resolved:
        if isinstance(op, SetRunColor):
            if local(el.tag) not in ("r", "fld"):
                raise UnsafeModification("not_a_run", f"{op.run_path} is not a text run")
            _set_run_color(el, op.color, op.hyperlink)
        elif isinstance(op, SetFill):
            kind = op.target.kind
            if kind.endswith("_background"):
                _set_background(el, op.color)
            elif kind == "shape_fill":
                _set_shape_fill(el, op.color)
            elif kind == "cell_fill":
                _set_cell_fill(el, op.color)
            else:
                raise UnsafeModification("unknown_target", kind)
        else:
            parent = el.getparent()
            if parent is None:
                raise UnsafeModification("no_parent", "Scrim anchor has no parent")
            root = roots[op.anchor.part]
            parent.insert(list(parent).index(el), _scrim_shape(_next_shape_id(root), op))

    replaced = {part: serialize_xml(root) for part, root in roots.items()}
    return build_package(package, replaced)


def build_package(package: PptxPackage, replaced: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as out:
        for name in package.part_order:
            info = package.zip_infos[name]
            new_info = zipfile.ZipInfo(name, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            out.writestr(new_info, replaced.get(name, package.parts[name]))
    return buffer.getvalue()


def strip_text(package: PptxPackage) -> bytes:
    """Copy of the deck with all slide text removed, used to sample backgrounds."""
    replaced: dict[str, bytes] = {}
    for part in package.slide_parts:
        root = parse_xml(package.parts[part])
        changed = False
        for t in root.iter(f"{A}t"):
            parent = t.getparent()
            if parent is not None and local(parent.tag) in ("r", "fld") and t.text:
                t.text = ""
                changed = True
        if changed:
            replaced[part] = serialize_xml(root)
    return build_package(package, replaced)
