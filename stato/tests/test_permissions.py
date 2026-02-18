"""
Unit tests for IsManager permission: unauthenticated users are denied, managers are allowed.
"""
from django.test import TestCase
from django.contrib.auth.models import User, AnonymousUser
from rest_framework.test import APIRequestFactory

from ..models import Team, Profile
from ..permissions import IsManager


class IsManagerPermissionTests(TestCase):
    """IsManager: used on some manager-only endpoints."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.team = Team.objects.create(club_name="C", team_name="T")

    def test_unauthenticated_denied(self):
        request = self.factory.get("/api/teams/me/")
        request.user = AnonymousUser()
        self.assertFalse(IsManager().has_permission(request, None))

    def test_manager_allowed(self):
        user = User.objects.create_user(username="m@test.com", email="m@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.team = self.team
        profile.role = "manager"
        profile.save()
        request = self.factory.get("/api/teams/me/")
        request.user = User.objects.get(pk=user.pk)
        self.assertTrue(IsManager().has_permission(request, None))
