import logging

from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


def health_check(request):
    payload = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'service': 'AI RAG Chatbot API',
    }
    try:
        from core.mongo import get_db
        get_db().command('ping')
        payload['mongodb'] = 'connected'
    except Exception as exc:
        logger.warning("Health check — MongoDB unavailable: %s", exc)
        payload['mongodb'] = 'unavailable'
        payload['status'] = 'degraded'

    return JsonResponse(payload)
