from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView

from .serializers import CustomTokenObtainPairSerializer
from .views import (
    TeamPlayersView,
    EventStatListView,
    MatchListCreateView,
    CurrentLiveMatchView,
    MatchDetailView,
    MatchStatsListView,
    IncrementEventForMatchView,
    PerformanceInsightsView,
)
from .views_auth import MeView
from .views_team import TeamSignupView, TeamMeView, TeamPerformanceStatsView, PlayerXGStatsView, TeamPerformanceSuggestionsView, ZoneAnalysisView
from .views_match import (
    MatchTimerControlView,
    MatchVideoUploadView,
    MatchVideoUploadURLView,
    MatchVideoConfirmView,
    MatchEventInstancesView,
    LiveMatchSuggestionsView,
    MatchPerformanceSuggestionsView,
)
from .views_chat import ChatMessagesView
from .views_ml import MLPerformanceImprovementView
from .views_player import PlayerSignupView, PlayerProfileView, PlayerJoinTeamView, PlayerLeaveTeamView, PlayerMeStatsView


class CustomTokenView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


urlpatterns = [
    # Auth
    path("auth/login/", CustomTokenView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/me/", MeView.as_view()),

    # Team
    path("teams/signup/", TeamSignupView.as_view()),
    path("teams/me/", TeamMeView.as_view()),
    path("teams/players/", TeamPlayersView.as_view()),
    path("teams/players/<int:player_id>/", TeamPlayersView.as_view()),
    path("teams/performance-stats/", TeamPerformanceStatsView.as_view()),
    path("teams/player-xg-stats/", PlayerXGStatsView.as_view()),
    path("teams/performance-suggestions/", TeamPerformanceSuggestionsView.as_view()),
    path("teams/zone-analysis/", ZoneAnalysisView.as_view()),

    # Player
    path("players/signup/", PlayerSignupView.as_view()),
    path("players/join-team/", PlayerJoinTeamView.as_view()),
    path("players/leave-team/", PlayerLeaveTeamView.as_view()),
    path("players/me/", PlayerProfileView.as_view()),
    path("players/me/stats/", PlayerMeStatsView.as_view()),

    # Matches
    path("matches/", MatchListCreateView.as_view()),
    path("matches/current-live/", CurrentLiveMatchView.as_view()),
    path("matches/<int:match_id>/", MatchDetailView.as_view()),  # ✅ needed for match page header
    path("matches/<int:match_id>/stats/", MatchStatsListView.as_view()),
    path("matches/<int:match_id>/<str:event>/<str:player>/increment/", IncrementEventForMatchView.as_view()),
    path("matches/<int:match_id>/timer/", MatchTimerControlView.as_view()),
    path("matches/<int:match_id>/video/", MatchVideoUploadView.as_view()),
    path("matches/<int:match_id>/video/upload-url/", MatchVideoUploadURLView.as_view()),
    path("matches/<int:match_id>/video/confirm/", MatchVideoConfirmView.as_view()),
    path("matches/<int:match_id>/events/", MatchEventInstancesView.as_view()),
    path("matches/<int:match_id>/live-suggestions/", LiveMatchSuggestionsView.as_view()),
    path("matches/<int:match_id>/performance-suggestions/", MatchPerformanceSuggestionsView.as_view()),

    # Overall stats (all matches)
    path("stats/", EventStatListView.as_view()),

    # Analytics / ML-style insights
    path("analytics/insights/", PerformanceInsightsView.as_view()),

    # Chat
    path("chat/messages/", ChatMessagesView.as_view()),

    # ML Performance Improvement
    path("ml/performance-improvement/", MLPerformanceImprovementView.as_view()),
]
