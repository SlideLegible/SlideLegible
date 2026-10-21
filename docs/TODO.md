# Implementation Checklist

This checklist tracks implementation work. Documentation in this planning phase does not count as implementation completion; all implementation tasks begin unchecked.

## Phase 1 — Workspace and project tooling

- [x] Choose supported Python versions and establish `uv` workspace projects for core, Web backend, and MCP.
- [x] Add package metadata, workspace dependencies, and installable core package under `packages/core`.
- [x] Configure Ruff, typing checks, pytest, and documented developer commands.
- [x] Decide frontend package manager and add React/TypeScript/Vite project under `apps/web/frontend`.
- [x] Record dependency/license review and supported operating systems, including renderer environments.

## Phase 2 — Shared core foundations

- [x] Define typed domain records, stable input-scoped element IDs, report schema version, and error categories.
- [x] Define explicit file/artifact interfaces and source fingerprinting.
- [x] Implement WCAG 2.x sRGB luminance and contrast ratio with reference-vector tests.
- [x] Define large-text classification and uncertainty reporting.
- [x] Select and version an APCA implementation or defer the metric with an explicit compatibility decision.
- [x] Establish named correction policies with documented numeric targets and tests.

## Phase 3 — PPTX package inspection and color resolution

- [ ] Validate PPTX ZIP structure and enforce archive, part-size, expansion, slide, and time limits.
- [x] Extract text runs from the initial supported shape subset with stable source references.
- [x] Resolve direct RGB and scheme colors to sRGB while retaining source OOXML expressions.
- [x] Resolve theme colors and ordered color modifiers with regression fixtures.
- [x] Resolve master, layout, placeholder, paragraph, and run inheritance precedence for documented cases.
- [x] Add table, group, and unsupported-content detection without claiming unverified coverage.
- [x] Create licensed minimal PPTX fixtures with provenance metadata.

## Phase 4 — Contrast analysis and reports

- [x] Model exact background colors for supported solid fills and inheritance cases.
- [x] Implement contrast analysis, severity, evidence, confidence, and partial-result reporting.
- [ ] Serialize reports to stable JSON-compatible schema and support slide/element filtering.
- [x] Add uncertainty behavior for unknown, layered, transparent, gradient, and image backgrounds.

## Phase 5 — Correction planning

- [x] Select or validate an OKLCH conversion implementation against published/reference vectors.
- [x] Implement lightness-first candidate search, gamut handling, and final sRGB contrast revalidation.
- [x] Generate non-mutating suggestions with changed side, policy, expected result, perceptual delta, and rationale.
- [x] Detect shared-theme and conflicting changes; support selective suggestion IDs.
- [x] Define safe fallback when text-only adjustment cannot reach the target.

## Phase 6 — Rendering and previews

- [ ] Define renderer process boundary, supported environments, timeouts, resource limits, and version reporting.
- [x] Implement isolated LibreOffice conversion and PDF-to-image preview generation.
- [x] Sample complex backgrounds with confidence and exact/estimated classification.
- [ ] Establish renderer-tagged visual regression fixtures and review tolerances.
- [x] Verify analysis still succeeds when rendering is unavailable.

## Phase 7 — PPTX modification and export

- [x] Implement targeted color writes to a working copy while preserving unrelated package parts.
- [x] Reject stale correction plans and never overwrite inputs by default.
- [x] Apply only selected suggestions and return per-item applied/skipped reasons.
- [ ] Validate exported package, target colors, relationships, and preservation invariants.
- [x] Document unsupported and unsafe modifications in the public content matrix.

## Phase 8 — MCP adapter

- [ ] Create an MCP adapter depending on the core public package only.
- [ ] Implement analyze, apply-corrections, get-report, and preview tools with structured schemas.
- [ ] Enforce configured local path allowlists, output handling, size limits, and artifact cleanup.
- [ ] Test tool results against core reports and test stdio lifecycle.
- [ ] Decide whether and how to deploy authenticated Streamable HTTP; keep disabled until security requirements are met.

## Phase 9 — Web backend

- [x] Implement upload validation, private staging, job status, and artifact lifecycle.
- [x] Add analysis, report, preview, selective correction, and download endpoints.
- [x] Map typed core errors and partial statuses consistently to HTTP responses.
- [ ] Add authentication/authorization and rate controls appropriate to deployment mode.
- [ ] Test cleanup, expiry, limits, unauthorized access, and adapter/core behavioral consistency.

## Phase 10 — Web frontend

- [x] Build upload and policy-selection flow with clear file and privacy expectations.
- [x] Display analysis summary, slide-filtered findings, evidence, uncertainty, and proposed changes.
- [x] Add original/corrected previews and selective accept/reject controls.
- [x] Support corrected PPTX and report download, including partial-success messaging.
- [ ] Check keyboard accessibility, responsive layout, and large-report pagination.

## Phase 11 — Integration, hardening, and release

- [ ] Add cross-interface tests proving Web and MCP use the same policies and core results.
- [ ] Add security tests for malformed PPTX, ZIP bombs, XML hazards, path traversal, and renderer isolation.
- [ ] Benchmark parse, analysis, render, and peak memory across representative decks.
- [ ] Establish CI for pure tests and a separate pinned renderer job.
- [ ] Add Docker deployment for a reproducible renderer environment when deployment targets are selected.
- [ ] Publish supported-content matrix, known limitations, retention policy, and contribution guide.
- [ ] Review license compatibility and release/versioning policy.

## Later enhancements

- [ ] Evaluate text size/line spacing recommendations, PDF workflows, color-vision simulation, and Office add-ins as separate product proposals.
- [ ] Add a CLI adapter that invokes the existing core, if contributor demand supports it.
- [ ] Expand format and OOXML coverage based on fixture-backed preservation evidence.

## Notes from the MVP branch

- Package limits exist (`PackageLimits`) but the local Web deployment disables size and slide limits; time and memory limits are not enforced yet.
- ONLYOFFICE (`x2t`) rendering is implemented next to LibreOffice (ADR 004) and is tested with a fake converter only.
- Rendering has a timeout but no memory limit or sandbox; visual regression baselines are not set up.
- The Web backend is local single-user: no authentication, rate limits, or expiry beyond deleting everything when the server stops.
