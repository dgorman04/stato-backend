"""
Unit tests for serializers and validation logic.
"""
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory
from django.test import TestCase

from ..models import Team, Profile, Player, Match
from ..serializers import (
    TeamSerializer,
    TeamSignupSerializer,
    MatchSerializer,
    EventInstanceSerializer,
)
from django.utils import timezone


class TeamSerializerTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(club_name="Test Club", team_name="Test Team")

    def test_serializer_includes_team_code(self):
        data = TeamSerializer(self.team).data
        self.assertIn("team_code", data)
        self.assertIn("club_name", data)
        self.assertIn("team_name", data)
        self.assertEqual(data["club_name"], "Test Club")

    def test_players_count_read_only(self):
        Player.objects.create(team=self.team, name="Player One")
        Player.objects.create(team=self.team, name="Player Two")
        data = TeamSerializer(self.team).data
        self.assertEqual(data["players_count"], 2)


class TeamSignupSerializerTests(TestCase):
    def test_valid_data_creates_team_and_user(self):
        data = {
            "club_name": "New Club",
            "team_name": "New Team",
            "email": "manager@test.com",
            "password": "securepass123",
            "players": ["Alice", "Bob"],
        }
        serializer = TeamSignupSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        result = serializer.save()
        self.assertIn("team", result)
        self.assertEqual(result["team"].club_name, "New Club")
        self.assertTrue(User.objects.filter(username="manager@test.com").exists())
        self.assertEqual(Player.objects.filter(team=result["team"]).count(), 2)

    def test_duplicate_email_invalid(self):
        User.objects.create_user(username="existing@test.com", email="existing@test.com", password="x")
        data = {
            "club_name": "C",
            "team_name": "T",
            "email": "existing@test.com",
            "password": "pass1234",
        }
        serializer = TeamSignupSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

    def test_short_password_invalid(self):
        data = {
            "club_name": "C",
            "team_name": "T",
            "email": "new@test.com",
            "password": "short",
        }
        serializer = TeamSignupSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)


class MatchSerializerTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(club_name="C", team_name="T")
        self.match = Match.objects.create(
            team=self.team,
            opponent="Rivals",
            kickoff_at=timezone.now(),
            analyst_name="Analyst",
            state="not_started",
            is_home=True,
        )
        self.factory = APIRequestFactory()

    def test_has_recording_false_without_recording(self):
        request = self.factory.get("/api/matches/1/")
        serializer = MatchSerializer(self.match, context={"request": request})
        data = serializer.data
        self.assertFalse(data["has_recording"])
        self.assertIsNone(data["recording_url"])

    def test_serializer_includes_expected_fields(self):
        request = self.factory.get("/api/matches/1/")
        serializer = MatchSerializer(self.match, context={"request": request})
        data = serializer.data
        for field in ["id", "opponent", "state", "formation", "is_home", "goals_scored", "goals_conceded"]:
            self.assertIn(field, data)
