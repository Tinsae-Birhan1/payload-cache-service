# Payload Cache Service

A FastAPI microservice that builds payloads from two lists of strings. Each string is
passed through a slow "transformer" (standing in for an external service such as an LLM
call), and the transformed strings are interleaved. Every transformer result is cached in
a database, so no string is ever sent to the transformer twice, and identical requests
get back the same payload identifier.

```
POST /payload   {"list_1": ["first string", ...], "list_2": ["other string", ...]}
  -> 201 {"id": "<uuid>", "message": "Payload created"}
  -> 200 {"id": "<same uuid>", "message": "Payload already exists"}   (repeat request)

GET  /payload/{id}
  -> 200 {"output": "FIRST STRING, OTHER STRING, SECOND STRING, ..."}
```

## Quick start

**Docker (API + PostgreSQL):**

```bash
docker compose up --build -d
uv run cache-cli -i examples/sample.json -r 3
```

**Local (SQLite, no Docker):** requires [uv](https://docs.astral.sh/uv/).

```bash
make install      # uv sync
make run          # migrate + uvicorn with reload on :8000
make demo         # cache-cli with the sample payload, three times
```

Interactive API docs: <http://localhost:8000/docs>.

Expected demo output: the first iteration creates the payload (6 transformer calls,
~200 ms with the simulated delay); the following iterations reuse it in a few ms:

```
[1/3] created 2337...fff9 in 227.7 ms
[2/3] reused  2337...fff9 in 8.8 ms
[3/3] reused  2337...fff9 in 8.8 ms
```

## CLI

```
cache-cli [-H|--host URL] [-r|--repeat N] [-i|--input FILE|-] [-j|--json JSON] [-o|--output FILE|-] [-h|--help]
```

| Option | Meaning |
|---|---|
| `-H`, `--host` | Service base URL (default `http://localhost:8000`) |
| `-r`, `--repeat` | Number of iterations, ≥ 1 (default 1) |
| `-i`, `--input` | JSON input file, `-` for stdin |
| `-j`, `--json` | JSON input given inline |
| `-o`, `--output` | Output file, `-` for stdout (default) |

Arguments are parsed and validated with Pydantic Settings, and the payload is validated
locally with the API's own request schema before anything is sent. Results are written as
JSON to `--output`; progress goes to stderr so stdout stays pipeable. Exit codes: `0`
success, `1` request failed, `2` invalid arguments or input.

```bash
cache-cli -j '{"list_1": ["a"], "list_2": ["b"]}' | jq -r .output
```

## Design

```
src/payload_cache/
├── domain/      pure logic: interleaving, fingerprints, transformer contract
├── db/          SQLAlchemy models, engine setup, dialect-aware upsert
├── services/    TransformationCache (read-through cache) and PayloadService
├── api/         FastAPI routes, schemas, dependencies, error mapping
├── cli/         cache-cli
└── main.py      app factory and lifespan wiring
migrations/      Alembic
```

Dependencies point inwards: `api` → `services` → `db`/`domain`. The domain layer knows
nothing about HTTP or SQL, so it can be tested without either.

### Minimising transformer calls

The spec asks to minimise calls to the transformer. `TransformationCache` does this at
three levels:

1. **Within a request.** Inputs are de-duplicated before anything else, so
   `["a", "a", "b"]` costs two calls.
2. **Across requests (persistent).** All inputs of a request are looked up with a single
   `SELECT … WHERE input_hash IN (…)`. Only the misses go to the transformer.
3. **Across concurrent requests (in flight).** If two requests need the same uncached
   string at the same moment, the second one awaits the first one's call instead of
   making its own (a "single-flight" registry of `asyncio.Task`s). `asyncio.shield`
   keeps the shared call alive if one waiting client disconnects.

Calls to the transformer run concurrently, capped by a semaphore
(`CACHE_TRANSFORMER_MAX_CONCURRENCY`), because real providers rate-limit.

**Partial failures.** If one of N transformer calls fails, the N−1 successful results are
still stored before the error is returned (`502`), so a retry only pays for the failed
input. Failures are never cached, so a temporary outage does not poison the cache.

### Reusing payload identifiers

A payload's identity is the SHA-256 of the canonical JSON `[list_1, list_2]`. Hashing
the JSON rather than the output string matters: `(["a, b"], ["c"])` and
`(["a"], ["b, c"])` render the same output but are different inputs. The fingerprint
column is `UNIQUE`; a repeat request finds it and returns the existing id without doing
any transformer work.

### Concurrency and transactions

- **The database decides races.** Both tables are written with
  `INSERT … ON CONFLICT DO NOTHING`. When two identical requests race, the unique
  constraint picks one winner atomically; the other re-reads and returns the same id
  (covered by tests that fire five identical requests at once).
- **No transaction spans a transformer call.** Each request reads in a short
  transaction, releases the connection, calls the transformer, then writes in another
  short transaction. Holding a pooled connection (or SQLite's write lock) while waiting
  on a slow external service would block every other request.

### Data model

| Table | Key | Why |
|---|---|---|
| `transformation_cache` | `input_hash` (SHA-256) | Fixed-width key. Postgres btree index entries are limited to ~2.7 KB, so a unique index on raw user text would reject long inputs |
| `payloads` | `id` (random UUID), `fingerprint` unique | UUIDs don't reveal volume or allow guessing other ids; the stored `output` makes `GET` a single primary-key lookup |

### Validation

Requests are validated before any work happens (`422`): the lists must have the same
length; they must hold at least one and at most 1,000 strings, each at most 10,000
characters; and unknown fields are rejected. The limits are part of the API contract
(visible in the OpenAPI schema), because without them one request could trigger an
unbounded number of paid calls.

## Testing

```bash
make check                                  # ruff + mypy --strict + pytest with coverage
TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest   # same suite on Postgres
```

| Layer | What it proves |
|---|---|
| `tests/unit/domain` | Interleaving, fingerprints, cache keys |
| `tests/unit/services` | Call counts for cold, warm and partially warm caches; de-duplication; single-flight under concurrency; partial-failure handling (real database, fake transformer that counts calls) |
| `tests/unit/cli` | Argument parsing, input sources, error exits, output file (HTTP mocked with `httpx.MockTransport`) |
| `tests/integration` | The API over HTTP against a real database; status codes and validation; migrations match the models and downgrade cleanly |
| `tests/e2e` | The real CLI against a real uvicorn server over TCP, on a migrated database |

CI (GitHub Actions) runs lint and type checks, runs the suite on **both SQLite and
PostgreSQL**, and smoke-tests the Docker Compose stack.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | |
|---|---|---|
| `CACHE_DATABASE_URL` | `sqlite+aiosqlite:///./payload_cache.db` | Any async SQLAlchemy URL; Compose uses `postgresql+asyncpg://…` |
| `CACHE_TRANSFORMER_DELAY_SECONDS` | `0.2` | Simulated latency of the external service |
| `CACHE_TRANSFORMER_MAX_CONCURRENCY` | `10` | Cap on parallel transformer calls |
| `CACHE_LOG_LEVEL` | `INFO` | |

## Decisions, assumptions and shortcuts

- **`-H` instead of `-h` for `--host`.** The spec gives `-h` to both `--host` and
  `--help`, which cannot work. `-h` keeps its universal meaning. The CLI also ignores
  environment variables on purpose, so an unrelated `HOST` variable cannot change its
  target.
- **Cache keys match exactly.** `"a"` and `"A "` are different keys, because nothing
  says the transformer treats them the same.
- **The output format is lossy.** The output joins strings with `", "` as the spec's
  sample shows, so a string that itself contains `", "` cannot be told apart from two
  strings. Kept because it is the specified contract; a JSON array would avoid it.
- **Single-flight works within one process.** With several replicas, two processes can
  still transform the same string at the same moment. The cost is a duplicate call, not
  wrong data, because the upsert keeps results consistent. Removing it would take a
  distributed lock (e.g. a Postgres advisory lock keyed by the input hash). There is
  also a narrow window in which a request that read the database just before another
  request stored a result makes a duplicate call.
- **Migrations run at container start.** This is simple and fine for one instance. With
  several replicas, migrations would move to a separate one-off job.
- **The cache never expires.** The spec treats the transformation as deterministic. A
  real LLM-backed transformer would need a model/version component in the cache key, and
  probably a TTL.
- **No authentication or rate limiting.** Out of scope for the task; both would sit in
  front of the API (gateway) or as middleware.
