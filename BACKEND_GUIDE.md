# StatSync Backend – Full Guide (Presentation & Q&A)

This document explains **every backend file**, what it does, how the app works, and what you need to know when presenting or answering questions.

---

## How the backend fits in

- **Frontend (Expo)** talks to the backend over **HTTP** (REST API). Every request that needs auth sends `Authorization: Bearer <JWT>`.
- **Real-time updates** (live stats, chat) work like this: Django **publishes** a message to **Redis** (channel `events`). A separate **Node.js WebSocket server** **subscribes** to Redis and **broadcasts** to all connected clients. So Django does not hold WebSocket connections; Node does.
- **Database**: SQLite locally, or PostgreSQL when `DATABASE_URL` is set (e.g. on Railway).

---

# 1. Project root & Django entry points

## `backend/manage.py`
- **What it does:** Django’s CLI entry point. You run `python manage.py runserver`, `python manage.py test`, `python manage.py migrate`, etc.
- **Talking point:** “We use it to run the server, run tests, and apply migrations.”
- **If asked:** It sets `DJANGO_SETTINGS_MODULE` to `backend.settings` and delegates to Django’s `execute_from_command_line`.

---

## `backend/backend/settings.py`
- **What it does:** Central Django configuration: database, installed apps, middleware, REST framework, JWT, CORS, Redis/Channels, media files.
- **Main points:**
  - **Database:** Uses `DATABASE_URL` if set (PostgreSQL on Railway), otherwise SQLite in `db.sqlite3`.
  - **INSTALLED_APPS:** Includes `rest_framework`, `corsheaders`, and our app `stato` (no Django Channels).
  - **CORS:** Allows all origins so the Expo app can call the API; allows `Authorization` and `content-type`.
  - **REST_FRAMEWORK:** Default auth is **JWT** (`JWTAuthentication`), default permission is **IsAuthenticated** (so every endpoint requires login unless overridden).
  - **SIMPLE_JWT:** Access token ~30 min, refresh token ~7 days; `Bearer` header.
  - **MEDIA:** Uploaded files (e.g. match videos) go to `MEDIA_ROOT` and are served under `/media/`.
- **If asked:** “We use JWT so the API is stateless; the frontend stores the token and sends it on every request. CORS allows the deployed or local frontend to call the API.”

---

## `backend/backend/urls.py`
- **What it does:** Root URL routing. Defines what happens for `/`, `/admin/`, `/api/`, and `/media/...`.
- **Routes:**
  - **GET /** – JSON response: “SportsHub API”, “api”: “/api/”, and a note that WebSockets use the Node server. So if someone points a WebSocket at the Django URL they get a clear message.
  - **/admin/** – Django admin (optional).
  - **/api/** – All API routes are under here; included from `stato.urls`.
  - **/media/<path>** – Serves files from `MEDIA_ROOT` with **Range request** support so video seeking works in the browser.
- **Talking point:** “We serve media ourselves with Range support so the frontend can seek in match videos without loading the whole file.”
- **If asked:** “Range requests return `206 Partial Content` and `Accept-Ranges: bytes` so the video player can request byte ranges.”

---

## `backend/backend/wsgi.py` & `backend/backend/asgi.py`
- **WSGI:** Used in production (e.g. Gunicorn) for HTTP only.
- **ASGI:** Plain Django ASGI for HTTP only. Real-time is handled entirely by the separate Node WebSocket server (Django publishes to Redis; Node subscribes and broadcasts).
- **If asked:** “We don’t use Django Channels; real-time is done by a separate Node server that subscribes to Redis, so Django only does HTTP and publishing.”

---

# 2. The `stato` app – URL routing

## `stato/urls.py`
- **What it does:** Defines all **API endpoints** under `/api/`. Each path maps to a view class.
- **Groups:**
  - **Auth:** `auth/login/`, `auth/refresh/`, `auth/me/`
  - **Team:** `teams/signup/`, `teams/me/`, `teams/players/`, `teams/performance-stats/`, etc.
  - **Player:** `players/signup/`, `players/join-team/`, `players/leave-team/`, `players/me/`, `players/me/stats/`
  - **Matches:** `matches/`, `matches/current-live/`, `matches/<id>/`, `matches/<id>/stats/`, `matches/<id>/<event>/<player>/increment/`, `matches/<id>/timer/`, `matches/<id>/video/`, `matches/<id>/events/`, live-suggestions, performance-suggestions (formation comparison via Match.opponent_formation only)
  - **Stats / analytics:** `stats/`, `analytics/insights/`, `ml/performance-improvement/`
  - **Chat:** `chat/messages/`
- **Talking point:** “All API routes live in one file so we can see the full surface; auth, team, player, match, and chat are clearly grouped.”
- **If asked:** “The increment URL is `matches/<id>/<event>/<player>/increment/` so the frontend sends the match id, event type, and player name or id; we get or create the player and update the aggregate stat plus create an instance for the timeline.”

---

# 3. Data layer – models

## `stato/models.py`
- **What it does:** Defines all **database tables** (Django ORM models) and one **signal** (create Profile when User is created).
- **Entities:**
  - **User** – Django’s built-in (email/username, password). We don’t define it; we use it.
  - **Profile** – One-to-one with User. Stores **role** (manager/player), **team**, and optional **player** link. Created automatically when a User is created (signal).
  - **Team** – `club_name`, `team_name`, **team_code** (unique 6-char, auto-generated in `save()`).
  - **Player** – Belongs to Team; **name**. Unique per team: `(team, name)`.
  - **Match** – Belongs to Team. Opponent, kickoff, **state** (not_started, in_progress, paused, finished), **elapsed_seconds**, **formation**, **opponent_formation** (for formation comparison only), season, is_home, goals_scored/conceded, **xg**, **xg_against**.
  - **PlayerEventStat** – One row per (team, match, player, event): **count**. Used for dashboards and totals.
  - **PlayerEventInstance** – One row per event occurrence: **second**, **zone**. Used for timeline and video jump-to-moment; also used for xG.
  - **MatchRecording** – One-to-one with Match; **file** (upload path), optional duration.
  - **ChatMessage** – team, optional match, sender (User), sender_role (manager or player), message, created_at.
  - **ZoneAnalysis** – Team-level zone strengths/weaknesses per season.
- **EVENT_CHOICES:** shots_on_target, shots_off_target, key_passes, duels_won/lost, fouls, interceptions, blocks, tackles, clearances.
- **Talking points:**
  - “We use two tables for events: **PlayerEventStat** for fast aggregates and **PlayerEventInstance** for timestamps and zones so we can jump to a moment in the video and compute xG.”
  - “Team code is generated in `save()` with a uniqueness check so every team gets a shareable code for players to join.”
  - “Profile is created by a **post_save** signal on User so every user has a profile with a role and optional team/player.”
- **If asked:** “We chose a relational model and constraints (e.g. unique team+player name, unique team+match+player+event) so the database enforces consistency; the dual event storage avoids heavy COUNT queries on the dashboard while still giving us a full event timeline.”

---

# 4. Request/response layer – serializers & permissions

## `stato/serializers.py`
- **What it does:** Converts model instances to/from JSON and validates input. Used by views to return API responses and to create/update data.
- **Main serializers:**
  - **EventStatSerializer** – PlayerEventStat with player name/id, match_id.
  - **MatchSerializer** – Match with `has_recording`, `recording_url` (full URL from request).
  - **EventInstanceSerializer** – PlayerEventInstance for timeline/events list.
  - **TeamSerializer** – Team with `team_code`, `players_count` (read-only).
  - **TeamSignupSerializer** – Validates club_name, team_name, email (unique), password (min length); **create()** creates Team, User, Profile (manager), and optional list of Players.
  - **CustomTokenObtainPairSerializer** – Adds **email**, **role**, **team_id** to the JWT payload so the frontend doesn’t have to call `/auth/me/` for every screen.
- **Talking point:** “We put custom claims in the JWT so the app knows the user’s role and team without an extra request; we still have `/auth/me/` for full profile when needed.”
- **If asked:** “TeamSignupSerializer creates the team and manager in one transaction and optionally bulk-creates players from a list, with duplicate-name stripping.”

---

## `stato/permissions.py`
- **What it does:** Custom permission classes for the API.
  - **IsManager:** Allows only if the user is authenticated and has a profile with `role == "manager"` or `"analyst"` (analyst treated as manager for backwards compatibility). Used on manager-only endpoints.
- **Talking point:** “Most endpoints only need IsAuthenticated; we use IsManager where only the manager should act (e.g. team signup, some team settings).”
- **If asked:** “We don’t store permissions in the token; we read the profile from the database when we need to check role, so if we change someone’s role it takes effect on the next request.”

---

# 5. Business logic – views (by file)

## `stato/views.py`
- **What it does:** Core helpers + views for **matches**, **event increment**, **stats**, **analytics**, and **squad**.
- **Helpers:**
  - **\_get_team(request)** – Returns the current user’s team from their profile, or None. Used everywhere we need team scope.
  - **\_get_or_create_player(team, player_name)** – Gets or creates a Player for that team (so managers can log events for players not in the original CSV).
  - **\_parse_kickoff(value)** – Parses ISO datetime for match kickoff; makes it timezone-aware.
  - **\_publish_event_to_redis(payload, kind)** – Publishes JSON to Redis channel **"events"**. If Redis isn’t configured, no-op. The Node server subscribes to "events" and broadcasts to WebSocket clients.
  - **\_update_match_xg(match)** – Recomputes match xG from PlayerEventInstance shot events (zones 1–3: 0.3, 4–6: 0.1, off target: 0.05) and saves to `match.xg`.
- **Views:**
  - **PerformanceInsightsView** – GET `/api/analytics/insights/`. Aggregates PlayerEventStat by player, computes simple attacking/defensive/discipline indices, and returns plain-English suggestions (e.g. “low shot volume”, “more duels lost than won”). No ML training; rule-based for a 3rd-year project.
  - **TeamPlayersView** – GET list squad; POST replace squad with a list of names (e.g. from CSV); DELETE remove a player (and unlink any profile linked to that player).
  - **MatchListCreateView** – GET list matches for team (optional season filter); POST create match (opponent, kickoff_at, formation, season, is_home, etc.).
  - **CurrentLiveMatchView** – GET current match when state is in_progress or paused (live).
  - **MatchDetailView** – GET one match; PATCH update (e.g. goals_scored, goals_conceded); on goal update, publishes to Redis for live UI.
  - **MatchStatsListView** – GET stats for one match (PlayerEventStat rows).
  - **EventStatListView** – GET overall stats across all matches for the team.
  - **IncrementEventForMatchView** – POST increment: get/create PlayerEventStat row, increment count, optionally create PlayerEventInstance (second, zone), publish to Redis, update xG if it’s a shot event. This is the **core of live event logging**.
- **Talking points:**
  - “Every event log goes to **PlayerEventStat** (for totals) and **PlayerEventInstance** (for timeline and xG); then we publish to Redis so the Node server can push to all connected clients.”
  - “xG is heuristic: we use zone and shot type from instances; we recalculate when a shot is logged and when the match is finished.”
  - “We allow creating a player on the fly in the increment endpoint so the manager can log events for someone not in the original squad list.”
- **If asked:** “If Redis is down, the API still works; we just don’t broadcast. The frontend can show a message like ‘Live updates offline’.”

---

## `stato/views_auth.py`
- **What it does:** **GET /api/auth/me/** – Returns the current user’s email, role, and team (serialized). Requires a valid JWT.
- **Talking point:** “The app calls this after login or on load to get the full profile and team; the JWT already has role and team_id but we use this for the full team object and to confirm the user still exists.”

---

## `stato/views_team.py`
- **What it does:** Team signup, team “me”, performance stats, suggestions, zone analysis, player xG stats.
  - **TeamSignupView** – POST create team + manager (uses TeamSignupSerializer); AllowAny.
  - **TeamMeView** – GET current user’s team; 400 if no team.
  - **TeamPerformanceStatsView** – GET aggregated stats: most used formation, goals scored/conceded, xG, match count, wins/draws/losses (optional season filter).
  - **TeamPerformanceSuggestionsView** – GET tactical suggestions based on team stats.
  - **PlayerXGStatsView** – GET per-player xG contribution.
  - **ZoneAnalysisView** – GET/POST zone-based strengths/weaknesses.
- **Talking point:** “Team signup is the only endpoint that doesn’t require auth; it creates the team and the manager user in one go, and optionally a list of players.”

---

## `stato/views_player.py`
- **What it does:** Player signup, join team, leave team, player “me”, player “me/stats”.
  - **PlayerSignupView** – POST create player account (email, password, player_name); role set to player, no team. AllowAny.
  - **PlayerJoinTeamView** – POST join using **team_code** and **player_name**. Finds team by code (404 if invalid). If player name doesn’t exist in squad, creates the Player. Links profile to team and player. Only players can call this (403 for manager).
  - **PlayerLeaveTeamView** – POST unlink profile from team and player.
  - **PlayerProfileView** – GET `/api/players/me/` – Returns player, team, and performance aggregate (only for role=player).
  - **PlayerMeStatsView** – GET `/api/players/me/stats/` – Returns that player’s event stats only (so players never see other players’ data).
- **Talking points:**
  - “Players join with a 6-character code the manager shares; we look up the team by that code and then find or create the player by name.”
  - “We enforce in the view that only users with role player can join; managers can’t use the join endpoint.”
- **If asked:** “If the player name isn’t in the squad we still create the Player so late sign-ups or trialists can be logged; the unique constraint is per team so the same name can exist in different teams.”

---

## `stato/views_match.py`
- **What it does:** Timer, video upload, event instances list, live and post-match suggestions. Opposition comparison is formation-only (Match.opponent_formation).
  - **MatchTimerControlView** – POST actions: **start** (→ in_progress), **pause** (→ paused, save elapsed_seconds), **resume** (→ in_progress), **finish** (→ finished, then _update_match_xg). Invalid action returns 400.
  - **MatchVideoUploadView** – POST multipart file; creates or replaces MatchRecording for that match; returns recording URL.
  - **MatchEventInstancesView** – GET list of PlayerEventInstance for the match (for timeline and video jump-to-moment).
  - **LiveMatchSuggestionsView** – GET tactical suggestions during a live match (score, our stats, formation hint from opponent_formation).
  - **MatchPerformanceSuggestionsView** – GET post-match suggestions (score, xG, our events; no opposition event stats).
- **Talking point:** “The timer has four actions: start, pause, resume, finish. Match state is not_started, in_progress, paused, or finished. When we finish the match we recalculate xG. Event instances are what the frontend uses to show the timeline and to seek the video to a specific second.”

---

## `stato/views_chat.py`
- **What it does:** **GET /api/chat/messages/** – List recent messages (optional match_id filter). **POST /api/chat/messages/** – Create message, then **publish to Redis** (same _publish_event_to_redis with kind `"chat"`) so the Node server can broadcast to clients.
- **Talking point:** “Chat is stored in the database and also published to Redis so all connected clients get the new message in real time; the payload includes team_id so clients can filter by team.”
- **If asked:** “We don’t authenticate the WebSocket connection; the client filters messages by team_id. A more secure design would pass a token when connecting to the Node server.”

---

## `stato/views_ml.py`
- **What it does:** **GET /api/ml/performance-improvement/** – “ML-style” performance recommendations. Optional query params: player_id, match_id. Aggregates PlayerEventStat, computes duel win rate, shot accuracy, defensive actions, discipline; then applies **rule-based** logic (e.g. duel_win_rate < 50% → “Improve Duel Success Rate”) and returns structured recommendations with category, priority, action items.
- **Talking point:** “We call it ML in the URL but it’s statistical analysis and rules, not trained models; that keeps it explainable and appropriate for the project scope.”
- **If asked:** “We could replace this with a real model later; the API shape would stay the same, only the logic inside would change.”

---

# 6. Real-time – Redis & Node

## `stato/views.py` (again) – `_publish_event_to_redis`
- Django publishes to Redis channel **"events"** with a JSON body like `{"kind": "stat"|"chat", "data": {...}}`. The Node server subscribes to **"events"** (and in code also "chat", but currently all publish to "events") and broadcasts the message to every open WebSocket client.

## `backend/ws-server/server.js`
- **What it does:** Standalone **Node.js WebSocket server**. Listens on port 3001 (or WS_PORT/PORT). Subscribes to Redis channels **"events"** and **"chat"**. On any message, broadcasts it to all connected WebSocket clients. Uses ping/pong to detect dead connections and close them.
- **Talking point:** “We use a separate Node server so Django stays focused on HTTP and the database; Node only subscribes to Redis and fans out to clients. That way we can scale or restart the WebSocket layer independently.”
- **If asked:** “The frontend connects to this server’s URL (e.g. ws://localhost:3001 or wss:// on production); it doesn’t connect to Django for WebSockets. Django and Node both use the same Redis instance so when we publish from Django, Node receives and broadcasts.”

---

# 7. Other files

## `stato/apps.py`
- **What it does:** Django app config for `stato`. No customisation needed for this project.

## `stato/admin.py`
- **What it does:** Empty; we don’t register models in Django admin. You could register Team, Match, etc. for debugging.

## `stato/migrations/`
- **What it does:** Django migrations that create/alter tables to match the models. You run `python manage.py migrate` to apply them.
- **Talking point:** “We use migrations so the schema is versioned and the same structure can be applied locally and on production.”

## `stato/management/commands/generate_team_codes.py`
- **What it does:** Management command to backfill team_code for teams that don’t have one (e.g. created before we added the field). Run with `python manage.py generate_team_codes`.

---

# 8. Flow summaries for presenting

**Login**
1. Frontend POSTs email/password to `/api/auth/login/`.
2. CustomTokenView uses CustomTokenObtainPairSerializer → JWT with email, role, team_id.
3. Frontend stores access + refresh tokens and uses access in `Authorization: Bearer <token>`.

**Join team (player)**
1. Player POSTs team_code + player_name to `/api/players/join-team/` with JWT.
2. Backend checks role is player; finds Team by team_code (404 if invalid); finds or creates Player; links Profile to team and player; returns team + player.

**Log an event (manager)**
1. Frontend POSTs to `/api/matches/<id>/<event>/<player>/increment/` (optional body: second, zone).
2. Backend gets team from profile; validates event type; gets or creates player; increments PlayerEventStat; creates PlayerEventInstance; publishes to Redis; updates match xG if shot; returns new count and payload.
3. Node server receives from Redis and broadcasts to all WebSocket clients; frontend updates UI.

**Chat**
1. User POSTs message to `/api/chat/messages/`. Backend saves ChatMessage and publishes to Redis. Node broadcasts; other clients receive and show the message.

---

# 9. Quick Q&A cheatsheet

| Question | Short answer |
|----------|---------------|
| Why JWT? | Stateless; frontend stores token; no server-side session; good for mobile. |
| Why two event tables? | PlayerEventStat for fast totals; PlayerEventInstance for timeline, video seek, and xG. |
| Why Redis + Node instead of only Django? | Keeps Django focused on HTTP/DB; Node only does WebSocket fan-out; we can scale or restart them separately. |
| How does the frontend get live updates? | Connects to Node WebSocket server; Node subscribes to Redis; Django publishes to Redis when events or chat are saved. |
| How is xG calculated? | From PlayerEventInstance shot events; zones 1–3 = 0.3, 4–6 = 0.1, off target = 0.05; saved on Match. |
| Who can join a team? | Only users with role **player**; they use the 6-character team_code and their player_name (created if not in squad). |
| Where is video stored? | In MEDIA_ROOT (e.g. `media/recordings/`); served by Django with Range support for seeking. |
| What if Redis is down? | API still works; we just don’t publish; real-time updates stop until Redis is back. |

You can use this document to walk through the backend in a presentation and to answer technical questions about how and why each part works.
