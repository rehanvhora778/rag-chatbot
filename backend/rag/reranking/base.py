"""The reranker contract.

Retrieval and reranking answer different questions, which is why both exist.

A bi-encoder — what the vector store uses — embeds the query and each passage
separately and compares the results. That is what makes it fast enough to search
a whole corpus: the passage vectors were computed at ingestion time and never
have to be recomputed. The cost is that the passage was embedded without any
knowledge of the question, so its vector has to summarise everything the passage
might ever be asked about.

A cross-encoder reads the query and one passage *together* and scores that pair.
It is far more accurate for the same model size, and far too slow to run over a
corpus — every pair is a fresh forward pass. So it runs last, over the twenty or
so candidates retrieval has already narrowed to.

That ordering is the whole design: retrieve wide and cheap, rerank narrow and
accurate, then hand the model fewer, better passages.
"""
from typing import Protocol, runtime_checkable

from langchain_core.documents import Document


@runtime_checkable
class Reranker(Protocol):
    """Reorders retrieved passages by relevance to the query."""

    name: str

    def available(self) -> bool:
        """Whether this reranker can actually run.

        Asked before use because the cross-encoder needs a model that is not
        installed in every environment. A reranker that silently did nothing
        would leave the pipeline reporting rerank_enabled=True while ranking
        exactly as it did before — and an evaluation run comparing the two
        would find no difference and draw the wrong conclusion.
        """
        ...

    def rerank(self, query: str, documents: list[Document],
               top_k: int) -> list[Document]:
        """Return the `top_k` most relevant passages, best first."""
        ...


