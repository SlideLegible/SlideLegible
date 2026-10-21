"""Estimate backgrounds behind text from a rendered, text-free copy of the deck."""

from __future__ import annotations

from .color import RGB, contrast_ratio, relative_luminance
from .model import BackgroundKind, Certainty, Inspection, Rect
from .render import PageImage

PERCENTILES = (2, 10, 25, 50, 75, 90, 98)
UNIFORM_RATIO = 1.1  # p2 vs p98 contrast below this counts as a flat color
MAX_SAMPLES = 6_000


def map_pages(inspection: Inspection, page_count: int) -> dict[int, int]:
    """Map slide index -> page index, accounting for hidden slides being skipped."""
    if page_count == len(inspection.slides):
        return {s.index: i for i, s in enumerate(inspection.slides)}
    visible = [s for s in inspection.slides if not s.hidden]
    if page_count == len(visible):
        return {s.index: i for i, s in enumerate(visible)}
    return {}


def sample_region(page: PageImage, area: Rect, slide_w: int, slide_h: int) -> list[RGB]:
    x0 = max(0, int(area.x / slide_w * page.width))
    y0 = max(0, int(area.y / slide_h * page.height))
    x1 = min(page.width, int(area.right / slide_w * page.width + 0.5))
    y1 = min(page.height, int(area.bottom / slide_h * page.height + 0.5))
    if x1 <= x0 or y1 <= y0:
        return []
    count = (x1 - x0) * (y1 - y0)
    step = max(1, int((count / MAX_SAMPLES) ** 0.5))
    pixels: list[tuple[float, RGB]] = []
    for y in range(y0, y1, step):
        for x in range(x0, x1, step):
            r, g, b = page.pixel(x, y)
            color = RGB.from_255(r, g, b)
            pixels.append((relative_luminance(color), color))
    pixels.sort(key=lambda item: item[0])
    n = len(pixels)
    return [pixels[min(n - 1, int(p / 100 * (n - 1) + 0.5))][1] for p in PERCENTILES]


def apply_samples(inspection: Inspection, pages: list[PageImage]) -> int:
    """Replace unresolved backgrounds with rendered estimates. Returns the count updated."""
    mapping = map_pages(inspection, len(pages))
    if not mapping:
        inspection.warnings.append(
            f"rendered page count ({len(pages)}) does not match slide count; sampling skipped"
        )
        return 0
    updated = 0
    for run in inspection.runs:
        bg = run.background
        if not bg.needs_render or run.text_area is None:
            continue
        page_index = mapping.get(run.slide_index)
        if page_index is None:
            continue
        samples = sample_region(
            pages[page_index], run.text_area, inspection.slide_width, inspection.slide_height
        )
        if not samples:
            continue
        lo, hi = samples[0], samples[-1]
        bg.certainty = Certainty.RENDERED
        bg.needs_render = False
        if contrast_ratio(lo, hi) < UNIFORM_RATIO:
            bg.color = samples[len(samples) // 2]
            bg.samples = []
            if bg.kind in (BackgroundKind.COMPLEX, BackgroundKind.UNKNOWN):
                bg.kind = BackgroundKind.SOLID
        else:
            bg.samples = samples
            bg.color = None
            if bg.kind == BackgroundKind.UNKNOWN:
                bg.kind = BackgroundKind.COMPLEX
        bg.layers.append("rendered sample of the area behind the text")
        updated += 1
    return updated
