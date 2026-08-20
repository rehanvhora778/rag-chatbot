from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminUser(BasePermission):
    message = 'Admin access required.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsOwner(BasePermission):
    message = 'You do not have permission to access this resource.'

    def has_object_permission(self, request, view, obj):
        user_id = str(request.user.id)
        if isinstance(obj, dict):
            return str(obj.get('user_id', '')) == user_id
        return str(getattr(obj, 'user_id', '')) == user_id


class IsOwnerOrAdmin(BasePermission):
    message = 'You do not have permission to access this resource.'

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        user_id = str(request.user.id)
        if isinstance(obj, dict):
            return str(obj.get('user_id', '')) == user_id
        return str(getattr(obj, 'user_id', '')) == user_id


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
