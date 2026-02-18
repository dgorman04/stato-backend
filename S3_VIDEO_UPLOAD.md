# S3 Video Upload & Playback – Troubleshooting

## Flow

1. **Frontend (web)** calls `POST /api/matches/<id>/video/upload-url/` with `{ "filename": "..." }`.
2. **Backend** returns `{ "upload_url", "key" }`. Presigned PUT URL is for the bucket/key; no `Content-Type` is signed so the client can send the real MIME type (e.g. `video/quicktime` for .mov).
3. **Frontend** uploads the file with `PUT upload_url`, body = blob, header `Content-Type: blob.type || "video/mp4"`.
4. **Frontend** calls `POST /api/matches/<id>/video/confirm/` with `{ "key" }`. Backend saves the recording with `file = key` (S3 key).
5. **Playback** uses `GET /api/matches/<id>/recording/stream/?token=<signed_token>`. Backend streams from S3 (or local) via `default_storage.open(key)`.

## Why S3 might not be working

### 1. **403 on PUT (SignatureDoesNotMatch)**

- **Cause:** Presigned URL was generated with a specific `Content-Type` (e.g. `video/mp4`) but the client sent another (e.g. `video/quicktime` for .mov). S3 rejects because the request does not match the signature.
- **Fix (done):** Backend does **not** include `ContentType` in `generate_presigned_url` Params, so the client can send any `Content-Type` and the signature is valid.

### 2. **CORS on PUT to S3**

- **Symptom:** Browser blocks the PUT with “blocked by CORS policy” or “No 'Access-Control-Allow-Origin' header”.
- **Cause:** S3 bucket CORS must allow the **origin** of the page (e.g. `http://localhost:8081` or your Railway web URL) and the **PUT** method.
- **Fix:** In AWS S3 → bucket → Permissions → CORS, use something like:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"]
  }
]
```

- For production, replace `"*"` in `AllowedOrigins` with your frontend origins (e.g. `https://web-production-xxx.up.railway.app`, `http://localhost:8081`).

### 3. **Backend not using S3 (uploads never hit S3)**

- **Symptom:** “Video uploaded successfully” but S3 bucket is empty; recording URL is `https://your-backend/media/...`.
- **Cause:** On the **deployed** backend (e.g. Railway), env vars for S3 are missing or wrong, so `DEFAULT_FILE_STORAGE` stays default (local). Then upload-url returns 503 or the frontend falls back to `POST /video/`, which saves to local/disk.
- **Fix:** On Railway (or wherever the backend runs), set:
  - `AWS_STORAGE_BUCKET_NAME` = your bucket (e.g. `stato-recording`)
  - `AWS_S3_REGION_NAME` = bucket region (e.g. `eu-north-1`)
  - `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` = IAM user with `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` on that bucket.
- **Check:** After deploy, call `POST /api/matches/<id>/video/upload-url/`. If you get 503, S3 is not configured in that environment.

### 4. **Presigned upload fails silently, fallback used**

- **Symptom:** Upload “works” but file is in backend `/media/` (or 502 on fallback) and not in S3.
- **Cause:** PUT to presigned URL failed (CORS, 403, network). Frontend catches the error and falls back to `POST /video/`, which goes through the backend and may timeout or save locally.
- **Fix:** Open DevTools → Network, upload a video, and inspect the **PUT** to the S3 URL. If it’s red, check status (403 = signature/CORS; 0 or CORS error = CORS). Fix CORS and Content-Type as above. Ensure the frontend uses the **stream URL with token** for playback so you’re not relying on S3 CORS for GET.

### 5. **Playback (stream) works from backend, not from S3 URL**

- Playback is designed to go through **your backend**: `GET /api/matches/<id>/recording/stream/?token=...`. The backend then streams from S3 (or local) via `default_storage`. So the browser never talks to S3 for playback; no S3 CORS needed for GET. If you see CORS errors when loading a **presigned S3 URL** in a `<video>` tag, that’s expected unless you fixed S3 CORS for GET; use the **stream URL with token** as the video `src` instead.

## Checklist

- [ ] Railway (or backend host) has `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` set.
- [ ] S3 bucket CORS allows your frontend origin and `PUT` (and `GET`/`HEAD` if you ever use direct S3 URLs for playback).
- [ ] Backend does **not** sign `ContentType` in the presigned URL (so .mov and .mp4 both work).
- [ ] Frontend uses `recording_stream_url` (with `?token=`) for the video `src`, not the raw S3 URL.
