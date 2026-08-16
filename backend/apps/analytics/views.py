import logging
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.mongo import analytics_col, documents_col, chat_sessions_col, messages_col
from core.responses import APIResponse
from core.constants import EVENT_UPLOAD, EVENT_QUERY, EVENT_EXPORT, EVENT_SUMMARY

logger = logging.getLogger(__name__)


class UserAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return aggregated analytics for the authenticated user."""
        uid = request.user.id
        now = timezone.now()
        last_30 = now - timedelta(days=30)
        last_7  = now - timedelta(days=7)

        # Document stats
        total_docs     = documents_col().count_documents({'user_id': uid})
        completed_docs = documents_col().count_documents({'user_id': uid, 'status': 'completed'})
        failed_docs    = documents_col().count_documents({'user_id': uid, 'status': 'failed'})
        docs_this_week = documents_col().count_documents({'user_id': uid, 'created_at': {'$gte': last_7}})

        # Chat stats
        total_sessions = chat_sessions_col().count_documents({'user_id': uid})
        active_sessions = chat_sessions_col().count_documents({'user_id': uid, 'status': 'active'})
        total_messages  = messages_col().count_documents({'user_id': uid})
        user_messages   = messages_col().count_documents({'user_id': uid, 'role': 'user'})
        messages_this_week = messages_col().count_documents({'user_id': uid, 'created_at': {'$gte': last_7}})

        # Analytics events
        uploads_30d = analytics_col().count_documents({'user_id': uid, 'event_type': EVENT_UPLOAD, 'created_at': {'$gte': last_30}})
        queries_30d = analytics_col().count_documents({'user_id': uid, 'event_type': EVENT_QUERY,  'created_at': {'$gte': last_30}})
        exports_30d = analytics_col().count_documents({'user_id': uid, 'event_type': EVENT_EXPORT, 'created_at': {'$gte': last_30}})

        # Daily query trend (last 7 days)
        daily_trend = []
        for i in range(6, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end   = day_start + timedelta(days=1)
            count = analytics_col().count_documents({
                'user_id':    uid,
                'event_type': EVENT_QUERY,
                'created_at': {'$gte': day_start, '$lt': day_end},
            })
            daily_trend.append({
                'date':  day_start.strftime('%Y-%m-%d'),
                'queries': count,
            })

        # Document type breakdown
        type_pipeline = [
            {'$match': {'user_id': uid}},
            {'$group': {'_id': '$file_type', 'count': {'$sum': 1}}},
        ]
        type_breakdown = {r['_id']: r['count'] for r in documents_col().aggregate(type_pipeline)}

        # Most-used documents — how many questions were asked against each one.
        # A session pins its documents up front, so a session's user-message
        # count is exactly the number of questions asked of those documents.
        usage = {}
        for s in chat_sessions_col().find(
            {'user_id': uid}, {'document_ids': 1, 'message_count': 1},
        ):
            # message_count counts both sides of each exchange.
            questions = (s.get('message_count', 0) or 0) // 2
            for doc_id in (s.get('document_ids') or []):
                entry = usage.setdefault(doc_id, {'queries': 0, 'sessions': 0})
                entry['queries']  += questions
                entry['sessions'] += 1

        most_used = []
        if usage:
            from bson import ObjectId
            from bson.errors import InvalidId
            oids = []
            for d in usage:
                try:
                    oids.append(ObjectId(d))
                except (InvalidId, TypeError):
                    continue
            names = {
                str(d['_id']): d.get('original_filename', 'Unknown')
                for d in documents_col().find(
                    {'_id': {'$in': oids}, 'user_id': uid},
                    {'original_filename': 1},
                )
            }
            # Documents that have since been deleted drop out here rather than
            # showing up as "Unknown" rows.
            most_used = sorted(
                (
                    {'document_id': doc_id, 'name': names[doc_id], **stats}
                    for doc_id, stats in usage.items() if doc_id in names
                ),
                key=lambda r: (r['queries'], r['sessions']),
                reverse=True,
            )[:5]

        # Recent activity — the raw event log, newest first.
        ACTIVITY_LABELS = {
            EVENT_UPLOAD:  'Uploaded a document',
            EVENT_QUERY:   'Asked a question',
            EVENT_EXPORT:  'Exported a chat',
            EVENT_SUMMARY: 'Generated a summary',
        }
        recent_activity = [
            {
                'event_type': e.get('event_type', ''),
                'label':      ACTIVITY_LABELS.get(e.get('event_type'), 'Activity'),
                'detail':     (e.get('metadata') or {}).get('filename', ''),
                'created_at': e.get('created_at'),
            }
            for e in analytics_col()
            .find({'user_id': uid, 'event_type': {'$in': list(ACTIVITY_LABELS)}})
            .sort('created_at', -1)
            .limit(12)
        ]

        return APIResponse.success(data={
            'documents': {
                'total':      total_docs,
                'completed':  completed_docs,
                'failed':     failed_docs,
                'this_week':  docs_this_week,
                'by_type':    type_breakdown,
            },
            'chat': {
                'total_sessions':    total_sessions,
                'active_sessions':   active_sessions,
                'total_messages':    total_messages,
                'user_queries':      user_messages,
                'messages_this_week': messages_this_week,
            },
            'activity': {
                'uploads_last_30d':  uploads_30d,
                'queries_last_30d':  queries_30d,
                'exports_last_30d':  exports_30d,
            },
            'daily_query_trend':   daily_trend,
            'most_used_documents': most_used,
            'recent_activity':     recent_activity,
        })


class UserDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Summary data for the user dashboard."""
        uid = request.user.id

        recent_docs = list(
            documents_col()
            .find({'user_id': uid})
            .sort('created_at', -1)
            .limit(5)
        )
        recent_sessions = list(
            chat_sessions_col()
            .find({'user_id': uid})
            .sort('last_message_at', -1)
            .limit(5)
        )

        from core.utils import serialize_mongo_doc, format_file_size

        def ser_doc(d):
            r = serialize_mongo_doc(d)
            r['id'] = r.pop('_id', '')
            r['file_size_display'] = format_file_size(r.get('file_size', 0))
            return r

        def ser_session(s):
            r = serialize_mongo_doc(s)
            r['id'] = r.pop('_id', '')
            return r

        total_docs     = documents_col().count_documents({'user_id': uid})
        total_sessions = chat_sessions_col().count_documents({'user_id': uid})
        total_queries  = messages_col().count_documents({'user_id': uid, 'role': 'user'})

        return APIResponse.success(data={
            'stats': {
                'total_documents': total_docs,
                'total_sessions':  total_sessions,
                'total_queries':   total_queries,
            },
            'recent_documents': [ser_doc(d) for d in recent_docs],
            'recent_sessions':  [ser_session(s) for s in recent_sessions],
        })
