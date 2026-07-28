# AI RAG Chatbot

A full-stack Retrieval-Augmented Generation chatbot: upload documents (PDF / DOCX / TXT),
then chat with an AI that answers **grounded in your files** with inline citations.

**Stack:** Django REST Framework · MongoDB · FAISS (vector search) ·
Sentence-Transformers embeddings · Groq (Llama 3.3 70B) · React + Vite + Tailwind

## Project structure

```
.
├── backend/            Django API (Python)
│   ├── apps/           authentication, documents, chat, analytics, admin_panel
│   ├── config/         settings, urls, wsgi/asgi
│   ├── core/           Mongo client, shared utils, responses, permissions
│   ├── services/       RAG pipeline, embeddings, FAISS store, chunker, LLM, extractor
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
Set up the database, then install the frontend packages:
```
cd backend
..\venv\Scripts\python manage.py migrate
..\venv\Scripts\python manage.py createsuperuser
cd ..\frontend
npm install
```
