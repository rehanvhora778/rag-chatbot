"""Query rewriting for conversation-aware retrieval.

This fixes a failure that is invisible in the transcript and obvious once you
look at what retrieval actually received.

    User:      What is the refund policy?
    Assistant: Domestic orders can be returned within 30 days. (Page 2)
    User:      What about international purchases?

The second question is passed to retrieval exactly as typed. Embedded on its
own, "What about international purchases?" is a question about *purchases* — the
words "refund", "return" and "policy" appear nowhere in it, so the vector lands
somewhere between shipping and payment, and the passage the user is plainly
asking about may not be retrieved at all. The model then answers from whatever
did come back, and the answer looks like a reasoning failure when it was a
retrieval one.

The generation step already receives the history, which is why this is easy to
miss: the model has the context, the retriever does not.

Rewriting resolves the reference before retrieval sees it:

    "What are the refund terms for international purchases?"

**Cost, stated plainly.** This is an extra LLM call on every follow-up, adding
roughly half a second to a question that already takes several. It is therefore
off by default, skipped entirely on the first turn of a conversation, and
skipped when the question is already self-contained.
"""
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """Rewrite the FOLLOW-UP QUESTION so it can be understood on its own, without the conversation.

Rules:
- Replace pronouns and references ("it", "that", "those", "what about X") with what they actually refer to.
- Keep the user's intent and specificity exactly. Do not answer, expand, or add detail that was not implied.
- If the question already stands alone, return it unchanged.
- Reply with the rewritten question only. No preamble, no quotes, no explanation.

CONVERSATION:
{history}

FOLLOW-UP QUESTION:
{question}

REWRITTEN QUESTION:"""

# A question with none of these, and of reasonable length, is almost certainly
# self-contained — so the rewrite call is skipped and its latency with it.
DEPENDENT_MARKERS = re.compile(
    r'\b(it|its|that|this|those|these|they|them|their|he|she|his|her|'
    r'the same|above|previous|earlier|instead|also|too|as well)\b',
    re.IGNORECASE,
)
SHORT_QUESTION_WORDS = 8
MAX_REWRITE_LENGTH = 400


def needs_rewrite(question: str, history: list[dict]) -> bool:
    """Is this question likely to depend on what came before?

    A cheap heuristic in front of an expensive call. It is deliberately
    generous about saying yes: a needless rewrite costs half a second, while a
    missed one costs the user a wrong answer they have no way to diagnose.
    """
    if not history:
        return False

    text = (question or '').strip()
    if not text:
        return False

    # Short questions are the classic follow-up shape — "and internationally?",
    # "why?", "what about refunds?" — regardless of which words they use.
    if len(text.split()) <= SHORT_QUESTION_WORDS:
        return True

    return bool(DEPENDENT_MARKERS.search(text))


def rewrite_query(question: str, history: list[dict],
                  max_turns: int = 3) -> tuple[str, bool]:
    """Resolve a follow-up into a standalone question.

    Returns (question, was_rewritten). Never raises: a rewrite failure must
    leave retrieval working with the original question rather than failing the
    turn, because the original is at worst what the pipeline did before this
    existed.
    """
    if not settings.RAG_QUERY_REWRITE:
        return question, False

    if not needs_rewrite(question, history):
        return question, False

    from rag.llm.base import Message
    from rag.registry import get_llm

    # Only the last few turns. The reference being resolved is nearly always in
    # the immediately preceding exchange, and a longer history costs tokens
    # while giving the model more chances to drag in an unrelated topic.
    recent = history[-(max_turns * 2):]
    rendered = '\n'.join(
        f'{"User" if m.get("role") == "user" else "Assistant"}: {m.get("content", "")}'
        for m in recent
    )

    try:
        response = get_llm().complete(
            [Message(role='user', content=REWRITE_PROMPT.format(
                history=rendered, question=question,
            ))],
            # Deterministic: this is a transformation with a right answer, not
            # a generation task, and a creative rewrite is a wrong one.
            temperature=0.0,
            max_tokens=120,
        )
    except Exception as exc:
        logger.warning('Query rewrite failed, using the original question: %s', exc)
        return question, False

    rewritten = _clean(response.text)

    if not _is_plausible(rewritten, question):
        logger.info('Discarding an implausible rewrite: %r', rewritten[:80])
        return question, False

    if rewritten.lower() == question.strip().lower():
        return question, False

    logger.info('Rewrote %r -> %r', question[:60], rewritten[:60])
    return rewritten, True


def _clean(text: str) -> str:
    """Strip the wrapping models add however firmly they are told not to."""
    cleaned = (text or '').strip()

    # A leading label: "Rewritten question: ..."
    cleaned = re.sub(r'^(rewritten\s+question|question)\s*:\s*', '', cleaned,
                     flags=re.IGNORECASE)
    # Surrounding quotes.
    if len(cleaned) >= 2 and cleaned[0] in '"“\'' and cleaned[-1] in '"”\'':
        cleaned = cleaned[1:-1].strip()
    # Only the first line — a model that explains itself does so underneath.
    cleaned = cleaned.split('\n')[0].strip()

    return cleaned


def _is_plausible(rewritten: str, original: str) -> bool:
    """Reject a rewrite that has clearly gone wrong.

    The failure this guards against is the model answering the question instead
    of rewriting it. That answer would then be embedded and used as the search
    query, retrieving passages similar to the model's own guess rather than to
    what the user asked — which is a self-fulfilling retrieval and exactly the
    ungrounded behaviour the whole system is built to prevent.
    """
    if not rewritten:
        return False
    if len(rewritten) > MAX_REWRITE_LENGTH:
        return False
    # A rewrite far longer than the original is an answer, not a question.
    if len(rewritten) > max(len(original) * 4, 200):
        return False
    return True


def expand_query(question: str) -> list[str]:
    """Alternative phrasings to search alongside the original.

    Not implemented, and listed here so the absence is a decision rather than
    an oversight. Multi-query expansion means one LLM call plus one retrieval
    per variant; with reranking already narrowing a wide candidate pool, the
    measured gain did not justify tripling retrieval latency on a free-tier
    provider that is already the slowest part of a turn.
    """
    return [question]


def preprocess(question: str) -> str:
    """Normalise a question before it is embedded.

    Collapsing whitespace only. Deliberately not lowercasing or stripping
    punctuation: the embedding model was trained on natural text, and "What is
    Section 8.2?" and "what is section 82" are not the same query to it — the
    second has lost the very identifier that made the question specific.
    """
    return ' '.join((question or '').split())
