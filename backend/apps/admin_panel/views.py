import logging
import os
from datetime import timedelta

from bson import ObjectId
from bson.errors import InvalidId
from django.contrib.auth.models import User
from django.utils import timezone

# aliased: `status` is used as a local variable for document filtering below
from rest_framework import status as status_codes
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.mongo import analytics_col, chat_sessions_col, documents_col, messages_col
from core.permissions import IsAdminUser
from core.responses import APIResponse
from core.utils import format_file_size, serialize_mongo_doc

logger = logging.getLogger(__name__)


class AdminSystemStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        now    = timezone.now()
        last_7  = now - timedelta(days=7)
        last_30 = now - timedelta(days=30)

        total_users  = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        new_users_7d = User.objects.filter(date_joined__gte=last_7).count()
        admin_users  = User.objects.filter(is_staff=True).count()

        total_docs     = documents_col().count_documents({})
        completed_docs = documents_col().count_documents({'status': 'completed'})
        failed_docs    = documents_col().count_documents({'status': 'failed'})
        pending_docs   = documents_col().count_documents({'status': 'pending'})
        docs_7d        = documents_col().count_documents({'created_at': {'$gte': last_7}})

        total_sessions = chat_sessions_col().count_documents({})
        total_messages = messages_col().count_documents({})
        queries_7d     = messages_col().count_documents({'role': 'user', 'created_at': {'$gte': last_7}})
        queries_30d    = messages_col().count_documents({'role': 'user', 'created_at': {'$gte': last_30}})

        # Daily active users trend (last 7 days)
        dau_trend = []
        for i in range(6, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end   = day_start + timedelta(days=1)
            active = analytics_col().distinct('user_id', {'created_at': {'$gte': day_start, '$lt': day_end}})
            dau_trend.append({'date': day_start.strftime('%b %d'), 'users': len(active)})

        # Queries per day (last 7 days)
        query_trend = []
        for i in range(6, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end   = day_start + timedelta(days=1)
            count = messages_col().count_documents({'role': 'user', 'created_at': {'$gte': day_start, '$lt': day_end}})
            query_trend.append({'date': day_start.strftime('%b %d'), 'queries': count})

        return APIResponse.success(data={
            'users':     {'total': total_users, 'active': active_users, 'new_7d': new_users_7d, 'admins': admin_users},
            'documents': {'total': total_docs, 'completed': completed_docs, 'failed': failed_docs, 'pending': pending_docs, 'new_7d': docs_7d},
            'chat':      {'total_sessions': total_sessions, 'total_messages': total_messages, 'queries_7d': queries_7d, 'queries_30d': queries_30d},
            'dau_trend':   dau_trend,
            'query_trend': query_trend,
        })


class AdminUserListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        page      = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        search    = request.query_params.get('search', '').strip()

        qs = User.objects.all().order_by('-date_joined')
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))

        total = qs.count()
        users = qs[(page - 1) * page_size: page * page_size]

        user_list = []
        for u in users:
            doc_count = documents_col().count_documents({'user_id': u.id})
            msg_count = messages_col().count_documents({'user_id': u.id, 'role': 'user'})
            ses_count = chat_sessions_col().count_documents({'user_id': u.id})
            user_list.append({
                'id':          u.id,
                'username':    u.username,
                'email':       u.email,
                'full_name':   u.first_name,
                'is_active':   u.is_active,
                'is_staff':    u.is_staff,
                'is_superuser': u.is_superuser,
                'date_joined': u.date_joined.isoformat(),
                'last_login':  u.last_login.isoformat() if u.last_login else None,
                'documents':   doc_count,
                'queries':     msg_count,
                'sessions':    ses_count,
            })

        return APIResponse.paginated(data=user_list, total=total, page=page, page_size=page_size)


class AdminUserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, user_id):
        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return APIResponse.not_found('User not found.')

        docs = list(documents_col().find({'user_id': u.id}).sort('created_at', -1).limit(5))

        def ser_doc(d):
            r = serialize_mongo_doc(d)
            r['id'] = r.pop('_id', '')
            r['file_size_display'] = format_file_size(r.get('file_size', 0))
            return r

        return APIResponse.success(data={
            'user': {
                'id': u.id, 'username': u.username, 'email': u.email,
                'full_name': u.first_name,
                'is_active': u.is_active, 'is_staff': u.is_staff, 'is_superuser': u.is_superuser,
                'date_joined': u.date_joined.isoformat(),
                'last_login':  u.last_login.isoformat() if u.last_login else None,
            },
            'stats': {
                'documents': documents_col().count_documents({'user_id': u.id}),
                'sessions':  chat_sessions_col().count_documents({'user_id': u.id}),
                'queries':   messages_col().count_documents({'user_id': u.id, 'role': 'user'}),
            },
            'recent_documents': [ser_doc(d) for d in docs],
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
            'is_active': u.is_active, 'is_staff': u.is_staff, 'is_superuser': u.is_superuser,
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

        documents_col().delete_many({'user_id': u.id})
        chat_sessions_col().delete_many({'user_id': u.id})
        messages_col().delete_many({'user_id': u.id})
        analytics_col().delete_many({'user_id': u.id})
        u.delete()
        logger.info("Admin %s deleted user %s", request.user.username, user_id)
        return APIResponse.success(message='User and all data deleted.')


class AdminDocumentListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        page      = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        status    = request.query_params.get('status', '')
        search    = request.query_params.get('search', '').strip()

        import re
        query = {}
        if status: query['status'] = status
        if search: query['original_filename'] = {'$regex': re.compile(re.escape(search), re.IGNORECASE)}

        total = documents_col().count_documents(query)
        docs  = list(documents_col().find(query).sort('created_at', -1).skip((page - 1) * page_size).limit(page_size))

        def ser(d):
            r = serialize_mongo_doc(d)
            r['id'] = r.pop('_id', '')
            r['file_size_display'] = format_file_size(r.get('file_size', 0))
            try:
                r['username'] = User.objects.get(id=r.get('user_id')).username
            except User.DoesNotExist:
                r['username'] = 'deleted'
            return r

        return APIResponse.paginated(data=[ser(d) for d in docs], total=total, page=page, page_size=page_size)


class AdminDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, doc_id):
        try:
            oid = ObjectId(doc_id)
        except InvalidId:
            return APIResponse.not_found('Document not found.')

        doc = documents_col().find_one({'_id': oid})
        if not doc:
            return APIResponse.not_found('Document not found.')

        # Delete file from disk
        file_path = doc.get('file_path', '')
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as exc:
                # The record still goes away, so log loudly: the file is now
                # orphaned on disk and nothing else will ever clean it up.
                logger.warning("Could not delete %s: %s", file_path, exc)

        # Delete the document's vectors
        try:
            from rag.registry import get_vector_store
            get_vector_store().delete(doc['user_id'], doc_id)
        except Exception as exc:
            logger.warning("Could not delete the vector index for %s: %s", doc_id, exc)

        from core.mongo import chunks_col
        chunks_col().delete_many({'document_id': doc_id})
        documents_col().delete_one({'_id': oid})

        logger.info("Admin %s deleted document %s", request.user.username, doc_id)
        return APIResponse.success(message='Document deleted.')


class AdminChatSessionListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        page      = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        search    = request.query_params.get('search', '').strip()

        import re
        query = {}
        if search: query['title'] = {'$regex': re.compile(re.escape(search), re.IGNORECASE)}

        total    = chat_sessions_col().count_documents(query)
        sessions = list(chat_sessions_col().find(query).sort('updated_at', -1).skip((page - 1) * page_size).limit(page_size))

        def ser(s):
            r = serialize_mongo_doc(s)
            r['id'] = r.pop('_id', '')
            try:
                r['username'] = User.objects.get(id=r.get('user_id')).username
            except User.DoesNotExist:
                r['username'] = 'deleted'
            return r

        return APIResponse.paginated(data=[ser(s) for s in sessions], total=total, page=page, page_size=page_size)

    def delete(self, request, session_id):
        try:
            oid = ObjectId(session_id)
        except InvalidId:
            return APIResponse.not_found('Session not found.')

        chat_sessions_col().delete_one({'_id': oid})
        messages_col().delete_many({'session_id': session_id})
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
