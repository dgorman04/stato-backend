# views_ml.py - Machine Learning Performance Improvement API
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta

from .models import PlayerEventStat, Player, Team, Match
from .views import _get_team


class MLPerformanceImprovementView(APIView):
    """
    GET /api/ml/performance-improvement/
    
    Provides ML-based performance improvement recommendations for players.
    Uses basic statistical analysis and pattern detection.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        player_id = request.query_params.get("player_id")
        match_id = request.query_params.get("match_id")

        if player_id:
            # Get recommendations for specific player
            try:
                player = Player.objects.get(id=player_id, team=team)
                recommendations = self._analyze_player_performance(player, team, match_id)
                return Response(recommendations, status=200)
            except Player.DoesNotExist:
                return Response({"detail": "Player not found."}, status=404)
        else:
            # Get recommendations for all players
            players = Player.objects.filter(team=team)
            recommendations = []
            for player in players:
                rec = self._analyze_player_performance(player, team, match_id)
                if rec.get("recommendations"):
                    recommendations.append({
                        "player_id": player.id,
                        "player_name": player.name,
                        **rec
                    })
            return Response({"players": recommendations}, status=200)

    def _analyze_player_performance(self, player, team, match_id=None):
        """
        Analyze player performance and generate ML-style recommendations.
        Uses statistical analysis to identify patterns and improvement areas.
        """
        # Get player stats
        stats_query = PlayerEventStat.objects.filter(team=team, player=player)
        if match_id:
            stats_query = stats_query.filter(match_id=match_id)
        
        stats = stats_query.values("event").annotate(
            total=Sum("count"),
            matches=Count("match", distinct=True)
        )

        # Build performance profile
        performance = {}
        total_events = 0
        for stat in stats:
            event = stat["event"]
            count = stat["total"] or 0
            matches = stat["matches"] or 1
            avg_per_match = count / matches if matches > 0 else 0
            
            performance[event] = {
                "total": count,
                "matches": matches,
                "average_per_match": round(avg_per_match, 2)
            }
            total_events += count

        # Calculate key metrics
        shots_on_target = performance.get("shots_on_target", {}).get("total", 0)
        shots_off_target = performance.get("shots_off_target", {}).get("total", 0)
        key_passes = performance.get("key_passes", {}).get("total", 0)
        duels_won = performance.get("duels_won", {}).get("total", 0)
        duels_lost = performance.get("duels_lost", {}).get("total", 0)
        interceptions = performance.get("interceptions", {}).get("total", 0)
        blocks = performance.get("blocks", {}).get("total", 0)
        tackles = performance.get("tackles", {}).get("total", 0)
        clearances = performance.get("clearances", {}).get("total", 0)
        fouls = performance.get("fouls", {}).get("total", 0)

        # Calculate total number of matches
        total_matches = stats_query.values("match").distinct().count()
        
        # Calculate ratios and metrics
        duel_win_rate = (duels_won / (duels_won + duels_lost)) * 100 if (duels_won + duels_lost) > 0 else 0
        shot_accuracy = (shots_on_target / (shots_on_target + shots_off_target)) * 100 if (shots_on_target + shots_off_target) > 0 else 0
        defensive_actions = interceptions + blocks + tackles + clearances
        discipline_score = 100 - (fouls * 10) if fouls < 10 else 0

        # Generate ML-style recommendations
        recommendations = []
        priority_score = 0

        # Duel performance
        if duel_win_rate < 50 and (duels_won + duels_lost) > 5:
            recommendations.append({
                "category": "Physical Performance",
                "priority": "High",
                "title": "Improve Duel Success Rate",
                "message": f"Current duel win rate is {duel_win_rate:.1f}%. Focus on positioning and timing in 1v1 situations.",
                "action_items": [
                    "Practice defensive positioning drills",
                    "Work on timing of challenges",
                    "Improve body positioning in duels"
                ],
                "expected_improvement": "+15% duel win rate"
            })
            priority_score += 3

        # Key passes
        if key_passes < 2 and total_matches > 0:
            recommendations.append({
                "category": "Attacking",
                "priority": "Medium",
                "title": "Increase Creative Passing",
                "message": f"Only {key_passes} key passes recorded. Focus on creating goal-scoring opportunities.",
                "action_items": [
                    "Practice through balls and final third passes",
                    "Work on vision and decision-making in attack",
                    "Improve positioning to create chances",
                    "Train with drills more focused on passing"
                ],
                "expected_improvement": "+2 key passes per match"
            })
            priority_score += 2
        
        # Shot accuracy
        if (shots_on_target + shots_off_target) > 5 and shot_accuracy < 40:
            recommendations.append({
                "category": "Attacking",
                "priority": "Medium",
                "title": "Improve Shot Accuracy",
                "message": f"Shot accuracy is {shot_accuracy:.1f}%. Focus on shot placement and technique.",
                "action_items": [
                    "Practice shooting drills from various angles",
                    "Work on composure in front of goal",
                    "Improve shot selection and placement",
                    "Train finishing under pressure"
                ],
                "expected_improvement": "+15% shot accuracy"
            })
            priority_score += 1

        # Defensive contribution
        if defensive_actions < 5 and match_id:  # Only for current match
            recommendations.append({
                "category": "Defensive Awareness",
                "priority": "Medium",
                "title": "Increase Defensive Involvement",
                "message": "Low defensive actions recorded. Increase awareness and positioning.",
                "action_items": [
                    "Improve defensive positioning",
                    "Increase interceptions and blocks",
                    "Better reading of opposition play"
                ],
                "expected_improvement": "+3 defensive actions per match"
            })
            priority_score += 1

        # Discipline
        if fouls > 3:
            recommendations.append({
                "category": "Discipline",
                "priority": "High",
                "title": "Reduce Fouls",
                "message": f"{fouls} fouls recorded. Focus on cleaner challenges.",
                "action_items": [
                    "Practice timing of tackles",
                    "Improve body control",
                    "Better positioning to avoid late challenges"
                ],
                "expected_improvement": "-50% fouls"
            })
            priority_score += 2

        # Shot opportunities
        total_shots = shots_on_target + shots_off_target
        if total_shots < 2 and total_matches > 0:
            recommendations.append({
                "category": "Attacking",
                "priority": "Medium",
                "title": "Increase Shot Opportunities",
                "message": f"Only {total_shots} shot(s) recorded. Look for more attacking opportunities.",
                "action_items": [
                    "Improve positioning in final third",
                    "Work on movement off the ball",
                    "Increase confidence in shooting",
                    "Practice getting into goal-scoring positions"
                ],
                "expected_improvement": "+2 shots per match"
            })
            priority_score += 1

        # Overall performance summary
        performance_score = min(100, (
            (duel_win_rate * 0.3) +
            (shot_accuracy * 0.2) +
            (min(defensive_actions * 2, 30)) +
            (min(key_passes * 5, 20)) +
            (discipline_score * 0.1)
        ))

        return {
            "player_id": player.id,
            "player_name": player.name,
            "performance_metrics": {
                "overall_score": round(performance_score, 1),
                "duel_win_rate": round(duel_win_rate, 1),
                "shot_accuracy": round(shot_accuracy, 1),
                "defensive_actions": defensive_actions,
                "key_passes": key_passes,
                "discipline_score": round(discipline_score, 1),
                "total_events": total_events,
            },
            "performance_breakdown": performance,
            "recommendations": recommendations,
            "priority_score": priority_score,
            "analysis_date": timezone.now().isoformat(),
        }
