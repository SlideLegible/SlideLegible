"""Correction planning: turn failing findings into reviewable, non-mutating suggestions.

Order of strategies (each only when the policy allows it):

1. Background normalization: reduce over-saturated backgrounds behind text
   (OKLCH chroma above ``SATURATION_LIMIT``) and, when softening is enabled,
   soften pure black/white backgrounds. Text fixes are computed so that they
   pass on both the original and the normalized background, so these
   suggestions can be accepted or rejected independently.
2. Text color, same polarity: move OKLCH lightness away from the background,
   keeping hue (and chroma where in gamut), with the smallest passing change.
3. Background lightness: when text alone cannot pass, move the editable solid
   background away from the text (background only first; otherwise the
   smallest background change that makes a text fix possible). Layout and
   master backgrounds are edited in place, so every slide using them is
   re-checked and re-fixed.
4. Polarity flip of the text color (marked as a major change).
5. Image backgrounds: a semi-transparent scrim in the theme's dark or light
   color with the smallest opacity in ``SCRIM_MIN_ALPHA..SCRIM_MAX_ALPHA``,
   plus a text change if the scrim alone is not enough.

Gradient or mixed backgrounds where no single text color passes everywhere
are reported as unfixable. Every suggestion is re-verified on 8-bit colors.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from .analyze import Finding, Status
from .apca import apca_lc
from .color import (
    OKLCH,
    RGB,
    composite,
    contrast_ratio,
    oklch_to_rgb,
    relative_luminance,
    rgb_to_oklch,
)
from .model import BackgroundKind, FillTarget, Inspection, ScrimAnchor
from .policy import (
    POLICY_VERSION,
    SATURATION_LIMIT,
    SCRIM_MAX_ALPHA,
    SCRIM_MIN_ALPHA,
    SOFT_BLACK_BACKGROUND,
    SOFT_BLACK_TEXT,
    SOFT_WHITE_BACKGROUND,
    SOFT_WHITE_TEXT,
    CorrectionPolicy,
    Requirement,
)

BLACK = RGB(0.0, 0.0, 0.0)
WHITE = RGB(1.0, 1.0, 1.0)


@dataclass
class Suggestion:
    id: str
    kind: (
        str  # text_color | background_color | saturation | scrim | soften_text | soften_background
    )
    strategy: str
    major: bool
    run_ids: list[str]
    slides: list[int]
    original: RGB | None
    proposed: RGB
    rationale: str
    alpha: float | None = None
    target: FillTarget | None = None
    scrim_anchor: ScrimAnchor | None = None
    depends_on: list[str] = field(default_factory=list)
    before_ratio: float | None = None
    after_ratio: float | None = None
    before_apca: float | None = None
    after_apca: float | None = None
    estimate: bool = False
    affected_slides: list[int] = field(default_factory=list)

    def delta(self) -> dict[str, float] | None:
        if self.original is None:
            return None
        a, b = rgb_to_oklch(self.original), rgb_to_oklch(self.proposed)
        dh = abs(a.h - b.h) % 360
        dh = min(dh, 360 - dh) if min(a.c, b.c) > 0.02 else 0.0
        return {
            "lightness": round(b.l - a.l, 4),
            "chroma": round(b.c - a.c, 4),
            "hue": round(dh, 2),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "strategy": self.strategy,
            "major": self.major,
            "runs": self.run_ids,
            "slides": self.slides,
            "affected_slides": self.affected_slides,
            "original": f"#{self.original.hex}" if self.original else None,
            "proposed": f"#{self.proposed.hex}",
            "alpha": self.alpha,
            "target": self.target.to_dict() if self.target else None,
            "depends_on": self.depends_on,
            "before": {"ratio": _r(self.before_ratio), "apca_lc": _r(self.before_apca, 1)},
            "after": {"ratio": _r(self.after_ratio), "apca_lc": _r(self.after_apca, 1)},
            "delta_oklch": self.delta(),
            "estimate": self.estimate,
            "rationale": self.rationale,
        }


@dataclass
class Unfixed:
    run_id: str
    slide: int
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"run": self.run_id, "slide": self.slide, "reason": self.reason}


@dataclass
class CorrectionPlan:
    id: str
    fingerprint: str
    policy: dict[str, object]
    suggestions: list[Suggestion]
    unfixed: list[Unfixed]

    def by_id(self) -> dict[str, Suggestion]:
        return {s.id: s for s in self.suggestions}

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "policy": self.policy,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "unfixed": [u.to_dict() for u in self.unfixed],
        }


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


# --- search primitives ---------------------------------------------------------------


def passes(fg: RGB, colors: list[RGB], req: Requirement) -> bool:
    return bool(colors) and all(req.met(fg, c) for c in colors)


ACHROMATIC_C = 0.004


def _at_lightness(base: OKLCH, lightness: float) -> RGB:
    chroma = 0.0 if base.c < ACHROMATIC_C else base.c
    return oklch_to_rgb(OKLCH(lightness, chroma, base.h)).quantized()


def search_lightness(
    color: RGB,
    check: Callable[[RGB], bool],
    direction: int,
    steps: int = 32,
    max_shift: float | None = None,
) -> RGB | None:
    """Smallest OKLCH lightness move of ``color`` in ``direction`` for which ``check`` holds."""
    base = rgb_to_oklch(color)
    end = 1.0 if direction > 0 else 0.0
    if max_shift is not None:
        end = min(1.0, base.l + max_shift) if direction > 0 else max(0.0, base.l - max_shift)
    candidate_end = _at_lightness(base, end)
    if not check(candidate_end):
        return None
    lo, hi = base.l, end
    best = candidate_end
    for _ in range(steps):
        mid = (lo + hi) / 2
        cand = _at_lightness(base, mid)
        if check(cand):
            hi, best = mid, cand
        else:
            lo = mid
    return best


def polarity(fg: RGB, colors: list[RGB]) -> list[int]:
    """Directions that keep the text's polarity relative to every background color."""
    y = relative_luminance(fg)
    lums = [relative_luminance(c) for c in colors]
    if all(y >= v for v in lums):
        return [1]
    if all(y <= v for v in lums):
        return [-1]
    return [1, -1]


def best_text_fix(
    fg: RGB, colors: list[RGB], req: Requirement, directions: list[int]
) -> RGB | None:
    found: list[RGB] = []
    for d in directions:
        cand = search_lightness(fg, lambda c: passes(c, colors, req), d)
        if cand is not None:
            found.append(cand)
    if not found:
        return None
    base = rgb_to_oklch(fg).l
    return min(found, key=lambda c: abs(rgb_to_oklch(c).l - base))


def desaturate(color: RGB, limit: float = SATURATION_LIMIT) -> RGB | None:
    value = rgb_to_oklch(color)
    if value.c <= limit:
        return None
    return oklch_to_rgb(OKLCH(value.l, limit, value.h)).quantized()


# --- planner -------------------------------------------------------------------------


@dataclass
class _Ctx:
    finding: Finding
    fg: RGB
    req: Requirement  # search requirement (with margin)
    base_colors: list[RGB]

    @property
    def run_id(self) -> str:
        return self.finding.run.id

    @property
    def target(self) -> FillTarget | None:
        return self.finding.run.background.editable


def _fixable(f: Finding) -> bool:
    run = f.run
    return (
        f.status in (Status.PASS, Status.FAIL)
        and not run.unsupported
        and run.color_certain
        and bool(run.background.colors())
    )


def _is_image(f: Finding) -> bool:
    bg = f.run.background
    return bg.has_image and bg.kind in (BackgroundKind.IMAGE, BackgroundKind.COMPLEX)


class Planner:
    def __init__(self, inspection: Inspection, findings: list[Finding], policy: CorrectionPolicy):
        self.inspection = inspection
        self.findings = findings
        self.policy = policy
        self.suggestions: list[Suggestion] = []
        self.unfixed: list[Unfixed] = []
        self._counter = 0
        self.slide_of_part: dict[str, list[int]] = defaultdict(list)
        self.target_runs: dict[str, list[_Ctx]] = defaultdict(list)
        self.target_obj: dict[str, FillTarget] = {}
        self.normalized: dict[str, tuple[RGB, str]] = {}  # key -> (new color, suggestion id)
        self.bg_final: dict[str, tuple[RGB, str]] = {}
        slides_by_layout: dict[str, list[int]] = defaultdict(list)
        slides_by_master: dict[str, list[int]] = defaultdict(list)
        for s in inspection.slides:
            self.slide_of_part[s.part].append(s.index)
            if s.layout_part:
                slides_by_layout[s.layout_part].append(s.index)
            if s.master_part:
                slides_by_master[s.master_part].append(s.index)
        self.slides_by_layout = slides_by_layout
        self.slides_by_master = slides_by_master
        self.theme_by_slide = {s.index: (s.theme_dark, s.theme_light) for s in inspection.slides}

    def _id(self) -> str:
        self._counter += 1
        return f"s{self._counter:03d}"

    def _affected(self, target: FillTarget) -> list[int]:
        """Slides with text on this fill (a layout/master edit reaches several slides)."""
        slides = {
            f.run.slide_index
            for f in self.findings
            if f.run.background.editable is not None and f.run.background.editable.key == target.key
        }
        return sorted(slides)

    # -- background color sets ----------------------------------------------------
    def colors_for(self, ctx: _Ctx) -> tuple[list[RGB], list[str]]:
        target = ctx.target
        if target is not None:
            if target.key in self.bg_final:
                color, sid = self.bg_final[target.key]
                return [color], [sid]
            if target.key in self.normalized:
                color, _ = self.normalized[target.key]
                return [target.color, color], []
        return ctx.base_colors, []

    # -- phases -------------------------------------------------------------------
    def plan(self) -> CorrectionPlan:
        ctxs: list[_Ctx] = []
        for f in self.findings:
            if f.status == Status.FAIL and not _fixable(f):
                self.unfixed.append(Unfixed(f.run.id, f.run.slide_index, "not_fixable"))
            if not _fixable(f):
                continue
            ctx = _Ctx(
                f,
                f.effective_fg,
                self.policy.search_requirement(f.large),
                f.run.background.colors(),
            )
            ctxs.append(ctx)
            if ctx.target is not None:
                self.target_runs[ctx.target.key].append(ctx)
                self.target_obj[ctx.target.key] = ctx.target

        self._normalize_backgrounds()
        image_ctxs = [c for c in ctxs if _is_image(c.finding)]
        plain = [c for c in ctxs if not _is_image(c.finding)]

        unresolved = [
            c
            for c in plain
            if not self._ok(c)
            and best_text_fix(
                c.fg, self.colors_for(c)[0], c.req, polarity(c.fg, self.colors_for(c)[0])
            )
            is None
        ]
        if self.policy.edit_background:
            self._background_changes(unresolved)
        self._text_pass(plain)
        if self.policy.add_scrims:
            self._scrims(image_ctxs)
        else:
            for c in image_ctxs:
                if c.finding.status == Status.FAIL:
                    self.unfixed.append(
                        Unfixed(c.run_id, c.finding.run.slide_index, "image_background")
                    )
        self._order()
        plan_id = hashlib.sha256(
            (self.inspection.fingerprint + POLICY_VERSION + str(self.policy.to_dict())).encode()
        ).hexdigest()[:16]
        return CorrectionPlan(
            plan_id,
            self.inspection.fingerprint,
            self.policy.to_dict(),
            self.suggestions,
            self.unfixed,
        )

    def _ok(self, ctx: _Ctx) -> bool:
        colors, _ = self.colors_for(ctx)
        real = self.policy.requirement(ctx.finding.large)
        return passes(ctx.fg, colors, real)

    def _normalize_backgrounds(self) -> None:
        for key, ctxs in self.target_runs.items():
            target = self.target_obj[key]
            new: RGB | None = None
            kind = ""
            if self.policy.reduce_saturation:
                new = desaturate(target.color)
                kind = "saturation"
            if new is None and self.policy.soften:
                if target.color.hex == "000000":
                    new, kind = SOFT_BLACK_BACKGROUND, "soften_background"
                elif target.color.hex == "FFFFFF":
                    new, kind = SOFT_WHITE_BACKGROUND, "soften_background"
                if new is not None:
                    # Softening must not make any run on this background fail.
                    if not all(
                        passes(c.fg, [new], self.policy.requirement(c.finding.large))
                        for c in ctxs
                        if passes(c.fg, [target.color], self.policy.requirement(c.finding.large))
                    ):
                        new = None
            if new is None:
                continue
            sid = self._id()
            self.normalized[key] = (new, sid)
            runs = [c.run_id for c in ctxs]
            measured = [c for c in ctxs if c.finding.status == Status.PASS]
            ratios = [contrast_ratio(c.fg, target.color) for c in measured]
            after = [contrast_ratio(c.fg, new) for c in measured]
            self.suggestions.append(
                Suggestion(
                    id=sid,
                    kind=kind,
                    strategy=kind,
                    major=False,
                    run_ids=runs,
                    slides=sorted({c.finding.run.slide_index for c in ctxs}),
                    original=target.color,
                    proposed=new,
                    target=target,
                    rationale="reduce_saturation" if kind == "saturation" else "soften_background",
                    before_ratio=min(ratios) if ratios else None,
                    after_ratio=min(after) if after else None,
                    affected_slides=self._affected(target),
                )
            )

    def _background_changes(self, unresolved: list[_Ctx]) -> None:
        by_target: dict[str, list[_Ctx]] = defaultdict(list)
        for c in unresolved:
            if c.target is not None:
                by_target[c.target.key].append(c)
        limit = self.policy.max_background_shift
        for key, ctxs in by_target.items():
            target = self.target_obj[key]
            base = self.normalized[key][0] if key in self.normalized else target.color
            everyone = self.target_runs[key]
            others = [c for c in everyone if c not in ctxs]

            def others_ok(bg: RGB, group: list[_Ctx] = others) -> bool:
                return all(
                    passes(c.fg, [bg], c.req)
                    or best_text_fix(c.fg, [bg], c.req, [1, -1]) is not None
                    for c in group
                )

            options: list[tuple[int, float, RGB, str]] = []
            for direction in (1, -1):
                group = [
                    c
                    for c in ctxs
                    if (relative_luminance(c.fg) >= relative_luminance(base)) == (direction < 0)
                ]
                if not group:
                    continue
                rest = [c for c in ctxs if c not in group]

                def bg_only(bg: RGB, g: list[_Ctx] = group, r: list[_Ctx] = rest) -> bool:
                    return (
                        all(passes(c.fg, [bg], c.req) for c in g)
                        and others_ok(bg)
                        and others_ok(bg, r)
                    )

                def with_text(
                    bg: RGB, g: list[_Ctx] = group, r: list[_Ctx] = rest, d: int = direction
                ) -> bool:
                    return (
                        all(best_text_fix(c.fg, [bg], c.req, [-d]) is not None for c in g)
                        and others_ok(bg)
                        and others_ok(bg, r)
                    )

                for strategy, check in (
                    ("background", bg_only),
                    ("background_and_text", with_text),
                ):
                    found = search_lightness(base, check, direction, max_shift=limit)
                    if found is not None:
                        shift = abs(rgb_to_oklch(found).l - rgb_to_oklch(base).l)
                        # Prefer fixing more runs in their own polarity, then the smaller shift.
                        options.append((-len(group), shift, found, strategy))
                        break
            if not options:
                continue
            options.sort(key=lambda o: (o[0], o[1]))
            _, _, new, strategy = options[0]
            sid = self._id()
            # Replace a pending normalization of the same target: this change includes it.
            if key in self.normalized:
                old_sid = self.normalized.pop(key)[1]
                self.suggestions = [s for s in self.suggestions if s.id != old_sid]
            self.bg_final[key] = (new, sid)
            self.suggestions.append(
                Suggestion(
                    id=sid,
                    kind="background_color",
                    strategy=strategy,
                    major=True,
                    run_ids=[c.run_id for c in everyone],
                    slides=sorted({c.finding.run.slide_index for c in everyone}),
                    original=target.color,
                    proposed=new,
                    target=target,
                    rationale="text_cannot_reach_target",
                    before_ratio=min(contrast_ratio(c.fg, target.color) for c in ctxs),
                    after_ratio=min(contrast_ratio(c.fg, new) for c in ctxs),
                    affected_slides=self._affected(target),
                )
            )

    def _soft_text(self, color: RGB, colors: list[RGB], req: Requirement) -> RGB:
        if not self.policy.soften:
            return color
        soft = {"FFFFFF": SOFT_WHITE_TEXT, "000000": SOFT_BLACK_TEXT}.get(color.hex)
        if soft is not None and passes(soft, colors, req):
            return soft
        return color

    def _text_pass(self, ctxs: list[_Ctx]) -> None:
        groups: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[_Ctx]] = defaultdict(list)
        soften_groups: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[_Ctx]] = defaultdict(
            list
        )
        for c in ctxs:
            colors, dep_ids = self.colors_for(c)
            key = (c.fg.hex, tuple(sorted(x.hex for x in colors)), tuple(dep_ids))
            if self._ok(c):
                if self.policy.soften and c.fg.hex in ("FFFFFF", "000000"):
                    soften_groups[key].append(c)
                continue
            groups[key].append(c)
        for (_fg_hex, _colors_key, group_deps), members in groups.items():
            deps = list(group_deps)
            colors, _ = self.colors_for(members[0])
            req = members[0].req
            for m in members[1:]:
                req = req.stricter(m.req)
            fg = members[0].fg
            dirs = polarity(fg, colors)
            fix = best_text_fix(fg, colors, req, dirs)
            strategy, major = "lightness", False
            if (
                fix is None
                and len(dirs) == 1
                and self.policy.allow_polarity_flip
                and self._solid(members)
            ):
                fix = best_text_fix(fg, colors, req, [-dirs[0]])
                strategy, major = "flip", True
            if fix is None:
                reason = (
                    "gradient_no_single_color" if not self._solid(members) else "no_passing_color"
                )
                for m in members:
                    self.unfixed.append(Unfixed(m.run_id, m.finding.run.slide_index, reason))
                continue
            fix = self._soft_text(fix, colors, req)
            if (
                strategy == "lightness"
                and deps
                and any(self._bg_strategy(d) == "background_and_text" for d in deps)
            ):
                strategy = "background_and_text"
            self._add_text(members, fg, fix, colors, list(deps), strategy, major)
        for (_fg, _ck, soft_deps), members in soften_groups.items():
            colors, _ = self.colors_for(members[0])
            req = self.policy.requirement(members[0].finding.large)
            for m in members[1:]:
                req = req.stricter(self.policy.requirement(m.finding.large))
            soft = self._soft_text(members[0].fg, colors, req)
            if soft.hex != members[0].fg.hex:
                self._add_text(
                    members,
                    members[0].fg,
                    soft,
                    colors,
                    list(soft_deps),
                    "soften",
                    False,
                    kind="soften_text",
                    rationale="soften_text",
                )

    def _bg_strategy(self, sid: str) -> str:
        for s in self.suggestions:
            if s.id == sid:
                return s.strategy
        return ""

    @staticmethod
    def _solid(members: list[_Ctx]) -> bool:
        return all(len(m.base_colors) == 1 for m in members)

    def _add_text(
        self,
        members: list[_Ctx],
        fg: RGB,
        fix: RGB,
        colors: list[RGB],
        deps: list[str],
        strategy: str,
        major: bool,
        *,
        kind: str = "text_color",
        rationale: str | None = None,
    ) -> Suggestion:
        orig_colors = [c for m in members for c in m.base_colors]
        before = min(contrast_ratio(fg, c) for c in orig_colors)
        after = min(contrast_ratio(fix, c) for c in colors)
        estimate = any(m.finding.run.background.certainty.value not in ("exact",) for m in members)
        suggestion = Suggestion(
            id=self._id(),
            kind=kind,
            strategy=strategy,
            major=major,
            run_ids=[m.run_id for m in members],
            slides=sorted({m.finding.run.slide_index for m in members}),
            original=fg,
            proposed=fix,
            depends_on=deps,
            rationale=rationale
            or {
                "lightness": "text_lightness",
                "flip": "text_flip",
                "background_and_text": "text_after_background",
            }.get(strategy, strategy),
            before_ratio=before,
            after_ratio=after,
            before_apca=min((apca_lc(fg, c) for c in orig_colors), key=abs),
            after_apca=min((apca_lc(fix, c) for c in colors), key=abs),
            estimate=estimate,
        )
        suggestion.affected_slides = suggestion.slides
        self.suggestions.append(suggestion)
        return suggestion

    def _scrims(self, ctxs: list[_Ctx]) -> None:
        by_shape: dict[str, list[_Ctx]] = defaultdict(list)
        for c in ctxs:
            anchor = c.finding.run.scrim_anchor
            if c.finding.run.background.samples and anchor is not None:
                by_shape[f"{anchor.part}#{anchor.shape_path}"].append(c)
            elif c.finding.status == Status.FAIL:
                self.unfixed.append(
                    Unfixed(c.run_id, c.finding.run.slide_index, "image_needs_renderer")
                )
        for members in by_shape.values():
            if all(self._ok(m) for m in members):
                continue
            samples = members[0].finding.run.background.samples
            slide = members[0].finding.run.slide_index
            dark, light = self.theme_by_slide.get(slide, (BLACK, WHITE))
            light_text = sum(relative_luminance(m.fg) for m in members) / len(members) > 0.18
            preferred = [dark, light] if light_text else [light, dark]
            steps = int(round((SCRIM_MAX_ALPHA - SCRIM_MIN_ALPHA) / 0.05)) + 1
            chosen: float | None = None
            scrim = preferred[0]
            for candidate in preferred:
                for i in range(steps):
                    alpha = round(SCRIM_MIN_ALPHA + 0.05 * i, 2)
                    comp = [
                        composite(candidate.with_alpha(alpha), x).opaque().quantized()
                        for x in samples
                    ]
                    if all(passes(m.fg, comp, m.req) for m in members):
                        if chosen is None or alpha < chosen:
                            chosen, scrim = alpha, candidate
                        break
            alpha = chosen if chosen is not None else SCRIM_MAX_ALPHA
            comp = [composite(scrim.with_alpha(alpha), x).opaque().quantized() for x in samples]
            anchor = members[0].finding.run.scrim_anchor
            sid = self._id()
            self.suggestions.append(
                Suggestion(
                    id=sid,
                    kind="scrim",
                    strategy="scrim",
                    major=False,
                    run_ids=[m.run_id for m in members],
                    slides=[slide],
                    original=None,
                    proposed=scrim.opaque(),
                    alpha=alpha,
                    scrim_anchor=anchor,
                    rationale="image_background",
                    before_ratio=min(contrast_ratio(m.fg, s) for m in members for s in samples),
                    after_ratio=min(contrast_ratio(m.fg, s) for m in members for s in comp),
                    estimate=True,
                    affected_slides=[slide],
                )
            )
            if chosen is not None:
                continue
            for m in members:
                if passes(m.fg, comp, m.req):
                    continue
                dirs = polarity(m.fg, comp)
                fix = best_text_fix(m.fg, comp, m.req, dirs)
                strategy, major = "lightness", False
                if fix is None and self.policy.allow_polarity_flip and len(dirs) == 1:
                    fix = best_text_fix(m.fg, comp, m.req, [-dirs[0]])
                    strategy, major = "flip", True
                if fix is None:
                    self.unfixed.append(Unfixed(m.run_id, slide, "image_no_passing_color"))
                    continue
                ctx = _Ctx(m.finding, m.fg, m.req, samples)
                s = self._add_text(
                    [ctx], m.fg, fix, comp, [sid], strategy, major, rationale="text_after_scrim"
                )
                s.estimate = True

    def _order(self) -> None:
        run_order = {f.run.id: i for i, f in enumerate(self.findings)}

        def key(s: Suggestion) -> tuple[int, int]:
            first = min((run_order.get(r, 0) for r in s.run_ids), default=0)
            return (min(s.slides) if s.slides else 0, first)

        old = sorted(self.suggestions, key=key)
        # Renumber deterministically by display order; remap dependencies.
        mapping: dict[str, str] = {}
        for i, s in enumerate(old, start=1):
            mapping[s.id] = f"s{i:03d}"
        for s in old:
            s.id = mapping[s.id]
            s.depends_on = [mapping.get(d, d) for d in s.depends_on]
        self.suggestions = old
        seen: set[str] = set()
        unique: list[Unfixed] = []
        for u in self.unfixed:
            if u.run_id not in seen:
                seen.add(u.run_id)
                unique.append(u)
        self.unfixed = unique


def suggest_corrections(
    inspection: Inspection, findings: list[Finding], policy: CorrectionPolicy
) -> CorrectionPlan:
    return Planner(inspection, findings, policy).plan()
