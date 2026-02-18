# Backend tests – what each file does

We run these with: `python manage.py test stato.tests` (from the `backend` folder). No Redis or WebSocket server is needed; Django uses an in-memory SQLite database for tests.

We only test **key behaviour** we rely on – not every edge case. There are **28 tests** in total. The idea is: if these pass, the main flows (login, join team, matches) are working.

---

## Unit tests (models, helpers, serializers, permissions)

| File | What it tests |
|------|----------------|
| **test_models.py** | **Team**: code is auto-generated and unique. **Profile**: created automatically when a User is created. **Player**: same name can’t appear twice in the same team. **Match**: default state is `not_started`, elapsed_seconds is 0. **ChatMessage**: can be linked to a match (optional). **PlayerEventStat**: one row per (team, match, player, event) – duplicate raises IntegrityError. |
| **test_views_helpers.py** | **_get_team(request)** – returns the user’s team if they have one, else None. **_parse_kickoff(value)** – parses an ISO date string (e.g. for match kickoff) and returns a timezone-aware datetime. |
| **test_permissions.py** | **IsManager** – unauthenticated user is denied; user with role manager is allowed. (Used on some manager-only endpoints.) |
| **test_serializers.py** | **TeamSerializer** – output includes `team_code` and `club_name`. **TeamSignupSerializer** – valid data creates team + manager user + players; duplicate email is invalid. |

---

## Integration tests (HTTP API)

These call the real URLs and check status codes and response data. We use Django’s `APITestCase` and `force_authenticate` to log in as a user.

| File | What it tests |
|------|----------------|
| **test_api_auth.py** | **POST /api/auth/login/** – returns 200 with `access` and `refresh` tokens. **GET /api/auth/me/** – returns 401 without auth; with auth returns user and team. |
| **test_api_players.py** | **POST /api/players/signup/** – creates user and profile with role player. **POST /api/players/join-team/** – 401 without auth; 404 for invalid team code; 200 and profile updated for valid code + player name. |
| **test_api_teams.py** | **GET /api/teams/me/** – 401 without auth; with auth returns team (including team_code). **POST /api/teams/signup/** – creates team, manager user, and players. |
| **test_api_matches.py** | **GET /api/matches/** – 401 without auth; with auth returns list including the team’s matches. **POST /api/matches/{id}/timer/** with `action: "start"` – updates match state to `in_progress` and elapsed_seconds to 0. |
---

## What we don’t test

- Frontend (Expo/React Native)
- Redis or WebSocket (real-time broadcast)
- Every possible error (e.g. wrong password, missing fields on every endpoint)
- Leave-team, player /me, performance-stats, match detail 404, timer invalid action, etc.

We added tests for the flows that would break the app if they failed (login, join team, match list + timer). The rest (including chat) we check manually.
