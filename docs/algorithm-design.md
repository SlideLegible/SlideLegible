# Algorithm Design

## Contrast measurement

For WCAG 2.x, convert each sRGB channel to linear light using the WCAG transfer function, then compute relative luminance as `0.2126 R + 0.7152 G + 0.0722 B`. Contrast ratio is `(L lighter + 0.05) / (L darker + 0.05)`. Keep calculations in full precision and round only for display. Tests should cover reference pairs, black/white extremes, equal colors, and threshold boundaries.

Use WCAG 2.x as the MVP pass/fail criterion. Evaluate font size and weight to select normal- or large-text thresholds when source metadata is sufficiently resolved. If it is not, report the uncertain classification and avoid claiming a definitive pass based on an unsupported assumption.

APCA may be reported as a supplementary readability metric only after selecting and pinning a compatible specification/version. It must not replace WCAG pass/fail in MVP, and the report must identify its version and avoid presenting an APCA value as a WCAG ratio.

## Alpha and compositing

Composite foreground/background colors using source alpha and the actual stacking order in linear-light sRGB when those inputs are known. Transparency inherited from fills and effects may require OOXML resolution or rendering. If the effective composite cannot be recovered, report an estimate or unresolved background rather than treating an arbitrary base color as exact.

## Background resolution

Use a tiered approach:

1. Resolve solid shape, slide, layout, and master fills from OOXML when inheritance and modifiers are understood.
2. Resolve simple transparency and shape overlap from package geometry when feasible.
3. Render a slide when gradients, images, effects, layering, or unresolved inheritance determine the pixels behind text.
4. Sample pixels from the rendered region behind glyphs, excluding glyph pixels and accounting for antialiasing as far as practical. Summarize a representative distribution, not just one pixel.

Tag observations as `exact`, `derived`, `rendered_estimate`, or `unknown`, with evidence and confidence. Background sampling is intrinsically difficult around partially transparent text, shadows, overlapping shapes, and gradients. LibreOffice can differ from PowerPoint in font substitution, effects, and rendering; preserve renderer/version metadata and allow users to inspect previews.

## Correction search

Convert candidate sRGB colors to OKLCH and search lightness first while holding hue and chroma as stable as possible. For each candidate, convert back to sRGB, apply the actual compositing model, and recalculate WCAG contrast. Search both lighter and darker directions where allowed, then rank passing candidates by perceptual change and policy preferences. Do not assume constant hue/chroma will remain in gamut.

When a candidate is out of gamut, use a documented chroma-reduction/gamut-mapping procedure and recalculate in sRGB. Include a safety margin for channel quantization and compositing; never report a proposed color as passing until the serialized color has been re-evaluated. Explain which side changes and the expected visual delta.

Prefer consistent mappings for repeated uses of the same source color and context, but do not force one color mapping across distinct backgrounds if it would fail contrast. Record conflicts where shared theme colors or inherited formatting make a local edit affect other text. Default to editing the text color when safe; consider changing the background only when policy permits and scope is explicit. If neither side can be changed safely, report that no safe suggestion is available.

## Minimizing changes

Apply only selected suggestions, retain source formatting, and avoid modifying unreferenced OOXML parts. A writer should preserve source color semantics (theme reference versus explicit RGB) when a safe equivalent can be represented. If the correction would change shared theme behavior or requires restructuring unsupported content, surface the risk for review or skip it. Preview and correction reports must state whether contrast was rechecked against an exact or estimated background.
