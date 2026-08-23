"""Document ingestion — what happens after a file is uploaded.

    file -> extract text (per page)
         -> split into overlapping chunks
         -> embed each chunk
         -> store chunks and vectors

Runs on a Celery worker (see apps/documents/tasks.py), so nothing here may
assume a request, a user session, or that it is the only copy running.

**Idempotent by construction.** A worker killed mid-document has its task
redelivered, so this must be safe to re-run: existing chunks and the vector
index are dropped before new ones are written, never appended to. Running it
twice produces the same result as running it once, which is the property that
makes ``acks_late`` safe.

ML imports stay inside the functions so the module can be imported — by the
web process, by a test, by ``manage.py`` — without loading numpy, FAISS or a
tokenizer.
"""
import logging
import time
from typing import Any, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# The placeholder text_extractor leaves for a page it could not read.
OCR_PLACEHOLDER_PREFIX = '[Page '


class ProcessingError(Exception):
    """Ingestion failed for a reason worth showing the user."""


def _repository():
    from repositories.factory import get_document_repository

    return get_document_repository()


def _mark(document_id: str, user_id: int, **fields: Any) -> None:
    _repository().update(document_id, user_id, **fields)


def process_document(document_id: str, user_id: int, file_path: str,
                     file_type: str) -> dict[str, Any]:
    """Extract, chunk, embed and index one uploaded document.

    Returns a small summary of what was produced, which the task records.
    Raises on failure after marking the document failed, so Celery sees the
    error and can retry.
    """
    from core.constants import STATUS_COMPLETED, STATUS_FAILED, STATUS_PROCESSING
    from rag.ingestion.chunker import chunk_pages
    from rag.ingestion.extract import extract_text, get_word_count
    from rag.registry import get_embeddings

    repository = _repository()
    started = time.perf_counter()

    document = repository.get(document_id, user_id)
    if document is None:
        # The document was deleted between the upload and the worker picking
        # the job up. Not an error worth retrying — there is nothing to process.
        logger.warning('Document %s no longer exists; skipping.', document_id)
        return {'skipped': 'document no longer exists'}

    filename = document.get('original_filename', '')

    try:
        _mark(document_id, user_id,
              status=STATUS_PROCESSING,
              processing_started_at=timezone.now(),
              error_message='')

        # Anything left from a previous run of this same document. Dropping
        # first is what makes a redelivered task produce one set of chunks
        # rather than two.
        repository.delete_chunks(document_id, user_id)
        _delete_vector_index(user_id, document)

        # --- 1. Text, one entry per page ---
        pages = extract_text(file_path, file_type)
        if not pages:
            raise ProcessingError(
                'No text could be extracted from this document. The file may be '
                'corrupted, empty, or in an unsupported format.'
            )

        # OCR leaves a placeholder for pages it could not read. Those carry no
        # meaning, so they are kept out of the index — unless they are all there
        # is, in which case the document is kept anyway rather than failing an
        # upload the user watched succeed.
        readable = [p for p in pages if not p['content'].startswith(OCR_PLACEHOLDER_PREFIX)]
        if not readable:
            logger.warning('%s: no readable text found — indexing placeholders.', filename)
            readable = pages

        # --- 2. Chunks ---
        chunks = chunk_pages(readable)
        if not chunks:
            raise ProcessingError('Chunking produced no results.')

        logger.info('%s: %d chunks, embedding…', filename or document_id, len(chunks))

        # --- 3. Vectors ---
        embeddings = get_embeddings().embed_documents([c['content'] for c in chunks])
        logger.info('%s: embedded %d chunks, storing…', filename or document_id, len(chunks))

        # --- 4. Store ---
        for chunk, vector in zip(chunks, embeddings, strict=True):
            chunk['embedding'] = vector
            chunk['filename'] = filename

        chunk_ids = repository.replace_chunks(document_id, user_id, chunks)
        _save_vector_index(user_id, document, embeddings, chunk_ids)

        # --- 5. Ready to chat with ---
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        word_count = get_word_count(readable)

        _mark(
            document_id, user_id,
            status=STATUS_COMPLETED,
            page_count=len(pages),
            word_count=word_count,
            chunk_count=len(chunks),
            vector_count=len(chunk_ids),
            processing_completed_at=timezone.now(),
            processing_duration_ms=elapsed_ms,
            error_message='',
        )
        logger.info(
            'Indexed %s in %.1fs: %d pages, %d chunks, %d words',
            filename or document_id, elapsed_ms / 1000,
            len(pages), len(chunks), word_count,
        )

        return {
            'document_id': document_id,
            'pages': len(pages),
            'chunks': len(chunks),
            'words': word_count,
            'duration_ms': elapsed_ms,
        }

    except Exception as exc:
        logger.error('Processing failed for %s: %s', document_id, exc, exc_info=True)
        _mark(
            document_id, user_id,
            status=STATUS_FAILED,
            error_message=str(exc)[:2000],
            processing_completed_at=timezone.now(),
            processing_duration_ms=round((time.perf_counter() - started) * 1000),
        )
        raise


def generate_summary(document_id: str, user_id: int) -> Optional[str]:
    """Produce and store the document's AI summary.

    Separate from ingestion on purpose. It is a blocking LLM call that the user
    does not have to wait for — the document is chat-ready without it — and it
    fails for entirely different reasons (rate limits, a retired model) than
    text extraction does. Keeping it apart means a summary failure cannot mark
    a perfectly indexed document as failed, and it can be retried on its own.
    """
    from rag.chains.summarize import generate_document_summary
    from rag.ingestion.extract import extract_text

    repository = _repository()
    document = repository.get(document_id, user_id)
    if document is None:
        return None

    try:
        pages = extract_text(document['file_path'], document['file_type'])
        summary = generate_document_summary(pages)
    except Exception as exc:
        logger.warning('Summary generation failed for %s: %s', document_id, exc)
        raise

    repository.update(document_id, user_id, summary=summary)
    return summary


# ══════════════════════════════════════════════════════════════════
# Vector index
# ══════════════════════════════════════════════════════════════════

def _index_key(document: dict[str, Any]) -> str:
    """The name this document's FAISS index is stored under."""
    return document.get('legacy_mongo_id') or document['id']


def _save_vector_index(user_id: int, document: dict[str, Any],
                       embeddings, chunk_ids: list[str]) -> None:
    """Hand the vectors to whichever store is configured.

    There is no ``if backend == 'faiss'`` here any more: pgvector keeps each
    vector on the chunk row that ``replace_chunks`` has already written, so its
    ``add`` is a no-op by design. Asking the store to do the right thing beats
    asking a setting which store is in use — the branch was one more place to
    update when a third backend arrives.
    """
    from rag.registry import get_vector_store

    get_vector_store().add(user_id, _index_key(document), embeddings, chunk_ids)


def _delete_vector_index(user_id: int, document: dict[str, Any]) -> None:
    from rag.registry import get_vector_store

    get_vector_store().delete(user_id, _index_key(document))
