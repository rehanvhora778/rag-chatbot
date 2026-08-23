"""Executes an evaluation dataset against the live RAG pipeline.

The pipeline is exercised through the same functions the chat endpoint uses —
``retrieve_relevant_chunks`` then ``generate_rag_response`` — rather than a
reimplementation, because an evaluation that runs a copy of the pipeline
measures the copy. It stops short of persisting anything to a conversation:
a run must not fill somebody's chat history with three dozen test questions.

Every run stores a snapshot of the settings actually in force. Retrieval
settings are editable, and a score is meaningless without knowing what produced
it — "recall 0.91" is a fact about a configuration, not about the project.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

from apps.evaluation import metrics
from apps.evaluation.models import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    RAGConfiguration,
    RunStatus,
)
from repositories.factory import get_document_repository

logger = logging.getLogger(__name__)


class EvaluationError(Exception):
    """The run cannot proceed — usually a corpus that is not loaded."""


@dataclass
class CaseOutcome:
    case: EvaluationCase
    answer: str = ''
    chunks: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, Any] = field(default_factory=dict)
    retrieval_ms: int = 0
    generation_ms: int = 0
    refused: bool = False
    passed: bool = False
    error: str = ''


# ══════════════════════════════════════════════════════════════════
# Corpus
# ══════════════════════════════════════════════════════════════════

def resolve_corpus(dataset: EvaluationDataset, user_id: int) -> list[str]:
    """Find the document ids this dataset's questions are meant to be asked of.

    Datasets name documents rather than referencing them by id so they survive
    export and reload on another machine. Resolution therefore happens here, and
    fails loudly: a dataset silently evaluated against a corpus missing half its
    documents would report a retrieval collapse that is really a setup mistake.
    """
    repository = get_document_repository()
    owned = repository.list_for_user(user_id, page=1, page_size=500)['items']
    completed = {d['original_filename']: d for d in owned if d.get('status') == 'completed'}

    required = dataset.required_document_names or []
    if not required:
        # No requirement declared: use everything this user has finished
        # processing, which is what a first exploratory run wants.
        if not completed:
            raise EvaluationError(
                f'User {user_id} has no completed documents to evaluate against.'
            )
        return [d['id'] for d in completed.values()]

    missing = [name for name in required if name not in completed]
    if missing:
        raise EvaluationError(
            'These documents are required by the dataset but are not uploaded '
            f'and completed for user {user_id}:\n  - ' + '\n  - '.join(missing)
            + '\n\nUpload them, wait for processing to finish, then re-run.'
        )
    return [completed[name]['id'] for name in required]


def settings_snapshot() -> dict[str, Any]:
    """The configuration a run happened under, frozen into the record."""
    return {
        'persistence_backend': settings.PERSISTENCE_BACKEND,
        'vector_backend': settings.VECTOR_BACKEND,
        'embedding_model': settings.EMBEDDING_MODEL_NAME,
        'embedding_backend': settings.EMBEDDING_BACKEND,
        'llm_provider': settings.LLM_PROVIDER,
        'llm_model': settings.GROQ_MODEL,
        'temperature': settings.GROQ_TEMPERATURE,
        'chunk_size': settings.RAG_CHUNK_SIZE,
        'chunk_overlap': settings.RAG_CHUNK_OVERLAP,
        'top_k': settings.RAG_TOP_K,
        'fetch_k': settings.RAG_FETCH_K,
        'use_mmr': settings.RAG_USE_MMR,
        'mmr_lambda': settings.RAG_MMR_LAMBDA,
        'min_similarity': settings.RAG_MIN_SIMILARITY_SCORE,
        'hybrid_enabled': settings.RAG_HYBRID_ENABLED,
        'rerank_enabled': settings.RAG_RERANK_ENABLED,
        'rerank_model': settings.RAG_RERANK_MODEL,
        'keyword_top_k': settings.RAG_KEYWORD_TOP_K,
        'rrf_k': settings.RAG_RRF_K,
        'query_rewrite': settings.RAG_QUERY_REWRITE,
    }


# ══════════════════════════════════════════════════════════════════
# One case
# ══════════════════════════════════════════════════════════════════

def evaluate_case(case: EvaluationCase, user_id: int, document_ids: list[str],
                  judge: bool = False) -> CaseOutcome:
    from rag.chains.rag_chain import generate_from_chunks
    from rag.prompts.grounding import REFUSAL_MESSAGE

    outcome = CaseOutcome(case=case)

    # --- Retrieve ---
    started = time.perf_counter()
    try:
        outcome.chunks, outcome.trace = _retrieve_with_trace(
            user_id, document_ids, case.question,
        )
    except Exception as exc:
        logger.error('Retrieval failed for case %s: %s', case.pk, exc, exc_info=True)
        outcome.error = f'retrieval failed: {exc}'
        return outcome
    outcome.retrieval_ms = round((time.perf_counter() - started) * 1000)

    # --- Generate ---
    started = time.perf_counter()
    if outcome.chunks:
        try:
            # No conversation history: each case is scored on its own question,
            # so that a run's numbers do not depend on the order cases happen
            # to be stored in.
            outcome.answer = generate_from_chunks(case.question, outcome.chunks, [])
        except Exception as exc:
            # The generation failed, but retrieval did not, and what came back
            # is still measurable. Discarding it would mean a provider rate
            # limit — the normal failure of a free tier, and one that hits
            # several cases of a long run — silently erases the retrieval
            # numbers for those cases, leaving an average computed over
            # whichever handful got through. That is a far more misleading
            # result than a run that reports both the scores and the failures.
            logger.error('Generation failed for case %s: %s', case.pk, exc)
            outcome.error = f'generation failed: {exc}'
            outcome.generation_ms = round((time.perf_counter() - started) * 1000)
            outcome.scores = _score(case, outcome, judge=False)
            outcome.scores['generation_failed'] = True
            # Never passes: an unanswered question is not a success, whatever
            # retrieval managed.
            outcome.passed = False
            return outcome
    else:
        outcome.answer = REFUSAL_MESSAGE
    outcome.generation_ms = round((time.perf_counter() - started) * 1000)

    outcome.refused = metrics.is_refusal(outcome.answer)
    outcome.scores = _score(case, outcome, judge=judge)
    outcome.passed = _passed(case, outcome)
    return outcome


def _retrieve_with_trace(user_id: int, document_ids: list[str],
                         question: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Retrieve, and report which retrieval components actually ran.

    Settings say what was asked for; this says what happened. A run labelled
    "with reranking" whose reranker could not load would otherwise score
    identically to the baseline and be read as evidence that reranking does not
    help.
    """
    from apps.documents.services import resolve_index_keys
    from rag.retrievers.hybrid import build_retriever
    from rag.types import documents_to_chunks

    keys = resolve_index_keys(user_id, document_ids)
    if not keys:
        return [], {}

    retriever = build_retriever(user_id, keys)
    documents = retriever.invoke(question)
    trace = dict(getattr(retriever, 'trace', {}) or {})
    trace['retriever'] = type(retriever).__name__
    return documents_to_chunks(documents), trace


def _score(case: EvaluationCase, outcome: CaseOutcome, judge: bool) -> dict[str, Any]:
    chunks = outcome.chunks
    expected_docs = case.expected_document_names or []
    expected_pages = [int(p) for p in (case.expected_pages or [])]

    scores: dict[str, Any] = {
        'chunks_retrieved': len(chunks),
        'refused': outcome.refused,
    }

    if case.must_refuse:
        # A control case has no correct passage to find, so retrieval metrics do
        # not apply. What is being measured is whether the pipeline declines —
        # and a pipeline that answers these is answering from the model's own
        # knowledge, which is the failure this system exists to prevent.
        scores['refusal_correct'] = 1.0 if outcome.refused else 0.0
        scores['faithfulness_lexical'] = metrics.faithfulness_lexical(outcome.answer, chunks)
        return scores

    scores['refusal_correct'] = 0.0 if outcome.refused else 1.0
    scores['retrieval_recall'] = metrics.retrieval_recall(chunks, expected_docs, expected_pages)
    scores['retrieval_precision'] = metrics.retrieval_precision(chunks, expected_docs, expected_pages)
    scores['reciprocal_rank'] = metrics.reciprocal_rank(chunks, expected_docs, expected_pages)
    scores['context_relevance'] = metrics.context_relevance(chunks, case.question)
    scores['faithfulness_lexical'] = metrics.faithfulness_lexical(outcome.answer, chunks)
    scores['citation_validity'] = metrics.citation_validity(outcome.answer, chunks)
    scores['answer_correctness_lexical'] = (
        metrics.token_f1(outcome.answer, case.expected_answer)
        if case.expected_answer else None
    )

    if judge:
        from apps.evaluation import judge as llm_judge

        faithful = llm_judge.judge_faithfulness(outcome.answer, chunks)
        scores['faithfulness'] = faithful.score
        if faithful.reason:
            scores['faithfulness_reason'] = faithful.reason

        correct = llm_judge.judge_correctness(
            case.question, outcome.answer, case.expected_answer,
        )
        scores['answer_correctness'] = correct.score
        if correct.reason:
            scores['answer_correctness_reason'] = correct.reason

    return scores


def _passed(case: EvaluationCase, outcome: CaseOutcome) -> bool:
    """A single pass/fail verdict per case, for the headline count.

    Kept strict and simple. For a control case, passing means refusing. For a
    normal case it means not refusing, retrieving at least one expected page,
    and — where the answer cited pages — citing only pages that were actually
    retrieved. Everything subtler is in the individual scores.
    """
    if outcome.error:
        return False

    if case.must_refuse:
        return outcome.refused

    if outcome.refused:
        return False

    recall = outcome.scores.get('retrieval_recall')
    if recall is not None and recall <= 0:
        return False

    citation = outcome.scores.get('citation_validity')
    if citation is not None and citation < 1.0:
        return False

    return True


# ══════════════════════════════════════════════════════════════════
# A whole run
# ══════════════════════════════════════════════════════════════════

def corpus_size(user_id: int, document_ids: list[str]) -> int:
    """Total chunks the retriever has to choose between."""
    documents = get_document_repository().list_completed(user_id, document_ids)
    return sum(d.get('chunk_count') or 0 for d in documents)


def run_evaluation(dataset: EvaluationDataset, user_id: int, *,
                   label: str = '', judge: bool = False,
                   configuration: Optional[RAGConfiguration] = None,
                   limit: Optional[int] = None,
                   progress=None) -> EvaluationRun:
    document_ids = resolve_corpus(dataset, user_id)
    available_chunks = corpus_size(user_id, document_ids)

    cases = list(dataset.cases.all())
    if limit:
        cases = cases[:limit]
    if not cases:
        raise EvaluationError(f'Dataset "{dataset.name}" has no cases.')

    run = EvaluationRun.objects.create(
        dataset=dataset,
        configuration=configuration or RAGConfiguration.objects.filter(is_active=True).first(),
        run_by_id=user_id,
        label=label,
        status=RunStatus.RUNNING,
        started_at=timezone.now(),
        settings_snapshot={**settings_snapshot(),
                           'corpus_chunks': available_chunks,
                           'corpus_documents': len(document_ids)},
    )

    outcomes: list[CaseOutcome] = []
    try:
        for index, case in enumerate(cases, start=1):
            if progress:
                progress(index, len(cases), case)
            outcome = evaluate_case(case, user_id, document_ids, judge=judge)
            outcomes.append(outcome)
            _store(run, outcome)

        run.metrics = aggregate(outcomes, available_chunks)
        run.status = RunStatus.COMPLETED
    except Exception as exc:
        logger.error('Evaluation run %s failed: %s', run.pk, exc, exc_info=True)
        run.status = RunStatus.FAILED
        run.error_message = str(exc)
        # Whatever completed before the failure is still recorded and still
        # aggregated — a run that dies on case 30 of 40 should not throw away
        # the 29 measurements it already made.
        if outcomes:
            run.metrics = aggregate(outcomes, available_chunks)
        raise
    finally:
        run.finished_at = timezone.now()
        run.save()

    return run


def _store(run: EvaluationRun, outcome: CaseOutcome) -> None:
    EvaluationResult.objects.create(
        run=run,
        case=outcome.case,
        answer=outcome.answer,
        refused=outcome.refused,
        retrieved=[
            {
                'document_name': c.get('document_name'),
                'page_number': c.get('page_number'),
                'similarity_score': round(c.get('similarity_score', 0.0), 4),
                'preview': c.get('content', '')[:160],
            }
            for c in outcome.chunks
        ],
        scores={**outcome.scores, 'trace': outcome.trace},
        retrieval_ms=outcome.retrieval_ms,
        generation_ms=outcome.generation_ms,
        total_ms=outcome.retrieval_ms + outcome.generation_ms,
        passed=outcome.passed,
        error=outcome.error,
    )


def aggregate(outcomes: list[CaseOutcome],
              available_chunks: int = 0) -> dict[str, Any]:
    """Roll per-case scores into the run's headline numbers."""
    answerable = [o for o in outcomes if not o.case.must_refuse]
    controls = [o for o in outcomes if o.case.must_refuse]

    def collect(key: str, source: list[CaseOutcome]) -> Optional[float]:
        return metrics.mean(o.scores.get(key) for o in source)

    # Retrieval metrics are averaged over every case that retrieved something,
    # including ones whose generation failed. Answer metrics are averaged only
    # over cases that produced an answer: an answer that never arrived is not a
    # bad answer, and scoring it as one would blame the pipeline for the
    # provider being busy.
    answered = [o for o in outcomes if not o.error]
    answered_answerable = [o for o in answered if not o.case.must_refuse]
    latencies = [float(o.retrieval_ms + o.generation_ms) for o in answered]

    summary: dict[str, Any] = {
        'cases_total': len(outcomes),
        'cases_answerable': len(answerable),
        'cases_control': len(controls),
        'cases_passed': sum(1 for o in outcomes if o.passed),
        'cases_errored': sum(1 for o in outcomes if o.error),
        'pass_rate': (sum(1 for o in outcomes if o.passed) / len(outcomes)) if outcomes else None,

        'retrieval_recall': collect('retrieval_recall', answerable),
        'retrieval_precision': collect('retrieval_precision', answerable),
        'mrr': collect('reciprocal_rank', answerable),
        'context_relevance': collect('context_relevance', answerable),
        'faithfulness_lexical': collect('faithfulness_lexical', answered),
        'citation_validity': collect('citation_validity', answered_answerable),
        'answer_correctness_lexical': collect('answer_correctness_lexical', answered_answerable),

        # Reported separately: refusing a control is a different skill from
        # answering an answerable question, and one average hides which of the
        # two a pipeline is bad at.
        'refusal_accuracy_control': collect('refusal_correct',
                                            [o for o in answered if o.case.must_refuse]),
        'answer_rate_answerable': collect('refusal_correct', answered_answerable),

        # All three latency figures are computed over the SAME cases — the ones
        # that completed. Mixing populations here produced a report where the
        # generation component was larger than the total it was a component of,
        # because the total counted only successes while the parts counted
        # every attempt, including the ones that spent their time being retried
        # and then failing.
        'latency_ms_mean': metrics.mean(latencies),
        'latency_ms_p50': metrics.percentile(latencies, 0.50),
        'latency_ms_p95': metrics.percentile(latencies, 0.95),
        'retrieval_ms_mean': metrics.mean(
            [float(o.retrieval_ms) for o in answered]),
        'generation_ms_mean': metrics.mean(
            [float(o.generation_ms) for o in answered]),
        # Retrieval ran for every case, so this one is over all of them and is
        # the number to read when a run was heavily rate limited.
        'retrieval_ms_mean_all': metrics.mean(
            [float(o.retrieval_ms) for o in outcomes]),

        # Recorded so the report can say when recall is not worth reading.
        # A corpus with fewer chunks than the retriever returns makes recall
        # near-certain regardless of how good retrieval is: with 8 chunks and
        # top_k=6, three quarters of the corpus is handed over every time.
        'corpus_chunks': available_chunks,
        'retrieval_coverage': (
            min(1.0, settings.RAG_TOP_K / available_chunks) if available_chunks else None
        ),
    }

    judged_faithfulness = collect('faithfulness', outcomes)
    if judged_faithfulness is not None:
        summary['faithfulness'] = judged_faithfulness
    judged_correctness = collect('answer_correctness', answerable)
    if judged_correctness is not None:
        summary['answer_correctness'] = judged_correctness

    return {k: v for k, v in summary.items() if v is not None}
