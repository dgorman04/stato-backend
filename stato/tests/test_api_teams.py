"""
Integration tests: teams API (teams/me/, teams/performance-stats/, teams/signup).
"""
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import Team, Profile, Match


class TeamMeIntegrationTests(APITestCase):
    """Integration tests for GET /api/teams/me/."""

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
        self.assertEqual(response.data["club_name"], "Test Club")
        self.assertEqual(response.data["team_name"], "Test Team")
        self.assertIn("team_code", response.data)

    def test_teams_me_no_team_returns_400(self):
        user_no_team = User.objects.create_user(
            username="noteam@test.com",
            email="noteam@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=user_no_team)
        profile.team = None
        profile.save()
        self.client.force_authenticate(user=user_no_team)
        response = self.client.get("/api/teams/me/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TeamSignupIntegrationTests(APITestCase):
    """Integration tests for POST /api/teams/signup/."""

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

    def test_team_signup_duplicate_email_returns_400(self):
        User.objects.create_user(
            username="existing@test.com",
            email="existing@test.com",
            password="x",
        )
        response = self.client.post(
            "/api/teams/signup/",
            {
                "club_name": "C",
                "team_name": "T",
                "email": "existing@test.com",
                "password": "pass1234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)


class TeamPerformanceStatsIntegrationTests(APITestCase):
    """Integration tests for GET /api/teams/performance-stats/."""

    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(club_name="C", team_name="T")
        self.user = User.objects.create_user(
            username="m@test.com",
            email="m@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=self.user)
        profile.team = self.team
        profile.role = "manager"
        profile.save()
        self.user = User.objects.get(pk=self.user.pk)

    def test_performance_stats_requires_auth(self):
        response = self.client.get("/api/teams/performance-stats/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_performance_stats_returns_structure(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/teams/performance-stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn("most_used_formation", data)
        self.assertIn("goals", data)
        self.assertIn("scored", data["goals"])
        self.assertIn("conceded", data["goals"])
        self.assertIn("match_count", data)
        self.assertIn("record", data)
        self.assertIn("wins", data["record"])
        self.assertIn("draws", data["record"])
        self.assertIn("losses", data["record"])

    def test_performance_stats_no_team_returns_400(self):
        user_no_team = User.objects.create_user(
            username="n@test.com",
            email="n@test.com",
            password="pass1234",
        )
        Profile.objects.filter(user=user_no_team).update(team=None)
        self.client.force_authenticate(user=user_no_team)
        response = self.client.get("/api/teams/performance-stats/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
