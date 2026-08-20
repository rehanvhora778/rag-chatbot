"""Reciprocal Rank Fusion.

Combining a dense retriever with a keyword one has an awkward problem: cosine
similarity runs 0 to 1 and means "how close in meaning", while PostgreSQL's
``ts_rank`` is unbounded and means "how often, how prominently". Averaging them
is meaningless, and normalising them per-query is worse than meaningless —
min-max scaling makes the best result in a list of terrible results score 1.0,
so a query the keyword side found nothing useful for still contributes a
confident top hit.

RRF sidesteps this by throwing the scores away and keeping only the *ranks*:

    score(d) = sum over retrievers of  1 / (k + rank(d))

A passage ranked first by one retriever and absent from the other beats one
ranked fourth by both — but not by much, and a passage both retrievers rank
highly wins outright. That "found by both" signal is most of what makes hybrid
retrieval better than either half.

k = 60 is the constant from Cormack, Clarke & Buettcher (2009), where it was
chosen empirically and has been the default in most implementations since. Its
role is to flatten the difference between the top few ranks so that being
first rather than third is an advantage, not a landslide.
"""
import logging
from collections import defaultdict
from typing import Iterable, Optional

from django.conf import settings
from langchain_core.documents import Document

from rag.types import RANKS, RETRIEVER, SCORE, identity

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    result_lists: dict[str, list[Document]],
    k: Optional[int] = None,
    weights: Optional[dict[str, float]] = None,
) -> list[Document]:
    """Fuse several ranked lists into one.

    `result_lists` maps a retriever name to its results, best first. The name is
    kept on each fused Document so an answer can be traced back to which
    retriever found its sources — the difference between "both agreed" and
    "only keyword found this" is most of what makes a hybrid pipeline
    debuggable.
    """
    smoothing = settings.RAG_RRF_K if k is None else k
    weights = weights or {}

    scores: dict[str, float] = defaultdict(float)
    found_by: dict[str, list[str]] = defaultdict(list)
    ranks: dict[str, dict[str, int]] = defaultdict(dict)
    documents: dict[str, Document] = {}

    for retriever_name, results in result_lists.items():
        weight = weights.get(retriever_name, 1.0)

        for position, document in enumerate(results, start=1):
            key = identity(document)
            scores[key] += weight / (smoothing + position)
            found_by[key].append(retriever_name)
            ranks[key][retriever_name] = position

            # Keep the first copy seen. They are the same passage; the metadata
            # differs only in the score each retriever assigned, and that score
            # is about to be replaced by the fused one anyway.
            documents.setdefault(key, document)

    if not documents:
        return []

    fused = []
    for key, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        document = documents[key]
        # A new Document rather than mutating: the originals belong to the
        # retrievers that produced them, and a caller comparing "what did the
        # vector side return" against the fused list would otherwise find both
        # rewritten.
        fused.append(Document(
            page_content=document.page_content,
            metadata={
                **document.metadata,
                SCORE: round(score, 6),
                RETRIEVER: '+'.join(sorted(set(found_by[key]))),
                RANKS: dict(ranks[key]),
            },
        ))

    agreed = sum(1 for key in documents if len(set(found_by[key])) > 1)
    logger.info(
        'RRF fused %d list(s) into %d passage(s); %d found by more than one retriever',
        len(result_lists), len(fused), agreed,
    )
    return fused


def deduplicate(documents: Iterable[Document]) -> list[Document]:
    """Drop repeated passages, keeping the best-ranked copy of each.

    Chunks overlap by design, so two retrievers frequently return the same
    passage and a single retriever can return near-identical neighbours. Not
    strictly needed after RRF, which fuses by identity — this is for callers
    that concatenate lists without fusing.
    """
    seen: set[str] = set()
    unique: list[Document] = []

    for document in documents:
        key = identity(document)
        if key in seen:
            continue
        seen.add(key)
        unique.append(document)

    return unique
