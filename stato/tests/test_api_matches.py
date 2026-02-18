"""
Integration tests: GET /api/matches/ and timer (start match).
"""
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import Team, Profile, Match


class MatchesIntegrationTests(APITestCase):
    """Match list and timer - manager sees their matches and can start the clock."""

    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(club_name="Test Club", team_name="Test Team")
        self.user = User.objects.create_user(username="manager@test.com", email="manager@test.com", password="pass1234")
        profile = Profile.objects.get(user=self.user)
        profile.team = self.team
        profile.role = "manager"
        profile.enabled = True
        profile.save()
        self.user = User.objects.get(pk=self.user.pk)
        self.match = Match.objects.create(
            team=self.team,
            opponent="Rivals",
            kickoff_at=timezone.now(),
            analyst_name="Manager",
            state="not_started",
            is_home=True,
        )

    def test_match_list_requires_auth(self):
        response = self.client.get("/api/matches/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_match_list_returns_team_matches(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/matches/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertGreaterEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["opponent"], "Rivals")

    def test_timer_start_updates_match_state(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f"/api/matches/{self.match.id}/timer/",
            {"action": "start"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.match.refresh_from_db()
        self.assertEqual(self.match.state, "in_progress")
        self.assertEqual(self.match.elapsed_seconds, 0)
