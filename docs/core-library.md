# Core Library Specification

## Purpose

The core is the single source of truth for presentation analysis and correction. Its public API is independent of HTTP, MCP, CLI, and frontend types. The following names and signatures are conceptual contracts, not implementation code.

## Public operations

| Operation | Inputs | Result |
| --- | --- | --- |
| `inspect_presentation` | Input reference, inspection options | Presentation metadata, slides, text elements, color resolution records, warnings |
| `analyze_contrast` | Inspected presentation or input reference, analysis options | `AnalysisReport` with issues, measurements, confidence, and warnings |
| `suggest_corrections` | Analysis report, `CorrectionPolicy`, issue selection | Non-mutating `CorrectionPlan` with proposed color changes and expected outcomes |
| `apply_corrections` | Input reference, plan, selected suggestion IDs, output destination policy | `CorrectionResult`, output artifact reference, applied/skipped items |
| `render_previews` | Input reference and optional corrected artifact, slide selection, render options | Preview artifact references and renderer metadata |
| `get_report` | Report or job identifier | Structured report, optionally filtered by slide or element |

Adapters may combine operations into a convenience action (for example analyze then suggest), but the underlying steps and results remain explicit. The core should offer stream/path-based I/O internally where practical; public transport adapters must decide how callers provide and retrieve artifacts.

## Domain records

- **Presentation**: input fingerprint, filename label, package metadata, slide count, inspection status, warnings.
- **Slide**: stable input-scoped ID, 1-based display index, dimensions, text-element references.
- **TextElement**: stable input-scoped element ID, slide ID, shape and paragraph/run coordinates, text excerpt or protected text reference, typography attributes relevant to WCAG large-text classification, resolved foreground, background observation.
- **Color**: normalized sRGB channels and alpha, plus original OOXML source representation and optional theme/source reference.
- **BackgroundObservation**: resolved color or sampled estimate, sampling method, confidence, and contributing layers where available.
- **ContrastResult**: algorithm identifier/version, ratio or metric value, applicable threshold, pass status, foreground/background inputs.
- **ContrastIssue**: issue ID, element reference, severity, measurement, confidence, evidence, and limitations.
- **CorrectionPolicy**: named mode, thresholds, allowed edit sides, maximum perceptual change, and fallback behavior. Presets are core data, not adapter constants.
- **CorrectionSuggestion**: issue IDs addressed, target(s), original/proposed colors, expected measurements, perceptual delta, rationale, and safety status.
- **CorrectionPlan**: source fingerprint, policy version, suggestions, conflicts, and expiry/validity notes.
- **CorrectionResult**: output artifact, applied IDs, skipped IDs with reasons, validation status, and warnings.
- **AnalysisReport**: schema version, source metadata, settings, results, summary counts, warnings, and provenance.

Identifiers should be deterministic for one source package and inspection version. Reports should not include full slide text by default; use short excerpts only when necessary and support redaction.

## Correction modes

The MVP should define three explicit presets: **comfortable reading** (a practical target chosen and justified during validation), **projector** (a higher target informed by display conditions), and **strict AAA** (WCAG AAA thresholds where applicable). Exact non-WCAG preset targets remain an implementation decision requiring usability review. Every report must record preset name and resolved numeric requirements. Policies should permit callers to set a custom minimum where supported without silently weakening a named preset.

WCAG text contrast uses 4.5:1 for normal text and 3:1 for large text at AA, with AAA thresholds of 7:1 and 4.5:1 respectively. Classification depends on measured font size and weight and may be uncertain for inherited or unsupported typography; report the basis.

## Error and partial-success model

Use typed core categories that adapters map to their own protocols:

- `InvalidInput`: malformed package, unsupported format, corrupt OOXML.
- `UnsupportedContent`: content or color construct cannot be interpreted safely.
- `AnalysisFailure`: required resolution or metric operation failed.
- `CorrectionConflict`: stale plan, conflicting suggestions, or invalid selection.
- `UnsafeModification`: applying the change could damage or misrepresent content.
- `RenderingUnavailable` / `RenderingFailure`: renderer absent or failed; analysis may still succeed.
- `ResourceLimitExceeded`: configured size, time, slide, or memory budget exceeded.
- `ArtifactAccessFailure`: input/output could not be read or written under allowed policy.

Warnings and per-element failures should be represented in results when safe to continue. A report must distinguish complete success, partial success, and failure. Adapters must not convert partial success into a success claim without exposing skipped items.

## File and serialization rules

Never overwrite the original input by default. A correction plan is bound to an input fingerprint; reject application if the source has changed. Use unique output names and atomic output finalization. Core report objects should serialize to versioned JSON-compatible data with no adapter-specific fields. Binary PPTX and preview data are artifacts referenced by opaque IDs or controlled paths, not embedded in normal reports.

## Determinism and extension

Keep color math, threshold evaluation, policy selection, and suggestion ranking deterministic and renderer-free. Put filesystem and subprocess operations behind narrow services so unit tests can substitute them. Add a new metric by defining its inputs, version, output, and applicability; do not change WCAG semantics. Add strategies through policy options only after a concrete need appears.
