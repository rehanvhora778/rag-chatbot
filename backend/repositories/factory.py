"""Repository selection.

One place decides which implementation the application talks to. Everything
else asks for "a document repository" and gets whichever backend
``PERSISTENCE_BACKEND`` names.

Instances are cached per backend rather than built per call: they hold no
request state — a repository is a set of queries, not a session — so a single
instance is safe to share, and building one per request would be pure churn.
``reset_repositories()`` clears the cache, which is what lets a test flip the
setting and get the other implementation.
"""
import logging
from functools import cache

from django.conf import settings

from repositories.base import ConversationRepository, DocumentRepository

logger = logging.getLogger(__name__)

MONGO = 'mongo'
POSTGRES = 'postgres'


def _backend() -> str:
    backend = getattr(settings, 'PERSISTENCE_BACKEND', MONGO)
    if backend not in (MONGO, POSTGRES):
        # A typo here would silently route every read at the wrong store, so it
        # is louder than a warning but still recoverable: fall back to the
        # historical default rather than taking the process down.
        logger.error(
            "PERSISTENCE_BACKEND=%r is not a known backend; falling back to %r.",
            backend, MONGO,
        )
        return MONGO
    return backend


@cache
def _document_repository(backend: str) -> DocumentRepository:
    if backend == POSTGRES:
        from repositories.postgres.documents import PostgresDocumentRepository

        return PostgresDocumentRepository()
    from repositories.mongo.documents import MongoDocumentRepository

    return MongoDocumentRepository()


@cache
def _conversation_repository(backend: str) -> ConversationRepository:
    if backend == POSTGRES:
        from repositories.postgres.conversations import PostgresConversationRepository

        return PostgresConversationRepository()
    from repositories.mongo.conversations import MongoConversationRepository

    return MongoConversationRepository()


def get_document_repository() -> DocumentRepository:
    return _document_repository(_backend())


def get_conversation_repository() -> ConversationRepository:
    return _conversation_repository(_backend())


def reset_repositories() -> None:
    """Forget the cached instances. For tests that change the backend setting."""
    _document_repository.cache_clear()
    _conversation_repository.cache_clear()
