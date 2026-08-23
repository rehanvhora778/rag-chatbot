"""Document upload, validation and deletion.

Everything the upload endpoint used to do inline. The view is now responsible
for HTTP and nothing else; this module owns the rules — what may be uploaded,
what counts as a duplicate, what has to be cleaned up when a document goes away
— and it is callable from a test, a management command, or a Celery task
without a request object.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from django.conf import settings

from core.analytics import record_event
from core.constants import EVENT_UPLOAD, STATUS_PENDING
from core.utils import (
    compute_file_hash,
    generate_unique_filename,
    get_file_extension,
    get_user_upload_dir,
)
from repositories.factory import get_conversation_repository, get_document_repository

logger = logging.getLogger(__name__)

# Broker reachability is cached briefly: this is checked on every upload, and a
# dead broker would otherwise cost each one a connection timeout. Short enough
# that starting Redis is noticed without restarting Django.
_BROKER_CACHE_KEY = 'celery-broker-available'
_BROKER_CACHE_SECONDS = 30
# Short: this runs on the upload path, and a broker that is not there should
# cost milliseconds to discover, not seconds.
_BROKER_PROBE_TIMEOUT = 0.5
# How long to wait for a worker to answer a ping. Longer than the socket probe
# because this is a round trip through the broker rather than a TCP connect,
# and it is paid at most once per _BROKER_CACHE_SECONDS.
_WORKER_PING_TIMEOUT = 0.75


class DocumentError(Exception):
    """A rejected upload or an invalid request, with a message meant for a user."""


@dataclass
class UploadOutcome:
    """What came of an upload request: some files accepted, some rejected."""

    created: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def any_created(self) -> bool:
        return bool(self.created)


# ══════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════

def validate_upload(uploaded_file) -> Optional[str]:
    """Return a rejection reason, or None when the file is acceptable.

    The checks live in core/validators.py — filename, extension, size, and the
    content actually matching what the extension claims. Adapted to a return
    value here because the upload loop reports one reason per file rather than
    failing the whole batch on the first bad one.
    """
    from core.validators import ValidationFailed
    from core.validators import validate_upload as run_checks

    try:
        run_checks(uploaded_file, extension=get_file_extension(uploaded_file.name))
    except ValidationFailed as exc:
        return str(exc)
    return None


def check_quota(user_id: int, incoming: int) -> Optional[str]:
    """Reject an upload that would take the account past its document limit."""
    limit = settings.MAX_DOCUMENTS_PER_USER
    if not limit:
        return None

    current = get_document_repository().count_for_user(user_id)
    if current + incoming > limit:
        return (f'This would exceed the limit of {limit} documents '
                f'({current} already stored). Delete some first.')
    return None


# ══════════════════════════════════════════════════════════════════
# Upload
# ══════════════════════════════════════════════════════════════════

def upload_documents(user_id: int, files: list) -> UploadOutcome:
    """Validate, store and queue a batch of uploaded files.

    Each file is handled independently: one rejected file does not fail the
    others, because a user selecting five documents and getting a single blanket
    error has no way to tell which one was the problem.
    """
    outcome = UploadOutcome()

    if not files:
        raise DocumentError('No files provided.')

    quota_error = check_quota(user_id, len(files))
    if quota_error:
        raise DocumentError(quota_error)

    repository = get_document_repository()

    for uploaded_file in files:
        rejection = validate_upload(uploaded_file)
        if rejection:
            outcome.errors.append(rejection)
            continue

        file_hash = compute_file_hash(uploaded_file)
        if repository.find_by_hash(user_id, file_hash):
            outcome.errors.append(f'{uploaded_file.name}: already uploaded.')
            continue

        try:
            document = _store_and_queue(user_id, uploaded_file, file_hash)
        except Exception as exc:
            # One file failing to reach disk must not lose the rest of the batch.
            logger.error('Could not store %s for user %s: %s',
                         uploaded_file.name, user_id, exc, exc_info=True)
            outcome.errors.append(f'{uploaded_file.name}: could not be stored.')
            continue

        outcome.created.append(document)

    return outcome


def _store_and_queue(user_id: int, uploaded_file, file_hash: str) -> dict[str, Any]:
    extension = get_file_extension(uploaded_file.name)
    # A generated name, never the uploaded one: a filename like
    # "../../config/settings.py" must not be able to decide where bytes land.
    stored_name = generate_unique_filename(uploaded_file.name)
    destination = get_user_upload_dir(user_id) / stored_name

    with open(destination, 'wb') as handle:
        for chunk in uploaded_file.chunks():
            handle.write(chunk)

    document = get_document_repository().create(
        user_id,
        original_filename=uploaded_file.name,
        filename=stored_name,
        file_path=str(destination),
        file_type=extension,
        file_size=uploaded_file.size,
        file_hash=file_hash,
        status=STATUS_PENDING,
    )

    record_event(user_id, EVENT_UPLOAD, {
        'document_id': document['id'],
        'filename': uploaded_file.name,
        'file_type': extension,
    })

    queue_processing(document['id'], user_id, str(destination), extension)
    return document


def queue_processing(document_id: str, user_id: int, file_path: str,
                     file_type: str) -> str:
    """Hand a document to whatever runs ingestion. Returns the task id, if any.

    Celery when a broker is reachable; a daemon thread when it is not.

    The fallback is not laziness — it is what keeps ``manage.py runserver`` with
    no Redis working exactly as this project always has, so a clone can be run
    and demonstrated without standing up infrastructure first. It is chosen by
    whether the broker actually answers, not by a setting someone has to
    remember to change, and it logs which path it took so a document processed
    in-process is never a silent surprise.

    The thread has the failure mode this whole phase exists to remove: a
    restart loses the job. That is acceptable on a laptop and not in
    production, which is why the container images run a worker.
    """
    if broker_available():
        from apps.documents.tasks import process_document_task

        task = process_document_task.delay(document_id, user_id, file_path, file_type)
        logger.info('Queued document %s on Celery (task %s)', document_id, task.id)
        return task.id

    logger.warning(
        'No Celery broker reachable — processing document %s in a background '
        'thread instead. A restart will lose this job; run a worker for '
        'anything that matters.',
        document_id,
    )
    _process_in_thread(document_id, user_id, file_path, file_type)
    return ''


def _process_in_thread(document_id: str, user_id: int, file_path: str,
                       file_type: str) -> None:
    import threading

    def _run() -> None:
        from rag.ingestion.pipeline import generate_summary, process_document

        try:
            process_document(document_id, user_id, file_path, file_type)
        except Exception:
            # Already marked failed with a reason by process_document, and
            # already logged with a traceback there.
            return
        try:
            generate_summary(document_id, user_id)
        except Exception as exc:
            logger.warning('Summary generation failed for %s: %s', document_id, exc)

    threading.Thread(target=_run, daemon=True).start()


def broker_available() -> bool:
    """Will a Celery worker actually run a task dispatched right now?

    Note what this asks. Not "is there a broker" — "will the job get done". The
    two come apart in a way that matters: a Redis belonging to some other
    project on the same machine answers on 6379 just as readily as one this
    project owns, and dispatching into it with no worker attached means the
    document sits at "pending" for ever. Nothing raises, nothing retries, and
    the sweep that would eventually mark it failed is itself a Celery task that
    is not running either. A silent hang is a worse failure than the thread
    fallback this question exists to choose.

    Cached for a short time because this is on the upload path. Short enough
    that starting a worker is picked up without restarting Django.
    """
    from django.core.cache import cache

    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        # Eager mode runs tasks inline with no broker involved, which is what
        # the test settings use.
        return True

    cached = cache.get(_BROKER_CACHE_KEY)
    if cached is not None:
        return cached

    available = _probe_broker()
    cache.set(_BROKER_CACHE_KEY, available, _BROKER_CACHE_SECONDS)
    return available


def _probe_broker() -> bool:
    """Port open first, then a worker that answers. Both, or fall back.

    The socket check comes first because it is the cheap way to rule out the
    common case. A plain connect rather than ``connection.ensure_connection``:
    kombu does not apply its timeout to the initial TCP connect, so probing a
    broker that is simply not there took over four seconds — paid by the first
    upload after every restart, precisely the request that should feel fast.
    """
    import socket
    from urllib.parse import urlparse

    from django.conf import settings

    url = urlparse(getattr(settings, 'CELERY_BROKER_URL', '') or '')
    host = url.hostname or 'localhost'
    port = url.port or (6379 if url.scheme.startswith('redis') else 5672)

    try:
        with socket.create_connection((host, port), timeout=_BROKER_PROBE_TIMEOUT):
            pass
    except OSError as exc:
        logger.debug('Celery broker at %s:%s is not reachable: %s', host, port, exc)
        return False

    return _worker_listening(host, port)


def _worker_listening(host: str, port: int) -> bool:
    """Does any worker answer a ping on this broker?

    An open port only proves something is listening on it — not that it is this
    project's broker, and not that anything is consuming the queue. Redis in
    particular is shared infrastructure that other projects leave running, so
    "port 6379 answered" is weak evidence and dispatching on it alone is how a
    document ends up queued into a stranger's Redis, never processed.

    ``ping`` is a broadcast that only live workers reply to, which is exactly
    the question being asked. A broker that is present but unhealthy also
    produces no replies, and falling back to the thread is the right answer
    there too — the work gets done either way.
    """
    try:
        from config import celery_app
    except ImportError:
        return False

    if celery_app is None:
        # Celery is not installed — the trimmed production image does this.
        return False

    try:
        replies = celery_app.control.ping(timeout=_WORKER_PING_TIMEOUT)
    except Exception as exc:
        # Any transport-level problem means the same thing to the caller.
        logger.debug('Could not ping Celery workers on %s:%s: %s', host, port, exc)
        return False

    if not replies:
        logger.info(
            'A broker answers on %s:%s but no Celery worker replied, so a task '
            'dispatched now would never run. Processing in a thread instead — '
            'start a worker to use the queue.',
            host, port,
        )
        return False

    return True


def processing_status(user_id: int, document_ids: list[str]) -> list[dict[str, Any]]:
    """Status of several documents in one request.

    The upload screen polls while files are ingesting. Asking for each document
    separately means N requests every couple of seconds for a batch upload, so
    this answers for the whole batch at once and returns only the fields the
    poll actually renders — the summary and the full text are large and change
    rarely.
    """
    repository = get_document_repository()
    statuses = []

    for document_id in document_ids[:50]:
        document = repository.get(document_id, user_id)
        if document is None:
            # Deleted while the page was polling. Reported rather than omitted,
            # so the UI can stop asking instead of retrying forever.
            statuses.append({'id': document_id, 'status': 'missing'})
            continue

        statuses.append({
            'id': document['id'],
            'status': document['status'],
            'page_count': document.get('page_count', 0),
            'chunk_count': document.get('chunk_count', 0),
            'error_message': document.get('error_message', ''),
            'processing_duration_ms': document.get('processing_duration_ms'),
            'has_summary': bool((document.get('summary') or '').strip()),
        })

    return statuses


def reprocess_document(user_id: int, document_id: str) -> str:
    """Re-run ingestion for a document the user already owns."""
    repository = get_document_repository()
    document = repository.get(document_id, user_id)
    if document is None:
        raise DocumentError('Document not found.')

    repository.update(document_id, user_id,
                      status=STATUS_PENDING, error_message='')

    return queue_processing(
        document_id, user_id, document['file_path'], document['file_type'],
    )


# ══════════════════════════════════════════════════════════════════
# Rename and delete
# ══════════════════════════════════════════════════════════════════

def rename_document(user_id: int, document_id: str, new_name: str) -> dict[str, Any]:
    repository = get_document_repository()

    if repository.get(document_id, user_id) is None:
        raise DocumentError('Document not found.')

    updated = repository.update(document_id, user_id, original_filename=new_name)
    if updated is None:
        raise DocumentError('Document not found.')

    # Only the MongoDB backend has copies of the name to keep in step; the
    # PostgreSQL one reaches it through a foreign key and does nothing here.
    get_conversation_repository().rename_document_everywhere(
        user_id, document_id, new_name,
    )
    return updated


def delete_document(user_id: int, document_id: str) -> None:
    """Remove a document and everything derived from it.

    Order matters. The database row goes last, because it is the only record of
    where the file and the index are: deleting it first and then failing to
    remove the file leaves bytes on disk that nothing knows about.
    """
    repository = get_document_repository()
    document = repository.get(document_id, user_id)
    if document is None:
        raise DocumentError('Document not found.')

    _delete_vector_index(user_id, document)
    _delete_file(document.get('file_path', ''))

    repository.delete(document_id, user_id)
    logger.info('Document %s deleted by user %s', document_id, user_id)


def _delete_vector_index(user_id: int, document: dict[str, Any]) -> None:
    try:
        from rag.registry import get_vector_store

        # No backend check: pgvector keeps vectors on the chunk rows that the
        # cascade removes, so its delete is a no-op by design.
        get_vector_store().delete(user_id, document['id'])
    except Exception as exc:
        # A stale index file is a leak, not a correctness problem — the document
        # is gone either way — so this is logged rather than raised.
        logger.warning('Could not delete the vector index for %s: %s',
                       document['id'], exc)


def _delete_file(file_path: str) -> None:
    if not file_path:
        return
    path = Path(file_path)
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as exc:
        logger.warning('Could not delete %s: %s', file_path, exc)


def regenerate_summary(user_id: int, document_id: str) -> None:
    """Rebuild a completed document's AI summary in the background.

    The document must have finished processing: a summary of a file whose text
    was never extracted would be a summary of nothing, and re-extracting here
    would duplicate the ingestion pipeline.
    """
    import threading

    from core.constants import STATUS_COMPLETED

    repository = get_document_repository()
    document = repository.get(document_id, user_id)
    if document is None:
        raise DocumentError('Document not found.')

    if document.get('status') != STATUS_COMPLETED:
        raise DocumentError('Document has not finished processing yet.')

    if broker_available():
        from apps.documents.tasks import generate_summary_task

        generate_summary_task.delay(document_id, user_id)
        return

    def _regenerate() -> None:
        from rag.ingestion.pipeline import generate_summary

        try:
            generate_summary(document_id, user_id)
        except Exception as exc:
            logger.error('Summary regeneration failed for %s: %s',
                         document_id, exc, exc_info=True)

    threading.Thread(target=_regenerate, daemon=True).start()


# ══════════════════════════════════════════════════════════════════
# Retrieval glue
# ══════════════════════════════════════════════════════════════════
#
# The RAG package has no idea what a Document record is, and should not: it
# searches "index keys" for a user. Turning stored documents into those keys is
# this layer's job, and it lives here — with the documents — rather than in
# chat, because the evaluation harness and the test_rag command need it without
# there being a conversation anywhere.

def resolve_index_keys(user_id: int, document_ids: list[str]) -> list[str]:
    """Document ids -> the keys their vectors are stored under.

    A document migrated out of MongoDB keeps its old id as the name of its
    FAISS index file, so retrieval has to ask for that rather than the new
    UUID. Documents that never finished processing are dropped: searching them
    finds nothing, and including them would make a partial corpus look like a
    retrieval failure.
    """
    documents = get_document_repository().list_completed(user_id, document_ids)
    if not documents:
        logger.info('No completed documents to search for user %s', user_id)
        return []
    return [d.get('legacy_mongo_id') or d['id'] for d in documents]


def retrieve_relevant_chunks(user_id: int, document_ids: list[str],
                             query: str) -> list[dict[str, Any]]:
    """Passages most relevant to `query`, best first.

    Returns dicts rather than Documents because the callers — the evaluation
    harness and `manage.py test_rag` — score what comes back rather than
    feeding it onward.
    """
    from rag.retrievers.vector import VectorRetriever
    from rag.types import documents_to_chunks

    index_keys = resolve_index_keys(user_id, document_ids)
    if not index_keys:
        return []

    documents = VectorRetriever(user_id=user_id, document_keys=index_keys).invoke(query)
    logger.info('Retrieved %d passage(s) for: %s', len(documents), query[:60])
    return documents_to_chunks(documents)
