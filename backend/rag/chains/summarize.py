"""Document summarisation.

A separate chain from question-answering, because it answers a different
question: not "what does this document say about X" but "what is this document".
It reads the first few pages rather than retrieved passages — there is nothing
to retrieve against yet, and the opening pages of a report are where its subject
is stated.

Called from ingestion, on its own Celery task. A document is chat-ready without
a summary, so a rate limit here must not fail the upload.
"""
import logging

logger = logging.getLogger(__name__)

PAGE_BREAK = '\n\n---PAGE BREAK---\n\n'
SUMMARY_SAMPLE_PAGES = 5
# The sample is capped as well as page-limited: five pages of a dense appendix
# can be longer than the context window, and the provider silently drops the
# end of an over-long prompt rather than reporting it.
SUMMARY_MAX_CHARS = 15000


def generate_document_summary(pages_content: list[dict]) -> str:
    """Summarise a document from its first few pages."""
    from rag.llm.base import Message
    from rag.prompts.grounding import SUMMARY_PROMPT
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
