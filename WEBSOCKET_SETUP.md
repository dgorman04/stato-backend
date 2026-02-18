# WebSocket + Redis Setup

## Why WebSockets Show "Offline"

The app connects to the backend in two ways:

1. **REST API** – Django on **port 8000** (HTTP).
2. **WebSockets** – Node.js server on **port 3001** (ws/wss).

Django and the Node server talk via **Redis** (port 6379):

- When stats or chat are saved, **Django** publishes a message to Redis (channels `events` or `chat`).
- The **Node WebSocket server** subscribes to those channels and broadcasts every message to all connected clients.
- The **frontend** opens a WebSocket to the Node server (not to Django).

If the app’s WebSocket URL points at the Django server (e.g. the same base URL as the API), the connection hits Django instead of the Node server → connection fails → status shows **Offline**. API and WebSocket must use separate URLs (Django for API, Node for WebSocket).

---

## How to Get WebSockets Online

### 1. Start Redis

- **Windows:** Install Redis (e.g. [Redis for Windows](https://github.com/microsoftarchive/redis/releases) or WSL) and run `redis-server`.
- **Mac:** `brew install redis` then `redis-server`.
- **Linux:** `sudo apt install redis-server` (or equivalent) then `redis-server`.

Check: `redis-cli ping` should reply `PONG`.

### 2. Start the Node WebSocket server

From the **backend/ws-server** folder:

```bash
cd backend/ws-server
node server.js
```

Or:

```bash
npm run ws
```

You should see:

- `WebSocket running on ws://0.0.0.0:3001`
- `Subscribed to Redis channels: events, chat`

Leave this terminal running.

### 3. Configure frontend URLs

- **Deployed:** Set `EXPO_PUBLIC_API_BASE` to your Django API URL and `EXPO_PUBLIC_WS_URL` to your Node WebSocket URL (e.g. on Railway or your host). The two URLs must be different.
- **Local (same Wi‑Fi):** If the phone and computer are on the same Wi‑Fi:

1. Find your computer’s IP (e.g. `ipconfig` on Windows, `ifconfig` on Mac/Linux).
2. In the frontend `.env`:
   - `EXPO_PUBLIC_API_BASE=http://192.168.x.x:8000`
   - `EXPO_PUBLIC_WS_URL=ws://192.168.x.x:3001`
3. Start Redis and `node backend/ws-server/server.js` as above.

---

## Flow summary

```
Frontend (Expo)
  ├── HTTP → EXPO_PUBLIC_API_BASE (Django :8000)
  └── WebSocket → EXPO_PUBLIC_WS_URL (Node :3001)

Django (:8000)
  └── Publishes to Redis (channel "events" / "chat")

Redis (:6379)
  └── Subscribed by Node server

Node server (:3001)
  ├── Subscribes to Redis
  └── Broadcasts to all WebSocket clients
```
