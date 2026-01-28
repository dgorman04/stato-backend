# permissions.py
from rest_framework.permissions import BasePermission

class IsManager(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, "profile", None)
        if not profile:
            return False
        return profile.role == "manager"

class IsEnabled(BasePermission):
    def has_permission(self, request, view):
        return True
