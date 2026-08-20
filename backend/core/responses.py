import math

from rest_framework import status as http_status
from rest_framework.response import Response


class APIResponse:
    @staticmethod
    def success(data=None, message: str = 'Success',
                status_code: int = http_status.HTTP_200_OK) -> Response:
        return Response(
            {'success': True, 'message': message, 'data': data},
            status=status_code,
        )

    @staticmethod
    def created(data=None, message: str = 'Created successfully') -> Response:
        return APIResponse.success(data, message, http_status.HTTP_201_CREATED)

    @staticmethod
    def error(message: str = 'An error occurred.', errors=None,
              status_code: int = http_status.HTTP_400_BAD_REQUEST) -> Response:
        return Response(
            {'success': False, 'message': message, 'errors': errors},
            status=status_code,
        )

    @staticmethod
    def not_found(message: str = 'Resource not found.') -> Response:
        return APIResponse.error(message, status_code=http_status.HTTP_404_NOT_FOUND)

    @staticmethod
    def unauthorized(message: str = 'Authentication required.') -> Response:
        return APIResponse.error(message, status_code=http_status.HTTP_401_UNAUTHORIZED)

    @staticmethod
    def forbidden(message: str = 'Permission denied.') -> Response:
        return APIResponse.error(message, status_code=http_status.HTTP_403_FORBIDDEN)

    @staticmethod
    def server_error(message: str = 'Internal server error.') -> Response:
        return APIResponse.error(message, status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

    @staticmethod
    def paginated(data, total: int, page: int, page_size: int,
                  message: str = 'Success') -> Response:
        return Response(
            {
                'success': True,
                'message': message,
                'data': data,
                'pagination': {
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': math.ceil(total / page_size) if page_size else 1,
                    'has_next': page * page_size < total,
                    'has_previous': page > 1,
                },
            },
            status=http_status.HTTP_200_OK,
        )
