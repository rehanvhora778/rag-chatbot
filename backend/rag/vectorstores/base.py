"""The vector store contract.

Two implementations answer it: FAISS index files on disk, and pgvector columns
in PostgreSQL. Everything above works against this interface, so moving from
one to the other is a settings change rather than a rewrite of retrieval.

The interface is deliberately narrow. It does not expose "get me the index" or
"give me the raw vectors", because those are the operations that leak one
backend's shape into the caller — a FAISS index is a file with integer offsets,
a pgvector column is a row with a primary key, and no caller should have to
know which. What both can do is: store vectors for a document, search them for
a user, and forget a document.

**Every search takes an owner.** Not for convenience — it is the isolation
boundary. A vector store that could be asked for "the nearest passages" without
saying whose is one refactor away from returning somebody else's.
"""
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

import numpy as np


@dataclass
class SearchHit:
    """One nearest-neighbour result.

    Deliberately not a Document: at this level a hit is an id and a score, and
    the text has not been loaded yet. Keeping them separate is what lets the
    retriever fetch passage text once, through the repository, with the owner
    filter applied — rather than each vector store growing its own way to read
    chunk content.
    """

    chunk_id: str
    score: float
    vector: Optional[np.ndarray] = None


@dataclass
class SearchRequest:
    """Everything a similarity search needs.

    Bundled into an object rather than passed as eight arguments because the
    hybrid retriever in the next phase forwards these unchanged, and a
    positional signature that long is one reordering away from a silent bug.
    """

    user_id: int
    query_vector: np.ndarray
    # Index keys, not document ids — see VectorStore.index_key.
    document_keys: list[str]
    top_k: int
    fetch_k: int
    use_mmr: bool = True
    mmr_lambda: float = 0.7
    min_score: float = 0.0
    # Reserved for metadata filtering (page ranges, collections). Honoured by
    # pgvector, ignored by FAISS, which has nowhere to evaluate it.
    filters: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """Storage and nearest-neighbour search over chunk embeddings."""

    name: str

    def add(self, user_id: int, index_key: str, embeddings: np.ndarray,
            chunk_ids: list[str]) -> None:
        """Store vectors for one document, replacing anything already there.

        Replacing rather than appending is what makes re-ingestion idempotent,
        which is what makes the Celery task safe to redeliver.
        """
        ...

    def search(self, request: SearchRequest) -> list[SearchHit]:
        """Nearest passages for a query, best first, scoped to one user."""
        ...

    def delete(self, user_id: int, index_key: str) -> None:
        """Forget a document's vectors. Must not raise if there are none."""
        ...

    def supports_filters(self) -> bool:
        """Whether `SearchRequest.filters` is honoured.

        Asked rather than assumed, so a caller can decide between filtering in
        the store and filtering after retrieval — and so a filter is never
        silently dropped, which would return results the caller believes were
        excluded.
        """
        ...


def mmr_select(hits: list[SearchHit], k: int, lambda_mult: float) -> list[SearchHit]:
    """Maximal Marginal Relevance selection.

    Balances relevance to the query against difference from what has already
    been picked, so the context is not six near-identical passages. That
    matters most where it is least obvious: overlapping chunks mean the two
    best matches for a question are frequently the same sentence twice, and
    without this the model is handed one fact repeated rather than several.

    Embeddings are L2-normalised, so a dot product is cosine similarity.

    Shared by both stores because it operates on candidate vectors, not on how
    they were fetched — implementing it twice would be two chances to get the
    lambda the wrong way round.
    """
    usable = [h for h in hits if h.vector is not None]
    if not usable:
        # Nothing to diversify against; fall back to plain relevance order.
        return hits[:k]

    selected: list[SearchHit] = []
    selected_vectors: list[np.ndarray] = []
    remaining = list(usable)

    while remaining and len(selected) < k:
        best_index, best_score = 0, -float('inf')

        for index, hit in enumerate(remaining):
            if selected_vectors:
                redundancy = max(float(np.dot(hit.vector, chosen))
                                 for chosen in selected_vectors)
            else:
                redundancy = 0.0
            score = lambda_mult * hit.score - (1.0 - lambda_mult) * redundancy
            if score > best_score:
                best_score, best_index = score, index

        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_vectors.append(chosen.vector)

    return selected
