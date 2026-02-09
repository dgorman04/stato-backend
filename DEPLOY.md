# Deploying STATO backend to Railway with PostgreSQL

This guide gets your Django backend running on [Railway](https://railway.app) with a PostgreSQL database.

---

## 1. Prerequisites

- A [Railway](https://railway.app) account (GitHub login is easiest).
- Your backend code in a Git repo (GitHub, GitLab, or Bitbucket). Railway deploys from Git.

---

## 2. Create a new project on Railway

1. Go to [railway.app](https://railway.app) and log in.
2. Click **New Project**.
3. Choose **Deploy from GitHub repo** and select the repo that contains this `backend` folder (or the whole project; see **Root directory** below).
4. If your repo is the whole project (e.g. “Project Learning” with `backend/` inside), after adding the repo:
   - Select the new **Service** (the GitHub deploy).
   - Go to **Settings** → **Root Directory** and set it to **`backend`** so Railway uses the Django app as the root.
   - Save.

---

## 3. Add PostgreSQL

1. In the same project, click **+ New**.
2. Select **Database** → **PostgreSQL**.
3. Railway will create a Postgres service and expose a `DATABASE_URL` variable.
4. Go to your **backend service** (the one from GitHub).
5. Open **Variables**.
6. You should see **Reference** or **Add a variable**. Link the Postgres variable:
   - Click **+ New Variable** or **Add variable**.
   - Choose **Add a variable reference** (or “Reference”).
   - Select the **PostgreSQL** service and pick **`DATABASE_URL`**.
   - This makes `DATABASE_URL` available to your Django app.

---

## 4. Set required environment variables

In your **backend service** → **Variables**, add (or reference):

| Variable          | Example / description |
|-------------------|------------------------|
| `SECRET_KEY`      | A long random string, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DEBUG`           | `false` (use `false` in production) |
| `ALLOWED_HOSTS`   | Your Railway app host, e.g. `yourapp.up.railway.app` (no `https://`). For multiple hosts use comma-separated. |
| `DATABASE_URL`    | Already set by referencing the Postgres plugin (see step 3). |

Optional:

- **`CSRF_TRUSTED_ORIGINS`** – If you use the web app on a custom domain or specific URL, add it here as a comma-separated list, e.g. `https://yourapp.up.railway.app,https://yourfrontend.vercel.app`.
- **`REDIS_URL`** – Only if you add a Redis plugin later (e.g. for WebSockets). Not required for the API to run.

---

## 5. Run migrations (release command)

Railway can run migrations before each deploy:

1. Backend service → **Settings**.
2. Find **Deploy** or **Build & Deploy**.
3. Set **Release Command** to:
   ```bash
   python manage.py migrate --noinput
   ```
4. Save.

If you use `railway.json` in the repo, it already sets `releaseCommand` to the same. Either way, migrations will run automatically on each deploy.

---

## 6. Deploy

1. Push your code to the connected branch (e.g. `main`). Railway will build and deploy.
2. Or trigger a deploy from the Railway dashboard (e.g. **Deploy** / **Redeploy**).
3. After the build, open your service → **Settings** → **Networking** → **Generate Domain** to get a public URL like `https://yourbackend.up.railway.app`.

---

## 7. Check the API

- Open `https://yourbackend.up.railway.app/` in a browser. You should see the JSON message (e.g. “SportsHub API”, “api”: “/api/”).
- Try `https://yourbackend.up.railway.app/api/auth/login/` with a POST (e.g. via Postman or curl) to confirm auth works.

---

## 8. Point the frontend at Railway

In your Expo app (e.g. `frontend3/SportsHub/.env`), set:

```env
EXPO_PUBLIC_API_BASE=https://yourbackend.up.railway.app
```

Rebuild or restart the Expo app so it uses the new API URL.

---

## 9. Optional: Redis (WebSockets)

- The API works without Redis. WebSockets (e.g. live match updates) need Redis if you run more than one worker or want persistence.
- To add Redis: in the same Railway project, **+ New** → **Database** → **Redis**, then in the backend service add a variable reference to the Redis service’s `REDIS_URL`. The app already uses `REDIS_URL` when set.

---

## 10. Media files (video uploads)

- Uploaded videos are stored in `media/` on the server. On Railway, the filesystem is **ephemeral**: files can be lost on redeploy or when the container restarts.
- For persistent storage you’d need a volume (Railway Volumes) or an external store (e.g. S3) and to change Django’s file storage. For demos, ephemeral uploads are often acceptable.

---

## Summary checklist

- [ ] New Railway project, deploy from GitHub, **Root Directory** = `backend` if needed.
- [ ] PostgreSQL added and `DATABASE_URL` referenced in the backend service.
- [ ] Variables: `SECRET_KEY`, `DEBUG=false`, `ALLOWED_HOSTS=yourapp.up.railway.app`.
- [ ] Release command: `python manage.py migrate --noinput`.
- [ ] Generate public domain and test `/` and `/api/auth/login/`.
- [ ] Set `EXPO_PUBLIC_API_BASE` in the frontend to your Railway backend URL.
