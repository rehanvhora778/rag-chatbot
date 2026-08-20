"""Cross-encoder reranking.

``cross-encoder/ms-marco-MiniLM-L-6-v2`` scores each (query, passage) pair
directly. It is a 22 MB model — smaller than the embedding model — and it runs
over the candidates retrieval already selected rather than the corpus, so the
cost is bounded by ``fetch_k`` and not by how many documents exist.

**It needs the PyTorch stack**, via sentence-transformers. That is present in
requirements.txt and deliberately absent from requirements-prod.txt, where
PyTorch alone is around 800 MB and would not fit a free-tier build. So this
degrades rather than fails: ``available()`` reports honestly, the pipeline logs
once and continues with fusion order, and the evaluation snapshot records
whether reranking actually ran — a run labelled "with reranking" that silently
did not rerank is worse than no run at all.

The model is loaded once and kept. On a Celery worker or a long-lived web
process that is a one-off cost of a few seconds; reloading per query would make
reranking slower than the LLM call it is meant to be improving.
"""
import logging
import threading
from typing import Optional

from django.conf import settings
from langchain_core.documents import Document

from rag.types import SCORE

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()
_load_failed = False


def _load_model(model_name: str):
    """Load the cross-encoder once, thread-safely.

    Two concurrent chat requests would otherwise both start loading it, which
    on a constrained instance means two copies in memory at the same moment.
    """
    global _model, _load_failed

    if _model is not None or _load_failed:
        return _model

    with _model_lock:
        if _model is not None or _load_failed:
            return _model

        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            logger.warning(
                'Reranking is enabled but sentence-transformers is not installed, '
                'so results will keep their fusion order. It is excluded from '
                'requirements-prod.txt because PyTorch is ~800 MB; install '
                'requirements.txt to enable reranking.'
            )
            _load_failed = True
            return None

        try:
            logger.info('Loading cross-encoder %s…', model_name)
            _model = CrossEncoder(model_name, max_length=512)
            logger.info('Cross-encoder ready.')
        except Exception as exc:
            logger.error('Could not load the cross-encoder %s: %s', model_name, exc)
            _load_failed = True
            return None

    return _model


class CrossEncoderReranker:
    """Reorders passages with a (query, passage) cross-encoder."""

    name = 'cross-encoder'

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.RAG_RERANK_MODEL

    def available(self) -> bool:
        return _load_model(self.model_name) is not None

    def rerank(self, query: str, documents: list[Document],
               top_k: int) -> list[Document]:
        if not documents:
            return []

        model = _load_model(self.model_name)
        if model is None:
            # Honest degradation: fusion order, not a crash and not a pretence
            # that reranking happened.
            return documents[:top_k]

        pairs = [(query, document.page_content) for document in documents]

        try:
            scores = model.predict(pairs)
        except Exception as exc:
            logger.error('Reranking failed, keeping fusion order: %s', exc)
            return documents[:top_k]

        ranked = sorted(zip(documents, scores, strict=True),
                        key=lambda pair: float(pair[1]), reverse=True)

        reranked = []
        for document, score in ranked[:top_k]:
            reranked.append(Document(
                page_content=document.page_content,
                metadata={
                    **document.metadata,
                    SCORE: round(float(score), 6),
                    # The pre-rerank score is kept rather than overwritten. When
                    # an answer cites something surprising, the question is
                    # always "did retrieval find it or did the reranker promote
                    # it", and that is unanswerable if only one number survives.
                    'retrieval_score': document.metadata.get(SCORE),
                },
            ))

        logger.info('Reranked %d candidate(s) down to %d', len(documents), len(reranked))
        return reranked


def reset_model() -> None:
    """Drop the cached model. For tests."""
    global _model, _load_failed
    with _model_lock:
        _model = None
        _load_failed = False
