"""
Integration tests: player API (signup, join-team, leave-team, me, me/stats).
"""
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import Team, Profile, Player, Match, PlayerEventStat


class PlayerSignupIntegrationTests(APITestCase):
    """Integration tests for POST /api/players/signup/."""

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
        self.assertTrue(User.objects.filter(username="newplayer@test.com").exists())
        user = User.objects.get(username="newplayer@test.com")
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.role, "player")
        self.assertIsNone(profile.team)

    def test_signup_duplicate_email_returns_400(self):
        User.objects.create_user(
            username="existing@test.com",
            email="existing@test.com",
            password="x",
        )
        response = self.client.post(
            "/api/players/signup/",
            {
                "email": "existing@test.com",
                "password": "pass1234",
                "player_name": "Someone",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_signup_missing_fields_returns_400(self):
        response = self.client.post(
            "/api/players/signup/",
            {"email": "a@test.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PlayerJoinLeaveIntegrationTests(APITestCase):
    """Integration tests for join-team and leave-team."""

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

    def test_join_team_missing_player_name_returns_400(self):
        self.client.force_authenticate(user=self.player_user)
        response = self.client.post(
            "/api/players/join-team/",
            {"team_code": self.team.team_code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manager_cannot_join_team(self):
        manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="pass1234",
        )
        Profile.objects.filter(user=manager).update(role="manager", team=self.team)
        self.client.force_authenticate(user=manager)
        response = self.client.post(
            "/api/players/join-team/",
            {"team_code": self.team.team_code, "player_name": "M"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_leave_team_requires_player(self):
        self.client.force_authenticate(user=self.player_user)
        response = self.client.post("/api/players/leave-team/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not on any team", response.data["detail"].lower())

    def test_leave_team_success(self):
        player = Player.objects.create(team=self.team, name="P1")
        profile = Profile.objects.get(user=self.player_user)
        profile.team = self.team
        profile.player = player
        profile.save()
        self.player_user = User.objects.get(pk=self.player_user.pk)
        self.client.force_authenticate(user=self.player_user)
        response = self.client.post("/api/players/leave-team/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = Profile.objects.get(user=self.player_user)
        self.assertIsNone(profile.team_id)
        self.assertIsNone(profile.player_id)


class PlayerMeIntegrationTests(APITestCase):
    """Integration tests for GET /api/players/me/ and /api/players/me/stats/."""

    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(club_name="C", team_name="T")
        self.player_user = User.objects.create_user(
            username="p@test.com",
            email="p@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=self.player_user)
        profile.role = "player"
        profile.team = None
        profile.player = None
        profile.save()
        # Ensure client sees updated profile (fresh user instance)
        self.player_user = User.objects.get(pk=self.player_user.pk)

    def test_me_requires_auth(self):
        response = self.client.get("/api/players/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_no_player_returns_null_team(self):
        self.client.force_authenticate(user=self.player_user)
        response = self.client.get("/api/players/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data.get("player"))
        self.assertIsNone(response.data.get("team"))

    def test_me_with_team_returns_player_and_team(self):
        player = Player.objects.create(team=self.team, name="Star")
        profile = Profile.objects.get(user=self.player_user)
        profile.team = self.team
        profile.player = player
        profile.save()
        self.player_user = User.objects.get(pk=self.player_user.pk)
        self.client.force_authenticate(user=self.player_user)
        response = self.client.get("/api/players/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["player"]["name"], "Star")
        self.assertEqual(response.data["team"]["id"], self.team.id)
        self.assertIn("performance", response.data)

    def test_me_stats_returns_empty_when_no_player(self):
        self.client.force_authenticate(user=self.player_user)
        response = self.client.get("/api/players/me/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_me_stats_returns_player_stats(self):
        match = Match.objects.create(
            team=self.team,
            opponent="R",
            kickoff_at=timezone.now(),
            analyst_name="A",
            state="finished",
            is_home=True,
        )
        player = Player.objects.create(team=self.team, name="Star")
        profile = Profile.objects.get(user=self.player_user)
        profile.team = self.team
        profile.player = player
        profile.save()
        self.player_user = User.objects.get(pk=self.player_user.pk)
        PlayerEventStat.objects.create(
            team=self.team,
            match=match,
            player=player,
            event="shots_on_target",
            count=3,
        )
        self.client.force_authenticate(user=self.player_user)
        response = self.client.get("/api/players/me/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertGreaterEqual(len(response.data), 1)

    def test_manager_cannot_access_players_me(self):
        manager = User.objects.create_user(
            username="m@test.com",
            email="m@test.com",
            password="pass1234",
        )
        Profile.objects.filter(user=manager).update(role="manager", team=self.team)
        self.client.force_authenticate(user=manager)
        response = self.client.get("/api/players/me/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
