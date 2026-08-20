"""PostgreSQL implementation of DocumentRepository.

Answers exactly the same calls as the MongoDB implementation and returns the
same dict shape, so nothing above the repository can tell which one it is
talking to. The parity tests assert that claim rather than trusting it.
"""
import logging
import uuid
from typing import Any, Optional

from django.db import IntegrityError, transaction

from apps.documents.models import Document, DocumentChunk, DocumentStatus
from repositories.base import ChunkDTO, DocumentDTO, Page

logger = logging.getLogger(__name__)

# Written by create/update; everything else on the model is derived.
_WRITABLE = {
    'original_filename', 'stored_filename', 'file_path', 'file_type',
    'file_size', 'file_hash', 'status', 'error_message', 'page_count',
    'word_count', 'chunk_count', 'vector_count', 'summary', 'task_id',
    'processing_started_at', 'processing_completed_at', 'processing_duration_ms',
    'collection_id',
}

# Keys the Mongo implementation uses that name something different here.
_ALIASES = {'filename': 'stored_filename'}


def _uuid(value: str) -> Optional[uuid.UUID]:
    """Parse an id from a URL, returning None instead of raising on a typo."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _to_dto(doc: Optional[Document]) -> Optional[DocumentDTO]:
    """Render a Document in the shape the API has always returned.

    ``filename`` and ``user_id`` keep their MongoDB-era names because the React
    app reads them, and a rename here would be an API break for no benefit.
    """
    if doc is None:
        return None
    return {
        'id': str(doc.pk),
        'user_id': doc.owner_id,
        'filename': doc.stored_filename,
        'original_filename': doc.original_filename,
        'file_type': doc.file_type,
        'file_size': doc.file_size,
        'file_hash': doc.file_hash,
        'file_path': doc.file_path,
        'status': doc.status,
        'page_count': doc.page_count,
        'word_count': doc.word_count,
        'chunk_count': doc.chunk_count,
        'vector_count': doc.vector_count,
        'summary': doc.summary,
        'error_message': doc.error_message,
        # Exposed because the FAISS backend names index files after the id the
        # document had in MongoDB. Retrieval asks for it via
        # rag_pipeline._index_key; without it a migrated document would be
        # looked up under its new UUID, find no index file, and silently
        # retrieve nothing. Unused once VECTOR_BACKEND=pgvector.
        'legacy_mongo_id': doc.legacy_mongo_id,
        'created_at': doc.created_at,
        'updated_at': doc.updated_at,
    }


def _normalise(fields: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in fields.items():
        key = _ALIASES.get(key, key)
        if key in _WRITABLE:
            out[key] = value
    return out


class PostgresDocumentRepository:
    # ── reads ────────────────────────────────────────────────────
    def list_for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> Page:
        qs = Document.objects.filter(owner_id=user_id).order_by('-created_at')
        total = qs.count()
        start = max(page - 1, 0) * page_size
        return {
            'items': [_to_dto(d) for d in qs[start:start + page_size]],
            'total': total,
        }

    def get(self, document_id: str, user_id: int) -> Optional[DocumentDTO]:
        pk = _uuid(document_id)
        if pk is None:
            return None
        return _to_dto(Document.objects.filter(pk=pk, owner_id=user_id).first())

    def find_by_hash(self, user_id: int, file_hash: str) -> Optional[DocumentDTO]:
        return _to_dto(
            Document.objects.filter(owner_id=user_id, file_hash=file_hash).first()
        )

    def count_for_user(self, user_id: int) -> int:
        return Document.objects.filter(owner_id=user_id).count()

    def list_completed(self, user_id: int, document_ids: list[str]) -> list[DocumentDTO]:
        pks = [p for p in (_uuid(d) for d in document_ids) if p is not None]
        if not pks:
            return []
        found = Document.objects.filter(
            pk__in=pks, owner_id=user_id, status=DocumentStatus.COMPLETED,
        )
        return [_to_dto(d) for d in found]

    # ── writes ───────────────────────────────────────────────────
    def create(self, user_id: int, **fields: Any) -> DocumentDTO:
        data = _normalise(fields)
        data.setdefault('status', DocumentStatus.PENDING)
        try:
            doc = Document.objects.create(owner_id=user_id, **data)
        except IntegrityError:
            # (owner, file_hash) is unique here, where MongoDB only had an
            # application-level check. Two uploads of the same file racing each
            # other now lose the race in the database rather than both being
            # accepted, so surface the existing row instead of a 500.
            existing = self.find_by_hash(user_id, data.get('file_hash', ''))
            if existing:
                logger.info('Duplicate upload for user %s resolved to existing document %s',
                            user_id, existing['id'])
                return existing
            raise
        return _to_dto(doc)

    def update(self, document_id: str, user_id: int, **fields: Any) -> Optional[DocumentDTO]:
        pk = _uuid(document_id)
        if pk is None:
            return None
        data = _normalise(fields)
        if not data:
            return self.get(document_id, user_id)

        updated = Document.objects.filter(pk=pk, owner_id=user_id).update(**data)
        if not updated:
            return None
        return self.get(document_id, user_id)

    def delete(self, document_id: str, user_id: int) -> bool:
        pk = _uuid(document_id)
        if pk is None:
            return False
        # Chunks go with it through the cascade — no second delete needed, and
        # no way to forget one.
        deleted, _ = Document.objects.filter(pk=pk, owner_id=user_id).delete()
        return deleted > 0

    # ── chunks ───────────────────────────────────────────────────
    def replace_chunks(self, document_id: str, user_id: int,
                       chunks: list[dict[str, Any]]) -> list[str]:
        pk = _uuid(document_id)
        if pk is None:
            return []

        with transaction.atomic():
            DocumentChunk.objects.filter(document_id=pk, owner_id=user_id).delete()
            if not chunks:
                return []

            rows = []
            for chunk in chunks:
                vector = chunk.get('embedding')
                rows.append(DocumentChunk(
                    document_id=pk,
                    owner_id=user_id,
                    content=chunk['content'],
                    chunk_index=chunk['chunk_index'],
                    page_number=chunk.get('page_number', 1),
                    start_char=chunk.get('start_char', 0),
                    end_char=chunk.get('end_char', 0),
                    word_count=chunk.get('word_count', 0),
                    # content_tsv is deliberately absent: the database trigger
                    # fills it on insert, and setting it here would be a second
                    # place that has to stay correct.
                    embedding=vector.tolist() if vector is not None else None,
                ))
            created = DocumentChunk.objects.bulk_create(rows, batch_size=500)

        return [str(c.pk) for c in created]

    def get_chunks(self, chunk_ids: list[str], user_id: int) -> list[ChunkDTO]:
        pks = [p for p in (_uuid(c) for c in chunk_ids) if p is not None]
        # Ids that are not UUIDs are MongoDB ObjectIds coming back out of a
        # FAISS index built before the migration — see _legacy_chunks below.
        legacy_ids = [c for c in chunk_ids if _uuid(c) is None]

        if not pks and not legacy_ids:
            return []

        found = {
            str(c.pk): c
            for c in DocumentChunk.objects
            .filter(pk__in=pks, owner_id=user_id)
            .select_related('document')
        }
        found.update(self._legacy_chunks(legacy_ids, user_id))
        # Caller order is the ranking; a database IN clause has no order.
        results: list[ChunkDTO] = []
        for chunk_id in chunk_ids:
            chunk = found.get(str(chunk_id))
            if chunk is None:
                continue
            results.append({
                'chunk_id': chunk_id,
                'document_id': str(chunk.document_id),
                'document_name': chunk.document.original_filename,
                'page_number': chunk.page_number,
                'content': chunk.content,
                'chunk_index': chunk.chunk_index,
            })
        return results

    def _legacy_chunks(self, legacy_ids: list[str], user_id: int) -> dict[str, DocumentChunk]:
        """Resolve chunks by the MongoDB id they were migrated from.

        A FAISS index stores, alongside its vectors, the chunk id each vector
        belongs to. Indexes built before the migration hold MongoDB ObjectIds,
        so with ``PERSISTENCE_BACKEND=postgres`` and ``VECTOR_BACKEND=faiss``
        the search returns ids this repository cannot look up — and the failure
        is silent: no error, no results, and every question answered with the
        refusal message as though the documents contained nothing.

        ``migrate_from_mongo`` records the original id in ``metadata``, so the
        lookup is possible. This exists to keep retrieval working through the
        migration, which is what allows the two backends to be compared on
        identical queries before MongoDB is retired.

        Removable once every index is either rebuilt or replaced by pgvector.
        """
        if not legacy_ids:
            return {}

        matched = (
            DocumentChunk.objects
            .filter(owner_id=user_id, metadata__legacy_mongo_id__in=legacy_ids)
            .select_related('document')
        )
        # Keyed by the legacy id, because that is what the caller asked for and
        # what it will use to attach the similarity score.
        return {c.metadata['legacy_mongo_id']: c for c in matched}

    def delete_chunks(self, document_id: str, user_id: int) -> int:
        pk = _uuid(document_id)
        if pk is None:
            return 0
        deleted, _ = DocumentChunk.objects.filter(
            document_id=pk, owner_id=user_id
        ).delete()
        return deleted
