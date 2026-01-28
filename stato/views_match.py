"""
Match management views: timer control, video upload, opposition stats, event instances.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from django.core.files.storage import default_storage
from django.conf import settings

from .models import Match, PlayerEventInstance, OppositionStat, MatchRecording, EVENT_CHOICES
from .serializers import MatchSerializer, EventInstanceSerializer, OppositionStatSerializer
from .views import _get_team, EVENT_KEYS


class MatchTimerControlView(APIView):
    """
    POST /api/matches/<match_id>/timer/
    body: { action: "start" | "pause" | "resume" | "half_time" | "finish", elapsed_seconds?: number }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        action = request.data.get("action")
        elapsed = request.data.get("elapsed_seconds")

        if action == "start":
            match.state = "first_half"
            match.elapsed_seconds = 0
        elif action == "pause":
            if elapsed is not None:
                match.elapsed_seconds = int(elapsed)
        elif action == "resume":
            if match.state == "first_half":
                match.state = "first_half"
            elif match.state == "second_half":
                match.state = "second_half"
        elif action == "half_time":
            match.state = "half_time"
            if elapsed is not None:
                match.first_half_duration = int(elapsed)
        elif action == "second_half":
            match.state = "second_half"
            if elapsed is not None:
                match.elapsed_seconds = int(elapsed)
        elif action == "finish":
            match.state = "finished"
            if elapsed is not None:
                match.elapsed_seconds = int(elapsed)
            # Calculate xG when match finishes
            from .views import _update_match_xg
            _update_match_xg(match)
        else:
            return Response({"detail": "Invalid action."}, status=400)

        match.save()
        return Response(MatchSerializer(match, context={"request": request}).data, status=200)


class MatchVideoUploadView(APIView):
    """
    POST /api/matches/<match_id>/video/
    multipart/form-data with 'file' field
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        if "file" not in request.FILES:
            return Response({"detail": "No file provided."}, status=400)

        video_file = request.FILES["file"]
        duration = request.data.get("duration_seconds")

        # Create or update recording
        recording, created = MatchRecording.objects.get_or_create(
            match=match,
            defaults={"file": video_file}
        )

        if not created:
            # Update existing recording
            if default_storage.exists(recording.file.name):
                default_storage.delete(recording.file.name)
            recording.file = video_file

        if duration:
            try:
                recording.duration_seconds = int(duration)
            except (TypeError, ValueError):
                pass

        recording.save()

        return Response({
            "ok": True,
            "recording_url": request.build_absolute_uri(recording.file.url) if recording.file else None,
            "duration_seconds": recording.duration_seconds,
        }, status=200 if created else 201)


class MatchEventInstancesView(APIView):
    """
    GET /api/matches/<match_id>/events/
    Returns all event instances with timestamps for video seeking.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        instances = PlayerEventInstance.objects.filter(team=team, match=match).order_by("second", "created_at")
        return Response(EventInstanceSerializer(instances, many=True).data, status=200)


class OppositionStatsView(APIView):
    """
    GET /api/matches/<match_id>/opposition/
    POST /api/matches/<match_id>/opposition/
    Manage opposition team stats for comparison.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        stats = OppositionStat.objects.filter(match=match)
        return Response(OppositionStatSerializer(stats, many=True).data, status=200)

    def post(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        event = request.data.get("event")
        count = request.data.get("count", 0)

        if event not in EVENT_KEYS:
            return Response({"detail": "Invalid event."}, status=400)

        try:
            count = int(count)
        except (TypeError, ValueError):
            return Response({"detail": "count must be an integer."}, status=400)

        stat, created = OppositionStat.objects.get_or_create(
            match=match,
            event=event,
            defaults={"count": count}
        )

        if not created:
            stat.count = count
            stat.save()

        return Response(OppositionStatSerializer(stat).data, status=200 if created else 201)


class LiveMatchSuggestionsView(APIView):
    """
    GET /api/matches/<match_id>/live-suggestions/
    Returns real-time tactical suggestions for live matches based on current stats and opposition.
    Designed to help managers react to opponent and get the best out of the team in the moment.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        # Only provide suggestions for live matches
        if match.state not in ["first_half", "second_half", "half_time"]:
            return Response({
                "suggestions": [],
                "message": "Match is not live."
            }, status=200)

        suggestions = []
        
        # Get current match stats
        from .models import PlayerEventStat
        from django.db.models import Sum
        
        match_stats = PlayerEventStat.objects.filter(team=team, match=match).values("event").annotate(
            total=Sum("count")
        )
        
        event_totals = {}
        for stat in match_stats:
            event_totals[stat["event"]] = stat["total"] or 0
        
        # Get opposition stats for comparison
        opp_stats = OppositionStat.objects.filter(match=match)
        opp_totals = {}
        for stat in opp_stats:
            opp_totals[stat.event] = stat.count
        
        # Current score
        goals_for = match.goals_scored or 0
        goals_against = match.goals_conceded or 0
        score_diff = goals_for - goals_against
        
        # Time context
        elapsed = match.elapsed_seconds or 0
        is_second_half = match.state == "second_half"
        time_remaining = (90 * 60) - elapsed  # Approximate 90 min match
        
        # 1. Score-based tactical suggestions
        if score_diff < 0:
            # Losing
            if time_remaining > 30 * 60:  # More than 30 min left
                suggestions.append({
                    "category": "Tactical",
                    "priority": "High",
                    "title": "Trailing - Increase Pressure",
                    "message": f"Down {abs(score_diff)} goal(s). Push forward and increase attacking intensity.",
                    "action_items": [
                        "Push fullbacks higher to support attacks",
                        "Increase pressing in opposition half",
                        "Take more risks in final third",
                        "Look for quick counter-attacks"
                    ]
                })
            else:  # Less than 30 min left
                suggestions.append({
                    "category": "Tactical",
                    "priority": "High",
                    "title": "Urgent - All Out Attack",
                    "message": f"Down {abs(score_diff)} goal(s) with limited time. Need immediate response.",
                    "action_items": [
                        "Commit more players forward",
                        "Take long shots if space opens",
                        "Use width to stretch defense",
                        "Quick restarts and throw-ins"
                    ]
                })
        elif score_diff == 0:
            # Drawing
            if time_remaining < 15 * 60:  # Less than 15 min left
                suggestions.append({
                    "category": "Tactical",
                    "priority": "Medium",
                    "title": "Level - Push for Winner",
                    "message": "Score is level with time running out. Push for winning goal.",
                    "action_items": [
                        "Maintain attacking threat",
                        "Keep defensive discipline",
                        "Look for set-piece opportunities",
                        "Fresh legs in attacking positions"
                    ]
                })
        else:
            # Winning
            if time_remaining < 20 * 60:  # Less than 20 min left
                suggestions.append({
                    "category": "Tactical",
                    "priority": "Medium",
                    "title": "Leading - Manage Game",
                    "message": f"Up {score_diff} goal(s). Control tempo and see out the match.",
                    "action_items": [
                        "Keep possession and slow tempo",
                        "Stay compact defensively",
                        "Avoid unnecessary risks",
                        "Waste time intelligently on restarts"
                    ]
                })
        
        # 2. Opposition threat analysis
        opp_key_passes = opp_totals.get("key_passes", 0)
        our_key_passes = event_totals.get("key_passes", 0)
        
        if opp_key_passes > our_key_passes * 1.5:
            suggestions.append({
                "category": "Defensive",
                "priority": "High",
                "title": "Opposition Creating More Chances",
                "message": f"They have {opp_key_passes} key passes vs our {our_key_passes}. Tighten up defensively.",
                "action_items": [
                    "Drop deeper to limit space",
                    "Double up on their creative players",
                    "Close down passing lanes",
                    "Stay compact between lines"
                ]
            })
        
        opp_shots_on = opp_totals.get("shots_on_target", 0)
        our_shots_on = event_totals.get("shots_on_target", 0)
        
        if opp_shots_on > our_shots_on * 1.2:
            suggestions.append({
                "category": "Defensive",
                "priority": "High",
                "title": "Opposition Shooting More",
                "message": f"They have {opp_shots_on} shots on target vs our {our_shots_on}. Need to limit their chances.",
                "action_items": [
                    "Close down quicker in final third",
                    "Block shots and crosses",
                    "Pressure their shooters",
                    "Keep defensive shape"
                ]
            })
        
        # 3. Our attacking performance
        our_shots_on = event_totals.get("shots_on_target", 0)
        our_shots_off = event_totals.get("shots_off_target", 0)
        total_shots = our_shots_on + our_shots_off
        
        if total_shots > 0:
            shot_accuracy = (our_shots_on / total_shots) * 100
            if shot_accuracy < 35 and total_shots >= 5:
                suggestions.append({
                    "category": "Attacking",
                    "priority": "Medium",
                    "title": "Poor Shot Accuracy",
                    "message": f"Only {shot_accuracy:.0f}% shots on target. Need better finishing.",
                    "action_items": [
                        "Work ball into better positions",
                        "Take time to compose before shooting",
                        "Aim for corners of goal",
                        "Practice composure in training"
                    ]
                })
        
        if our_key_passes < 3 and elapsed > 30 * 60:  # After 30 min
            suggestions.append({
                "category": "Attacking",
                "priority": "Medium",
                "title": "Low Creativity",
                "message": f"Only {our_key_passes} key passes. Need more creative play.",
                "action_items": [
                    "Encourage through balls",
                    "Use width to create space",
                    "Quick combinations in final third",
                    "Take risks with final passes"
                ]
            })
        
        # 4. Duel performance
        our_duels_won = event_totals.get("duels_won", 0)
        our_duels_lost = event_totals.get("duels_lost", 0)
        total_duels = our_duels_won + our_duels_lost
        
        if total_duels > 10:
            duel_win_rate = (our_duels_won / total_duels) * 100
            if duel_win_rate < 40:
                suggestions.append({
                    "category": "Physical",
                    "priority": "Medium",
                    "title": "Losing Physical Battles",
                    "message": f"Only winning {duel_win_rate:.0f}% of duels. Need more intensity.",
                    "action_items": [
                        "Increase physical commitment",
                        "Better body positioning in challenges",
                        "Win second balls",
                        "Match opponent's intensity"
                    ]
                })
        
        # 5. Defensive actions
        our_interceptions = event_totals.get("interceptions", 0)
        our_tackles = event_totals.get("tackles", 0)
        defensive_total = our_interceptions + our_tackles
        
        if elapsed > 20 * 60 and defensive_total < 10:  # After 20 min
            suggestions.append({
                "category": "Defensive",
                "priority": "Medium",
                "title": "Passive Defending",
                "message": f"Only {defensive_total} defensive actions. Need to be more proactive.",
                "action_items": [
                    "Step up and intercept passes",
                    "Close down space quicker",
                    "Win the ball back higher up pitch",
                    "Increase defensive intensity"
                ]
            })
        
        # 6. Formation/opponent specific
        if match.opponent_formation:
            suggestions.append({
                "category": "Tactical",
                "priority": "Low",
                "title": "Opponent Formation",
                "message": f"Opponent playing {match.opponent_formation}. Adjust accordingly.",
                "action_items": [
                    "Exploit spaces in their formation",
                    "Match their shape if needed",
                    "Target weak areas",
                    "Adjust our formation if struggling"
                ]
            })
        
        # Sort by priority
        priority_order = {"High": 3, "Medium": 2, "Low": 1}
        suggestions.sort(key=lambda x: priority_order.get(x.get("priority", "Low"), 0), reverse=True)
        
        return Response({
            "match_id": match.id,
            "match_state": match.state,
            "elapsed_seconds": elapsed,
            "score": f"{goals_for}-{goals_against}",
            "suggestions": suggestions[:8],  # Top 8 most relevant
        }, status=200)


class MatchPerformanceSuggestionsView(APIView):
    """
    GET /api/matches/<match_id>/performance-suggestions/
    Returns match-specific performance suggestions based on the match data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        suggestions = []
        
        # Get match stats
        from .models import PlayerEventStat
        from django.db.models import Sum
        
        match_stats = PlayerEventStat.objects.filter(team=team, match=match).values("event").annotate(
            total=Sum("count")
        )
        
        event_totals = {}
        for stat in match_stats:
            event_totals[stat["event"]] = stat["total"] or 0
        
        # Get opposition stats for comparison
        opp_stats = OppositionStat.objects.filter(match=match)
        opp_totals = {}
        for stat in opp_stats:
            opp_totals[stat.event] = stat.count
        
        # 1. Score Analysis
        goals_for = match.goals_scored or 0
        goals_against = match.goals_conceded or 0
        
        if goals_for < goals_against:
            suggestions.append({
                "category": "Tactical",
                "priority": "High",
                "title": "Match Result Analysis",
                "message": f"Lost {goals_for}-{goals_against}. Analyze what went wrong and adjust for next match.",
                "action_items": [
                    "Review defensive positioning and organization",
                    "Analyze where goals were conceded",
                    "Consider formation changes for similar opponents",
                    "Work on maintaining possession better"
                ]
            })
        elif goals_for == goals_against:
            suggestions.append({
                "category": "Tactical",
                "priority": "Medium",
                "title": "Draw Analysis",
                "message": f"Drew {goals_for}-{goals_against}. Could have won with better finishing or defense.",
                "action_items": [
                    "Focus on converting chances in training",
                    "Work on defensive concentration",
                    "Practice set pieces (both attacking and defending)"
                ]
            })
        
        # 2. xG Analysis
        xg = float(match.xg or 0)
        xg_against = float(match.xg_against or 0)
        
        if xg < 1.0:
            suggestions.append({
                "category": "Attacking",
                "priority": "High",
                "title": "Low Chance Creation",
                "message": f"xG of {xg:.2f} indicates few high-quality chances created.",
                "action_items": [
                    "Work on creating more goal-scoring opportunities",
                    "Practice attacking patterns and combinations",
                    "Keep forward players higher up the pitch",
                    "Focus on key passes and through balls"
                ]
            })
        
        if xg_against > 2.0:
            suggestions.append({
                "category": "Defending",
                "priority": "High",
                "title": "Too Many Chances Conceded",
                "message": f"Opposition xG of {xg_against:.2f} shows they created many good chances.",
                "action_items": [
                    "Improve defensive organization and shape",
                    "Work on pressing and closing down space",
                    "Practice blocking shots and intercepting passes",
                    "Better communication between defenders"
                ]
            })
        
        # 3. Event Analysis
        shots_on_target = event_totals.get("shots_on_target", 0)
        shots_off_target = event_totals.get("shots_off_target", 0)
        total_shots = shots_on_target + shots_off_target
        
        if total_shots > 0:
            shot_accuracy = (shots_on_target / total_shots) * 100
            if shot_accuracy < 40:
                suggestions.append({
                    "category": "Attacking",
                    "priority": "Medium",
                    "title": "Poor Shot Accuracy",
                    "message": f"Only {shot_accuracy:.1f}% of shots were on target.",
                    "action_items": [
                        "Practice shooting drills focusing on accuracy",
                        "Work on composure in front of goal",
                        "Improve shot selection and placement",
                        "Train finishing under pressure"
                    ]
                })
        
        key_passes = event_totals.get("key_passes", 0)
        if key_passes < 3:
            suggestions.append({
                "category": "Attacking",
                "priority": "Medium",
                "title": "Low Creative Passing",
                "message": f"Only {key_passes} key passes recorded. Need more creativity in attack.",
                "action_items": [
                    "Train with drills more focused on passing",
                    "Practice through balls and final third passes",
                    "Work on vision and decision-making in attack",
                    "Encourage players to take risks in final third"
                ]
            })
        
        # 4. Duel Analysis
        duels_won = event_totals.get("duels_won", 0)
        duels_lost = event_totals.get("duels_lost", 0)
        total_duels = duels_won + duels_lost
        
        if total_duels > 0:
            duel_win_rate = (duels_won / total_duels) * 100
            if duel_win_rate < 45:
                suggestions.append({
                    "category": "Physical",
                    "priority": "Medium",
                    "title": "Poor Duel Performance",
                    "message": f"Team won only {duel_win_rate:.1f}% of duels.",
                    "action_items": [
                        "Focus on strength and conditioning",
                        "Practice 1v1 situations and duels",
                        "Work on timing and positioning in challenges",
                        "Improve body positioning in physical contests"
                    ]
                })
        
        # 5. Defensive Actions
        interceptions = event_totals.get("interceptions", 0)
        tackles = event_totals.get("tackles", 0)
        blocks = event_totals.get("blocks", 0)
        clearances = event_totals.get("clearances", 0)
        defensive_total = interceptions + tackles + blocks + clearances
        
        if defensive_total < 15:
            suggestions.append({
                "category": "Defending",
                "priority": "Medium",
                "title": "Passive Defending",
                "message": f"Only {defensive_total} defensive actions recorded. Team was too passive.",
                "action_items": [
                    "Practice aggressive defending and pressing",
                    "Work on reading the game and intercepting",
                    "Train players to be more proactive in defense",
                    "Improve anticipation and positioning"
                ]
            })
        
        # 6. Fouls Analysis
        fouls = event_totals.get("fouls", 0)
        if fouls > 8:
            suggestions.append({
                "category": "Discipline",
                "priority": "Medium",
                "title": "Too Many Fouls",
                "message": f"{fouls} fouls committed. Discipline needs improvement.",
                "action_items": [
                    "Practice timing of tackles",
                    "Improve body control",
                    "Better positioning to avoid late challenges",
                    "Work on cleaner defensive techniques"
                ]
            })
        
        # 7. Opposition Comparison
        if opp_totals:
            our_key_passes = key_passes
            opp_key_passes = opp_totals.get("key_passes", 0)
            
            if opp_key_passes > our_key_passes * 1.5:
                suggestions.append({
                    "category": "Tactical",
                    "priority": "High",
                    "title": "Outplayed in Attack",
                    "message": f"Opposition created {opp_key_passes} key passes vs our {our_key_passes}.",
                    "action_items": [
                        "Analyze opposition's attacking patterns",
                        "Work on defensive shape to limit their creativity",
                        "Improve our own attacking play to match",
                        "Consider tactical adjustments for similar opponents"
                    ]
                })
        
        # Sort by priority
        priority_order = {"High": 3, "Medium": 2, "Low": 1}
        suggestions.sort(key=lambda x: priority_order.get(x.get("priority", "Low"), 0), reverse=True)
        
        return Response({
            "match_id": match.id,
            "suggestions": suggestions[:10],  # Limit to top 10
        }, status=200)
