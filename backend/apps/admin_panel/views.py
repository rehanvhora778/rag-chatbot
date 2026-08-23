"""Admin endpoints.

HTTP and authorisation only. Every read and delete goes through
``apps/admin_panel/queries.py``, which is where the cross-user access lives and
where either persistence backend is answered — these views previously called
``documents_col()`` and friends directly, which made the whole admin panel
MongoDB-only regardless of ``PERSISTENCE_BACKEND`` and returned 500 on a
Postgres deployment.

The authorisation rules stay here, because they are about who is asking rather
than where the data is: you cannot lock yourself out, and only a superuser may
modify another superuser or hand out superuser rights.
"""
import logging
import os

from django.contrib.auth.models import User

# aliased: `status` is used as a local variable for document filtering below
from rest_framework import status as status_codes
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.permissions import IsAdminUser
from core.responses import APIResponse
from core.utils import format_file_size

from .queries import get_admin_queries

logger = logging.getLogger(__name__)

TREND_DAYS = 7
RECENT_DOCUMENTS = 5


def _pagination(request) -> tuple[int, int]:
    page = max(int(request.query_params.get('page', 1)), 1)
    page_size = min(int(request.query_params.get('page_size', 20)), 100)
    return page, page_size


def _present(document: dict) -> dict:
    """Add the display-only field the admin tables expect."""
    return {**document,
            'file_size_display': format_file_size(document.get('file_size', 0))}


class AdminSystemStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        from datetime import timedelta

        from django.utils import timezone

        queries = get_admin_queries()
        week_ago = timezone.now() - timedelta(days=7)

        documents = queries.document_totals()
        chat = queries.chat_totals()

        return APIResponse.success(data={
            'users': {
                'total': User.objects.count(),
                'active': User.objects.filter(is_active=True).count(),
                'new_7d': User.objects.filter(date_joined__gte=week_ago).count(),
                'admins': User.objects.filter(is_staff=True).count(),
            },
            'documents': documents,
            'chat': chat,
            'dau_trend': queries.daily_active_users(TREND_DAYS),
            'query_trend': queries.queries_per_day(TREND_DAYS),
        })


class AdminUserListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        page, page_size = _pagination(request)
        search = request.query_params.get('search', '').strip()

        queryset = User.objects.all().order_by('-date_joined')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
            )

        total = queryset.count()
        users = list(queryset[(page - 1) * page_size: page * page_size])

        # One batched call for the whole page. This used to be three counts per
        # user — sixty round trips to render twenty rows.
        counts = get_admin_queries().per_user_counts([u.id for u in users])

        user_list = []
        for u in users:
            stats = counts.get(u.id, {})
            user_list.append({
                'id': u.id,
                'username': u.username,
                'email': u.email,
                'full_name': u.first_name,
                'is_active': u.is_active,
                'is_staff': u.is_staff,
                'is_superuser': u.is_superuser,
                'date_joined': u.date_joined.isoformat(),
                'last_login': u.last_login.isoformat() if u.last_login else None,
                'documents': stats.get('documents', 0),
                'queries': stats.get('queries', 0),
                'sessions': stats.get('sessions', 0),
            })

        return APIResponse.paginated(data=user_list, total=total,
                                     page=page, page_size=page_size)


class AdminUserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, user_id):
        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return APIResponse.not_found('User not found.')

        queries = get_admin_queries()
        stats = queries.per_user_counts([u.id]).get(u.id, {})

        return APIResponse.success(data={
            'user': {
                'id': u.id, 'username': u.username, 'email': u.email,
                'full_name': u.first_name,
                'is_active': u.is_active, 'is_staff': u.is_staff,
                'is_superuser': u.is_superuser,
                'date_joined': u.date_joined.isoformat(),
                'last_login': u.last_login.isoformat() if u.last_login else None,
            },
            'stats': {
                'documents': stats.get('documents', 0),
                'sessions': stats.get('sessions', 0),
                'queries': stats.get('queries', 0),
            },
            'recent_documents': [
                _present(d) for d in queries.recent_documents(u.id, RECENT_DOCUMENTS)
            ],
        })

    def patch(self, request, user_id):
        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return APIResponse.not_found('User not found.')

        is_self = str(user_id) == str(request.user.id)

        # Locking yourself out is never what you meant to do.
        if is_self and request.data.get('is_active') is False:
            return APIResponse.error('You cannot deactivate your own account.')
        if is_self and request.data.get('is_staff') is False:
            return APIResponse.error('You cannot remove your own admin access.')

        # Only a superuser may touch another superuser, or hand out superuser rights.
        if u.is_superuser and not is_self and not request.user.is_superuser:
            return APIResponse.error('Only a superuser can modify another superuser.',
                                     status_code=status_codes.HTTP_403_FORBIDDEN)
        if 'is_superuser' in request.data and not request.user.is_superuser:
            return APIResponse.error('Only a superuser can change superuser rights.',
                                     status_code=status_codes.HTTP_403_FORBIDDEN)

        if 'is_active'    in request.data: u.is_active    = bool(request.data['is_active'])
        if 'is_staff'     in request.data: u.is_staff     = bool(request.data['is_staff'])
        if 'is_superuser' in request.data: u.is_superuser = bool(request.data['is_superuser'])
        u.save()

        logger.info("Admin %s updated user %s -> active=%s staff=%s superuser=%s",
                    request.user.email, u.email, u.is_active, u.is_staff, u.is_superuser)

        return APIResponse.success(data={
            'id': u.id, 'username': u.username,
            'is_active': u.is_active, 'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
        }, message='User updated.')

    def delete(self, request, user_id):
        # Admins may delete their own account too — the frontend signs them out afterwards.
        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return APIResponse.not_found('User not found.')

        if u.is_superuser and u.id != request.user.id and not request.user.is_superuser:
            return APIResponse.error('Only a superuser can delete another superuser.',
                                     status_code=status_codes.HTTP_403_FORBIDDEN)

        get_admin_queries().purge_user(u.id)
        u.delete()
        logger.info("Admin %s deleted user %s", request.user.username, user_id)
        return APIResponse.success(message='User and all data deleted.')


class AdminDocumentListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        page, page_size = _pagination(request)
        status = request.query_params.get('status', '')
        search = request.query_params.get('search', '').strip()

        total, documents = get_admin_queries().list_documents(
            page=page, page_size=page_size, status=status, search=search,
        )
        return APIResponse.paginated(data=[_present(d) for d in documents],
                                     total=total, page=page, page_size=page_size)


class AdminDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, doc_id):
        queries = get_admin_queries()

        document = queries.get_document(doc_id)
        if document is None:
            return APIResponse.not_found('Document not found.')

        # The file on disk, first: if the record went first and this failed,
        # nothing would remember the file existed.
        file_path = document.get('file_path', '')
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as exc:
                # The record still goes away, so log loudly: the file is now
                # orphaned on disk and nothing else will ever clean it up.
                logger.warning("Could not delete %s: %s", file_path, exc)

        # Vectors next. The index key is the id the document was indexed under,
        # which for a migrated document is its old MongoDB id rather than its
        # current one — reading it back from the record is what keeps FAISS
        # files findable after the Postgres migration.
        index_key = document.get('legacy_mongo_id') or document['id']
        try:
            from rag.registry import get_vector_store
            get_vector_store().delete(document['user_id'], index_key)
        except Exception as exc:
            logger.warning("Could not delete the vector index for %s: %s", doc_id, exc)

        queries.delete_document(doc_id)

        logger.info("Admin %s deleted document %s", request.user.username, doc_id)
        return APIResponse.success(message='Document deleted.')


class AdminChatSessionListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        page, page_size = _pagination(request)
        search = request.query_params.get('search', '').strip()

        total, conversations = get_admin_queries().list_conversations(
            page=page, page_size=page_size, search=search,
        )
        return APIResponse.paginated(data=conversations, total=total,
                                     page=page, page_size=page_size)

    def delete(self, request, session_id):
        if not get_admin_queries().delete_conversation(session_id):
            return APIResponse.not_found('Session not found.')
        return APIResponse.success(message='Chat session deleted.')


class AdminMetricsView(APIView):
    """Operational metrics: latency, tokens, feedback, ingestion health.

    GET /api/admin-panel/metrics/?days=7

    Separate from AdminSystemStatsView, which counts rows. This answers the
    operational questions — how fast, at what cost, and is anything failing.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        from apps.analytics import metrics_service

        try:
            days = max(1, min(int(request.query_params.get('days', 7)), 90))
        except (TypeError, ValueError):
            days = 7

        return APIResponse.success(data=metrics_service.collect(days))
