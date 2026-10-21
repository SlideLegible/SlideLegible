"""Domain records shared by inspection, analysis, correction, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .color import RGB, contrast_ratio


class BackgroundKind(StrEnum):
    SOLID = "solid"
    GRADIENT = "gradient"
    IMAGE = "image"
    COMPLEX = "complex"
    UNKNOWN = "unknown"


class Certainty(StrEnum):
    EXACT = "exact"  # resolved from OOXML, opaque solid layers only
    DERIVED = "derived"  # computed from OOXML with assumptions (alpha, gradient stops)
    RENDERED = "rendered_estimate"  # sampled from a rendered slide
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in EMU."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def contains(self, other: Rect, tolerance: float = 12_700) -> bool:
        return (
            self.x - tolerance <= other.x
            and self.y - tolerance <= other.y
            and self.right + tolerance >= other.right
            and self.bottom + tolerance >= other.bottom
        )

    def intersects(self, other: Rect) -> bool:
        return not (
            other.x >= self.right
            or other.right <= self.x
            or other.y >= self.bottom
            or other.bottom <= self.y
        )

    def inset(self, left: float, top: float, right: float, bottom: float) -> Rect:
        w = max(self.w - left - right, 1)
        h = max(self.h - top - bottom, 1)
        return Rect(self.x + left, self.y + top, w, h)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True)
class FillTarget:
    """An editable solid fill: a background or shape/cell fill in a specific part."""

    kind: str  # slide_background | layout_background | master_background | shape_fill | cell_fill
    part: str
    path: str  # element path within the part (cSld for backgrounds, sp/tc otherwise)
    label: str
    color: RGB

    @property
    def key(self) -> str:
        return f"{self.part}#{self.path}"

    @property
    def shared(self) -> bool:
        return self.kind in ("layout_background", "master_background") or not self.part.startswith(
            "ppt/slides/"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "part": self.part,
            "label": self.label,
            "color": f"#{self.color.hex}",
            "shared": self.shared,
        }


@dataclass
class Background:
    kind: BackgroundKind
    certainty: Certainty
    color: RGB | None = None  # representative opaque color (solid backgrounds)
    samples: list[RGB] = field(default_factory=list)  # gradient stops or rendered samples
    layers: list[str] = field(default_factory=list)  # human-readable evidence, top first
    editable: FillTarget | None = None
    has_image: bool = False
    needs_render: bool = False
    note: str | None = None

    def colors(self) -> list[RGB]:
        if self.samples:
            return self.samples
        if self.color is not None:
            return [self.color]
        return []

    def worst_ratio(self, text: RGB) -> float | None:
        colors = self.colors()
        if not colors:
            return None
        return min(contrast_ratio(text, c) for c in colors)

    def worst_color(self, text: RGB) -> RGB | None:
        colors = self.colors()
        if not colors:
            return None
        return min(colors, key=lambda c: contrast_ratio(text, c))

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "certainty": self.certainty.value,
            "color": f"#{self.color.hex}" if self.color else None,
            "samples": [f"#{c.hex}" for c in self.samples],
            "layers": self.layers,
            "editable": self.editable.to_dict() if self.editable else None,
            "has_image": self.has_image,
            "note": self.note,
        }


@dataclass(frozen=True)
class ScrimAnchor:
    """Where a scrim rectangle can be inserted directly beneath a text shape."""

    part: str
    shape_path: str
    off_x: int
    off_y: int
    ext_cx: int
    ext_cy: int


@dataclass
class TextRun:
    id: str
    slide_index: int
    slide_part: str
    run_path: str
    shape_id: str
    shape_name: str
    shape_path: str
    excerpt: str
    paragraph: int
    run: int
    cell: tuple[int, int] | None
    size_pt: float | None
    size_basis: str
    bold: bool
    color: RGB
    color_expr: str
    color_source: str
    color_certain: bool
    hyperlink: bool
    text_area: Rect | None
    background: Background
    unsupported: str | None = None
    scrim_anchor: ScrimAnchor | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "slide": self.slide_index,
            "shape": self.shape_name,
            "shape_id": self.shape_id,
            "cell": list(self.cell) if self.cell else None,
            "paragraph": self.paragraph,
            "run": self.run,
            "excerpt": self.excerpt,
            "size_pt": self.size_pt,
            "size_basis": self.size_basis,
            "bold": self.bold,
            "color": f"#{self.color.hex}",
            "color_alpha": round(self.color.alpha, 3),
            "color_expr": self.color_expr,
            "color_source": self.color_source,
            "color_certain": self.color_certain,
            "hyperlink": self.hyperlink,
            "text_area": self.text_area.to_dict() if self.text_area else None,
            "background": self.background.to_dict(),
            "unsupported": self.unsupported,
        }


@dataclass(frozen=True)
class UnsupportedItem:
    slide_index: int
    shape_name: str
    kind: str  # chart | smartart | ole | wordart | ...
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "slide": self.slide_index,
            "shape": self.shape_name,
            "kind": self.kind,
            "detail": self.detail,
        }


@dataclass
class SlideInfo:
    index: int
    part: str
    layout_part: str | None
    master_part: str | None
    width_emu: int
    height_emu: int
    hidden: bool = False
    theme_dark: RGB = RGB(0.0, 0.0, 0.0)
    theme_light: RGB = RGB(1.0, 1.0, 1.0)


@dataclass
class Inspection:
    fingerprint: str
    filename: str
    slide_width: int
    slide_height: int
    slides: list[SlideInfo]
    runs: list[TextRun]
    unsupported: list[UnsupportedItem]
    warnings: list[str]
