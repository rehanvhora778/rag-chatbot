"""Analytics event recording.

Four views were each writing the same analytics document inline, wrapped in a
bare ``except Exception: pass``. That shape has two problems:

  * the same insert is written out four times, so a change to the event shape
    has to be made four times;
  * a broken analytics write is completely invisible. Losing telemetry must
    never fail a user's request, but it also must not happen silently — the
    first symptom would be an empty dashboard with no explanation anywhere.

``record_event`` keeps the first property (it never raises) and fixes the
second (it logs). It is also the single seam through which analytics moves off
MongoDB, rather than four.

That seam went unused for longer than it should have. Until this was fixed the
function wrote to MongoDB unconditionally, so on a PostgreSQL deployment every
event was silently dropped — the write failed, logged a WARNING nobody was
reading, and the analytics page showed zeroes for ever. Migrating the *read*
side alone would have fixed nothing, because there was nothing to read.
"""
import logging
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def record_event(
    user_id: Optional[int],
    event_type: str,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """Record one analytics event. Returns whether it was stored.

    Never raises: telemetry is not worth failing a request over. A failure is
    logged at WARNING with the event type, which is enough to notice that the
    analytics store is unreachable without drowning the log in stack traces.
    """
    try:
        if getattr(settings, 'PERSISTENCE_BACKEND', 'mongo') == 'postgres':
            _record_postgres(user_id, event_type, metadata or {})
        else:
            _record_mongo(user_id, event_type, metadata or {})
        return True
    except Exception as exc:
        logger.warning(
            "Analytics event '%s' for user %s was not recorded: %s",
            event_type, user_id, exc,
        )
        return False


def _record_postgres(user_id: Optional[int], event_type: str,
                     metadata: dict[str, Any]) -> None:
    from apps.analytics.models import AnalyticsEvent

    # user_id rather than user: the column is nullable by design (see the model)
    # and assigning an id avoids a SELECT to hydrate a User this never reads.
    AnalyticsEvent.objects.create(
        user_id=user_id, event_type=event_type, metadata=metadata,
    )


def _record_mongo(user_id: Optional[int], event_type: str,
                  metadata: dict[str, Any]) -> None:
    from core.mongo import analytics_col

    analytics_col().insert_one({
        'user_id': user_id,
        'event_type': event_type,
        'metadata': metadata,
        # Set explicitly because MongoDB has no auto_now_add; the Postgres
        # model fills this itself.
        'created_at': timezone.now(),
    })
