"""The retrieval-augmented generation chain.

Retrieve, build a grounded prompt, generate, return the answer with the
citations that support it.

The steps are separate functions rather than one LCEL pipeline expression. LCEL
composes beautifully when every step is a pure transformation; here the steps
need to report their own latency, the generation step has to be skippable
entirely when retrieval finds nothing, and each stage's intermediate output is
surfaced in the debug payload and the evaluation harness. Wrapping that in
``|`` operators would hide the control flow that is the interesting part of this
code — so the LangChain pieces used are the ones that earn their place
(Document, the prompt template, BaseRetriever) and the orchestration stays
explicit.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from django.conf import settings
from langchain_core.documents import Document

from rag.prompts.grounding import REFUSAL_MESSAGE, build_rag_prompt, format_history
from rag.types import documents_to_chunks, truncate_to_budget

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    answer: str
    documents: list[Document] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    refused: bool = False
    retrieval_ms: int = 0
    generation_ms: int = 0
    provider: str = ''
    model: str = ''
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    truncated: bool = False
    # What retrieval actually did, as opposed to what settings asked for.
    # Recorded because a component that silently did not run is the failure
    # mode an evaluation cannot detect on its own.
    trace: dict[str, Any] = field(default_factory=dict)
    rewritten_query: str = ''
    # Injection-shaped content noticed in the passages that were used. Never a
    # reason to block an answer; recorded so attempts are visible.
    security_findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_ms(self) -> int:
        return self.retrieval_ms + self.generation_ms

    @property
    def chunks(self) -> list[dict[str, Any]]:
        """The retrieved passages in the dict shape the rest of the app uses."""
        return documents_to_chunks(self.documents)


EXCERPT_LENGTH = 300


def build_citations(documents: list[Document]) -> list[dict[str, Any]]:
    """One citation per (document, page).

    Deduplicated because two passages from the same page are one source to a
    reader, and a Sources list repeating "Page 4" three times looks like a bug
    in the product rather than a consequence of chunk overlap.
    """
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for document in documents:
        meta = document.metadata or {}
        key = (meta.get('document_id', ''), int(meta.get('page_number', 0)))
        if key in seen:
            continue
        seen.add(key)

        excerpt = document.page_content
        if len(excerpt) > EXCERPT_LENGTH:
            excerpt = excerpt[:EXCERPT_LENGTH] + '...'

        citations.append({
            'document_id': meta.get('document_id', ''),
            'document_name': meta.get('document_name', 'Unknown'),
            'page_number': meta.get('page_number', 1),
            'similarity_score': round(float(meta.get('score', 0.0)), 4),
            'excerpt': excerpt,
        })

    return citations


def build_messages(question: str, documents: list[Document],
                   history: Optional[list[dict]] = None) -> tuple[list, Any]:
    """Render the grounded prompt for one question.

    Returns the messages and the HardenedContext they were built from, so the
    caller can report what was noticed in the retrieved passages.

    The context is trimmed to a character budget first. Without a ceiling, six
    passages from a document with long pages can exceed the model's context
    window, and the failure is not an error — the provider silently drops the
    end of the prompt, which is where the question is.
    """
    from rag.llm.base import Message
    from rag.security.injection import harden_context

    budgeted = truncate_to_budget(documents, settings.RAG_MAX_CONTEXT_CHARS)
    if len(budgeted) < len(documents):
        logger.info('Context budget dropped %d of %d passage(s)',
                    len(documents) - len(budgeted), len(documents))

    # Retrieved text is untrusted input that happens to live in the user's own
    # files. It is wrapped in delimiters carrying a nonce the document could not
    # have predicted, and the system prompt is told that everything between them
    # is quoted data. The content itself is never altered — an answer cites a
    # page so a human can check it, and rewriting what the model read would make
    # that citation point at something else.
    hardened = harden_context(budgeted)

    prompt = build_rag_prompt(nonce=hardened.nonce).format_messages(
        context=hardened.text,
        history=format_history(history or []),
        question=question,
    )
    # LangChain message objects -> the provider-neutral shape.
    messages = [Message(role=_role_of(m), content=m.content) for m in prompt]

    # Returned, not stashed on the module. Module-level state would be shared
    # by every thread in a gunicorn worker and every task in a Celery process,
    # so two concurrent questions would report each other's findings — the kind
    # of bug that only appears under load and cannot be reproduced on demand.
    return messages, hardened


def _role_of(message) -> str:
    mapping = {'system': 'system', 'human': 'user', 'ai': 'assistant'}
    return mapping.get(getattr(message, 'type', 'human'), 'user')


def run(user_id: int, question: str, document_keys: list[str],
        history: Optional[list[dict]] = None,
        filters: Optional[dict[str, Any]] = None) -> RAGResult:
    """Answer one question against a set of documents."""
    from rag.query.rewrite import preprocess, rewrite_query
    from rag.registry import get_llm
    from rag.retrievers.hybrid import build_retriever

    started = time.perf_counter()

    # --- Preprocess and (optionally) rewrite ---
    # A follow-up like "what about international purchases?" retrieves nothing
    # useful on its own; the reference is resolved against the history before
    # the retriever ever sees it. Off by default — see rag/query/rewrite.py.
    search_query, rewritten = rewrite_query(preprocess(question), history or [])

    # --- Retrieve ---
    retriever = build_retriever(user_id, document_keys, filters)
    documents = retriever.invoke(search_query)
    retrieval_ms = round((time.perf_counter() - started) * 1000)
    trace = dict(getattr(retriever, 'trace', {}) or {})
    trace['retriever'] = type(retriever).__name__

    if not documents:
        # Nothing relevant. Refuse rather than letting the model answer from
        # its own knowledge — this is the behaviour the whole system exists to
        # guarantee, and it costs no LLM call.
        logger.info('Nothing retrieved for %r — refusing.', question[:60])
        return RAGResult(
            answer=REFUSAL_MESSAGE,
            refused=True,
            retrieval_ms=retrieval_ms,
            provider=settings.LLM_PROVIDER,
            trace=trace,
            rewritten_query=search_query if rewritten else '',
        )

    # --- Generate ---
    # The ORIGINAL question goes to the model, not the rewrite. The rewrite
    # exists to steer retrieval; showing it to the model would have the
    # assistant answering a question the user did not ask, and any imprecision
    # the rewrite introduced would become the answer's subject.
    llm = get_llm()
    messages, hardened = build_messages(question, documents, history)
    findings = [f.as_dict() for f in hardened.findings]

    started = time.perf_counter()
    response = llm.complete(messages)
    generation_ms = round((time.perf_counter() - started) * 1000)

    logger.info('RAG: retrieval=%dms generation=%dms passages=%d',
                retrieval_ms, generation_ms, len(documents))

    return RAGResult(
        answer=response.text,
        documents=documents,
        citations=build_citations(documents),
        refused=response.text.strip().startswith(REFUSAL_MESSAGE[:60]),
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        provider=response.provider,
        model=response.model,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        total_tokens=response.usage.total_tokens,
        truncated=response.truncated,
        trace=trace,
        rewritten_query=search_query if rewritten else '',
        security_findings=findings,
    )


def stream(user_id: int, question: str, document_keys: list[str],
           history: Optional[list[dict]] = None,
           filters: Optional[dict[str, Any]] = None) -> Iterator[dict[str, Any]]:
    """Answer one question, yielding the response as it is produced.

    Yields event dicts rather than bare strings so the caller receives the
    citations before the first token. That ordering is what lets the UI show
    Sources while the answer is still being written, instead of having the
    layout jump when they arrive at the end.

    Used by the streaming chat endpoint in Phase 8.
    """
    from rag.query.rewrite import preprocess, rewrite_query
    from rag.registry import get_llm
    from rag.retrievers.hybrid import build_retriever

    started = time.perf_counter()
    search_query, _rewritten = rewrite_query(preprocess(question), history or [])
    retriever = build_retriever(user_id, document_keys, filters)
    documents = retriever.invoke(search_query)
    retrieval_ms = round((time.perf_counter() - started) * 1000)

    citations = build_citations(documents)
    yield {'type': 'sources', 'citations': citations, 'retrieval_ms': retrieval_ms}

    if not documents:
        yield {'type': 'token', 'text': REFUSAL_MESSAGE}
        yield {'type': 'done', 'refused': True, 'retrieval_ms': retrieval_ms,
               'generation_ms': 0}
        return

    llm = get_llm()
    messages, hardened = build_messages(question, documents, history)
    if hardened.suspicious:
        yield {'type': 'security',
               'findings': [f.as_dict() for f in hardened.findings]}

    started = time.perf_counter()
    pieces: list[str] = []
    try:
        for piece in llm.stream(messages):
            pieces.append(piece)
            yield {'type': 'token', 'text': piece}
    except Exception as exc:
        logger.error('Streaming failed: %s', exc, exc_info=True)
        yield {'type': 'error', 'message': str(exc)}
        return

    answer = ''.join(pieces)
    yield {
        'type': 'done',
        'answer': answer,
        'refused': answer.strip().startswith(REFUSAL_MESSAGE[:60]),
        'retrieval_ms': retrieval_ms,
        'generation_ms': round((time.perf_counter() - started) * 1000),
        'provider': llm.name,
        'model': llm.model,
    }
