"""RAG orchestration for the chat service.

The pipeline itself now lives in ``rag/`` — retrieval, prompting and generation
are there, behind provider and vector-store interfaces. What remains here is
the part that is specific to *this application* rather than to RAG: resolving a
conversation's documents to the keys its vector index is stored under, and
recording the exchange.

Keeping that split means the RAG package has no idea what a conversation is,
and the chat service has no idea what a vector store is.

The public names below are unchanged, so the chat service, the evaluation
harness and `manage.py test_rag` all keep working.
"""
import logging
from typing import Any, Optional

from django.conf import settings

from repositories.factory import get_conversation_repository, get_document_repository

logger = logging.getLogger(__name__)


def resolve_index_keys(user_id: int, document_ids: list[str]) -> list[str]:
    """Conversation document ids -> the keys their vectors are stored under.

    A document migrated out of MongoDB keeps its old id as the name of its
    FAISS index file, so retrieval has to ask for that rather than the new
    UUID. Documents that never finished processing are dropped: searching them
    finds nothing, and including them would make a partial corpus look like a
    retrieval failure.
    """
    documents = get_document_repository().list_completed(user_id, document_ids)
    if not documents:
        logger.info('No completed documents to search for user %s', user_id)
        return []
    return [d.get('legacy_mongo_id') or d['id'] for d in documents]


def retrieve_relevant_chunks(user_id: int, document_ids: list[str],
                             query: str) -> list[dict[str, Any]]:
    """Passages most relevant to `query`, best first.

    Kept as a function returning dicts because the evaluation harness and the
    `test_rag` command both call it directly and score what comes back.
    """
    from rag.retrievers.vector import VectorRetriever
    from rag.types import documents_to_chunks

    index_keys = resolve_index_keys(user_id, document_ids)
    if not index_keys:
        return []

    documents = VectorRetriever(user_id=user_id, document_keys=index_keys).invoke(query)
    logger.info('Retrieved %d passage(s) for: %s', len(documents), query[:60])
    return documents_to_chunks(documents)


def build_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One citation per (document, page). Kept for callers that hold dicts."""
    from rag.chains.rag_chain import build_citations as _build
    from rag.types import chunks_to_documents

    return _build(chunks_to_documents(chunks))


def answer_question(user_id: int, conversation_id: str, document_ids: list[str],
                    question: str) -> dict[str, Any]:
    """Answer one question in a conversation, and record the exchange."""
    from rag.chains import rag_chain

    conversations = get_conversation_repository()

    history = _trim_history(
        conversations.recent_history(
            conversation_id, user_id, settings.CONVERSATION_MEMORY_TURNS,
        )
    )

    result = rag_chain.run(
        user_id=user_id,
        question=question,
        document_keys=resolve_index_keys(user_id, document_ids),
        history=history,
    )

    conversations.add_turn(
        conversation_id, user_id,
        question=question,
        answer=result.answer,
        sources=result.citations,
        provider=result.provider,
        model_name=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        retrieval_ms=result.retrieval_ms,
        generation_ms=result.generation_ms,
        total_ms=result.total_ms,
        chunks_retrieved=len(result.documents),
    )

    return {
        'answer': result.answer,
        'citations': result.citations,
        'chunks_retrieved': len(result.documents),
        'debug': {
            'retrieval_ms': result.retrieval_ms,
            'generation_ms': result.generation_ms,
            'provider': result.provider,
            'model': result.model,
            'total_tokens': result.total_tokens,
            'truncated': result.truncated,
            'retrieved_chunks': [
                {
                    'document_name': c['document_name'],
                    'page_number': c['page_number'],
                    'similarity_score': round(c['similarity_score'], 4),
                    'preview': c['content'][:200],
                }
                for c in result.chunks
            ],
        },
    }


def _trim_history(history: list[dict[str, Any]],
                  max_chars: Optional[int] = None) -> list[dict[str, Any]]:
    """Keep the most recent turns within a character budget.

    Whole turns are dropped rather than a message being truncated: half a
    question followed by a full answer reads as a non-sequitur, and the model
    treats it as context it is supposed to make sense of.
    """
    budget = max_chars or 3000
    trimmed = list(history)

    while trimmed and sum(len(m['content']) for m in trimmed) > budget:
        trimmed = trimmed[2:]        # oldest user + assistant pair

    return trimmed


