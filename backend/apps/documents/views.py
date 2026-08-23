"""Document endpoints.

HTTP only: parse the request, call a service, shape the response. Every rule
about what may be uploaded, what counts as a duplicate and what deleting a
document has to clean up lives in apps/documents/services.py, where it can be
tested without a request.
"""
import logging

from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import APIResponse
from core.utils import format_file_size
from repositories.factory import get_document_repository

from . import services as document_service
from .serializers import RenameDocumentSerializer
from .services import DocumentError

logger = logging.getLogger(__name__)


def _present(document: dict) -> dict:
    """Add the display-only fields the API has always included."""
    return {**document, 'file_size_display': format_file_size(document.get('file_size', 0))}


class DocumentListUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    # Uploads are the most expensive unauthenticated-cost endpoint: each one
    # writes to disk and starts embedding work.
    throttle_scope = 'upload'

    def get(self, request):
        """List the authenticated user's documents, newest first."""
        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = min(int(request.query_params.get('page_size', 20)), 100)

        result = get_document_repository().list_for_user(
            request.user.id, page=page, page_size=page_size,
        )
        return APIResponse.paginated(
            data=[_present(d) for d in result['items']],
            total=result['total'],
            page=page,
            page_size=page_size,
            message='Documents retrieved.',
        )

    def post(self, request):
        """Upload one or more documents and queue them for processing."""
        try:
            outcome = document_service.upload_documents(
                request.user.id, request.FILES.getlist('files'),
            )
        except DocumentError as exc:
            return APIResponse.error(str(exc))

        if not outcome.any_created:
            return APIResponse.error('No documents were uploaded.', outcome.errors)

        data = {'uploaded': [_present(d) for d in outcome.created]}
        if outcome.errors:
            # Partial success: the accepted files are reported alongside the
            # reason each rejected one was refused, so the user can tell which
            # of five files was the problem.
            data['errors'] = outcome.errors

        return APIResponse.created(
            data=data,
            message=f'{len(outcome.created)} document(s) queued for processing.',
        )


class DocumentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        document = get_document_repository().get(document_id, request.user.id)
        if document is None:
            return APIResponse.not_found('Document not found.')
        return APIResponse.success(data=_present(document))

    def patch(self, request, document_id):
        """Rename a document. The file, its hash, chunks and index are untouched."""
        serializer = RenameDocumentSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        try:
            document = document_service.rename_document(
                request.user.id, document_id,
                serializer.validated_data['original_filename'],
            )
        except DocumentError as exc:
            return APIResponse.not_found(str(exc))

        return APIResponse.success(data=_present(document), message='Document renamed.')

    def delete(self, request, document_id):
        try:
            document_service.delete_document(request.user.id, document_id)
        except DocumentError as exc:
            return APIResponse.not_found(str(exc))
        return APIResponse.success(message='Document deleted successfully.')


class DocumentStatusView(APIView):
    """Batch status poll for documents being processed.

    GET /api/documents/status/?ids=<id>,<id>

    Deliberately not throttled by the upload scope: this is the endpoint the UI
    calls every couple of seconds while a batch ingests, and rate-limiting it
    would make the progress display stall rather than protecting anything — it
    is a cheap read of rows the caller already owns.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get('ids', '')
        ids = [i.strip() for i in raw.split(',') if i.strip()]
        if not ids:
            return APIResponse.error('Pass ?ids=<comma-separated document ids>.')

        return APIResponse.success(
            data=document_service.processing_status(request.user.id, ids)
        )


class DocumentReprocessView(APIView):
    """Re-run ingestion for a document, e.g. after a failure."""

    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload'

    def post(self, request, document_id):
        try:
            task_id = document_service.reprocess_document(request.user.id, document_id)
        except DocumentError as exc:
            return APIResponse.not_found(str(exc))

        return APIResponse.success(
            data={'document_id': document_id, 'task_id': task_id},
            message='Document queued for reprocessing.',
        )


class DocumentSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        document = get_document_repository().get(document_id, request.user.id)
        if document is None:
            return APIResponse.not_found('Document not found.')

        return APIResponse.success(data={
            'document_id': document_id,
            'filename': document.get('original_filename', ''),
            'status': document.get('status', ''),
            'summary': document.get('summary', ''),
        })

    def post(self, request, document_id):
        """Regenerate the summary of a document that finished processing."""
        try:
            document_service.regenerate_summary(request.user.id, document_id)
        except DocumentError as exc:
            return APIResponse.error(str(exc))
        return APIResponse.success(message='Summary regeneration started.')
