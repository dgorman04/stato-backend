# views_player.py - Player signup and management
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum, Count

from .models import Profile, Team, Player, PlayerEventStat
from .serializers import TeamSerializer, EventStatSerializer


class PlayerSignupView(APIView):
    """
    POST /api/players/signup/
    Allows a player to sign up by providing:
    - email (username)
    - password
    - player_name
    Player can join a team later after login.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""
        player_name = (request.data.get("player_name") or "").strip()

        if not email or not password or not player_name:
            return Response(
                {"detail": "email, password, and player_name are required"},
                status=400,
            )

        # Check if user already exists
        if User.objects.filter(username=email).exists():
            return Response({"detail": "User with this email already exists."}, status=400)

        # Create user and profile (no team assigned yet)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                )

                # Profile is auto-created by signal, so update it instead of creating
                profile, created = Profile.objects.get_or_create(
                    user=user,
                    defaults={
                        "team": None,
                        "role": "player",
                        "player": None,
                    }
                )
                
                # If profile already exists (from signal), update it
                if not created:
                    profile.role = "player"
                    profile.team = None
                    profile.player = None
                    profile.save()

                return Response(
                    {
                        "message": "Player account created successfully. You can join a team after logging in.",
                        "user_id": user.id,
                    },
                    status=201,
                )
        except Exception as e:
            return Response(
                {"detail": f"Error creating account: {str(e)}"},
                status=500,
            )


class PlayerJoinTeamView(APIView):
    """
    POST /api/players/join-team/
    Allows a logged-in player to join a team using team code.
    If player name is not in CSV, adds them to the squad.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = getattr(request.user, "profile", None)
        if not profile or profile.role != "player":
            return Response({"detail": "Only players can join teams."}, status=403)

        team_code = (request.data.get("team_code") or "").strip().upper()
        player_name = (request.data.get("player_name") or "").strip()

        if not team_code:
            return Response({"detail": "team_code is required."}, status=400)

        # Find team by code
        team = Team.objects.filter(team_code=team_code).first()
        if not team:
            return Response({"detail": "Invalid team code."}, status=404)

        # If player already has a team, they must leave first
        if profile.team and profile.team.id != team.id:
            return Response(
                {"detail": "You are already on a team. Please leave your current team first."},
                status=400,
            )

        # If already on this team, return success
        if profile.team and profile.team.id == team.id:
            return Response(
                {"message": "You are already on this team.", "team": TeamSerializer(team).data},
                status=200,
            )

        # Check if player name is provided
        if not player_name:
            return Response({"detail": "player_name is required."}, status=400)

        # Find or create player in team
        player = Player.objects.filter(team=team, name__iexact=player_name).first()
        
        if not player:
            # Player not in CSV, add them to squad
            player = Player.objects.create(team=team, name=player_name)

        # Check if player already has a user_profile linked to a different user
        existing_profile = Profile.objects.filter(player=player).exclude(user=request.user).first()
        if existing_profile:
            return Response(
                {"detail": "This player name is already linked to another account."},
                status=400,
            )

        # Update profile to join team
        profile.team = team
        profile.player = player
        profile.save()

        return Response(
            {
                "message": "Successfully joined team.",
                "team": TeamSerializer(team).data,
                "player": {"id": player.id, "name": player.name},
            },
            status=200,
        )


class PlayerLeaveTeamView(APIView):
    """
    POST /api/players/leave-team/
    Allows a logged-in player to leave their current team.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = getattr(request.user, "profile", None)
        if not profile or profile.role != "player":
            return Response({"detail": "Only players can leave teams."}, status=403)

        if not profile.team:
            return Response({"detail": "You are not on any team."}, status=400)

        # Fully unlink profile from team and player — they will see no team and no stats
        profile.team = None
        profile.player = None
        profile.save()

        return Response({"message": "Successfully left team."}, status=200)


class PlayerProfileView(APIView):
    """
    GET /api/players/me/
    Get player's own profile and stats
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "profile", None)
        if not profile or profile.role != "player":
            return Response({"detail": "Not a player account."}, status=403)

        player = profile.player
        if not player:
            return Response({
                "player": None,
                "team": None,
                "performance": {},
                "message": "No player linked. Join a team to see your stats.",
            }, status=200)

        # Get player stats
        stats = PlayerEventStat.objects.filter(player=player).values("event").annotate(
            total=Sum("count"),
            matches=Count("match", distinct=True),
        )

        performance = {}
        for stat in stats:
            event = stat["event"]
            performance[event] = {
                "total": stat["total"] or 0,
                "matches": stat["matches"] or 0,
                "average_per_match": (stat["total"] or 0) / (stat["matches"] or 1),
            }

        return Response({
            "player": {
                "id": player.id,
                "name": player.name,
                "team": TeamSerializer(player.team).data if player.team else None,
            },
            "team": TeamSerializer(profile.team).data if profile.team else None,
            "performance": performance,
        }, status=200)


class PlayerMeStatsView(APIView):
    """
    GET /api/players/me/stats/
    Returns only the logged-in player's stats (per match, same format as /api/stats/)
    so players never receive other team members' data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "profile", None)
        if not profile or profile.role != "player":
            return Response({"detail": "Not a player account."}, status=403)

        player = profile.player
        if not player:
            return Response([], status=200)

        qs = PlayerEventStat.objects.filter(player=player).order_by("-updated_at")
        serializer = EventStatSerializer(qs, many=True)
        return Response(serializer.data, status=200)
