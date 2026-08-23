"""Hybrid retrieval: dense + keyword, fused, then reranked.

    query
      |
      +-- vector retrieval (pgvector, fetch_k candidates)
      |
      +-- keyword retrieval (Postgres FTS, keyword_top_k candidates)
      |
      v
    Reciprocal Rank Fusion
      |
      v
    cross-encoder rerank        (optional)
      |
      v
    top_k passages

The two retrievers run over the same chunks and disagree usefully. Dense finds
"return period" when the user asked about a "refund window"; keyword finds
"Section 8.2" and "order #4471", which mean nothing to an embedding. Fusion
keeps what either found and rewards what both did.

Reranking is where the precision comes from. Fusion produces a good candidate
set but its ordering is a compromise between two rankings, neither of which
looked at the query and the passage together. The cross-encoder does, over
twenty-odd candidates rather than a corpus, and is what makes it reasonable to
hand the model four passages instead of six.

**Degrades rather than fails.** Without PostgreSQL there is no keyword side and
this falls back to dense-only; without the reranker model the fusion order
stands. Both are logged once, and both are recorded in the evaluation snapshot,
so a run can never claim a component that did not actually run.
"""
import logging
from typing import Any, Optional

from django.conf import settings
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from rag.retrievers.fusion import reciprocal_rank_fusion

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """Dense and keyword retrieval, fused by RRF and optionally reranked."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: int
    document_keys: list[str] = Field(default_factory=list)
    top_k: Optional[int] = None
    fetch_k: Optional[int] = None
    keyword_top_k: Optional[int] = None
    use_keyword: Optional[bool] = None
    use_rerank: Optional[bool] = None
    filters: dict[str, Any] = Field(default_factory=dict)

    # Populated each call so the pipeline can report what actually ran rather
    # than what was configured to run.
    trace: dict[str, Any] = Field(default_factory=dict)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun = None,
    ) -> list[Document]:
        from rag.retrievers.vector import VectorRetriever

        if not self.document_keys:
            return []

        final_k = self.top_k or settings.RAG_TOP_K
        self.trace = {'keyword': False, 'reranked': False}

        # --- Dense ---
        # Deliberately not truncated to top_k here. Fusion and reranking both
        # need a pool to work over; narrowing before them would mean the
        # reranker only ever reorders passages dense retrieval already liked,
        # which is most of the value gone.
        vector_results = VectorRetriever(
            user_id=self.user_id,
            document_keys=self.document_keys,
            top_k=self.fetch_k or settings.RAG_FETCH_K,
            fetch_k=self.fetch_k or settings.RAG_FETCH_K,
            use_mmr=False,
            filters=self.filters,
        ).invoke(query)

        result_lists = {'vector': vector_results}

        # --- Keyword ---
        if self._keyword_enabled():
            keyword_results = self._keyword_search(query)
            if keyword_results:
                result_lists['keyword'] = keyword_results
                self.trace['keyword'] = True

        if not any(result_lists.values()):
            logger.info('Hybrid retrieval found nothing for: %s', query[:60])
            return []

        # --- Fuse ---
        fused = (reciprocal_rank_fusion(result_lists)
                 if len(result_lists) > 1 else vector_results)
        self.trace['candidates'] = len(fused)
        self.trace['vector_hits'] = len(vector_results)
        self.trace['keyword_hits'] = len(result_lists.get('keyword', []))

        # --- Rerank ---
        reranked = self._rerank(query, fused, final_k)
        if reranked is not None:
            self.trace['reranked'] = True
            return reranked

        return fused[:final_k]

    # ── keyword ──────────────────────────────────────────────────
    def _keyword_enabled(self) -> bool:
        if self.use_keyword is not None:
            return self.use_keyword
        return bool(settings.RAG_HYBRID_ENABLED)

    def _keyword_search(self, query: str) -> list[Document]:
        from django.db import connection

        if connection.vendor != 'postgresql':
            # Reachable only if the system check was bypassed. Silence here
            # would mean an evaluation labelled "hybrid" that ran dense-only.
            logger.warning(
                'Hybrid retrieval is enabled but the database is %s; the keyword '
                'half needs PostgreSQL full-text search. Running dense-only.',
                connection.vendor,
            )
            return []

        from rag.retrievers.keyword import KeywordRetriever

        try:
            return KeywordRetriever(
                user_id=self.user_id,
                document_keys=self.document_keys,
                top_k=self.keyword_top_k or settings.RAG_KEYWORD_TOP_K,
                filters=self.filters,
            ).invoke(query)
        except Exception as exc:
            # One half failing must not lose the other: a dense-only answer is
            # far better than no answer.
            logger.error('Keyword retrieval failed, continuing dense-only: %s',
                         exc, exc_info=True)
            return []

    # ── rerank ───────────────────────────────────────────────────
    def _rerank(self, query: str, documents: list[Document],
                top_k: int) -> Optional[list[Document]]:
        enabled = (settings.RAG_RERANK_ENABLED if self.use_rerank is None
                   else self.use_rerank)
        if not enabled or not documents:
            return None

        from rag.reranking.cross_encoder import CrossEncoderReranker

        reranker = CrossEncoderReranker()
        if not reranker.available():
            return None

        return reranker.rerank(query, documents, top_k)


def build_retriever(user_id: int, document_keys: list[str],
                    filters: Optional[dict[str, Any]] = None) -> BaseRetriever:
    """The retriever the current configuration calls for.

    One place decides, so the chain does not branch on settings and a test can
    ask for a specific retriever directly.
    """
    from rag.retrievers.vector import VectorRetriever

    if settings.RAG_HYBRID_ENABLED or settings.RAG_RERANK_ENABLED:
        return HybridRetriever(
            user_id=user_id, document_keys=document_keys, filters=filters or {},
        )

    return VectorRetriever(
        user_id=user_id, document_keys=document_keys, filters=filters or {},
    )
