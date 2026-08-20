"""Local sentence-transformer embeddings.

Wraps services/embeddings, which runs all-MiniLM-L6-v2 through ONNX Runtime
(DirectML where a GPU is available) and falls back to PyTorch. That module stays
where it is: it handles the awkward parts — thread-safe lazy loading, batching
by length to minimise padding, the ONNX-to-torch fallback — and the value of
this class is the interface, not a rewrite.

Local rather than hosted is a real choice. Embedding a 50-page document is a
hundred passages; sending them to a paid API would make ingestion cost money
per upload and fail whenever the network does. The model is 90 MB and runs on a
laptop.

**This class does not subclass LangChain's ``Embeddings``, on purpose.** That
interface is specified to return ``list[list[float]]``, and this returns numpy
arrays — converting 100,000 floats into Python lists on every ingest, only for
the vector store to convert them straight back, is real work done for nothing.
Claiming to satisfy an interface while returning a different type would be
worse than not claiming it: anything LangChain handed this to would fail
somewhere far from the cause. ``as_langchain()`` provides a conforming adapter
for the cases that genuinely need one.
"""
import numpy as np
from django.conf import settings
from langchain_core.embeddings import Embeddings


class LocalEmbeddingProvider:
    """all-MiniLM-L6-v2 via ONNX Runtime, with a PyTorch fallback."""

    name = 'local'

    @property
    def model_name(self) -> str:
        return settings.EMBEDDING_MODEL_NAME

    @property
    def dimension(self) -> int:
        return settings.EMBEDDING_DIMENSION

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        from services.embeddings import embed_texts

        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return embed_texts(texts)

    def embed_query(self, text: str) -> np.ndarray:
        from services.embeddings import embed_query

        return embed_query(text)

    def as_langchain(self) -> Embeddings:
        """A LangChain-conforming view of this provider."""
        return _LangChainEmbeddings(self)


class _LangChainEmbeddings(Embeddings):
    """Adapts an EmbeddingProvider to LangChain's list-of-floats contract.

    Only used where a LangChain component is doing the calling. The project's
    own pipeline uses the numpy path.
    """

    def __init__(self, provider: LocalEmbeddingProvider):
        self._provider = provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_documents(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return np.asarray(self._provider.embed_query(text)).reshape(-1).tolist()
