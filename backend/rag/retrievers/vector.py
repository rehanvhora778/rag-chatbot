"""Dense vector retrieval.

Implements LangChain's ``BaseRetriever``, so it can be dropped into an
``EnsembleRetriever`` or a compression retriever without an adapter — which is
exactly what the hybrid retriever in the next phase needs.

The division of labour is the point of this class. The vector store answers
"which chunk ids are nearest", knowing nothing about ownership beyond the id it
was given to filter on. The repository turns ids into text, applying the owner
filter again as it does. Neither one alone could leak another user's passage,
and the retriever never touches raw storage.
"""
import logging
from typing import Any, Optional

from django.conf import settings
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from rag.types import chunks_to_documents

logger = logging.getLogger(__name__)


class VectorRetriever(BaseRetriever):
    """Nearest-neighbour retrieval over one user's documents."""

    # BaseRetriever is a pydantic model; these are its fields.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: int
    document_keys: list[str] = Field(default_factory=list)
    top_k: Optional[int] = None
    fetch_k: Optional[int] = None
    use_mmr: Optional[bool] = None
    mmr_lambda: Optional[float] = None
    min_score: Optional[float] = None
    filters: dict[str, Any] = Field(default_factory=dict)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun = None,
    ) -> list[Document]:
        from rag.registry import get_embeddings, get_vector_store
        from rag.vectorstores.base import SearchRequest
        from repositories.factory import get_document_repository

        if not self.document_keys:
            logger.info('No documents to search for user %s', self.user_id)
            return []

        store = get_vector_store()
        request = SearchRequest(
            user_id=self.user_id,
            query_vector=get_embeddings().embed_query(query),
            document_keys=self.document_keys,
            top_k=self.top_k or settings.RAG_TOP_K,
            fetch_k=self.fetch_k or settings.RAG_FETCH_K,
            use_mmr=settings.RAG_USE_MMR if self.use_mmr is None else self.use_mmr,
            mmr_lambda=(settings.RAG_MMR_LAMBDA if self.mmr_lambda is None
                        else self.mmr_lambda),
            min_score=(settings.RAG_MIN_SIMILARITY_SCORE if self.min_score is None
                       else self.min_score),
            filters=self.filters,
        )

        hits = store.search(request)
        if not hits:
            logger.info('Vector search returned nothing for: %s', query[:60])
            return []

        # One repository call for all of them, in ranked order. get_chunks
        # preserves the order it is given, because that order is the ranking.
        scores = {hit.chunk_id: hit.score for hit in hits}
        chunks = get_document_repository().get_chunks(
            [hit.chunk_id for hit in hits], self.user_id,
        )

        if len(chunks) < len(hits):
            # The index knows about passages the store does not. Normal right
            # after a document is deleted, and a symptom of a stale index
            # otherwise — worth a line either way, because silently returning
            # fewer results than were found is how a retrieval regression hides.
            logger.info(
                'Vector search matched %d chunk(s) but only %d resolved for user %s',
                len(hits), len(chunks), self.user_id,
            )

        for chunk in chunks:
            chunk['similarity_score'] = scores.get(chunk['chunk_id'], 0.0)

        return chunks_to_documents(chunks)
