"""Public core operations used by every adapter (Web today, MCP/CLI later)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from . import __version__
from .analyze import Finding, Status, analyze, evaluate
from .correct import CorrectionPlan, Suggestion, suggest_corrections
from .errors import CorrectionConflict, RenderingFailure, RenderingUnavailable
from .model import Certainty, Inspection
from .policy import CorrectionPolicy
from .pptx.inspect import inspect_package
from .pptx.package import DEFAULT_LIMITS, PackageLimits, PptxPackage
from .pptx.writer import InsertScrim, Operation, SetFill, SetRunColor, apply_operations, strip_text
from .render import DEFAULT_DPI, PageImage, Renderer, RendererInfo, render_pptx
from .sampling import apply_samples

REPORT_SCHEMA_VERSION = "1.0"
ProgressFn = Callable[[str, float], None]


def _noop(stage: str, fraction: float) -> None:
    return None


@dataclass
class RenderOutcome:
    pages: list[PageImage] = field(default_factory=list)
    error: str | None = None


@dataclass
class AnalysisResult:
    package: PptxPackage
    inspection: Inspection
    findings: list[Finding]
    plan: CorrectionPlan
    policy: CorrectionPolicy
    renderer: RendererInfo | None
    original_pages: RenderOutcome
    sampled: int

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in Status}
        for f in self.findings:
            counts[f.status.value] += 1
        counts["total_runs"] = len(self.findings)
        counts["suggestions"] = len(self.plan.suggestions)
        counts["unfixed"] = len(self.plan.unfixed)
        counts["slides"] = len(self.inspection.slides)
        counts["slides_with_issues"] = len(
            {f.run.slide_index for f in self.findings if f.status == Status.FAIL}
        )
        return counts

    def report(self) -> dict[str, object]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "core_version": __version__,
            "source": {
                "filename": self.inspection.filename,
                "fingerprint": self.inspection.fingerprint,
                "slides": len(self.inspection.slides),
                "slide_size_emu": [self.inspection.slide_width, self.inspection.slide_height],
            },
            "policy": self.policy.to_dict(),
            "renderer": self.renderer.to_dict() if self.renderer else None,
            "render_error": self.original_pages.error,
            "rendered_backgrounds": self.sampled,
            "summary": self.summary(),
            "findings": [f.to_dict() for f in self.findings],
            "unsupported": [u.to_dict() for u in self.inspection.unsupported],
            "warnings": list(dict.fromkeys(self.inspection.warnings)),
            "plan": self.plan.to_dict(),
        }


def analyze_presentation(
    data: bytes,
    filename: str,
    policy: CorrectionPolicy,
    renderer: Renderer | None = None,
    *,
    dpi: int = DEFAULT_DPI,
    limits: PackageLimits = DEFAULT_LIMITS,
    progress: ProgressFn = _noop,
) -> AnalysisResult:
    progress("inspect", 0.05)
    package = PptxPackage(data, limits)
    inspection = inspect_package(package, filename)
    original = RenderOutcome()
    sampled = 0
    info = renderer.info if renderer is not None else None
    if renderer is not None:
        try:
            progress("render_original", 0.15)
            original.pages = render_pptx(renderer, data, dpi)
            if any(r.background.needs_render for r in inspection.runs):
                progress("render_backgrounds", 0.4)
                stripped = render_pptx(renderer, strip_text(package), dpi)
                sampled = apply_samples(inspection, stripped)
        except (RenderingFailure, RenderingUnavailable) as exc:
            original.error = exc.message
            inspection.warnings.append(f"rendering failed: {exc.message}")
    for run in inspection.runs:
        if run.background.needs_render and not run.background.colors():
            run.background.certainty = Certainty.UNKNOWN
    progress("analyze", 0.7)
    findings = analyze(inspection.runs, policy)
    plan = suggest_corrections(inspection, findings, policy)
    progress("done", 1.0)
    return AnalysisResult(package, inspection, findings, plan, policy, info, original, sampled)


@dataclass
class CorrectionResult:
    data: bytes
    applied: list[str]
    skipped: dict[str, str]
    verification: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "applied": self.applied,
            "skipped": self.skipped,
            "verification": self.verification,
        }


def _operations(result: AnalysisResult, suggestion: Suggestion) -> list[Operation]:
    runs = {r.id: r for r in result.inspection.runs}
    if suggestion.kind in ("text_color", "soften_text"):
        return [
            SetRunColor(
                runs[r].slide_part, runs[r].run_path, suggestion.proposed, runs[r].hyperlink
            )
            for r in suggestion.run_ids
            if r in runs
        ]
    if suggestion.kind in ("background_color", "saturation", "soften_background"):
        assert suggestion.target is not None
        return [SetFill(suggestion.target, suggestion.proposed)]
    if suggestion.kind == "scrim":
        assert suggestion.scrim_anchor is not None and suggestion.alpha is not None
        return [
            InsertScrim(
                suggestion.scrim_anchor,
                suggestion.proposed,
                suggestion.alpha,
                f"SlideLegible scrim {suggestion.id}",
            )
        ]
    return []


def apply_corrections(
    result: AnalysisResult, selected: list[str] | None = None, *, fingerprint: str | None = None
) -> CorrectionResult:
    """Apply selected suggestions (all when ``selected`` is None) to a new package."""
    if fingerprint is not None and fingerprint != result.package.fingerprint:
        raise CorrectionConflict("stale_plan", "The plan does not belong to this presentation.")
    by_id = result.plan.by_id()
    wanted = list(by_id) if selected is None else [s for s in selected if s in by_id]
    skipped: dict[str, str] = {s: "unknown_suggestion" for s in (selected or []) if s not in by_id}
    chosen: list[str] = []
    for sid in wanted:
        missing = [d for d in by_id[sid].depends_on if d not in wanted]
        if missing:
            skipped[sid] = "dependency_not_selected:" + ",".join(missing)
        else:
            chosen.append(sid)
    # Later suggestions for the same run override earlier ones (e.g. softening after a fix).
    ops: list[Operation] = []
    run_ops: dict[tuple[str, str], SetRunColor] = {}
    for sid in chosen:
        for op in _operations(result, by_id[sid]):
            if isinstance(op, SetRunColor):
                run_ops[(op.part, op.run_path)] = op
            else:
                ops.append(op)
    ops = [*run_ops.values(), *ops]
    data = apply_operations(result.package, ops) if ops else result.package.source_bytes
    verification = verify(result, data, chosen)
    return CorrectionResult(data, chosen, skipped, verification)


def verify(result: AnalysisResult, data: bytes, applied: list[str]) -> list[dict[str, object]]:
    """Re-inspect the output; re-check contrast where backgrounds are exact."""
    out_pkg = PptxPackage(data)
    out = inspect_package(out_pkg, result.inspection.filename)
    out_runs = {r.id: r for r in out.runs}
    by_id = result.plan.by_id()
    checks: list[dict[str, object]] = []
    for sid in applied:
        s = by_id[sid]
        for rid in s.run_ids:
            run = out_runs.get(rid)
            if run is None:
                checks.append({"suggestion": sid, "run": rid, "status": "missing"})
                continue
            if run.background.certainty != Certainty.EXACT:
                checks.append({"suggestion": sid, "run": rid, "status": "estimate"})
                continue
            finding = evaluate(run, result.policy)
            checks.append(
                {
                    "suggestion": sid,
                    "run": rid,
                    "status": "pass"
                    if finding.status in (Status.PASS, Status.DECORATIVE)
                    else "fail",
                    "ratio": round(finding.ratio or 0, 2),
                }
            )
    return checks
