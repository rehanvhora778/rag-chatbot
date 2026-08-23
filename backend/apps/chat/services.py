"""Conversation lifecycle and the send-a-message flow.

The view used to do session lookup, validation, retrieval, generation, storage
and analytics in one method. Those are separable concerns with different
failure modes, and only one of them is about HTTP.

This is the seam between the application and the RAG engine. Everything above
it deals in conversations, users and permissions; everything below — in
``rag/`` — deals in questions, passages and vectors and has never heard of
either. ``answer_question`` is where the two meet: it resolves a conversation
to the documents it may search, runs the chain, and records the exchange.
"""
import logging
from typing import Any, Optional

from django.conf import settings

from core.analytics import record_event
from core.constants import EVENT_EXPORT, EVENT_FEEDBACK, EVENT_QUERY, SESSION_ARCHIVED
from repositories.factory import get_conversation_repository, get_document_repository

logger = logging.getLogger(__name__)


class ChatError(Exception):
    """An invalid request, with a message meant for a user."""


class ConversationNotFound(ChatError):
    """The conversation does not exist, or does not belong to this user.

    Deliberately one exception for both cases: distinguishing them would confirm
    that a given id exists, which is precisely what a probing request wants.
    """


# ══════════════════════════════════════════════════════════════════
# Conversations
# ══════════════════════════════════════════════════════════════════

def list_conversations(user_id: int, page: int = 1, page_size: int = 20):
    return get_conversation_repository().list_for_user(
        user_id, page=page, page_size=page_size,
    )


def get_transcript(user_id: int, conversation_id: str) -> dict[str, Any]:
    repository = get_conversation_repository()
    conversation = repository.get(conversation_id, user_id)
    if conversation is None:
        raise ConversationNotFound('Session not found.')
    return {
        'session': conversation,
        'messages': repository.list_messages(conversation_id, user_id),
    }


def _resolve_documents(user_id: int, document_ids: list[str]) -> tuple[list[str], list[str]]:
    """Turn a client-supplied id list into documents that are safe to ground in.

    Everything the client sends is a claim: that these ids exist, that they
    belong to this user, and that they finished processing. All three are
    re-established here from the database. The repository checks ownership again
    when it writes — that redundancy is deliberate.
    """
    documents = get_document_repository().list_completed(user_id, document_ids)
    if not documents:
        raise ChatError(
            'None of those documents are available. They must be your own and '
            'finished processing.'
        )

    by_id = {d['id']: d['original_filename'] for d in documents}
    # The user's ordering is preserved; anything that failed validation is gone.
    ordered = [d for d in document_ids if d in by_id]
    return ordered, [by_id[d] for d in ordered]


def create_conversation(user_id: int, title: str,
                        document_ids: list[str]) -> dict[str, Any]:
    ids, names = _resolve_documents(user_id, document_ids)
    return get_conversation_repository().create(user_id, title, ids, names)


def update_conversation(user_id: int, conversation_id: str,
                        **changes: Any) -> dict[str, Any]:
    repository = get_conversation_repository()
    if repository.get(conversation_id, user_id) is None:
        raise ConversationNotFound('Session not found.')

    if 'document_ids' in changes:
        ids, names = _resolve_documents(user_id, changes['document_ids'])
        changes['document_ids'] = ids
        changes['document_names'] = names

    updated = repository.update(conversation_id, user_id, **changes)
    if updated is None:
        raise ConversationNotFound('Session not found.')
    return updated


def delete_conversation(user_id: int, conversation_id: str) -> None:
    if not get_conversation_repository().delete(conversation_id, user_id):
        raise ConversationNotFound('Session not found.')


def search_conversations(user_id: int, query: str, page: int = 1, page_size: int = 20):
    query = (query or '').strip()
    if not query:
        raise ChatError('Search query is required.')
    return get_conversation_repository().search(
        user_id, query, page=page, page_size=page_size,
    )


# ══════════════════════════════════════════════════════════════════
# Asking a question
# ══════════════════════════════════════════════════════════════════

def send_message(user_id: int, conversation_id: str, question: str,
                 debug: bool = False) -> dict[str, Any]:
    """Answer one question in a conversation and record the exchange."""
    repository = get_conversation_repository()

    conversation = repository.get(conversation_id, user_id)
    if conversation is None:
        raise ConversationNotFound('Session not found.')

    if conversation.get('status') == SESSION_ARCHIVED:
        raise ChatError('Cannot send messages to an archived session.')

    document_ids = conversation.get('document_ids') or []
    if not document_ids:
        # Reachable when every document a conversation was grounded in has since
        # been deleted. Answering anyway would mean answering from the model's
        # own knowledge, which is the one thing this system must not do.
        raise ChatError(
            'This conversation has no documents left to search. Attach a '
            'document to it and try again.'
        )

    result = answer_question(
        user_id=user_id,
        conversation_id=conversation_id,
        document_ids=document_ids,
        question=question,
    )

    record_event(user_id, EVENT_QUERY, {
        'session_id': conversation_id,
        'question_length': len(question),
        'chunks_retrieved': result['chunks_retrieved'],
    })

    response = {
        'answer': result['answer'],
        'citations': result['citations'],
        'session_id': conversation_id,
    }
    if debug or settings.RAG_DEBUG:
        response['debug'] = result.get('debug', {})
    return response


# ══════════════════════════════════════════════════════════════════
# Running one question through the RAG chain
# ══════════════════════════════════════════════════════════════════

def answer_question(user_id: int, conversation_id: str, document_ids: list[str],
                    question: str) -> dict[str, Any]:
    """Answer one question in a conversation, and record the exchange."""
    from apps.documents.services import resolve_index_keys
    from rag.chains import rag_chain

    conversations = get_conversation_repository()

    history = trim_history(
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


def trim_history(history: list[dict[str, Any]],
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


# ══════════════════════════════════════════════════════════════════
# Export
# ══════════════════════════════════════════════════════════════════

def export_conversation_pdf(user_id: int, conversation_id: str) -> tuple[bytes, str]:
    """Render a conversation to a PDF. Returns the bytes and a filename."""
    from apps.chat.export import build_export_filename, export_chat_to_pdf

    repository = get_conversation_repository()
    conversation = repository.get(conversation_id, user_id)
    if conversation is None:
        raise ConversationNotFound('Session not found.')

    messages = repository.list_messages(conversation_id, user_id)
    title = conversation.get('title', 'Document')

    pdf_bytes = export_chat_to_pdf(session_title=title, messages=messages)
    record_event(user_id, EVENT_EXPORT, {'session_id': conversation_id})

    return pdf_bytes, build_export_filename(title, messages)


def get_engine_config() -> dict[str, Any]:
    """What the RAG engine is running. Read-only, for the Settings page."""
    return {
        'model': settings.GROQ_MODEL,
        'embedding_model': settings.EMBEDDING_MODEL_NAME,
        'retrieval': {
            'top_k': settings.RAG_TOP_K,
            'chunk_size': settings.RAG_CHUNK_SIZE,
            'chunk_overlap': settings.RAG_CHUNK_OVERLAP,
            'fetch_k': settings.RAG_FETCH_K,
            'use_mmr': settings.RAG_USE_MMR,
            'min_similarity': settings.RAG_MIN_SIMILARITY_SCORE,
            'memory_turns': settings.CONVERSATION_MEMORY_TURNS,
            'hybrid_enabled': settings.RAG_HYBRID_ENABLED,
            'rerank_enabled': settings.RAG_RERANK_ENABLED,
        },
    }


# ══════════════════════════════════════════════════════════════════
# Feedback
# ══════════════════════════════════════════════════════════════════

VALID_RATINGS = (-1, 1)
NEGATIVE_REASONS = ('incorrect', 'irrelevant', 'missing', 'hallucination', 'other')
MAX_COMMENT_CHARS = 2000


def submit_feedback(user_id: int, message_id: str, rating: int,
                    reason: str = '', comment: str = '') -> dict[str, Any]:
    """Record a thumbs up or down on one answer."""
    if rating not in VALID_RATINGS:
        raise ChatError('Rating must be 1 (helpful) or -1 (not helpful).')

    reason = (reason or '').strip().lower()
    if reason and reason not in NEGATIVE_REASONS:
        raise ChatError(f'Unknown reason. One of: {", ".join(NEGATIVE_REASONS)}.')

    # A reason on a positive rating is meaningless — every option describes a
    # way the answer was wrong — and would pollute the queue of things to fix.
    if rating == 1:
        reason = ''

    record = get_conversation_repository().save_feedback(
        message_id, user_id,
        rating=rating,
        reason=reason,
        comment=(comment or '').strip()[:MAX_COMMENT_CHARS],
    )
    if record is None:
        raise ConversationNotFound('Message not found.')

    record_event(user_id, EVENT_FEEDBACK, {
        'message_id': message_id, 'rating': rating, 'reason': reason,
    })
    return record


def get_feedback(user_id: int, message_id: str) -> Optional[dict[str, Any]]:
    return get_conversation_repository().get_feedback(message_id, user_id)


def stream_message(user_id: int, conversation_id: str, question: str):
    """Validate a streaming request and return the SSE generator.

    Validation happens here, before any bytes are sent: once a streamed
    response has started, the status code is already committed and a 404 can no
    longer be returned.
    """
    from apps.chat.streaming import chat_event_stream

    conversation = get_conversation_repository().get(conversation_id, user_id)
    if conversation is None:
        raise ConversationNotFound('Session not found.')

    if conversation.get('status') == SESSION_ARCHIVED:
        raise ChatError('Cannot send messages to an archived session.')

    document_ids = conversation.get('document_ids') or []
    if not document_ids:
        raise ChatError(
            'This conversation has no documents left to search. Attach a '
            'document to it and try again.'
        )

    return chat_event_stream(user_id, conversation_id, question, document_ids)
