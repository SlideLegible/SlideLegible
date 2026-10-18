# MCP Server Architecture

## Purpose and boundary

The MCP server is a thin adapter over the shared Python core. Tool handlers validate schemas, enforce the server's file-access policy, invoke public core APIs, and return concise structured results plus controlled artifact references. No contrast, color-conversion, parsing, or correction algorithm belongs in the server.

## Initial tool set

Keep the first surface small:

| Tool | Inputs | Output |
| --- | --- | --- |
| `analyze_presentation` | Authorized input reference, policy name/options, preview preference | Job/report reference, summary, issues, warnings |
| `apply_corrections` | Source reference, report/plan reference, selected suggestion IDs, output naming choice | Output artifact reference, applied/skipped items, validation summary |
| `get_report` | Report reference and optional slide/issue filter | Structured report page or selected correction details |
| `render_preview` | Authorized source/output reference and slide index | Preview artifact reference or image content if small and supported |

Analysis can include suggested corrections in its result, avoiding a separate recommendation tool. `get_contrast_issues` is a filtered report read, not a separate algorithm operation. Add tools only when client workflows demonstrate a distinct need.

Tool results should use structured JSON content where supported and include stable IDs and status fields. Return short summaries, not full presentations, full slide text, or huge base64 payloads. Use an artifact path or resource link within the server's controlled workspace for binaries; disclose expiration and access scope.

## File access and transports

Start with **stdio** for local user-invoked deployments. Local path inputs are permitted only under directories explicitly configured by the operator; reject traversal, symlinks escaping the boundary, and paths outside that allowlist. Do not assume a path provided by a remote client is local to the server. For remote clients, prefer an explicit upload/content workflow or an authenticated service-owned artifact store rather than arbitrary filesystem paths.

Remote **Streamable HTTP** is a later deployment mode, not an automatic default. Before enabling it, define authentication, tenant isolation, upload limits, filesystem isolation, quotas, rate limits, and artifact retention. Bind only to intended interfaces and require TLS at the deployment boundary. Transport choice does not change the core API.

## Large jobs and response size

Analyze synchronously only when bounded work finishes within the MCP host's expected tool-call limits. Otherwise return a job ID and expose status/report retrieval through core-backed adapter state, using MCP progress notifications when available. Page issue results and support slide filters. Keep artifact retrieval separate from report text. Temporary files should have unpredictable IDs, strict permissions, quotas, and cleanup.

## Safety and idempotency

Never overwrite source files by default. Bind plans to source fingerprints and reject stale plans. Applying selected suggestion IDs should be deterministic for the same input and policy; duplicate requests should either reuse a completed artifact or produce a distinct safe output according to documented behavior. Validate output before returning it. Tool descriptions must explain whether backgrounds are exact or estimated and whether any changes were skipped.

The server should minimize its filesystem permissions, reject malformed/oversized PPTX packages, enforce time and resource limits, and isolate LibreOffice. Do not expose arbitrary read/write filesystem tools. The MCP server itself should not offer broad filesystem resources; if report resources are later added, scope them to artifacts created by that server session/tenant.

## Errors

Map core categories to MCP tool errors with actionable, concise messages and stable error codes in structured data. Return partial reports as successful structured results only when they accurately carry partial status and skipped items. Distinguish invalid input, unsupported content, stale plan, permission denial, resource limit, renderer unavailable, and internal failure.
