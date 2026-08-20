"""MongoDB implementation of DocumentRepository.

This is the behaviour the project has always had, lifted out of the views
unchanged. Nothing here is new logic — the point of moving it is that the views
stop knowing what a BSON ObjectId is, and that the same calls can be answered by
the PostgreSQL implementation beside it.
"""
import logging
from typing import Any, Optional

from bson import Binary, ObjectId
from bson.errors import InvalidId
from django.utils import timezone

from core.constants import STATUS_COMPLETED
from core.mongo import chunks_col, documents_col
from core.utils import serialize_mongo_doc
from repositories.base import ChunkDTO, DocumentDTO, Page

logger = logging.getLogger(__name__)


def _oid(value: str) -> Optional[ObjectId]:
    """Parse an id, returning None rather than raising on anything malformed.

    ObjectId() raises on anything that is not 24 hex characters, and these ids
    arrive straight from URLs. Letting that propagate turns a client typo into
    a 500; returning None lets the caller answer 404, which is also what it
    would answer for an id that simply does not exist.
    """
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _to_dto(doc: Optional[dict]) -> Optional[DocumentDTO]:
    if doc is None:
        return None
    data = serialize_mongo_doc(doc)
    data['id'] = data.pop('_id', '')
    return data


class MongoDocumentRepository:
    """Documents in the `documents` collection, chunks in `chunks`."""

    # ── reads ────────────────────────────────────────────────────
    def list_for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> Page:
        query = {'user_id': user_id}
        total = documents_col().count_documents(query)
        cursor = (
            documents_col().find(query)
            .sort('created_at', -1)
            .skip(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
        return {'items': [_to_dto(d) for d in cursor], 'total': total}

    def get(self, document_id: str, user_id: int) -> Optional[DocumentDTO]:
        oid = _oid(document_id)
        if oid is None:
            return None
        return _to_dto(documents_col().find_one({'_id': oid, 'user_id': user_id}))

    def find_by_hash(self, user_id: int, file_hash: str) -> Optional[DocumentDTO]:
        return _to_dto(documents_col().find_one({'user_id': user_id, 'file_hash': file_hash}))

    def count_for_user(self, user_id: int) -> int:
        return documents_col().count_documents({'user_id': user_id})

    def list_completed(self, user_id: int, document_ids: list[str]) -> list[DocumentDTO]:
        oids = [o for o in (_oid(d) for d in document_ids) if o is not None]
        if not oids:
            return []
        found = documents_col().find({
            '_id': {'$in': oids},
            'user_id': user_id,
            'status': STATUS_COMPLETED,
        })
        return [_to_dto(d) for d in found]

    # ── writes ───────────────────────────────────────────────────
    def create(self, user_id: int, **fields: Any) -> DocumentDTO:
        now = timezone.now()
        doc = {
            'user_id': user_id,
            'status': fields.pop('status', 'pending'),
            'page_count': 0,
            'word_count': 0,
            'chunk_count': 0,
            'summary': '',
            'error_message': '',
            'created_at': now,
            'updated_at': now,
            **fields,
        }
        result = documents_col().insert_one(doc)
        doc['_id'] = result.inserted_id
        return _to_dto(doc)

    def update(self, document_id: str, user_id: int, **fields: Any) -> Optional[DocumentDTO]:
        oid = _oid(document_id)
        if oid is None:
            return None
        fields['updated_at'] = timezone.now()
        # The owner is part of the filter, not checked beforehand: a separate
        # read-then-write would leave a window in which ownership changed.
        result = documents_col().find_one_and_update(
            {'_id': oid, 'user_id': user_id},
            {'$set': fields},
            return_document=True,
        )
        return _to_dto(result)

    def delete(self, document_id: str, user_id: int) -> bool:
        oid = _oid(document_id)
        if oid is None:
            return False
        chunks_col().delete_many({'document_id': document_id, 'user_id': user_id})
        return documents_col().delete_one({'_id': oid, 'user_id': user_id}).deleted_count > 0

    # ── chunks ───────────────────────────────────────────────────
    def replace_chunks(self, document_id: str, user_id: int,
                       chunks: list[dict[str, Any]]) -> list[str]:
        chunks_col().delete_many({'document_id': document_id})
        if not chunks:
            return []

        now = timezone.now()
        rows = []
        for chunk in chunks:
            vector = chunk.get('embedding')
            rows.append({
                'document_id': document_id,
                'user_id': user_id,
                'filename': chunk.get('filename', ''),
                'content': chunk['content'],
                'chunk_index': chunk['chunk_index'],
                'page_number': chunk.get('page_number', 1),
                'start_char': chunk.get('start_char', 0),
                'end_char': chunk.get('end_char', 0),
                'word_count': chunk.get('word_count', 0),
                # Stored alongside the text so a lost FAISS index can be rebuilt
                # without re-embedding. See services/faiss_store.rebuild_index.
                'embedding': Binary(vector.tobytes()) if vector is not None else None,
                'created_at': now,
            })
        inserted = chunks_col().insert_many(rows)
        return [str(oid) for oid in inserted.inserted_ids]

    def get_chunks(self, chunk_ids: list[str], user_id: int) -> list[ChunkDTO]:
        oids = [o for o in (_oid(c) for c in chunk_ids) if o is not None]
        if not oids:
            return []

        found = {
            str(c['_id']): c
            for c in chunks_col().find({'_id': {'$in': oids}, 'user_id': user_id})
        }
        doc_ids = {c.get('document_id') for c in found.values() if c.get('document_id')}
        names = {
            str(d['_id']): d.get('original_filename', 'Unknown')
            for d in documents_col().find(
                {'_id': {'$in': [o for o in (_oid(d) for d in doc_ids) if o]}},
                {'original_filename': 1},
            )
        }

        # Returned in the order asked for: the caller's order is the ranking,
        # and Mongo's $in gives no ordering guarantee at all.
        results: list[ChunkDTO] = []
        for chunk_id in chunk_ids:
            chunk = found.get(chunk_id)
            if chunk is None:
                continue
            document_id = str(chunk.get('document_id', ''))
            results.append({
                'chunk_id': chunk_id,
                'document_id': document_id,
                'document_name': names.get(document_id, 'Unknown'),
                'page_number': chunk.get('page_number', 1),
                'content': chunk.get('content', ''),
                'chunk_index': chunk.get('chunk_index', 0),
            })
        return results

    def delete_chunks(self, document_id: str, user_id: int) -> int:
        return chunks_col().delete_many(
            {'document_id': document_id, 'user_id': user_id}
        ).deleted_count
