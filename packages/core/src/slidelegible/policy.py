"""Named correction policies. Presets are core data shared by every adapter."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from .apca import APCA_VERSION, apca_lc
from .color import RGB, contrast_ratio

POLICY_VERSION = "2026.10-mvp1"

# Large text per WCAG 2.x: at least 18 pt, or at least 14 pt bold.
LARGE_TEXT_PT = 18.0
LARGE_BOLD_TEXT_PT = 14.0

# Decorative text is reported but never corrected.
DECORATIVE_ALPHA_MAX = 0.5  # text opacity at or below this (transparency >= 50 %)
DECORATIVE_MIN_PT = 72.0
DECORATIVE_MAX_RATIO = 1.5

# Over-saturated backgrounds behind text (OKLCH chroma).
SATURATION_LIMIT = 0.20

# Background lightness changes are limited to a gentle adjustment (OKLCH L).
MAX_BACKGROUND_SHIFT = 0.15

# Image scrims: opacity range searched for the smallest passing value.
SCRIM_MIN_ALPHA = 0.30
SCRIM_MAX_ALPHA = 0.85

# Softening targets used only when the caller enables softening.
SOFT_BLACK_BACKGROUND = RGB.from_hex("121212")
SOFT_WHITE_BACKGROUND = RGB.from_hex("FAFAFA")
SOFT_BLACK_TEXT = RGB.from_hex("1A1A1A")
SOFT_WHITE_TEXT = RGB.from_hex("F0F0F0")


class PolicyName(StrEnum):
    COMFORTABLE = "comfortable"
    PROJECTOR = "projector"
    STRICT_AAA = "strict_aaa"


@dataclass(frozen=True)
class Requirement:
    """Numeric target for one text size class."""

    min_ratio: float
    min_apca: float | None = None  # absolute Lc; None means APCA is informational only

    def met(self, text: RGB, background: RGB) -> bool:
        if contrast_ratio(text, background) < self.min_ratio:
            return False
        if self.min_apca is not None and abs(apca_lc(text, background)) < self.min_apca:
            return False
        return True

    def stricter(self, other: Requirement) -> Requirement:
        apca: float | None
        if self.min_apca is None:
            apca = other.min_apca
        elif other.min_apca is None:
            apca = self.min_apca
        else:
            apca = max(self.min_apca, other.min_apca)
        return Requirement(max(self.min_ratio, other.min_ratio), apca)

    def to_dict(self) -> dict[str, float | None]:
        return {"min_ratio": self.min_ratio, "min_apca_lc": self.min_apca}


@dataclass(frozen=True)
class CorrectionPolicy:
    name: PolicyName
    normal: Requirement
    large: Requirement
    allow_soften: bool
    soften: bool = False
    # Edit permissions selected for the MVP.
    edit_text: bool = True
    edit_background: bool = True
    allow_polarity_flip: bool = True
    reduce_saturation: bool = True
    add_scrims: bool = True
    max_background_shift: float = MAX_BACKGROUND_SHIFT
    # Small margin so rounding and renderer differences do not land exactly on the edge.
    ratio_margin: float = 0.05
    apca_margin: float = 1.0
    notes: tuple[str, ...] = field(default_factory=tuple)

    def requirement(self, large: bool) -> Requirement:
        return self.large if large else self.normal

    def search_requirement(self, large: bool) -> Requirement:
        req = self.requirement(large)
        apca = None if req.min_apca is None else req.min_apca + self.apca_margin
        return Requirement(req.min_ratio + self.ratio_margin, apca)

    def with_options(self, *, soften: bool) -> CorrectionPolicy:
        return replace(self, soften=soften and self.allow_soften)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name.value,
            "version": POLICY_VERSION,
            "apca_version": APCA_VERSION,
            "normal_text": self.normal.to_dict(),
            "large_text": self.large.to_dict(),
            "soften_extremes": self.soften,
            "large_text_definition": {
                "min_pt": LARGE_TEXT_PT,
                "min_bold_pt": LARGE_BOLD_TEXT_PT,
            },
            "saturation_limit_oklch_c": SATURATION_LIMIT,
            "max_background_shift_oklch_l": self.max_background_shift,
            "scrim_alpha_range": [SCRIM_MIN_ALPHA, SCRIM_MAX_ALPHA],
        }


PRESETS: dict[PolicyName, CorrectionPolicy] = {
    # Large text on slides is still held to 4.5:1 because projection and
    # ambient light reduce effective contrast.
    PolicyName.COMFORTABLE: CorrectionPolicy(
        name=PolicyName.COMFORTABLE,
        normal=Requirement(4.5, 75.0),
        large=Requirement(4.5, 60.0),
        allow_soften=True,
    ),
    PolicyName.PROJECTOR: CorrectionPolicy(
        name=PolicyName.PROJECTOR,
        normal=Requirement(7.0),
        large=Requirement(4.5),
        allow_soften=True,
    ),
    PolicyName.STRICT_AAA: CorrectionPolicy(
        name=PolicyName.STRICT_AAA,
        normal=Requirement(7.0),
        large=Requirement(4.5),
        allow_soften=False,
    ),
}


def get_policy(name: str | PolicyName, *, soften: bool = False) -> CorrectionPolicy:
    try:
        key = PolicyName(name)
    except ValueError as exc:
        raise ValueError(f"Unknown policy: {name!r}") from exc
    return PRESETS[key].with_options(soften=soften)


def is_large_text(size_pt: float | None, bold: bool) -> bool:
    if size_pt is None:
        return False
    return size_pt >= LARGE_TEXT_PT or (bold and size_pt >= LARGE_BOLD_TEXT_PT)
