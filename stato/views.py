from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated

from django.utils.dateparse import parse_datetime
from django.utils import timezone

from .models import Player, PlayerEventStat, Match, EVENT_CHOICES, PlayerEventInstance, Profile
from .serializers import EventStatSerializer, MatchSerializer


try:
    # Redis client for publishing live updates to the Node WebSocket server
    # (subscribes to the "events" channel).
    import os
    import redis

    _redis_client = redis.Redis.from_url(
        # Use REDIS_URL in production (e.g. on Railway), fall back to local.
        os.environ.get("REDIS_URL", "redis://localhost:6379"),
        decode_responses=True,
    )
except Exception:  # pragma: no cover - safe fallback if redis isn't installed / misconfigured
    _redis_client = None


EVENT_KEYS = {k for (k, _label) in EVENT_CHOICES}


def _get_team(request):
    profile = getattr(request.user, "profile", None)
    return getattr(profile, "team", None)


def _get_or_create_player(team, player_name: str):
    name = (player_name or "").strip()
    if not name:
        return None
    player, _ = Player.objects.get_or_create(team=team, name=name)
    return player


def _parse_kickoff(value):
    """
    Accepts ISO strings like:
    - 2026-01-13T18:30:00Z
    - 2026-01-13T18:30:00.000Z
    - 2026-01-13T18:30:00+00:00
    Returns aware datetime.
    """
    if not value:
        return None

    dt = parse_datetime(value)
    if not dt:
        return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    return dt


def _publish_event_to_redis(payload: dict, kind="stat"):
    """
    Publish a small JSON message to Redis so the Node WebSocket server
    can fan it out to connected clients. If Redis is not configured this
    is a no-op so the API still works in plain HTTP mode.
    """
    if not _redis_client:
        return

    try:
        import json
        msg = json.dumps({"kind": kind, "data": payload})
        _redis_client.publish("events", msg)
    except Exception:
        pass


class PerformanceInsightsView(APIView):
    """
    Simple analytics / ML-style endpoint that computes per-player metrics
    and generates plain‑English suggestions for improvement. This keeps
    the "ML" story lightweight but explainable for a 3rd‑year project.

    GET /api/analytics/insights/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        # Pull all stats for the team and build a nested map:
        # player -> event -> count
        qs = PlayerEventStat.objects.filter(team=team)

        by_player = {}
        for row in qs:
            name = row.player.name
            event = row.event
            count = int(row.count or 0)
            if name not in by_player:
                by_player[name] = {}
            by_player[name][event] = count

        insights = []

        for player_name, evs in by_player.items():
            shots_on = evs.get("shots_on_target", 0)
            shots_off = evs.get("shots_off_target", 0)
            total_shots = shots_on + shots_off
            key_passes = evs.get("key_passes", 0)
            duels_won = evs.get("duels_won", 0)
            duels_lost = evs.get("duels_lost", 0)
            fouls = evs.get("fouls", 0)
            interceptions = evs.get("interceptions", 0)
            blocks = evs.get("blocks", 0)

            # Simple scores from actual EVENT_CHOICES (shots_on_target, shots_off_target, key_passes, etc.)
            attacking_index = total_shots * 2 + key_passes * 0.5
            defensive_index = interceptions * 1.5 + blocks * 1.0 + duels_won * 0.8
            discipline_index = max(0, 100 - fouls * 5)

            suggestions = []

            # Attacking suggestions
            if total_shots < 2 and key_passes >= 3:
                suggestions.append(
                    "Good passing but low shot volume – consider encouraging more shooting opportunities."
                )
            if key_passes < 3 and total_shots >= 5:
                suggestions.append(
                    "Shots are being taken but key passes are low – work on creating clearer chances."
                )

            # Defensive suggestions
            if duels_lost > duels_won and (duels_lost + duels_won) >= 5:
                suggestions.append(
                    "More duels are being lost than won – focus on 1v1 defending and body positioning."
                )
            if interceptions + blocks < 3 and fouls >= 3:
                suggestions.append(
                    "Low interceptions/blocks but many fouls – consider improving reading of the game to defend earlier."
                )

            # Discipline
            if fouls >= 4:
                suggestions.append(
                    "Foul count is high – manage aggression and timing of challenges to avoid dangerous free kicks."
                )

            total_events = sum(evs.values())

            insights.append(
                {
                    "player": player_name,
                    "total_events": total_events,
                    "attacking_index": attacking_index,
                    "defensive_index": defensive_index,
                    "discipline_index": discipline_index,
                    "raw_events": evs,
                    "suggestions": suggestions or [
                        "Balanced contribution – maintain current habits and look for marginal gains in weak areas."
                    ],
                }
            )

        # Simple ranking by attacking_index for now
        insights.sort(key=lambda x: x["attacking_index"], reverse=True)

        return Response({"team_id": team.id, "players": insights}, status=200)


class TeamPlayersView(APIView):
    """
    GET  /api/teams/players/  -> list squad
    POST /api/teams/players/  -> replace squad with CSV names
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        players = list(team.players.order_by("name").values("id", "name"))
        return Response({"players": players, "count": len(players)}, status=200)

    def post(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        players_in = request.data.get("players", [])
        if not isinstance(players_in, list):
            return Response({"detail": "players must be a list of names"}, status=400)

        cleaned = []
        seen = set()
        for n in players_in:
            name = str(n or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(name)

        team.players.all().delete()
        Player.objects.bulk_create([Player(team=team, name=name) for name in cleaned])

        return Response({"ok": True, "count": len(cleaned)}, status=200)

    def delete(self, request, player_id):
        """
        DELETE /api/teams/players/<player_id>/
        Remove a player from the team. Also unlinks any user Profile that was
        linked to this player so they see "no team" and can rejoin with the code.
        """
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        try:
            player = Player.objects.get(id=player_id, team=team)
            # Unlink any profile that was linked to this player so they see no team
            # on home and profile until they rejoin.
            Profile.objects.filter(player=player).update(team=None, player=None)
            player.delete()
            return Response({"ok": True, "message": "Player removed from team."}, status=200)
        except Player.DoesNotExist:
            return Response({"detail": "Player not found."}, status=404)


# ----------------------------
# MATCHES
# ----------------------------
class MatchListCreateView(APIView):
    """
    GET  /api/matches/  -> list matches for team
    POST /api/matches/ -> create match
    body: { opponent, kickoff_at, analyst_name }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        qs = Match.objects.filter(team=team)
        
        # Filter by season if provided
        season = request.query_params.get("season", None)
        if season:
            qs = qs.filter(season=season)
        
        qs = qs.order_by("-kickoff_at")
        return Response(MatchSerializer(qs, many=True, context={"request": request}).data, status=200)

    def post(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        opponent = (request.data.get("opponent") or "").strip()
        kickoff_at_raw = request.data.get("kickoff_at")
        analyst_name = (request.data.get("analyst_name") or "").strip()
        formation = request.data.get("formation") or None
        opponent_formation = request.data.get("opponent_formation") or None
        season = request.data.get("season") or None
        is_home = request.data.get("is_home", True)
        goals_scored = request.data.get("goals_scored", 0)
        goals_conceded = request.data.get("goals_conceded", 0)

        if not opponent or not analyst_name:
            return Response(
                {"detail": "opponent and analyst_name are required"},
                status=400,
            )

        # Use current time if kickoff_at not provided
        if kickoff_at_raw:
            kickoff_at = _parse_kickoff(kickoff_at_raw)
            if not kickoff_at:
                return Response({"detail": "kickoff_at must be ISO datetime"}, status=400)
        else:
            kickoff_at = timezone.now()

        try:
            m = Match.objects.create(
                team=team,
                opponent=opponent,
                kickoff_at=kickoff_at,
                analyst_name=analyst_name,
                formation=formation,
                opponent_formation=opponent_formation,
                season=season,
                is_home=bool(is_home),
                goals_scored=int(goals_scored) if goals_scored else 0,
                goals_conceded=int(goals_conceded) if goals_conceded else 0,
                created_by=request.user,
            )
        except Exception as e:
            import traceback
            error_detail = str(e)
            print(f"Match creation error: {error_detail}")
            print(traceback.format_exc())
            return Response(
                {"detail": f"Failed to create match: {error_detail}"},
                status=500,
            )

        return Response(MatchSerializer(m, context={"request": request}).data, status=201)


class CurrentLiveMatchView(APIView):
    """
    GET /api/matches/current-live/
    Returns the currently live match (state in_progress or paused).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        live_match = Match.objects.filter(
            team=team,
            state__in=["in_progress", "paused", "first_half", "second_half"]
        ).order_by("-created_at").first()

        if not live_match:
            return Response({"match": None}, status=200)

        return Response({
            "match": MatchSerializer(live_match, context={"request": request}).data
        }, status=200)


class MatchDetailView(APIView):
    """
    GET /api/matches/<match_id>/
    PATCH /api/matches/<match_id>/ -> update match (e.g., goals_scored, goals_conceded)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        return Response(MatchSerializer(match, context={"request": request}).data, status=200)

    def patch(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        # Update goals if provided
        if "goals_scored" in request.data:
            try:
                match.goals_scored = int(request.data["goals_scored"])
            except (TypeError, ValueError):
                return Response({"detail": "goals_scored must be an integer."}, status=400)

        if "goals_conceded" in request.data:
            try:
                match.goals_conceded = int(request.data["goals_conceded"])
            except (TypeError, ValueError):
                return Response({"detail": "goals_conceded must be an integer."}, status=400)

        match.save()
        
        # Publish goal update to Redis for real-time updates
        if "goals_scored" in request.data or "goals_conceded" in request.data:
            _publish_event_to_redis({
                "team_id": team.id,
                "match_id": match.id,
                "goals_scored": match.goals_scored,
                "goals_conceded": match.goals_conceded,
                "type": "goal_update",
            }, kind="stat")
        
        return Response(MatchSerializer(match, context={"request": request}).data, status=200)


class MatchStatsListView(generics.ListAPIView):
    """
    GET /api/matches/<match_id>/stats/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EventStatSerializer

    def get_queryset(self):
        team = _get_team(self.request)
        match_id = self.kwargs["match_id"]
        if not team:
            return PlayerEventStat.objects.none()
        return PlayerEventStat.objects.filter(team=team, match_id=match_id).order_by("-updated_at")


class EventStatListView(generics.ListAPIView):
    """
    GET /api/stats/ -> overall stats across ALL matches
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EventStatSerializer

    def get_queryset(self):
        team = _get_team(self.request)
        if not team:
            return PlayerEventStat.objects.none()
        return PlayerEventStat.objects.filter(team=team).order_by("-updated_at")


# ----------------------------
# INCREMENT (MATCH-AWARE)
# ----------------------------
class IncrementEventForMatchView(APIView):
    """
    POST /api/matches/<match_id>/<event>/<player>/increment/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, match_id, event, player):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        if event not in EVENT_KEYS:
            return Response({"detail": "Invalid event."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        p = _get_or_create_player(team, player)
        if not p:
            return Response({"detail": "Invalid player."}, status=400)

        stat, _ = PlayerEventStat.objects.get_or_create(
            team=team,
            match=match,
            player=p,
            event=event,
            defaults={"count": 0},
        )

        stat.count += 1
        stat.save()

        # optional richer instance for timestamps + pitch zones
        second = request.data.get("second")
        zone = request.data.get("zone")
        try:
            if second is not None:
                second = int(second)
        except (TypeError, ValueError):
            second = None

        # Create event instance if table exists (gracefully skip if migrations not run yet)
        try:
            PlayerEventInstance.objects.create(
                team=team,
                match=match,
                player=p,
                event=event,
                second=second,
                zone=str(zone) if zone is not None else None,
            )
        except Exception:
            # Table might not exist yet - that's okay, the stat increment still worked
            pass

        data = {
            "team_id": team.id,
            "match_id": match.id,
            "player": p.name,
            "player_id": p.id,
            "event": stat.event,
            "count": stat.count,
            "second": second,
            "zone": zone,
        }

        # Publish to Redis so the Node WebSocket server can broadcast to clients
        _publish_event_to_redis(data)

        # Update xG if shots events are recorded
        _update_match_xg(match)

        return Response(data, status=status.HTTP_200_OK)


def _update_match_xg(match):
    """
    Calculate and update xG for a match based on shot events.
    Simplified xG model:
    - Shots on target in zones 1-3 (attacking zones): 0.3 xG each
    - Shots on target in zones 4-6 (defensive zones): 0.1 xG each
    - Shots off target: 0.05 xG each
    """
    from .models import PlayerEventInstance
    
    # Get all shot events for this match
    shots_on_target = PlayerEventInstance.objects.filter(
        match=match,
        event="shots_on_target"
    )
    shots_off_target = PlayerEventInstance.objects.filter(
        match=match,
        event="shots_off_target"
    )
    
    xg_total = 0.0
    
    # Calculate xG for shots on target based on zone
    for shot in shots_on_target:
        zone = shot.zone
        if zone in ["1", "2", "3"]:  # Attacking zones
            xg_total += 0.3
        elif zone in ["4", "5", "6"]:  # Defensive/midfield zones
            xg_total += 0.1
        else:
            xg_total += 0.2  # Default
    
    # Shots off target have lower xG
    xg_total += shots_off_target.count() * 0.05
    
    match.xg = xg_total
    match.save(update_fields=["xg"])


# ----------------------------
# LEGACY ENDPOINTS (OPTIONAL)
# ----------------------------
