"""
Integration tests: GET /api/teams/me/ and POST /api/teams/signup/.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import Team, Profile


class TeamMeIntegrationTests(APITestCase):
    """GET /api/teams/me/ - returns the logged-in user's team (with team_code)."""

    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(club_name="Test Club", team_name="Test Team")
        self.user = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=self.user)
        profile.team = self.team
        profile.role = "manager"
        profile.enabled = True
        profile.save()
        self.user = User.objects.get(pk=self.user.pk)

    def test_teams_me_requires_auth(self):
        response = self.client.get("/api/teams/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_teams_me_returns_team(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/teams/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.team.id)
        self.assertIn("team_code", response.data)


class TeamSignupIntegrationTests(APITestCase):
    """POST /api/teams/signup/ - creates team and manager account (and optional players)."""

    def setUp(self):
        self.client = APIClient()

    def test_team_signup_creates_team_and_manager(self):
        response = self.client.post(
            "/api/teams/signup/",
            {
                "club_name": "New Club",
                "team_name": "New Team",
                "email": "manager@new.com",
                "password": "securepass123",
                "players": ["Alice", "Bob"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("team", response.data)
        self.assertEqual(response.data["team"]["club_name"], "New Club")
        self.assertTrue(User.objects.filter(username="manager@new.com").exists())
        team = Team.objects.get(club_name="New Club")
        self.assertEqual(team.players.count(), 2)
