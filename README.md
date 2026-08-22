# Nexus RAG — a hybrid retrieval-augmented generation platform

Upload documents, then ask questions and get answers **grounded in those files** —
every fact carrying the page it came from, and an explicit refusal when the
documents do not contain the answer.

```
question ─┬─ vector retrieval (pgvector, HNSW/cosine) ──┐
          └─ keyword retrieval (PostgreSQL full-text) ──┴─ RRF ─ rerank ─ top_k
                                                                    │
                              grounded prompt ─ LLM ─ answer + page citations
```

The refusal is the point. A retrieval system that answers everything is
indistinguishable from a model answering from memory, and this one is built so
that it declines instead — measurably.

---

## What it does

- **Grounded answers with page citations.** `(Page 4)`, `(Pages 3, 7)`,
  `(report.pdf, Page 12)` — checkable against the source.
- **Refuses out-of-scope questions** rather than guessing.
- **Hybrid retrieval** — dense vectors for meaning, full-text for exact strings,
  fused by Reciprocal Rank Fusion, then reranked by a cross-encoder.
- **Streamed answers** over Server-Sent Events, with sources shown before the
  first token.
- **Background ingestion** on Celery: a 50-page PDF returns the upload request
  in ~200 ms and processes on a worker.
- **Scanned PDFs** are OCR'd page by page via a vision model.
- **Prompt-injection resistant** — document text is quoted data behind an
  unforgeable boundary, never instructions.
- **Per-user isolation** enforced in every query, with a test suite that proves
  it.
- **A measurable evaluation harness** — `manage.py evaluate_rag`.

## Measured, not asserted

Run `python manage.py evaluate_rag` against the bundled sample corpus. These are
real numbers from this repository, 21 cases (16 answerable, 5 control):

| configuration | recall | precision | MRR | context relevance |
|---|---|---|---|---|
| dense only, `top_k=6` | 1.000 | 0.220 | 0.969 | 0.660 |
| + keyword + RRF, `top_k=6` | 1.000 | 0.210 | **1.000** | 0.704 |
| + cross-encoder rerank, `top_k=3` | 1.000 | **0.365** | **1.000** | **0.833** |

Two things worth reading out of that table:

**Hybrid retrieval fixes ranking, not precision.** MRR reaching 1.000 means the
correct page is ranked first for every answerable question. The clearest case:
asked for `"Revision 7.2"`, dense retrieval returns *nothing* — the string means
nothing to an embedding — while full-text search finds it immediately.

**Precision only moves when `top_k` comes down, and reranking is what makes that
safe.** At `top_k=3` *without* reranking, recall falls to 0.969: a correct
passage is lost. *With* it, recall holds at 1.000 while precision nearly
doubles.

Two metrics stay pinned at 1.000 across every configuration and are treated as
regression guards rather than targets: **citation validity** (no invented page
numbers) and **refusal accuracy** (all five out-of-scope controls declined,
including a prompt-injection attempt).

> Recall is 1.000 throughout because the sample corpus holds 8 chunks and
> retrieval returns up to 6 of them. The harness detects this and prints a
> warning rather than letting the number be read as evidence.

## Stack

| Layer | Choice | Why |
|---|---|---|
| API | Django 4.2 + DRF | |
| Data | PostgreSQL 16 + pgvector | vectors, full-text and foreign keys in one place |
| Vectors | pgvector HNSW (cosine) | with a FAISS backend still selectable |
| Queue | Celery + Redis | ingestion off the request thread |
| Embeddings | all-MiniLM-L6-v2 via ONNX Runtime | local; ~90 MB, no per-upload API cost |
| Rerank | `ms-marco-MiniLM-L-6-v2` cross-encoder | optional; needs the PyTorch stack |
| LLM | Groq (`openai/gpt-oss-120b`) | behind a provider interface |
| RAG glue | `langchain-core` | interfaces only — see below |
| Frontend | React 18 + Vite + Tailwind | |

**On LangChain:** `langchain-core` only, for its *interfaces* — `Document`,
`Embeddings`, `BaseRetriever`, prompt templates — so components here compose
with off-the-shelf ones. Its *implementations* are deliberately not used;
`RecursiveCharacterTextSplitter` in particular splits a document as one
continuous string and loses the page a passage came from, and page numbers are
the product here.

## Quick start

### Docker (everything)

```bash
cp .env.docker.example .env      # then set GROQ_API_KEY
docker compose up --build
```

- frontend http://localhost:3000
- API http://localhost:8000/api/health/
- admin http://localhost:8000/django-admin/

```bash
docker compose exec api python manage.py create_admin --generate-password
```

### Local

```bash
python -m venv venv
venv/Scripts/python -m pip install -r backend/requirements.txt   # Windows
# .venv/bin/pip install -r backend/requirements.txt              # macOS / Linux

cp backend/.env.example backend/.env     # then set GROQ_API_KEY
cd backend && python manage.py migrate && python manage.py runserver
```

```bash
cd frontend && npm install && npm run dev
```

A free Groq key: <https://console.groq.com/keys>

### Try the evaluation

```bash
cd backend
python manage.py make_demo_corpus       # writes an 8-page sample policy PDF
# upload it through the UI, wait for processing
python manage.py load_eval_dataset
python manage.py evaluate_rag --label baseline
python manage.py evaluate_rag --compare
```

## Configuration

Everything is environment-driven; see [`backend/.env.example`](backend/.env.example)
for the annotated list. The switches that change behaviour most:

| Setting | Default | |
|---|---|---|
| `PERSISTENCE_BACKEND` | `mongo` | `mongo` \| `postgres` |
| `VECTOR_BACKEND` | `faiss` | `faiss` \| `pgvector` |
| `RAG_HYBRID_ENABLED` | `False` | needs `postgres` + `pgvector` |
| `RAG_RERANK_ENABLED` | `False` | needs the PyTorch stack |
| `RAG_QUERY_REWRITE` | `False` | one extra LLM call per follow-up |

The MongoDB and FAISS defaults are the project's original storage. Both
implementations are live and covered by the same test suite, which is what made
migrating to PostgreSQL possible without downtime. To move across:

```bash
python manage.py migrate_from_mongo --dry-run --users-from-sqlite db.sqlite3
python manage.py migrate_from_mongo --users-from-sqlite db.sqlite3
```

Then set `PERSISTENCE_BACKEND=postgres VECTOR_BACKEND=pgvector`.

## Tests

```bash
cd backend && pytest              # 300 tests
cd frontend && npm test           # 9 tests
```

The suite that matters most is `tests/test_repository_parity.py`: every
assertion runs **twice**, once per storage backend, so "the backend can be
swapped without the API changing" is asserted rather than hoped for. It found
three real defects, including a missing ownership filter.

`tests/test_security.py` covers prompt injection, upload validation, brute-force
lockout and cross-user isolation at the API surface.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — how the pieces fit and why they were chosen
- [API.md](API.md) — every endpoint
- [SECURITY.md](SECURITY.md) — the threat model and what is done about it
- [DEPLOYMENT.md](DEPLOYMENT.md) — running it somewhere real
- [CONTRIBUTING.md](CONTRIBUTING.md) — working on it

## Known limits

Stated plainly, because a README that lists only strengths is not useful.

- **The sample corpus is small.** Recall of 1.000 is a fact about an 8-chunk
  corpus, not about retrieval. Use a real document set for numbers that move.
- **Reranking needs PyTorch**, which `requirements-prod.txt` excludes (~800 MB).
  Without it the pipeline keeps fusion order and says so in the log.
- **Groq's free tier rate-limits** after roughly a hundred calls, which is about
  five full evaluation runs.
- **Only Groq is implemented.** The provider registry makes another adapter a
  new file, but writing one nobody has run against a real endpoint would be a
  claim the project cannot back up.
- **The admin analytics dashboard is an API, not a UI.**
  `GET /api/admin-panel/metrics/` returns the data; nothing renders it yet.
- **Hybrid retrieval ships off by default** because it requires PostgreSQL. The
  gains above are real but are not what a fresh clone runs.
