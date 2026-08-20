"""The RAG pipeline — the heart of the project.

Answering one question runs five steps:

    1. embed the question                       services/embeddings
    2. search the vector store for similar text  services/faiss_store
    3. load those passages, keeping page numbers repositories
    4. ask the LLM to answer using ONLY that text  services/llm
    5. save the exchange                         repositories

If step 2 finds nothing relevant enough, the assistant refuses rather than
guessing. That refusal is what keeps the answers honest, and it is why the
similarity floor and the grounding prompt both exist.

Storage is reached through repositories now, so the pipeline works against
MongoDB or PostgreSQL without knowing which. Retrieval still goes through the
FAISS store; swapping that for pgvector is Phase 6, behind VECTOR_BACKEND.
"""
import logging
import time
from typing import Any, Optional

from django.conf import settings

from repositories.base import ChunkDTO
from repositories.factory import get_conversation_repository, get_document_repository

logger = logging.getLogger(__name__)

EXCERPT_LENGTH = 300


def retrieve_relevant_chunks(
    user_id: int,
    document_ids: list[str],
    query: str,
) -> list[ChunkDTO]:
    """Find the passages most similar to `query` in the given documents.

    Returns one dict per passage with its text, its page number and its
    similarity score, best first. An empty list means nothing was relevant
    enough — which the caller must treat as "refuse", not as "answer anyway".
    """
    from services.embeddings import embed_query
    from services.faiss_store import search_multiple_indexes

    repository = get_document_repository()

    # The index files are named by document, and a migrated document keeps its
    # original MongoDB id as that name. Ask the repository for the documents so
    # the right key is used either way.
    documents = repository.list_completed(user_id, document_ids)
    if not documents:
        logger.info('No completed documents to search for user %s', user_id)
        return []

    index_keys = [_index_key(d) for d in documents]

    matches = search_multiple_indexes(
        user_id=user_id,
        document_ids=index_keys,
        query_embedding=embed_query(query),
        top_k=settings.RAG_TOP_K,
    )
    if not matches:
        logger.warning('No vector results — check the documents finished processing.')
        return []

    # Drop weak matches. Without this floor an unrelated question still pulls
    # back the least-unrelated passage, and the model may answer from it.
    floor = settings.RAG_MIN_SIMILARITY_SCORE
    matches = [(chunk_id, score) for chunk_id, score in matches if score >= floor]
    if not matches:
        logger.info('Nothing met the %.2f relevance floor — question is out of scope.',
                    floor)
        return []

    # get_chunks preserves the order it is given, which is the ranking.
    ordered_ids = [chunk_id for chunk_id, _ in matches]
    scores = dict(matches)

    chunks = repository.get_chunks(ordered_ids, user_id)
    for chunk in chunks:
        chunk['similarity_score'] = scores.get(chunk['chunk_id'], 0.0)

    logger.info('Retrieved %d passage(s) for: %s', len(chunks), query[:60])
    return chunks


def _index_key(document: dict[str, Any]) -> str:
    """The name this document's vector index is stored under.

    Documents migrated out of MongoDB keep their original id as the index
    filename, because that is what the file on disk is already called.
    """
    return document.get('legacy_mongo_id') or document['id']


def build_citations(chunks: list[ChunkDTO]) -> list[dict[str, Any]]:
    """One citation per (document, page) — what the UI shows under Sources.

    Deduplicated because two chunks from the same page are one source to a
    reader, and a list repeating "page 4" three times looks like a bug.
    """
    citations = []
    seen = set()

    for chunk in chunks:
        key = (chunk['document_id'], chunk['page_number'])
        if key in seen:
            continue
        seen.add(key)

        excerpt = chunk['content']
        if len(excerpt) > EXCERPT_LENGTH:
            excerpt = excerpt[:EXCERPT_LENGTH] + '...'

        citations.append({
            'document_id': chunk['document_id'],
            'document_name': chunk['document_name'],
            'page_number': chunk['page_number'],
            'similarity_score': round(chunk.get('similarity_score', 0.0), 4),
            'excerpt': excerpt,
        })

    return citations


def answer_question(
    user_id: int,
    conversation_id: str,
    document_ids: list[str],
    question: str,
) -> dict[str, Any]:
    """Answer one question against a conversation's documents, and store it."""
    from services.llm import REFUSAL_MESSAGE, generate_rag_response

    conversations = get_conversation_repository()

    # --- Retrieve ---
    started = time.perf_counter()
    chunks = retrieve_relevant_chunks(user_id, document_ids, question)
    retrieval_ms = (time.perf_counter() - started) * 1000

    # --- Generate ---
    history = _trim_history(
        conversations.recent_history(
            conversation_id, user_id, settings.CONVERSATION_MEMORY_TURNS,
        )
    )

    started = time.perf_counter()
    error = ''
    if chunks:
        try:
            answer = generate_rag_response(question, chunks, history)
        except Exception as exc:
            # The turn is still recorded below. A failed answer that vanishes
            # leaves the user looking at a question with no reply and no way to
            # tell whether it was sent.
            logger.error('Answer generation failed: %s', exc, exc_info=True)
            raise
    else:
        answer = REFUSAL_MESSAGE          # nothing relevant — refuse, never invent
    generation_ms = (time.perf_counter() - started) * 1000

    logger.info('RAG: retrieval=%.0fms generation=%.0fms passages=%d',
                retrieval_ms, generation_ms, len(chunks))

    citations = build_citations(chunks)

    conversations.add_turn(
        conversation_id, user_id,
        question=question,
        answer=answer,
        sources=citations,
        provider=settings.LLM_PROVIDER,
        model_name=settings.GROQ_MODEL,
        retrieval_ms=round(retrieval_ms),
        generation_ms=round(generation_ms),
        total_ms=round(retrieval_ms + generation_ms),
        chunks_retrieved=len(chunks),
        error=error,
    )

    return {
        'answer': answer,
        'citations': citations,
        'chunks_retrieved': len(chunks),
        # Only surfaced by the API when RAG_DEBUG is on or ?debug=true.
        'debug': {
            'retrieval_ms': round(retrieval_ms, 1),
            'generation_ms': round(generation_ms, 1),
            'retrieved_chunks': [
                {
                    'document_name': c['document_name'],
                    'page_number': c['page_number'],
                    'similarity_score': round(c.get('similarity_score', 0.0), 4),
                    'preview': c['content'][:200],
                }
                for c in chunks
            ],
        },
    }


def _trim_history(history: list[dict[str, Any]],
                  max_chars: Optional[int] = None) -> list[dict[str, Any]]:
    """Keep the most recent turns within a character budget.

    Dropping whole turns rather than truncating a message: half a question
    followed by a full answer reads as a non-sequitur, and the model treats it
    as context it is supposed to make sense of.
    """
    budget = max_chars or 3000
    trimmed = list(history)

    while trimmed and sum(len(m['content']) for m in trimmed) > budget:
        trimmed = trimmed[2:]        # oldest user+assistant pair

    return trimmed


# Kept so the existing `manage.py test_rag` command and any other caller keep
# working while the views move over. Same behaviour, new name upstream.
def run_rag_query(user_id: int, session_id: str, document_ids: list[str],
                  question: str) -> dict[str, Any]:
    return answer_question(user_id, session_id, document_ids, question)
