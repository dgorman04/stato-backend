from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce

from .models import Match, PlayerEventStat, ZoneAnalysis, PlayerEventInstance, Team
from .serializers import ZoneAnalysisSerializer, TeamSignupSerializer, TeamSerializer


def _get_team(request):
    profile = getattr(request.user, "profile", None)
    return getattr(profile, "team", None)


class TeamSignupView(APIView):
    """
    POST /api/teams/signup/
    Create a new team and manager account
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TeamSignupSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response({
                "message": "Team created successfully",
                "team": TeamSerializer(result["team"]).data,
            }, status=201)
        return Response(serializer.errors, status=400)


class TeamMeView(APIView):
    """
    GET /api/teams/me/
    Get current user's team information
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)
        return Response(TeamSerializer(team).data, status=200)


class TeamPerformanceStatsView(APIView):
    """
    GET /api/teams/performance-stats/
    Returns team-level performance statistics across all matches:
    - Most used formation
    - Total goals scored/conceded
    - Total xG/xG against
    - Match count
    - Win/draw/loss record
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        season = request.query_params.get("season", None)

        # Include all matches (not just finished/live) to show all goals
        matches_qs = Match.objects.filter(team=team)
        if season:
            matches_qs = matches_qs.filter(season=season)

        matches = matches_qs

        # Most used formation
        formation_counts = matches.exclude(formation__isnull=True).exclude(formation="").values("formation").annotate(
            count=Count("id")
        ).order_by("-count")
        most_used_formation = formation_counts.first()["formation"] if formation_counts else None

        # Goals
        total_goals_scored = matches.aggregate(total=Sum("goals_scored"))["total"] or 0
        total_goals_conceded = matches.aggregate(total=Sum("goals_conceded"))["total"] or 0

        # xG
        total_xg = matches.aggregate(total=Sum("xg"))["total"] or 0
        total_xg_against = matches.aggregate(total=Sum("xg_against"))["total"] or 0

        # Match record
        wins = matches.filter(goals_scored__gt=F("goals_conceded")).count()
        draws = matches.filter(goals_scored=F("goals_conceded")).count()
        losses = matches.filter(goals_scored__lt=F("goals_conceded")).count()

        # Total matches
        match_count = matches.count()

        # Average goals per match
        avg_goals_scored = total_goals_scored / match_count if match_count > 0 else 0
        avg_goals_conceded = total_goals_conceded / match_count if match_count > 0 else 0

        return Response({
            "season": season,
            "match_count": match_count,
            "most_used_formation": most_used_formation,
            "goals": {
                "scored": total_goals_scored,
                "conceded": total_goals_conceded,
                "difference": total_goals_scored - total_goals_conceded,
                "avg_scored": round(avg_goals_scored, 2),
                "avg_conceded": round(avg_goals_conceded, 2),
            },
            "xg": {
                "for": float(total_xg),
                "against": float(total_xg_against),
                "difference": float(total_xg - total_xg_against),
            },
            "record": {
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "points": wins * 3 + draws,
            },
        }, status=200)


class PlayerXGStatsView(APIView):
    """
    GET /api/teams/player-xg-stats/
    Returns player xG totals calculated from shot events with zones.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        season = request.query_params.get("season", None)
        from .models import PlayerEventInstance
        from django.db.models import Q

        season_filter = Q()
        if season:
            season_filter = Q(match__season=season)

        # Get all shot events for the team
        shots_on_target = PlayerEventInstance.objects.filter(
            team=team,
            event="shots_on_target"
        ).filter(season_filter).select_related("player")

        shots_off_target = PlayerEventInstance.objects.filter(
            team=team,
            event="shots_off_target"
        ).filter(season_filter).select_related("player")

        # Calculate xG per player
        player_xg = {}
        
        for shot in shots_on_target:
            player_name = shot.player.name
            if player_name not in player_xg:
                player_xg[player_name] = 0.0
            
            zone = shot.zone
            if zone in ["1", "2", "3"]:  # Attacking zones
                player_xg[player_name] += 0.3
            elif zone in ["4", "5", "6"]:  # Defensive/midfield zones
                player_xg[player_name] += 0.1
            else:
                player_xg[player_name] += 0.2  # Default

        for shot in shots_off_target:
            player_name = shot.player.name
            if player_name not in player_xg:
                player_xg[player_name] = 0.0
            player_xg[player_name] += 0.05

        # Convert to list and sort
        player_xg_list = [
            {"player": name, "xg": round(xg, 2)}
            for name, xg in player_xg.items()
        ]
        player_xg_list.sort(key=lambda x: x["xg"], reverse=True)

        return Response({
            "season": season,
            "player_xg": player_xg_list,
        }, status=200)


class TeamPerformanceSuggestionsView(APIView):
    """
    GET /api/teams/performance-suggestions/
    Returns team-level performance suggestions based on historical data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        season = request.query_params.get("season", None)
        
        # Filter matches
        matches_qs = Match.objects.filter(team=team, state="finished")
        if season:
            matches_qs = matches_qs.filter(season=season)
        
        matches = matches_qs
        match_count = matches.count()
        
        if match_count == 0:
            return Response({
                "suggestions": [],
                "message": "Not enough match data to generate suggestions."
            }, status=200)

        suggestions = []
        
        # 1. Formation Analysis
        formation_results = {}
        for match in matches:
            if match.formation:
                if match.formation not in formation_results:
                    formation_results[match.formation] = {"wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0, "matches": 0}
                
                formation_results[match.formation]["matches"] += 1
                formation_results[match.formation]["goals_for"] += match.goals_scored
                formation_results[match.formation]["goals_against"] += match.goals_conceded
                
                if match.goals_scored > match.goals_conceded:
                    formation_results[match.formation]["wins"] += 1
                elif match.goals_scored == match.goals_conceded:
                    formation_results[match.formation]["draws"] += 1
                else:
                    formation_results[match.formation]["losses"] += 1
        
        if formation_results:
            # Find best and worst formations
            best_formation = None
            worst_formation = None
            best_win_rate = -1
            worst_win_rate = 101
            
            for formation, data in formation_results.items():
                if data["matches"] >= 2:  # Only consider formations used at least twice
                    win_rate = (data["wins"] / data["matches"]) * 100
                    if win_rate > best_win_rate:
                        best_win_rate = win_rate
                        best_formation = formation
                    if win_rate < worst_win_rate:
                        worst_win_rate = win_rate
                        worst_formation = formation
            
            if best_formation and worst_formation and best_formation != worst_formation:
                suggestions.append({
                    "category": "Tactical",
                    "priority": "High",
                    "title": "Consider Formation Change",
                    "message": f"Your team performs better with {best_formation} (win rate: {best_win_rate:.1f}%) compared to {worst_formation} (win rate: {worst_win_rate:.1f}%).",
                    "action_items": [
                        f"Use {best_formation} formation more frequently",
                        f"Analyze why {best_formation} works better for your team",
                        f"Consider phasing out {worst_formation} unless match-specific circumstances require it"
                    ]
                })
        
        # 2. Goals Analysis
        total_goals_for = matches.aggregate(total=Sum("goals_scored"))["total"] or 0
        total_goals_against = matches.aggregate(total=Sum("goals_conceded"))["total"] or 0
        avg_goals_for = total_goals_for / match_count if match_count > 0 else 0
        avg_goals_against = total_goals_against / match_count if match_count > 0 else 0
        
        if avg_goals_for < 1.0:
            suggestions.append({
                "category": "Attacking",
                "priority": "High",
                "title": "Improve Goal Scoring",
                "message": f"Team averages only {avg_goals_for:.1f} goals per match. Focus on attacking play.",
                "action_items": [
                    "Train with drills focused on finishing and shooting",
                    "Work on creating more goal-scoring opportunities",
                    "Keep forward players higher up the pitch",
                    "Practice set pieces and crosses"
                ]
            })
        
        if avg_goals_against > 2.0:
            suggestions.append({
                "category": "Defending",
                "priority": "High",
                "title": "Strengthen Defense",
                "message": f"Team concedes {avg_goals_against:.1f} goals per match on average. Defensive work needed.",
                "action_items": [
                    "Focus training on defensive positioning",
                    "Work on team shape and compactness",
                    "Practice defensive drills and clearances",
                    "Improve communication between defenders"
                ]
            })
        
        # 3. xG Analysis
        total_xg = matches.aggregate(total=Sum("xg"))["total"] or 0
        total_xg_against = matches.aggregate(total=Sum("xg_against"))["total"] or 0
        avg_xg = float(total_xg) / match_count if match_count > 0 else 0
        avg_xg_against = float(total_xg_against) / match_count if match_count > 0 else 0
        
        if avg_xg < 1.0:
            suggestions.append({
                "category": "Attacking",
                "priority": "Medium",
                "title": "Create Better Chances",
                "message": f"Low xG ({avg_xg:.2f}) suggests team isn't creating high-quality chances.",
                "action_items": [
                    "Practice attacking patterns and combinations",
                    "Work on getting into better shooting positions",
                    "Focus on key passes and through balls",
                    "Train players to take shots from better angles"
                ]
            })
        
        if avg_xg_against > 1.5:
            suggestions.append({
                "category": "Defending",
                "priority": "Medium",
                "title": "Reduce Opposition Chances",
                "message": f"Opposition xG of {avg_xg_against:.2f} indicates they're creating too many good chances.",
                "action_items": [
                    "Improve defensive organization",
                    "Work on pressing and closing down space",
                    "Practice blocking shots and intercepting passes",
                    "Train defenders to force shots from wider angles"
                ]
            })
        
        # 4. Event Analysis (passing, duels, etc.)
        from .models import PlayerEventStat
        event_stats = PlayerEventStat.objects.filter(
            team=team,
            match__in=matches
        ).values("event").annotate(
            total=Sum("count"),
            matches=Count("match", distinct=True)
        )
        
        event_totals = {}
        for stat in event_stats:
            event = stat["event"]
            total = stat["total"] or 0
            matches_count = stat["matches"] or 1
            event_totals[event] = {
                "total": total,
                "avg_per_match": total / matches_count if matches_count > 0 else 0
            }
        
        # Passing analysis
        key_passes = event_totals.get("key_passes", {}).get("avg_per_match", 0)
        if key_passes < 3:
            suggestions.append({
                "category": "Attacking",
                "priority": "Medium",
                "title": "Improve Creative Passing",
                "message": f"Team averages only {key_passes:.1f} key passes per match. Need more creativity.",
                "action_items": [
                    "Train with drills more focused on passing",
                    "Practice through balls and final third passes",
                    "Work on vision and decision-making in attack",
                    "Encourage players to take risks in final third"
                ]
            })
        
        # Duel analysis
        duels_won = event_totals.get("duels_won", {}).get("total", 0)
        duels_lost = event_totals.get("duels_lost", {}).get("total", 0)
        total_duels = duels_won + duels_lost
        if total_duels > 0:
            duel_win_rate = (duels_won / total_duels) * 100
            if duel_win_rate < 45:
                suggestions.append({
                    "category": "Physical",
                    "priority": "Medium",
                    "title": "Improve Physical Battles",
                    "message": f"Team wins only {duel_win_rate:.1f}% of duels. Physical work needed.",
                    "action_items": [
                        "Focus on strength and conditioning",
                        "Practice 1v1 situations and duels",
                        "Work on timing and positioning in challenges",
                        "Improve body positioning in physical contests"
                    ]
                })
        
        # Defensive actions
        interceptions = event_totals.get("interceptions", {}).get("avg_per_match", 0)
        tackles = event_totals.get("tackles", {}).get("avg_per_match", 0)
        if interceptions + tackles < 10:
            suggestions.append({
                "category": "Defending",
                "priority": "Medium",
                "title": "Increase Defensive Actions",
                "message": "Low number of interceptions and tackles suggests passive defending.",
                "action_items": [
                    "Practice aggressive defending and pressing",
                    "Work on reading the game and intercepting",
                    "Train players to be more proactive in defense",
                    "Improve anticipation and positioning"
                ]
            })
        
        # Sort by priority (High first)
        priority_order = {"High": 3, "Medium": 2, "Low": 1}
        suggestions.sort(key=lambda x: priority_order.get(x.get("priority", "Low"), 0), reverse=True)
        
        return Response({
            "season": season,
            "match_count": match_count,
            "suggestions": suggestions[:10],  # Limit to top 10
        }, status=200)


class ZoneAnalysisView(APIView):
    """
    GET /api/teams/zone-analysis/
    Returns zone-based analysis showing strengths and weaknesses
    
    POST /api/teams/zone-analysis/
    Create or update zone analysis (manual entry for presentation)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        season = request.query_params.get("season", None)

        # Get zone analysis from database
        zones_qs = ZoneAnalysis.objects.filter(team=team)
        if season:
            zones_qs = zones_qs.filter(season=season)

        zones = zones_qs

        # If no manual entries, calculate from event instances
        if not zones.exists():
            from .models import PlayerEventInstance
            from django.db.models import Count, Q

            season_filter = Q()
            if season:
                season_filter = Q(match__season=season)

            # Get event counts by zone
            zone_stats = PlayerEventInstance.objects.filter(
                team=team
            ).filter(season_filter).exclude(zone__isnull=True).exclude(zone="").values("zone").annotate(
                total_events=Count("id"),
                successful=Count("id", filter=Q(event__in=["duels_won", "interceptions", "blocks", "tackles", "clearances"])),
            )

            # Calculate success rates and identify strengths/weaknesses
            strengths = []
            weaknesses = []
            
            for zone_stat in zone_stats:
                zone = zone_stat["zone"]
                total = zone_stat["total_events"]
                successful = zone_stat["successful"]
                success_rate = (successful / total * 100) if total > 0 else 0

                if success_rate >= 60:  # Threshold for strength
                    strengths.append({
                        "zone": zone,
                        "events": total,
                        "success_rate": round(success_rate, 1),
                    })
                elif success_rate < 40:  # Threshold for weakness
                    weaknesses.append({
                        "zone": zone,
                        "events": total,
                        "success_rate": round(success_rate, 1),
                    })

            return Response({
                "season": season,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "source": "calculated",
            }, status=200)

        # Return manual entries
        strengths = zones.filter(zone_type="strength")
        weaknesses = zones.filter(zone_type="weakness")

        return Response({
            "season": season,
            "strengths": ZoneAnalysisSerializer(strengths, many=True).data,
            "weaknesses": ZoneAnalysisSerializer(weaknesses, many=True).data,
            "source": "manual",
        }, status=200)

    def post(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        zone = request.data.get("zone")
        zone_type = request.data.get("zone_type")  # "strength" or "weakness"
        season = request.data.get("season", None)
        notes = request.data.get("notes", "")

        if not zone or zone_type not in ["strength", "weakness"]:
            return Response({"detail": "zone and zone_type (strength/weakness) are required."}, status=400)

        zone_analysis, created = ZoneAnalysis.objects.update_or_create(
            team=team,
            season=season,
            zone=zone,
            zone_type=zone_type,
            defaults={
                "events_in_zone": request.data.get("events_in_zone", 0),
                "successful_events": request.data.get("successful_events", 0),
                "failed_events": request.data.get("failed_events", 0),
                "notes": notes,
            }
        )

        return Response(ZoneAnalysisSerializer(zone_analysis).data, status=201 if created else 200)
