# Transform Cache Service

A FastAPI microservice that builds payloads by interleaving two lists of transformed
strings. Transformer results are cached in SQLite and reused across requests, and
identical requests reuse the same payload identifier.

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

## Assumptions

Decisions on points the task leaves open:

- **Payloads are stored as database rows, not files.** The generated output is stored
  with its id, so reading a payload never calls the transformer again.
- **`POST /payload` returns 201 for a new payload and 200 for an input seen before.**
  Both return the same body shape with the payload id.
- **Payload identity is the exact ordered pair of lists.** Reordering items or swapping
  `list_1` and `list_2` produces a different payload; transformer results are still
  reused because they are cached per string.
- **The transformer is deterministic and does not fail.** Determinism is what makes
  caching its results valid. Upstream failure handling (retries, error mapping, partial
  results) is out of scope; an unexpected error surfaces as a 500.
- **Empty lists are valid** and produce an empty output.
- **The output format follows the task example**: items joined with `", "`. An input
  string that itself contains `", "` makes the output ambiguous to split.

## Shortcuts

- **SQLite only.** The task allows it and it needs no extra infrastructure. Conflict
  handling uses SQLite's `ON CONFLICT` syntax; other databases are untested.
- **No migrations.** Tables are created at startup with `create_all()`. A production
  service would manage schema changes with a migration tool such as Alembic.
- **Deduplication of concurrent transformer calls is per process.** Several workers or
  replicas would each call the transformer for the same new string; avoiding that would
  need a distributed lock. Database unique constraints keep the stored data consistent
  either way.
- **Very large inputs are not chunked.** The cache lookup binds one parameter per unique
  string, and SQLite allows at most 32,766 per statement.
