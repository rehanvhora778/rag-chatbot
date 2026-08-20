"""
Re-run the extraction -> chunk -> embed -> index pipeline for documents that
were processed with the old chunker, so they benefit from the improved
character-based chunking and MMR retrieval.

Usage:
    python manage.py reprocess_documents                 # all documents
    python manage.py reprocess_documents --user 5        # one user's documents
    python manage.py reprocess_documents --document <id> # a single document
    python manage.py reprocess_documents --dry-run       # list, don't process

Reprocessing is idempotent: process_document() deletes the document's existing
chunks and FAISS index before rebuilding, so nothing is duplicated.
"""
from pathlib import Path

from bson import ObjectId
from django.core.management.base import BaseCommand, CommandError

from core.mongo import documents_col
from services.document_processor import process_document


class Command(BaseCommand):
    help = "Re-chunk, re-embed, and rebuild the FAISS index for existing documents."

    def add_arguments(self, parser):
        parser.add_argument('--user', type=int, default=None,
                            help='Only reprocess documents owned by this user id.')
        parser.add_argument('--document', type=str, default=None,
                            help='Only reprocess this single document id.')
        parser.add_argument('--dry-run', action='store_true',
                            help='List the documents that would be reprocessed, then exit.')

    def handle(self, *args, **opts):
        query = {}
        if opts['document']:
            try:
                query['_id'] = ObjectId(opts['document'])
            except Exception as exc:
                raise CommandError(f"Invalid document id: {opts['document']}") from exc
        if opts['user'] is not None:
            query['user_id'] = opts['user']

        docs = list(documents_col().find(query))
        if not docs:
            self.stdout.write(self.style.WARNING("No matching documents found."))
            return

        self.stdout.write(f"Found {len(docs)} document(s) to reprocess.\n")

        ok = skipped = failed = 0
        for doc in docs:
            doc_id    = str(doc['_id'])
            user_id   = doc.get('user_id')
            file_path = doc.get('file_path', '')
            file_type = doc.get('file_type', '')
            name      = doc.get('original_filename', doc_id)

            if not file_path or not Path(file_path).exists():
                self.stdout.write(self.style.WARNING(
                    f"  SKIP  {name}: source file missing ({file_path})"))
                skipped += 1
                continue

            if opts['dry_run']:
                self.stdout.write(f"  WOULD REPROCESS  {name}  ({doc_id})")
                continue

            self.stdout.write(f"  Reprocessing {name} ...", ending=' ')
            try:
                process_document(doc_id, user_id, file_path, file_type)
                self.stdout.write(self.style.SUCCESS("done"))
                ok += 1
            except Exception as exc:  # keep going on individual failures
                self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))
                failed += 1

        if not opts['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f"\nReprocessed: {ok}  |  Skipped: {skipped}  |  Failed: {failed}"))
