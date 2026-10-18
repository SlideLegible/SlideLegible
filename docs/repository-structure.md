# Repository Structure

The planned monorepo keeps the reusable Python package separate from interface applications while allowing them to share one dependency and version during early development.

```text
slidelegible/
├── apps/
│   ├── web/
│   │   ├── backend/       # FastAPI adapter; depends on packages/core
│   │   └── frontend/      # React + TypeScript client
│   └── mcp/               # MCP adapter; depends on packages/core
├── packages/
│   └── core/              # Installable SlideLegible Python library
├── tests/
│   ├── integration/       # Cross-package and end-to-end adapter tests
│   ├── fixtures/          # Small, licensed, purpose-built PPTX examples
│   └── visual/            # Renderer-dependent reference cases and metadata
├── docs/                  # Architecture, specifications, decisions, roadmap
├── examples/              # User-facing sample inputs and report examples
├── README.md
└── LICENSE
```

## Responsibilities and dependency direction

- `packages/core` will be a normal installable Python project and the only home for domain models, policies, algorithms, PPTX processing, rendering orchestration, and reports.
- `apps/web/backend` and `apps/mcp` will be separate Python projects that declare the core as a workspace dependency. They contain protocol translation, lifecycle, and interface configuration only.
- `apps/web/frontend` is a separately managed TypeScript project. It communicates with the Web backend and does not implement analysis or correction rules.
- `tests/` holds cross-package behavioral tests and shared PPTX fixtures. Core-specific unit tests should live with the core package (for example under `packages/core/tests`) so its package can be tested independently.
- `examples/` contains only material suitable for public distribution. Keep generated, sensitive, oversized, or licensed third-party files out of the repository.
- `docs/` describes design and operational decisions; it does not imply that a directory or component is already implemented.

Dependency direction is one-way: adapters depend on core; core depends on small libraries and its own ports, never on FastAPI, MCP protocol classes, or frontend packages. The Web and MCP adapters select the same named policies exposed by core and pass equivalent options.

## Tests and fixtures

Use core-local tests for pure algorithms and parser behavior; use top-level integration tests to exercise adapter contracts against the same core behavior. Fixtures should be minimal and purpose-built, each illustrating one construct and carrying a short description and provenance/license note. Golden images and rendered PDFs belong in visual-test storage only when their size and licensing are acceptable; avoid checking in large derivative files.

## Packaging and deployment

`uv` workspace configuration should be added during the implementation setup phase, not before. Core, Web backend, and MCP should be independently installable Python projects with explicit workspace dependencies. The frontend can use its own package manager and lockfile after selection. A local Web deployment can package the renderer alongside the backend in Docker; local MCP deployments may use an environment with LibreOffice installed. Hosted deployments need isolated temporary storage, worker limits, retention controls, and an explicit renderer image.

## Future interfaces

A CLI, if prioritized, should be another adapter under `apps/` depending on core. New formats should introduce format-specific readers/writers behind core-defined document operations only when a real use case exists; avoid general plugin abstractions in advance.
