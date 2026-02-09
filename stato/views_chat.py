# views_chat.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta

from .models import ChatMessage, Team, Match
from .views import _get_team


class ChatMessagesView(APIView):
    """
    GET /api/chat/messages/ - Get recent team chat messages (manager, analyst, player with team)
    POST /api/chat/messages/ - Send a new message (manager, analyst, player with team)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match_id = request.query_params.get("match_id")
        
        # Get last 50 messages from all roles (manager, analyst, player)
        queryset = ChatMessage.objects.filter(team=team)
        if match_id:
            try:
                match = Match.objects.get(id=match_id, team=team)
                queryset = queryset.filter(match=match)
            except Match.DoesNotExist:
                pass

        messages = queryset[:50]
        
        return Response([
            {
                "id": msg.id,
                "sender": msg.sender.username,
                "sender_role": msg.sender_role,
                "message": msg.message,
                "timestamp": msg.created_at.isoformat(),
            }
            for msg in reversed(messages)
        ], status=200)

    def post(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        profile = getattr(request.user, "profile", None)
        if not profile:
            return Response({"detail": "No profile found."}, status=400)

        message_text = (request.data.get("message") or "").strip()
        if not message_text:
            return Response({"detail": "Message cannot be empty."}, status=400)

        match_id = request.data.get("match_id")
        match = None
        if match_id:
            try:
                match = Match.objects.get(id=match_id, team=team)
            except Match.DoesNotExist:
                pass

        # Create message
        chat_message = ChatMessage.objects.create(
            team=team,
            match=match,
            sender=request.user,
            sender_role=profile.role,
            message=message_text,
        )

        # Publish to Redis for WebSocket broadcast
        from .views import _publish_event_to_redis
        _publish_event_to_redis(
            {
                "id": chat_message.id,
                "sender": request.user.username,
                "sender_role": profile.role,
                "message": message_text,
                "timestamp": chat_message.created_at.isoformat(),
                "team_id": team.id,
                "match_id": match.id if match else None,
            },
            kind="chat"
        )

        return Response({
            "id": chat_message.id,
            "sender": request.user.username,
            "sender_role": profile.role,
            "message": message_text,
            "timestamp": chat_message.created_at.isoformat(),
        }, status=201)
