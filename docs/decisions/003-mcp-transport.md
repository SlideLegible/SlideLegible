# ADR 003: Start MCP with Local stdio

**Status:** Accepted for initial implementation direction

## Context

MCP tools need to accept presentations and return reports/artifacts. Local and remote clients do not share a filesystem, and arbitrary path access creates a security boundary. Remote transport also requires authentication, tenant isolation, and artifact lifecycle design.

## Alternatives

- Start with local stdio and explicitly allowed paths.
- Start with unauthenticated remote HTTP.
- Start with authenticated Streamable HTTP and a managed upload store.
- Send whole presentation binaries in every tool call and response.

## Decision

Implement local stdio first using the official Python MCP SDK, with operator-configured input/output directories and controlled artifact references. Consider Streamable HTTP only as a later deployment mode after security and storage requirements are defined.

## Rationale

Stdio is the simplest local integration model and avoids exposing an unauthenticated network service. Artifact references keep large binary files out of ordinary tool responses. The core API remains transport-independent.

## Consequences

The local server must enforce path boundaries and cleanup. A remote deployment needs a separate explicit access model; local paths cannot be assumed to exist on the remote server. Tool schemas and artifact behavior should remain independent of transport.
