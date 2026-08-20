"""Celery tasks for document ingestion.

Ingestion used to run in a ``threading.Thread`` started from inside the upload
view. Under gunicorn that means a deploy, a worker recycle or an OOM kill takes
the job with it: the document sits at "processing" forever, with no retry, no
record of what happened, and no way to find out. It also burned CPU embedding
inside the process that was meant to be answering requests.

These tasks fix that, and the guarantees they rely on are configured in
``config/settings/base.py``:

* ``task_acks_late`` — the job is acknowledged after it finishes, not when it is
  picked up, so a worker that dies mid-document has its job redelivered.
* ``task_reject_on_worker_lost`` — the same for a hard kill.
* ``worker_prefetch_multiplier = 1`` — one document at a time per process, since
  embedding is CPU-bound and holds a model in memory.

Redelivery is only safe because ``process_document`` is idempotent: it drops
the existing chunks and index before writing new ones, so running it twice
produces one set of results rather than two.
"""
import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

# Retried on: a transient database blip, a provider rate limit, an OCR call that
# timed out. NOT retried on a corrupt file — that fails identically every time,
# and retrying it three times just delays telling the user.
RETRY_FOR = (ConnectionError, TimeoutError, OSError)


@shared_task(
    bind=True,
    name='documents.process_document',
    autoretry_for=RETRY_FOR,
    retry_backoff=10,          # 10s, 20s, 40s
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def process_document_task(self, document_id: str, user_id: int,
                          file_path: str, file_type: str) -> dict:
    """Extract, chunk, embed and index one uploaded document."""
    from services.document_processor import process_document

    logger.info('Processing document %s (attempt %d/%d)',
                document_id, self.request.retries + 1, self.max_retries + 1)

    # Recorded so a document stuck in "processing" can be traced to a specific
    # task and revoked, rather than being a mystery with no thread to pull.
    _record_task_id(document_id, user_id, self.request.id)

    try:
        result = process_document(document_id, user_id, file_path, file_type)
    except SoftTimeLimitExceeded:
        # The soft limit fires before the hard one, so there is a chance to
        # record why the document stopped instead of the worker vanishing.
        logger.error('Document %s exceeded the time limit', document_id)
        _mark_failed(document_id, user_id,
                     'Processing took too long and was stopped. The document may '
                     'be very large or scanned at high resolution.')
        raise
    except RETRY_FOR as exc:
        if self.request.retries >= self.max_retries:
            logger.error('Document %s failed after %d attempts: %s',
                         document_id, self.max_retries + 1, exc)
        raise
    except Exception:
        # process_document has already marked the document failed with the
        # reason. Re-raised so the failure is visible in Celery too, but not
        # retried: a document that cannot be parsed cannot be parsed on the
        # second attempt either.
        raise

    if not result.get('skipped'):
        # Chained rather than called inline: the document is chat-ready now,
        # and a rate-limited summary must not hold that up or fail it.
        generate_summary_task.delay(document_id, user_id)

    return result


@shared_task(
    bind=True,
    name='documents.generate_summary',
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=2,
)
def generate_summary_task(self, document_id: str, user_id: int) -> dict:
    """Generate the document's AI summary.

    Failure here is deliberately not fatal to the document. It is already
    indexed and answerable; a missing summary is a cosmetic gap, and marking a
    working document as failed because a rate limit was hit would be worse than
    the gap.
    """
    from services.document_processor import generate_summary

    try:
        summary = generate_summary(document_id, user_id)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            logger.warning('Giving up on the summary for %s: %s', document_id, exc)
            _set_summary(document_id, user_id,
                         'A summary could not be generated for this document.')
            return {'document_id': document_id, 'summary': None}
        raise

    return {'document_id': document_id, 'summary_length': len(summary or '')}


@shared_task(name='documents.reindex_document', acks_late=True)
def reindex_document_task(document_id: str, user_id: int) -> dict:
    """Re-run ingestion for a document already stored.

    Used after a chunking or embedding-model change, when existing chunks are no
    longer comparable with new ones. Reads the file path back from the record
    rather than taking it as an argument, so a caller cannot point it at a file
    belonging to somebody else.
    """
    from repositories.factory import get_document_repository
    from services.document_processor import process_document

    document = get_document_repository().get(document_id, user_id)
    if document is None:
        return {'skipped': 'document not found'}

    return process_document(
        document_id, user_id, document['file_path'], document['file_type'],
    )


@shared_task(name='documents.delete_document_embeddings')
def delete_document_embeddings_task(document_id: str, user_id: int,
                                    index_key: str = '') -> dict:
    """Remove a document's chunks and vector index.

    Runs on deletion when the chunk count is large enough that doing it inline
    would hold the HTTP request open. Takes the index key explicitly because by
    the time this runs the document row may already be gone.
    """
    from django.conf import settings

    from repositories.factory import get_document_repository

    removed = get_document_repository().delete_chunks(document_id, user_id)

    if settings.VECTOR_BACKEND == 'faiss':
        from services.faiss_store import delete_index

        try:
            delete_index(user_id, index_key or document_id)
        except Exception as exc:
            logger.warning('Could not delete the index for %s: %s', document_id, exc)

    return {'document_id': document_id, 'chunks_deleted': removed}


@shared_task(name='documents.sweep_stuck_documents')
def sweep_stuck_documents(older_than_minutes: int = 60) -> dict:
    """Mark documents that have been "processing" implausibly long as failed.

    A document whose worker was killed before ``acks_late`` could redeliver the
    job — or whose job was lost entirely because the broker was flushed — stays
    at "processing" forever. The UI polls it, sees no change, and shows a
    spinner that will never stop. This turns that into an honest failure the
    user can act on by reprocessing.

    Scheduled by Celery beat; see CELERY_BEAT_SCHEDULE.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from core.constants import STATUS_FAILED, STATUS_PROCESSING

    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    swept = 0

    if settings.PERSISTENCE_BACKEND == 'postgres':
        from apps.documents.models import Document

        swept = Document.objects.filter(
            status=STATUS_PROCESSING, updated_at__lt=cutoff,
        ).update(
            status=STATUS_FAILED,
            error_message=(
                'Processing stopped unexpectedly and did not resume. '
                'Reprocess the document to try again.'
            ),
            updated_at=timezone.now(),
        )
    else:
        from core.mongo import documents_col

        result = documents_col().update_many(
            {'status': STATUS_PROCESSING, 'updated_at': {'$lt': cutoff}},
            {'$set': {
                'status': STATUS_FAILED,
                'error_message': (
                    'Processing stopped unexpectedly and did not resume. '
                    'Reprocess the document to try again.'
                ),
                'updated_at': timezone.now(),
            }},
        )
        swept = result.modified_count

    if swept:
        logger.warning('Swept %d document(s) stuck in processing for over %d minutes',
                       swept, older_than_minutes)
    return {'swept': swept, 'older_than_minutes': older_than_minutes}


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _record_task_id(document_id: str, user_id: int, task_id: str) -> None:
    from repositories.factory import get_document_repository

    try:
        get_document_repository().update(document_id, user_id, task_id=task_id or '')
    except Exception as exc:
        # Bookkeeping. Losing it must not stop the document being processed.
        logger.debug('Could not record the task id for %s: %s', document_id, exc)


def _mark_failed(document_id: str, user_id: int, message: str) -> None:
    from django.utils import timezone

    from core.constants import STATUS_FAILED
    from repositories.factory import get_document_repository

    try:
        get_document_repository().update(
            document_id, user_id,
            status=STATUS_FAILED,
            error_message=message,
            processing_completed_at=timezone.now(),
        )
    except Exception as exc:
        logger.error('Could not mark %s as failed: %s', document_id, exc)


def _set_summary(document_id: str, user_id: int, summary: str) -> None:
    from repositories.factory import get_document_repository

    try:
        get_document_repository().update(document_id, user_id, summary=summary)
    except Exception as exc:
        logger.debug('Could not store the summary placeholder for %s: %s', document_id, exc)
