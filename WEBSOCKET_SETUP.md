# WebSocket + Redis Setup

## Why WebSockets Show "Offline"

The app connects to the backend in two ways:

1. **REST API** – Django on **port 8000** (HTTP).
2. **WebSockets** – Node.js server on **port 3001** (ws/wss).

Django and the Node server talk via **Redis** (port 6379):

- When stats or chat are saved, **Django** publishes a message to Redis (channels `events` or `chat`).
- The **Node WebSocket server** subscribes to those channels and broadcasts every message to all connected clients.
- The **frontend** opens a WebSocket to the Node server (not to Django).

If you use **one ngrok URL** for both API and WebSocket, that URL is tunnelled to port 8000 only. So the app’s WebSocket connection hits Django instead of the Node server → connection fails → status shows **Offline**.

---

## How to Get WebSockets Online

### 1. Start Redis

- **Windows:** Install Redis (e.g. [Redis for Windows](https://github.com/microsoftarchive/redis/releases) or WSL) and run `redis-server`.
- **Mac:** `brew install redis` then `redis-server`.
- **Linux:** `sudo apt install redis-server` (or equivalent) then `redis-server`.

Check: `redis-cli ping` should reply `PONG`.

### 2. Start the Node WebSocket server

From the **backend** folder:

```bash
cd backend
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

### 3. Use two ngrok tunnels when testing on phone

- **Terminal 1:** `ngrok http 8000`  
  → Use the `https://...` URL for **API** in the frontend `.env`:  
  `EXPO_PUBLIC_API_BASE=https://xxxx.ngrok-free.app`

- **Terminal 2:** `ngrok http 3001`  
  → Use the `https://...` URL as **wss** for WebSockets:  
  `EXPO_PUBLIC_WS_URL=wss://yyyy.ngrok-free.app`

The two URLs must be different (two tunnels). Do **not** set `EXPO_PUBLIC_WS_URL` to the same URL as the API.

### 4. Restart Expo

After changing `.env`, restart the Expo app so it picks up the new `EXPO_PUBLIC_WS_URL`:

```bash
# In frontend3/SportsHub
npx expo start
```

---

## Same WiFi (no ngrok)

If the phone and computer are on the same Wi‑Fi:

1. Find your computer’s IP (e.g. `ipconfig` on Windows, `ifconfig` on Mac/Linux).
2. In the frontend `.env`:
   - `EXPO_PUBLIC_API_BASE=http://192.168.x.x:8000`
   - `EXPO_PUBLIC_WS_URL=ws://192.168.x.x:3001`
3. Start Redis and `node server.js` as above. No second ngrok needed.

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
