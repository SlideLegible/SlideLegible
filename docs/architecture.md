# Architecture

## Goals and boundaries

SlideLegible is organized around one Python domain library. It owns document inspection, effective color resolution, contrast analysis, correction planning, safe PPTX changes, previews, and reports. The Web backend and MCP server are protocol adapters; neither owns a second implementation of those behaviors. Interface-specific concerns such as HTTP status codes, MCP schemas, authentication, browser state, uploads, and transport lifecycle stay outside the core.

The MVP analyzes and corrects color contrast in `.pptx` files. It should produce explainable findings and allow users or agents to review and selectively apply proposed changes. Rendering is an optional infrastructure capability, not a prerequisite for deterministic color math or basic XML analysis.

## System view

```text
React + TypeScript ── HTTPS/JSON ── FastAPI adapter ──┐
                                                     ├── Python core package
MCP client ── stdio / Streamable HTTP ── MCP adapter ┘       │
                                     PPTX/OOXML adapters ────┤
                                     renderer adapter ───────┘
```

The core exposes typed, serializable domain results and accepts explicit services for operations that need files or external processes. The first implementation should use direct package calls in both adapters. A job queue, plugin framework, or service mesh is not warranted until usage demonstrates the need.

## Core components

| Component | Responsibility | Test profile |
| --- | --- | --- |
| Domain | Stable identifiers, values, options, findings, suggestions, reports, and errors | Deterministic unit tests |
| PPTX reader | Package validation, text extraction, OOXML color/theme/inheritance resolution | Fixture-driven regression tests |
| Background resolver | Exact XML background resolution and confidence-marked rendered sampling | Unit tests plus renderer-dependent cases |
| Analyzer | WCAG contrast and supplementary APCA calculations | Pure-function unit tests |
| Correction planner | Policy application, candidate search in OKLCH, gamut handling, minimal-change ranking | Deterministic unit tests |
| Writer | Apply reviewed changes to copied package parts and validate output | Round-trip and preservation tests |
| Renderer | Isolated LibreOffice and PDF/image conversion process boundary | Environment-dependent integration tests |
| Reporting | JSON-compatible reports and issue/correction lookup | Unit and serialization tests |
| Web and MCP adapters | Validate protocol input, call public core operations, map outcomes | Adapter integration tests |

## Data flow

1. An adapter validates caller options and obtains an input file through its allowed file-handling mechanism.
2. The core validates the OOXML package, reads content, and resolves supported text and color sources into stable element references.
3. The analyzer evaluates exact colors directly and requests rendered sampling only when the background cannot be resolved reliably from OOXML.
4. The planner creates suggestions without modifying the input. Suggestions include policy, target, changed color side, expected contrast, source certainty, and rationale.
5. A caller may apply all safe suggestions or a selected set. The writer modifies a working copy and records skipped or unsafe changes.
6. The core returns a report and artifact references; each adapter presents or transports them using its own protocol.

Analysis and mutation are separate operations. This supports review, selective application, reproducibility, and safe retries. Stable element references are scoped to an input fingerprint and include slide index plus OOXML shape/text-run identity; they must not be treated as durable identifiers after arbitrary user edits.

## Technology recommendations

- **Python core:** `python-pptx` for convenient package access, supplemented by targeted `lxml` edits because library coverage of OOXML is incomplete. Preserve original package parts where possible.
- **Color math:** begin with a small, documented internal implementation only if established libraries do not offer the required conversions and license/runtime fit. Pin conventions and verify against reference vectors. Keep WCAG/APCA and OKLCH calculations separately testable.
- **Rendering:** LibreOffice headless in a controlled environment, with PDF conversion and rasterization isolated behind a renderer interface. It is useful for previews and complex backgrounds, but is not pixel-identical to Microsoft PowerPoint.
- **Web:** FastAPI adapter, React + TypeScript, Vite, and a lightweight CSS approach such as CSS modules or a small utility system. Select styling after a prototype; it does not affect the core.
- **MCP:** official Python MCP SDK, initially stdio for local use. Add Streamable HTTP only with explicit remote deployment and authentication/security decisions.
- **Workspace and quality:** `uv` workspace, pytest, Ruff, and modern typing are recommended. Docker is appropriate for reproducible renderer deployment. GitHub Actions should follow once packaging and test commands exist.

## Cross-interface consistency

Both adapters call the same versioned core operations and share correction policy definitions from the core. They must not set their own contrast thresholds or change policies implicitly. Adapter contract tests should compare normalized core results for identical input and options. Protocol-specific serialization may differ, but issue identifiers, values, severity, confidence, and correction outcomes must retain the same meaning.

## Quality attributes

- Preserve the source file and make corrected output a distinct artifact.
- Make uncertainty visible: distinguish resolved colors from renderer-derived estimates.
- Keep pure algorithm paths usable without LibreOffice.
- Make partial success explicit and never silently claim full correction.
- Limit process and filesystem access at adapter boundaries.
- Prefer small, inspectable OOXML changes over package-wide reconstruction.

## Open questions

The first prototype should establish supported text-run types, accepted file-size/slide-count limits, renderer operating systems, and whether the initial public deployment is local-only or hosted. These questions affect operations and threat boundaries but do not change the shared-core requirement.
