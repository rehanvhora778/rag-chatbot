# Deploying the AI RAG Chatbot

There are two supported ways to run this, and which you want depends on whether
you need the hybrid retrieval features.

| | Docker Compose | Managed services |
|---|---|---|
| Store | PostgreSQL 16 + pgvector | MongoDB Atlas |
| Hybrid retrieval | **yes** | no — needs PostgreSQL full-text |
| Reranking | yes | no — image excludes PyTorch |
| Background worker | yes | no — falls back to a thread |
| Cost | your own host | free tiers |
| Setup | one command | three services to wire together |

The managed-services route is documented in full below and is what
`render.yaml` describes. The Docker route is newer and is what the measured
retrieval numbers in the README were produced on.

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

## Option B — Managed services (Render + Atlas + Vercel)

Three free services, each doing the thing it is best at:

| Piece | Platform | Free tier |
|---|---|---|
| Database (documents, chunks, chats, users' OTPs) | **MongoDB Atlas** | 512 MB, permanent |
| Backend API (Django + FAISS + Groq) | **Render** | 512 MB RAM, sleeps when idle |
| Frontend (React SPA) | **Vercel** | 100 GB bandwidth |

```
Browser ──> Vercel (React)  ──HTTPS──>  Render (Django API)  ──>  MongoDB Atlas
                                              │
                                              └──>  Groq API (gpt-oss-120b)
```

> **`GROQ_MODEL` is pinned in `render.yaml`.** Groq retires models without
> notice and the failure is quiet: `llama-3.3-70b-versatile` began returning
> `404 model_not_found`, which broke chat answers and left every document
> summary reading *"Summary could not be generated."* No Llama chat model
> remains on Groq. If answers start failing, check
> [Groq's model list](https://console.groq.com/docs/models) first. Note that
> `qwen/qwen3.6-27b` is available but unsuitable as the chat model — it emits
> its `<think>` reasoning into the reply body; it is used only for vision OCR.

Deploy in this order — each step needs a URL from the one before it.

---

## Before you start

Have these ready:

- The project pushed to a **GitHub** repository
- A **Groq API key** — https://console.groq.com/keys

> **OTP email does not work on Render's free tier, and no Gmail App Password
> will fix it.** Free instances have no outbound SMTP: `smtp.gmail.com:587`
> fails with `[Errno 101] Network is unreachable`. Leave `EMAIL_HOST_USER`
> blank and Django falls back to the console backend, which prints the code
> into the service log — search the Render logs for `OTP` and read it from
> there. For real delivery you need either a paid instance (SMTP is allowed) or
> an HTTP email API; `BREVO_API_KEY` is already wired up for the latter and
> takes precedence over the SMTP settings when set.

> **Rotate your keys first.** The Groq key and Gmail App Password currently in
> `backend/.env` have been sitting on disk. `.env` is gitignored so they are not
> in your repo, but generate fresh ones before going public and paste those into
> Render instead.

---

## Step 1 — MongoDB Atlas (the database)

1. Sign up at https://www.mongodb.com/cloud/atlas/register
2. **Create a cluster** → choose **M0 Free** → pick a region near you
   (Mumbai `ap-south-1` if you are in India) → *Create Deployment*
3. **Database Access** → *Add New Database User*
   - Username: `ragchatbot`
   - Password: *Autogenerate* → **copy it now**, you cannot see it again
   - Role: *Read and write to any database*
4. **Network Access** → *Add IP Address* → **Allow Access from Anywhere**
   (`0.0.0.0/0`)

   Render's free instances have no fixed outbound IP, so a narrower rule would
   break every time the instance moves. The database user's password is what
   actually protects the data.
5. **Connect** → *Drivers* → *Python* → copy the connection string:

   ```
   mongodb+srv://ragchatbot:<db_password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

   Replace `<db_password>` with the password from step 3. Keep this — it is the
   `MONGODB_HOST` value in the next step.

---

## Step 2 — Render (the backend API)

1. Sign up at https://render.com with GitHub
2. **New +** → **Blueprint** → select your repository

   Render reads `render.yaml` from the repo root and configures the service.
   (Prefer clicking through instead? **New +** → **Web Service**, set
   *Root Directory* `backend`, *Build Command* `bash ./build.sh`, *Start Command*
   `gunicorn config.wsgi:application --workers 1 --threads 4 --timeout 180`.)
3. Render prompts for the secret environment variables. Fill them in:

   | Variable | Value |
   |---|---|
   | `MONGODB_HOST` | the Atlas string from Step 1 |
   | `GROQ_API_KEY` | your Groq key |
   | `EMAIL_HOST_USER` | **leave blank** — SMTP is blocked on the free tier, see the note above |
   | `EMAIL_HOST_PASSWORD` | leave blank |
   | `DEFAULT_ADMIN_EMAIL` | the admin account to create |
   | `DEFAULT_ADMIN_PASSWORD` | a strong password |
   | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` for now — fixed in Step 4 |

   `SECRET_KEY` is generated by Render. `DEBUG=False`, `EMBEDDING_BACKEND=onnx`
   and `EMBEDDING_ONNX_PROVIDER=cpu` are already set in `render.yaml`.
4. **Create** and watch the log. The first build takes **5–10 minutes** — it
   installs the ML packages and downloads the embedding model.
5. When it says *Live*, test it:

   ```
   https://<your-service>.onrender.com/api/health/
   ```

   You want:

   ```json
   {"status": "healthy", "mongodb": "connected", "service": "AI RAG Chatbot API"}
   ```

   `"mongodb": "unavailable"` means Step 1 is wrong — check the password in the
   connection string and that Network Access is `0.0.0.0/0`.

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

   These are baked in at build time, so **changing them later needs a redeploy**,
   not just a restart.
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
   - Ask a question → answer comes back with `(Page N)` citations
   - Sign in at `/admin-login` with your `DEFAULT_ADMIN_EMAIL`

---

## What the free tier costs you

These are real limits, not warnings to skim. Know them before your demo.

**The backend sleeps after 15 minutes of inactivity.** The next request has to
wake it, which takes **around 50 seconds**. Open the site a minute before you
present and it will be warm. (A cron ping every 10 minutes keeps it awake, but
that burns your monthly instance hours.)

**The disk is wiped on every deploy and restart.** This is the big one. Render's
free tier has no persistent storage, and three things live on disk:

| Lost on restart | Consequence |
|---|---|
| Uploaded PDFs (`media/`) | The original file is gone |
| FAISS indexes (`indexes/`) | Rebuilt automatically — see below |
| `db.sqlite3` — Django's user table | **Registered accounts are gone** |

MongoDB keeps every document record, chunk, and chat message, so the app does
not break. Users must register again; the admin account survives because
`build.sh` re-creates it on every deploy.

**The FAISS indexes repair themselves.** Losing them used to be the worst of
these: the document still appeared in the sidebar marked "completed", but with
no index there was nothing to retrieve, so *every* question came back "I could
not find an answer to your question in the uploaded document(s)" — a refusal
that looked like a broken model rather than a missing file. Each chunk's vector
is now stored in MongoDB next to its text, and `faiss_store.rebuild_index`
writes the index back from those vectors the first time a question touches a
document whose index is gone. It is a copy, not a recompute, so it costs a
second or so and the answer arrives normally.

Two things to know about it:
- Documents uploaded *before* this change have no stored vectors, so their
  first rebuild re-embeds the text instead. That is slow on a throttled free
  instance and a large document can exceed the 180s request timeout. Re-upload
  anything from before to move it onto the fast path.
- The original PDF is still gone, so downloading the source file will not work
  even though questions do.

For a viva demo this is usually fine: upload your PDF at the start of the
session and everything works. To make it permanent, either
- upgrade to Render **Starter ($7/mo)** and attach a **persistent disk**, mounted
  at a path you set as `VOLUME_PATH` (settings.py already reads it), or
- move Django's auth tables to a hosted Postgres (Neon and Supabase both have
  permanent free tiers) so at least accounts survive.

**512 MB RAM.** One gunicorn worker plus the embedding model fits, but not with
much headroom. Do not raise `--workers` above 1 on the free plan.

---

## If something breaks

**Build fails with `permission denied: ./build.sh`**
`render.yaml` already uses `bash ./build.sh` to avoid this. If you configured the
service by hand, set the build command to `bash ./build.sh` too — git on Windows
does not carry the executable bit.

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
`EMAIL_HOST_USER` is blank, so Django is using the console backend and printing
the code into the Render log instead of sending it. Set both email variables. It
must be a Gmail *App Password*, not your account password.

**First question after a deploy is very slow**
Expected. The instance is waking and loading the embedding model. Subsequent
questions are fast.

**Every answer is "I could not find an answer to your question in the uploaded
document(s)"**
The document is listed and marked completed, but its FAISS index was wiped by a
restart, so retrieval returns nothing and the pipeline refuses rather than
guessing. This now repairs itself — the index is rebuilt from the vectors kept
in MongoDB on the next question. If you still see it, check the Render log for
`Rebuilding lost FAISS index`:
- `no chunks in MongoDB` means processing never finished for that document —
  upload it again.
- A rebuild that starts but never logs `Rebuilt index` is the slow re-embedding
  path on a document uploaded before vectors were stored. Re-upload it.
- No rebuild line at all means the index is present and the documents genuinely
  do not contain the answer. Confirm with `RAG_DEBUG=true`, which returns the
  retrieved passages and their similarity scores with the answer.

---

## Deploying an update

Both platforms watch your GitHub repo and redeploy on push to `main`:

```bash
git add .
git commit -m "Your change"
git push
```

Render rebuilds the API (a few minutes); Vercel rebuilds the frontend (under a
minute). Remember that the Render disk is wiped by this — see above.
