import logging
from django.http import HttpResponse
from django.utils import timezone
from bson import ObjectId
from bson.errors import InvalidId
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.mongo import chat_sessions_col, messages_col, documents_col, analytics_col
from core.responses import APIResponse
from core.utils import serialize_mongo_doc
from core.constants import SESSION_ACTIVE, SESSION_ARCHIVED, EVENT_QUERY, EVENT_EXPORT
from services.rag_pipeline import run_rag_query
from services.pdf_export import export_chat_to_pdf, build_export_filename
from .serializers import (
    CreateSessionSerializer, UpdateSessionSerializer, SendMessageSerializer,
)

logger = logging.getLogger(__name__)


def _ser_session(s: dict) -> dict:
    d = serialize_mongo_doc(s)
    d['id'] = d.pop('_id', '')
    return d


def _ser_message(m: dict) -> dict:
    d = serialize_mongo_doc(m)
    d['id'] = d.pop('_id', '')
    return d


class ChatSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all chat sessions for the user, newest first."""
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        total = chat_sessions_col().count_documents({'user_id': request.user.id})
        sessions = list(
            chat_sessions_col()
            .find({'user_id': request.user.id})
            .sort('created_at', -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )

        return APIResponse.paginated(
            data=[_ser_session(s) for s in sessions],
            total=total,
            page=page,
            page_size=page_size,
        )

    def post(self, request):
        """Create a new chat session linked to one or more documents."""
        serializer = CreateSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        doc_ids = serializer.validated_data['document_ids']

        # A malformed id must be a 400, not a 500 — ObjectId() raises on anything
        # that isn't a 24-character hex string.
        try:
            oids = [ObjectId(d) for d in doc_ids]
        except (InvalidId, TypeError):
            return APIResponse.error('One or more document ids are not valid.')

        # Verify documents belong to user
        valid_docs = list(documents_col().find({
            '_id': {'$in': oids},
            'user_id': request.user.id,
            'status': 'completed',
        }, {'original_filename': 1}))

        if not valid_docs:
            return APIResponse.error('No valid completed documents found for the given IDs.')

        valid_ids = [str(d['_id']) for d in valid_docs]
        doc_names = [d.get('original_filename', '') for d in valid_docs]

        now = timezone.now()
        session = {
            'user_id':       request.user.id,
            'title':         serializer.validated_data['title'],
            'document_ids':  valid_ids,
            'document_names': doc_names,
            'status':        SESSION_ACTIVE,
            'message_count': 0,
            'last_message_preview': '',
            'created_at':    now,
            'updated_at':    now,
            'last_message_at': now,
        }
        result = chat_sessions_col().insert_one(session)
        session['_id'] = str(result.inserted_id)

        return APIResponse.created(data=_ser_session(session), message='Chat session created.')


class ChatSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_session(self, session_id: str, user_id: int):
        try:
            return chat_sessions_col().find_one({'_id': ObjectId(session_id), 'user_id': user_id})
        except InvalidId:
            return None

    def get(self, request, session_id):
        """Get session details and all messages."""
        session = self._get_session(session_id, request.user.id)
        if not session:
            return APIResponse.not_found('Session not found.')

        msgs = list(
            messages_col()
            .find({'session_id': session_id})
            .sort('created_at', 1)
        )

        return APIResponse.success(data={
            'session':  _ser_session(session),
            'messages': [_ser_message(m) for m in msgs],
        })

    def patch(self, request, session_id):
        """Rename or archive a session."""
        session = self._get_session(session_id, request.user.id)
        if not session:
            return APIResponse.not_found('Session not found.')

        serializer = UpdateSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        updates = {k: v for k, v in serializer.validated_data.items()}

        # Changing which documents the chat is grounded in. Re-validate against
        # this user's own completed documents so a crafted id can never attach
        # someone else's file — the frontend's list is never trusted.
        if 'document_ids' in updates:
            requested = updates['document_ids']
            try:
                oids = [ObjectId(d) for d in requested]
            except (InvalidId, TypeError):
                return APIResponse.error('One or more document ids are not valid.')

            valid_docs = list(documents_col().find({
                '_id':     {'$in': oids},
                'user_id': request.user.id,
                'status':  'completed',
            }, {'original_filename': 1}))

            if not valid_docs:
                return APIResponse.error(
                    'None of those documents are available. They must be your own and '
                    'finished processing.'
                )

            # Preserve the order the user picked, dropping anything that didn't
            # survive validation.
            by_id = {str(d['_id']): d.get('original_filename', '') for d in valid_docs}
            ordered = [d for d in requested if d in by_id]
            updates['document_ids']   = ordered
            updates['document_names'] = [by_id[d] for d in ordered]

        updates['updated_at'] = timezone.now()

        chat_sessions_col().update_one({'_id': ObjectId(session_id)}, {'$set': updates})
        updated = chat_sessions_col().find_one({'_id': ObjectId(session_id)})
        return APIResponse.success(data=_ser_session(updated), message='Session updated.')

    def delete(self, request, session_id):
        """Delete a session and all its messages."""
        session = self._get_session(session_id, request.user.id)
        if not session:
            return APIResponse.not_found('Session not found.')

        messages_col().delete_many({'session_id': session_id})
        chat_sessions_col().delete_one({'_id': ObjectId(session_id)})

        return APIResponse.success(message='Session deleted.')


class SendMessageView(APIView):
    permission_classes = [IsAuthenticated]
    # Per-user rate limit on the expensive RAG endpoint (see CHAT_THROTTLE_RATE).
    # Shields the shared Groq key from bursts/abuse; returns HTTP 429 when exceeded.
    throttle_scope = 'chat'

    def post(self, request, session_id):
        """Main RAG endpoint — receive question, return AI answer with citations."""
        try:
            session = chat_sessions_col().find_one(
                {'_id': ObjectId(session_id), 'user_id': request.user.id}
            )
        except InvalidId:
            return APIResponse.not_found('Session not found.')

        if not session:
            return APIResponse.not_found('Session not found.')

        if session.get('status') == SESSION_ARCHIVED:
            return APIResponse.error('Cannot send messages to an archived session.')

        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.error('Validation failed.', serializer.errors)

        question     = serializer.validated_data['question']
        document_ids = session.get('document_ids', [])

        try:
            result = run_rag_query(
                user_id=request.user.id,
                session_id=session_id,
                document_ids=document_ids,
                question=question,
            )
        except Exception as exc:
            logger.error("RAG query failed: %s", exc, exc_info=True)
            return APIResponse.server_error('Failed to generate response. Please try again.')

        # Log analytics
        try:
            analytics_col().insert_one({
                'user_id':    request.user.id,
                'event_type': EVENT_QUERY,
                'metadata':   {
                    'session_id': session_id,
                    'question_length': len(question),
                    'chunks_retrieved': result['chunks_retrieved'],
                },
                'created_at': timezone.now(),
            })
        except Exception:
            pass

        from django.conf import settings
        debug_enabled = settings.RAG_DEBUG or request.query_params.get('debug') == 'true'

        data = {
            'answer':    result['answer'],
            'citations': result['citations'],
            'session_id': session_id,
        }
        if debug_enabled:
            data['debug'] = result.get('debug', {})

        return APIResponse.success(data=data, message='Response generated.')


class ChatConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """What the RAG engine is running — read-only, for the Settings page.

        Everything here is a server-side constant that applies to every
        conversation, so the page reports it rather than offering it as a
        choice. Reading it from settings means the page can never drift out of
        step with what the pipeline actually does.
        """
        from django.conf import settings

        return APIResponse.success(data={
            'model':           settings.GROQ_MODEL,
            'embedding_model': settings.EMBEDDING_MODEL_NAME,
            'retrieval': {
                'top_k':          settings.RAG_TOP_K,
                'chunk_size':     settings.RAG_CHUNK_SIZE,
                'chunk_overlap':  settings.RAG_CHUNK_OVERLAP,
                'fetch_k':        settings.RAG_FETCH_K,
                'use_mmr':        settings.RAG_USE_MMR,
                'min_similarity': settings.RAG_MIN_SIMILARITY_SCORE,
                'memory_turns':   settings.CONVERSATION_MEMORY_TURNS,
            },
        })


class ChatSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Search chat sessions by title (case-insensitive substring match)."""
        query = request.query_params.get('q', '').strip()
        if not query:
            return APIResponse.error('Search query is required.')

        import re
        page      = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        # Case-insensitive title search
        regex = re.compile(re.escape(query), re.IGNORECASE)
        filter_query = {
            'user_id': request.user.id,
            'title':   {'$regex': regex},
        }

        total   = chat_sessions_col().count_documents(filter_query)
        results = list(
            chat_sessions_col()
            .find(filter_query)
            .sort('updated_at', -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )

        return APIResponse.paginated(
            data=[_ser_session(s) for s in results],
            total=total,
            page=page,
            page_size=page_size,
            message=f'{total} sessions found.',
        )


class ExportChatPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        """Export a chat session as a downloadable PDF."""
        try:
            session = chat_sessions_col().find_one(
                {'_id': ObjectId(session_id), 'user_id': request.user.id}
            )
        except InvalidId:
            return APIResponse.not_found('Session not found.')

        if not session:
            return APIResponse.not_found('Session not found.')

        msgs = list(messages_col().find({'session_id': session_id}).sort('created_at', 1))

        pdf_bytes = export_chat_to_pdf(
            session_title=session.get('title', 'Document'),
            messages=msgs,
        )

        # Log analytics
        try:
            analytics_col().insert_one({
                'user_id':    request.user.id,
                'event_type': EVENT_EXPORT,
                'metadata':   {'session_id': session_id},
                'created_at': timezone.now(),
            })
        except Exception:
            pass

        filename = build_export_filename(session.get('title', 'Document'), msgs)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
