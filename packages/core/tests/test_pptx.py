"""Fixture-driven tests for inspection, planning, and writing (no renderer)."""

from __future__ import annotations

import io
import zipfile

import decks
import pytest
from pptx import Presentation
from slidelegible.analyze import Status, analyze
from slidelegible.api import analyze_presentation, apply_corrections
from slidelegible.color import contrast_ratio
from slidelegible.errors import InvalidInput
from slidelegible.model import BackgroundKind, Certainty
from slidelegible.policy import get_policy
from slidelegible.pptx.inspect import inspect_package
from slidelegible.pptx.package import PptxPackage
from slidelegible.pptx.writer import strip_text

COMFORT = get_policy("comfortable")


def _inspect(data: bytes):  # type: ignore[no-untyped-def]
    return inspect_package(PptxPackage(data))


def _result(data: bytes, soften: bool = False):  # type: ignore[no-untyped-def]
    return analyze_presentation(data, "t.pptx", get_policy("comfortable", soften=soften), None)


def test_rejects_non_zip() -> None:
    with pytest.raises(InvalidInput):
        PptxPackage(b"not a zip")


def test_rejects_path_traversal() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("../evil.xml", "<x/>")
    with pytest.raises(InvalidInput):
        PptxPackage(buf.getvalue())


def test_xml_entities_are_not_expanded() -> None:
    data = decks.deck_basic()
    pkg = PptxPackage(data)
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
    pkg.parts["evil.xml"] = evil
    root = pkg.xml("evil.xml")
    assert "root:" not in (root.text or "")


def test_explicit_colors_on_master_background() -> None:
    insp = _inspect(decks.deck_basic())
    yellow = insp.runs[0]
    assert yellow.color.hex == "FFFF66"
    assert yellow.background.kind == BackgroundKind.SOLID
    assert yellow.background.certainty == Certainty.EXACT
    assert yellow.background.color is not None and yellow.background.color.hex == "FFFFFF"
    assert yellow.background.editable is not None
    assert yellow.background.editable.kind == "master_background"


def test_theme_text_inherits_master_title_style() -> None:
    run = _inspect(decks.deck_theme_text()).runs[0]
    assert run.color_source == "master titleStyle"
    assert run.color.hex == "000000"
    assert run.size_pt == 44.0


def test_shape_style_font_ref_color() -> None:
    run = _inspect(decks.deck_shape_style()).runs[0]
    assert run.color_source == "shape style (fontRef)"
    assert run.color.hex == "FFFFFF"
    assert run.background.color is not None and run.background.color.hex == "9DC3E6"


def test_group_child_background() -> None:
    run = _inspect(decks.deck_group()).runs[0]
    assert run.background.color is not None and run.background.color.hex == "1F3864"


def test_table_cells_and_hyperlink_and_chart() -> None:
    table = _inspect(decks.deck_table()).runs
    assert [r.cell for r in table][:2] == [(0, 0), (0, 1)]
    assert table[2].background.color is not None and table[2].background.color.hex == "FFF2CC"
    misc = _inspect(decks.deck_misc())
    link = next(r for r in misc.runs if r.hyperlink)
    assert link.color.hex == "99E6FF"
    assert [u.kind for u in misc.unsupported] == ["chart"]


def test_gradient_and_image_backgrounds_without_renderer() -> None:
    grad = _inspect(decks.deck_gradients()).runs[0]
    assert grad.background.kind == BackgroundKind.GRADIENT
    assert {c.hex for c in grad.background.samples} == {"FFFFFF", "000000"}
    image = _inspect(decks.deck_image()).runs[0]
    assert image.background.kind == BackgroundKind.IMAGE
    assert image.background.needs_render


def test_decorative_watermark_is_skipped() -> None:
    insp = _inspect(decks.deck_misc())
    findings = analyze(insp.runs, COMFORT)
    watermark = next(f for f in findings if f.run.excerpt == "DRAFT")
    assert watermark.status == Status.DECORATIVE


def test_text_fix_keeps_hue_and_passes() -> None:
    result = _result(decks.deck_dark_slide())
    (s,) = result.plan.suggestions
    assert s.kind == "text_color" and s.strategy == "lightness"
    delta = s.delta()
    assert delta is not None and delta["hue"] < 3
    assert s.after_ratio is not None and s.after_ratio >= 4.5


def test_layout_background_change_refixes_other_slides() -> None:
    result = _result(decks.deck_layout_background())
    kinds = [(s.kind, s.depends_on) for s in result.plan.suggestions]
    bg = next(s for s in result.plan.suggestions if s.kind == "background_color")
    assert bg.target is not None and bg.target.kind == "layout_background"
    assert bg.affected_slides == [1, 2]
    dependents = [s for s in result.plan.suggestions if bg.id in s.depends_on]
    assert {r for s in dependents for r in s.run_ids} == {"s1-sh2-p0-r0", "s2-sh2-p0-r0"}, kinds


def test_unfixable_gradient_is_reported() -> None:
    result = _result(decks.deck_gradients())
    assert [u.reason for u in result.plan.unfixed] == ["gradient_no_single_color"]


def test_apply_all_and_verify() -> None:
    data = decks.deck_basic()
    result = _result(data)
    out = apply_corrections(result)
    assert out.applied == [s.id for s in result.plan.suggestions]
    assert all(v["status"] == "pass" for v in out.verification)
    after = _result(out.data)
    assert all(f.status == Status.PASS for f in after.findings)
    # The output opens in python-pptx and unrelated parts are byte-identical.
    Presentation(io.BytesIO(out.data))
    src, dst = PptxPackage(data), PptxPackage(out.data)
    changed = {n for n in src.parts if src.parts[n] != dst.parts.get(n)}
    assert changed == {"ppt/slides/slide1.xml"}


def test_apply_selected_skips_missing_dependencies() -> None:
    result = _result(decks.deck_layout_background())
    dependent = next(s for s in result.plan.suggestions if s.depends_on)
    out = apply_corrections(result, [dependent.id])
    assert out.applied == []
    assert dependent.id in out.skipped


def test_stale_plan_is_rejected() -> None:
    from slidelegible.errors import CorrectionConflict

    result = _result(decks.deck_basic())
    with pytest.raises(CorrectionConflict):
        apply_corrections(result, fingerprint="0" * 64)


def test_hyperlink_fix_adds_color_extension() -> None:
    result = _result(decks.deck_misc())
    out = apply_corrections(result)
    slide = PptxPackage(out.data).parts["ppt/slides/slide1.xml"].decode()
    assert "A12FA001-AC4F-418D-AE19-62706E023703" in slide
    link = next(r for r in _inspect(out.data).runs if r.hyperlink)
    assert link.color.hex != "99E6FF"


def test_softening_pure_black_and_white() -> None:
    result = _result(decks.deck_misc(), soften=True)
    kinds = {s.kind: s for s in result.plan.suggestions}
    assert kinds["soften_background"].proposed.hex == "121212"
    assert kinds["soften_text"].proposed.hex == "F0F0F0"
    for s in result.plan.suggestions:
        if s.kind.startswith("soften") and s.after_ratio is not None:
            assert s.after_ratio >= 4.5


def test_saturated_background_is_reduced() -> None:
    result = _result(decks.demo_deck())
    sat = [s for s in result.plan.suggestions if s.target and s.target.color.hex == "FF0000"]
    assert sat, "red background should be adjusted"
    from slidelegible.color import rgb_to_oklch

    assert rgb_to_oklch(sat[0].proposed).c <= 0.2001


def test_strip_text_removes_slide_text_only() -> None:
    data = decks.deck_basic()
    stripped = PptxPackage(strip_text(PptxPackage(data)))
    assert all(not r.excerpt.strip() for r in inspect_package(stripped).runs) or not (
        inspect_package(stripped).runs
    )


def test_contrast_of_each_fix_is_rechecked_on_8bit_values() -> None:
    result = _result(decks.demo_deck())
    for s in result.plan.suggestions:
        if s.kind == "text_color" and not s.estimate:
            assert s.proposed == s.proposed.quantized()
            runs = {r.id: r for r in result.inspection.runs}
            for rid in s.run_ids:
                bg = runs[rid].background
                if s.depends_on or bg.color is None:
                    continue
                assert contrast_ratio(s.proposed, bg.color) >= 4.5
