"""
Module 10: RAG Pipeline — the heart of the project.

Answering one question runs five steps:
    1. embed the question            (services/embeddings)
    2. search FAISS for similar text (services/faiss_store)
    3. load those chunks from MongoDB, keeping each one's page number
    4. ask Groq to answer using ONLY that text  (services/llm)
    5. save the question, the answer and its page citations to MongoDB

If step 2 finds nothing relevant enough, the assistant refuses instead of
guessing — that refusal is what keeps the answers honest.
"""
import logging
import time
from datetime import timedelta
from typing import List, Dict, Any

from bson import ObjectId
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def retrieve_relevant_chunks(
    user_id: int,
    document_ids: List[str],
    query: str,
) -> List[Dict[str, Any]]:
    """Find the passages most similar to `query` in the given documents.

    Returns one dict per passage with its text, its page number and its
    similarity score. An empty list means nothing was relevant enough.
    """
    from core.mongo import chunks_col, documents_col
    from services.embeddings import embed_query
    from services.faiss_store import search_multiple_indexes

    # 1. Question -> vector, then vector -> nearest chunk ids.
    matches = search_multiple_indexes(
        user_id=user_id,
        document_ids=document_ids,
        query_embedding=embed_query(query),
        top_k=settings.RAG_TOP_K,
    )
    if not matches:
        logger.warning("No FAISS results — check the documents finished processing.")
        return []

    # 2. Drop weak matches. Without this floor an unrelated question would still
    #    pull back the "least unrelated" chunk and the model might answer from it.
    min_score = settings.RAG_MIN_SIMILARITY_SCORE
    matches = [(cid, score) for cid, score in matches if score >= min_score]
    if not matches:
        logger.info("Nothing met the %.2f relevance floor — question is out of scope.", min_score)
        return []

    # 3. Load the chunk text and the file names they belong to.
    chunks = {
        str(c['_id']): c
        for c in chunks_col().find({'_id': {'$in': [ObjectId(cid) for cid, _ in matches]}})
    }
    doc_ids = {c.get('document_id') for c in chunks.values() if c.get('document_id')}
    names = {
        str(d['_id']): d.get('original_filename', 'Unknown')
        for d in documents_col().find(
            {'_id': {'$in': [ObjectId(d) for d in doc_ids]}}, {'original_filename': 1}
        )
    }

    # 4. Rebuild in score order — best passage first, page number attached.
    results = []
    for chunk_id, score in matches:
        chunk = chunks.get(chunk_id)
        if not chunk:
            continue
        results.append({
            'chunk_id':         chunk_id,
            'document_id':      str(chunk.get('document_id', '')),
            'document_name':    names.get(str(chunk.get('document_id', '')), 'Unknown'),
            'page_number':      chunk.get('page_number', 1),
            'content':          chunk.get('content', ''),
            'similarity_score': score,
        })

    logger.info("Retrieved %d passage(s) for: %s", len(results), query[:60])
    return results


def _build_citations(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One citation per (document, page) — this is what the UI shows as Sources."""
    citations = []
    seen = set()
    for chunk in chunks:
        key = (chunk['document_id'], chunk['page_number'])
        if key in seen:
            continue
        seen.add(key)
        excerpt = chunk['content']
        citations.append({
            'document_id':      chunk['document_id'],
            'document_name':    chunk['document_name'],
            'page_number':      chunk['page_number'],
            'similarity_score': round(chunk['similarity_score'], 4),
            'excerpt':          excerpt[:300] + '...' if len(excerpt) > 300 else excerpt,
        })
    return citations


def run_rag_query(
    user_id: int,
    session_id: str,
    document_ids: List[str],
    question: str,
) -> Dict[str, Any]:
    """Answer one question against a session's documents and save the exchange."""
    from core.mongo import messages_col, chat_sessions_col
    from core.constants import ROLE_USER, ROLE_ASSISTANT
    from services.llm import generate_rag_response, REFUSAL_MESSAGE
    from services.memory import get_conversation_history, summarize_history_if_long

    # --- Retrieve ---
    started = time.perf_counter()
    chunks = retrieve_relevant_chunks(user_id, document_ids, question)
    retrieval_ms = (time.perf_counter() - started) * 1000

    # --- Generate (with the last few turns for follow-up questions) ---
    history = summarize_history_if_long(get_conversation_history(session_id))

    started = time.perf_counter()
    if chunks:
        answer = generate_rag_response(question, chunks, history)
    else:
        answer = REFUSAL_MESSAGE       # nothing relevant — refuse, never invent
    generation_ms = (time.perf_counter() - started) * 1000

    logger.info("RAG: retrieval=%.0fms generation=%.0fms passages=%d",
                retrieval_ms, generation_ms, len(chunks))

    citations = _build_citations(chunks)
    now = timezone.now()

    # --- Save both messages so the conversation survives a refresh ---
    # The history is read back sorted by created_at, so the answer is stamped a
    # millisecond after the question to keep the pair in order.
    messages_col().insert_many([
        {'session_id': session_id, 'user_id': user_id, 'role': ROLE_USER,
         'content': question, 'sources': [], 'created_at': now},
        {'session_id': session_id, 'user_id': user_id, 'role': ROLE_ASSISTANT,
         'content': answer, 'sources': citations,
         'created_at': now + timedelta(milliseconds=1)},
    ])

    # The question doubles as the sidebar preview, so a session can be
    # recognised without loading its messages.
    preview = question if len(question) <= 90 else question[:87] + '...'
    chat_sessions_col().update_one(
        {'_id': ObjectId(session_id)},
        {'$inc': {'message_count': 2},
         '$set': {'last_message_at': now, 'updated_at': now,
                  'last_message_preview': preview}},
    )

    return {
        'answer':           answer,
        'citations':        citations,
        'chunks_retrieved': len(chunks),
        # Only surfaced by the API when RAG_DEBUG is on.
        'debug': {
            'retrieval_ms':  round(retrieval_ms, 1),
            'generation_ms': round(generation_ms, 1),
            'retrieved_chunks': [
                {'document_name':    c['document_name'],
                 'page_number':      c['page_number'],
                 'similarity_score': round(c['similarity_score'], 4),
                 'preview':          c['content'][:200]}
                for c in chunks
            ],
        },
    }
