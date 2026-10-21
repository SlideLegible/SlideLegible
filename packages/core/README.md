# SlideLegible Core

The shared Python package for SlideLegible. Domain logic belongs here; interface adapters should depend on this package rather than reimplementing analysis behavior.

## Development

From the repository root, install the workspace and development tools with `uv sync`.
If you prefer `venv` and `pip`, create and activate a virtual environment, then run `pip install -r requirements.txt` from the repository root.

Run the configured checks with:

```sh
uv run ruff check .
uv run mypy
uv run pytest
```

The package supports Python 3.11 through 3.13. The repository's development interpreter is pinned to Python 3.12.
