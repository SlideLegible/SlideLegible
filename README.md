# SlideLegible

SlideLegible is a planned open-source tool for finding and correcting text contrast problems in PowerPoint presentations while preserving the author's visual design.

PowerPoint color is often inherited through themes, layouts, placeholders, transparency, and layered artwork. That makes contrast problems difficult to spot consistently by eye or by inspecting a single color value. SlideLegible is designed to resolve those presentation details, explain findings, and offer reviewable corrections.

## Planned capabilities

- Inspect `.pptx` text, effective colors, and likely text backgrounds.
- Evaluate text contrast with WCAG 2.x ratios, with APCA as supplementary information.
- Recommend minimally disruptive color changes and report the before-and-after values.
- Review slide previews and selectively apply recommendations.
- Export a corrected presentation and a structured report.

The initial MVP is limited to color contrast analysis and correction for supported PowerPoint content. Complex image and gradient backgrounds will be identified as estimates where possible. Font sizing, line spacing, PDF correction, color-vision simulation, and PowerPoint add-ins are future possibilities.

## Interfaces and architecture

The project is planned as a monorepo with a shared Python library at its center. A web backend and an MCP server will both call the same core APIs for parsing, analysis, correction, previews, and reports. They will translate their own protocol inputs and outputs without reimplementing domain logic. A future CLI can use the same package.

```text
Web UI ── Web API ──┐
                    ├── SlideLegible Python core ── PPTX / rendering adapters
MCP client ─ MCP ───┘
```

The proposed stack is Python, `python-pptx` with targeted `lxml` OOXML support, FastAPI, React/TypeScript with Vite, and the official Python MCP SDK. LibreOffice headless is the planned rendering engine. `uv`, pytest, Ruff, Docker, and GitHub Actions are candidates for workspace, quality, deployment, and CI tooling. Details and tradeoffs are in the [architecture](docs/architecture.md) and [decision records](docs/decisions/README.md).

## Project status

**Implementation foundations.** Python workspace packages and a React/TypeScript frontend scaffold are in place. Contrast analysis and end-user workflows are not implemented yet. See the [frontend setup](apps/web/frontend/README.md) for its development commands.

## Documentation

- [Architecture](docs/architecture.md)
- [Repository structure](docs/repository-structure.md)
- [Core library specification](docs/core-library.md)
- [Algorithm design](docs/algorithm-design.md)
- [PowerPoint processing](docs/pptx-processing.md)
- [Web architecture](docs/web-architecture.md)
- [MCP architecture](docs/mcp-architecture.md)
- [Testing strategy](docs/testing-strategy.md)
- [Development plan](docs/development-plan.md)
- [Implementation checklist](docs/TODO.md)
- [Dependency and platform support](docs/dependency-and-platform-support.md)
- [Decision records](docs/decisions/README.md)

## Contributing

Contributions will be welcome as implementation begins. For now, please review the design documents and open an issue or discussion to propose changes. Future contributions should keep domain behavior in the shared core, add regression fixtures for supported PowerPoint constructs, and clearly label renderer-dependent behavior. The project is distributed under the [MIT License](LICENSE).
