"""LLM-as-judge scoring for faithfulness and answer correctness.

Two things a lexical overlap metric genuinely cannot do: recognise that a
correct answer paraphrased the source, and notice that an answer built entirely
from words present in the context still says something the context does not.
A model reading both can do each.

The costs are real and stated rather than hidden. Every judged case is an extra
API call. The verdict varies between runs even at temperature 0. And the judge
is a Groq model that may be retired, at which point historical judged scores
stop being comparable with new ones. That is why ``evaluate_rag`` defaults to
the deterministic metrics and treats judging as opt-in: the numbers a project
quotes should be the ones that can be reproduced.

The rubric is deliberately narrow. A judge asked "is this a good answer?" scores
its own taste; asked "is every claim supported by this text, yes or no", it does
something closer to a measurement.
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 8000

FAITHFULNESS_PROMPT = """You are grading whether an ANSWER is supported by the CONTEXT it was given.

Judge ONLY support, not correctness, style, or completeness. An answer may be
factually true about the world and still unsupported here.

Score 0.0 to 1.0:
  1.0  every claim in the answer is stated in or directly follows from the context
  0.5  the main claim is supported but some detail is not present in the context
  0.0  the answer asserts something the context does not contain

If the answer declines to answer or says the information could not be found,
score 1.0 — declining is fully supported behaviour.

CONTEXT:
{context}

ANSWER:
{answer}

Reply with JSON only, no other text:
{{"score": <number>, "reason": "<one short sentence>"}}"""

CORRECTNESS_PROMPT = """You are grading whether an ANSWER matches a REFERENCE answer.

Grade meaning, not wording. A different phrasing that conveys the same facts is
fully correct. Extra accurate detail is not penalised; a missing fact from the
reference is.

Score 0.0 to 1.0:
  1.0  conveys everything the reference does
  0.5  partially correct, or correct but missing a fact the reference states
  0.0  contradicts the reference, or answers a different question

QUESTION:
{question}

REFERENCE ANSWER:
{reference}

ANSWER TO GRADE:
{answer}

Reply with JSON only, no other text:
{{"score": <number>, "reason": "<one short sentence>"}}"""


@dataclass
class Verdict:
    score: Optional[float]
    reason: str = ''

    @property
    def available(self) -> bool:
        return self.score is not None


_JSON_BLOCK = re.compile(r'\{.*\}', re.DOTALL)


def _parse(reply: str) -> Verdict:
    """Pull a score out of the judge's reply.

    Models wrap JSON in prose or fences however firmly they are asked not to,
    so the first {...} block is extracted rather than parsing the whole reply.
    An unparseable verdict returns None — the case is then excluded from the
    judged average, which is honest, rather than defaulting to 0.0 and
    reporting a failure the pipeline did not have.
    """
    if not reply:
        return Verdict(None, 'empty reply from judge')

    match = _JSON_BLOCK.search(reply)
    if not match:
        return Verdict(None, 'judge did not return JSON')

    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return Verdict(None, 'judge returned malformed JSON')

    raw = payload.get('score')
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return Verdict(None, 'judge returned a non-numeric score')

    return Verdict(max(0.0, min(1.0, score)), str(payload.get('reason', ''))[:200])


def _ask(prompt: str) -> Verdict:
    from rag.llm.base import Message
    from rag.registry import get_llm

    try:
        reply = get_llm().complete([Message(role='user', content=prompt)]).text
    except Exception as exc:
        # One judge failure must not abandon the run: the remaining cases still
        # produce usable deterministic metrics.
        logger.warning('Judge call failed: %s', exc)
        return Verdict(None, f'judge unavailable: {exc}')
    return _parse(reply)


def _format_context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for chunk in chunks:
        header = f"[{chunk.get('document_name', 'source')} — Page {chunk.get('page_number', '?')}]"
        parts.append(f"{header}\n{chunk.get('content', '')}")
    context = '\n\n---\n\n'.join(parts)

    if len(context) > MAX_CONTEXT_CHARS:
        # Truncation is marked, so a low faithfulness score on a long case can
        # be recognised as possibly an artefact of what the judge was shown.
        context = context[:MAX_CONTEXT_CHARS] + '\n\n[context truncated for judging]'
    return context


def judge_faithfulness(answer: str, chunks: list[dict[str, Any]]) -> Verdict:
    if not chunks:
        return Verdict(None, 'nothing was retrieved, so there is nothing to be faithful to')
    return _ask(FAITHFULNESS_PROMPT.format(
        context=_format_context(chunks), answer=answer,
    ))


def judge_correctness(question: str, answer: str, reference: str) -> Verdict:
    if not (reference or '').strip():
        return Verdict(None, 'no reference answer for this case')
    return _ask(CORRECTNESS_PROMPT.format(
        question=question, reference=reference, answer=answer,
    ))
