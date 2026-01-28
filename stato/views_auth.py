# views_auth.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .serializers import TeamSerializer


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "profile", None)
        team = getattr(profile, "team", None)

        return Response(
            {
                "email": request.user.email,
                "role": getattr(profile, "role", "manager"),
                "team": TeamSerializer(team).data if team else None,
                "team_id": team.id if team else None,
            },
            status=200,
        )
