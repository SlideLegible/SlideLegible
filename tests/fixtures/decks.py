"""Synthetic, purpose-built PPTX fixtures.

Every deck is generated from code with python-pptx plus small OOXML edits, so
the fixtures carry no third-party content. Run this module to write the decks
to a folder for manual testing::

    uv run python tests/fixtures/decks.py out/
"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from pathlib import Path

import pymupdf
from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE
from pptx.presentation import Presentation as PresentationType
from pptx.slide import Slide
from pptx.util import Inches, Pt

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
BLANK = 6
TITLE_ONLY = 5


def _new() -> PresentationType:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def _textbox(
    slide: Slide,
    text: str,
    rgb: str | None,
    *,
    left: float = 1,
    top: float = 1,
    width: float = 8,
    height: float = 1.2,
    size: int = 28,
    bold: bool = False,
) -> object:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.text = text
    run = tf.paragraphs[0].runs[0]
    run.font.size = Pt(size)
    run.font.bold = bold
    if rgb is not None:
        run.font.color.rgb = RGBColor.from_string(rgb)
    return box


def _solid_bg(slide_or_layout: object, rgb: str) -> None:
    fill = slide_or_layout.background.fill  # type: ignore[attr-defined]
    fill.solid()
    fill.fore_color.rgb = RGBColor.from_string(rgb)


def _gradient_bg(slide: Slide, start: str, end: str) -> None:
    fill = slide.background.fill
    fill.gradient()
    fill.gradient_angle = 0
    stops = fill.gradient_stops
    stops[0].color.rgb = RGBColor.from_string(start)
    stops[1].color.rgb = RGBColor.from_string(end)


def noisy_png(width: int = 160, height: int = 90, seed: int = 7) -> bytes:
    """A deterministic busy picture with light and dark patches."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), 0)
    state = seed
    block = 10
    for y in range(0, height, block):
        for x in range(0, width, block):
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            bright = (state >> 8) & 1
            r = 200 + (state >> 3) % 55 if bright else (state >> 3) % 70
            g = 190 + (state >> 5) % 60 if bright else (state >> 5) % 60
            b = 120 + (state >> 7) % 120
            pix.set_rect(pymupdf.IRect(x, y, x + block, y + block), (r, g, b))
    return bytes(pix.tobytes("png"))


def _set_run_alpha(run: object, alpha_pct: int) -> None:
    r_pr = run._r.get_or_add_rPr()  # type: ignore[attr-defined]
    srgb = r_pr.find(f"{{{A_NS}}}solidFill/{{{A_NS}}}srgbClr")
    if srgb is not None:
        etree.SubElement(srgb, f"{{{A_NS}}}alpha", val=str(alpha_pct * 1000))


def _save(prs: PresentationType) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# --- individual decks -----------------------------------------------------------------


def deck_basic() -> bytes:
    """Explicit colors on the default white master background."""
    prs = _new()
    s = prs.slides.add_slide(prs.slide_layouts[BLANK])
    _textbox(s, "Pale yellow on white", "FFFF66")
    _textbox(s, "Readable dark text", "222222", top=3)
    _textbox(s, "Light gray caption text", "AAAAAA", top=5, size=12)
    return _save(prs)


def deck_dark_slide() -> bytes:
    """Dark slide background with a low-contrast title."""
    prs = _new()
    s = prs.slides.add_slide(prs.slide_layouts[BLANK])
    _solid_bg(s, "2E3B4E")
    _textbox(s, "Navy title on navy background", "4A5A75", size=40, bold=True)
    return _save(prs)


def deck_theme_text() -> bytes:
    """Placeholder text that inherits theme tx1 on a dark slide background."""
    prs = _new()
    s = prs.slides.add_slide(prs.slide_layouts[TITLE_ONLY])
    _solid_bg(s, "333333")
    assert s.shapes.title is not None
    s.shapes.title.text = "Inherited dark title"
    return _save(prs)


def deck_shape_style() -> bytes:
    """Autoshape whose white text comes from p:style/fontRef on a pale fill."""
    prs = _new()
    s = prs.slides.add_slide(prs.slide_layouts[BLANK])
    shape = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(6), Inches(2))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string("9DC3E6")
    shape.text_frame.text = "White style text on pale blue"
    shape.text_frame.paragraphs[0].runs[0].font.size = Pt(24)
    return _save(prs)


def deck_layout_background() -> bytes:
    """Two slides share a layout with a mid-gray background."""
    prs = _new()
    layout = prs.slide_layouts[BLANK]
    _solid_bg(layout, "808080")
    s1 = prs.slides.add_slide(layout)
    _textbox(s1, "Light gray on mid gray", "A0A0A0", size=24)
    s2 = prs.slides.add_slide(layout)
    _textbox(s2, "Black text that passes", "000000", size=24)
    return _save(prs)


def deck_gradients() -> bytes:
    prs = _new()
    s1 = prs.slides.add_slide(prs.slide_layouts[BLANK])
    _gradient_bg(s1, "FFFFFF", "000000")
    _textbox(s1, "Gray text across a black-to-white gradient", "808080", size=24)
    s2 = prs.slides.add_slide(prs.slide_layouts[BLANK])
    _gradient_bg(s2, "F2F2F2", "D0D0D0")
    _textbox(s2, "Gray text on a soft gradient", "999999", size=24)
    return _save(prs)


def deck_image() -> bytes:
    prs = _new()
    s = prs.slides.add_slide(prs.slide_layouts[BLANK])
    s.shapes.add_picture(io.BytesIO(noisy_png()), 0, 0, prs.slide_width, prs.slide_height)
    _textbox(s, "White text on a busy photo", "FFFFFF", size=32, bold=True)
    s2 = prs.slides.add_slide(prs.slide_layouts[BLANK])
    s2.shapes.add_picture(io.BytesIO(noisy_png(seed=11)), 0, 0, prs.slide_width, prs.slide_height)
    overlay = s2.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(0.5), Inches(9), Inches(2)
    )
    overlay.fill.solid()
    overlay.fill.fore_color.rgb = RGBColor(0, 0, 0)
    overlay.line.fill.background()
    srgb = overlay.fill._xPr.find(f"{{{A_NS}}}solidFill/{{{A_NS}}}srgbClr")  # type: ignore[attr-defined]
    etree.SubElement(srgb, f"{{{A_NS}}}alpha", val="40000")
    _textbox(s2, "Gray text on a translucent overlay", "999999", left=1, top=1, size=28)
    return _save(prs)


def deck_table() -> bytes:
    prs = _new()
    s = prs.slides.add_slide(prs.slide_layouts[BLANK])
    table = s.shapes.add_table(3, 2, Inches(1), Inches(1), Inches(8), Inches(2)).table
    for r in range(3):
        for c in range(2):
            cell = table.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string("FFF2CC" if r else "4472C4")
            cell.text = f"Cell {r},{c}"
            cell.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(
                "FFD966" if r else "FFFFFF"
            )
    return _save(prs)


def deck_misc() -> bytes:
    """Watermark, hyperlink, chart, pure black/white, saturated red."""
    prs = _new()
    s1 = prs.slides.add_slide(prs.slide_layouts[BLANK])
    box = _textbox(s1, "DRAFT", "C0C0C0", size=96, top=2, height=2)
    _set_run_alpha(box.text_frame.paragraphs[0].runs[0], 30)  # type: ignore[attr-defined]
    link_box = _textbox(s1, "Visit the course page", None, top=5, size=20)
    run = link_box.text_frame.paragraphs[0].runs[0]  # type: ignore[attr-defined]
    run.hyperlink.address = "https://example.com/"
    # Make the theme hyperlink color pale so the link fails contrast.
    data = CategoryChartData()
    data.categories = ["A", "B"]
    data.add_series("S", (1, 2))
    s1.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(9), Inches(1), Inches(3), Inches(3), data
    )

    s2 = prs.slides.add_slide(prs.slide_layouts[BLANK])
    _solid_bg(s2, "000000")
    _textbox(s2, "Pure white on pure black", "FFFFFF", size=24)

    s3 = prs.slides.add_slide(prs.slide_layouts[BLANK])
    _solid_bg(s3, "FF0000")
    _textbox(s3, "White on saturated red", "FFFFFF", size=16)

    blob = _save(prs)
    # Lighten the theme's hlink color to a pale cyan.
    prs2 = Presentation(io.BytesIO(blob))
    master = prs2.slide_masters[0]
    theme_part = master.part.part_related_by(
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
    )
    root = etree.fromstring(theme_part.blob)
    hlink = root.find(f".//{{{A_NS}}}clrScheme/{{{A_NS}}}hlink")
    if hlink is not None:
        for ch in list(hlink):
            hlink.remove(ch)
        etree.SubElement(hlink, f"{{{A_NS}}}srgbClr", val="99E6FF")
    theme_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return _save(prs2)


def deck_group() -> bytes:
    """A filled rectangle and text box inside a scaled group."""
    prs = _new()
    s = prs.slides.add_slide(prs.slide_layouts[BLANK])
    group = s.shapes.add_group_shape()
    rect = group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(6), Inches(2))
    rect.fill.solid()
    rect.fill.fore_color.rgb = RGBColor.from_string("1F3864")
    rect.line.fill.background()
    _textbox(group, "Dark blue text inside a group", "203864", left=1.5, top=1.4, width=5)  # type: ignore[arg-type]
    return _save(prs)


DECKS: dict[str, Callable[[], bytes]] = {
    "basic": deck_basic,
    "dark_slide": deck_dark_slide,
    "theme_text": deck_theme_text,
    "shape_style": deck_shape_style,
    "layout_background": deck_layout_background,
    "gradients": deck_gradients,
    "image": deck_image,
    "table": deck_table,
    "misc": deck_misc,
    "group": deck_group,
}


def demo_deck() -> bytes:
    """All fixture slides combined into one deck (for manual testing)."""
    out = _new()
    blank = out.slide_layouts[BLANK]
    title_only = out.slide_layouts[TITLE_ONLY]

    s = out.slides.add_slide(title_only)
    _solid_bg(s, "2E3B4E")
    assert s.shapes.title is not None
    s.shapes.title.text = "SlideLegible 示範簡報"
    _textbox(s, "深藍底配深藍字：很難讀的副標題", "4A5A75", top=3.5, size=28)

    s = out.slides.add_slide(blank)
    _textbox(s, "白底淡黃字 Pale yellow on white", "FFFF66", size=32)
    _textbox(s, "淺灰色的小字註解，常常看不清楚", "AAAAAA", top=3, size=14)
    _textbox(s, "這行是正常的深灰字", "333333", top=5, size=20)

    s = out.slides.add_slide(blank)
    shape = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(1), Inches(7), Inches(2.2)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string("9DC3E6")
    shape.text_frame.text = "淺藍色塊上的白字"
    shape.text_frame.paragraphs[0].runs[0].font.size = Pt(28)
    _textbox(s, "鮮紅底白字（過飽和）", "FFFFFF", top=4.2, size=16)
    red = s.shapes[-1]
    red.fill.solid()  # type: ignore[attr-defined]
    red.fill.fore_color.rgb = RGBColor.from_string("FF0000")  # type: ignore[attr-defined]

    s = out.slides.add_slide(blank)
    _gradient_bg(s, "F2F2F2", "C8C8C8")
    _textbox(s, "柔和漸層上的灰字", "A6A6A6", size=28)
    s = out.slides.add_slide(blank)
    _gradient_bg(s, "FFFFFF", "000000")
    _textbox(s, "黑白漸層上的灰字：任何字色都救不了", "808080", size=28, width=11)

    s = out.slides.add_slide(blank)
    s.shapes.add_picture(io.BytesIO(noisy_png()), 0, 0, out.slide_width, out.slide_height)
    _textbox(s, "照片背景上的白字", "FFFFFF", size=36, bold=True)

    s = out.slides.add_slide(blank)
    table = s.shapes.add_table(3, 2, Inches(1), Inches(1), Inches(8), Inches(2)).table
    for r in range(3):
        for c in range(2):
            cell = table.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string("FFF2CC" if r else "4472C4")
            cell.text = "表頭" if r == 0 else f"資料 {r}-{c}"
            cell.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(
                "FFFFFF" if r == 0 else "FFD966"
            )
    box = _textbox(s, "草稿", "C0C0C0", top=4, size=96, height=2)
    _set_run_alpha(box.text_frame.paragraphs[0].runs[0], 30)  # type: ignore[attr-defined]

    s = out.slides.add_slide(blank)
    _solid_bg(s, "000000")
    _textbox(s, "純黑底純白字（可開啟柔化）", "FFFFFF", size=28)
    return _save(out)


def write_all(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, builder in {**DECKS, "demo": demo_deck}.items():
        path = directory / f"{name}.pptx"
        path.write_bytes(builder())
        written.append(path)
    return written


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures-out")
    for p in write_all(target):
        print(p)
