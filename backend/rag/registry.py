"""Provider selection.

One place turns a settings string into an implementation, for LLMs, embeddings
and vector stores alike. Everything else asks for "the configured provider".

Instances are cached per configuration: a provider holds a client and, for
embeddings, a loaded model — building one per request would reload the model on
every chat message. ``reset_providers()`` clears the cache, which is what lets a
test swap in a fake and what an admin-changed configuration will use later.
"""
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from rag.embeddings.base import EmbeddingProvider
    from rag.llm.base import LLMProvider
    from rag.vectorstores.base import VectorStore

logger = logging.getLogger(__name__)


class UnknownProvider(Exception):
    """A configured provider name has no implementation."""


# ══════════════════════════════════════════════════════════════════
# LLM
# ══════════════════════════════════════════════════════════════════

@lru_cache(maxsize=8)
def _llm(name: str, model: str) -> 'LLMProvider':
    if name == 'groq':
        from rag.llm.groq_provider import GroqProvider

        return GroqProvider(model=model or None)

    raise UnknownProvider(
        f"LLM_PROVIDER='{name}' has no implementation. Available: groq.\n"
        'Adding one means a new module in rag/llm/ satisfying the LLMProvider '
        'protocol and a branch here.'
    )


def get_llm(model: str = '') -> 'LLMProvider':
    return _llm(getattr(settings, 'LLM_PROVIDER', 'groq'), model)


# ══════════════════════════════════════════════════════════════════
# Embeddings
# ══════════════════════════════════════════════════════════════════

@lru_cache(maxsize=4)
def _embeddings(name: str) -> 'EmbeddingProvider':
    if name == 'local':
        from rag.embeddings.local import LocalEmbeddingProvider

        return LocalEmbeddingProvider()

    raise UnknownProvider(
        f"EMBEDDING_PROVIDER='{name}' has no implementation. Available: local."
    )


def get_embeddings() -> 'EmbeddingProvider':
    return _embeddings(getattr(settings, 'EMBEDDING_PROVIDER', 'local'))


# ══════════════════════════════════════════════════════════════════
# Vector store
# ══════════════════════════════════════════════════════════════════

@lru_cache(maxsize=4)
def _vector_store(name: str) -> 'VectorStore':
    if name == 'pgvector':
        from rag.vectorstores.pgvector_store import PgVectorStore

        return PgVectorStore()
    if name == 'faiss':
        from rag.vectorstores.faiss_store import FAISSVectorStore

        return FAISSVectorStore()

    logger.error(
        "VECTOR_BACKEND='%s' is not a known store; falling back to faiss.", name,
    )
    from rag.vectorstores.faiss_store import FAISSVectorStore

    return FAISSVectorStore()


def get_vector_store() -> 'VectorStore':
    return _vector_store(getattr(settings, 'VECTOR_BACKEND', 'faiss'))


def reset_providers() -> None:
    """Forget every cached provider. For tests and configuration changes."""
    _llm.cache_clear()
    _embeddings.cache_clear()
    _vector_store.cache_clear()
