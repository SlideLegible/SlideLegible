# PowerPoint Processing

## Package and extraction model

A `.pptx` is an OOXML ZIP package containing presentation, slide, layout, master, theme, relationship, media, and other parts. Validate package structure and resource limits before parsing. Use `python-pptx` for supported presentation traversal and `lxml` for targeted reads or edits where the higher-level API does not expose required details. Do not reconstruct an entire presentation from extracted objects.

Text is spread across shapes, paragraphs, runs, tables, grouped shapes, placeholders, and possibly charts or SmartArt. The MVP should explicitly define which of these are supported and report unsupported or partially inspected content. Stable element references should include slide, shape, paragraph, and run location within an input fingerprint.

## Effective color resolution

Resolve direct run formatting first, then paragraph/list style, placeholder style, layout/master defaults, and theme defaults according to OOXML precedence. Theme colors map through the theme color scheme; DrawingML color transforms such as tint, shade, luminance, alpha, and gamma operations must be applied in specified order. Preserve both the resolved sRGB result and the source expression for diagnostics and safe writing.

Fallback inheritance is context-sensitive. Avoid silently substituting black or white when a reference is missing or unsupported; report unresolved source details. Text fill may itself be a gradient or effect and should be treated as unsupported for automatic rewriting until validated.

## Complex content

- **Tables:** cells can have inherited table-style fills and text styles; determine supported style resolution before claiming effective contrast.
- **Groups:** coordinates and overlap require transforming child geometry through group transforms.
- **Images and gradients:** require rendering and regional sampling for effective background estimates.
- **Transparency and effects:** compositing, glow, shadow, and anti-aliasing can affect apparent contrast; report when not modeled.
- **Charts, SmartArt, embedded objects, and custom XML:** may contain text and formatting outside the simple shape traversal model. Exclude or inspect only when safely supported.

`python-pptx` does not expose all OOXML features or preserve every unknown extension with equal guarantees under all edit patterns. This is why low-level part preservation, targeted writes, and regression fixtures are required.

## Rendering boundary

LibreOffice headless should be invoked only by a renderer adapter with controlled input/output directories, execution timeout, memory/resource limits, and captured version. Convert to PDF and then rasterize selected pages using a chosen maintained PDF/image tool. Rendering failure should not prevent color-only analysis where exact XML information suffices. Do not invoke a renderer in unit tests for pure algorithms.

## Safe modification and preservation

1. Keep the original immutable and work on a copy of the package.
2. Revalidate the source fingerprint and suggestion target before applying changes.
3. Edit only the target run/shape properties and required relationships; preserve unknown parts and ordering where possible.
4. Preserve layouts, geometry, text formatting unrelated to color, theme relationships, media, animations, notes, and embedded objects by avoiding broad serialization/recreation.
5. Reopen and validate the resulting package, verify targeted color values, and compare inventories/hashes of unrelated parts where feasible.
6. Emit an explicit warning or skip a suggestion if it requires changing shared theme semantics, modifying unsupported text types, altering an image, changing animation/effect behavior, or editing embedded content unsafely.

Successful ZIP creation is not proof of fidelity. Round-trip and visual checks should establish which content classes are supported. The report should list applied, skipped, and unverified changes.

## Security and resource limits

Treat uploaded files as untrusted ZIP/XML input. Reject path traversal entries, malformed archives, excessive expansion ratios, oversized parts, entity-expansion risks, and resource exhaustion. Disable unsafe XML entity behavior. Run rendering in an isolated process/container without network access where possible. Enforce file-size, slide-count, extraction-size, time, and memory limits at deployment boundaries.
