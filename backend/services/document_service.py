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

    Extension and size only, as before. Content sniffing (`filetype` is already
    a dependency) belongs with the rest of the upload hardening in the security
    phase — checking it here now, with nothing testing it, would be a claim the
    project cannot back up.
    """
    extension = get_file_extension(uploaded_file.name)
    allowed = settings.ALLOWED_DOCUMENT_EXTENSIONS

    if extension not in allowed:
        return (f'{uploaded_file.name}: unsupported type. '
                f'Allowed: {", ".join(allowed)}.')

    limit_mb = settings.MAX_DOCUMENT_SIZE_MB
    if uploaded_file.size > limit_mb * 1024 * 1024:
        return f'{uploaded_file.name}: exceeds the {limit_mb} MB limit.'

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
                     file_type: str) -> None:
    """Hand a document to whatever runs ingestion.

    Still a background thread, exactly as before. This function exists so that
    Phase 4 replaces one call with a Celery ``.delay()`` instead of editing a
    view, and so that a test can assert a document was queued without running
    the pipeline.
    """
    import threading

    from services.document_processor import process_document

    thread = threading.Thread(
        target=process_document,
        args=(document_id, user_id, file_path, file_type),
        daemon=True,
    )
    thread.start()
    logger.info('Queued document %s for processing', document_id)


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
    if settings.VECTOR_BACKEND != 'faiss':
        # pgvector stores vectors on the chunk rows, which the cascade removes.
        return
    try:
        from services.faiss_store import delete_index

        delete_index(user_id, document['id'])
    except Exception as exc:
        # A stale index file is a leak, not a correctness problem — the document
        # is gone either way — so this is logged rather than raised.
        logger.warning('Could not delete the FAISS index for %s: %s',
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

    def _regenerate() -> None:
        from services.llm import generate_document_summary
        from services.text_extractor import extract_text

        try:
            pages = extract_text(document['file_path'], document['file_type'])
            summary = generate_document_summary(pages)
            repository.update(document_id, user_id, summary=summary)
        except Exception as exc:
            logger.error('Summary regeneration failed for %s: %s',
                         document_id, exc, exc_info=True)

    threading.Thread(target=_regenerate, daemon=True).start()
