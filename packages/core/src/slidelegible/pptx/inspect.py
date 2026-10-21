"""Extract text runs with effective colors, sizes, and background observations.

Supported (documented in docs/supported-content.md):

* text in ``p:sp`` shapes and table cells, including grouped shapes;
* direct, paragraph, list-style, placeholder (layout/master), master text
  style, presentation default, and shape-style (``fontRef``) inheritance;
* theme colors through the effective color map and DrawingML transforms;
* slide/layout/master backgrounds, shape fills (``spPr`` and ``fillRef``),
  table cell fills (explicit and table styles), transparency, text highlight.

Charts, SmartArt, OLE objects and WordArt-style text are listed as
unsupported and never modified.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from lxml import etree

from ..color import RGB, composite
from ..model import (
    Background,
    BackgroundKind,
    Certainty,
    FillTarget,
    Inspection,
    Rect,
    ScrimAnchor,
    SlideInfo,
    TextRun,
    UnsupportedItem,
)
from ..policy import is_large_text
from .colors import ColorContext, ResolvedColor, read_clr_map, read_color_scheme
from .package import PptxPackage
from .xml import HLINK_COLOR_EXT_URI, NS, P, local

FILL_TAGS = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}
RECT_LIKE = {
    "rect",
    "roundRect",
    "snip1Rect",
    "snip2SameRect",
    "snip2DiagRect",
    "snipRoundRect",
    "round1Rect",
    "round2SameRect",
    "round2DiagRect",
    "flowChartProcess",
    "flowChartAlternateProcess",
    "plaque",
}
URI_TABLE = "http://schemas.openxmlformats.org/drawingml/2006/table"
URI_CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"
URI_DIAGRAM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
WHITE = RGB(1.0, 1.0, 1.0)
DEFAULT_INSETS = (91_440, 45_720, 91_440, 45_720)
EXCERPT_CHARS = 40


# --- small helpers -------------------------------------------------------------------


def element_path(el: etree._Element) -> str:
    return str(el.getroottree().getelementpath(el))


def _fill_child(container: etree._Element | None) -> etree._Element | None:
    if container is None:
        return None
    for el in container:
        if local(el.tag) in FILL_TAGS:
            return el
    return None


@dataclass
class Fill:
    kind: str  # none | solid | gradient | image | pattern | group | unknown
    color: ResolvedColor | None = None
    stops: list[RGB] = field(default_factory=list)
    source: str = ""


def read_fill(
    ctx: ColorContext, fill_el: etree._Element | None, ph_color: ResolvedColor | None = None
) -> Fill | None:
    if fill_el is None:
        return None
    tag = local(fill_el.tag)
    if tag == "noFill":
        return Fill("none", source="noFill")
    if tag == "solidFill":
        color = ctx.resolve_fill_color(fill_el, ph_color)
        if color is None:
            return Fill("unknown", source="solidFill (unresolved color)")
        return Fill("solid", color=color, source=f"solidFill {color.expression}")
    if tag == "gradFill":
        stops: list[RGB] = []
        for gs in fill_el.findall("a:gsLst/a:gs", NS):
            resolved = ctx.resolve_fill_color(gs, ph_color)
            if resolved is not None:
                stops.append(resolved.rgb)
        return Fill("gradient", stops=stops, source="gradFill")
    if tag == "pattFill":
        stops = []
        for name in ("a:fgClr", "a:bgClr"):
            resolved = ctx.resolve_fill_color(fill_el.find(name, NS), ph_color)
            if resolved is not None:
                stops.append(resolved.rgb)
        return Fill("pattern", stops=stops, source="pattFill")
    if tag == "blipFill":
        return Fill("image", source="blipFill")
    if tag == "grpFill":
        return Fill("group", source="grpFill")
    return None


@dataclass(frozen=True)
class Transform:
    sx: float = 1.0
    sy: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    def apply(self, x: float, y: float, w: float, h: float) -> Rect:
        return Rect(self.sx * x + self.tx, self.sy * y + self.ty, self.sx * w, self.sy * h)

    def child(self, xfrm: etree._Element | None) -> Transform:
        if xfrm is None:
            return self
        off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
        ch_off, ch_ext = xfrm.find("a:chOff", NS), xfrm.find("a:chExt", NS)
        if off is None or ext is None or ch_off is None or ch_ext is None:
            return self
        cx, cy = float(ch_ext.get("cx", "0")), float(ch_ext.get("cy", "0"))
        kx = float(ext.get("cx", "0")) / cx if cx else 1.0
        ky = float(ext.get("cy", "0")) / cy if cy else 1.0
        ox = float(off.get("x", "0")) - float(ch_off.get("x", "0")) * kx
        oy = float(off.get("y", "0")) - float(ch_off.get("y", "0")) * ky
        return Transform(self.sx * kx, self.sy * ky, self.sx * ox + self.tx, self.sy * oy + self.ty)


def _xfrm_values(xfrm: etree._Element | None) -> tuple[int, int, int, int, int] | None:
    if xfrm is None:
        return None
    off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    try:
        return (
            int(off.get("x", "0")),
            int(off.get("y", "0")),
            int(ext.get("cx", "0")),
            int(ext.get("cy", "0")),
            int(xfrm.get("rot", "0")),
        )
    except ValueError:
        return None


def _ph(el: etree._Element) -> etree._Element | None:
    for path in ("p:nvSpPr/p:nvPr/p:ph", "p:nvPicPr/p:nvPr/p:ph", "p:nvGraphicFramePr/p:nvPr/p:ph"):
        found = el.find(path, NS)
        if found is not None:
            return found
    return None


def _c_nv_pr(el: etree._Element) -> etree._Element | None:
    for path in (
        "p:nvSpPr/p:cNvPr",
        "p:nvPicPr/p:cNvPr",
        "p:nvGraphicFramePr/p:cNvPr",
        "p:nvGrpSpPr/p:cNvPr",
        "p:nvCxnSpPr/p:cNvPr",
    ):
        found = el.find(path, NS)
        if found is not None:
            return found
    return None


def _iter_tree(container: etree._Element) -> Iterator[etree._Element]:
    """Yield drawable children, unwrapping mc:AlternateContent via its fallback."""
    for el in container:
        if el.tag == f"{{{MC_NS}}}AlternateContent":
            branch = el.find(f"{{{MC_NS}}}Fallback")
            if branch is None:
                branch = el.find(f"{{{MC_NS}}}Choice")
            if branch is not None:
                yield from _iter_tree(branch)
            continue
        yield el


# --- placeholder lookup ------------------------------------------------------------


@dataclass
class PlaceholderIndex:
    by_idx: dict[str, etree._Element] = field(default_factory=dict)
    by_type: dict[str, etree._Element] = field(default_factory=dict)

    @classmethod
    def build(cls, root: etree._Element | None) -> PlaceholderIndex:
        index = cls()
        if root is None:
            return index
        for sp in root.iter(f"{P}sp"):
            ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
            if ph is None:
                continue
            idx = ph.get("idx")
            ph_type = ph.get("type", "obj")
            if idx is not None:
                index.by_idx.setdefault(idx, sp)
            index.by_type.setdefault(ph_type, sp)
        return index

    def find(self, ph_type: str, idx: str | None, *, master: bool = False) -> etree._Element | None:
        if master:
            mapped = {"ctrTitle": "title", "subTitle": "body", "obj": "body"}.get(ph_type, ph_type)
            found = self.by_type.get(mapped)
            if found is None and mapped not in ("title", "dt", "ftr", "sldNum"):
                found = self.by_type.get("body")
            return found
        if idx is not None and idx in self.by_idx:
            return self.by_idx[idx]
        found = self.by_type.get(ph_type)
        if found is None and ph_type == "ctrTitle":
            found = self.by_type.get("title")
        return found


# --- text style sources ------------------------------------------------------------


@dataclass
class StyleSource:
    label: str
    el: etree._Element | None = None
    color: ResolvedColor | None = None  # color-only sources (fontRef, table styles)
    bold: bool | None = None


def _lvl_def(list_style: etree._Element | None, lvl: int) -> etree._Element | None:
    if list_style is None:
        return None
    found = list_style.find(f"a:lvl{lvl + 1}pPr/a:defRPr", NS)
    if found is None and local(list_style.tag) == "defaultTextStyle":
        found = list_style.find("a:defPPr/a:defRPr", NS)
    return found


@dataclass
class TextProps:
    color: ResolvedColor | None
    color_source: str
    fill_kind: str  # solid | none | gradient | unknown
    size_pt: float | None
    size_basis: str
    bold: bool
    color_certain: bool = True


def _bool_attr(value: str | None) -> bool | None:
    if value is None:
        return None
    return value in ("1", "true", "on")


def resolve_text_props(
    ctx: ColorContext, sources: list[StyleSource], default_color: ResolvedColor | None
) -> TextProps:
    color: ResolvedColor | None = None
    color_source = "default"
    fill_kind = "solid"
    for src in sources:
        if src.el is not None:
            fill = _fill_child(src.el)
            if fill is None:
                continue
            tag = local(fill.tag)
            if tag == "solidFill":
                color = ctx.resolve_fill_color(fill)
                color_source = src.label
                fill_kind = "solid" if color is not None else "unknown"
            elif tag == "noFill":
                fill_kind = "none"
                color_source = src.label
            else:
                fill_kind = "gradient" if tag == "gradFill" else "unknown"
                color_source = src.label
            break
        if src.color is not None:
            color = src.color
            color_source = src.label
            break
    if color is None and fill_kind == "solid":
        color = default_color
        color_source = "default"

    size: float | None = None
    size_basis = "default"
    for src in sources:
        if src.el is not None and src.el.get("sz"):
            try:
                size = int(src.el.get("sz", "1800")) / 100
            except ValueError:
                continue
            size_basis = src.label
            break
    if size is None:
        size = 18.0

    bold = False
    for src in sources:
        value = _bool_attr(src.el.get("b")) if src.el is not None else src.bold
        if value is not None:
            bold = value
            break
    return TextProps(color, color_source, fill_kind, size, size_basis, bold)


# --- layers ------------------------------------------------------------------------


@dataclass
class Layer:
    rect: Rect | None  # None = covers the whole slide
    fill: Fill
    rect_like: bool
    label: str
    target: FillTarget | None
    key: str  # part#path, used to recognise a run's own shape

    @property
    def is_background(self) -> bool:
        return self.rect is None


@dataclass
class ShapeEntry:
    el: etree._Element
    part: str
    origin: str  # master | layout | slide
    transform: Transform
    group_fill: Fill | None


@dataclass
class _Theme:
    ctx: ColorContext
    fill_styles: list[etree._Element]
    bg_fill_styles: list[etree._Element]


class Inspector:
    def __init__(self, package: PptxPackage, filename: str = "presentation.pptx") -> None:
        self.pkg = package
        self.filename = filename
        self.warnings: list[str] = []
        self.unsupported: list[UnsupportedItem] = []
        self._table_styles: dict[str, etree._Element] | None = None

    # -- entry point --------------------------------------------------------------
    def inspect(self) -> Inspection:
        width, height = self.pkg.slide_size
        slides: list[SlideInfo] = []
        runs: list[TextRun] = []
        for number, slide_part in enumerate(self.pkg.slide_parts, start=1):
            layout = self.pkg.layout_for(slide_part)
            master = self.pkg.master_for(layout) if layout else None
            info = SlideInfo(number, slide_part, layout, master, width, height)
            slide_root = self.pkg.xml(slide_part)
            info.hidden = slide_root.get("show") in ("0", "false")
            theme = self._theme(master, slide_root)
            info.theme_dark = theme.ctx.scheme.get("dk1", info.theme_dark)
            info.theme_light = theme.ctx.scheme.get("lt1", info.theme_light)
            slides.append(info)
            try:
                runs.extend(self._inspect_slide(number, slide_part, layout, master))
            except (etree.XMLSyntaxError, KeyError, ValueError) as exc:
                self.warnings.append(f"slide {number}: skipped ({exc})")
        return Inspection(
            fingerprint=self.pkg.fingerprint,
            filename=self.filename,
            slide_width=width,
            slide_height=height,
            slides=slides,
            runs=runs,
            unsupported=self.unsupported,
            warnings=self.warnings,
        )

    # -- theme and context --------------------------------------------------------
    def _theme(self, master: str | None, slide_root: etree._Element) -> _Theme:
        scheme: dict[str, RGB] = {}
        fills: list[etree._Element] = []
        bg_fills: list[etree._Element] = []
        clr_map = None
        if master:
            theme_part = self.pkg.theme_for(master)
            if theme_part and self.pkg.has_part(theme_part):
                theme_root = self.pkg.xml(theme_part)
                scheme = read_color_scheme(theme_root)
                fmt = theme_root.find("a:themeElements/a:fmtScheme", NS)
                if fmt is not None:
                    fill_lst = fmt.find("a:fillStyleLst", NS)
                    bg_lst = fmt.find("a:bgFillStyleLst", NS)
                    fills = list(fill_lst) if fill_lst is not None else []
                    bg_fills = list(bg_lst) if bg_lst is not None else []
            clr_map = read_clr_map(self.pkg.xml(master).find("p:clrMap", NS))
        override = read_clr_map(slide_root.find("p:clrMapOvr/a:overrideClrMapping", NS))
        ctx = ColorContext(scheme)
        if override is not None:
            ctx.clr_map = override
        elif clr_map is not None:
            ctx.clr_map = clr_map
        if not scheme:
            self.warnings.append("theme colors missing; using white/black defaults")
            ctx.scheme = {"lt1": WHITE, "dk1": RGB(0, 0, 0)}
        return _Theme(ctx, fills, bg_fills)

    def _style_fill(
        self, theme: _Theme, idx: int, ph_color: ResolvedColor | None, label: str
    ) -> Fill | None:
        if idx in (0, 1000):
            return Fill("none", source=f"{label} idx={idx}")
        styles = theme.bg_fill_styles if idx > 1000 else theme.fill_styles
        pos = idx - 1001 if idx > 1000 else idx - 1
        if not 0 <= pos < len(styles):
            return Fill("unknown", source=f"{label} idx={idx} (missing)")
        fill = read_fill(theme.ctx, styles[pos], ph_color)
        if fill is not None:
            fill.source = f"theme {label} idx={idx}: {fill.source}"
        return fill

    # -- backgrounds --------------------------------------------------------------
    def _background_layer(self, theme: _Theme, chain: list[tuple[str, str]]) -> Layer:
        for kind, part in chain:
            root = self.pkg.xml(part)
            c_sld = root.find("p:cSld", NS)
            bg = c_sld.find("p:bg", NS) if c_sld is not None else None
            if bg is None or c_sld is None:
                continue
            label = {
                "slide_background": "slide background",
                "layout_background": "layout background",
                "master_background": "master background",
            }[kind]
            fill: Fill | None = None
            bg_pr = bg.find("p:bgPr", NS)
            bg_ref = bg.find("p:bgRef", NS)
            if bg_pr is not None:
                fill = read_fill(theme.ctx, _fill_child(bg_pr))
            elif bg_ref is not None:
                ph_color = theme.ctx.resolve_fill_color(bg_ref)
                try:
                    idx = int(bg_ref.get("idx", "0"))
                except ValueError:
                    idx = 0
                fill = self._style_fill(theme, idx, ph_color, "bgRef")
            if fill is None:
                fill = Fill("unknown", source="unreadable background")
            target = None
            if fill.kind == "solid" and fill.color is not None:
                target = FillTarget(kind, part, element_path(c_sld), label, fill.color.rgb.opaque())
            return Layer(None, fill, True, f"{label} ({fill.source})", target, f"{part}#bg")
        return Layer(
            None,
            Fill("solid", ResolvedColor(WHITE, "default white")),
            True,
            "no background (white)",
            None,
            "none#bg",
        )

    # -- shapes -------------------------------------------------------------------
    def _flatten(
        self,
        container: etree._Element,
        part: str,
        origin: str,
        transform: Transform,
        group_fill: Fill | None,
        theme: _Theme,
    ) -> Iterator[ShapeEntry]:
        for el in _iter_tree(container):
            tag = local(el.tag)
            c_nv = _c_nv_pr(el)
            if c_nv is not None and c_nv.get("hidden") in ("1", "true"):
                continue
            if tag == "grpSp":
                grp_pr = el.find("p:grpSpPr", NS)
                fill = read_fill(theme.ctx, _fill_child(grp_pr)) or group_fill
                yield from self._flatten(
                    el,
                    part,
                    origin,
                    transform.child(grp_pr.find("a:xfrm", NS) if grp_pr is not None else None),
                    fill,
                    theme,
                )
            elif tag in ("sp", "pic", "graphicFrame"):
                yield ShapeEntry(el, part, origin, transform, group_fill)

    def _shape_rect(
        self, entry: ShapeEntry, inherited: list[etree._Element]
    ) -> tuple[Rect | None, int, tuple[int, int, int, int] | None]:
        tag = local(entry.el.tag)
        xfrm = entry.el.find("p:xfrm" if tag == "graphicFrame" else "p:spPr/a:xfrm", NS)
        values = _xfrm_values(xfrm)
        if values is None:
            for parent in inherited:
                values = _xfrm_values(parent.find("p:spPr/a:xfrm", NS))
                if values is not None:
                    break
        if values is None:
            return None, 0, None
        x, y, cx, cy, rot = values
        return entry.transform.apply(x, y, cx, cy), rot, (x, y, cx, cy)

    def _shape_fill(
        self, theme: _Theme, entry: ShapeEntry, inherited: list[etree._Element]
    ) -> Fill:
        tag = local(entry.el.tag)
        if tag == "pic":
            return Fill("image", source="picture")
        if tag == "graphicFrame":
            return Fill("unknown", source="graphic frame")
        for sp in [entry.el, *inherited]:
            fill = read_fill(theme.ctx, _fill_child(sp.find("p:spPr", NS)))
            if fill is not None:
                if fill.kind == "group":
                    return entry.group_fill or Fill("none", source="grpFill")
                return fill
        fill_ref = entry.el.find("p:style/a:fillRef", NS)
        if fill_ref is not None:
            ph_color = theme.ctx.resolve_fill_color(fill_ref)
            try:
                idx = int(fill_ref.get("idx", "0"))
            except ValueError:
                idx = 0
            styled = self._style_fill(theme, idx, ph_color, "fillRef")
            if styled is not None:
                return styled
        return Fill("none", source="no fill")

    def _rect_like(self, el: etree._Element) -> bool:
        if local(el.tag) in ("pic", "graphicFrame"):
            return True
        geom = el.find("p:spPr/a:prstGeom", NS)
        if geom is None:
            return el.find("p:spPr/a:custGeom", NS) is None
        return geom.get("prst", "rect") in RECT_LIKE

    def _shape_label(self, el: etree._Element) -> str:
        c_nv = _c_nv_pr(el)
        return (c_nv.get("name") if c_nv is not None else None) or local(el.tag)

    def _make_layer(
        self, theme: _Theme, entry: ShapeEntry, inherited: list[etree._Element]
    ) -> Layer | None:
        tag = local(entry.el.tag)
        if tag == "graphicFrame":
            uri = self._graphic_uri(entry.el)
            if uri == URI_TABLE:
                return None  # tables are handled cell by cell
        rect, _rot, _ = self._shape_rect(entry, inherited)
        fill = self._shape_fill(theme, entry, inherited)
        name = self._shape_label(entry.el)
        target = None
        if fill.kind == "solid" and fill.color is not None and tag == "sp":
            target = FillTarget(
                "shape_fill",
                entry.part,
                element_path(entry.el),
                f"shape '{name}' fill",
                fill.color.rgb.opaque(),
            )
        origin = "" if entry.origin == "slide" else f" on {entry.origin}"
        return Layer(
            rect,
            fill,
            self._rect_like(entry.el),
            f"shape '{name}'{origin} ({fill.source})",
            target,
            f"{entry.part}#{element_path(entry.el)}",
        )

    @staticmethod
    def _graphic_uri(el: etree._Element) -> str:
        data = el.find("a:graphic/a:graphicData", NS)
        return data.get("uri", "") if data is not None else ""

    # -- per slide ----------------------------------------------------------------
    def _inspect_slide(
        self, number: int, slide_part: str, layout: str | None, master: str | None
    ) -> list[TextRun]:
        slide_root = self.pkg.xml(slide_part)
        theme = self._theme(master, slide_root)
        layout_root = self.pkg.xml(layout) if layout and self.pkg.has_part(layout) else None
        master_root = self.pkg.xml(master) if master and self.pkg.has_part(master) else None
        layout_ph = PlaceholderIndex.build(layout_root)
        master_ph = PlaceholderIndex.build(master_root)

        bg_chain = [("slide_background", slide_part)]
        if layout_root is not None and layout:
            bg_chain.append(("layout_background", layout))
        if master_root is not None and master:
            bg_chain.append(("master_background", master))
        background = self._background_layer(theme, bg_chain)

        show_master = slide_root.get("showMasterSp") not in ("0", "false")
        layout_shows_master = layout_root is None or layout_root.get("showMasterSp") not in (
            "0",
            "false",
        )
        layers: list[Layer] = []
        if show_master and layout_shows_master and master_root is not None and master:
            layers.extend(self._non_ph_layers(theme, master_root, master, "master"))
        if show_master and layout_root is not None and layout:
            layers.extend(self._non_ph_layers(theme, layout_root, layout, "layout"))
        base_count = len(layers)

        sp_tree = slide_root.find("p:cSld/p:spTree", NS)
        if sp_tree is None:
            return []
        entries = list(self._flatten(sp_tree, slide_part, "slide", Transform(), None, theme))
        slide_layers: list[tuple[ShapeEntry, Layer | None, list[etree._Element]]] = []
        for entry in entries:
            inherited = self._inherited_ph(entry.el, layout_ph, master_ph)
            layer = self._make_layer(theme, entry, inherited)
            slide_layers.append((entry, layer, inherited))
            if layer is not None:
                layers.append(layer)

        runs: list[TextRun] = []
        seen_ids: set[str] = set()
        layer_pos = base_count
        for entry, layer, inherited in slide_layers:
            below = list(reversed(layers[:layer_pos]))
            if layer is not None:
                layer_pos += 1
            tag = local(entry.el.tag)
            name = self._shape_label(entry.el)
            if tag == "graphicFrame":
                uri = self._graphic_uri(entry.el)
                if uri == URI_TABLE:
                    runs.extend(
                        self._table_runs(
                            number,
                            slide_part,
                            entry,
                            theme,
                            below,
                            background,
                            master_root,
                            seen_ids,
                        )
                    )
                elif uri == URI_CHART:
                    self.unsupported.append(
                        UnsupportedItem(number, name, "chart", "chart text is not analyzed")
                    )
                elif uri == URI_DIAGRAM:
                    self.unsupported.append(
                        UnsupportedItem(number, name, "smartart", "SmartArt text is not analyzed")
                    )
                else:
                    self.unsupported.append(
                        UnsupportedItem(number, name, "embedded", uri or "graphic frame")
                    )
                continue
            if tag != "sp" or entry.el.find("p:txBody", NS) is None:
                continue
            runs.extend(
                self._shape_runs(
                    number,
                    slide_part,
                    entry,
                    layer,
                    inherited,
                    theme,
                    below,
                    background,
                    master_root,
                    seen_ids,
                )
            )
        return runs

    def _non_ph_layers(
        self, theme: _Theme, root: etree._Element, part: str, origin: str
    ) -> list[Layer]:
        tree = root.find("p:cSld/p:spTree", NS)
        if tree is None:
            return []
        result: list[Layer] = []
        for entry in self._flatten(tree, part, origin, Transform(), None, theme):
            if _ph(entry.el) is not None:
                continue
            layer = self._make_layer(theme, entry, [])
            if layer is not None:
                result.append(layer)
        return result

    def _inherited_ph(
        self, el: etree._Element, layout_ph: PlaceholderIndex, master_ph: PlaceholderIndex
    ) -> list[etree._Element]:
        ph = _ph(el)
        if ph is None:
            return []
        ph_type = ph.get("type", "obj")
        idx = ph.get("idx")
        result: list[etree._Element] = []
        layout_sp = layout_ph.find(ph_type, idx)
        if layout_sp is not None:
            result.append(layout_sp)
            lph = _ph(layout_sp)
            ph_type = lph.get("type", ph_type) if lph is not None else ph_type
        master_sp = master_ph.find(ph_type, idx, master=True)
        if master_sp is not None:
            result.append(master_sp)
        return result

    # -- text in shapes -----------------------------------------------------------
    def _text_sources(
        self,
        el: etree._Element,
        inherited: list[etree._Element],
        theme: _Theme,
        master_root: etree._Element | None,
        lvl: int,
        para: etree._Element,
    ) -> list[StyleSource]:
        sources: list[StyleSource] = []
        p_pr = para.find("a:pPr", NS)
        if p_pr is not None:
            sources.append(StyleSource("paragraph", p_pr.find("a:defRPr", NS)))
        sources.append(
            StyleSource("shape list style", _lvl_def(el.find("p:txBody/a:lstStyle", NS), lvl))
        )
        ph = _ph(el)
        if ph is not None:
            for sp in inherited:
                in_master = master_root is not None and sp.getroottree().getroot() is master_root
                label = "master placeholder" if in_master else "layout placeholder"
                sources.append(
                    StyleSource(label, _lvl_def(sp.find("p:txBody/a:lstStyle", NS), lvl))
                )
            ph_type = ph.get("type", "obj")
            for sp in inherited:
                inner = _ph(sp)
                if inner is not None and inner.get("type"):
                    ph_type = inner.get("type", ph_type)
            style_name = (
                "titleStyle"
                if ph_type in ("title", "ctrTitle")
                else "otherStyle"
                if ph_type in ("dt", "ftr", "sldNum", "hdr")
                else "bodyStyle"
            )
            if master_root is not None:
                sources.append(
                    StyleSource(
                        f"master {style_name}",
                        _lvl_def(master_root.find(f"p:txStyles/p:{style_name}", NS), lvl),
                    )
                )
        else:
            font_ref = el.find("p:style/a:fontRef", NS)
            if font_ref is not None:
                color = theme.ctx.resolve_fill_color(font_ref)
                if color is not None:
                    sources.append(StyleSource("shape style (fontRef)", color=color))
            if master_root is not None:
                sources.append(
                    StyleSource(
                        "master otherStyle",
                        _lvl_def(master_root.find("p:txStyles/p:otherStyle", NS), lvl),
                    )
                )
        pres = self.pkg.xml(self.pkg.presentation_part)
        sources.append(
            StyleSource("presentation default", _lvl_def(pres.find("p:defaultTextStyle", NS), lvl))
        )
        return sources

    def _body_pr_values(
        self, el: etree._Element, inherited: list[etree._Element]
    ) -> tuple[tuple[int, int, int, int], float, bool]:
        insets = list(DEFAULT_INSETS)
        names = ("lIns", "tIns", "rIns", "bIns")
        found = [False] * 4
        font_scale = 1.0
        scale_found = False
        warp = False
        for sp in [el, *inherited]:
            body = sp.find("p:txBody/a:bodyPr", NS)
            if body is None:
                continue
            for i, name in enumerate(names):
                if not found[i] and body.get(name) is not None:
                    try:
                        insets[i] = int(body.get(name, "0"))
                        found[i] = True
                    except ValueError:
                        pass
            auto = body.find("a:normAutofit", NS)
            if not scale_found and auto is not None:
                scale_found = True
                try:
                    font_scale = int(auto.get("fontScale", "100000")) / 100_000
                except ValueError:
                    font_scale = 1.0
            warp_el = body.find("a:prstTxWarp", NS)
            if (
                sp is el
                and warp_el is not None
                and warp_el.get("prst", "textNoShape") != "textNoShape"
            ):
                warp = True
        return (insets[0], insets[1], insets[2], insets[3]), font_scale, warp

    def _shape_runs(
        self,
        number: int,
        slide_part: str,
        entry: ShapeEntry,
        own_layer: Layer | None,
        inherited: list[etree._Element],
        theme: _Theme,
        below: list[Layer],
        background: Layer,
        master_root: etree._Element | None,
        seen_ids: set[str],
    ) -> list[TextRun]:
        el = entry.el
        name = self._shape_label(el)
        c_nv = _c_nv_pr(el)
        shape_id = c_nv.get("id", "0") if c_nv is not None else "0"
        rect, rot, local_xfrm = self._shape_rect(entry, inherited)
        insets, font_scale, warp = self._body_pr_values(el, inherited)
        text_area = rect.inset(*insets) if rect is not None else None
        if warp:
            self.unsupported.append(
                UnsupportedItem(number, name, "wordart", "warped text is not modified")
            )
        stack = ([own_layer] if own_layer is not None else []) + below
        shape_bg = self._walk(stack, background, text_area, own_layer.key if own_layer else None)
        if rot:
            shape_bg.note = "rotated shape: background estimated from its unrotated box"
            if shape_bg.certainty == Certainty.EXACT:
                shape_bg.certainty = Certainty.DERIVED
        anchor = None
        if local_xfrm is not None and el.getparent() is not None:
            anchor = ScrimAnchor(slide_part, element_path(el), *local_xfrm)

        runs: list[TextRun] = []
        paragraphs = el.findall("p:txBody/a:p", NS)
        for p_index, para in enumerate(paragraphs):
            p_pr = para.find("a:pPr", NS)
            try:
                lvl = int(p_pr.get("lvl", "0")) if p_pr is not None else 0
            except ValueError:
                lvl = 0
            sources_tail = self._text_sources(el, inherited, theme, master_root, lvl, para)
            r_index = -1
            for run_el in para:
                if local(run_el.tag) not in ("r", "fld"):
                    continue
                r_index += 1
                t_el = run_el.find("a:t", NS)
                text = (t_el.text or "") if t_el is not None else ""
                if not text.strip():
                    continue
                run_id = self._unique(f"s{number}-sh{shape_id}-p{p_index}-r{r_index}", seen_ids)
                runs.append(
                    self._build_run(
                        run_id,
                        number,
                        slide_part,
                        el,
                        run_el,
                        name,
                        shape_id,
                        text,
                        p_index,
                        r_index,
                        None,
                        sources_tail,
                        theme,
                        font_scale,
                        text_area,
                        shape_bg,
                        anchor,
                        "wordart" if warp else None,
                    )
                )
        return runs

    @staticmethod
    def _unique(candidate: str, seen: set[str]) -> str:
        value = candidate
        n = 2
        while value in seen:
            value = f"{candidate}-{n}"
            n += 1
        seen.add(value)
        return value

    def _build_run(
        self,
        run_id: str,
        number: int,
        slide_part: str,
        shape_el: etree._Element,
        run_el: etree._Element,
        name: str,
        shape_id: str,
        text: str,
        p_index: int,
        r_index: int,
        cell: tuple[int, int] | None,
        sources_tail: list[StyleSource],
        theme: _Theme,
        font_scale: float,
        text_area: Rect | None,
        shape_bg: Background,
        anchor: ScrimAnchor | None,
        unsupported: str | None,
    ) -> TextRun:
        r_pr = run_el.find("a:rPr", NS)
        sources = [StyleSource("run", r_pr), *sources_tail]
        default_color = theme.ctx.scheme_color("tx1")
        default = (
            ResolvedColor(default_color[0], "schemeClr tx1 (default)", default_color[1])
            if default_color
            else None
        )
        props = resolve_text_props(theme.ctx, sources, default)
        color_certain = props.color is not None and props.fill_kind == "solid"
        color = props.color.rgb if props.color is not None else RGB(0, 0, 0)
        expr = props.color.expression if props.color is not None else "unresolved"
        source = props.color_source
        if any(s.label == "table style (unresolved)" for s in sources_tail) and source in (
            "default",
            "presentation default",
            "master otherStyle",
        ):
            color_certain = False

        hyperlink = False
        hlink = r_pr.find("a:hlinkClick", NS) if r_pr is not None else None
        if hlink is not None and hlink.get(f"{{{NS['r']}}}id"):
            hyperlink = True
            uses_text = any(
                ext.get("uri") == HLINK_COLOR_EXT_URI
                and ext.find(f"{{{NS['ahyp']}}}hlinkClr", None) is not None
                for ext in hlink.findall("a:extLst/a:ext", NS)
            )
            if not uses_text:
                found = theme.ctx.scheme_color("hlink")
                if found is not None:
                    color = found[0].with_alpha(color.alpha)
                    expr = "theme hyperlink color (hlink)"
                    source = "hyperlink"

        if props.fill_kind == "gradient":
            unsupported = unsupported or "gradient_text"
        elif props.fill_kind == "none":
            unsupported = unsupported or "invisible_text"
        elif props.fill_kind == "unknown":
            unsupported = unsupported or "unresolved_text_fill"

        size = props.size_pt * font_scale if props.size_pt is not None else None
        background = shape_bg
        highlight = r_pr.find("a:highlight", NS) if r_pr is not None else None
        if highlight is not None:
            hl = theme.ctx.resolve_fill_color(highlight)
            if hl is not None:
                background = Background(
                    BackgroundKind.SOLID,
                    Certainty.EXACT,
                    composite(hl.rgb, shape_bg.color or WHITE) if hl.rgb.alpha < 1 else hl.rgb,
                    layers=[f"text highlight ({hl.expression})"],
                )
        excerpt = text if len(text) <= EXCERPT_CHARS else text[: EXCERPT_CHARS - 1] + "…"
        return TextRun(
            id=run_id,
            slide_index=number,
            slide_part=slide_part,
            run_path=element_path(run_el),
            shape_id=shape_id,
            shape_name=name,
            shape_path=element_path(shape_el),
            excerpt=excerpt,
            paragraph=p_index,
            run=r_index,
            cell=cell,
            size_pt=round(size, 2) if size is not None else None,
            size_basis=props.size_basis,
            bold=props.bold,
            color=color,
            color_expr=expr,
            color_source=source,
            color_certain=color_certain,
            hyperlink=hyperlink,
            text_area=text_area,
            background=background,
            unsupported=unsupported,
            scrim_anchor=anchor,
        )

    # -- background walk ----------------------------------------------------------
    def _walk(
        self, stack: list[Layer], background: Layer, area: Rect | None, own_key: str | None
    ) -> Background:
        transparent: list[tuple[RGB, str]] = []
        evidence: list[str] = []
        has_image = False
        for layer in [*stack, background]:
            if layer.fill.kind == "none":
                continue
            own = layer.key == own_key
            if not layer.is_background and not own:
                if area is None or layer.rect is None:
                    continue
                if not layer.rect.intersects(area):
                    continue
                full = layer.rect.contains(area) and layer.rect_like
                if not full:
                    evidence.append(f"partly overlapped by {layer.label}")
                    has_image = has_image or layer.fill.kind == "image"
                    return Background(
                        BackgroundKind.COMPLEX,
                        Certainty.UNKNOWN,
                        layers=evidence,
                        has_image=has_image,
                        needs_render=True,
                        note="text area is partly covered by another shape",
                    )
            evidence.append(layer.label)
            kind = layer.fill.kind
            if kind == "solid" and layer.fill.color is not None:
                rgb = layer.fill.color.rgb
                if rgb.alpha < 0.999:
                    transparent.append((rgb, layer.label))
                    continue
                color = rgb
                for top, _ in reversed(transparent):
                    color = composite(top, color)
                certainty = Certainty.EXACT if not transparent else Certainty.DERIVED
                editable = layer.target if not transparent else None
                if not transparent and layer.is_background and layer.target is None:
                    certainty = Certainty.DERIVED
                return Background(
                    BackgroundKind.SOLID,
                    certainty,
                    color.opaque(),
                    layers=evidence,
                    editable=editable,
                )
            if kind in ("gradient", "pattern"):
                samples = []
                for stop in layer.fill.stops:
                    color = stop.opaque()
                    for top, _ in reversed(transparent):
                        color = composite(top, color)
                    samples.append(color.opaque())
                return Background(
                    BackgroundKind.GRADIENT,
                    Certainty.DERIVED if samples else Certainty.UNKNOWN,
                    samples=samples,
                    layers=evidence,
                    needs_render=True,
                    note="gradient: worst case over its color stops",
                )
            if kind == "image":
                return Background(
                    BackgroundKind.IMAGE,
                    Certainty.UNKNOWN,
                    layers=evidence,
                    has_image=True,
                    needs_render=True,
                    note="image behind text",
                )
            return Background(
                BackgroundKind.COMPLEX,
                Certainty.UNKNOWN,
                layers=evidence,
                needs_render=True,
                note="background could not be resolved from the file",
            )
        return Background(BackgroundKind.SOLID, Certainty.DERIVED, WHITE, layers=evidence)

    # -- tables -------------------------------------------------------------------
    def _table_style(self, style_id: str) -> etree._Element | None:
        if self._table_styles is None:
            self._table_styles = {}
            part = self.pkg.table_styles_part
            if part and self.pkg.has_part(part):
                for style in self.pkg.xml(part).findall("a:tblStyle", NS):
                    sid = style.get("styleId")
                    if sid:
                        self._table_styles[sid] = style
        return self._table_styles.get(style_id)

    @staticmethod
    def _regions(tbl_pr: etree._Element | None, r: int, c: int, rows: int, cols: int) -> list[str]:
        """Table style regions for a cell, lowest priority first."""
        flags = {
            k: (tbl_pr is not None and tbl_pr.get(k) in ("1", "true"))
            for k in ("firstRow", "lastRow", "firstCol", "lastCol", "bandRow", "bandCol")
        }
        regions = ["wholeTbl"]
        if flags["bandCol"]:
            start = 1 if flags["firstCol"] else 0
            if c >= start:
                regions.append("band1V" if (c - start) % 2 == 0 else "band2V")
        if flags["bandRow"]:
            start = 1 if flags["firstRow"] else 0
            if r >= start:
                regions.append("band1H" if (r - start) % 2 == 0 else "band2H")
        if flags["lastCol"] and c == cols - 1:
            regions.append("lastCol")
        if flags["firstCol"] and c == 0:
            regions.append("firstCol")
        if flags["lastRow"] and r == rows - 1:
            regions.append("lastRow")
        if flags["firstRow"] and r == 0:
            regions.append("firstRow")
        return regions

    def _table_style_props(
        self, theme: _Theme, style: etree._Element, regions: list[str]
    ) -> tuple[Fill | None, ResolvedColor | None, bool | None]:
        fill: Fill | None = None
        color: ResolvedColor | None = None
        bold: bool | None = None
        for region in regions:
            reg = style.find(f"a:{region}", NS)
            if reg is None:
                continue
            tc_style = reg.find("a:tcStyle", NS)
            if tc_style is not None:
                fill_el = tc_style.find("a:fill", NS)
                if fill_el is not None:
                    found = read_fill(theme.ctx, _fill_child(fill_el))
                    if found is not None:
                        fill = found
                fill_ref = tc_style.find("a:fillRef", NS)
                if fill_ref is not None:
                    ph_color = theme.ctx.resolve_fill_color(fill_ref)
                    try:
                        idx = int(fill_ref.get("idx", "0"))
                    except ValueError:
                        idx = 0
                    styled = self._style_fill(theme, idx, ph_color, "table fillRef")
                    if styled is not None:
                        fill = styled
            tx = reg.find("a:tcTxStyle", NS)
            if tx is not None:
                for el in tx:
                    name = local(el.tag)
                    if name in ("srgbClr", "schemeClr", "sysClr", "prstClr", "scrgbClr", "hslClr"):
                        resolved = theme.ctx.resolve(el)
                        if resolved is not None:
                            color = resolved
                    elif name == "fontRef":
                        resolved = theme.ctx.resolve_fill_color(el)
                        if resolved is not None:
                            color = resolved
                b = tx.get("b")
                if b in ("on", "off"):
                    bold = b == "on"
        return fill, color, bold

    def _table_runs(
        self,
        number: int,
        slide_part: str,
        entry: ShapeEntry,
        theme: _Theme,
        below: list[Layer],
        background: Layer,
        master_root: etree._Element | None,
        seen_ids: set[str],
    ) -> list[TextRun]:
        el = entry.el
        name = self._shape_label(el)
        c_nv = _c_nv_pr(el)
        shape_id = c_nv.get("id", "0") if c_nv is not None else "0"
        tbl = el.find("a:graphic/a:graphicData/a:tbl", NS)
        if tbl is None:
            return []
        frame, _rot, _ = self._shape_rect(entry, [])
        tbl_pr = tbl.find("a:tblPr", NS)
        style_id_el = tbl_pr.find("a:tableStyleId", NS) if tbl_pr is not None else None
        style = None
        style_unresolved = False
        if style_id_el is not None and style_id_el.text:
            style = self._table_style(style_id_el.text.strip())
            style_unresolved = style is None
        widths = [int(g.get("w", "0")) for g in tbl.findall("a:tblGrid/a:gridCol", NS)]
        rows = tbl.findall("a:tr", NS)
        heights = [int(r.get("h", "0")) for r in rows]
        if style_unresolved:
            self.warnings.append(
                f"slide {number}: table '{name}' uses a table style that is not stored "
                "in the file; cell colors are estimated"
            )
        pres = self.pkg.xml(self.pkg.presentation_part)
        runs: list[TextRun] = []
        for r_i, tr in enumerate(rows):
            for c_i, tc in enumerate(tr.findall("a:tc", NS)):
                if tc.get("hMerge") in ("1", "true") or tc.get("vMerge") in ("1", "true"):
                    continue
                span_c = int(tc.get("gridSpan", "1"))
                span_r = int(tc.get("rowSpan", "1"))
                cell_rect = None
                if frame is not None and widths:
                    sx = frame.w / max(sum(widths), 1)
                    sy = frame.h / max(sum(heights), 1) if sum(heights) else 1.0
                    x = frame.x + sum(widths[:c_i]) * sx
                    y = frame.y + sum(heights[:r_i]) * sy
                    w = sum(widths[c_i : c_i + span_c]) * sx
                    h = sum(heights[r_i : r_i + span_r]) * sy
                    tc_pr = tc.find("a:tcPr", NS)
                    margins = [
                        int(tc_pr.get(k, str(d))) if tc_pr is not None else d
                        for k, d in (
                            ("marL", 91_440),
                            ("marT", 45_720),
                            ("marR", 91_440),
                            ("marB", 45_720),
                        )
                    ]
                    cell_rect = Rect(x, y, w, h).inset(*margins)
                regions = self._regions(tbl_pr, r_i, c_i, len(rows), len(widths))
                style_fill, style_color, style_bold = (
                    self._table_style_props(theme, style, regions)
                    if style is not None
                    else (None, None, None)
                )
                cell_fill = read_fill(theme.ctx, _fill_child(tc.find("a:tcPr", NS)))
                fill = cell_fill or style_fill
                cell_key = f"{slide_part}#{element_path(tc)}"
                stack: list[Layer] = []
                if fill is not None:
                    target = None
                    if fill.kind == "solid" and fill.color is not None:
                        target = FillTarget(
                            "cell_fill",
                            slide_part,
                            element_path(tc),
                            f"table '{name}' cell ({r_i + 1},{c_i + 1})",
                            fill.color.rgb.opaque(),
                        )
                    stack.append(
                        Layer(
                            cell_rect, fill, True, f"table cell ({fill.source})", target, cell_key
                        )
                    )
                if style_unresolved and cell_fill is None:
                    cell_bg = Background(
                        BackgroundKind.COMPLEX,
                        Certainty.UNKNOWN,
                        layers=["table style not stored in file"],
                        needs_render=True,
                        note="table style missing from file",
                    )
                else:
                    cell_bg = self._walk(stack + below, background, cell_rect, cell_key)
                sources_tail_base: list[StyleSource] = []
                if style_color is not None or style_bold is not None:
                    sources_tail_base.append(
                        StyleSource("table style", color=style_color, bold=style_bold)
                    )
                if style_unresolved:
                    sources_tail_base.append(StyleSource("table style (unresolved)"))
                for p_i, para in enumerate(tc.findall("a:txBody/a:p", NS)):
                    p_pr = para.find("a:pPr", NS)
                    try:
                        lvl = int(p_pr.get("lvl", "0")) if p_pr is not None else 0
                    except ValueError:
                        lvl = 0
                    tail: list[StyleSource] = []
                    if p_pr is not None:
                        tail.append(StyleSource("paragraph", p_pr.find("a:defRPr", NS)))
                    tail.append(
                        StyleSource(
                            "cell list style", _lvl_def(tc.find("a:txBody/a:lstStyle", NS), lvl)
                        )
                    )
                    tail.extend(sources_tail_base)
                    if master_root is not None:
                        tail.append(
                            StyleSource(
                                "master otherStyle",
                                _lvl_def(master_root.find("p:txStyles/p:otherStyle", NS), lvl),
                            )
                        )
                    tail.append(
                        StyleSource(
                            "presentation default",
                            _lvl_def(pres.find("p:defaultTextStyle", NS), lvl),
                        )
                    )
                    r_index = -1
                    for run_el in para:
                        if local(run_el.tag) not in ("r", "fld"):
                            continue
                        r_index += 1
                        t = run_el.find("a:t", NS)
                        text = (t.text or "") if t is not None else ""
                        if not text.strip():
                            continue
                        run_id = self._unique(
                            f"s{number}-sh{shape_id}-c{r_i}x{c_i}-p{p_i}-r{r_index}", seen_ids
                        )
                        runs.append(
                            self._build_run(
                                run_id,
                                number,
                                slide_part,
                                el,
                                run_el,
                                name,
                                shape_id,
                                text,
                                p_i,
                                r_index,
                                (r_i, c_i),
                                tail,
                                theme,
                                1.0,
                                cell_rect,
                                cell_bg,
                                None,
                                None,
                            )
                        )
        return runs


def inspect_package(package: PptxPackage, filename: str = "presentation.pptx") -> Inspection:
    return Inspector(package, filename).inspect()


def large_text(run: TextRun) -> bool:
    return is_large_text(run.size_pt, run.bold)
