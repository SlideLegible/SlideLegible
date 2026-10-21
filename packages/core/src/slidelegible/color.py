"""Color math: sRGB values, WCAG 2.x contrast, compositing, and OKLab/OKLCH.

All public functions are pure and renderer-free. Colors are gamma-encoded sRGB
channels in ``[0, 1]`` plus an alpha channel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "RGB",
    "OKLCH",
    "composite",
    "contrast_ratio",
    "relative_luminance",
    "srgb_to_linear",
    "linear_to_srgb",
    "rgb_to_oklch",
    "oklch_to_rgb",
    "oklch_in_gamut",
]


@dataclass(frozen=True, order=True)
class RGB:
    """A gamma-encoded sRGB color with optional alpha, channels in ``[0, 1]``."""

    r: float
    g: float
    b: float
    alpha: float = 1.0

    @classmethod
    def from_hex(cls, value: str, alpha: float = 1.0) -> RGB:
        text = value.strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        if len(text) != 6:
            raise ValueError(f"Invalid hex color: {value!r}")
        r, g, b = (int(text[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return cls(r, g, b, alpha)

    @classmethod
    def from_255(cls, r: int, g: int, b: int, alpha: float = 1.0) -> RGB:
        return cls(r / 255, g / 255, b / 255, alpha)

    def clamped(self) -> RGB:
        return RGB(_clamp01(self.r), _clamp01(self.g), _clamp01(self.b), _clamp01(self.alpha))

    def quantized(self) -> RGB:
        """Round channels to 8-bit precision, as written to OOXML ``srgbClr``."""
        r, g, b = self.to_255()
        return RGB(r / 255, g / 255, b / 255, self.alpha)

    def to_255(self) -> tuple[int, int, int]:
        c = self.clamped()
        return (round(c.r * 255), round(c.g * 255), round(c.b * 255))

    @property
    def hex(self) -> str:
        r, g, b = self.to_255()
        return f"{r:02X}{g:02X}{b:02X}"

    def opaque(self) -> RGB:
        return RGB(self.r, self.g, self.b, 1.0)

    def with_alpha(self, alpha: float) -> RGB:
        return RGB(self.r, self.g, self.b, alpha)

    def __str__(self) -> str:
        if self.alpha < 1:
            return f"#{self.hex}@{self.alpha:.2f}"
        return f"#{self.hex}"


@dataclass(frozen=True)
class OKLCH:
    """OKLCH lightness ``l`` in ``[0, 1]``, chroma ``c`` >= 0, hue ``h`` in degrees."""

    l: float  # noqa: E741 - conventional name for OKLCH lightness
    c: float
    h: float


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def srgb_to_linear(channel: float) -> float:
    """WCAG 2.x sRGB transfer function (0.04045 breakpoint, IEC 61966-2-1)."""
    if channel <= 0.04045:
        return channel / 12.92
    return float(((channel + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(channel: float) -> float:
    if channel <= 0.0031308:
        return 12.92 * channel
    return float(1.055 * channel ** (1 / 2.4) - 0.055)


def relative_luminance(color: RGB) -> float:
    """WCAG 2.x relative luminance of an opaque color."""
    return (
        0.2126 * srgb_to_linear(color.r)
        + 0.7152 * srgb_to_linear(color.g)
        + 0.0722 * srgb_to_linear(color.b)
    )


def contrast_ratio(a: RGB, b: RGB) -> float:
    """WCAG 2.x contrast ratio between two opaque colors, in ``[1, 21]``."""
    la = relative_luminance(a)
    lb = relative_luminance(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def composite(top: RGB, bottom: RGB) -> RGB:
    """Source-over composite of ``top`` onto ``bottom``.

    Blending happens on gamma-encoded sRGB values because that is what
    PowerPoint, LibreOffice and browsers produce on screen, so the result
    matches the pixels a reader actually sees.
    """
    a_top = _clamp01(top.alpha)
    a_bot = _clamp01(bottom.alpha)
    out_a = a_top + a_bot * (1 - a_top)
    if out_a <= 0:
        return RGB(0, 0, 0, 0)

    def mix(t: float, b: float) -> float:
        return (t * a_top + b * a_bot * (1 - a_top)) / out_a

    return RGB(mix(top.r, bottom.r), mix(top.g, bottom.g), mix(top.b, bottom.b), out_a)


# --- OKLab / OKLCH (Björn Ottosson, 2020) -------------------------------------


def _linear_rgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_c, m_c, s_c = (
        math.copysign(abs(l_) ** (1 / 3), l_),
        math.copysign(abs(m_) ** (1 / 3), m_),
        math.copysign(abs(s_) ** (1 / 3), s_),
    )
    return (
        0.2104542553 * l_c + 0.7936177850 * m_c - 0.0040720468 * s_c,
        1.9779984951 * l_c - 2.4285922050 * m_c + 0.4505937099 * s_c,
        0.0259040371 * l_c + 0.7827717662 * m_c - 0.8086757660 * s_c,
    )


def _oklab_to_linear_rgb(lightness: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l3, m3, s3 = l_**3, m_**3, s_**3
    return (
        4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
        -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
        -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3,
    )


def rgb_to_oklch(color: RGB) -> OKLCH:
    lin = (srgb_to_linear(color.r), srgb_to_linear(color.g), srgb_to_linear(color.b))
    lightness, a, b = _linear_rgb_to_oklab(*lin)
    chroma = math.hypot(a, b)
    hue = math.degrees(math.atan2(b, a)) % 360 if chroma > 1e-7 else 0.0
    return OKLCH(lightness, chroma, hue)


def _oklch_to_linear(value: OKLCH) -> tuple[float, float, float]:
    rad = math.radians(value.h)
    return _oklab_to_linear_rgb(value.l, value.c * math.cos(rad), value.c * math.sin(rad))


def oklch_in_gamut(value: OKLCH, eps: float = 1e-6) -> bool:
    return all(-eps <= ch <= 1 + eps for ch in _oklch_to_linear(value))


def oklch_to_rgb(value: OKLCH, alpha: float = 1.0) -> RGB:
    """Convert OKLCH to sRGB, reducing chroma (hue and lightness fixed) if out of gamut."""
    lightness = _clamp01(value.l)
    target = OKLCH(lightness, max(0.0, value.c), value.h)
    if not oklch_in_gamut(target):
        lo, hi = 0.0, target.c
        for _ in range(40):
            mid = (lo + hi) / 2
            if oklch_in_gamut(OKLCH(lightness, mid, value.h)):
                lo = mid
            else:
                hi = mid
        target = OKLCH(lightness, lo, value.h)
    r, g, b = (_clamp01(linear_to_srgb(_clamp01(ch))) for ch in _oklch_to_linear(target))
    return RGB(r, g, b, alpha)
