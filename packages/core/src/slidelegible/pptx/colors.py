"""Resolve DrawingML color expressions (theme colors, color maps, and transforms)."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

from lxml import etree

from ..color import RGB, linear_to_srgb, srgb_to_linear
from .xml import NS, local

COLOR_TAGS = {"srgbClr", "schemeClr", "sysClr", "prstClr", "scrgbClr", "hslClr"}
SCHEME_KEYS = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)
DEFAULT_CLR_MAP = {
    "bg1": "lt1",
    "tx1": "dk1",
    "bg2": "lt2",
    "tx2": "dk2",
    **{f"accent{i}": f"accent{i}" for i in range(1, 7)},
    "hlink": "hlink",
    "folHlink": "folHlink",
}

# A subset of DrawingML preset colors (ST_PresetColorVal) common in real decks.
PRESET_COLORS = {
    "black": "000000",
    "white": "FFFFFF",
    "red": "FF0000",
    "green": "008000",
    "lime": "00FF00",
    "blue": "0000FF",
    "yellow": "FFFF00",
    "cyan": "00FFFF",
    "aqua": "00FFFF",
    "magenta": "FF00FF",
    "fuchsia": "FF00FF",
    "gray": "808080",
    "grey": "808080",
    "silver": "C0C0C0",
    "darkGray": "A9A9A9",
    "dkGray": "A9A9A9",
    "lightGray": "D3D3D3",
    "ltGray": "D3D3D3",
    "orange": "FFA500",
    "purple": "800080",
    "navy": "000080",
    "maroon": "800000",
    "olive": "808000",
    "teal": "008080",
    "pink": "FFC0CB",
    "brown": "A52A2A",
    "gold": "FFD700",
}


@dataclass(frozen=True)
class ResolvedColor:
    rgb: RGB
    expression: str
    scheme: str | None = None  # theme slot name when the color came from the theme


@dataclass
class ColorContext:
    """Theme color scheme plus the effective color map for one slide/layout/master."""

    scheme: dict[str, RGB]
    clr_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CLR_MAP))

    def scheme_color(self, name: str) -> tuple[RGB, str] | None:
        slot = self.clr_map.get(name, name)
        value = self.scheme.get(slot)
        if value is None:
            return None
        return value, slot

    def resolve_fill_color(
        self, fill: etree._Element | None, ph_color: ResolvedColor | None = None
    ) -> ResolvedColor | None:
        """Resolve the color child of a ``solidFill`` (or similar) element."""
        if fill is None:
            return None
        for el in fill:
            if local(el.tag) in COLOR_TAGS:
                return self.resolve(el, ph_color)
        return None

    def resolve(
        self, el: etree._Element, ph_color: ResolvedColor | None = None
    ) -> ResolvedColor | None:
        tag = local(el.tag)
        base: RGB | None = None
        scheme: str | None = None
        expr = tag
        val = el.get("val", "")
        if tag == "srgbClr":
            try:
                base = RGB.from_hex(val)
            except ValueError:
                return None
            expr = f"srgbClr {val.upper()}"
        elif tag == "schemeClr":
            if val == "phClr":
                if ph_color is None:
                    return None
                base, scheme = ph_color.rgb, ph_color.scheme
                expr = f"phClr({ph_color.expression})"
            else:
                found = self.scheme_color(val)
                if found is None:
                    return None
                base, scheme = found[0], found[1]
                expr = f"schemeClr {val}" + (f"→{scheme}" if scheme != val else "")
        elif tag == "sysClr":
            last = el.get("lastClr")
            fallback = {"windowText": "000000", "window": "FFFFFF"}.get(val)
            hex_value = last or fallback
            if hex_value is None:
                return None
            base = RGB.from_hex(hex_value)
            expr = f"sysClr {val}"
        elif tag == "prstClr":
            hex_value = PRESET_COLORS.get(val)
            if hex_value is None:
                return None
            base = RGB.from_hex(hex_value)
            expr = f"prstClr {val}"
        elif tag == "scrgbClr":
            lin = [int(el.get(k, "0")) / 100_000 for k in ("r", "g", "b")]
            base = RGB(*(linear_to_srgb(min(max(c, 0.0), 1.0)) for c in lin))
            expr = "scrgbClr"
        elif tag == "hslClr":
            hue = int(el.get("hue", "0")) / 60_000 / 360
            sat = int(el.get("sat", "0")) / 100_000
            lum = int(el.get("lum", "0")) / 100_000
            base = RGB(*colorsys.hls_to_rgb(hue % 1, min(max(lum, 0), 1), min(max(sat, 0), 1)))
            expr = "hslClr"
        if base is None:
            return None
        rgb, mods = apply_transforms(base, el)
        if mods:
            expr += " " + " ".join(mods)
        return ResolvedColor(rgb, expr, scheme)


def apply_transforms(base: RGB, el: etree._Element) -> tuple[RGB, list[str]]:
    """Apply DrawingML color transforms in document order."""
    r, g, b, alpha = base.r, base.g, base.b, base.alpha
    applied: list[str] = []
    for mod in el:
        name = local(mod.tag)
        try:
            v = int(mod.get("val", "0")) / 100_000
        except ValueError:
            continue
        if name in ("tint", "shade") or name.startswith(("red", "green", "blue")):
            lr, lg, lb = srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b)
            if name == "tint":
                lr, lg, lb = (1 - (1 - c) * v for c in (lr, lg, lb))
            elif name == "shade":
                lr, lg, lb = (c * v for c in (lr, lg, lb))
            else:
                channel = name.removesuffix("Mod").removesuffix("Off")
                op = name[len(channel) :]
                vals = {"red": lr, "green": lg, "blue": lb}
                cur = vals[channel]
                cur = cur * v if op == "Mod" else cur + v if op == "Off" else v
                vals[channel] = cur
                lr, lg, lb = vals["red"], vals["green"], vals["blue"]
            r, g, b = (linear_to_srgb(min(max(c, 0.0), 1.0)) for c in (lr, lg, lb))
        elif name in (
            "lumMod",
            "lumOff",
            "satMod",
            "satOff",
            "hueMod",
            "hueOff",
            "hue",
            "sat",
            "lum",
            "comp",
        ):
            h, lum, s = colorsys.rgb_to_hls(r, g, b)
            if name == "lumMod":
                lum *= v
            elif name == "lumOff":
                lum += v
            elif name == "lum":
                lum = v
            elif name == "satMod":
                s *= v
            elif name == "satOff":
                s += v
            elif name == "sat":
                s = v
            elif name == "hueMod":
                h = (h * v) % 1
            elif name == "hueOff":
                h = (h + int(mod.get("val", "0")) / 60_000 / 360) % 1
            elif name == "hue":
                h = (int(mod.get("val", "0")) / 60_000 / 360) % 1
            elif name == "comp":
                h = (h + 0.5) % 1
            r, g, b = colorsys.hls_to_rgb(h, min(max(lum, 0.0), 1.0), min(max(s, 0.0), 1.0))
        elif name == "alpha":
            alpha = v
        elif name == "alphaMod":
            alpha *= v
        elif name == "alphaOff":
            alpha += v
        elif name == "inv":
            r, g, b = 1 - r, 1 - g, 1 - b
        elif name == "gray":
            y = 0.2126 * r + 0.7152 * g + 0.0722 * b
            r = g = b = y
        else:
            continue
        applied.append(f"{name}={mod.get('val', '')}" if mod.get("val") else name)
    return RGB(r, g, b, min(max(alpha, 0.0), 1.0)).clamped(), applied


def read_color_scheme(theme_root: etree._Element) -> dict[str, RGB]:
    scheme: dict[str, RGB] = {}
    clr = theme_root.find("a:themeElements/a:clrScheme", NS)
    if clr is None:
        return scheme
    bootstrap = ColorContext({})
    for key in SCHEME_KEYS:
        slot = clr.find(f"a:{key}", NS)
        if slot is None:
            continue
        for el in slot:
            if local(el.tag) in COLOR_TAGS:
                resolved = bootstrap.resolve(el)
                if resolved is not None:
                    scheme[key] = resolved.rgb
                break
    return scheme


def read_clr_map(el: etree._Element | None) -> dict[str, str] | None:
    if el is None:
        return None
    mapping = dict(DEFAULT_CLR_MAP)
    for key, value in el.attrib.items():
        mapping[str(key)] = str(value)
    return mapping
