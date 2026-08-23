"""The embedding provider contract.

Satisfies LangChain's ``Embeddings`` interface as well as this project's own,
so a provider written here can be handed to any LangChain component that wants
one — and a LangChain embedding can be used here — without an adapter in
between.

``dimension`` is on the interface because it is not a detail: the chunk table
declares a ``vector(384)`` column, and a provider whose output is a different
width fails at insert time with a driver error that says nothing about which
setting was wrong. A system check compares the two at startup instead.
"""
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into vectors."""

    name: str

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of passages. Returns (len(texts), dimension)."""
        ...

    def embed_query(self, text: str) -> np.ndarray:
        """Embed one question. Returns (1, dimension).

        The shape matches what FAISS expects for a search. pgvector wants a
        flat list and reshapes it itself, so the difference stays in the store
        rather than becoming something every caller has to remember.
        """
        ...
