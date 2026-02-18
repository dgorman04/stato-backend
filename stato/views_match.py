"""
Match management views: timer control, video upload, event instances, live and post-match suggestions.
Formation comparison uses Match.opponent_formation only; no opposition event stats.
"""
import uuid
from urllib.parse import quote
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from django.core.files.storage import default_storage
from django.conf import settings
from django.http import FileResponse
from rest_framework.permissions import AllowAny

from .models import Match, PlayerEventInstance, MatchRecording, EVENT_CHOICES
from .serializers import MatchSerializer, EventInstanceSerializer
from .views import _get_team, EVENT_KEYS
from .stream_token import make_stream_token, validate_stream_token


class MatchTimerControlView(APIView):
    """
    POST /api/matches/<match_id>/timer/
    body: { action: "start" | "pause" | "resume" | "finish", elapsed_seconds?: number }
    Timer has three states: not_started, in_progress, paused, finished.
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
            match.state = "in_progress"
            match.elapsed_seconds = int(elapsed) if elapsed is not None else 0
        elif action == "pause":
            match.state = "paused"
            if elapsed is not None:
                match.elapsed_seconds = int(elapsed)
        elif action == "resume":
            match.state = "in_progress"
            if elapsed is not None:
                match.elapsed_seconds = int(elapsed)
        elif action == "finish":
            match.state = "finished"
            if elapsed is not None:
                match.elapsed_seconds = int(elapsed)
            from .views import _update_match_xg
            _update_match_xg(match)
        else:
            return Response({"detail": "Invalid action. Use start, pause, resume, or finish."}, status=400)

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

        if recording.file and request.user.is_authenticated:
            token = make_stream_token(match_id, request.user.id)
            stream_url = request.build_absolute_uri(f"/api/matches/{match_id}/recording/stream/?token={quote(token, safe='')}")
        else:
            stream_url = None
        return Response({
            "ok": True,
            "recording_url": request.build_absolute_uri(recording.file.url) if recording.file else None,
            "recording_stream_url": stream_url,
            "duration_seconds": recording.duration_seconds,
        }, status=200 if created else 201)


def _s3_client():
    """Return boto3 S3 client if AWS is configured."""
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    if not bucket:
        return None
    try:
        import boto3
        return boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "eu-west-1"),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
        )
    except Exception:
        return None


class MatchVideoUploadURLView(APIView):
    """
    POST /api/matches/<match_id>/video/upload-url/
    Returns a presigned PUT URL for direct upload to S3. Client uploads file to the URL, then calls confirm.
    Requires AWS_STORAGE_BUCKET_NAME (and credentials) to be set.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)
        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        s3 = _s3_client()
        if not s3:
            return Response(
                {"detail": "S3 upload is not configured. Set AWS_STORAGE_BUCKET_NAME and credentials."},
                status=503,
            )

        bucket = settings.AWS_STORAGE_BUCKET_NAME
        ext = (request.data.get("filename") or "video.mp4").split(".")[-1]
        if ext not in ("mp4", "mov", "webm", "avi"):
            ext = "mp4"
        key = f"recordings/match_{match_id}/{uuid.uuid4().hex}.{ext}"

        try:
            url = s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": key, "ContentType": "video/mp4"},
                ExpiresIn=3600,
            )
        except Exception as e:
            return Response({"detail": f"Failed to generate upload URL: {str(e)}"}, status=500)

        return Response({
            "upload_url": url,
            "key": key,
            "expires_in": 3600,
        }, status=200)


class MatchVideoConfirmView(APIView):
    """
    POST /api/matches/<match_id>/video/confirm/
    body: { key: "<s3 key>" }
    After client uploads file to the presigned URL, call this to save the recording.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)
        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        key = (request.data.get("key") or "").strip()
        if not key or not key.startswith(f"recordings/match_{match_id}/"):
            return Response({"detail": "Invalid or missing key."}, status=400)

        recording, created = MatchRecording.objects.update_or_create(
            match=match,
            defaults={"file": key},
        )
        if request.data.get("duration_seconds") is not None:
            try:
                recording.duration_seconds = int(request.data.get("duration_seconds"))
                recording.save(update_fields=["duration_seconds"])
            except (TypeError, ValueError):
                pass

        recording_url = recording.file.url if recording.file else None
        if callable(recording_url):
            recording_url = recording_url()
        if request.user.is_authenticated:
            token = make_stream_token(match_id, request.user.id)
            stream_url = request.build_absolute_uri(f"/api/matches/{match_id}/recording/stream/?token={quote(token, safe='')}")
        else:
            stream_url = None
        return Response({
            "ok": True,
            "recording_url": recording_url,
            "recording_stream_url": stream_url,
            "duration_seconds": recording.duration_seconds,
        }, status=200 if created else 201)


class MatchOppositionView(APIView):
    """
    GET /api/matches/<match_id>/opposition/
    Opposition event stats were removed; formation comparison uses Match.opponent_formation only.
    Returns empty list so the frontend does not 404.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)
        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)
        return Response([], status=200)


def _content_type_for_recording(name):
    """Return a sensible Content-Type for a recording filename."""
    if not name:
        return "video/mp4"
    name_lower = name.lower()
    if name_lower.endswith(".mov"):
        return "video/quicktime"
    if name_lower.endswith(".mp4"):
        return "video/mp4"
    if name_lower.endswith(".webm"):
        return "video/webm"
    return "video/mp4"


class MatchRecordingStreamView(APIView):
    """
    GET /api/matches/<match_id>/recording/stream/?token=<signed_token>
    Stream the match recording. Accepts either ?token= (for <video> src) or Bearer auth.
    Token is short-lived so the video element can load without sending Authorization header.
    """
    permission_classes = [AllowAny]

    def get(self, request, match_id):
        match = None
        token = request.query_params.get("token", "").strip()
        if token:
            valid, user_id = validate_stream_token(token, match_id)
            if valid:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.filter(pk=user_id).first()
                if user:
                    team = getattr(getattr(user, "profile", None), "team", None)
                    if team:
                        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            # Fall back to normal auth
            if not request.user or not request.user.is_authenticated:
                return Response({"detail": "Authentication required."}, status=401)
            team = _get_team(request)
            if not team:
                return Response({"detail": "No team assigned."}, status=400)
            match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)
        try:
            recording = match.recording
        except MatchRecording.DoesNotExist:
            return Response({"detail": "No recording."}, status=404)
        if not recording.file:
            return Response({"detail": "No recording file."}, status=404)
        name = recording.file.name
        if not default_storage.exists(name):
            return Response({"detail": "Recording file not found."}, status=404)
        content_type = _content_type_for_recording(name)
        try:
            f = default_storage.open(name, "rb")
            response = FileResponse(f, content_type=content_type, as_attachment=False)
            response["Accept-Ranges"] = "bytes"
            return response
        except Exception as e:
            return Response({"detail": str(e)}, status=500)


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


class LiveMatchSuggestionsView(APIView):
    """
    GET /api/matches/<match_id>/live-suggestions/
    Returns real-time tactical suggestions for live matches based on current stats and formation (opponent_formation).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, match_id):
        team = _get_team(request)
        if not team:
            return Response({"detail": "No team assigned."}, status=400)

        match = Match.objects.filter(team=team, id=match_id).first()
        if not match:
            return Response({"detail": "Match not found."}, status=404)

        # Only provide suggestions for live matches (in progress or paused)
        if match.state not in ["in_progress", "paused"]:
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
        
        # Current score
        goals_for = match.goals_scored or 0
        goals_against = match.goals_conceded or 0
        score_diff = goals_for - goals_against
        
        # Time context
        elapsed = match.elapsed_seconds or 0
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
        
        # 2. Our attacking performance
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
        
        our_key_passes = event_totals.get("key_passes", 0)
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
        
        # Sort by priority
        priority_order = {"High": 3, "Medium": 2, "Low": 1}
        suggestions.sort(key=lambda x: priority_order.get(x.get("priority", "Low"), 0), reverse=True)
        
        return Response({
            "match_id": match.id,
            "suggestions": suggestions[:10],  # Limit to top 10
        }, status=200)
