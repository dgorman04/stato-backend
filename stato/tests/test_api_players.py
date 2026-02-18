"""
Integration tests: player signup and join-team (main player flows).
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import Team, Profile


class PlayerSignupIntegrationTests(APITestCase):
    """POST /api/players/signup/ - creates a player account."""

    def setUp(self):
        self.client = APIClient()

    def test_signup_creates_user_and_player_profile(self):
        response = self.client.post(
            "/api/players/signup/",
            {
                "email": "newplayer@test.com",
                "password": "securepass123",
                "player_name": "New Player",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user_id", response.data)
        user = User.objects.get(username="newplayer@test.com")
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.role, "player")
        self.assertIsNone(profile.team)


class PlayerJoinTeamIntegrationTests(APITestCase):
    """POST /api/players/join-team/ - player joins with team code."""

    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(club_name="Test Club", team_name="Test Team")
        self.player_user = User.objects.create_user(
            username="player@test.com",
            email="player@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=self.player_user)
        profile.role = "player"
        profile.team = None
        profile.player = None
        profile.save()

    def test_join_team_requires_auth(self):
        response = self.client.post(
            "/api/players/join-team/",
            {"team_code": self.team.team_code, "player_name": "New One"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_join_team_invalid_code_returns_404(self):
        self.client.force_authenticate(user=self.player_user)
        response = self.client.post(
            "/api/players/join-team/",
            {"team_code": "INVALID", "player_name": "New One"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    def test_join_team_success(self):
        self.client.force_authenticate(user=self.player_user)
        response = self.client.post(
            "/api/players/join-team/",
            {"team_code": self.team.team_code, "player_name": "New One"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("team", response.data)
        self.assertEqual(response.data["team"]["id"], self.team.id)
        profile = Profile.objects.get(user=self.player_user)
        self.assertEqual(profile.team_id, self.team.id)
        self.assertIsNotNone(profile.player_id)
