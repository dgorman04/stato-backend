# permissions.py
from rest_framework.permissions import BasePermission

class IsManager(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, "profile", None)
        if not profile:
            return False
        # Manager and analyst are treated the same; accept both for backwards compatibility with existing DB rows.
        return profile.role in ("manager", "analyst")
