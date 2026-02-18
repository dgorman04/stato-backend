"""
Unit tests for serializers we rely on: Team (has team_code), TeamSignup (creates team + manager, rejects duplicate email).
"""
from django.contrib.auth.models import User
from django.test import TestCase

from ..models import Team, Player
from ..serializers import TeamSerializer, TeamSignupSerializer


class TeamSerializerTests(TestCase):
    """TeamSerializer: used for /teams/me/ and includes team_code for sharing."""

    def setUp(self):
        self.team = Team.objects.create(club_name="Test Club", team_name="Test Team")

    def test_serializer_includes_team_code(self):
        data = TeamSerializer(self.team).data
        self.assertIn("team_code", data)
        self.assertEqual(data["club_name"], "Test Club")


class TeamSignupSerializerTests(TestCase):
    """TeamSignupSerializer: creates team and manager user; rejects duplicate email."""

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
