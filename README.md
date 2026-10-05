# Transform Cache Service

A FastAPI microservice that builds payloads by interleaving two lists of transformed
strings. Transformer results are cached in SQLite and reused across requests, and
identical requests reuse the same payload identifier.

## Running

```bash
uv run uvicorn --factory transform_cache.main:create_app
```

Interactive API docs are served at http://127.0.0.1:8000/docs.

### Docker

```bash
docker compose up --build -d
docker compose exec app cache-cli -j '{"list_1": ["a"], "list_2": ["b"]}' -r 3
```

The SQLite database lives in the `cache-data` volume, so cached results and payload ids
survive restarts and rebuilds. Settings are environment variables with the `CACHE_`
prefix (see `docker-compose.yml`).

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CACHE_DATABASE_URL` | `sqlite+aiosqlite:///./cache.db` | SQLite database location |
| `CACHE_TRANSFORMER_LATENCY_SECONDS` | `0.5` | Simulated cost of one transformer call |
| `CACHE_TRANSFORMER_MAX_CONCURRENCY` | `10` | Simultaneous transformer calls allowed |

## API

| Request | Response |
|---|---|
| `POST /payload` with `{"list_1": [...], "list_2": [...]}` | `201` `{"id", "message"}` for a new payload, `200` with the existing id for an input seen before |
| `GET /payload/{id}` | `200` `{"output": "..."}`, `404` if unknown |
| `GET /health` | `200` `{"status": "ok"}` |

Invalid input (lists of different lengths, non-string items, unknown fields, malformed
id) is rejected with `422`.

## How it works

`POST /payload` in `PayloadService.create_payload`:

1. Hash the ordered input into a payload key. If a payload with that key exists, return
   its id: no transformer calls.
2. Deduplicate the strings and load their cached results in one query.
3. Transform only the misses, concurrently, under a concurrency limit. A string already
   being transformed for another request is awaited, not transformed again. Each result
   is cached before the call completes.
4. Interleave the results into the output and store the payload. Unique constraints and
   `INSERT ... ON CONFLICT DO NOTHING` make concurrent identical requests converge on one
   stored payload.

| Module | Role |
|---|---|
| `main.py` | FastAPI app, routes, lifespan |
| `service.py` | Caching and payload logic |
| `payload.py` | Pure rules: interleaving, payload key |
| `transformer.py` | Transformer interface and the simulated one |
| `models.py`, `db.py` | Tables and database setup |
| `schemas.py` | API request/response models, also used by the CLI |
| `cli.py` | `cache-cli` |

## CLI

`cache-cli` sends a payload to the service, reads it back, and prints one JSON line per
iteration with the payload id, HTTP status, output, and elapsed time. Repeating a request
shows the cache at work: later iterations return the same id with status 200 and no
transformer calls.

```bash
uv run cache-cli --json '{"list_1": ["a", "b"], "list_2": ["c", "d"]}' --repeat 3
echo '{"list_1": ["a"], "list_2": ["b"]}' | uv run cache-cli -H http://127.0.0.1:8000 -i -
uv run cache-cli --input body.json --output results.jsonl
```

| Flag                     | Meaning                                            |
| ------------------------ | -------------------------------------------------- |
| `-H`, `--host URL`       | Service base URL (default `http://127.0.0.1:8000`) |
| `-r`, `--repeat N`       | Number of POST + GET iterations (default 1)        |
| `-i`, `--input FILE\|-`  | Request body from a file, or `-` for stdin         |
| `-j`, `--json JSON`      | Request body as an argument                        |
| `-o`, `--output FILE\|-` | Where to write results, `-` for stdout (default)   |
| `-h`, `--help`           | Show help                                          |

Arguments are defined and validated by Pydantic Settings.

Exactly one of `--input` and `--json` is required. The body is validated before any
request is sent. Exit codes: 0 success, 1 request failed or unexpected response, 2 invalid arguments
or input.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # create .venv and install dependencies
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy src tests   # type check
uv run pytest           # tests
```

`tests/unit` covers pure logic and parsing. `tests/integration` runs against a real
SQLite file: the service, the API through FastAPI's test client, and the CLI against the
app in-process. A counting fake transformer lets tests assert how many transformer calls
were made, which is what the caching exists to minimize.

HTTP calls use `httpx2`, the Pydantic-maintained successor of `httpx`: Starlette's test
client requires it and deprecates `httpx`, so one HTTP library serves the CLI and the tests.

## Assumptions

Decisions:

- **Payloads are stored as database rows, not files**. The
  generated output is stored with its id, so reading a payload never calls the
  transformer again.
- **The CLI uses `-H` for `--host` and `-h` for help**.
- **`POST /payload` returns 201 for a new payload and 200 for an input seen before.**
  Both return the same body shape with the payload id.
- **Payload identity is the exact ordered pair of lists.** Reordering items or swapping
  `list_1` and `list_2` produces a different payload; transformer results are still
  reused because they are cached per string.
- **The transformer is deterministic and does not fail.** Determinism is what makes
  caching its results valid. Upstream failure handling (retries, error mapping, partial
  results) is out of scope; an unexpected error surfaces as a 500.
- **Empty lists are valid** and produce an empty output.
- **One CLI iteration is a full POST then GET**, so each line reports both the id and the
  stored output.
- **CLI results are JSON Lines**, one object per iteration, so they can be streamed and
  parsed by other tools.
- **The CLI reads only its command line**, not environment variables, so unrelated
  variables such as `HOST` cannot change its behaviour.

## Shortcuts

- **SQLite only.**
- **No migrations.** Tables are created at startup with `create_all()`. A production
  service would manage schema changes with a migration tool such as Alembic.
- **Deduplication of concurrent transformer calls is per process.** Several workers or
  replicas would each call the transformer for the same new string; avoiding that would
  need a distributed lock. Database unique constraints keep the stored data consistent
  either way.
- **Very large inputs are not chunked.** The cache lookup binds one parameter per unique
  string, and SQLite allows at most 32,766 per statement.
