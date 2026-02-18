# CORS: "No 'Access-Control-Allow-Origin' header" – What to check

## 1. Which URL is failing?

The message means **the server that answered the request** did not send `Access-Control-Allow-Origin`. That server is either **your API** or **S3**.

**How to see it:**
- Open **DevTools (F12) → Network**.
- Reproduce the error (e.g. load the page, upload a video, or play a video).
- Find the **red** (failed) request.
- Check **Request URL**:
  - If it contains **`amazonaws.com`** or **`s3.`** → the failing request is **to S3**. Your backend cannot add headers to S3 responses. See section 2.
  - If it is **your API** (e.g. `https://something.up.railway.app/api/...` or `http://localhost:8000/api/...`) → the failing request is **to your backend**. See section 3.

## 2. If the failing request is to S3

You **cannot** add CORS headers to S3 from your backend. You have two options:

**Option A – Use the stream URL (recommended)**  
- Use **`recording_stream_url`** (with `?token=...`) as the `<video src>`, not the raw S3 URL.  
- Then the browser only talks to your API; no request goes to S3 from the frontend, so no S3 CORS.

**Option B – Configure S3 CORS**  
- In **AWS S3 → your bucket → Permissions → CORS**, add a configuration that allows your frontend origin and the methods you use (e.g. GET, PUT).  
- Example: `AllowedOrigins`: your app URL(s) or `["*"]`, `AllowedMethods`: `["GET","PUT","HEAD"]`.

## 3. If the failing request is to your API

The backend is already configured to send CORS (django-cors-headers + explicit headers on the recording stream and media views). If you still see the error for an API URL:

- **502 / 504:** The response might be coming from the proxy (e.g. Railway) before it reaches Django, so Django’s CORS headers are never sent. Fix the underlying error (e.g. timeout, crash) so that Django responds.
- **Exact request:** Share the **Request URL** and **Request Method** (and whether it’s the main request or an OPTIONS preflight). Then we can target that endpoint.

## What to send when asking for help

Please provide:

1. **Request URL** of the failing request (from Network tab).
2. **Request Method** (GET, PUT, OPTIONS, etc.).
3. **Status code** if shown (e.g. 403, 404, 502).
4. **Where you’re running the frontend** (e.g. `http://localhost:8081`, or your Railway web URL).

With that, we can say whether the fix is S3 CORS, using the stream URL, or something on the backend.
