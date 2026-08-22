"""Operational metrics for the admin console.

Reads what the pipeline already records rather than adding a second collection
path. Every assistant message stores its provider, model, token usage and the
latency of each stage, so answering "how fast is it and what is it costing" is
a query, not new instrumentation — which is why those columns are on the
message row rather than only in a log line.

PostgreSQL only. The MongoDB backend never recorded per-message latency or
tokens, so the honest answer there is that the data does not exist, rather than
a dashboard of zeroes that looks like a system doing nothing.
"""
import logging
from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 7


def available() -> bool:
    from django.conf import settings

    return settings.PERSISTENCE_BACKEND == 'postgres'


def collect(days: int = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
    """Latency, cost and quality metrics over a recent window."""
    if not available():
        return {
            'available': False,
            'reason': (
                'Per-message latency and token usage are only recorded by the '
                'PostgreSQL backend. Set PERSISTENCE_BACKEND=postgres.'
            ),
        }

    from apps.chat.models import Conversation, Message, MessageFeedback, MessageRole
    from apps.documents.models import Document, DocumentStatus

    since = timezone.now() - timedelta(days=days)
    answers = Message.objects.filter(role=MessageRole.ASSISTANT, created_at__gte=since)

    latencies = sorted(
        answers.exclude(total_ms=None).values_list('total_ms', flat=True)
    )

    tokens = answers.aggregate(
        prompt=Sum('prompt_tokens'),
        completion=Sum('completion_tokens'),
        total=Sum('total_tokens'),
    )

    # Grouped in the database rather than in Python: the whole point of putting
    # these on the row was to avoid loading every message to count them.
    by_model = list(
        answers.exclude(model_name='')
        .values('model_name')
        .annotate(count=Count('id'), avg_ms=Avg('total_ms'))
        .order_by('-count')[:5]
    )

    feedback = MessageFeedback.objects.filter(created_at__gte=since).aggregate(
        total=Count('id'),
        helpful=Count('id', filter=Q(rating=1)),
        unhelpful=Count('id', filter=Q(rating=-1)),
        unreviewed_negative=Count('id', filter=Q(rating=-1, reviewed=False)),
    )

    documents = Document.objects.aggregate(
        total=Count('id'),
        completed=Count('id', filter=Q(status=DocumentStatus.COMPLETED)),
        failed=Count('id', filter=Q(status=DocumentStatus.FAILED)),
        # A document stuck here is the failure the sweep task exists to catch,
        # so it is worth showing rather than leaving to be noticed by a user.
        in_progress=Count('id', filter=Q(status__in=[
            DocumentStatus.PENDING, DocumentStatus.PROCESSING,
        ])),
        avg_processing_ms=Avg('processing_duration_ms'),
    )

    return {
        'available': True,
        'window_days': days,
        'answers': {
            'total': answers.count(),
            # A refusal is not a failure — it is the system working — but a
            # refusal *rate* that climbs means retrieval has stopped finding
            # things, which is exactly what to watch.
            'refused': answers.filter(chunks_retrieved=0).count(),
            'errored': answers.exclude(error='').count(),
        },
        'latency_ms': {
            'mean': round(sum(latencies) / len(latencies)) if latencies else None,
            'p50': _percentile(latencies, 0.50),
            'p95': _percentile(latencies, 0.95),
            'p99': _percentile(latencies, 0.99),
            'retrieval_mean': _rounded(answers.aggregate(v=Avg('retrieval_ms'))['v']),
            'generation_mean': _rounded(answers.aggregate(v=Avg('generation_ms'))['v']),
        },
        'tokens': {
            'prompt': tokens['prompt'] or 0,
            'completion': tokens['completion'] or 0,
            'total': tokens['total'] or 0,
        },
        'models': [
            {'model': row['model_name'], 'answers': row['count'],
             'avg_ms': _rounded(row['avg_ms'])}
            for row in by_model
        ],
        'feedback': {
            'total': feedback['total'] or 0,
            'helpful': feedback['helpful'] or 0,
            'unhelpful': feedback['unhelpful'] or 0,
            'unreviewed_negative': feedback['unreviewed_negative'] or 0,
            'satisfaction': _ratio(feedback['helpful'], feedback['total']),
        },
        'documents': {
            'total': documents['total'] or 0,
            'completed': documents['completed'] or 0,
            'failed': documents['failed'] or 0,
            'in_progress': documents['in_progress'] or 0,
            'success_rate': _ratio(documents['completed'], documents['total']),
            'avg_processing_ms': _rounded(documents['avg_processing_ms']),
        },
        'conversations': Conversation.objects.filter(created_at__gte=since).count(),
    }


def _percentile(ordered: list[int], fraction: float):
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, round(fraction * len(ordered) + 0.5) - 1))
    return ordered[index]


def _rounded(value):
    return round(value) if value is not None else None


def _ratio(part, whole):
    if not whole:
        return None
    return round((part or 0) / whole, 4)
