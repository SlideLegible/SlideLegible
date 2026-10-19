# Development Plan

## Strategy

Build vertical slices around the shared core. Start with deterministic color calculations and a deliberately narrow set of PPTX text/fill cases; then add resolution, safe edits, and interface adapters. Keep the source immutable, make findings explainable, and label estimates. Web and MCP should arrive only after the core has stable public operations and fixture coverage.

## Milestones and dependencies

| Milestone | Priority | Depends on | Acceptance criteria |
| --- | --- | --- | --- |
| 1. Workspace and package foundations | P0 | None | Installable core and adapter projects, formatting/type/test commands, documented supported runtime |
| 2. Domain records and color math | P0 | 1 | Deterministic WCAG calculations, color model, policy representation, JSON-compatible report records |
| 3. Narrow PPTX inspection | P0 | 2 | Read common shapes/text runs and direct solid colors; identify unsupported constructs without guessing |
| 4. Theme and inheritance resolution | P0 | 3 | Resolve covered theme/master/layout/placeholder cases with regression fixtures and traceable evidence |
| 5. Analysis and correction planning | P0 | 2–4 | Produce stable issues and suggestions; verify candidate colors in sRGB; do not modify input |
| 6. Targeted PPTX export | P0 | 5 | Selectively apply supported corrections to a copy; reopen output and report partial/skipped changes |
| 7. Rendering and previews | P1 | 1, 3 | Isolated renderer, preview artifacts, confidence-marked sampling, failure does not block exact analysis |
| 8. MCP local adapter | P1 | 5–6 | Stdio tools use public core APIs, controlled paths, structured reports, safe output artifacts |
| 9. Web backend and frontend | P1 | 5–7 | Upload/review/preview/select/export flow with lifecycle/security limits and same core policies |
| 10. Hardening and release | P1 | 6–9 | Security/performance checks, fidelity evidence, deployment docs, CI and versioned public contracts |

## MVP scope

MVP means usable color contrast analysis and selective correction for a documented subset of `.pptx` content. It includes WCAG 2.x ratios, source-linked findings, explainable recommendations, safe output generation, structured reports, and at least one interface (prefer MCP local first or a minimal Web slice based on maintainer priorities). Rendering and complex backgrounds are capability-labeled; they should not be prerequisites for deterministic analysis. Comfortable reading, projector, and strict AAA policies need explicit definitions and validation before release.

Excluded from MVP: font-size/spacing adjustment, PDF correction, color vision deficiency simulation, add-ins, arbitrary file-format plugins, and guaranteed PowerPoint/LibreOffice pixel parity.

## Technical risks

- **OOXML scope:** inheritance and modifiers are broad; narrow supported cases and surface omissions.
- **Background certainty:** a rendered pixel estimate may not represent glyph-level effective contrast.
- **Fidelity:** editing packages through high-level APIs may alter content outside the target; use targeted edits and preservation tests.
- **Correction tradeoffs:** color-only fixes may be impossible without larger visual changes or changing backgrounds.
- **Renderer variance:** font substitution and Office differences affect previews and sampling.
- **Untrusted files:** ZIP/XML expansion, malformed parts, and LibreOffice processing require limits and isolation.
- **MCP filesystem semantics:** local and remote clients do not share path namespaces; transport-specific access policy is essential.

## Release acceptance

Before an MVP release, define the supported PPTX content matrix; publish known limitations; verify targeted exported changes and unrelated-part preservation on fixtures; pass deterministic algorithm and security tests; label estimated backgrounds; support partial success; and ensure Web/MCP call the same core version and policy implementation. Performance limits and retention behavior must be documented for each deployment mode.

## Future opportunities

After evidence from users: broader table/chart/SmartArt coverage, refined renderer sampling, additional correction strategies, a CLI adapter, APCA as a mature supplementary metric, font or spacing recommendations, and other presentation formats. Add only after the underlying use cases and preservation constraints are understood.
