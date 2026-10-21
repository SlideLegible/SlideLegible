"""Evaluate every text run against a correction policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .apca import apca_lc
from .color import RGB, composite, contrast_ratio
from .model import BackgroundKind, TextRun
from .policy import (
    DECORATIVE_ALPHA_MAX,
    DECORATIVE_MAX_RATIO,
    DECORATIVE_MIN_PT,
    CorrectionPolicy,
    Requirement,
    is_large_text,
)


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    DECORATIVE = "decorative"  # reported, never corrected
    UNSUPPORTED = "unsupported"  # chart/WordArt/gradient text...
    UNKNOWN_BACKGROUND = "unknown_background"
    UNCERTAIN_COLOR = "uncertain_color"


@dataclass
class Finding:
    run: TextRun
    large: bool
    requirement: Requirement
    effective_fg: RGB
    ratio: float | None
    apca: float | None
    worst_bg: RGB | None
    status: Status
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "run": self.run.to_dict(),
            "large_text": self.large,
            "requirement": self.requirement.to_dict(),
            "effective_color": f"#{self.effective_fg.hex}",
            "ratio": round(self.ratio, 2) if self.ratio is not None else None,
            "apca_lc": round(self.apca, 1) if self.apca is not None else None,
            "worst_background": f"#{self.worst_bg.hex}" if self.worst_bg else None,
            "status": self.status.value,
            "reason": self.reason,
        }


def effective_text_color(run: TextRun, background: RGB | None) -> RGB:
    """Composite semi-transparent text over its background."""
    if run.color.alpha >= 0.999 or background is None:
        return run.color.opaque()
    return composite(run.color, background).opaque()


def evaluate(run: TextRun, policy: CorrectionPolicy, colors: list[RGB] | None = None) -> Finding:
    large = is_large_text(run.size_pt, run.bold)
    requirement = policy.requirement(large)
    bg_colors = colors if colors is not None else run.background.colors()
    base = bg_colors[len(bg_colors) // 2] if bg_colors else None
    fg = effective_text_color(run, base)
    if run.unsupported:
        status = Status.UNSUPPORTED
        reason = run.unsupported
    elif not bg_colors:
        status, reason = Status.UNKNOWN_BACKGROUND, run.background.note or "background unknown"
    else:
        status, reason = Status.PASS, None
    ratio = lc = None
    worst = None
    if bg_colors:
        per_bg = [effective_text_color(run, c) for c in bg_colors]
        pairs = list(zip(per_bg, bg_colors, strict=True))
        worst_pair = min(pairs, key=lambda p: contrast_ratio(p[0], p[1]))
        ratio = contrast_ratio(*worst_pair)
        worst = worst_pair[1]
        fg = worst_pair[0]
        lcs = [apca_lc(f, b) for f, b in pairs]
        lc = min(lcs, key=abs)
        if status == Status.PASS:
            passes = all(requirement.met(f, b) for f, b in pairs)
            if run.color.alpha <= DECORATIVE_ALPHA_MAX:
                status, reason = Status.DECORATIVE, "transparent_text"
            elif (
                run.size_pt is not None
                and run.size_pt >= DECORATIVE_MIN_PT
                and ratio < DECORATIVE_MAX_RATIO
            ):
                status, reason = Status.DECORATIVE, "watermark"
            elif not passes:
                status = Status.FAIL
                if not run.color_certain:
                    status, reason = (
                        Status.UNCERTAIN_COLOR,
                        "text color could not be resolved reliably",
                    )
    elif run.color.alpha <= DECORATIVE_ALPHA_MAX and status == Status.UNKNOWN_BACKGROUND:
        status, reason = Status.DECORATIVE, "transparent_text"
    if status == Status.PASS and run.background.kind == BackgroundKind.UNKNOWN:
        status = Status.UNKNOWN_BACKGROUND
    return Finding(run, large, requirement, fg, ratio, lc, worst, status, reason)


def analyze(runs: list[TextRun], policy: CorrectionPolicy) -> list[Finding]:
    return [evaluate(run, policy) for run in runs]
