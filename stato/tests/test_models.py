"""
Unit tests for stato models: Team, Profile, Player, Match, ChatMessage, and constraints.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from ..models import (
    Team,
    Profile,
    Player,
    Match,
    ChatMessage,
    PlayerEventStat,
    PlayerEventInstance,
    EVENT_CHOICES,
)
from django.utils import timezone


class TeamModelTests(TestCase):
    """Unit tests for Team model."""

    def test_team_str(self):
        team = Team.objects.create(club_name="Test Club", team_name="Test Team")
        self.assertEqual(str(team), "Test Club — Test Team")

    def test_team_code_auto_generated_on_save(self):
        team = Team.objects.create(club_name="C", team_name="T")
        self.assertIsNotNone(team.team_code)
        self.assertEqual(len(team.team_code), 6)
        self.assertTrue(team.team_code.isalnum())
        self.assertEqual(team.team_code.upper(), team.team_code)

    def test_team_code_unique(self):
        team1 = Team.objects.create(club_name="C1", team_name="T1")
        team2 = Team.objects.create(club_name="C2", team_name="T2")
        self.assertNotEqual(team1.team_code, team2.team_code)

    def test_team_code_preserved_when_set(self):
        team = Team(club_name="C", team_name="T", team_code="CUSTOM1")
        team.save()
        self.assertEqual(team.team_code, "CUSTOM1")


class ProfileModelTests(TestCase):
    """Unit tests for Profile model and User signal."""

    def test_profile_created_on_user_save(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.role, "analyst")
        self.assertTrue(profile.enabled)

    def test_profile_str(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        profile = Profile.objects.get(user=user)
        profile.role = "manager"
        profile.save()
        self.assertIn("u@test.com", str(profile))
        self.assertIn("manager", str(profile))


class PlayerModelTests(TestCase):
    """Unit tests for Player model and unique constraint."""

    def setUp(self):
        self.team = Team.objects.create(club_name="C", team_name="T")

    def test_player_str(self):
        player = Player.objects.create(team=self.team, name="Alice")
        self.assertIn("Alice", str(player))
        self.assertIn(str(self.team.id), str(player))

    def test_unique_team_player_name(self):
        Player.objects.create(team=self.team, name="Alice")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Player.objects.create(team=self.team, name="Alice")

    def test_same_name_different_teams_allowed(self):
        team2 = Team.objects.create(club_name="C2", team_name="T2")
        Player.objects.create(team=self.team, name="Alice")
        player2 = Player.objects.create(team=team2, name="Alice")
        self.assertNotEqual(player2.team_id, self.team.id)


class MatchModelTests(TestCase):
    """Unit tests for Match model."""

    def setUp(self):
        self.team = Team.objects.create(club_name="C", team_name="T")

    def test_match_str(self):
        match = Match.objects.create(
            team=self.team,
            opponent="Rivals",
            kickoff_at=timezone.now(),
            analyst_name="Analyst",
            state="not_started",
            is_home=True,
        )
        self.assertIn("Rivals", str(match))
        self.assertIn("T", str(match))

    def test_match_default_state(self):
        match = Match.objects.create(
            team=self.team,
            opponent="R",
            kickoff_at=timezone.now(),
            analyst_name="A",
            is_home=True,
        )
        self.assertEqual(match.state, "not_started")
        self.assertEqual(match.elapsed_seconds, 0)
        self.assertEqual(match.goals_scored, 0)
        self.assertEqual(match.goals_conceded, 0)


class ChatMessageModelTests(TestCase):
    """Unit tests for ChatMessage model."""

    def setUp(self):
        self.team = Team.objects.create(club_name="C", team_name="T")
        self.user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        self.match = Match.objects.create(
            team=self.team,
            opponent="R",
            kickoff_at=timezone.now(),
            analyst_name="A",
            state="not_started",
            is_home=True,
        )

    def test_chat_message_str(self):
        msg = ChatMessage.objects.create(
            team=self.team,
            match=None,
            sender=self.user,
            sender_role="manager",
            message="Hello world",
        )
        self.assertIn("u@test.com", str(msg))
        self.assertIn("Hello", str(msg))

    def test_chat_message_optional_match(self):
        msg = ChatMessage.objects.create(
            team=self.team,
            match=self.match,
            sender=self.user,
            sender_role="analyst",
            message="Test",
        )
        self.assertEqual(msg.match_id, self.match.id)


class PlayerEventStatModelTests(TestCase):
    """Unit tests for PlayerEventStat unique constraint."""

    def setUp(self):
        self.team = Team.objects.create(club_name="C", team_name="T")
        self.player = Player.objects.create(team=self.team, name="P1")
        self.match = Match.objects.create(
            team=self.team,
            opponent="R",
            kickoff_at=timezone.now(),
            analyst_name="A",
            state="not_started",
            is_home=True,
        )

    def test_unique_team_match_player_event(self):
        PlayerEventStat.objects.create(
            team=self.team,
            match=self.match,
            player=self.player,
            event="shots_on_target",
            count=1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlayerEventStat.objects.create(
                    team=self.team,
                    match=self.match,
                    player=self.player,
                    event="shots_on_target",
                    count=2,
                )
