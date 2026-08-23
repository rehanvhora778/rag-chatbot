"""Per-user analytics, over whichever store is live.

The views behind ``/api/analytics/`` read MongoDB collections directly, which
made the user-facing analytics page MongoDB-only regardless of
``PERSISTENCE_BACKEND`` — the same defect the admin panel had, but hitting every
user rather than only staff.

Why this is not in ``repositories/``, given these ARE owner-scoped
------------------------------------------------------------------
The admin layer sits outside that package because its queries are cross-user
and would break the owner-in-every-signature rule. These are the opposite:
every method here takes a ``user_id`` and honours it, so that objection does
not apply.

They are separate for a duller reason. These are aggregates assembled for two
specific screens — counts by status, a seven-day trend, a top-five table — not
entity access. Folding a dozen of them into the document and conversation
repositories would double those files with methods no other caller wants, and
would tie the shape of a dashboard to the interface every other feature depends
on. When the dashboard changes, only this module should have to.
"""
import logging
from typing import Any, Optional, Protocol

from django.utils import timezone

from core.constants import EVENT_EXPORT, EVENT_QUERY, EVENT_SUMMARY, EVENT_UPLOAD
from core.utils import day_windows

logger = logging.getLogger(__name__)

# Only these appear in the activity feed. A login is not something a user needs
# reflected back at them, and feedback events would list their own opinions.
ACTIVITY_LABELS = {
    EVENT_UPLOAD: 'Uploaded a document',
    EVENT_QUERY: 'Asked a question',
    EVENT_EXPORT: 'Exported a chat',
    EVENT_SUMMARY: 'Generated a summary',
}


class AnalyticsQueries(Protocol):
    """Everything the analytics and dashboard screens read. Owner-scoped."""

    def document_stats(self, user_id: int) -> dict[str, Any]: ...

    def chat_stats(self, user_id: int) -> dict[str, int]: ...

    def event_counts(self, user_id: int, days: int) -> dict[str, int]: ...

    def daily_query_trend(self, user_id: int, days: int) -> list[dict[str, Any]]: ...

    def most_used_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        """Which documents the user actually asks questions of.

        A conversation pins its documents up front, so its user-message count
        is exactly the number of questions asked of that set. Documents deleted
        since are dropped rather than listed as "Unknown".
        """
        ...

    def recent_activity(self, user_id: int, limit: int) -> list[dict[str, Any]]: ...

    def recent_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]: ...

    def recent_conversations(self, user_id: int, limit: int) -> list[dict[str, Any]]: ...


def _activity_row(event_type: str, detail: str, created_at) -> dict[str, Any]:
    return {
        'event_type': event_type or '',
        'label': ACTIVITY_LABELS.get(event_type, 'Activity'),
        'detail': detail or '',
        'created_at': created_at,
    }


def _rank_usage(usage: dict[str, dict[str, int]], names: dict[str, str],
                limit: int) -> list[dict[str, Any]]:
    """Shared ranking so both backends order ties identically."""
    return sorted(
        (
            {'document_id': doc_id, 'name': names[doc_id], **stats}
            for doc_id, stats in usage.items() if doc_id in names
        ),
        key=lambda row: (row['queries'], row['sessions']),
        reverse=True,
    )[:limit]


# ══════════════════════════════════════════════════════════════════
# PostgreSQL
# ══════════════════════════════════════════════════════════════════

class PostgresAnalyticsQueries:
    name = 'postgres'

    def document_stats(self, user_id: int) -> dict[str, Any]:
        from datetime import timedelta

        from django.db.models import Count, Q

        from apps.documents.models import Document

        week_ago = timezone.now() - timedelta(days=7)
        owned = Document.objects.filter(owner_id=user_id)

        totals = owned.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            failed=Count('id', filter=Q(status='failed')),
            this_week=Count('id', filter=Q(created_at__gte=week_ago)),
        )
        by_type = {
            row['file_type']: row['n']
            for row in owned.values('file_type').annotate(n=Count('id'))
        }
        return {**{k: v or 0 for k, v in totals.items()}, 'by_type': by_type}

    def chat_stats(self, user_id: int) -> dict[str, int]:
        from datetime import timedelta

        from django.db.models import Count, Q

        from apps.chat.models import Conversation, Message

        week_ago = timezone.now() - timedelta(days=7)

        sessions = Conversation.objects.filter(owner_id=user_id).aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
        )
        messages = Message.objects.filter(conversation__owner_id=user_id).aggregate(
            total=Count('id'),
            user_queries=Count('id', filter=Q(role='user')),
            this_week=Count('id', filter=Q(created_at__gte=week_ago)),
        )
        return {
            'total_sessions': sessions['total'] or 0,
            'active_sessions': sessions['active'] or 0,
            'total_messages': messages['total'] or 0,
            'user_queries': messages['user_queries'] or 0,
            'messages_this_week': messages['this_week'] or 0,
        }

    def event_counts(self, user_id: int, days: int) -> dict[str, int]:
        from datetime import timedelta

        from django.db.models import Count, Q

        from apps.analytics.models import AnalyticsEvent

        since = timezone.now() - timedelta(days=days)
        row = AnalyticsEvent.objects.filter(
            user_id=user_id, created_at__gte=since,
        ).aggregate(
            uploads=Count('id', filter=Q(event_type=EVENT_UPLOAD)),
            queries=Count('id', filter=Q(event_type=EVENT_QUERY)),
            exports=Count('id', filter=Q(event_type=EVENT_EXPORT)),
        )
        return {key: value or 0 for key, value in row.items()}

    def daily_query_trend(self, user_id: int, days: int) -> list[dict[str, Any]]:
        from apps.analytics.models import AnalyticsEvent

        windows = day_windows(days, '%Y-%m-%d')
        stamps = list(
            AnalyticsEvent.objects
            .filter(user_id=user_id, event_type=EVENT_QUERY,
                    created_at__gte=windows[0][0])
            .values_list('created_at', flat=True)
        )
        return [
            {'date': label, 'queries': sum(1 for at in stamps if start <= at < end)}
            for start, end, label in windows
        ]

    def most_used_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from apps.chat.models import Conversation

        usage: dict[str, dict[str, int]] = {}
        names: dict[str, str] = {}

        conversations = (
            Conversation.objects
            .filter(owner_id=user_id)
            .prefetch_related('documents')
            .only('id', 'message_count')
        )
        for conversation in conversations:
            # message_count counts both sides of each exchange.
            questions = (conversation.message_count or 0) // 2
            for document in conversation.documents.all():
                key = str(document.pk)
                # Read from the relation, so a document deleted since simply is
                # not here — no second query, and no "Unknown" rows.
                names[key] = document.original_filename
                entry = usage.setdefault(key, {'queries': 0, 'sessions': 0})
                entry['queries'] += questions
                entry['sessions'] += 1

        return _rank_usage(usage, names, limit)

    def recent_activity(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from apps.analytics.models import AnalyticsEvent

        events = (
            AnalyticsEvent.objects
            .filter(user_id=user_id, event_type__in=list(ACTIVITY_LABELS))
            # The insertion order breaks ties, because created_at alone does
            # not: several events can share a timestamp to the microsecond
            # (an upload that immediately triggers a summary), and the feed
            # would then reorder itself between two refreshes with nothing
            # having happened. The id is a sequence, so later is always higher.
            .order_by('-created_at', '-id')[:limit]
        )
        return [
            _activity_row(e.event_type, (e.metadata or {}).get('filename', ''),
                          e.created_at)
            for e in events
        ]

    def recent_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from apps.documents.models import Document
        from repositories.postgres.documents import _to_dto

        rows = Document.objects.filter(owner_id=user_id).order_by('-created_at')[:limit]
        return [_to_dto(row) for row in rows]

    def recent_conversations(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from django.db.models import F

        from apps.chat.models import Conversation
        from repositories.postgres.conversations import _to_dto

        rows = (
            Conversation.objects
            .filter(owner_id=user_id)
            .prefetch_related('documents')
            # NULLs last, explicitly: a conversation with no messages yet has no
            # last_message_at, and PostgreSQL sorts NULLs FIRST on a descending
            # order — which would put every empty session above every real one
            # on the dashboard. SQLite sorts them last, so the default would
            # also have behaved differently on the two databases.
            .order_by(F('last_message_at').desc(nulls_last=True))[:limit]
        )
        return [_to_dto(row) for row in rows]


# ══════════════════════════════════════════════════════════════════
# MongoDB
# ══════════════════════════════════════════════════════════════════

class MongoAnalyticsQueries:
    name = 'mongo'

    def document_stats(self, user_id: int) -> dict[str, Any]:
        from datetime import timedelta

        from core.mongo import documents_col

        col = documents_col()
        week_ago = timezone.now() - timedelta(days=7)
        by_type = {
            row['_id']: row['count']
            for row in col.aggregate([
                {'$match': {'user_id': user_id}},
                {'$group': {'_id': '$file_type', 'count': {'$sum': 1}}},
            ])
        }
        return {
            'total': col.count_documents({'user_id': user_id}),
            'completed': col.count_documents({'user_id': user_id, 'status': 'completed'}),
            'failed': col.count_documents({'user_id': user_id, 'status': 'failed'}),
            'this_week': col.count_documents({
                'user_id': user_id, 'created_at': {'$gte': week_ago},
            }),
            'by_type': by_type,
        }

    def chat_stats(self, user_id: int) -> dict[str, int]:
        from datetime import timedelta

        from core.mongo import chat_sessions_col, messages_col

        sessions, messages = chat_sessions_col(), messages_col()
        week_ago = timezone.now() - timedelta(days=7)
        return {
            'total_sessions': sessions.count_documents({'user_id': user_id}),
            'active_sessions': sessions.count_documents({
                'user_id': user_id, 'status': 'active',
            }),
            'total_messages': messages.count_documents({'user_id': user_id}),
            'user_queries': messages.count_documents({
                'user_id': user_id, 'role': 'user',
            }),
            'messages_this_week': messages.count_documents({
                'user_id': user_id, 'created_at': {'$gte': week_ago},
            }),
        }

    def event_counts(self, user_id: int, days: int) -> dict[str, int]:
        from datetime import timedelta

        from core.mongo import analytics_col

        col = analytics_col()
        since = timezone.now() - timedelta(days=days)
        return {
            key: col.count_documents({
                'user_id': user_id, 'event_type': event,
                'created_at': {'$gte': since},
            })
            for key, event in (('uploads', EVENT_UPLOAD),
                               ('queries', EVENT_QUERY),
                               ('exports', EVENT_EXPORT))
        }

    def daily_query_trend(self, user_id: int, days: int) -> list[dict[str, Any]]:
        from core.mongo import analytics_col

        col = analytics_col()
        return [
            {'date': label,
             'queries': col.count_documents({
                 'user_id': user_id, 'event_type': EVENT_QUERY,
                 'created_at': {'$gte': start, '$lt': end},
             })}
            for start, end, label in day_windows(days, '%Y-%m-%d')
        ]

    def most_used_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from bson import ObjectId
        from bson.errors import InvalidId

        from core.mongo import chat_sessions_col, documents_col

        usage: dict[str, dict[str, int]] = {}
        for session in chat_sessions_col().find(
            {'user_id': user_id}, {'document_ids': 1, 'message_count': 1},
        ):
            questions = (session.get('message_count', 0) or 0) // 2
            for doc_id in (session.get('document_ids') or []):
                entry = usage.setdefault(doc_id, {'queries': 0, 'sessions': 0})
                entry['queries'] += questions
                entry['sessions'] += 1

        if not usage:
            return []

        object_ids = []
        for doc_id in usage:
            try:
                object_ids.append(ObjectId(doc_id))
            except (InvalidId, TypeError):
                continue

        names = {
            str(row['_id']): row.get('original_filename', 'Unknown')
            for row in documents_col().find(
                {'_id': {'$in': object_ids}, 'user_id': user_id},
                {'original_filename': 1},
            )
        }
        return _rank_usage(usage, names, limit)

    def recent_activity(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from core.mongo import analytics_col

        events = (
            analytics_col()
            .find({'user_id': user_id, 'event_type': {'$in': list(ACTIVITY_LABELS)}})
            # _id breaks ties for the same reason the Postgres path uses id:
            # an ObjectId leads with a timestamp and a counter, so it orders
            # by insertion. Without it the two backends could present the same
            # events in different orders.
            .sort([('created_at', -1), ('_id', -1)])
            .limit(limit)
        )
        return [
            _activity_row(e.get('event_type', ''),
                          (e.get('metadata') or {}).get('filename', ''),
                          e.get('created_at'))
            for e in events
        ]

    def recent_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from core.mongo import documents_col

        rows = (
            documents_col().find({'user_id': user_id})
            .sort('created_at', -1).limit(limit)
        )
        return [_from_mongo(row) for row in rows]

    def recent_conversations(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from core.mongo import chat_sessions_col

        rows = (
            chat_sessions_col().find({'user_id': user_id})
            .sort('last_message_at', -1).limit(limit)
        )
        return [_from_mongo(row) for row in rows]


def _from_mongo(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    from core.utils import serialize_mongo_doc

    out = serialize_mongo_doc(row)
    out['id'] = out.pop('_id', '')
    return out


# ══════════════════════════════════════════════════════════════════
# Selection
# ══════════════════════════════════════════════════════════════════

_INSTANCES: dict[str, AnalyticsQueries] = {}


def get_analytics_queries() -> AnalyticsQueries:
    """The implementation for whichever store is live."""
    from django.conf import settings

    backend = getattr(settings, 'PERSISTENCE_BACKEND', 'mongo')
    if backend not in _INSTANCES:
        _INSTANCES[backend] = (
            PostgresAnalyticsQueries() if backend == 'postgres'
            else MongoAnalyticsQueries()
        )
    return _INSTANCES[backend]
