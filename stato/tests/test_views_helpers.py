"""
Unit tests for view helper functions: _get_team, _parse_kickoff.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory

from ..models import Team, Profile
from ..views import _get_team, _parse_kickoff


class GetTeamHelperTests(TestCase):
    """Unit tests for _get_team(request)."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.team = Team.objects.create(club_name="C", team_name="T")

    def test_returns_team_when_profile_has_team(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.team = self.team
        profile.save()
        request = self.factory.get("/api/teams/me/")
        # Use a fresh user instance so .profile.team is loaded from DB
        request.user = User.objects.get(pk=user.pk)
        self.assertEqual(_get_team(request), self.team)

    def test_returns_none_when_profile_has_no_team(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.team = None
        profile.save()
        request = self.factory.get("/api/teams/me/")
        request.user = user
        self.assertIsNone(_get_team(request))

    def test_returns_none_when_user_has_no_profile(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        Profile.objects.filter(user=user).delete()
        request = self.factory.get("/api/teams/me/")
        request.user = user
        self.assertIsNone(_get_team(request))


class ParseKickoffHelperTests(TestCase):
    """Unit tests for _parse_kickoff(value)."""

    def test_none_returns_none(self):
        self.assertIsNone(_parse_kickoff(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_kickoff(""))

    def test_valid_iso_returns_aware_datetime(self):
        dt = _parse_kickoff("2026-01-13T18:30:00Z")
        self.assertIsNotNone(dt)
        from django.utils import timezone
        self.assertTrue(timezone.is_aware(dt))

    def test_valid_iso_with_ms(self):
        dt = _parse_kickoff("2026-01-13T18:30:00.000Z")
        self.assertIsNotNone(dt)

    def test_invalid_string_returns_none(self):
        self.assertIsNone(_parse_kickoff("not-a-date"))
