     """
Unit tests for custom permissions: IsManager, IsEnabled.
"""
from django.test import TestCase
from django.contrib.auth.models import User, AnonymousUser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from ..models import Team, Profile
from ..permissions import IsManager, IsEnabled


class IsManagerPermissionTests(TestCase):
    """Unit tests for IsManager permission."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.team = Team.objects.create(club_name="C", team_name="T")

    def test_unauthenticated_denied(self):
        request = self.factory.get("/api/teams/me/")
        request.user = AnonymousUser()
        perm = IsManager()
        self.assertFalse(perm.has_permission(request, None))

    def test_authenticated_no_profile_denied(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        # Remove profile to simulate missing profile
        Profile.objects.filter(user=user).delete()
        request = self.factory.get("/api/teams/me/")
        request.user = user
        perm = IsManager()
        self.assertFalse(perm.has_permission(request, None))

    def test_manager_allowed(self):
        user = User.objects.create_user(username="m@test.com", email="m@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.team = self.team
        profile.role = "manager"
        profile.save()
        request = self.factory.get("/api/teams/me/")
        # Use a fresh user instance so .profile is loaded from DB with updated role
        request.user = User.objects.get(pk=user.pk)
        perm = IsManager()
        self.assertTrue(perm.has_permission(request, None))

    def test_analyst_denied(self):
        user = User.objects.create_user(username="a@test.com", email="a@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.team = self.team
        profile.role = "analyst"
        profile.save()
        request = self.factory.get("/api/teams/me/")
        request.user = user
        perm = IsManager()
        self.assertFalse(perm.has_permission(request, None))

    def test_player_denied(self):
        user = User.objects.create_user(username="p@test.com", email="p@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.role = "player"
        profile.save()
        request = self.factory.get("/api/teams/me/")
        request.user = user
        perm = IsManager()
        self.assertFalse(perm.has_permission(request, None))


class IsEnabledPermissionTests(TestCase):
    """Unit tests for IsEnabled permission (always True)."""

    def test_returns_true(self):
        perm = IsEnabled()
        request = APIRequestFactory().get("/")
        request.user = User()
        self.assertTrue(perm.has_permission(request, None))
