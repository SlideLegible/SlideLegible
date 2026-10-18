# Testing Strategy

Testing must distinguish deterministic domain behavior from renderer- and platform-dependent behavior. The core should be useful and testable without LibreOffice.

## Test layers

1. **Pure unit tests:** WCAG luminance/ratio, thresholds, APCA version behavior, sRGB/OKLCH conversion, gamut mapping, alpha compositing, policy ranking, stable serialization.
2. **Core component tests:** OOXML color resolution, theme modifiers, inheritance precedence, text extraction, correction planning, report generation, targeted writes.
3. **PPTX regression tests:** minimal fixtures for themes, master/layout/placeholder inheritance, runs, tables, grouped shapes, gradients, images, transparency, modifiers, unsupported content, and malformed packages.
4. **Round-trip/preservation tests:** open exported files, validate targeted changes, compare unrelated package-part inventories and hashes, and verify notes/media/relationships/animations remain present where applicable.
5. **Renderer tests:** render known fixtures with pinned LibreOffice/PDF conversion versions; compare image metrics or reviewed baselines with tolerances for font/platform variance.
6. **Adapter integration tests:** exercise Web endpoints and MCP tools against the same core inputs; assert matching issue IDs, metrics, policies, and correction outcomes after protocol normalization.
7. **Operational/security tests:** archive bombs, path traversal, malformed XML, XML entity attacks, oversized inputs, timeouts, unauthorized artifact access, cleanup, and output isolation.
8. **Performance checks:** track parse/analyze/render time and peak resource use across representative slide counts and image-heavy documents.

## Fixtures and visual baselines

Build purpose-made, small `.pptx` fixtures that isolate one behavior each. Record fixture purpose, expected behavior, creation method, and license/provenance. Avoid customer decks and copyrighted sample decks unless redistribution rights are clear. Keep canonical inputs stable; review fixture changes explicitly. Store binary fixtures only when small enough for repository policy; otherwise use a controlled fixture source with checksums.

Golden images should be limited to representative rendering cases, tagged with renderer and font environment, and reviewed when baselines change. Pixel-perfect equality is inappropriate across all environments; use tolerances and human review for visual fidelity. Algorithm tests must use explicit color samples and never depend on renderer output.

## Coverage expectations

- Verify contrast reference values, threshold edges, large-text classification, transparency, and unsupported assumptions.
- Test OKLCH round trips, hue/lightness behavior, gamut boundaries, and final sRGB contrast revalidation.
- Cover theme, master, layout, placeholder, direct formatting, color modifier, table, group, gradient/image, and unresolved-background cases.
- Verify selected corrections only are applied, stale plans are rejected, output is separate, and failures preserve the original.
- Compare Web and MCP contracts using identical core policies and fixtures.
- Test renderer absence/failure separately from algorithm results.

Continuous integration should run pure and fixture-based tests on supported Python versions, with a separate renderer job using a pinned environment once the repository has executable tooling. Do not make every unit-test run depend on Docker or LibreOffice.
