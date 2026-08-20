"""FAISS vector store — per-user index files on disk.

Wraps the existing services/faiss_store implementation behind the VectorStore
interface rather than replacing it. That code has been in production, handles
the awkward cases (a missing index rebuilt from stored vectors, concurrent
rebuilds of the same document), and rewriting it to satisfy a new interface
would be throwing away working code to make a diagram tidier.

Its real constraint is the one this whole abstraction exists to escape: an
index is a file. On a host without a persistent disk it disappears on every
restart, it cannot be filtered by anything the file does not contain, and two
processes writing the same document race.
"""
import logging

import numpy as np

from rag.vectorstores.base import SearchHit, SearchRequest, mmr_select

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """IndexFlatIP files under FAISS_INDEX_DIR/<user_id>/<index_key>.index."""

    name = 'faiss'

    def add(self, user_id: int, index_key: str, embeddings: np.ndarray,
            chunk_ids: list[str]) -> None:
        from services.faiss_store import save_index

        save_index(user_id, index_key, embeddings, chunk_ids)

    def search(self, request: SearchRequest) -> list[SearchHit]:
        from services.faiss_store import _fetch_candidates

        if request.filters:
            # Said out loud rather than ignored. A caller that asked for a page
            # range and silently got everything would draw conclusions from
            # results it believes were filtered.
            logger.warning(
                'FAISS cannot evaluate metadata filters (%s); they are being '
                'ignored. Use VECTOR_BACKEND=pgvector for filtered retrieval.',
                sorted(request.filters),
            )

        candidates: list[SearchHit] = []
        for index_key in request.document_keys:
            for chunk_id, score, vector in _fetch_candidates(
                request.user_id, index_key, request.query_vector, request.fetch_k,
            ):
                candidates.append(SearchHit(chunk_id=str(chunk_id), score=float(score),
                                            vector=vector))

        if not candidates:
            return []

        candidates.sort(key=lambda hit: hit.score, reverse=True)

        # The relevance floor is applied BEFORE diversity selection, which is a
        # deliberate change from the original pipeline (it filtered afterwards).
        #
        # MMR's job is to pick a varied set from among *relevant* passages, so
        # spending one of its k slots on a passage that is about to be discarded
        # wastes it — filtering afterwards could return four passages when six
        # good ones were available. The cost is that a query now returns top_k
        # whenever top_k clear the floor, where before it sometimes returned
        # fewer: measured on the evaluation set, 5.19 passages per question
        # against 5.00, which shows up as slightly lower retrieval precision.
        if request.min_score:
            candidates = [h for h in candidates if h.score >= request.min_score]
            if not candidates:
                return []

        if request.use_mmr:
            return mmr_select(candidates, request.top_k, request.mmr_lambda)
        return candidates[:request.top_k]

    def delete(self, user_id: int, index_key: str) -> None:
        from services.faiss_store import delete_index

        delete_index(user_id, index_key)

    def supports_filters(self) -> bool:
        return False
