"""Backwards-compatible shim over the LLM provider layer.

The implementation moved to ``rag/llm/`` behind a provider interface. These
names stay because they are imported in several places — the summary path, the
OCR fallback in text_extractor, the evaluation metrics that match the refusal
sentence — and changing all of them at once would have made the provider
refactor a much larger diff for no benefit.

New code should use ``rag.registry.get_llm()`` and
``rag.prompts.grounding.REFUSAL_MESSAGE`` directly.
"""
import logging
from typing import Optional

from rag.prompts.grounding import REFUSAL_MESSAGE, SUMMARY_PROMPT  # noqa: F401
from rag.prompts.grounding import SYSTEM_PROMPT as RAG_SYSTEM_PROMPT  # noqa: F401

logger = logging.getLogger(__name__)

PAGE_BREAK = '\n\n---PAGE BREAK---\n\n'
SUMMARY_SAMPLE_PAGES = 5
SUMMARY_MAX_CHARS = 15000


def _call_with_retry(messages: list[dict], max_retries: int = 3) -> str:
    """Send raw chat messages to the configured provider.

    Used by the evaluation judge and anything else that builds its own message
    list rather than going through the grounding prompt. Retries live in the
    provider now, so ``max_retries`` is accepted and ignored — kept only so the
    existing call sites do not have to change.
    """
    from rag.llm.base import Message
    from rag.registry import get_llm

    payload = [Message(role=m['role'], content=m['content']) for m in messages]
    return get_llm().complete(payload).text


def generate_rag_response(question: str, context_chunks: list[dict],
                          conversation_history: Optional[list[dict]] = None) -> str:
    """Answer a question from retrieved passages. Returns the answer text."""
    from rag.chains.rag_chain import build_messages
    from rag.registry import get_llm
    from rag.types import chunks_to_documents

    messages = build_messages(
        question, chunks_to_documents(context_chunks), conversation_history or [],
    )
    return get_llm().complete(messages).text


def generate_document_summary(pages_content: list[dict]) -> str:
    """Summarise a document from its first few pages."""
    from rag.llm.base import Message
    from rag.registry import get_llm

    sample = pages_content[:SUMMARY_SAMPLE_PAGES]
    combined = PAGE_BREAK.join(
        f"Page {p['page_number']}:\n{p['content']}" for p in sample
    )
    if len(combined) > SUMMARY_MAX_CHARS:
        combined = combined[:SUMMARY_MAX_CHARS] + '\n... [truncated]'

    rendered = SUMMARY_PROMPT.format_messages(content=combined)
    return get_llm().complete(
        [Message(role='user', content=rendered[0].content)]
    ).text


def read_image(image_b64: str, prompt: str, mime_type: str = 'image/png',
               max_tokens: int = 600) -> str:
    """OCR a rendered page image. Needs a provider with vision support."""
    from rag.registry import get_llm

    provider = get_llm()
    if not hasattr(provider, 'read_image'):
        raise NotImplementedError(
            f'The {provider.name} provider cannot read images, so scanned pages '
            "cannot be OCR'd. Use LLM_PROVIDER=groq for that."
        )
    return provider.read_image(image_b64, prompt, mime_type, max_tokens)


def get_groq_client():
    """Deprecated: reach the provider through rag.registry.get_llm()."""
    from rag.registry import get_llm

    return get_llm()._get_client()
