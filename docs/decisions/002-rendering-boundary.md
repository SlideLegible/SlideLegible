# ADR 002: Isolate Rendering Behind an Optional Adapter

**Status:** Accepted for initial architecture

## Context

Some backgrounds can be resolved exactly from OOXML; images, gradients, effects, and layered shapes may require rendering. LibreOffice introduces an external process and environment dependency that must not burden pure algorithm tests.

## Alternatives

- Require LibreOffice for every analysis.
- Avoid rendering and support only explicit XML colors.
- Isolate rendering and use it when exact package inspection is insufficient.
- Depend on Microsoft PowerPoint automation as the primary renderer.

## Decision

Define a narrow renderer boundary in the core infrastructure. Use LibreOffice headless as the initial candidate for previews and sampled backgrounds. Mark rendered samples as estimates and allow analysis to complete when rendering is absent or fails.

## Rationale

This balances useful support for complex slides with deterministic, fast, renderer-free algorithm paths. LibreOffice is cross-platform and suitable for controlled server environments, though it does not guarantee PowerPoint-identical output.

## Consequences

Renderer version and environment must accompany previews and golden files. Deployments need process isolation and resource limits. Visual sampling requires confidence reporting and user review. A future renderer can replace the adapter without changing contrast algorithms.
