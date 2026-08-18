# AI RAG Chatbot

A full-stack Retrieval-Augmented Generation chatbot: upload your documents
(PDF / DOCX / TXT), then chat with an AI that answers **grounded in those files** —
every fact carries the page it came from, e.g. *(Page 12)*.

Scanned PDFs have no selectable text, so those pages are rendered to an image and read
by Groq's vision model (OCR) before being indexed like any other page.

**How a question is answered**

```
question -> embed -> FAISS search -> top passages (with page numbers)
         -> Groq (gpt-oss-120b) -> answer + page citations
```

**Stack:** Django REST Framework · MongoDB · FAISS (vector search) ·
ONNX Runtime embeddings (all-MiniLM-L6-v2) · Groq (openai/gpt-oss-120b) ·
React + Vite + Tailwind

> Groq retires models without notice — `llama-3.3-70b-versatile`, used here
> originally, now returns `404 model_not_found`, and no Llama chat model remains
> on Groq. `GROQ_MODEL` is therefore worth checking against
> [Groq's model list](https://console.groq.com/docs/models) if answers start
> failing. The `openai/` prefix names who published the weights; inference still
> runs entirely on Groq.

## Project structure

```
.
├── backend/            Django API (Python)
│   ├── apps/           authentication, documents, chat, analytics, admin_panel
│   ├── config/         settings, urls, wsgi/asgi
│   ├── core/           Mongo client, shared utils, responses, permissions
│   ├── services/       RAG pipeline, embeddings, FAISS store, chunker, LLM,
│   │                   text extractor, PDF export
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env            secrets — not committed (create manually)
│   ├── db.sqlite3      Django auth/JWT only (project data lives in MongoDB)
│   ├── media/          uploaded files        (auto-created, gitignored)
│   └── indexes/        per-user FAISS indexes (auto-created, gitignored)
├── frontend/           React + Vite single-page app
└── venv/               Python virtual environment (gitignored)
```

## Prerequisites

- Python 3.11, Node.js 18+
- **MongoDB** running on `localhost:27017`
- A `GROQ_API_KEY` in `backend/.env`

## Run (Windows)

Make sure MongoDB is running, then open **two terminals**.

**Backend** — terminal 1:
```
cd backend
python manage.py runserver
```
Django starts on http://localhost:8000

**Frontend** — terminal 2:
```
cd frontend
npm run dev
```
Vite starts on http://localhost:3000 — open it in your browser.

**Backend says `No module named 'django'`?** Your virtual-env isn't active. You don't
need to activate it (or change PowerShell's execution policy) — just run the server
with the venv's Python directly:
```
cd backend
..\venv\Scripts\python manage.py runserver
```

## First-time setup

Run these once from the project root:
```
python -m venv venv
venv\Scripts\python -m pip install -r backend\requirements.txt
```
Create `backend\.env` and add your key:
```
GROQ_API_KEY=your-key-here
```
Set up the database, create the administrator, then install the frontend packages:
```
cd backend
..\venv\Scripts\python manage.py migrate
..\venv\Scripts\python manage.py create_admin
cd ..\frontend
npm install
```

## Signing in

Accounts are identified by **email address** — there is no username to remember.

| Page | Route | Who it's for |
|---|---|---|
| Register | `/register` | New users — name, email, password |
| User login | `/login` | Everyone |
| Admin login | `/admin-login` | Staff only; the endpoint rejects normal accounts |

`manage.py create_admin` seeds the administrator from `DEFAULT_ADMIN_EMAIL` /
`DEFAULT_ADMIN_PASSWORD` in `backend\.env` (defaults: `rehanvhora86@gmail.com` /
`rehan@786`). Re-run it any time to reset that password. From **Admin Console →
Users** an admin can promote or demote other admins, deactivate accounts, and
delete users along with their data.

### Google (Gmail) sign-in — optional

The "Continue with Google" buttons stay inert until you add an OAuth client id.
Create an **OAuth 2.0 Client ID → Web application** at
https://console.cloud.google.com/apis/credentials, list `http://localhost:3000`
under *Authorised JavaScript origins*, then put the id in `backend\.env`:
```
GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
```
The frontend picks it up from the backend automatically (or set
`VITE_GOOGLE_CLIENT_ID` in `frontend\.env` to override). Signing in with Google
creates the account on first use; the ID token is verified server-side against
Google's public keys.
