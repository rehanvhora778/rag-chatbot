"""
Module 8: FAISS Vector Store — lazy imports, per-user on-disk indexes.
"""
import logging
from pathlib import Path
from typing import List, Tuple

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
    import numpy as np

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss.write_index(index, str(_index_path(user_id, document_id)))
    np.save(str(_meta_path(user_id, document_id)), np.array(chunk_ids))
    logger.info("FAISS index saved for document %s (%d vectors)", document_id, index.ntotal)


def load_index(user_id, document_id: str):
    import faiss
    import numpy as np

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


def _fetch_candidates(user_id, document_id: str, query_embedding, fetch_k: int):
    """Return up to `fetch_k` nearest candidates for one document as
    (chunk_id, similarity, vector) tuples. Vectors (normalized) are reconstructed
    so the caller can run MMR diversity selection."""
    try:
        index, chunk_ids = load_index(user_id, document_id)
    except FileNotFoundError:
        logger.warning("Index missing for document %s, skipping.", document_id)
        return []

    k = min(fetch_k, index.ntotal)
    if k == 0:
        return []

    distances, indices = index.search(query_embedding, k)
    candidates = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        try:
            vec = index.reconstruct(int(idx))
        except Exception:
            vec = None
        candidates.append((chunk_ids[idx], float(dist), vec))
    return candidates


def _mmr_select(candidates, k: int, lambda_mult: float):
    """Maximum Marginal Relevance selection.

    Balances relevance to the query against diversity among picked chunks so the
    context isn't six near-duplicate passages. Embeddings are L2-normalized, so
    dot product == cosine similarity.

    candidates: list of (chunk_id, similarity, vector) sorted by similarity desc.
    Returns list of (chunk_id, similarity).
    """
    import numpy as np

    usable = [c for c in candidates if c[2] is not None]
    if not usable:
        return [(cid, score) for cid, score, _ in candidates[:k]]

    selected = []
    selected_vecs = []
    remaining = usable[:]

    while remaining and len(selected) < k:
        best_i, best_mmr = 0, -float("inf")
        for i, (cid, score, vec) in enumerate(remaining):
            if selected_vecs:
                diversity = max(float(np.dot(vec, sv)) for sv in selected_vecs)
            else:
                diversity = 0.0
            mmr = lambda_mult * score - (1.0 - lambda_mult) * diversity
            if mmr > best_mmr:
                best_mmr, best_i = mmr, i
        cid, score, vec = remaining.pop(best_i)
        selected.append((cid, score))
        selected_vecs.append(vec)

    return selected


def search_multiple_indexes(
    user_id,
    document_ids: List[str],
    query_embedding,
    top_k: int = None,
    fetch_k: int = None,
    use_mmr: bool = None,
    lambda_mult: float = None,
) -> List[Tuple[str, float]]:
    """Retrieve the best `top_k` chunks across all of a session's documents.

    Pulls a wider `fetch_k` candidate pool first, then (optionally) applies MMR
    to pick a relevant *and* diverse final set.
    """
    from django.conf import settings

    top_k       = top_k       or settings.RAG_TOP_K
    fetch_k     = fetch_k     or settings.RAG_FETCH_K
    use_mmr     = settings.RAG_USE_MMR if use_mmr is None else use_mmr
    lambda_mult = settings.RAG_MMR_LAMBDA if lambda_mult is None else lambda_mult

    candidates = []
    for doc_id in document_ids:
        candidates.extend(_fetch_candidates(user_id, doc_id, query_embedding, fetch_k))

    if not candidates:
        return []

    candidates.sort(key=lambda x: x[1], reverse=True)

    if use_mmr:
        return _mmr_select(candidates, top_k, lambda_mult)
    return [(cid, score) for cid, score, _ in candidates[:top_k]]
