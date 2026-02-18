"""
Unit tests for key models: Team (code), Profile (signal), Player (unique name), Match (defaults), ChatMessage, PlayerEventStat (constraint).
We only test the behaviour we rely on (e.g. team code exists and is unique, profile created when user is).
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
)
from django.utils import timezone


class TeamModelTests(TestCase):
    """Team: code is auto-generated and unique."""

    def test_team_code_auto_generated_on_save(self):
        team = Team.objects.create(club_name="C", team_name="T")
        self.assertIsNotNone(team.team_code)
        self.assertEqual(len(team.team_code), 6)

    def test_team_code_unique(self):
        team1 = Team.objects.create(club_name="C1", team_name="T1")
        team2 = Team.objects.create(club_name="C2", team_name="T2")
        self.assertNotEqual(team1.team_code, team2.team_code)


class ProfileModelTests(TestCase):
    """Profile is created automatically when a User is created (Django signal)."""

    def test_profile_created_on_user_save(self):
        user = User.objects.create_user(username="u@test.com", email="u@test.com", password="pass")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        profile = Profile.objects.get(user=user)
        self.assertTrue(profile.enabled)


class PlayerModelTests(TestCase):
    """Player: same name cannot appear twice in the same team (unique constraint)."""

    def setUp(self):
        self.team = Team.objects.create(club_name="C", team_name="T")

    def test_unique_team_player_name(self):
        Player.objects.create(team=self.team, name="Alice")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Player.objects.create(team=self.team, name="Alice")


class MatchModelTests(TestCase):
    """Match: default state and timer values."""

    def setUp(self):
        self.team = Team.objects.create(club_name="C", team_name="T")

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


class ChatMessageModelTests(TestCase):
    """ChatMessage: match is optional (team-wide or match-specific)."""

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

    def test_chat_message_optional_match(self):
        msg = ChatMessage.objects.create(
            team=self.team,
            match=self.match,
            sender=self.user,
            sender_role="manager",
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
