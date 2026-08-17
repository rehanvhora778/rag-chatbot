"""
Module 7: Document Processing — what happens after a file is uploaded.

    file -> extract text (per page)
         -> split into overlapping chunks
         -> embed each chunk into a 384-d vector
         -> save chunks to MongoDB + vectors to a FAISS index

Runs in a background thread, so the upload request returns immediately and the
UI polls the document's status. ML imports are done inside the function so the
server can start even before the heavy packages are loaded.
"""
import logging
import time

from bson import ObjectId
from django.utils import timezone

logger = logging.getLogger(__name__)


def _mark(document_id: ObjectId, **fields) -> None:
    """Update a document record, always refreshing `updated_at`."""
    from core.mongo import documents_col

    documents_col().update_one(
        {'_id': document_id},
        {'$set': {**fields, 'updated_at': timezone.now()}},
    )


def _add_summary(document_id: ObjectId, pages: list) -> None:
    """Generate the AI summary and store it.

    Deliberately runs *after* the document is marked completed: it is a blocking
    LLM call, and the user should be able to start chatting without waiting for
    it. Fully guarded so a summary failure can never fail an indexed document.
    """
    from services.llm import generate_document_summary

    try:
        summary = generate_document_summary(pages)
    except Exception as exc:
        logger.warning("Summary generation failed: %s", exc)
        summary = "Summary could not be generated."

    try:
        _mark(document_id, summary=summary)
    except Exception as exc:
        logger.warning("Could not store the summary: %s", exc)


def process_document(document_id: str, user_id: int, file_path: str, file_type: str) -> None:
    """Extract -> chunk -> embed -> index one uploaded document.

    Safe to re-run: existing chunks and the FAISS index are dropped first, so
    the embeddings are always rebuilt fresh rather than duplicated.
    """
    from core.mongo import documents_col, chunks_col
    from core.constants import STATUS_PROCESSING, STATUS_COMPLETED, STATUS_FAILED
    from services.text_extractor import extract_text, get_word_count
    from services.chunker import chunk_pages
    from services.embeddings import embed_chunks
    from services.faiss_store import save_index, delete_index

    doc_oid = ObjectId(document_id)
    started = time.perf_counter()

    try:
        doc = documents_col().find_one({'_id': doc_oid}, {'original_filename': 1})
        filename = (doc or {}).get('original_filename', '')
        _mark(doc_oid, status=STATUS_PROCESSING)

        # Clear anything left from a previous run of this same document.
        chunks_col().delete_many({'document_id': document_id})
        delete_index(user_id, document_id)

        # --- 1. Text, one entry per page ---
        pages = extract_text(file_path, file_type)
        if not pages:
            raise ValueError(
                "No text could be extracted from this document. "
                "The file may be corrupted, empty, or in an unsupported format."
            )

        # OCR leaves a "[Page 4: Image-based content...]" placeholder for pages it
        # could not read. Those carry no meaning, so they are excluded from the
        # index — unless that is all we have, in which case the document is kept
        # anyway rather than failing the upload outright.
        real_pages = [p for p in pages if not p['content'].startswith('[Page ')]
        if not real_pages:
            logger.warning("%s: no readable text found — indexing placeholders.", filename)
            real_pages = pages

        # --- 2. Chunks ---
        chunks = chunk_pages(real_pages)
        if not chunks:
            raise ValueError("Chunking produced no results.")

        logger.info("%s: %d chunks, embedding…", filename or document_id, len(chunks))

        # --- 3. Vectors ---
        embeddings = embed_chunks(chunks)
        logger.info("%s: embedded %d chunks, indexing…", filename or document_id, len(chunks))

        # --- 4. Store: chunk text in MongoDB, vectors in FAISS ---
        # Each chunk keeps its page_number — that is what lets an answer cite
        # "(Page 12)" later on.
        now = timezone.now()
        inserted = chunks_col().insert_many([
            {
                'document_id': document_id,
                'user_id':     user_id,
                'filename':    filename,
                'content':     chunk['content'],
                'chunk_index': chunk['chunk_index'],
                'page_number': chunk['page_number'],
                'start_char':  chunk['start_char'],
                'end_char':    chunk['end_char'],
                'word_count':  chunk['word_count'],
                'created_at':  now,
            }
            for chunk in chunks
        ])
        chunk_ids = [str(oid) for oid in inserted.inserted_ids]
        save_index(user_id, document_id, embeddings, chunk_ids)

        # --- 5. Ready to chat with ---
        word_count = get_word_count(real_pages)
        _mark(
            doc_oid,
            status=STATUS_COMPLETED,
            page_count=len(pages),
            word_count=word_count,
            chunk_count=len(chunks),
            vector_count=len(chunk_ids),
            summary='Generating summary…',
            error_message='',
        )
        logger.info(
            "Indexed %s in %.1fs: %d pages, %d chunks, %d words",
            filename or document_id, time.perf_counter() - started,
            len(pages), len(chunks), word_count,
        )

        _add_summary(doc_oid, real_pages)

    except Exception as exc:
        logger.error("Processing failed for %s: %s", document_id, exc, exc_info=True)
        _mark(doc_oid, status=STATUS_FAILED, error_message=str(exc))
        raise
