# Dependency and Platform Support

## Dependency and license review

This review covers the direct dependencies declared in the Python and frontend project files as of 2026-10-21. It records their published license metadata; it does not replace legal review. Transitive dependency licenses and notices must be inventoried from the resolved lockfiles before distribution.

| Component | Direct dependency | Use | Declared license |
| --- | --- | --- | --- |
| Python runtime | SlideLegible Core | Shared analysis library | MIT (this repository) |
| Python runtime | [FastAPI](https://pypi.org/project/fastapi/) | Web API | MIT |
| Python runtime | [MCP Python SDK](https://pypi.org/project/mcp/) | MCP adapter | MIT |
| Python runtime | [python-pptx](https://pypi.org/project/python-pptx/) | Package helpers, fixtures | MIT |
| Python runtime | [lxml](https://pypi.org/project/lxml/) | OOXML parsing and targeted edits | BSD-3-Clause |
| Python runtime | [PyMuPDF](https://pypi.org/project/PyMuPDF/) | PDF rasterizing for previews and sampling | AGPL-3.0 or commercial |
| Python runtime | [Uvicorn](https://pypi.org/project/uvicorn/) | Local web server | BSD-3-Clause |
| Python runtime | [python-multipart](https://pypi.org/project/python-multipart/) | File uploads | Apache-2.0 |
| Python development | [HTTPX](https://pypi.org/project/httpx/) | API tests | BSD-3-Clause |
| Python development | [lxml-stubs](https://pypi.org/project/lxml-stubs/) | Type checking | Apache-2.0 |
| Python build | [Hatchling](https://pypi.org/project/hatchling/) | Build Python packages | MIT |
| Python development | [Ruff](https://pypi.org/project/ruff/) | Linting | MIT |
| Python development | [mypy](https://pypi.org/project/mypy/) | Type checking | MIT |
| Python development | [pytest](https://pypi.org/project/pytest/) | Tests | MIT |
| Frontend runtime | [React](https://www.npmjs.com/package/react) and [React DOM](https://www.npmjs.com/package/react-dom) | UI | MIT |
| Frontend build | [Vite](https://www.npmjs.com/package/vite) and [@vitejs/plugin-react](https://www.npmjs.com/package/@vitejs/plugin-react) | Dev server and build | MIT |
| Frontend development | [TypeScript](https://www.npmjs.com/package/typescript) | Type checking and compilation | Apache-2.0 |
| Frontend development | [@types/react](https://www.npmjs.com/package/@types/react) and [@types/react-dom](https://www.npmjs.com/package/@types/react-dom) | React type definitions | MIT |

TypeScript is a development-only tool and is not bundled into the application runtime. The project itself is MIT licensed. Recheck direct and transitive licenses when dependency versions change and before publishing artifacts.

## Operating system targets

These are project targets, not a claim that the current scaffold has passed a release test matrix.

| Area | Target | Status and limits |
| --- | --- | --- |
| Python core, Web development, and local MCP | Windows 11, macOS 11+, and 64-bit Linux; Python 3.11–3.13 | Intended targets. Cross-platform automated coverage is not configured yet. |
| Hosted Web backend | 64-bit Linux container | First deployment target; container and resource limits remain to be defined. |
| Local slide rendering | ONLYOFFICE Desktop Editors (`x2t`) or LibreOffice on Windows, macOS, or Linux | Optional; see ADR 004. ONLYOFFICE support is untested in CI. |
| Slide rendering | LibreOffice headless in the hosted Linux container | Planned renderer environment. Pin the LibreOffice build and validate it before promising rendering support. |
| Frontend development | Windows, macOS, or Linux with Node.js 20.19+ or 22.12+ and npm | Vite currently requires these Node.js ranges. The app runs in a modern browser. |

LibreOffice publishes installers for Windows, macOS, and GNU/Linux, but this project selects Linux for its initial isolated renderer environment. Native Windows/macOS rendering and visual parity are not promised. See [LibreOffice system requirements](https://www.libreoffice.org/system-requirements/) and [Vite's Node.js compatibility note](https://vite.dev/guide/).
