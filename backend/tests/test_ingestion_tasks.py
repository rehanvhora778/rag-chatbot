"""Tests for background document ingestion.

The properties here are the ones that make a task queue worth having, and each
covers a failure the previous ``threading.Thread`` implementation had:

* the upload request returns without waiting for embedding
* a redelivered task produces one set of chunks, not two
* a document whose worker died stops claiming to be "processing" forever
* a summary failure does not fail an otherwise perfectly indexed document

Celery runs eagerly here (``CELERY_TASK_ALWAYS_EAGER`` in the test settings),
so ``.delay()`` executes inline and no broker is involved.
"""
import uuid

import numpy as np
import pytest

pytestmark = pytest.mark.django_db

PAGES = [
    {'page_number': 1, 'content': 'Refunds are issued within 30 days of delivery.',
     'char_count': 45},
    {'page_number': 2, 'content': 'Express delivery costs 12.99 GBP and takes 2 days.',
     'char_count': 49},
]


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Replace text extraction and embedding with deterministic stand-ins.

    Loading the real model would make every test in this file depend on a
    Hugging Face download and add seconds per case, and none of these tests are
    about whether the model works — they are about what happens around it.
    """
    calls = {'extract': 0, 'embed': 0}

    def fake_extract(file_path, file_type):
        calls['extract'] += 1
        return list(PAGES)

    def fake_embed(chunks):
        calls['embed'] += 1
        # Deterministic and normalised, so anything that later compares vectors
        # gets sensible values rather than noise.
        vectors = np.zeros((len(chunks), 384), dtype=np.float32)
        for i in range(len(chunks)):
            vectors[i][i % 384] = 1.0
        return vectors

    monkeypatch.setattr('services.text_extractor.extract_text', fake_extract)
    monkeypatch.setattr('services.embeddings.embed_chunks', fake_embed)
    return calls


@pytest.fixture
def pending_document(document_repo, user):
    return document_repo.create(
        user.id,
        original_filename='policy.pdf',
        filename='stored.pdf',
        file_path='/nonexistent/stored.pdf',  # noqa: S108
        file_type='pdf',
        file_size=1024,
        file_hash=uuid.uuid4().hex * 2,
        status='pending',
    )


# ══════════════════════════════════════════════════════════════════
# Idempotency — the property that makes acks_late safe
# ══════════════════════════════════════════════════════════════════

class TestIdempotency:
    def test_processing_twice_produces_one_set_of_chunks(
        self, document_repo, user, pending_document, fake_pipeline
    ):
        """A worker killed mid-document has its task redelivered.

        If ingestion appended instead of replacing, every redelivery would
        double the chunk count and the same passage would be retrieved several
        times, crowding the context window with duplicates.
        """
        from services.document_processor import process_document

        first = process_document(
            pending_document['id'], user.id, '/nonexistent/stored.pdf', 'pdf',
        )
        second = process_document(
            pending_document['id'], user.id, '/nonexistent/stored.pdf', 'pdf',
        )

        assert first['chunks'] == second['chunks']

        document = document_repo.get(pending_document['id'], user.id)
        assert document['chunk_count'] == second['chunks']
        assert document['status'] == 'completed'

    def test_reprocessing_replaces_rather_than_accumulates(
        self, document_repo, user, pending_document, fake_pipeline
    ):
        from services.document_processor import process_document

        process_document(pending_document['id'], user.id, '/nonexistent/x.pdf', 'pdf')
        document = document_repo.get(pending_document['id'], user.id)
        expected = document['chunk_count']

        for _ in range(3):
            process_document(pending_document['id'], user.id, '/nonexistent/x.pdf', 'pdf')

        document = document_repo.get(pending_document['id'], user.id)
        assert document['chunk_count'] == expected


# ══════════════════════════════════════════════════════════════════
# Status transitions
# ══════════════════════════════════════════════════════════════════

class TestStatusTransitions:
    def test_a_successful_run_records_what_it_produced(
        self, document_repo, user, pending_document, fake_pipeline
    ):
        from services.document_processor import process_document

        process_document(pending_document['id'], user.id, '/nonexistent/x.pdf', 'pdf')

        document = document_repo.get(pending_document['id'], user.id)
        assert document['status'] == 'completed'
        assert document['page_count'] == len(PAGES)
        assert document['chunk_count'] > 0
        assert document['vector_count'] == document['chunk_count']
        assert document['error_message'] == ''

    def test_a_failure_is_recorded_with_its_reason(
        self, document_repo, user, pending_document, monkeypatch
    ):
        """A failed document must say why.

        "Failed" with no reason gives the user nothing to act on and gives
        whoever debugs it nothing to search for.
        """
        from services.document_processor import process_document

        monkeypatch.setattr(
            'services.text_extractor.extract_text',
            lambda *a, **k: [],          # nothing extractable
        )

        from services.document_processor import ProcessingError

        with pytest.raises(ProcessingError):
            process_document(pending_document['id'], user.id, '/nonexistent/x.pdf', 'pdf')

        document = document_repo.get(pending_document['id'], user.id)
        assert document['status'] == 'failed'
        assert 'No text could be extracted' in document['error_message']

    def test_a_deleted_document_is_skipped_not_retried(
        self, document_repo, user, pending_document, fake_pipeline
    ):
        """Deleted between upload and the worker picking the job up.

        There is nothing to process and nothing a retry would fix, so this must
        return quietly rather than raising into Celery's retry machinery.
        """
        from services.document_processor import process_document

        document_id = pending_document['id']
        document_repo.delete(document_id, user.id)

        result = process_document(document_id, user.id, '/nonexistent/x.pdf', 'pdf')

        assert result.get('skipped')
        assert fake_pipeline['extract'] == 0


# ══════════════════════════════════════════════════════════════════
# Dispatch
# ══════════════════════════════════════════════════════════════════

class TestDispatch:
    def test_upload_queues_rather_than_processing_inline(
        self, document_repo, user, monkeypatch, settings
    ):
        """The point of the whole phase: the request does not do the work."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from services import document_service

        queued = []
        monkeypatch.setattr(
            document_service, 'queue_processing',
            lambda *args, **kwargs: queued.append(args) or 'task-id',
        )

        # Large enough to clear the minimum-size check in core/validators.py:
        # a file of a dozen bytes is truncated or empty in practice.
        upload = SimpleUploadedFile(
            'a.txt', b'Refunds are issued within 30 days of delivery. ' * 4,
            content_type='text/plain',
        )
        outcome = document_service.upload_documents(user.id, [upload])

        assert outcome.any_created
        assert outcome.created[0]['status'] == 'pending'
        assert len(queued) == 1

    def test_the_thread_fallback_is_used_when_no_broker_answers(
        self, monkeypatch, settings
    ):
        """Without Redis the project must still work, and must say so.

        The fallback has exactly the failure mode this phase removes, so it
        being silent would be worse than it not existing.
        """
        from services import document_service

        settings.CELERY_TASK_ALWAYS_EAGER = False
        monkeypatch.setattr(document_service, '_probe_broker', lambda: False)
        from django.core.cache import cache
        cache.delete(document_service._BROKER_CACHE_KEY)

        started = []
        monkeypatch.setattr(
            document_service, '_process_in_thread',
            lambda *args: started.append(args),
        )

        task_id = document_service.queue_processing('doc-1', 1, '/tmp/x.pdf', 'pdf')  # noqa: S108

        assert task_id == ''          # no Celery task exists
        assert len(started) == 1

    def test_broker_availability_is_cached(self, monkeypatch, settings):
        """Checked on every upload; a dead broker must not cost a timeout each time."""
        from django.core.cache import cache

        from services import document_service

        settings.CELERY_TASK_ALWAYS_EAGER = False
        cache.delete(document_service._BROKER_CACHE_KEY)

        probes = []
        monkeypatch.setattr(
            document_service, '_probe_broker',
            lambda: probes.append(1) or True,
        )

        for _ in range(5):
            document_service.broker_available()

        assert len(probes) == 1


# ══════════════════════════════════════════════════════════════════
# The stuck-document sweep
# ══════════════════════════════════════════════════════════════════

class TestStuckDocumentSweep:
    def test_a_long_stuck_document_is_failed(self, document_repo, user, settings,
                                             pending_document):
        """The failure mode acks_late cannot cover.

        If the broker loses the job entirely, nothing redelivers it and the
        document claims to be processing forever while the UI spins.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.documents.tasks import sweep_stuck_documents

        document_repo.update(pending_document['id'], user.id, status='processing')
        _age(settings, pending_document['id'], timezone.now() - timedelta(hours=3))

        result = sweep_stuck_documents(older_than_minutes=60)

        assert result['swept'] >= 1
        document = document_repo.get(pending_document['id'], user.id)
        assert document['status'] == 'failed'
        assert 'did not resume' in document['error_message']

    def test_a_recently_started_document_is_left_alone(
        self, document_repo, user, pending_document
    ):
        """A document that is legitimately still working must not be killed."""
        from apps.documents.tasks import sweep_stuck_documents

        document_repo.update(pending_document['id'], user.id, status='processing')

        sweep_stuck_documents(older_than_minutes=60)

        document = document_repo.get(pending_document['id'], user.id)
        assert document['status'] == 'processing'


def _age(settings, document_id: str, when):
    """Backdate a document's updated_at, whichever store is active."""
    if settings.PERSISTENCE_BACKEND == 'postgres':
        from apps.documents.models import Document

        Document.objects.filter(pk=document_id).update(updated_at=when)
    else:
        from bson import ObjectId

        from core.mongo import documents_col

        documents_col().update_one(
            {'_id': ObjectId(document_id)}, {'$set': {'updated_at': when}},
        )
