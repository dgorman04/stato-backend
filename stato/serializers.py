from urllib.parse import quote
from django.utils import timezone

from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Player, PlayerEventStat, Profile, Team, Match, PlayerEventInstance, ZoneAnalysis
from .stream_token import make_stream_token


class EventStatSerializer(serializers.ModelSerializer):
    player = serializers.CharField(source="player.name", read_only=True)
    player_id = serializers.IntegerField(source="player.id", read_only=True)
    match_id = serializers.IntegerField(source="match.id", read_only=True)

    class Meta:
        model = PlayerEventStat
        fields = ["id", "team", "match_id", "player_id", "player", "event", "count", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class MatchSerializer(serializers.ModelSerializer):
    is_home = serializers.BooleanField()
    elapsed_seconds = serializers.SerializerMethodField()
    has_recording = serializers.SerializerMethodField()
    recording_url = serializers.SerializerMethodField()
    recording_stream_url = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            "id", "opponent", "kickoff_at", "analyst_name", "created_at",
            "state", "elapsed_seconds", "first_half_duration",
            "formation", "opponent_formation",
            "season", "is_home", "goals_scored", "goals_conceded", "xg", "xg_against",
            "has_recording", "recording_url", "recording_stream_url"
        ]

    def get_elapsed_seconds(self, obj):
        """When match is in progress and timer_started_at is set, return live elapsed (so manager and analyst see same count)."""
        if obj.state == "in_progress" and getattr(obj, "timer_started_at", None):
            base = obj.elapsed_seconds or 0
            delta = (timezone.now() - obj.timer_started_at).total_seconds()
            return int(base + delta)
        return obj.elapsed_seconds or 0

    def get_has_recording(self, obj):
        return hasattr(obj, "recording")

    def get_recording_url(self, obj):
        if hasattr(obj, "recording") and obj.recording.file:
            request = self.context.get("request")
            if request:
                url = obj.recording.file.url
                if callable(url):
                    url = url()
                return request.build_absolute_uri(url) if url and not url.startswith("http") else url
        return None

    def get_recording_stream_url(self, obj):
        """Backend proxy URL for playback with signed token (video element cannot send Auth header)."""
        if hasattr(obj, "recording") and obj.recording.file:
            request = self.context.get("request")
            if request and request.user and request.user.is_authenticated:
                token = make_stream_token(obj.id, request.user.id)
                token_qs = quote(token, safe="")
                return request.build_absolute_uri(f"/api/matches/{obj.id}/recording/stream/?token={token_qs}")
        return None


class EventInstanceSerializer(serializers.ModelSerializer):
    player = serializers.CharField(source="player.name", read_only=True)
    player_id = serializers.IntegerField(source="player.id", read_only=True)
    
    class Meta:
        model = PlayerEventInstance
        fields = ["id", "player_id", "player", "event", "second", "zone", "created_at"]


class TeamSerializer(serializers.ModelSerializer):
    players_count = serializers.IntegerField(source="players.count", read_only=True)

    class Meta:
        model = Team
        fields = ["id", "club_name", "team_name", "team_code", "created_at", "players_count"]


class TeamSignupSerializer(serializers.Serializer):
    club_name = serializers.CharField()
    team_name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)

    players = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def create(self, validated_data):
        club_name = validated_data["club_name"].strip()
        team_name = validated_data["team_name"].strip()
        email = validated_data["email"].lower().strip()
        password = validated_data["password"]
        players_in = validated_data.get("players", [])

        team = Team.objects.create(club_name=club_name, team_name=team_name)

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
        )

        Profile.objects.update_or_create(
            user=user,
            defaults={"team": team, "role": "manager", "enabled": True},
        )

        if isinstance(players_in, list) and players_in:
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

            Player.objects.bulk_create([Player(team=team, name=name) for name in cleaned])

        return {"team": team, "email": email}


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["role"] = getattr(getattr(user, "profile", None), "role", "manager")
        token["team_id"] = getattr(getattr(getattr(user, "profile", None), "team", None), "id", None)
        return token


class ZoneAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZoneAnalysis
        fields = ["id", "season", "zone", "zone_type", "events_in_zone", "successful_events", "failed_events", "notes", "created_at", "updated_at"]
