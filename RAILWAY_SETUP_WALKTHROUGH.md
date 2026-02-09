# Railway + PostgreSQL setup – full walkthrough

Follow these steps in order. Replace placeholders like `your-repo` and `yourapp` with your actual names.

---

## Part A: Before you start

### Step 1 – Push your code to GitHub (if not already)

1. Open a terminal in your project root (the folder that contains `backend` and `frontend3`).
2. If you haven’t used Git yet:
   ```bash
   git init
   git add .
   git commit -m "Initial commit - STATO app"
   ```
3. Create a new repo on GitHub (e.g. `Project-Learning` or `stato-app`). Do **not** add a README if the folder already has content.
4. Add the remote and push (replace with your GitHub URL and branch name):
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git branch -M main
   git push -u origin main
   ```
5. Confirm on GitHub that you see the `backend` folder (and `frontend3`, etc.) in the repo.

---

### Step 2 – Generate a secret key for production

On your machine, run once:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copy the long string that’s printed (e.g. `Kx7f...`). You’ll paste it in Railway as `SECRET_KEY` in a later step.

---

## Part B: Railway project and backend service

### Step 3 – Log in to Railway and create a project

1. Go to **https://railway.app** and sign in (e.g. with GitHub).
2. Click **“New Project”**.

---

### Step 4 – Deploy from GitHub

1. Choose **“Deploy from GitHub repo”**.
2. If asked, authorize Railway to access your GitHub (one-time).
3. Select the repository that contains your `backend` folder (e.g. `Project-Learning` or whatever you pushed in Step 1).
4. Click **“Deploy now”** or **“Add service”**. Railway will create a service and start a build. The first build may fail until we set the root directory and variables; that’s expected.

---

### Step 5 – Set the root directory so Railway finds the Django app

Railway must build from the folder that contains `manage.py` and `requirements.txt`.

**Option A – Railway says “couldn’t find root directory” or path has spaces**  
Use a **backend-only repo** so you don’t need a root path at all. See **“Fix: Backend-only repo (no root path)”** at the end of this doc, then in Railway connect that new repo and **leave Root Directory empty**. Then skip to Step 6.

**Option B – Use a path (if your repo has backend inside a subfolder)**  
1. On GitHub, open **https://github.com/dgorman04/3rd-Year-Project** and see what’s at the **very top level** (first folder(s) you see).
2. If you see **`backend`** and **`frontend3`** at the top: in Railway set **Root Directory** to **`backend`** (nothing else).
3. If you see only **`OneDrive`** at the top: click into it and go **OneDrive → Attachments → Documents → Project Learning → backend**. Copy the full path from the address bar (e.g. `OneDrive/Attachments/Documents/Project Learning/backend`). If Railway rejects it (e.g. because of the space), try with a URL‑encoded space: **`OneDrive/Attachments/Documents/Project%20Learning/backend`**.

**Do this:**

1. In the Railway project, click the **service** that was just created (the one linked to GitHub).
2. Go to the **Settings** tab (or the gear icon).
3. Find **“Root Directory”** or **“Build”** → **“Root Directory”**.
4. Enter the value from Option A or B above (no leading slash).
5. Click **Save** or wait for it to auto-save.
6. Trigger a new deploy (e.g. **“Redeploy”** or **“Deploy”** in the **Deployments** tab).

---

### Step 6 – Generate a public URL for the backend

1. Still in your **backend service**, open the **Settings** tab.
2. Find **“Networking”** or **“Public Networking”**.
3. Click **“Generate Domain”** (or **“Add domain”**).
4. Railway will assign a URL like `something-production-xxxx.up.railway.app`. Copy this full URL (e.g. `https://something-production-xxxx.up.railway.app`).
5. The **host** for `ALLOWED_HOSTS` is the domain **without** `https://`, e.g. `something-production-xxxx.up.railway.app`. Keep that written down; you’ll use it in the next part.

---

## Part C: Add PostgreSQL and variables

### Step 7 – Add a PostgreSQL database

1. In the **same** Railway project (not inside the backend service), click **“+ New”** (or **“Add service”**).
2. Choose **“Database”** → **“Add PostgreSQL”** (or **“PostgreSQL”**).
3. Wait until the Postgres service is created. You’ll see a new card/service in the project.

---

### Step 8 – Connect the backend to the database

1. Click back on your **backend service** (the one from GitHub).
2. Open the **Variables** tab.
3. Click **“+ New Variable”** or **“Add variable”** / **“Variable reference”**.
4. Choose **“Add a reference”** (or **“Reference”**). You want to reference a variable from another service, not type a value.
5. Select the **PostgreSQL** service.
6. Pick the variable **`DATABASE_URL`**.
7. Confirm. You should now see `DATABASE_URL` in the backend’s variable list (often shown as a reference, not the raw URL). This is correct.

---

### Step 9 – Add the rest of the required variables

Still in the **backend service** → **Variables** tab, add these as **raw** variables (you type the value):

| Variable        | Value |
|-----------------|--------|
| `SECRET_KEY`    | The long string you generated in Step 2. |
| `DEBUG`         | `false` (all lowercase). |
| `ALLOWED_HOSTS` | Your Railway host **without** `https://`, e.g. `something-production-xxxx.up.railway.app`. |

- For **SECRET_KEY**: paste the token from Step 2.
- For **DEBUG**: type exactly `false`.
- For **ALLOWED_HOSTS**: paste only the hostname (e.g. `something-production-xxxx.up.railway.app`), no commas unless you have multiple hosts.

Save after each one if the UI asks. You should end up with at least: `DATABASE_URL` (reference), `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`.

---

### Step 10 – Set the release command (migrations)

1. In the **backend service**, go to **Settings**.
2. Find **“Deploy”** or **“Build & Deploy”** or **“Release Command”**.
3. In **Release Command**, enter:
   ```bash
   python manage.py migrate --noinput
   ```
4. Save. This runs Django migrations before each deploy so the Postgres schema stays up to date.

---

### Step 11 – Redeploy and wait for success

1. Go to the **Deployments** tab of the backend service.
2. Click **“Redeploy”** (or the three dots on the latest deploy → **Redeploy**).
3. Wait until the status is **Success** (green). If it fails, open the build/deploy logs and check for errors (often a missing variable or wrong root directory).
4. After a successful deploy, the app will be live at the domain you generated in Step 6.

---

## Part D: Check that the API works

### Step 12 – Test the root URL

1. Open a browser and go to your backend URL, e.g. `https://something-production-xxxx.up.railway.app/`.
2. You should see JSON like:
   ```json
   { "message": "SportsHub API", "api": "/api/", ... }
   ```
3. If you get “DisallowedHost” or 400, double-check **ALLOWED_HOSTS** (Step 9): it must be exactly the hostname (no `https://`, no path).

---

### Step 13 – Test login (optional but recommended)

1. Open **https://your-backend-url.up.railway.app/api/auth/login/** in a browser. You may see “Method not allowed” for GET – that’s normal.
2. To test POST (e.g. with PowerShell):
   ```powershell
   Invoke-RestMethod -Uri "https://YOUR-BACKEND-URL.up.railway.app/api/auth/login/" -Method POST -ContentType "application/json" -Body '{"username":"test@test.com","password":"testpass123"}'
   ```
   You expect either **401** (wrong credentials) or **200** with `access` and `refresh` tokens. Both mean the API is working. A 404 or 500 means something is wrong with the deploy or variables.

---

## Part E: Use the API from the frontend

### Step 14 – Point the Expo app at Railway

1. On your computer, open the file: **`frontend3/SportsHub/.env`**.
2. Set the API base to your Railway backend URL (with `https://`):
   ```env
   EXPO_PUBLIC_API_BASE=https://YOUR-BACKEND-URL.up.railway.app
   ```
   Example:
   ```env
   EXPO_PUBLIC_API_BASE=https://something-production-xxxx.up.railway.app
   ```
3. Save the file. If there are other lines (e.g. `EXPO_PUBLIC_WS_URL`), you can leave them; the app will use the new API for REST calls.

---

### Step 15 – Restart the Expo app

1. If the Expo dev server is running, stop it (Ctrl+C in the terminal).
2. From the `frontend3/SportsHub` folder, run:
   ```bash
   npx expo start
   ```
3. Open the app (web or device). Log in or create a team – that will hit the Railway backend and PostgreSQL. If you can log in or see data, the full setup is working.

---

## Part F: Create a user on production (optional)

The production database starts empty. To get a team and manager account:

1. **Option A – Use the app:** Open the Expo app pointed at Railway and use the **Team signup** flow (e.g. from the home or team signup screen). That creates a team and manager in the Railway Postgres DB.
2. **Option B – Django admin:** Create a superuser on your machine using the **production** database, then log in to admin on Railway (only do this if you’re comfortable with `DATABASE_URL` on your machine):
   - Temporarily set `DATABASE_URL` in your local `.env` to the same value as Railway (copy from Railway’s Postgres service → **Variables** → `DATABASE_URL`).
   - Run: `python manage.py createsuperuser`.
   - Then in the browser go to `https://your-backend-url.up.railway.app/admin/` and log in.

For most people, Option A (sign up through the app) is enough.

---

## Fix: Backend-only repo (no root path)

If Railway keeps saying it **couldn’t find the root directory**, use a separate repo where the **backend is at the root**. Then Railway doesn’t need a Root Directory at all.

1. **Create a new repo on GitHub** (e.g. `3rd-year-project-backend` or `stato-backend`). Leave it empty (no README).

2. **On your PC**, open PowerShell and run (replace paths if yours are different):
   ```powershell
   cd "c:\Users\darra\OneDrive\Attachments\Documents\Project Learning"
   mkdir stato-backend-deploy
   cd stato-backend-deploy
   git init
   ```
3. **Copy the backend contents** (not the `backend` folder itself – the files *inside* it) into this new folder so that `manage.py`, `requirements.txt`, the `backend` and `stato` folders, etc. are at the **root** of `stato-backend-deploy`:
   ```powershell
   Copy-Item -Path "..\backend\*" -Destination "." -Recurse -Force
   ```
4. **Commit and push to the new repo:**
   ```powershell
   git add .
   git commit -m "Backend for Railway deploy"
   git branch -M main
   git remote add origin https://github.com/dgorman04/3rd-year-project-backend.git
   git push -u origin main
   ```
   (Use your new repo URL instead of `3rd-year-project-backend` if the name is different.)

5. **In Railway:**  
   - Either add a **new service** → **Deploy from GitHub repo** → select this new repo,  
   - Or change the existing service’s **source** to this new repo.  
   - Leave **Root Directory** **empty** (or a single dot `.`).  
   - Redeploy. The build should find `requirements.txt` and `manage.py` at the root.

After that, continue from **Step 6** (generate domain, add Postgres, variables, etc.) in this walkthrough. Your main project (3rd-Year-Project) can stay as-is; this repo is only for Railway.

---

## Quick checklist

- [ ] Code pushed to GitHub (Step 1).
- [ ] Secret key generated (Step 2).
- [ ] Railway project created, deploy from GitHub (Steps 3–4).
- [ ] Root directory set to `backend` (Step 5).
- [ ] Public domain generated and copied (Step 6).
- [ ] PostgreSQL added (Step 7).
- [ ] `DATABASE_URL` referenced in backend variables (Step 8).
- [ ] `SECRET_KEY`, `DEBUG=false`, `ALLOWED_HOSTS` set (Step 9).
- [ ] Release command set to `python manage.py migrate --noinput` (Step 10).
- [ ] Redeploy successful (Step 11).
- [ ] Root URL returns JSON (Step 12).
- [ ] `.env` in frontend has `EXPO_PUBLIC_API_BASE=https://...` (Step 14).
- [ ] Expo restarted and app can hit API (Step 15).

If any step fails, check the Railway build/deploy logs and the variable names (case-sensitive). The most common issues are wrong **Root Directory**, missing **ALLOWED_HOSTS**, or **DATABASE_URL** not linked to the Postgres service.
