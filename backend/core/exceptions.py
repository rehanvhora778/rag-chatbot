import logging

from django.conf import settings
from pymongo.errors import PyMongoError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        detail = response.data
        if isinstance(detail, dict) and 'detail' in detail:
            message = str(detail['detail'])
        elif isinstance(detail, list) and detail:
            message = str(detail[0])
        else:
            message = 'An error occurred.'

        response.data = {
            'success': False,
            'message': message,
            'errors': detail,
            'status_code': response.status_code,
        }
        return response

    if isinstance(exc, PyMongoError):
        logger.error("MongoDB error: %s", exc, exc_info=True)
        return Response(
            {
                'success': False,
                'message': 'A database error occurred.',
                'errors': str(exc) if settings.DEBUG else None,
                'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return Response(
        {
            'success': False,
            'message': 'An internal server error occurred.',
            'errors': str(exc) if settings.DEBUG else None,
            'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
