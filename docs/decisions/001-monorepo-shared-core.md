# ADR 001: Monorepo with One Shared Python Core

**Status:** Accepted for initial architecture

## Context

SlideLegible needs a Web application and MCP server that expose the same PPTX parsing, contrast, correction, rendering, and reporting behavior. Separate implementations would drift and produce inconsistent results.

## Alternatives

- Put logic inside the Web backend and have MCP call Web endpoints.
- Maintain separate Web and MCP implementations.
- Put domain behavior in an installable Python package used directly by both adapters.
- Split all components into independently versioned repositories immediately.

## Decision

Use a monorepo and one installable Python core package at `packages/core`. The FastAPI backend and MCP server depend on it directly. The frontend communicates with the Web backend and contains no domain algorithms.

## Rationale

Direct package calls keep local use simple and avoid network indirection while making a future CLI straightforward. A monorepo allows coordinated API evolution and shared fixtures without premature release/version management overhead.

## Consequences

The core must define stable, protocol-independent operations and versioned report data. Workspace tooling must ensure adapters import the same core checkout. If independent release cadence becomes necessary, the package boundary supports publishing core without splitting repositories.
