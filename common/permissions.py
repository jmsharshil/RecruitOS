from rest_framework.permissions import BasePermission

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')

class IsManager(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'manager')

class IsRecruiter(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'recruiter')

class IsAdminOrManager(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role in ('admin', 'manager'))

class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == 'admin':
            return True
        if getattr(obj, 'created_by', None) == request.user:
            return True

        # Managers can VIEW admin/system-created users (read-only)
        from rest_framework.permissions import SAFE_METHODS
        if request.method in SAFE_METHODS and request.user.role == 'manager':
            creator = getattr(obj, 'created_by', None)
            if creator is None or getattr(creator, 'role', None) == 'admin':
                return True

        return False
