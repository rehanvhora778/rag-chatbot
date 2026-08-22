# Working on this project

## Setup

```bash
python -m venv venv
venv/Scripts/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cp backend/.env.example backend/.env      # set GROQ_API_KEY
cd frontend && npm install
```

For anything touching PostgreSQL, pgvector or hybrid retrieval:

```bash
cp .env.docker.example .env
docker compose up -d postgres redis
```

## Running it

```bash
# backend
cd backend && python manage.py migrate && python manage.py runserver

# frontend
cd frontend && npm run dev

# worker (only needed if you want ingestion off the request thread)
cd backend && celery -A config worker --loglevel=info --pool=solo   # --pool=solo on Windows
```

Without a broker, uploads process in a daemon thread and log a warning saying
so. That is fine locally and is not what the containers do.

## Tests

```bash
cd backend && pytest                 # 300 tests
cd backend && pytest -k isolation    # one area
cd frontend && npm test              # 9 tests

DATABASE_URL=postgresql://raguser:ragpass@localhost:5432/ragchatbot pytest
```

Without `DATABASE_URL` the suite runs on SQLite and the PostgreSQL-only tests
skip themselves — pgvector and full-text search have no SQLite equivalent. CI
always runs with it.

Tests never make real network calls. A test that tries one fails with a message
telling you to mock the provider or mark it `@pytest.mark.integration`.

## Lint

```bash
cd backend && ruff check . --fix
```

`ruff format` is deliberately **not** enforced. This codebase aligns assignments
into columns in settings, URL tables and Mongo documents; collapsing that is a
large diff containing no fix.

## Conventions

**Views do HTTP.** Parse a request, call a service, shape a response. If a view
is making decisions, those belong in `services/`.

**Repositories are the only code that knows which store is live.** Anything
importing `core.mongo` or `apps.*.models` outside `repositories/` is a layering
mistake. They return plain dicts, not model instances — see ARCHITECTURE.md.

**Both backends, always.** Adding a repository method means implementing it in
`repositories/mongo/` and `repositories/postgres/`, and adding it to the parity
suite. That suite is what makes `PERSISTENCE_BACKEND` trustworthy.

**Keep ML imports inside functions.** numpy, FAISS, torch and the tokenizer are
imported where used, so Django starts without loading them and a management
command does not pay for a model it will not use.

**Explain the why, not the what.** A comment saying what the next line does is
noise. A comment saying why it is that way — what breaks otherwise, what was
tried first — is the thing worth writing.

**Never silently swallow an exception.** `except Exception: pass` is a bug
waiting to be unfindable. Log it, or use `contextlib.suppress` with a comment
saying why nothing needs to happen.

## Changing retrieval

Anything touching chunking, embeddings, retrieval or the prompt must be measured
before and after:

```bash
python manage.py evaluate_rag --label before
# ... make the change ...
python manage.py evaluate_rag --label after
python manage.py evaluate_rag --compare
```

Two metrics are regression guards rather than targets, both currently 1.000:
**citation validity** (no invented page numbers) and **refusal accuracy** (every
out-of-scope control declined). If a retrieval change moves either, it broke
grounding — regardless of what it did to recall.

Changing chunk size, overlap or the embedding model invalidates every existing
chunk. Run `manage.py reprocess_documents` before trusting any measurement.

Groq's free tier rate-limits after roughly five full evaluation runs. Retrieval
metrics survive a generation failure, so a rate-limited run still reports usable
retrieval numbers and says how many cases were affected.

## Gotchas

- **Writing files with escape sequences via shell heredocs mangles them.** `\n`
  becomes a real newline. Use an editor.
- **Windows consoles are cp1252.** Piping model output through `print()` crashes
  on characters like U+202F. Set `PYTHONIOENCODING=utf-8`.
- **Celery on Windows needs `--pool=solo`.** Prefork does not work there.
- **`content_tsv` is maintained by a database trigger.** Never set it from
  application code.
- **The vector column is `vector(384)`**, fixed in the schema. Changing the
  embedding model is a migration plus a full re-embed, not a settings change. A
  system check catches the mismatch at startup.

## Adding an LLM provider

1. A module in `rag/llm/` satisfying `LLMProvider` — `complete`, `stream`,
   `supports_streaming`, `model`.
2. A branch in `rag/registry._llm`.
3. A conformance test alongside the existing ones.

Only add one you can actually run against a real endpoint. An adapter nobody has
exercised is three files that will not work the first time someone needs them,
plus a claim in the README that turns out to be false.

## Pull requests

CI runs ruff, pytest against real pgvector and Redis, a missing-migration check,
`check --deploy --fail-level WARNING`, the frontend tests and build, a
dependency audit, and both Docker image builds. Run the backend suite and
`ruff check` locally first — they are the two that fail most often.
