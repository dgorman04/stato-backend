# Step-by-step: Create a new S3 bucket for video uploads

Use this when creating a fresh bucket (e.g. `stato-recording-v2`) so CORS and permissions are correct from the start.

---

## Step 1: Create the bucket

1. Go to **AWS Console** → **S3** → **Buckets**.
2. Click **Create bucket**.
3. **Bucket name:** e.g. `stato-recording-v2` (must be globally unique; try adding your name or a suffix if taken).
4. **AWS Region:** Choose the same region you use elsewhere (e.g. **Europe (Stockholm) eu-north-1**).
5. **Block Public Access:** Leave **all four** checkboxes **on** (block all public access). Your app uses IAM credentials and presigned URLs; the bucket stays private.
6. Leave **Bucket Versioning** and **Default encryption** as you like (defaults are fine).
7. Click **Create bucket**.

---

## Step 2: Set CORS on the bucket

1. Open the new bucket (click its name).
2. Go to the **Permissions** tab.
3. Scroll to **Cross-origin resource sharing (CORS)**.
4. Click **Edit**.
5. Paste this (adjust origins if needed):

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "HEAD", "POST"],
    "AllowedOrigins": [
      "http://localhost:8081",
      "http://localhost:19006",
      "http://127.0.0.1:8081",
      "http://127.0.0.1:19006",
      "https://web-production-8d095.up.railway.app"
    ],
    "ExposeHeaders": ["ETag"]
  }
]
```

6. Click **Save changes**.

---

## Step 3: IAM permissions for the bucket

Your backend uses an IAM user (or role) that needs access to **this** bucket.

**Option A – Reuse existing IAM user**

1. Go to **IAM** → **Users** → select the user your backend uses (e.g. the one that had access to `stato-recording`).
2. Open its **Permissions** tab.
3. Edit the policy (or add an inline policy) so it includes the **new** bucket name. For example:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::stato-recording-v2",
        "arn:aws:s3:::stato-recording-v2/*"
      ]
    }
  ]
}
```

(If you want the same user to access both the old and new bucket, add both bucket ARNs and `/*` in `Resource`.)

**Option B – New IAM user for the new bucket**

1. **IAM** → **Users** → **Create user** (e.g. `stato-backend-v2`).
2. Attach a policy (inline or custom) with the same `Action` and `Resource` as above, but with your new bucket name.
3. **Security credentials** → **Create access key** (Application running outside AWS).
4. Copy **Access key ID** and **Secret access key**; you’ll put these in your backend env.

---

## Step 4: Point your backend at the new bucket

1. In **Railway** (or wherever the backend runs), open your backend service → **Variables**.
2. Set:
   - **`AWS_STORAGE_BUCKET_NAME`** = `stato-recording-v2` (your new bucket name).
   - **`AWS_S3_REGION_NAME`** = `eu-north-1` (or the region you chose in Step 1).
3. If you created a **new** IAM user (Option B), set:
   - **`AWS_ACCESS_KEY_ID`** = new access key
   - **`AWS_SECRET_ACCESS_KEY`** = new secret key  
   If you reused the same user (Option A), leave these as they are.
4. **Redeploy** the backend so it picks up the new variables.

---

## Step 5: Test

1. Open your app (e.g. `http://localhost:8081`).
2. Go to a match and **upload a video** (use the flow that gets a presigned URL and PUTs to S3).
3. In **S3** → your new bucket → **Objects**, you should see something like `recordings/match_<id>/<uuid>.mov` (or `.mp4`).
4. Playback should work via your backend stream URL (no change needed if you’re already using `recording_stream_url`).

---

## Checklist

- [ ] Bucket created, same region as the rest of your stack.
- [ ] Block public access left on.
- [ ] CORS set with **AllowedHeaders: ["*"]** and your frontend origins.
- [ ] IAM user/role has `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket` on the new bucket.
- [ ] Backend env has `AWS_STORAGE_BUCKET_NAME` = new bucket name (and new keys if you created a new user).
- [ ] Backend redeployed.
- [ ] Upload and playback tested.
