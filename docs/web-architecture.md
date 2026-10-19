# Web Architecture

## Components and workflow

The browser client (React + TypeScript) handles upload, mode selection, issue review, preview comparison, selective acceptance/rejection, and download. A FastAPI backend validates requests, manages upload and artifact lifecycle, calls the shared core, and exposes asynchronous work status where processing duration warrants it. The backend must use the same core package and policy presets as MCP.

1. Upload a `.pptx` and select a named correction mode.
2. Backend validates file type/signature, size, and package resource limits, stores it in a private temporary workspace, and starts analysis.
3. Core returns a report and, when supported/needed, correction suggestions.
4. User reviews issues and original/candidate previews and selects suggestions.
5. Backend asks core to apply those suggestions to a new output artifact.
6. User downloads the corrected `.pptx` and structured report; temporary artifacts expire under a documented retention policy.

## Conceptual API

| Endpoint | Responsibility |
| --- | --- |
| `POST /api/v1/presentations` | Validate and stage an upload; return an opaque presentation ID |
| `POST /api/v1/presentations/{id}/analysis` | Start analysis with a core policy and options |
| `GET /api/v1/jobs/{job_id}` | Return queued/running/completed/partial/failed state and progress where available |
| `GET /api/v1/reports/{report_id}` | Return paginated/filterable structured analysis and correction report |
| `GET /api/v1/previews/{artifact_id}` | Serve a generated slide image through controlled authorization |
| `POST /api/v1/presentations/{id}/corrections` | Apply selected suggestion IDs and return a job/artifact reference |
| `GET /api/v1/artifacts/{artifact_id}` | Download corrected PPTX or report after authorization and expiry checks |

These are design contracts; final route and schema names should be fixed with the first frontend prototype. Keep uploads, reports, and binaries out of URL parameters and ordinary JSON bodies.

## Processing and storage

Rendering and package processing can be CPU/memory intensive. Start with bounded background execution and explicit job states; a separate queue/broker is a later deployment choice if measured load requires it. A hosted deployment should store artifacts outside public web roots, use unpredictable identifiers, apply per-user authorization, and enforce expiration/cleanup even after failures. A local single-user deployment can begin with private temporary directories and bounded workers.

Set upload and expanded-package limits, request timeouts, slide/page limits, and output quotas. Validate actual ZIP/OOXML content rather than trusting file extensions or browser MIME types. Use atomic output creation and never overwrite the upload.

## Security and privacy

Presentations can contain confidential text and embedded content. Minimize retention, avoid logging slide text or file contents, redact excerpts in telemetry, and document whether files leave the user's machine. Hosted mode needs authentication, authorization, CSRF protections where cookie sessions are used, rate limits, and secure download lifetimes. Run LibreOffice with no network access and isolated filesystem permissions. Do not permit user-supplied paths or arbitrary conversion arguments.

## Frontend behavior

Show job progress and distinguish analysis completion from rendering availability. Each finding should include slide, target text reference, contrast measurement/threshold, exact-versus-estimated background status, suggested change, and reason. Allow filtering by slide/severity and selective acceptance. Present original and proposed slide previews with renderer caveats. If an issue has no safe fix or only an estimate, show that clearly instead of implying a guaranteed correction.

## Error handling

Map typed core errors into stable API error codes and HTTP status categories. Preserve per-slide warnings and partial results. A renderer failure should leave analysis downloadable when possible. Downloads should be unavailable until artifacts are validated and atomically finalized.
