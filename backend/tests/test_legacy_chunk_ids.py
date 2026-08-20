"""Regression tests for resolving chunks by their pre-migration MongoDB id.

The bug these cover was silent and total. With ``PERSISTENCE_BACKEND=postgres``
and ``VECTOR_BACKEND=faiss``, the FAISS index returns the chunk ids it was built
with — MongoDB ObjectIds — and the PostgreSQL repository could not look them up.
It raised nothing and logged nothing; it returned an empty list, so the pipeline
concluded the documents were irrelevant and answered every single question with
the refusal message. A user would see a working app that had apparently
forgotten everything they uploaded.
"""
import uuid

import pytest
from django.db import connection

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        connection.vendor != 'postgresql',
        reason='The legacy-id fallback uses a JSONB lookup; PostgreSQL only.',
    ),
]


@pytest.fixture
def pg_repo(settings):
    from repositories.factory import get_document_repository, reset_repositories

    settings.PERSISTENCE_BACKEND = 'postgres'
    reset_repositories()
    yield get_document_repository()
    reset_repositories()


@pytest.fixture
def migrated_chunks(pg_repo, user):
    """A document whose chunks carry the MongoDB id they were migrated from."""
    from apps.documents.models import Document, DocumentChunk, DocumentStatus

    document = Document.objects.create(
        owner=user,
        original_filename='migrated.pdf',
        stored_filename='migrated.pdf',
        file_path='/nonexistent/migrated.pdf',  # noqa: S108
        file_type='pdf',
        file_size=1024,
        file_hash=uuid.uuid4().hex * 2,
        status=DocumentStatus.COMPLETED,
        legacy_mongo_id='6a8168fb9db3df0fce5aa93c',
    )

    # 24-hex, the shape a real ObjectId has.
    legacy_ids = [f'6a8168fb9db3df0fce5aa{i:03d}' for i in range(3)]
    for index, legacy_id in enumerate(legacy_ids):
        DocumentChunk.objects.create(
            document=document,
            owner=user,
            content=f'Passage {index} about vector search.',
            chunk_index=index,
            page_number=index + 1,
            metadata={'legacy_mongo_id': legacy_id},
        )
    return document, legacy_ids


class TestLegacyChunkIdResolution:
    def test_chunks_resolve_by_their_mongo_id(self, pg_repo, user, migrated_chunks):
        _document, legacy_ids = migrated_chunks

        found = pg_repo.get_chunks(legacy_ids, user.id)

        assert len(found) == 3
        assert [c['chunk_id'] for c in found] == legacy_ids
        assert [c['page_number'] for c in found] == [1, 2, 3]

    def test_the_ranking_order_survives(self, pg_repo, user, migrated_chunks):
        """Order is the ranking, same as for native ids."""
        _document, legacy_ids = migrated_chunks

        requested = [legacy_ids[2], legacy_ids[0]]
        found = pg_repo.get_chunks(requested, user.id)

        assert [c['chunk_id'] for c in found] == requested

    def test_native_and_legacy_ids_can_be_mixed(self, pg_repo, user, migrated_chunks):
        """A document reprocessed after migration has UUID chunk ids while its
        neighbours still have legacy ones, so a single query sees both."""
        from apps.documents.models import DocumentChunk

        document, legacy_ids = migrated_chunks
        fresh = DocumentChunk.objects.create(
            document=document, owner=user, content='Reprocessed passage.',
            chunk_index=99, page_number=9,
        )

        found = pg_repo.get_chunks([legacy_ids[1], str(fresh.pk)], user.id)

        assert [c['chunk_id'] for c in found] == [legacy_ids[1], str(fresh.pk)]

    def test_the_owner_filter_still_applies(self, pg_repo, user, other_user,
                                            migrated_chunks):
        """The fallback must not become a way around isolation.

        These ids are the ones that leak most easily — they were handed to
        browsers inside citations for as long as the MongoDB backend was live.
        """
        _document, legacy_ids = migrated_chunks

        assert pg_repo.get_chunks(legacy_ids, other_user.id) == []

    def test_unknown_legacy_ids_are_skipped_not_fatal(self, pg_repo, user,
                                                      migrated_chunks):
        _document, legacy_ids = migrated_chunks

        found = pg_repo.get_chunks([legacy_ids[0], '0' * 24], user.id)

        assert [c['chunk_id'] for c in found] == [legacy_ids[0]]

    def test_document_name_is_attached_for_citations(self, pg_repo, user,
                                                     migrated_chunks):
        _document, legacy_ids = migrated_chunks

        found = pg_repo.get_chunks(legacy_ids, user.id)

        assert all(c['document_name'] == 'migrated.pdf' for c in found)
