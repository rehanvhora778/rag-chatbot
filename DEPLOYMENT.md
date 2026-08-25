# Deploying the AI RAG Chatbot

There are two supported ways to run this. Both give you the full stack —
PostgreSQL + pgvector, hybrid retrieval, page-cited answers. They differ in who
operates the database and whether ingestion gets a real worker.

| | Docker Compose | Managed services |
|---|---|---|
| Store | PostgreSQL 16 + pgvector | PostgreSQL 16 + pgvector (Neon) |
| Hybrid retrieval | **yes** | **yes** |
| Reranking | yes | no — 512 MB RAM cannot hold PyTorch |
| Background worker | yes — Celery | no — falls back to a thread |
| Cost | your own host | free |
| Setup | one command | three services to wire together |

The managed route is what `render.yaml` describes and what the live demo runs.
The Docker route is what the measured retrieval numbers in the README were
produced on, because it is the one that can afford the cross-encoder.

---

## Option A — Docker Compose

```bash
cp .env.docker.example .env      # set GROQ_API_KEY and POSTGRES_PASSWORD
docker compose up --build
```

Brings up PostgreSQL with pgvector, Redis, the API, a Celery worker, beat, and
the frontend. Migrations run on start.

```bash
docker compose exec api python manage.py create_admin --generate-password
```

For a production-shaped stack — gunicorn instead of runserver, nginx instead of
the Vite dev server, no host ports on the database, and every secret required
rather than defaulted:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

It refuses to start without `SECRET_KEY`, `ALLOWED_HOSTS`,
`CORS_ALLOWED_ORIGINS`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `GROQ_API_KEY`
and `VITE_API_BASE_URL`. That is deliberate: a stack that boots with defaults is
a stack that gets deployed with them.

`VITE_API_BASE_URL` is a **build argument**, not a runtime variable — Vite bakes
it into the bundle, so changing it means rebuilding the frontend image rather
than restarting the container.

### Turning hybrid retrieval on

```bash
PERSISTENCE_BACKEND=postgres
VECTOR_BACKEND=pgvector
RAG_HYBRID_ENABLED=True
RAG_RERANK_ENABLED=True      # needs requirements.txt, not requirements-prod.txt
RAG_TOP_K=3
```

A system check refuses to start if these are inconsistent — hybrid retrieval
without PostgreSQL would silently degrade to vector-only, which is exactly the
kind of thing that goes unnoticed.

### Migrating an existing MongoDB deployment

```bash
docker compose exec api python manage.py migrate_from_mongo --dry-run     --users-from-sqlite db.sqlite3
docker compose exec api python manage.py migrate_from_mongo     --users-from-sqlite db.sqlite3
```

Re-runnable, so rehearse it first. Users come from the SQLite file with their
primary keys and password hashes intact — every Mongo record references a user
by the id those tables issued.

Chunks written before vector persistence have text but no embedding. The command
reports how many, and they need `reprocess_documents` before they are visible to
vector search.

Keep `PERSISTENCE_BACKEND=mongo` until you have verified the copy, then switch.
Both implementations stay live and are covered by the same test suite.

---

## Option B — Managed services (Neon + Render + Vercel)

Three free services, each doing the thing it is best at:

| Piece | Platform | Free tier |
|---|---|---|
| Database — documents, chunks, **vectors**, chats, users | **Neon** (PostgreSQL 16 + pgvector) | 0.5 GB, permanent |
| Backend API (Django + ONNX + Groq) | **Render** | 512 MB RAM, sleeps when idle |
| Frontend (React SPA) | **Vercel** | 100 GB bandwidth |

```
Browser ──> Vercel (React)  ──HTTPS──>  Render (Django API)  ──>  Neon (Postgres + pgvector)
                                              │
                                              └──>  Groq API (gpt-oss-120b)
```

**Why Neon and not Render's own PostgreSQL.** Render's free database is deleted
after 30 days. That is fine for a viva and wrong for a link on a CV, which is
the whole point of keeping this deployed. Neon's free tier has no expiry, runs
PostgreSQL 16, and allows the `vector` extension — the three things this
project needs.

**What the migration buys you here specifically.** On the old stack the free
tier wiped `db.sqlite3` on every deploy, which meant every registered account
disappeared. Django's auth tables now live in Neon with everything else, so
**accounts survive restarts**. Only the original uploaded files in `media/` are
still lost, and answers no longer depend on them — the chunks and their vectors
are rows in the database.

> **`GROQ_MODEL` is pinned in `render.yaml`.** Groq retires models without
> notice and the failure is quiet: `llama-3.3-70b-versatile` began returning
> `404 model_not_found`, which broke chat answers and left every document
> summary reading *"Summary could not be generated."* If answers start failing,
> check [Groq's model list](https://console.groq.com/docs/models) first. Note
> that `qwen/qwen3.6-27b` is available but unsuitable as the chat model — it
> emits its `<think>` reasoning into the reply body; it is used only for vision
> OCR.

Deploy in this order — each step needs a value from the one before it.

---

## Before you start

Have these ready:

- The project pushed to a **GitHub** repository
- A **Groq API key** — https://console.groq.com/keys

> **Rotate your keys first.** Anything that has been sitting in a local
> `backend/.env` should be regenerated before it goes into a hosting dashboard.
> `.env` is gitignored so it is not in your repo, but generate fresh values and
> paste those into Render instead.

> **OTP email does not work over SMTP on Render's free tier, and no Gmail App
> Password will fix it.** Free instances have no outbound SMTP:
> `smtp.gmail.com:587` fails with `[Errno 101] Network is unreachable`. Two
> options that do work: set `BREVO_API_KEY`, which sends over HTTPS and takes
> precedence over the SMTP settings; or leave the email variables blank, and
> Django falls back to the console backend and prints the code into the service
> log — search the Render logs for `OTP`.

---

## Step 1 — Neon (the database)

1. Sign up at https://console.neon.tech
2. **Create a project** — Postgres 16, region near your Render region (`AWS
   us-west-2` pairs well with Render's `oregon`; keeping them close matters
   more than either being close to you, because every query is server-to-server)
3. On the dashboard, copy the connection string. **Take the direct one** — the
   host must *not* contain `-pooler`:

   ```
   postgresql://user:pass@ep-xxx.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

   Keep `?sslmode=require` on the end. Neon refuses unencrypted connections and
   `dj_database_url` passes the parameter straight through to psycopg.

   **Why not the pooled endpoint**, which is usually the right default and is
   not here. Django 4.2 talks to PostgreSQL through psycopg 3, which promotes a
   query to a server-side prepared statement after five executions. Neon's
   pooler is pgBouncer in transaction mode, where consecutive queries from one
   Django connection can land on different server connections — so the prepared
   statement is either missing or its name collides with one another session
   left behind. The symptom is `prepared statement "_pg3_0" already exists`,
   appearing intermittently and only under load, and reading like a Django bug
   rather than a pooling one.

   That is fixable — `'OPTIONS': {'prepare_threshold': None}` on the database
   config — but it is not worth doing here. A free Render instance runs one
   gunicorn worker with four threads, so it holds roughly four connections
   against a limit of a hundred. Pooling solves a problem this deployment does
   not have, at the cost of one that is genuinely hard to diagnose.

   Add the option first if you ever scale the worker count up far enough to
   need the pooler.

4. You do **not** need to create tables, or run `CREATE EXTENSION vector`
   yourself. `build.sh` runs `manage.py migrate` on every deploy, and
   `apps/documents/migrations/0001_initial.py` starts with `VectorExtension()`
   — `CREATE EXTENSION IF NOT EXISTS vector`, which is idempotent.

Keep the connection string. It is `DATABASE_URL` in the next step.

---

## Step 2 — Render (the backend API)

1. Sign up at https://render.com with GitHub
2. **New +** → **Blueprint** → select your repository

   Render reads `render.yaml` from the repo root and configures the service.
   (Prefer clicking through instead? **New +** → **Web Service**, set *Root
   Directory* `backend`, *Build Command* `bash ./build.sh`, *Start Command*
   `gunicorn config.wsgi:application --workers 1 --threads 4 --timeout 180`,
   then add every variable marked `sync: false` in `render.yaml` by hand.)

3. Render prompts for the secret environment variables. Fill them in:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the pooled Neon string from Step 1 |
   | `GROQ_API_KEY` | your Groq key |
   | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` for now — fixed in Step 4 |
   | `DEFAULT_ADMIN_EMAIL` | the admin account to create |
   | `DEFAULT_ADMIN_PASSWORD` | a strong password |
   | `BREVO_API_KEY` | for real OTP delivery, or leave blank |
   | `EMAIL_HOST_USER` | **leave blank** — SMTP is blocked, see above |
   | `EMAIL_HOST_PASSWORD` | leave blank |

   `SECRET_KEY` is generated by Render. Everything that selects the upgraded
   stack — `PERSISTENCE_BACKEND=postgres`, `VECTOR_BACKEND=pgvector`,
   `RAG_HYBRID_ENABLED=True` — is already fixed in `render.yaml`.

   **`MONGODB_HOST` is no longer needed.** Nothing reads it once
   `PERSISTENCE_BACKEND=postgres`, and the Mongo client is created lazily, so
   an absent value is never dialled. If you are keeping an Atlas cluster around
   as a fallback, leaving the variable set does no harm.

4. **Create** and watch the log. The first build takes **5–10 minutes** — it
   installs the ML packages and downloads the embedding model.

5. When it says *Live*, test it:

   ```
   https://<your-service>.onrender.com/api/health/
   ```

   You want:

   ```json
   {
     "status": "healthy",
     "service": "AI RAG Chatbot API",
     "persistence": "postgres",
     "vector_backend": "pgvector",
     "hybrid_retrieval": true,
     "reranking": false,
     "database": "connected"
   }
   ```

   Read those middle three fields, not just `status`. They are the check that
   the upgraded stack is what actually booted: all of them are derived from
   whether `DATABASE_URL` parsed, so a typo in the connection string does not
   crash the service — it quietly starts the *old* stack, which looks identical
   from the UI until the first question comes back worse.

   | What you see | What it means |
   |---|---|
   | `"persistence": "mongo"` | `DATABASE_URL` is unset or unparseable. Recheck it. |
   | `"database": "unavailable"` | Neon is not reachable. Check the password and that `?sslmode=require` survived the paste. |
   | `"database": "connected (pgvector missing)"` | Migrations did not run. Check the build log for the `migrate` step. |

**Copy your backend URL.** You need it next.

---

## Step 3 — Vercel (the frontend)

1. Sign up at https://vercel.com with GitHub
2. **Add New** → **Project** → import your repository
3. Set **Root Directory** to `frontend`

   Vercel detects Vite and reads `frontend/vercel.json` for the rest. The
   rewrite rule in that file is what stops a hard refresh on `/chat` or
   `/documents` returning 404 — every path must serve `index.html` so React
   Router can handle it.
4. Add environment variables:

   | Variable | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://<your-service>.onrender.com` (no trailing slash) |
   | `VITE_GOOGLE_CLIENT_ID` | your Google OAuth client id, or leave blank |

   These are baked into the bundle at build time, so **changing them later
   needs a redeploy**, not just a restart. If you ever recreate the Render
   service and it comes back on a different hostname, this is the variable that
   has to change — and redeploying Vercel is what makes it take effect.
5. **Deploy**, then copy your frontend URL (`https://<project>.vercel.app`).

---

## Step 4 — Connect the two

The browser blocks the frontend from calling the backend until the backend says
that origin is allowed.

1. Render → your service → **Environment** → edit `CORS_ALLOWED_ORIGINS`:

   ```
   https://<project>.vercel.app
   ```

   No trailing slash, and include `https://`. Multiple origins are
   comma-separated. Save — Render redeploys automatically.

2. **Using Google sign-in?** Add both URLs at
   https://console.cloud.google.com/apis/credentials → your OAuth client →
   *Authorised JavaScript origins*:

   ```
   https://<project>.vercel.app
   http://localhost:3000
   ```

3. Open your Vercel URL and check the whole flow:
   - Register → read the code from the Render log (search `OTP`) → account created
   - Upload a PDF → status reaches **Ready**
   - Ask a question → answer streams in with `(Page N)` citations
   - Ask something the document does not cover → it should **refuse**
   - Ask for an exact string in the document (a code, a revision number) —
     this is the one hybrid retrieval added; on the old stack it failed
   - Sign in at `/admin-login` with your `DEFAULT_ADMIN_EMAIL`

---

## What the free tier costs you

These are real limits, not warnings to skim. Know them before your demo.

**The backend sleeps after 15 minutes of inactivity.** The next request has to
wake it, which takes **around 50 seconds**. Open the site a minute before you
present and it will be warm. (A cron ping every 10 minutes keeps it awake, but
that burns your monthly instance hours.)

**Neon suspends an idle compute after 5 minutes.** It wakes on the next
connection, costing well under a second — and it almost never shows, because
Render's own 50-second wake happens first and the database is already up by the
time Django asks it anything. `conn_health_checks` is on in `settings.py`, so a
connection that died during the pause is replaced rather than raising.

**The disk is still wiped on every deploy and restart** — but this now costs
much less than it did:

| Lost on restart | Consequence |
|---|---|
| Uploaded PDFs (`media/`) | The original file is gone; **answers still work** |
| `indexes/` (FAISS) | Not used — vectors are rows in Neon |
| Django's user table | **Not lost any more** — it is in Neon |

Chunks, embeddings, chat history and accounts all live in PostgreSQL, so the
only casualty is downloading the source file you uploaded. On the old stack
this section was the worst thing about the free tier; the migration is most of
the reason it no longer is.

**Ingestion runs in a thread, not on a worker.** Render's background workers
are paid-only, so `queue_processing` pings for a live Celery worker, finds
none, logs that it is falling back, and processes the upload in a daemon
thread. The failure mode is narrow but real: an instance restart *during*
ingestion loses that one job, and the document stays at "processing". Re-upload
it. `render.yaml` has the worker and Key Value blocks commented out ready to
uncomment when there is a budget.

**512 MB RAM.** One gunicorn worker plus the ONNX embedding model fits, without
much headroom. Do not raise `--workers` above 1 on the free plan, and leave
`RAG_RERANK_ENABLED=False` — the cross-encoder needs PyTorch, which is ~520 MB
on its own and is excluded from `requirements-prod.txt` for exactly that reason.

**Groq's free tier rate-limits** after roughly a hundred calls. That is also
why `RAG_QUERY_REWRITE` is off: it spends an extra call per follow-up question,
and a rate-limited rewrite costs you the answer, not just the rewrite.

---

## If something breaks

**Health says `"persistence": "mongo"` on a deployment that should be Postgres**
`DATABASE_URL` is unset, misspelled, or failed to parse. Every stack switch is
derived from it, so this one variable being wrong silently reverts the whole
deployment to the old behaviour. Check it in the Render dashboard first.

**Health says `"database": "connected (pgvector missing)"`**
The connection works but `CREATE EXTENSION vector` never ran. Almost always a
build where `migrate` failed or was skipped — read the build log. On Neon the
extension is allowed by default; on a managed Postgres that forbids it, no
amount of retrying will help and you need a provider that permits pgvector.

**Build fails with `permission denied: ./build.sh`**
`render.yaml` already uses `bash ./build.sh` to avoid this. If you configured
the service by hand, set the build command to `bash ./build.sh` too — git on
Windows does not carry the executable bit.

**Build runs out of memory or times out**
Confirm the build is installing `requirements-prod.txt`, not `requirements.txt`.
The dev file pulls in PyTorch (~520 MB), which the free tier cannot take. The
ONNX backend produces identical vectors, so nothing about the answers changes.

**`DisallowedHost` in the logs**
Render sets `RENDER_EXTERNAL_HOSTNAME` and `settings.py` appends it to
`ALLOWED_HOSTS` automatically. If you use a custom domain, add it to the
`ALLOWED_HOSTS` variable yourself.

**Frontend loads but every request fails, console says CORS**
`CORS_ALLOWED_ORIGINS` on Render does not exactly match your Vercel URL. It must
include the scheme and have no trailing slash.

**Hard refresh on `/chat` gives a 404**
`frontend/vercel.json` is missing or the Root Directory is not set to `frontend`.

**OTP email never arrives**
Set `BREVO_API_KEY` — SMTP does not work on a free instance whatever you put in
`EMAIL_HOST_USER`. Without either, Django uses the console backend and prints
the code into the Render log.

**First question after a deploy is very slow**
Expected. The instance is waking and loading the embedding model lazily
(`EMBEDDING_PRELOAD=false`, which is deliberate — preloading deadlocks the
upload path). Subsequent questions are fast.

**A document sits at "processing" forever**
The instance restarted mid-ingest and the thread went with it. Re-upload.
This is the failure a Celery worker exists to remove; see the commented blocks
in `render.yaml`.

**Every answer is "I could not find an answer"**
On this stack that means retrieval genuinely returned nothing — the vectors are
in the database, so the old "the index file was wiped" cause is gone. Check
that the document reached **Ready** rather than "processing", then confirm with
`RAG_DEBUG=true`, which returns the retrieved passages and their similarity
scores alongside the answer.

---

## Deploying an update

Both platforms watch your GitHub repo and redeploy on push to `main`:

```bash
git add .
git commit -m "Your change"
git push
```

Render rebuilds the API (a few minutes); Vercel rebuilds the frontend (under a
minute). Migrations run automatically as part of `build.sh`, so a schema change
ships with the code that needs it.

Render's disk is still wiped by this, which now costs you only the uploaded
source files — see above.
