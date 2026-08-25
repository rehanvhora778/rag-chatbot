import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


def health_check(request):
    """Liveness plus a readable summary of which stack is actually running.

    Checks *the store the application reads from*, not every store it can be
    configured against. The earlier version pinged MongoDB unconditionally,
    which was right while Mongo was the only store and became actively
    misleading once it was not: a correct PostgreSQL deployment reported
    ``"mongodb": "unavailable"`` and ``"status": "degraded"`` for ever, because
    it was being marked down for failing to reach a database it is not
    supposed to be using.

    The backend fields are here for the same reason the Blueprint repeats them:
    ``PERSISTENCE_BACKEND``, ``VECTOR_BACKEND`` and hybrid retrieval are all
    derived from whether ``DATABASE_URL`` is set, so the one question worth
    answering from outside the box is which way that derivation actually went.
    A deploy that quietly fell back to the old stack looks identical from the
    UI until the first question returns a worse answer.
    """
    backend = getattr(settings, 'PERSISTENCE_BACKEND', 'mongo')

    payload = {
        'status':           'healthy',
        'timestamp':        timezone.now().isoformat(),
        'service':          'AI RAG Chatbot API',
        'persistence':      backend,
        'vector_backend':   getattr(settings, 'VECTOR_BACKEND', 'faiss'),
        'hybrid_retrieval': bool(getattr(settings, 'RAG_HYBRID_ENABLED', False)),
        'reranking':        bool(getattr(settings, 'RAG_RERANK_ENABLED', False)),
    }

    if backend == 'postgres':
        payload['database'] = _check_postgres(payload)
    else:
        # Kept under the original key: DEPLOYMENT.md's troubleshooting steps and
        # any external monitor set up against the old stack both read it.
        payload['mongodb'] = _check_mongo(payload)

    # Always 200, including when degraded. Render restarts an instance whose
    # health check fails, and Neon suspends an idle compute — so a 503 on a
    # database blip would turn a recoverable pause into a restart loop, at the
    # exact moment the service is least able to afford one. The status field
    # carries the bad news; the status code carries "the process is alive".
    return JsonResponse(payload)


def _check_postgres(payload: dict) -> str:
    """Is PostgreSQL reachable, and is pgvector actually installed?

    Both, because they fail independently and the second failure is the
    confusing one. A database that is up but missing the extension accepts the
    connection, serves every ordinary query, and fails only when something
    tries to search — which surfaces as "no answer found" rather than as an
    error, and looks like a retrieval problem rather than a setup one.
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            has_vector = cursor.fetchone() is not None
    except Exception as exc:
        logger.warning("Health check — PostgreSQL unavailable: %s", exc)
        payload['status'] = 'degraded'
        return 'unavailable'

    if not has_vector:
        logger.error(
            "Health check — PostgreSQL is up but the pgvector extension is "
            "missing. Vector search will return nothing. Run `manage.py migrate`."
        )
        payload['status'] = 'degraded'
        return 'connected (pgvector missing)'

    return 'connected'


def _check_mongo(payload: dict) -> str:
    try:
        from core.mongo import get_db
        get_db().command('ping')
    except Exception as exc:
        logger.warning("Health check — MongoDB unavailable: %s", exc)
        payload['status'] = 'degraded'
        return 'unavailable'

    return 'connected'
