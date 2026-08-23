"""FAISS vector store — per-user index files on disk.

An index is a file, and that is this backend's defining constraint: on a host
without a persistent disk it disappears on every restart, it cannot be filtered
by anything the file does not contain, and two processes writing the same
document race. The first of those is survivable because the chunk text is still
in the database — ``rebuild_index`` re-creates a missing index from the stored
vectors, and retrieval calls it automatically, so a document uploaded before a
restart stays searchable afterwards. The other two are why ``pgvector`` is the
recommended backend for anything deployed.

The module-level functions below are the file handling; ``FAISSVectorStore`` is
the ``VectorStore`` interface over them.
"""
import logging
import threading
import time
from pathlib import Path
from typing import List

import numpy as np

from rag.vectorstores.base import SearchHit, SearchRequest, mmr_select

logger = logging.getLogger(__name__)


def _index_path(user_id, document_id: str) -> Path:
    from django.conf import settings
    base = Path(settings.FAISS_INDEX_DIR) / str(user_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{document_id}.index"


def _meta_path(user_id, document_id: str) -> Path:
    from django.conf import settings
    base = Path(settings.FAISS_INDEX_DIR) / str(user_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{document_id}.meta.npy"


def save_index(user_id, document_id: str, embeddings, chunk_ids: List[str]) -> None:
    import faiss

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss.write_index(index, str(_index_path(user_id, document_id)))
    np.save(str(_meta_path(user_id, document_id)), np.array(chunk_ids))
    logger.info("FAISS index saved for document %s (%d vectors)", document_id, index.ntotal)


def load_index(user_id, document_id: str):
    import faiss

    idx_path  = _index_path(user_id, document_id)
    meta_path = _meta_path(user_id, document_id)

    if not idx_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"FAISS index not found for document {document_id}")

    index     = faiss.read_index(str(idx_path))
    chunk_ids = np.load(str(meta_path), allow_pickle=True).tolist()
    return index, chunk_ids


def delete_index(user_id, document_id: str) -> None:
    for path in [_index_path(user_id, document_id), _meta_path(user_id, document_id)]:
        if path.exists():
            path.unlink()
            logger.info("Deleted FAISS file: %s", path)


# One lock per document: two chat requests arriving together after a restart
# would otherwise both rebuild the same index, doubling the (already slow)
# embedding work on a 0.15-CPU container and racing to write the same two files.
_rebuild_locks: dict = {}
_rebuild_locks_guard = threading.Lock()


def _rebuild_lock(user_id, document_id: str) -> threading.Lock:
    key = (str(user_id), document_id)
    with _rebuild_locks_guard:
        lock = _rebuild_locks.get(key)
        if lock is None:
            lock = _rebuild_locks[key] = threading.Lock()
        return lock


def _index_exists(user_id, document_id: str) -> bool:
    return _index_path(user_id, document_id).exists() and _meta_path(user_id, document_id).exists()


def rebuild_index(user_id, document_id: str) -> bool:
    """Recreate a missing FAISS index from the chunks MongoDB still holds.

    The original upload is not needed. Chunks are normally stored with their
    vector, so the index is rebuilt by copying those back — cheap enough to do
    inside a request. Chunks written before vectors were persisted have text
    only; those are re-embedded instead, which is exact (embedding is
    deterministic) but slow enough to be worth avoiding.

    Returns False when there is nothing to rebuild from — a document whose
    processing never finished.
    """
    from django.conf import settings

    from core.mongo import chunks_col

    with _rebuild_lock(user_id, document_id):
        # Another thread may have finished the rebuild while we waited here.
        if _index_exists(user_id, document_id):
            return True

        # Sorted so the rebuild is reproducible; positions only have to agree
        # with the chunk_ids saved alongside them, not with the lost index.
        stored = list(
            chunks_col()
            .find({'document_id': document_id},
                  {'content': 1, 'chunk_index': 1, 'embedding': 1})
            .sort('chunk_index', 1)
        )
        if not stored:
            logger.warning(
                "Cannot rebuild the index for document %s: no chunks in MongoDB. "
                "It needs to be uploaded again.", document_id,
            )
            return False

        dim = settings.EMBEDDING_DIMENSION
        started = time.perf_counter()

        if all(c.get('embedding') for c in stored):
            # Normal path: the vectors were saved with the chunks, so this is a
            # copy rather than a recompute — fast enough to run inside a request.
            source = 'stored vectors'
            embeddings = np.frombuffer(
                b''.join(bytes(c['embedding']) for c in stored), dtype=np.float32,
            ).reshape(len(stored), dim).copy()
        else:
            # Documents indexed before the vectors were persisted have text only.
            # Re-embedding reproduces them exactly (embedding is deterministic),
            # but it is slow on a throttled instance — hence the warning.
            source = 're-embedding (indexed before vectors were stored)'
            logger.warning(
                "Document %s has no stored vectors — re-embedding %d chunks. "
                "This is slow; re-upload the document to avoid it next time.",
                document_id, len(stored),
            )
            from rag.registry import get_embeddings

            embeddings = get_embeddings().embed_documents(
                [c.get('content', '') for c in stored]
            )

        logger.info("Rebuilding lost FAISS index for document %s (%d chunks, %s)…",
                    document_id, len(stored), source)
        save_index(user_id, document_id, embeddings, [str(c['_id']) for c in stored])
        logger.info("Rebuilt index for document %s in %.1fs.",
                    document_id, time.perf_counter() - started)
        return True


def _fetch_candidates(user_id, document_id: str, query_embedding, fetch_k: int):
    """Return up to `fetch_k` nearest candidates for one document as
    (chunk_id, similarity, vector) tuples. Vectors (normalized) are reconstructed
    so the caller can run MMR diversity selection."""
    try:
        index, chunk_ids = load_index(user_id, document_id)
    except FileNotFoundError:
        # Skipping here used to be silent and total: with no index there are no
        # candidates, so the pipeline retrieved nothing and every question came
        # back "I could not find an answer to your question in the uploaded
        # document(s)" even though the document was listed and marked completed.
        # On a host with no persistent disk that is the normal state after any
        # restart, so rebuild from MongoDB instead of giving up.
        logger.warning("Index missing for document %s — rebuilding it.", document_id)
        try:
            if not rebuild_index(user_id, document_id):
                return []
            index, chunk_ids = load_index(user_id, document_id)
        except Exception as exc:
            # A failed rebuild must not take the whole answer down: other
            # documents in the session may still have their index.
            logger.error("Could not rebuild the index for document %s: %s",
                         document_id, exc, exc_info=True)
            return []

    k = min(fetch_k, index.ntotal)
    if k == 0:
        return []

    distances, indices = index.search(query_embedding, k)
    candidates = []
    for dist, idx in zip(distances[0], indices[0], strict=False):
        if idx < 0:
            continue
        try:
            vec = index.reconstruct(int(idx))
        except Exception:
            vec = None
        candidates.append((chunk_ids[idx], float(dist), vec))
    return candidates


class FAISSVectorStore:
    """IndexFlatIP files under FAISS_INDEX_DIR/<user_id>/<index_key>.index."""

    name = 'faiss'

    def add(self, user_id: int, index_key: str, embeddings: np.ndarray,
            chunk_ids: list[str]) -> None:
        save_index(user_id, index_key, embeddings, chunk_ids)

    def search(self, request: SearchRequest) -> list[SearchHit]:
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
        delete_index(user_id, index_key)

    def supports_filters(self) -> bool:
        return False
