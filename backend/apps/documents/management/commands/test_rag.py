"""
Smoke-test the RAG pipeline against an uploaded document set.

Runs a list of questions through retrieval + generation (without persisting any
chat messages) and prints, for each: how many chunks were retrieved, the top
similarity score, whether the answer was a refusal, and a short preview.

A control question ("What is the capital of France?") is expected to be refused;
the command reports PASS/FAIL for that check.

Usage:
    python manage.py test_rag --session <session_id>
    python manage.py test_rag --user 5 --document <doc_id> [--document <doc_id> ...]
    python manage.py test_rag --session <id> -q "What are embeddings?" -q "What is FAISS?"
"""
from bson import ObjectId
from django.core.management.base import BaseCommand, CommandError

from apps.documents.services import retrieve_relevant_chunks
from core.mongo import chat_sessions_col
from rag.chains.rag_chain import generate_from_chunks
from rag.prompts.grounding import REFUSAL_MESSAGE

DEFAULT_QUESTIONS = [
    "What are embeddings?",
    "What is FAISS?",
    "Explain RAG.",
    "What is Machine Learning?",
    "What is Python?",
]
CONTROL_QUESTION = "What is the capital of France?"


def _is_refusal(answer: str) -> bool:
    head = (answer or "").strip().lower()[:60]
    return head.startswith("i could not find an answer")


class Command(BaseCommand):
    help = "Run sample questions through the RAG pipeline and report retrieval quality."

    def add_arguments(self, parser):
        parser.add_argument('--session', type=str, default=None,
                            help='Chat session id (provides user + document ids).')
        parser.add_argument('--user', type=int, default=None, help='User id.')
        parser.add_argument('--document', action='append', default=[],
                            help='Document id (repeatable). Use with --user.')
        parser.add_argument('-q', '--question', action='append', default=[],
                            help='Custom question (repeatable). Overrides the defaults.')

    def handle(self, *args, **opts):
        user_id, document_ids = self._resolve_target(opts)
        questions = opts['question'] or DEFAULT_QUESTIONS

        self.stdout.write(f"User: {user_id}  |  Documents: {document_ids}\n")
        self.stdout.write("=" * 70)

        for q in questions:
            self._run_one(user_id, document_ids, q, expect_refusal=False)

        # Control: an out-of-document question must be refused.
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.HTTP_INFO("CONTROL (must be refused):"))
        self._run_one(user_id, document_ids, CONTROL_QUESTION, expect_refusal=True)

    def _resolve_target(self, opts):
        if opts['session']:
            try:
                session = chat_sessions_col().find_one({'_id': ObjectId(opts['session'])})
            except Exception as exc:
                raise CommandError(f"Invalid session id: {opts['session']}") from exc
            if not session:
                raise CommandError("Session not found.")
            return session['user_id'], session.get('document_ids', [])

        if opts['user'] is not None and opts['document']:
            return opts['user'], opts['document']

        raise CommandError("Provide either --session, or --user together with one or more --document.")

    def _run_one(self, user_id, document_ids, question, expect_refusal):
        chunks = retrieve_relevant_chunks(user_id, document_ids, question)
        top = max((c['similarity_score'] for c in chunks), default=0.0)

        if chunks:
            answer = generate_from_chunks(question, chunks, [])
        else:
            answer = REFUSAL_MESSAGE

        refused = _is_refusal(answer)
        preview = " ".join(answer.split())[:120]

        self.stdout.write(f"\nQ: {question}")
        self.stdout.write(f"   chunks={len(chunks)}  top_score={top:.4f}  refused={refused}")

        if expect_refusal:
            tag = self.style.SUCCESS("PASS") if refused else self.style.ERROR("FAIL")
            self.stdout.write(f"   [{tag}] expected a refusal")
        else:
            tag = self.style.WARNING("NO MATCH") if refused else self.style.SUCCESS("ANSWERED")
            self.stdout.write(f"   [{tag}]")
        self.stdout.write(f"   A: {preview}{'...' if len(answer) > 120 else ''}")
