from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


EVENT_CHOICES = [
    ("shots_on_target", "Shots on Target"),
    ("shots_off_target", "Shots off Target"),
    ("key_passes", "Key Passes"),
    ("duels_won", "Duels Won"),
    ("duels_lost", "Duels Lost"),
    ("fouls", "Fouls"),
    ("interceptions", "Interceptions"),
    ("blocks", "Blocks"),
    ("tackles", "Tackles"),
    ("clearances", "Clearances"),
]


class Team(models.Model):
    club_name = models.CharField(max_length=200)
    team_name = models.CharField(max_length=200)
    team_code = models.CharField(max_length=10, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.team_code or self.team_code == '':
            import random
            import string
            # Generate unique 6-character alphanumeric code
            while True:
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                # Check if code already exists (avoid duplicates)
                if not Team.objects.filter(team_code=code).exclude(pk=self.pk).exists():
                    self.team_code = code
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.club_name} — {self.team_name}"


class Profile(models.Model):
    ROLE_CHOICES = (
        ("manager", "Manager"),
        ("player", "Player"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, null=True, blank=True, related_name="members"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="manager")
    enabled = models.BooleanField(default=True)
    
    # For players, link to their Player record
    player = models.ForeignKey(
        "Player", on_delete=models.SET_NULL, null=True, blank=True, related_name="user_profile"
    )

    def __str__(self):
        return f"{self.user.username} ({self.role})"


@receiver(post_save, sender=User)
def create_profile_if_missing(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        Profile.objects.get_or_create(user=instance)


class Player(models.Model):
    """
    Squad players belonging to a Team (created from CSV upload).
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="players")
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "name"], name="uniq_team_player_name"),
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.team_id})"


class Match(models.Model):
    """
    A match container so stats can be split match-by-match.
    """
    MATCH_STATE_CHOICES = [
        ("not_started", "Not Started"),
        ("first_half", "1st Half"),
        ("second_half", "2nd Half"),
        ("in_progress", "In Progress"),
        ("paused", "Paused"),
        ("finished", "Finished"),
    ]

    FORMATION_CHOICES = [
        ("4-4-2", "4-4-2"),
        ("4-3-3", "4-3-3"),
        ("3-5-2", "3-5-2"),
        ("4-2-3-1", "4-2-3-1"),
        ("3-4-3", "3-4-3"),
        ("5-3-2", "5-3-2"),
        ("4-1-4-1", "4-1-4-1"),
        ("other", "Other"),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="matches")
    opponent = models.CharField(max_length=200)
    kickoff_at = models.DateTimeField()
    analyst_name = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_matches"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Match state and timer
    state = models.CharField(max_length=20, choices=MATCH_STATE_CHOICES, default="not_started")
    elapsed_seconds = models.PositiveIntegerField(default=0)  # Total elapsed match time
    first_half_duration = models.PositiveIntegerField(null=True, blank=True)  # Kept for DB compatibility
    
    # Formation
    formation = models.CharField(max_length=20, choices=FORMATION_CHOICES, null=True, blank=True)
    opponent_formation = models.CharField(max_length=20, choices=FORMATION_CHOICES, null=True, blank=True)
    
    # Season (e.g., "2024/25", "2025/26")
    season = models.CharField(max_length=10, null=True, blank=True, help_text="Format: YYYY/YY (e.g., 2024/25)")
    
    # Venue
    is_home = models.BooleanField(default=True, help_text="True if home match, False if away")
    
    # Match results
    goals_scored = models.PositiveIntegerField(default=0)
    goals_conceded = models.PositiveIntegerField(default=0)
    
    # Expected Goals (xG) - calculated from shot data
    xg = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Expected Goals for")
    xg_against = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Expected Goals Against")

    class Meta:
        ordering = ["-kickoff_at", "-created_at"]

    def __str__(self):
        return f"{self.team.team_name} vs {self.opponent} @ {self.kickoff_at}"


class PlayerEventStat(models.Model):
    """
    Count-based stats per player per event PER MATCH.
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="stats")
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="stats")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="stats")
    event = models.CharField(max_length=32, choices=EVENT_CHOICES)
    count = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "match", "player", "event"],
                name="uniq_team_match_player_event",
            ),
        ]

    def __str__(self):
        return f"{self.team_id} | m{self.match_id} | {self.player.name} - {self.event}: {self.count}"


class PlayerEventInstance(models.Model):
    """
    A single event occurrence with an optional timestamp + zone so we can
    jump to the exact moment in a match recording and build richer analytics.
    """

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="event_instances")
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="event_instances")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="event_instances")
    event = models.CharField(max_length=32, choices=EVENT_CHOICES)

    # seconds from kickoff; we intentionally keep this simple so the frontend
    # can just send int seconds based on its match clock
    second = models.PositiveIntegerField(null=True, blank=True)

    # simple pitch zone bucket (e.g. "1".."6"), aligned with the manager UI
    zone = models.CharField(max_length=8, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"m{self.match_id} #{self.player_id} {self.event}@{self.second}s (z={self.zone})"


class MatchRecording(models.Model):
    """
    Video (or any media) uploaded for a match so managers can
    review events and jump to timestamps.
    """

    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name="recording")
    file = models.FileField(upload_to="recordings/")

    # Optional metadata – can be filled by frontend or left empty
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recording for match {self.match_id}"


class ChatMessage(models.Model):
    """
    Real-time chat messages between team members (manager, players).
    """
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="chat_messages")
    match = models.ForeignKey(Match, on_delete=models.CASCADE, null=True, blank=True, related_name="chat_messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    sender_role = models.CharField(max_length=20)  # manager or player
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender.username} ({self.sender_role}): {self.message[:50]}"


class ZoneAnalysis(models.Model):
    """
    Track zone-based performance metrics to identify team strengths and weaknesses.
    """
    ZONE_CHOICES = [
        ("1", "Zone 1"),
        ("2", "Zone 2"),
        ("3", "Zone 3"),
        ("4", "Zone 4"),
        ("5", "Zone 5"),
        ("6", "Zone 6"),
    ]
    
    ZONE_TYPE_CHOICES = [
        ("strength", "Strength"),
        ("weakness", "Weakness"),
    ]
    
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="zone_analyses")
    season = models.CharField(max_length=10, null=True, blank=True, help_text="Format: YYYY/YY (e.g., 2024/25)")
    zone = models.CharField(max_length=8, choices=ZONE_CHOICES)
    zone_type = models.CharField(max_length=10, choices=ZONE_TYPE_CHOICES)
    
    # Metrics
    events_in_zone = models.PositiveIntegerField(default=0)
    successful_events = models.PositiveIntegerField(default=0)
    failed_events = models.PositiveIntegerField(default=0)
    
    # Description/notes
    notes = models.TextField(blank=True, help_text="Manual notes about this zone")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "season", "zone", "zone_type"],
                name="uniq_team_season_zone_type",
            ),
        ]
        ordering = ["zone", "zone_type"]
    
    def __str__(self):
        return f"{self.team.team_name} - {self.zone} ({self.zone_type}) - {self.season or 'All'}"