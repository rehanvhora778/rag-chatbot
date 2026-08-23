"""Chat endpoints.

HTTP only. Retrieval, generation, storage and analytics live in
apps/chat/services.py, which is the seam onto the RAG engine in rag/.
"""
import logging

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import APIResponse

from . import services as chat_service
from .serializers import (
    CreateSessionSerializer,
    FeedbackSerializer,
    SendMessageSerializer,
    UpdateSessionSerializer,
)
from .services import ChatError, ConversationNotFound
from .streaming import stream_response

logger = logging.getLogger(__name__)


def _pagination(request) -> tuple[int, int]:
    page = max(int(request.query_params.get('page', 1)), 1)
    # Capped: page_size is client-supplied, and an uncapped one is a request to
    # serialise the entire table.
    page_size = min(int(request.query_params.get('page_size', 20)), 100)
    return page, page_size


class ChatSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page, page_size = _pagination(request)
        result = chat_service.list_conversations(request.user.id, page, page_size)
        return APIResponse.paginated(
            data=result['items'], total=result['total'],
            page=page, page_size=page_size,
        )

    def post(self, request):
        serializer = CreateSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        try:
            conversation = chat_service.create_conversation(
                request.user.id,
                serializer.validated_data['title'],
                serializer.validated_data['document_ids'],
            )
        except ChatError as exc:
            return APIResponse.error(str(exc))

        return APIResponse.created(data=conversation, message='Chat session created.')


class ChatSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            return APIResponse.success(
                data=chat_service.get_transcript(request.user.id, session_id)
            )
        except ConversationNotFound as exc:
            return APIResponse.not_found(str(exc))

    def patch(self, request, session_id):
        serializer = UpdateSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        try:
            conversation = chat_service.update_conversation(
                request.user.id, session_id, **serializer.validated_data,
            )
        except ConversationNotFound as exc:
            return APIResponse.not_found(str(exc))
        except ChatError as exc:
            return APIResponse.error(str(exc))

        return APIResponse.success(data=conversation, message='Session updated.')

    def delete(self, request, session_id):
        try:
            chat_service.delete_conversation(request.user.id, session_id)
        except ConversationNotFound as exc:
            return APIResponse.not_found(str(exc))
        return APIResponse.success(message='Session deleted.')


class SendMessageView(APIView):
    permission_classes = [IsAuthenticated]
    # Per-user rate limit on the expensive RAG endpoint (CHAT_THROTTLE_RATE).
    # Shields the shared LLM key from bursts; returns 429 when exceeded.
    throttle_scope = 'chat'

    def post(self, request, session_id):
        """The main RAG endpoint: question in, grounded answer with citations out."""
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        try:
            result = chat_service.send_message(
                user_id=request.user.id,
                conversation_id=session_id,
                question=serializer.validated_data['question'],
                debug=request.query_params.get('debug') == 'true',
            )
        except ConversationNotFound as exc:
            return APIResponse.not_found(str(exc))
        except ChatError as exc:
            return APIResponse.error(str(exc))
        except Exception as exc:
            # The provider is down, out of quota, or returned something
            # unusable. The detail is logged; the user gets a message they can
            # act on rather than a stack trace.
            logger.error('RAG query failed for session %s: %s',
                         session_id, exc, exc_info=True)
            return APIResponse.server_error(
                'Failed to generate response. Please try again.'
            )

        return APIResponse.success(data=result, message='Response generated.')


class ChatConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """What the RAG engine is running — read-only, for the Settings page.

        Reported rather than offered as a choice: these are server-side
        constants that apply to every conversation, and reading them from the
        service means the page cannot drift out of step with the pipeline.
        """
        return APIResponse.success(data=chat_service.get_engine_config())


class ChatSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page, page_size = _pagination(request)
        try:
            result = chat_service.search_conversations(
                request.user.id, request.query_params.get('q', ''), page, page_size,
            )
        except ChatError as exc:
            return APIResponse.error(str(exc))

        return APIResponse.paginated(
            data=result['items'], total=result['total'],
            page=page, page_size=page_size,
            message=f'{result["total"]} sessions found.',
        )


class ExportChatPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            pdf_bytes, filename = chat_service.export_conversation_pdf(
                request.user.id, session_id,
            )
        except ConversationNotFound as exc:
            return APIResponse.not_found(str(exc))

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ChatStreamView(APIView):
    """Streamed RAG answers over Server-Sent Events.

    POST /api/chat/sessions/<id>/stream/

    Everything that can be validated is validated before the generator starts:
    once a streamed response has begun, the status code is already sent and a
    404 or 400 can no longer be returned.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = 'chat'

    def post(self, request, session_id):
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        try:
            generator = chat_service.stream_message(
                user_id=request.user.id,
                conversation_id=session_id,
                question=serializer.validated_data['question'],
            )
        except ConversationNotFound as exc:
            return APIResponse.not_found(str(exc))
        except ChatError as exc:
            return APIResponse.error(str(exc))

        return stream_response(generator)


class MessageFeedbackView(APIView):
    """Thumbs up or down on one answer.

    POST /api/chat/messages/<id>/feedback/   record or change a verdict
    GET  /api/chat/messages/<id>/feedback/   this user's existing verdict
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, message_id):
        return APIResponse.success(
            data=chat_service.get_feedback(request.user.id, message_id)
        )

    def post(self, request, message_id):
        serializer = FeedbackSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        try:
            record = chat_service.submit_feedback(
                request.user.id, message_id, **serializer.validated_data,
            )
        except ConversationNotFound as exc:
            return APIResponse.not_found(str(exc))
        except ChatError as exc:
            return APIResponse.error(str(exc))

        return APIResponse.success(data=record, message='Thanks for the feedback.')
