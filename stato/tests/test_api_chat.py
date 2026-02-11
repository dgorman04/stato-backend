"""
Integration tests: chat API (GET/POST /api/chat/messages/).
"""
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import Team, Profile, Player, Match, ChatMessage


class ChatAPIIntegrationTests(APITestCase):
    """Integration tests for /api/chat/messages/."""

    def setUp(self):
        self.client = APIClient()
        self.team = Team.objects.create(club_name="Test Club", team_name="Test Team")
        self.manager = User.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=self.manager)
        profile.team = self.team
        profile.role = "manager"
        profile.enabled = True
        profile.save()
        # Ensure next request sees updated profile (avoid reverse relation cache)
        self.manager = User.objects.get(pk=self.manager.pk)

    def test_chat_get_requires_auth(self):
        response = self.client.get("/api/chat/messages/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chat_get_no_team_returns_400(self):
        user_no_team = User.objects.create_user(
            username="noteam@test.com",
            email="noteam@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=user_no_team)
        profile.team = None
        profile.role = "manager"
        profile.save()
        self.client.force_authenticate(user=user_no_team)
        response = self.client.get("/api/chat/messages/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        self.assertIn("team", response.data["detail"].lower())

    def test_chat_get_returns_empty_list(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get("/api/chat/messages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 0)

    def test_chat_post_creates_message(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            "/api/chat/messages/",
            {"message": "Hello team"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["sender"], "manager@test.com")
        self.assertEqual(response.data["message"], "Hello team")
        self.assertIn("timestamp", response.data)
        self.assertTrue(ChatMessage.objects.filter(team=self.team, message="Hello team").exists())

    def test_chat_post_empty_message_returns_400(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            "/api/chat/messages/",
            {"message": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_chat_get_returns_messages_from_all_roles(self):
        ChatMessage.objects.create(
            team=self.team,
            match=None,
            sender=self.manager,
            sender_role="manager",
            message="First",
        )
        analyst = User.objects.create_user(
            username="analyst@test.com",
            email="analyst@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=analyst)
        profile.team = self.team
        profile.role = "analyst"
        profile.save()
        ChatMessage.objects.create(
            team=self.team,
            match=None,
            sender=analyst,
            sender_role="analyst",
            message="Second",
        )
        self.client.force_authenticate(user=self.manager)
        response = self.client.get("/api/chat/messages/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        messages = response.data
        self.assertEqual(len(messages), 2)
        texts = [m["message"] for m in messages]
        self.assertIn("First", texts)
        self.assertIn("Second", texts)

    def test_player_with_team_can_access_chat(self):
        player_user = User.objects.create_user(
            username="player@test.com",
            email="player@test.com",
            password="pass1234",
        )
        profile = Profile.objects.get(user=player_user)
        profile.team = self.team
        profile.role = "player"
        player = Player.objects.create(team=self.team, name="Test Player")
        profile.player = player
        profile.save()
        player_user = User.objects.get(pk=player_user.pk)
        self.client.force_authenticate(user=player_user)
        get_resp = self.client.get("/api/chat/messages/")
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        post_resp = self.client.post(
            "/api/chat/messages/",
            {"message": "Player says hi"},
            format="json",
        )
        self.assertEqual(post_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(post_resp.data["sender_role"], "player")
