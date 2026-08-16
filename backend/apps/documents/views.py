import logging
import threading
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from core.mongo import documents_col, chunks_col
from core.responses import APIResponse
from core.utils import (
    generate_unique_filename, compute_file_hash, get_file_extension,
    get_user_upload_dir, serialize_mongo_doc, format_file_size
)
from core.constants import STATUS_PENDING, EVENT_UPLOAD
from services.document_processor import process_document
from .serializers import RenameDocumentSerializer

logger = logging.getLogger(__name__)


def _serialize_doc(doc: dict) -> dict:
    d = serialize_mongo_doc(doc)
    d['id'] = d.pop('_id', '')
    d['file_size_display'] = format_file_size(d.get('file_size', 0))
    return d


class DocumentListUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        """List all documents for the authenticated user."""
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        total = documents_col().count_documents({'user_id': request.user.id})
        docs = list(
            documents_col()
            .find({'user_id': request.user.id})
            .sort('created_at', -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )

        return APIResponse.paginated(
            data=[_serialize_doc(d) for d in docs],
            total=total,
            page=page,
            page_size=page_size,
            message='Documents retrieved.',
        )

    def post(self, request):
        """Upload one or more documents and kick off processing in background threads."""
        files = request.FILES.getlist('files')
        if not files:
            return APIResponse.error('No files provided.')

        from django.conf import settings
        allowed_exts = settings.ALLOWED_DOCUMENT_EXTENSIONS
        limit_mb = settings.MAX_DOCUMENT_SIZE_MB

        created_docs = []
        errors = []

        for f in files:
            ext = get_file_extension(f.name)
            if ext not in allowed_exts:
                errors.append(f"{f.name}: unsupported type. Allowed: {', '.join(allowed_exts)}.")
                continue
            if f.size > limit_mb * 1024 * 1024:
                errors.append(f"{f.name}: exceeds the {limit_mb} MB limit for .{ext} files.")
                continue

            file_hash = compute_file_hash(f)

            # Check for duplicate
            existing = documents_col().find_one({'user_id': request.user.id, 'file_hash': file_hash})
            if existing:
                errors.append(f"{f.name}: already uploaded.")
                continue

            unique_name = generate_unique_filename(f.name)
            upload_dir = get_user_upload_dir(request.user.id)
            save_path = upload_dir / unique_name

            # Save file to disk
            with open(save_path, 'wb') as dest:
                for chunk in f.chunks():
                    dest.write(chunk)

            now = timezone.now()
            doc = {
                'user_id':           request.user.id,
                'filename':          unique_name,
                'original_filename': f.name,
                'file_type':         ext,
                'file_size':         f.size,
                'file_hash':         file_hash,
                'file_path':         str(save_path),
                'status':            STATUS_PENDING,
                'page_count':        0,
                'word_count':        0,
                'chunk_count':       0,
                'summary':           '',
                'error_message':     '',
                'created_at':        now,
                'updated_at':        now,
            }

            result = documents_col().insert_one(doc)
            document_id = str(result.inserted_id)
            doc['_id'] = document_id

            # Log analytics
            try:
                from core.mongo import analytics_col
                analytics_col().insert_one({
                    'user_id':    request.user.id,
                    'event_type': EVENT_UPLOAD,
                    'metadata':   {'document_id': document_id, 'filename': f.name, 'file_type': ext},
                    'created_at': now,
                })
            except Exception:
                pass

            # Process in background thread
            thread = threading.Thread(
                target=process_document,
                args=(document_id, request.user.id, str(save_path), ext),
                daemon=True,
            )
            thread.start()

            created_docs.append(_serialize_doc(doc))

        response_data = {'uploaded': created_docs}
        if errors:
            response_data['errors'] = errors

        if not created_docs:
            return APIResponse.error('No documents were uploaded.', errors)

        return APIResponse.created(data=response_data, message=f'{len(created_docs)} document(s) queued for processing.')


class DocumentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_document(self, document_id: str, user_id: int):
        try:
            doc = documents_col().find_one({'_id': ObjectId(document_id), 'user_id': user_id})
        except InvalidId:
            return None
        return doc

    def get(self, request, document_id):
        doc = self._get_document(document_id, request.user.id)
        if not doc:
            return APIResponse.not_found('Document not found.')
        return APIResponse.success(data=_serialize_doc(doc))

    def patch(self, request, document_id):
        """Rename a document. Only the display name changes — the file on disk,
        its hash, chunks and FAISS index are all untouched."""
        doc = self._get_document(document_id, request.user.id)
        if not doc:
            return APIResponse.not_found('Document not found.')

        serializer = RenameDocumentSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        new_name = serializer.validated_data['original_filename']
        documents_col().update_one(
            {'_id': ObjectId(document_id)},
            {'$set': {'original_filename': new_name, 'updated_at': timezone.now()}},
        )
        # Chunks carry a denormalised copy of the filename; keep it in step so
        # citations don't keep quoting the old name.
        chunks_col().update_many(
            {'document_id': document_id, 'user_id': request.user.id},
            {'$set': {'filename': new_name}},
        )
        # Chat sessions cache the names of the documents they're grounded in.
        old_name = doc.get('original_filename', '')
        if old_name and old_name != new_name:
            from core.mongo import chat_sessions_col
            for s in chat_sessions_col().find(
                {'user_id': request.user.id, 'document_ids': document_id},
                {'document_ids': 1, 'document_names': 1},
            ):
                names = list(s.get('document_names') or [])
                ids   = list(s.get('document_ids') or [])
                if document_id in ids and len(names) == len(ids):
                    names[ids.index(document_id)] = new_name
                    chat_sessions_col().update_one(
                        {'_id': s['_id']}, {'$set': {'document_names': names}},
                    )

        updated = documents_col().find_one({'_id': ObjectId(document_id)})
        return APIResponse.success(data=_serialize_doc(updated), message='Document renamed.')

    def delete(self, request, document_id):
        doc = self._get_document(document_id, request.user.id)
        if not doc:
            return APIResponse.not_found('Document not found.')

        # Delete FAISS index
        try:
            from services.faiss_store import delete_index
            delete_index(request.user.id, document_id)
        except Exception as exc:
            logger.warning("FAISS deletion warning: %s", exc)

        # Delete file from disk
        file_path = doc.get('file_path', '')
        if file_path and Path(file_path).exists():
            try:
                Path(file_path).unlink()
            except Exception as exc:
                logger.warning("File deletion warning: %s", exc)

        # Delete chunks
        chunks_col().delete_many({'document_id': document_id})

        # Delete document
        documents_col().delete_one({'_id': ObjectId(document_id)})

        logger.info("Document %s deleted by user %s", document_id, request.user.id)
        return APIResponse.success(message='Document deleted successfully.')


class DocumentSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        try:
            doc = documents_col().find_one(
                {'_id': ObjectId(document_id), 'user_id': request.user.id},
                {'summary': 1, 'status': 1, 'original_filename': 1}
            )
        except InvalidId:
            return APIResponse.not_found('Document not found.')

        if not doc:
            return APIResponse.not_found('Document not found.')

        return APIResponse.success(data={
            'document_id':   document_id,
            'filename':      doc.get('original_filename', ''),
            'status':        doc.get('status', ''),
            'summary':       doc.get('summary', ''),
        })

    def post(self, request, document_id):
        """Regenerate summary for a completed document."""
        try:
            doc = documents_col().find_one(
                {'_id': ObjectId(document_id), 'user_id': request.user.id}
            )
        except InvalidId:
            return APIResponse.not_found('Document not found.')

        if not doc:
            return APIResponse.not_found('Document not found.')

        if doc.get('status') != 'completed':
            return APIResponse.error('Document has not finished processing yet.')

        def _regen():
            from services.text_extractor import extract_text
            from services.llm import generate_document_summary
            try:
                pages = extract_text(doc['file_path'], doc['file_type'])
                summary = generate_document_summary(pages)
                documents_col().update_one(
                    {'_id': ObjectId(document_id)},
                    {'$set': {'summary': summary, 'updated_at': timezone.now()}},
                )
            except Exception as exc:
                logger.error("Summary regen failed: %s", exc)

        threading.Thread(target=_regen, daemon=True).start()
        return APIResponse.success(message='Summary regeneration started.')
