# Transform Cache Service

A FastAPI microservice that builds payloads by interleaving two lists of transformed
strings. Transformer results are cached in SQLite so each distinct string is transformed
only once, and identical requests reuse the same payload identifier.

## Running

```bash
uv run uvicorn --factory transform_cache.main:create_app
```

Interactive API docs are served at http://127.0.0.1:8000/docs.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # create .venv and install dependencies
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy src tests   # type check
uv run pytest           # tests
```
