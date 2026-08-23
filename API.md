# API reference

Base URL `http://localhost:8000`. Every route below is real — this list was
generated from the URL resolver, not written from memory.

## Conventions

All JSON responses share one envelope:

```jsonc
// success
{ "success": true, "message": "Success", "data": { } }

// paginated
{ "success": true, "data": [ ], "pagination": {
    "total": 42, "page": 1, "page_size": 20,
    "total_pages": 3, "has_next": true, "has_previous": false } }

// failure
{ "success": false, "message": "Document not found.", "errors": null }
```

**Authentication** — `Authorization: Bearer <access_token>` on everything except
`/api/health/` and the auth endpoints marked *public*. Access tokens last 1 hour,
refresh tokens 7 days and rotate on use.

**Ownership** — a resource belonging to another user returns **404**, never 403.
Distinguishing them would confirm that a given id exists.

**Request ids** — every response carries `X-Request-ID`. Send your own and it is
preserved, which is what makes a trace work across services.

**Status codes** — `400` validation, `401` unauthenticated, `403` authenticated
but not permitted, `404` missing *or not yours*, `429` rate limited, `500`
unexpected.

---

## Authentication

| Method | Path | |
|---|---|---|
| POST | `/api/auth/register/` | *public* · start sign-up, emails a code |
| POST | `/api/auth/register/verify/` | *public* · confirm the code, creates the account |
| POST | `/api/auth/register/resend/` | *public* · resend the code |
| POST | `/api/auth/login/` | *public* · email + password |
| POST | `/api/auth/admin/login/` | *public* · same, rejects non-staff |
| POST | `/api/auth/google/` | *public* · exchange a Google ID token |
| GET | `/api/auth/google/config/` | *public* · client id, or blank if disabled |
| POST | `/api/auth/password-reset/` | *public* · emails a code |
| POST | `/api/auth/password-reset/verify/` | *public* · confirm the code, returns a ticket |
| POST | `/api/auth/password-reset/confirm/` | *public* · set a new password |
| POST | `/api/auth/token/refresh/` | exchange a refresh token |
| POST | `/api/auth/logout/` | blacklists the refresh token |
| GET | `/api/auth/profile/` | the current user |
| POST | `/api/auth/change-password/` | |

Every public endpoint here is rate limited per IP (`AUTH_THROTTLE_RATE`, default
`10/min`). Accounts additionally lock for 15 minutes after 8 failed sign-ins.

```http
POST /api/auth/login/
{ "email": "you@example.com", "password": "…" }

200 { "success": true, "data": {
       "user": { "id": 8, "email": "…", "is_staff": false },
       "tokens": { "access": "…", "refresh": "…" } } }

401 { "success": false, "message": "Incorrect email or password." }
```

> One message covers both a missing account and a wrong password, and the
> password hash is computed even when no account exists — otherwise the timing
> difference alone reveals which addresses are registered.

## Documents

| Method | Path | |
|---|---|---|
| GET | `/api/documents/` | list, newest first · `?page=&page_size=` |
| POST | `/api/documents/` | upload · multipart, field `files` (repeatable) |
| GET | `/api/documents/status/` | batch poll · `?ids=a,b,c` |
| GET | `/api/documents/{id}/` | one document |
| PATCH | `/api/documents/{id}/` | rename · `{ "original_filename": "…" }` |
| DELETE | `/api/documents/{id}/` | document, chunks, file and index |
| POST | `/api/documents/{id}/reprocess/` | re-run ingestion |
| GET | `/api/documents/{id}/summary/` | the AI summary |
| POST | `/api/documents/{id}/summary/` | regenerate it |

```http
POST /api/documents/          (multipart)

201 { "success": true,
      "message": "2 document(s) queued for processing.",
      "data": { "uploaded": [ { "id": "…", "status": "pending", … } ],
                "errors": ["notes.exe: Unsupported file type \".exe\"."] } }
```

Partial success is normal: each file is validated independently, so one
rejection does not fail the batch. The upload returns in roughly 200 ms —
extraction, chunking and embedding happen on a worker.

Uploads are validated on **content**, not extension: a ZIP renamed to `.pdf` is
rejected, and the message says what the file actually is.

```http
GET /api/documents/status/?ids=abc,def

200 { "data": [
  { "id": "abc", "status": "completed", "chunk_count": 8, "has_summary": true },
  { "id": "def", "status": "missing" } ] }
```

`missing` means deleted *or not yours* — the UI should stop polling either way.

## Chat

| Method | Path | |
|---|---|---|
| GET | `/api/chat/sessions/` | list conversations |
| POST | `/api/chat/sessions/` | create · `{ "title", "document_ids": [] }` |
| GET | `/api/chat/sessions/{id}/` | conversation + full transcript |
| PATCH | `/api/chat/sessions/{id}/` | rename, archive, or re-ground |
| DELETE | `/api/chat/sessions/{id}/` | conversation and its messages |
| POST | `/api/chat/sessions/{id}/message/` | ask · blocking JSON |
| POST | `/api/chat/sessions/{id}/stream/` | ask · Server-Sent Events |
| GET | `/api/chat/sessions/{id}/export/` | transcript as PDF |
| GET | `/api/chat/search/` | search titles · `?q=` |
| GET | `/api/chat/config/` | the engine's read-only settings |
| GET/POST | `/api/chat/messages/{id}/feedback/` | thumbs up/down |

Both ask endpoints are rate limited (`CHAT_THROTTLE_RATE`, default `20/min`).

```http
POST /api/chat/sessions/{id}/message/
{ "question": "How long do I have to return a domestic order?" }

200 { "data": {
  "answer": "Domestic orders may be returned within **30 days** (Page 2).",
  "citations": [ { "document_name": "policy.pdf", "page_number": 2,
                   "similarity_score": 0.5594, "excerpt": "…" } ],
  "session_id": "…" } }
```

Add `?debug=true` for retrieval diagnostics — per-chunk scores, timings, which
retriever found what.

### Streaming

```http
POST /api/chat/sessions/{id}/stream/     →  text/event-stream
```

```
event: sources
data: {"citations":[{"document_name":"policy.pdf","page_number":2}],"retrieval_ms":210}

event: token
data: {"text":"Domestic orders "}

event: security
data: {"findings":[{"pattern":"instruction_override","document_name":"policy.pdf","page_number":4}]}

event: done
data: {"message_id":"…","refused":false,"retrieval_ms":210,"generation_ms":1840}
```

`sources` always arrives **before** the first token, so the UI can render
citations while the answer is still being written. `done` carries the
`message_id`, which does not exist until the turn is stored and which feedback
attaches to.

`security` means a retrieved passage contains text shaped like an injected
instruction. The answer is still produced — the passage was neutralised — but
the user should know their document contains it.

Failures *before* the stream starts (404, 400, 429) arrive as ordinary JSON.
Failures during it arrive as an `error` event, because the status code has
already been sent.

Use `fetch` + `ReadableStream`, not `EventSource` — the latter cannot set an
`Authorization` header. See `frontend/src/api/chat.js`.

### Feedback

```http
POST /api/chat/messages/{id}/feedback/
{ "rating": -1, "reason": "missing", "comment": "no international detail" }
```

`rating` is `1` or `-1`. `reason` is one of `incorrect`, `irrelevant`,
`missing`, `hallucination`, `other` — only meaningful on a negative rating, and
dropped on a positive one. One verdict per message: rating again replaces it.

## Analytics

| Method | Path | |
|---|---|---|
| GET | `/api/analytics/` | the caller's own usage |
| GET | `/api/analytics/dashboard/` | the caller's dashboard figures |

## Admin — staff only, `403` otherwise

| Method | Path | |
|---|---|---|
| GET | `/api/admin-panel/stats/` | row counts |
| GET | `/api/admin-panel/metrics/` | latency, tokens, feedback · `?days=7` |
| GET | `/api/admin-panel/users/` | |
| GET/PATCH/DELETE | `/api/admin-panel/users/{id}/` | |
| GET | `/api/admin-panel/documents/` | |
| DELETE | `/api/admin-panel/documents/{id}/` | |
| GET | `/api/admin-panel/chats/` | |
| DELETE | `/api/admin-panel/chats/{id}/` | |

`/metrics/` requires `PERSISTENCE_BACKEND=postgres` and says so when it is not
set, rather than returning zeroes that look like a system doing nothing.

## Health

```http
GET /api/health/     (public)

200 { "status": "healthy", "mongodb": "connected", "service": "AI RAG Chatbot API" }
```

Returns `degraded` with `200` when a dependency is unreachable — a container
healthcheck should restart on an unreachable process, not on a database blip.

## Not yet available

**OpenAPI/Swagger.** `drf-spectacular` is not installed. The API is entirely
`APIView`-based with hand-shaped envelopes rather than serializer-typed
responses, so generated schemas would document a shape the code does not
actually return. Adding it means annotating each view — worth doing, and not yet
done.
