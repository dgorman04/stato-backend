"""
Integration tests: login and /auth/me/ (core auth flow).
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import Team, Profile


class AuthIntegrationTests(APITestCase):
    """POST /api/auth/login/ and GET /api/auth/me/ - used on every app load."""

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

    def test_login_returns_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "manager@test.com", "password": "pass1234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_me_requires_auth(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_user_and_team(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "manager@test.com")
        self.assertIsNotNone(response.data.get("team"))
        self.assertEqual(response.data["team"]["id"], self.team.id)
