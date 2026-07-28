"""
Module 10: RAG Pipeline
Orchestrates: query embedding → FAISS retrieval → context building → Groq LLM → citations.
"""
import logging
from typing import List, Dict, Any
from bson import ObjectId
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def retrieve_relevant_chunks(
    user_id: int,
    document_ids: List[str],
    query: str,
    top_k: int = None,
) -> List[Dict[str, Any]]:
    from core.mongo import chunks_col, documents_col
    from services.embeddings import embed_query
    from services.faiss_store import search_multiple_indexes

    top_k = top_k or settings.RAG_TOP_K

    # Embed the query
    query_embedding = embed_query(query)

    # Search across all document indexes
    raw_results = search_multiple_indexes(
        user_id=user_id,
        document_ids=document_ids,
        query_embedding=query_embedding,
        top_k=top_k,
    )

    logger.info("FAISS search: %d document(s), %d raw results for query: '%s'",
                len(document_ids), len(raw_results), query[:60])

    if not raw_results:
        logger.warning("No FAISS results at all. Check that document was fully processed.")
        return []

    # Log top scores so you can tune the threshold
    for cid, score in raw_results[:5]:
        logger.info("  chunk=%s  score=%.4f", cid, score)

    min_score = settings.RAG_MIN_SIMILARITY_SCORE
    filtered = [(cid, score) for cid, score in raw_results if score >= min_score]
    logger.info("Score filter (>= %.3f): %d/%d chunks kept", min_score, len(filtered), len(raw_results))

    if not filtered:
        top_score = raw_results[0][1] if raw_results else 0.0
        # Nothing is relevant enough. Do NOT force an answer from loosely-related
        # chunks — return no context so the assistant honestly says it couldn't
        # find the information in the uploaded documents (no hallucination).
        logger.info(
            "No chunk met the relevance threshold (best %.4f < %.3f). "
            "Question is out-of-scope for these documents.",
            top_score, min_score,
        )
        return []

    # Fetch chunk content from MongoDB
    chunk_ids = [ObjectId(cid) for cid, _ in filtered]
    score_map = {cid: score for cid, score in filtered}

    chunks_cursor = chunks_col().find({'_id': {'$in': chunk_ids}})
    chunks_by_id = {str(c['_id']): c for c in chunks_cursor}

    # Fetch document names
    doc_id_set = set()
    for chunk in chunks_by_id.values():
        doc_id_set.add(str(chunk.get('document_id', '')))

    docs_cursor = documents_col().find(
        {'_id': {'$in': [ObjectId(d) for d in doc_id_set if d]}},
        {'original_filename': 1}
    )
    doc_names = {str(d['_id']): d.get('original_filename', 'Unknown') for d in docs_cursor}

    # Build enriched result list ordered by score
    enriched = []
    for chunk_id, score in filtered:
        chunk = chunks_by_id.get(chunk_id)
        if not chunk:
            continue
        doc_name = doc_names.get(str(chunk.get('document_id', '')), 'Unknown')
        enriched.append({
            'chunk_id':       chunk_id,
            'document_id':    str(chunk.get('document_id', '')),
            'document_name':  doc_name,
            'page_number':    chunk.get('page_number', 1),
            'content':        chunk.get('content', ''),
            'similarity_score': score,
        })

    logger.info("Returning %d enriched chunks to the LLM", len(enriched))
    return enriched


def run_rag_query(
    user_id: int,
    session_id: str,
    document_ids: List[str],
    question: str,
) -> Dict[str, Any]:
    import time
    from core.mongo import messages_col, chat_sessions_col
    from core.constants import ROLE_USER, ROLE_ASSISTANT
    from services.llm import generate_rag_response, REFUSAL_MESSAGE
    from services.memory import get_conversation_history, summarize_history_if_long

    # 1. Retrieve context (timed)
    t0 = time.perf_counter()
    context_chunks = retrieve_relevant_chunks(user_id, document_ids, question)
    retrieval_ms = (time.perf_counter() - t0) * 1000

    # 2. Load conversation memory
    history = get_conversation_history(session_id)
    history = summarize_history_if_long(history)

    # 3. Generate response (timed)
    t1 = time.perf_counter()
    if context_chunks:
        answer = generate_rag_response(question, context_chunks, history)
    else:
        # No qualifying context — refuse honestly instead of hallucinating.
        answer = REFUSAL_MESSAGE
    generation_ms = (time.perf_counter() - t1) * 1000

    logger.info(
        "RAG timing: retrieval=%.0fms generation=%.0fms chunks=%d question='%s'",
        retrieval_ms, generation_ms, len(context_chunks), question[:60],
    )

    # 4. Build citations
    seen = set()
    citations = []
    for chunk in context_chunks:
        key = (chunk['document_id'], chunk['page_number'])
        if key not in seen:
            seen.add(key)
            excerpt = chunk['content']
            citations.append({
                'document_id':    chunk['document_id'],
                'document_name':  chunk['document_name'],
                'page_number':    chunk['page_number'],
                'similarity_score': round(chunk['similarity_score'], 4),
                'excerpt': excerpt[:200] + '...' if len(excerpt) > 200 else excerpt,
            })

    now = timezone.now()

    # 5. Persist user message
    messages_col().insert_one({
        'session_id': session_id,
        'user_id':    user_id,
        'role':       ROLE_USER,
        'content':    question,
        'sources':    [],
        'created_at': now,
    })

    # 6. Persist assistant message
    messages_col().insert_one({
        'session_id': session_id,
        'user_id':    user_id,
        'role':       ROLE_ASSISTANT,
        'content':    answer,
        'sources':    citations,
        'created_at': now,
    })

    # 7. Update session
    chat_sessions_col().update_one(
        {'_id': ObjectId(session_id)},
        {'$inc': {'message_count': 2}, '$set': {'last_message_at': now, 'updated_at': now}},
    )

    # Debug payload — surfaced by the API only when debug mode is on.
    debug = {
        'retrieval_ms':  round(retrieval_ms, 1),
        'generation_ms': round(generation_ms, 1),
        'retrieved_chunks': [
            {
                'document_name':    c['document_name'],
                'page_number':      c['page_number'],
                'similarity_score': round(c['similarity_score'], 4),
                'preview':          c['content'][:200] + ('...' if len(c['content']) > 200 else ''),
            }
            for c in context_chunks
        ],
    }

    return {
        'answer':           answer,
        'citations':        citations,
        'chunks_retrieved': len(context_chunks),
        'debug':            debug,
    }
