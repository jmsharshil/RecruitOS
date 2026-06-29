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
        return bool(request.user and request.user.is_authenticated and (request.user.role == 'admin' or getattr(obj, 'created_by', None) == request.user))
