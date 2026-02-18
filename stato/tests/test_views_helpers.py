"""
Unit tests for view helpers: _get_team (used by team-scoped views) and _parse_kickoff (match kickoff date).
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from ..models import Team, Profile
from ..views import _get_team, _parse_kickoff


class GetTeamHelperTests(TestCase):
    """_get_team(request) returns the user's team if they have one, else None."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.team = Team.objects.create(club_name="C", team_name="T")

    def test_returns_team_when_profile_has_team(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.team = self.team
        profile.save()
        request = self.factory.get("/api/teams/me/")
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


class ParseKickoffHelperTests(TestCase):
    """_parse_kickoff(value) parses ISO date strings for match kickoff."""

    def test_valid_iso_returns_aware_datetime(self):
        dt = _parse_kickoff("2026-01-13T18:30:00Z")
        self.assertIsNotNone(dt)
        self.assertTrue(timezone.is_aware(dt))
