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

**MVP (color contrast) implemented on a local web tool.** Upload a `.pptx`, choose a mode (comfortable reading, projector, strict AAA), review findings with original and corrected previews, accept or reject each change, and download the corrected deck and an HTML report. See [supported content](docs/supported-content.md) for exactly what is analyzed and changed. Font size and line spacing are not implemented.

## Run locally

Requirements: [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed by uv), Node.js 20.19+ or 22.12+, and optionally ONLYOFFICE Desktop Editors or LibreOffice for previews and photo/gradient backgrounds.

```sh
uv sync
cd apps/web/frontend
npm ci
npm run build
cd ../../..
uv run uvicorn slidelegible_web.app:app
```

Open <http://127.0.0.1:8000>. Uploaded files and generated images live in a private temporary folder that is deleted when the server stops.

For frontend development, run the API with `uv run uvicorn slidelegible_web.app:app --reload` and, in `apps/web/frontend`, `npm run dev`; open the Vite URL (it forwards `/api` to port 8000).

### Renderers

Rendering is optional. Without a renderer, solid backgrounds are still analyzed exactly, but picture and gradient backgrounds cannot be measured and there are no previews.

- **ONLYOFFICE Desktop Editors**: found automatically at `C:\Program Files\ONLYOFFICE\DesktopEditors\converter\x2t.exe` with its font cache in `%LOCALAPPDATA%\ONLYOFFICE\DesktopEditors\data\fonts` (open the app once so the cache exists).
- **LibreOffice**: found on `PATH` or in its default install folder.

Check what was found and run a test conversion:

```sh
uv run python -m slidelegible.render
uv run python -m slidelegible.render path/to/deck.pptx
```

Environment variables: `SLIDELEGIBLE_RENDERER` (`auto`, `onlyoffice`, `libreoffice`, `none`), `SLIDELEGIBLE_X2T`, `SLIDELEGIBLE_ONLYOFFICE_FONTS`, `SLIDELEGIBLE_SOFFICE`, `SLIDELEGIBLE_RENDER_TIMEOUT` (seconds).

### Checks and sample decks

```sh
uv run ruff check .
uv run mypy
uv run pytest
uv run python tests/fixtures/decks.py fixtures-out
```

The last command writes synthetic test decks, including `demo.pptx` with every supported case; `examples/demo-low-contrast.pptx` is a copy.

## Documentation

- [Architecture](docs/architecture.md)
- [Repository structure](docs/repository-structure.md)
- [Core library specification](docs/core-library.md)
- [Supported content](docs/supported-content.md)
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
