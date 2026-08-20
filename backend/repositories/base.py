"""Repository contracts.

A repository is the only thing in the project that knows whether a document
lives in MongoDB or PostgreSQL. Everything above it — services, views,
serializers — works against these protocols, which is what makes
``PERSISTENCE_BACKEND`` a one-line switch instead of a rewrite.

**Repositories return plain dicts, not model instances.** That looks like a
weaker contract than returning objects, and it is chosen deliberately: the two
implementations have nothing in common to return — one produces BSON documents,
the other Django model instances — so any shared return type would have to be a
translation layer built twice. Dicts in a documented shape are that translation
layer, they are exactly what DRF serialises, and they are already the shape the
React app consumes, so the API response does not change by a single key while
the store underneath it does.

The TypedDicts below are the contract. They are checked by the parity tests,
which run the same assertions against both implementations — that suite is the
real specification, and the reason a backend swap can be trusted.
"""
from typing import Any, Optional, Protocol, TypedDict, runtime_checkable

# ══════════════════════════════════════════════════════════════════
# Shapes
# ══════════════════════════════════════════════════════════════════

class DocumentDTO(TypedDict, total=False):
    """One document, in exactly the shape /api/documents/ has always returned."""

    id: str
    user_id: int
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    file_hash: str
    file_path: str
    status: str
    page_count: int
    word_count: int
    chunk_count: int
    vector_count: int
    summary: str
    error_message: str
    # Only set on rows migrated out of MongoDB; names the FAISS index file.
    legacy_mongo_id: Optional[str]
    created_at: Any
    updated_at: Any


class ChunkDTO(TypedDict, total=False):
    """A retrieved passage, as the RAG pipeline and citation builder expect."""

    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    content: str
    chunk_index: int
    similarity_score: float


class ConversationDTO(TypedDict, total=False):
    id: str
    user_id: int
    title: str
    document_ids: list[str]
    document_names: list[str]
    status: str
    message_count: int
    last_message_preview: str
    created_at: Any
    updated_at: Any
    last_message_at: Any


class MessageDTO(TypedDict, total=False):
    id: str
    session_id: str
    user_id: int
    role: str
    content: str
    sources: list[dict[str, Any]]
    created_at: Any


class Page(TypedDict):
    """A slice of a listing, plus the total needed to render pagination."""

    items: list[Any]
    total: int


# ══════════════════════════════════════════════════════════════════
# Contracts
# ══════════════════════════════════════════════════════════════════

@runtime_checkable
class DocumentRepository(Protocol):
    """Storage for documents and their chunks.

    Every method that reads or writes a document takes ``user_id``. That is not
    convenience — it is the isolation boundary. There is deliberately no
    ``get(document_id)`` without an owner, so a caller cannot accidentally fetch
    someone else's file by passing an id it got from somewhere untrusted; the
    filter is part of the query rather than a check the caller must remember.
    """

    def list_for_user(self, user_id: int, *, page: int = 1,
                      page_size: int = 20) -> Page: ...

    def get(self, document_id: str, user_id: int) -> Optional[DocumentDTO]:
        """Return the document, or None if it does not exist *or* is not theirs.

        The two cases are deliberately indistinguishable to the caller: telling
        someone "that exists but is not yours" confirms the existence of another
        user's document, which is exactly what isolation is meant to prevent.
        """
        ...

    def find_by_hash(self, user_id: int, file_hash: str) -> Optional[DocumentDTO]: ...

    def create(self, user_id: int, **fields: Any) -> DocumentDTO: ...

    def update(self, document_id: str, user_id: int, **fields: Any) -> Optional[DocumentDTO]: ...

    def delete(self, document_id: str, user_id: int) -> bool: ...

    def count_for_user(self, user_id: int) -> int: ...

    def list_completed(self, user_id: int, document_ids: list[str]) -> list[DocumentDTO]:
        """The subset of `document_ids` that this user owns and that finished
        processing. Used wherever a client-supplied list of ids has to be
        turned into something safe to retrieve from."""
        ...

    # --- chunks ---

    def replace_chunks(self, document_id: str, user_id: int,
                       chunks: list[dict[str, Any]]) -> list[str]:
        """Drop this document's chunks and store the given ones. Returns the new
        chunk ids in the order supplied, so the caller can build a vector index
        whose positions line up."""
        ...

    def get_chunks(self, chunk_ids: list[str], user_id: int) -> list[ChunkDTO]: ...

    def delete_chunks(self, document_id: str, user_id: int) -> int: ...


@runtime_checkable
class ConversationRepository(Protocol):
    """Storage for conversations and their messages."""

    def list_for_user(self, user_id: int, *, page: int = 1,
                      page_size: int = 20) -> Page: ...

    def get(self, conversation_id: str, user_id: int) -> Optional[ConversationDTO]: ...

    def create(self, user_id: int, title: str,
               document_ids: list[str], document_names: list[str]) -> ConversationDTO: ...

    def update(self, conversation_id: str, user_id: int,
               **fields: Any) -> Optional[ConversationDTO]: ...

    def delete(self, conversation_id: str, user_id: int) -> bool: ...

    def search(self, user_id: int, query: str, *, page: int = 1,
               page_size: int = 20) -> Page: ...

    # --- messages ---

    def list_messages(self, conversation_id: str, user_id: int) -> list[MessageDTO]: ...

    def add_turn(self, conversation_id: str, user_id: int, question: str,
                 answer: str, sources: list[dict[str, Any]],
                 **metrics: Any) -> tuple[MessageDTO, MessageDTO]:
        """Append a question and its answer as one unit.

        A single call rather than two `add_message` calls because the pair is
        atomic: an answer stored without its question, or a question whose
        answer failed to save, leaves a transcript that cannot be replayed and
        a history the retriever would read as incoherent.
        """
        ...

    def recent_history(self, conversation_id: str, user_id: int,
                       max_turns: int) -> list[MessageDTO]: ...

    def rename_document_everywhere(self, user_id: int, document_id: str,
                                   new_name: str) -> int:
        """Keep the denormalised document names on conversations in step with a
        rename, so citations do not keep quoting the old filename."""
        ...
