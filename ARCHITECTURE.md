# Architecture

How the pieces fit, and — more usefully — why each one is shaped the way it is.
Where a decision had a real alternative, the alternative is named.

## The shape

```
React + Tailwind
      │  JWT · axios · SSE (fetch + ReadableStream)
      ▼
Django REST Framework  ── views: HTTP only
      │
      ▼
services/              ── the rules: validation, quotas, orchestration
      │
      ├──────────────► rag/          ── retrieval, prompting, generation
      │                   ├ retrievers/  vector · keyword · hybrid (RRF)
      │                   ├ reranking/   cross-encoder
      │                   ├ vectorstores/ pgvector · FAISS
      │                   ├ llm/         provider interface (Groq)
      │                   ├ prompts/     the grounding prompt
      │                   └ security/    prompt-injection defence
      │
      ▼
repositories/          ── the only layer that knows which store is live
      │
      ├─ postgres/  ── Django ORM  ── PostgreSQL 16 + pgvector
      └─ mongo/     ── pymongo     ── MongoDB (original store)

Celery + Redis ── ingestion: extract → chunk → embed → store
```

## Why the layers exist

**Views do HTTP and nothing else.** `apps/documents/views.py` went from 288
lines to 132, `apps/chat/views.py` from 347 to 177. What moved out was not
duplication — it was logic that could not be tested without a request object, a
live MongoDB, and a Groq key.

**Services own the rules.** What may be uploaded, what counts as a duplicate,
what deleting a document has to clean up and in what order. Callable from a
test, a management command or a Celery task.

**Repositories own storage.** They return plain dicts rather than model
instances, which looks like a weaker contract and is chosen deliberately: the
two implementations have nothing in common to return — BSON documents on one
side, Django models on the other — so any shared object type would be a
translation layer built twice. Dicts in a documented shape *are* that layer, and
they are already what the React app consumes.

That choice is what made the storage migration possible. `PERSISTENCE_BACKEND`
selects an implementation; `tests/test_repository_parity.py` runs every
assertion against both, so the claim that they are interchangeable is asserted
rather than assumed. It caught three real defects, including one implementation
storing document ids without checking ownership.

## Retrieval

```
question
   │
   ├─ query rewriting (optional) ── resolves "what about international purchases?"
   │                                against the conversation, BEFORE retrieval
   ▼
   ├─ vector retrieval ── pgvector, HNSW over cosine, fetch_k candidates
   └─ keyword retrieval ── PostgreSQL full-text, strict AND then broadened OR
   │
   ▼
Reciprocal Rank Fusion ── rank-based, never score-based
   │
   ▼
cross-encoder rerank (optional) ── scores (query, passage) pairs directly
   │
   ▼
context budget ── whole passages dropped, never truncated mid-sentence
   │
   ▼
grounded prompt ── passages wrapped in nonce-delimited blocks
```

### Why both retrievers

A dense embedding compresses a passage into 384 numbers capturing what it is
*about*, which is why it fails on things that mean nothing in isolation: an
order number, `Section 8.2`, a product code, an acronym. Those are exactly the
queries where the user knows precisely what they want.

Full-text search has the mirror-image weakness — it cannot tell that "refund
window" and "return period" are the same question.

Measured on the sample corpus: asked for `"Revision 7.2"`, vector retrieval
returns nothing at all; keyword search finds it on page 1.

### Why RRF, and why rank not score

Cosine similarity is bounded and means "close in meaning". PostgreSQL's
`ts_rank` is unbounded and means "often, prominently". Averaging them is
meaningless.

Normalising per query is *worse* than meaningless: min-max scaling makes the
best result in a list of terrible results score 1.0, so a query the keyword side
found nothing useful for still contributes a confident top hit.

RRF discards the scores and keeps only positions:

```
score(d) = Σ  1 / (k + rank(d))          k = 60
```

A passage both retrievers rank highly wins outright. That "found by both" signal
is most of what makes hybrid better than either half, and the fused document
records which retrievers found it — the difference between "both agreed" and
"only keyword found this" is most of what makes the pipeline debuggable.

### Why the reranker is last

A bi-encoder embeds query and passage *separately*, which is what makes
searching a whole corpus feasible — the passage vectors were computed at
ingestion and never recomputed. The cost is that a passage was embedded with no
knowledge of the question.

A cross-encoder reads query and passage *together*. Far more accurate, far too
slow for a corpus. So: retrieve wide and cheap, rerank narrow and accurate. That
ordering is what makes it reasonable to hand the model three passages instead of
six.

### The relevance floor runs before MMR

Deliberately changed from the original pipeline, which filtered afterwards. MMR
picks a varied set from among *relevant* passages, so spending one of its `k`
slots on a passage about to be discarded wastes it. Measured cost: 5.19 passages
per question against 5.00, which shows as slightly lower precision.

## Storage

### Why PostgreSQL replaced MongoDB

The original design used SQLite for Django's auth tables and MongoDB for
everything else, joined by an integer user id. That had no foreign keys: deleting
a user orphaned their documents, chunks, uploaded files and index files. It also
meant no ORM models, so Django Admin could show only Users, and nothing was
testable without a live Mongo.

Moving to PostgreSQL solved three requirements with one change — models and
therefore an admin and tests, `pgvector` for vector search where the data
already is, and full-text search for the keyword half of hybrid retrieval.

### Why the vector lives on the chunk row

`DocumentChunk.owner_id` is denormalised from `document.owner`. Every retrieval
filters by owner, and an HNSW index cannot satisfy a predicate it does not
contain — reaching the owner through a join means the filter is applied *after*
the vector scan has already chosen its candidates. Holding `owner_id` on the
chunk keeps filter and index on one table.

### What FAISS cost, and why it is still here

FAISS indexes are files. On a host without a persistent disk they vanish on
every restart, they cannot be filtered by anything the file does not contain,
and two processes writing the same document race.

The implementation remains selectable because a migration you cannot roll back
is not a migration. Both satisfy `VectorStore`, and retrieval was verified
identical between them — same pages, same scores to four decimal places — before
pgvector became the recommended path.

### `content_tsv` is maintained by a database trigger

Three separate paths write chunks: the ingestion task, the Mongo migration
command, and bulk operations from a shell. A column each of them must remember
to populate is a column that will be wrong.

## Ingestion

```
upload ─ validate ─ store file ─ create row ─► Celery ─► extract ─ chunk ─ embed ─ store
   │                                                                            │
   └── returns in ~200 ms with status=pending          generate_summary ◄────────┘
```

Previously a `threading.Thread` started inside the view. Under gunicorn a
deploy, worker recycle or OOM kill took the job with it: the document sat at
"processing" forever, with no retry and no record.

`acks_late` and `reject_on_worker_lost` redeliver a job whose worker died. That
is only safe because ingestion is **idempotent** — it drops existing chunks and
the index before writing, never appends. Two tests assert exactly that, because
it is the assumption the whole retry configuration rests on.

The summary is a *chained* task. The document is answerable without it, and it
fails for entirely different reasons (rate limits, a retired model). Marking a
perfectly indexed document as failed because Groq was busy would be worse than a
missing summary.

`sweep_stuck_documents` covers what `acks_late` cannot: if the broker loses a job
outright, nothing redelivers it and the UI polls a spinner forever.

## Prompt injection

Retrieved text is untrusted input that happens to live in the user's own files.
Three layers:

1. **Structural.** Passages are wrapped in delimiters carrying a nonce generated
   per request. Document text cannot close a block whose terminator it cannot
   predict. This is the layer that holds.
2. **Instructional.** The system prompt names those exact delimiters and states
   everything between them is quoted data — including text claiming otherwise.
3. **Detection.** Known shapes are logged with document and page. Deliberately
   *not* blocking: pattern matching on natural language cannot be made reliable,
   and a filter dropping passages a heuristic disliked would censor a security
   policy discussing prompt injection.

**Content is never modified.** An answer cites a page so a human can check it;
rewriting what the model read would make that citation point at something else.
Injected text is made inert, not absent.

Verified against the live model with a passage combining instruction override,
role reassignment, prompt exfiltration, grounding bypass and forged delimiters:
all detected, forgery contained, system prompt not leaked — and the model still
cited `(Page 2)` despite being instructed not to.

## Evaluation

`manage.py evaluate_rag` scores the pipeline through the same functions the chat
endpoint uses, not a reimplementation.

Deterministic metrics by default — free, instant, reproducible, so a score from
today is comparable with one from six months from now. `--judge` adds LLM-graded
faithfulness and correctness, opt-in because each case costs an API call and the
verdict varies between runs.

A proxy is always reported under its own name: `faithfulness_lexical`, never
`faithfulness`. Quietly substituting a weaker measure under the same label is
how an evaluation starts lying.

**Citation validity** is the metric most specific to this project. The promise is
that every fact carries its page; a model inventing `(Page 47)` produces an
answer that looks *more* trustworthy than an uncited one and is impossible to
check.

Control cases — questions the documents do not answer — are half the dataset's
value. Without them an evaluation cannot distinguish a grounded pipeline from a
model answering out of memory.

## Observability

Every log line carries a request id, generated per request, returned in
`X-Request-ID`, and accepted from an upstream service when already assigned:

```
[2026-08-22 11:57:17] [INFO] [core.mongo] [req=10b8621a802545ed user=8] ...
```

Stored in a `ContextVar` rather than on the request: the code that logs is
several layers below the view, and threading a request through the repository
and the retriever to reach a log line would be worse than the problem.

`GET /api/admin-panel/metrics/` reads latency, tokens, model mix and feedback
from what the pipeline already records — those are columns on the message row,
which is why this is a query rather than new instrumentation.

## Things deliberately not done

- **WebSockets** for streaming. Data flows one way; SSE is plain HTTP and works
  through the existing auth, CORS and WSGI deployment.
- **LangChain's implementations.** Its interfaces compose; its text splitter
  loses page numbers.
- **Untested LLM adapters.** The registry makes another provider a new file, but
  an adapter nobody has run is a claim, not support.
- **Blocking on a heuristic injection filter.** Detection informs; the nonce
  boundary defends.
- **Virus scanning and full PDF structure validation.** Both need a dedicated
  service; a token effort would give false confidence.
