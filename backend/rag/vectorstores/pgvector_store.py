"""pgvector vector store — embeddings live on the chunk rows they belong to.

What this fixes about the FAISS backend, in order of how much it matters:

* **The vectors are in the database.** No index file to lose on a host with an
  ephemeral disk, no rebuild path, nothing to keep in step with the chunk table.
* **The owner filter is part of the query.** Isolation is enforced by the same
  WHERE clause that does the search, rather than by remembering to look in the
  right per-user directory.
* **Metadata filters work.** A page range or a collection is a predicate the
  planner can apply; with FAISS there is nowhere to evaluate one.
* **Deleting a document deletes its vectors**, through the same cascade that
  removes its chunks. There is no second thing to forget.

Cosine distance, matching FAISS's inner product: the embeddings are
L2-normalised, so the two rank identically, and cosine is what the rest of the
pipeline reports as a similarity.
"""
import logging
from typing import Any

import numpy as np
from django.db.models import Q
from pgvector.django import CosineDistance

from rag.vectorstores.base import SearchHit, SearchRequest, mmr_select

logger = logging.getLogger(__name__)


class PgVectorStore:
    """Vectors stored in documents_documentchunk.embedding."""

    name = 'pgvector'

    # ── writes ───────────────────────────────────────────────────
    def add(self, user_id: int, index_key: str, embeddings: np.ndarray,
            chunk_ids: list[str]) -> None:
        """A no-op, and deliberately so.

        The repository writes each vector onto its chunk row as part of
        ``replace_chunks``. Writing them again here would mean the same value
        stored by two code paths, and the moment they disagree, retrieval
        returns passages whose text does not match the vector that found them.

        The method exists because it is part of the interface, and because the
        FAISS backend genuinely needs it.
        """
        return None

    def delete(self, user_id: int, index_key: str) -> None:
        """Also a no-op: deleting a document cascades to its chunks, and the
        vector is a column on the chunk."""
        return None

    def supports_filters(self) -> bool:
        return True

    # ── search ───────────────────────────────────────────────────
    def search(self, request: SearchRequest) -> list[SearchHit]:
        from apps.documents.models import DocumentChunk

        probe = _as_list(request.query_vector)
        if probe is None:
            return []

        queryset = (
            DocumentChunk.objects
            # owner_id is on the chunk row itself, so this predicate and the
            # vector scan are on the same table — which is what lets the HNSW
            # index be used rather than applied after the fact.
            .filter(owner_id=request.user_id, embedding__isnull=False)
        )

        document_filter = self._document_filter(request.document_keys)
        if document_filter is not None:
            queryset = queryset.filter(document_filter)

        queryset = self._apply_filters(queryset, request.filters)

        # fetch_k, not top_k: MMR needs a candidate pool to diversify within,
        # and the min-score floor may reject some of what comes back.
        rows = list(
            queryset
            .annotate(distance=CosineDistance('embedding', probe))
            .order_by('distance')
            .values_list('id', 'distance', 'embedding')[:max(request.fetch_k, request.top_k)]
        )
        if not rows:
            return []

        hits = [
            SearchHit(
                chunk_id=str(chunk_id),
                # pgvector returns a distance; the pipeline reports similarity.
                score=1.0 - float(distance),
                vector=np.asarray(embedding, dtype=np.float32)
                if embedding is not None else None,
            )
            for chunk_id, distance, embedding in rows
        ]

        # Floor before diversity selection, matching FAISSVectorStore — see the
        # rationale there. Both stores must order these the same way or the two
        # backends would return different numbers of passages for one query.
        if request.min_score:
            hits = [h for h in hits if h.score >= request.min_score]
            if not hits:
                return []

        if request.use_mmr:
            return mmr_select(hits, request.top_k, request.mmr_lambda)
        return hits[:request.top_k]

    # ── helpers ──────────────────────────────────────────────────
    @staticmethod
    def _document_filter(document_keys: list[str]):
        """Restrict the search to the conversation's documents.

        The keys arriving here may be UUIDs or, for anything migrated out of
        MongoDB, the id it had there. Both are accepted: a conversation created
        before the migration still names its documents by the old id, and a
        search that quietly matched nothing would look exactly like a document
        with no relevant content.
        """
        import uuid

        if not document_keys:
            return None

        uuids, legacy = [], []
        for key in document_keys:
            try:
                uuids.append(uuid.UUID(str(key)))
            except (ValueError, AttributeError, TypeError):
                legacy.append(str(key))

        condition = Q(pk__in=[])          # matches nothing, then widened below
        if uuids:
            condition |= Q(document_id__in=uuids)
        if legacy:
            condition |= Q(document__legacy_mongo_id__in=legacy)
        return condition

    @staticmethod
    def _apply_filters(queryset, filters: dict[str, Any]):
        """Metadata filters the store can push into the query."""
        if not filters:
            return queryset

        pages = filters.get('pages')
        if pages:
            queryset = queryset.filter(page_number__in=list(pages))

        page_range = filters.get('page_range')
        if page_range and len(page_range) == 2:
            queryset = queryset.filter(
                page_number__gte=page_range[0], page_number__lte=page_range[1],
            )

        collection_id = filters.get('collection_id')
        if collection_id:
            queryset = queryset.filter(document__collection_id=collection_id)

        unknown = set(filters) - {'pages', 'page_range', 'collection_id'}
        if unknown:
            # Never drop a filter silently: the caller believes those results
            # were excluded.
            logger.warning('Ignoring unsupported retrieval filter(s): %s',
                           sorted(unknown))

        return queryset


def _as_list(vector) -> list[float] | None:
    """Normalise a query vector to the flat list pgvector expects.

    embed_query returns a (1, dim) array because that is what FAISS wants;
    pgvector wants dim values. Passing the wrong shape produces an operator
    error from the driver that says nothing about which caller was wrong.
    """
    if vector is None:
        return None
    array = np.asarray(vector, dtype=np.float32).reshape(-1)
    if array.size == 0:
        return None
    return array.tolist()
