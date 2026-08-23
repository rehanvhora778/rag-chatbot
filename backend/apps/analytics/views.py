"""Per-user analytics endpoints.

HTTP only. Every read goes through ``apps/analytics/queries.py``, which answers
on either persistence backend — these views used to read MongoDB collections
directly, so the analytics page returned 500 on a PostgreSQL deployment for
every user, not only staff.

Both endpoints are scoped to ``request.user``. There is no id in either path,
so there is nothing a caller could tamper with to read somebody else's numbers.
"""
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import APIResponse
from core.utils import format_file_size

from .queries import get_analytics_queries

logger = logging.getLogger(__name__)

TREND_DAYS = 7
EVENT_WINDOW_DAYS = 30
TOP_DOCUMENTS = 5
RECENT_ITEMS = 5
ACTIVITY_ITEMS = 12


def _present(document: dict) -> dict:
    """Add the display-only field the document cards render."""
    return {**document,
            'file_size_display': format_file_size(document.get('file_size', 0))}


class UserAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Aggregated analytics for the authenticated user."""
        queries = get_analytics_queries()
        user_id = request.user.id

        documents = queries.document_stats(user_id)
        events = queries.event_counts(user_id, EVENT_WINDOW_DAYS)

        return APIResponse.success(data={
            'documents': {
                'total': documents['total'],
                'completed': documents['completed'],
                'failed': documents['failed'],
                'this_week': documents['this_week'],
                'by_type': documents['by_type'],
            },
            'chat': queries.chat_stats(user_id),
            'activity': {
                'uploads_last_30d': events['uploads'],
                'queries_last_30d': events['queries'],
                'exports_last_30d': events['exports'],
            },
            'daily_query_trend': queries.daily_query_trend(user_id, TREND_DAYS),
            'most_used_documents': queries.most_used_documents(user_id, TOP_DOCUMENTS),
            'recent_activity': queries.recent_activity(user_id, ACTIVITY_ITEMS),
        })


class UserDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Summary data for the user dashboard."""
        queries = get_analytics_queries()
        user_id = request.user.id

        documents = queries.document_stats(user_id)
        chat = queries.chat_stats(user_id)

        return APIResponse.success(data={
            'stats': {
                'total_documents': documents['total'],
                'total_sessions': chat['total_sessions'],
                'total_queries': chat['user_queries'],
            },
            'recent_documents': [
                _present(d) for d in queries.recent_documents(user_id, RECENT_ITEMS)
            ],
            'recent_sessions': queries.recent_conversations(user_id, RECENT_ITEMS),
        })
