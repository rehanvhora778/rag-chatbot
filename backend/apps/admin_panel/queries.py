"""Admin-scoped data access, over whichever store is live.

Why this is not in ``repositories/``
------------------------------------
That layer's defining rule is that every method takes an owner — the isolation
boundary is the signature, so a query that could return somebody else's rows
cannot be written by accident. Admin queries are the exact opposite: they exist
to count and list across all users.

Putting them in the same protocol would mean the repository layer no longer
guarantees the one thing it exists to guarantee, and a later reader could not
tell an owner-scoped method from an unscoped one without reading each body.
Keeping them here says it out loud: this module is cross-user by design, it is
reachable only behind ``IsAdminUser``, and there is exactly one place to audit.

Both backends implement the same operations and return the same dict shapes as
``repositories/`` does, because the React admin screens read those keys and a
rename would be an API break for no benefit.
"""
import logging
import re
from datetime import timedelta
from typing import Any, Optional, Protocol

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class AdminQueries(Protocol):
    """Cross-user reads and administrative deletes."""

    def document_totals(self) -> dict[str, int]: ...

    def chat_totals(self) -> dict[str, int]: ...

    def daily_active_users(self, days: int) -> list[dict[str, Any]]: ...

    def queries_per_day(self, days: int) -> list[dict[str, Any]]: ...

    def per_user_counts(self, user_ids: list[int]) -> dict[int, dict[str, int]]:
        """Documents, sessions and queries for several users at once.

        Batched rather than per-user because this feeds a paginated table: one
        call per user per column is 60 round trips for a 20-row page, and it is
        the reason the admin user list was the slowest screen in the product.
        """
        ...

    def recent_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]: ...

    def list_documents(self, *, page: int, page_size: int, status: str,
                       search: str) -> tuple[int, list[dict[str, Any]]]: ...

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]: ...

    def delete_document(self, document_id: str) -> bool: ...

    def list_conversations(self, *, page: int, page_size: int,
                           search: str) -> tuple[int, list[dict[str, Any]]]: ...

    def delete_conversation(self, conversation_id: str) -> bool: ...

    def purge_user(self, user_id: int) -> None:
        """Remove everything belonging to one user, before the account goes."""
        ...


# ══════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════

def _day_windows(days: int) -> list[tuple[Any, Any, str]]:
    """(start, end, label) for each of the last `days` days, oldest first.

    Shared so both backends bucket by the same boundaries. Two implementations
    of "midnight" is two chances for the graphs to disagree about which day a
    late-evening query belongs to.
    """
    now = timezone.now()
    windows = []
    for offset in range(days - 1, -1, -1):
        start = (now - timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        windows.append((start, start + timedelta(days=1), start.strftime('%b %d')))
    return windows


# ══════════════════════════════════════════════════════════════════
# PostgreSQL
# ══════════════════════════════════════════════════════════════════

class PostgresAdminQueries:
    """Admin reads through the ORM."""

    name = 'postgres'

    def document_totals(self) -> dict[str, int]:
        from django.db.models import Count, Q

        from apps.documents.models import Document

        week_ago = timezone.now() - timedelta(days=7)
        # One query for every bucket, rather than five COUNT round trips.
        row = Document.objects.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            failed=Count('id', filter=Q(status='failed')),
            pending=Count('id', filter=Q(status='pending')),
            new_7d=Count('id', filter=Q(created_at__gte=week_ago)),
        )
        return {key: value or 0 for key, value in row.items()}

    def chat_totals(self) -> dict[str, int]:
        from django.db.models import Count, Q

        from apps.chat.models import Conversation, Message

        now = timezone.now()
        counts = Message.objects.aggregate(
            total_messages=Count('id'),
            queries_7d=Count('id', filter=Q(role='user',
                                            created_at__gte=now - timedelta(days=7))),
            queries_30d=Count('id', filter=Q(role='user',
                                             created_at__gte=now - timedelta(days=30))),
        )
        return {
            'total_sessions': Conversation.objects.count(),
            'total_messages': counts['total_messages'] or 0,
            'queries_7d': counts['queries_7d'] or 0,
            'queries_30d': counts['queries_30d'] or 0,
        }

    def daily_active_users(self, days: int) -> list[dict[str, Any]]:
        from apps.analytics.models import AnalyticsEvent

        windows = _day_windows(days)
        oldest = windows[0][0]

        # Pulled in one query and bucketed in Python. A DATE_TRUNC group-by
        # would be one fewer loop but would also drop days with no activity,
        # and a trend line with missing days reads as a gap in the data rather
        # than a quiet Sunday.
        events = AnalyticsEvent.objects.filter(
            created_at__gte=oldest,
        ).values_list('user_id', 'created_at')

        rows = list(events)
        trend = []
        for start, end, label in windows:
            users = {uid for uid, at in rows if uid is not None and start <= at < end}
            trend.append({'date': label, 'users': len(users)})
        return trend

    def queries_per_day(self, days: int) -> list[dict[str, Any]]:
        from apps.chat.models import Message

        windows = _day_windows(days)
        stamps = list(
            Message.objects
            .filter(role='user', created_at__gte=windows[0][0])
            .values_list('created_at', flat=True)
        )
        return [
            {'date': label,
             'queries': sum(1 for at in stamps if start <= at < end)}
            for start, end, label in windows
        ]

    def per_user_counts(self, user_ids: list[int]) -> dict[int, dict[str, int]]:
        from django.db.models import Count

        from apps.chat.models import Conversation, Message
        from apps.documents.models import Document

        if not user_ids:
            return {}

        counts = {uid: {'documents': 0, 'sessions': 0, 'queries': 0} for uid in user_ids}

        for model, field, key, extra in (
            (Document, 'owner_id', 'documents', {}),
            (Conversation, 'owner_id', 'sessions', {}),
            (Message, 'conversation__owner_id', 'queries', {'role': 'user'}),
        ):
            grouped = (
                model.objects
                .filter(**{f'{field}__in': user_ids}, **extra)
                .values(field)
                .annotate(n=Count('id'))
            )
            for row in grouped:
                counts[row[field]][key] = row['n']

        return counts

    def recent_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from apps.documents.models import Document
        from repositories.postgres.documents import _to_dto

        rows = Document.objects.filter(owner_id=user_id).order_by('-created_at')[:limit]
        return [_to_dto(d) for d in rows]

    def list_documents(self, *, page: int, page_size: int, status: str,
                       search: str) -> tuple[int, list[dict[str, Any]]]:
        from apps.documents.models import Document
        from repositories.postgres.documents import _to_dto

        queryset = Document.objects.select_related('owner').order_by('-created_at')
        if status:
            queryset = queryset.filter(status=status)
        if search:
            queryset = queryset.filter(original_filename__icontains=search)

        total = queryset.count()
        rows = queryset[(page - 1) * page_size: page * page_size]

        documents = []
        for row in rows:
            dto = _to_dto(row)
            # select_related above means this costs no extra query per row.
            dto['username'] = row.owner.username if row.owner else 'deleted'
            documents.append(dto)
        return total, documents

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        from apps.documents.models import Document
        from repositories.postgres.documents import _to_dto, _uuid

        key = _uuid(document_id)
        if key is None:
            return None
        return _to_dto(Document.objects.filter(pk=key).first())

    def delete_document(self, document_id: str) -> bool:
        from apps.documents.models import Document
        from repositories.postgres.documents import _uuid

        key = _uuid(document_id)
        if key is None:
            return False
        # Chunks and their vectors go with it through the FK cascade, which is
        # the whole reason the Postgres path has no separate chunk delete here.
        deleted, _ = Document.objects.filter(pk=key).delete()
        return bool(deleted)

    def list_conversations(self, *, page: int, page_size: int,
                           search: str) -> tuple[int, list[dict[str, Any]]]:
        from apps.chat.models import Conversation
        from repositories.postgres.conversations import _to_dto

        queryset = (
            Conversation.objects
            .select_related('owner')
            .prefetch_related('documents')
            .order_by('-updated_at')
        )
        if search:
            queryset = queryset.filter(title__icontains=search)

        total = queryset.count()
        rows = queryset[(page - 1) * page_size: page * page_size]

        conversations = []
        for row in rows:
            dto = _to_dto(row)
            dto['username'] = row.owner.username if row.owner else 'deleted'
            conversations.append(dto)
        return total, conversations

    def delete_conversation(self, conversation_id: str) -> bool:
        from apps.chat.models import Conversation
        from repositories.postgres.documents import _uuid

        key = _uuid(conversation_id)
        if key is None:
            return False
        deleted, _ = Conversation.objects.filter(pk=key).delete()
        return bool(deleted)

    def purge_user(self, user_id: int) -> None:
        from apps.analytics.models import AnalyticsEvent
        from apps.chat.models import Conversation
        from apps.documents.models import Document

        # Messages, chunks and feedback follow their parents through the
        # cascade; deleting the User would too, but doing it explicitly keeps
        # the two backends behaving the same and survives on_delete changes.
        Document.objects.filter(owner_id=user_id).delete()
        Conversation.objects.filter(owner_id=user_id).delete()
        AnalyticsEvent.objects.filter(user_id=user_id).delete()


# ══════════════════════════════════════════════════════════════════
# MongoDB
# ══════════════════════════════════════════════════════════════════

class MongoAdminQueries:
    """Admin reads straight off the collections. The original implementation."""

    name = 'mongo'

    def document_totals(self) -> dict[str, int]:
        from core.mongo import documents_col

        col = documents_col()
        week_ago = timezone.now() - timedelta(days=7)
        return {
            'total': col.count_documents({}),
            'completed': col.count_documents({'status': 'completed'}),
            'failed': col.count_documents({'status': 'failed'}),
            'pending': col.count_documents({'status': 'pending'}),
            'new_7d': col.count_documents({'created_at': {'$gte': week_ago}}),
        }

    def chat_totals(self) -> dict[str, int]:
        from core.mongo import chat_sessions_col, messages_col

        now = timezone.now()
        messages = messages_col()
        return {
            'total_sessions': chat_sessions_col().count_documents({}),
            'total_messages': messages.count_documents({}),
            'queries_7d': messages.count_documents({
                'role': 'user', 'created_at': {'$gte': now - timedelta(days=7)},
            }),
            'queries_30d': messages.count_documents({
                'role': 'user', 'created_at': {'$gte': now - timedelta(days=30)},
            }),
        }

    def daily_active_users(self, days: int) -> list[dict[str, Any]]:
        from core.mongo import analytics_col

        col = analytics_col()
        return [
            {'date': label,
             'users': len(col.distinct('user_id',
                                       {'created_at': {'$gte': start, '$lt': end}}))}
            for start, end, label in _day_windows(days)
        ]

    def queries_per_day(self, days: int) -> list[dict[str, Any]]:
        from core.mongo import messages_col

        col = messages_col()
        return [
            {'date': label,
             'queries': col.count_documents({
                 'role': 'user', 'created_at': {'$gte': start, '$lt': end},
             })}
            for start, end, label in _day_windows(days)
        ]

    def per_user_counts(self, user_ids: list[int]) -> dict[int, dict[str, int]]:
        from core.mongo import chat_sessions_col, documents_col, messages_col

        if not user_ids:
            return {}

        counts = {uid: {'documents': 0, 'sessions': 0, 'queries': 0} for uid in user_ids}
        for col, key, extra in (
            (documents_col(), 'documents', {}),
            (chat_sessions_col(), 'sessions', {}),
            (messages_col(), 'queries', {'role': 'user'}),
        ):
            grouped = col.aggregate([
                {'$match': {'user_id': {'$in': user_ids}, **extra}},
                {'$group': {'_id': '$user_id', 'n': {'$sum': 1}}},
            ])
            for row in grouped:
                if row['_id'] in counts:
                    counts[row['_id']][key] = row['n']
        return counts

    def recent_documents(self, user_id: int, limit: int) -> list[dict[str, Any]]:
        from core.mongo import documents_col

        rows = documents_col().find({'user_id': user_id}).sort('created_at', -1).limit(limit)
        return [_from_mongo(row) for row in rows]

    def list_documents(self, *, page: int, page_size: int, status: str,
                       search: str) -> tuple[int, list[dict[str, Any]]]:
        from core.mongo import documents_col

        query: dict[str, Any] = {}
        if status:
            query['status'] = status
        if search:
            query['original_filename'] = {'$regex': re.compile(re.escape(search), re.I)}

        col = documents_col()
        total = col.count_documents(query)
        rows = list(
            col.find(query).sort('created_at', -1)
            .skip((page - 1) * page_size).limit(page_size)
        )

        names = _usernames({row.get('user_id') for row in rows})
        documents = []
        for row in rows:
            dto = _from_mongo(row)
            dto['username'] = names.get(row.get('user_id'), 'deleted')
            documents.append(dto)
        return total, documents

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        from core.mongo import documents_col

        key = _object_id(document_id)
        if key is None:
            return None
        row = documents_col().find_one({'_id': key})
        return _from_mongo(row) if row else None

    def delete_document(self, document_id: str) -> bool:
        from core.mongo import chunks_col, documents_col

        key = _object_id(document_id)
        if key is None:
            return False
        chunks_col().delete_many({'document_id': document_id})
        return documents_col().delete_one({'_id': key}).deleted_count > 0

    def list_conversations(self, *, page: int, page_size: int,
                           search: str) -> tuple[int, list[dict[str, Any]]]:
        from core.mongo import chat_sessions_col

        query: dict[str, Any] = {}
        if search:
            query['title'] = {'$regex': re.compile(re.escape(search), re.I)}

        col = chat_sessions_col()
        total = col.count_documents(query)
        rows = list(
            col.find(query).sort('updated_at', -1)
            .skip((page - 1) * page_size).limit(page_size)
        )

        names = _usernames({row.get('user_id') for row in rows})
        conversations = []
        for row in rows:
            dto = _from_mongo(row)
            dto['username'] = names.get(row.get('user_id'), 'deleted')
            conversations.append(dto)
        return total, conversations

    def delete_conversation(self, conversation_id: str) -> bool:
        from core.mongo import chat_sessions_col, messages_col

        key = _object_id(conversation_id)
        if key is None:
            return False
        removed = chat_sessions_col().delete_one({'_id': key}).deleted_count
        messages_col().delete_many({'session_id': conversation_id})
        return removed > 0

    def purge_user(self, user_id: int) -> None:
        from core.mongo import (
            analytics_col,
            chat_sessions_col,
            documents_col,
            messages_col,
        )

        documents_col().delete_many({'user_id': user_id})
        chat_sessions_col().delete_many({'user_id': user_id})
        messages_col().delete_many({'user_id': user_id})
        analytics_col().delete_many({'user_id': user_id})


def _object_id(value: str):
    """A Mongo ObjectId, or None when the string could never be one.

    None rather than an exception because every caller turns a bad id into the
    same 404 that a well-formed but absent id produces — telling them apart
    would confirm which ids exist.
    """
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _from_mongo(row: dict[str, Any]) -> dict[str, Any]:
    from core.utils import serialize_mongo_doc

    out = serialize_mongo_doc(row)
    out['id'] = out.pop('_id', '')
    return out


def _usernames(user_ids) -> dict[int, str]:
    """Resolve several user ids to usernames in one query, not one each."""
    from django.contrib.auth.models import User

    wanted = {uid for uid in user_ids if uid is not None}
    if not wanted:
        return {}
    return dict(User.objects.filter(id__in=wanted).values_list('id', 'username'))


# ══════════════════════════════════════════════════════════════════
# Selection
# ══════════════════════════════════════════════════════════════════

_INSTANCES: dict[str, AdminQueries] = {}


def get_admin_queries() -> AdminQueries:
    """The implementation for whichever store is live.

    Reads the setting on every call rather than caching the choice, so the
    `settings` fixture that flips PERSISTENCE_BACKEND mid-test takes effect —
    the same reason `repositories/factory.py` is resettable.
    """
    backend = getattr(settings, 'PERSISTENCE_BACKEND', 'mongo')
    if backend not in _INSTANCES:
        _INSTANCES[backend] = (
            PostgresAdminQueries() if backend == 'postgres' else MongoAdminQueries()
        )
    return _INSTANCES[backend]
