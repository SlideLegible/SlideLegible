"""Renderer plumbing tests that need no office suite (x2t is faked)."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import decks
import pytest
from slidelegible.api import analyze_presentation
from slidelegible.model import Certainty
from slidelegible.policy import get_policy
from slidelegible.render import OnlyOfficeRenderer, rasterize, render_pptx
from slidelegible.sampling import map_pages

FAKE_X2T = """#!{python}
import sys, xml.etree.ElementTree as ET
import pymupdf
task = ET.parse(sys.argv[1]).getroot()
assert task.findtext("m_nFormatTo") == "513"
assert task.findtext("m_sAllFontsPath").endswith("AllFonts.js")
doc = pymupdf.open()
for _ in range(int(open({count_file!r}).read())):
    page = doc.new_page(width=960, height=540)
    page.draw_rect(page.rect, color=None, fill=(0, 0, 0))
doc.save(task.findtext("m_sFileTo"))
"""


@pytest.fixture()
def fake_onlyoffice(tmp_path: Path) -> OnlyOfficeRenderer:
    if os.name == "nt":
        pytest.skip("fake x2t uses a shebang script")
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "AllFonts.js").write_text("// fonts")
    count = tmp_path / "count.txt"
    count.write_text("2")
    script = tmp_path / "x2t"
    script.write_text(FAKE_X2T.format(python=sys.executable, count_file=str(count)))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return OnlyOfficeRenderer(str(script), str(fonts))


def test_task_xml_escapes_paths(tmp_path: Path) -> None:
    fonts = tmp_path / "f&onts"
    fonts.mkdir()
    (fonts / "AllFonts.js").write_text("")
    renderer = OnlyOfficeRenderer("x2t", str(fonts))
    xml = renderer.task_xml(tmp_path / "a<b>.pptx", tmp_path / "out.pdf", tmp_path)
    assert "a&lt;b&gt;.pptx" in xml and "f&amp;onts" in xml
    assert "<m_nFormatTo>513</m_nFormatTo>" in xml


def test_missing_font_cache_marks_unavailable(tmp_path: Path) -> None:
    renderer = OnlyOfficeRenderer(str(tmp_path / "x2t"), None)
    renderer.fonts_dir = None
    assert not renderer.info.available


def test_fake_x2t_render_and_sampling(fake_onlyoffice: OnlyOfficeRenderer) -> None:
    pages = render_pptx(fake_onlyoffice, decks.deck_image(), dpi=40)
    assert len(pages) == 2 and pages[0].png.startswith(b"\x89PNG")
    result = analyze_presentation(
        decks.deck_image(), "x.pptx", get_policy("comfortable"), fake_onlyoffice
    )
    assert result.sampled >= 1
    run = result.inspection.runs[0]
    # The fake renderer paints every page black.
    assert run.background.certainty == Certainty.RENDERED
    assert run.background.color is not None and run.background.color.hex == "000000"


def test_page_mapping_with_hidden_slides() -> None:
    from slidelegible.pptx.inspect import inspect_package
    from slidelegible.pptx.package import PptxPackage

    insp = inspect_package(PptxPackage(decks.deck_layout_background()))
    assert map_pages(insp, 2) == {1: 0, 2: 1}
    insp.slides[0].hidden = True
    assert map_pages(insp, 1) == {2: 0}
    assert map_pages(insp, 5) == {}


def test_rasterize_rejects_garbage(tmp_path: Path) -> None:
    from slidelegible.errors import RenderingFailure

    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"nope")
    with pytest.raises(RenderingFailure):
        rasterize(bad)
