"""
Short-lived signed token for recording stream URL.
The <video> element cannot send Authorization header, so we allow GET with ?token=.
"""
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature

# 1 hour
STREAM_TOKEN_MAX_AGE = 3600


def make_stream_token(match_id, user_id):
    """Return a signed token string for stream URL. Include match_id and user_id."""
    signer = TimestampSigner()
    payload = f"stream:{match_id}:{user_id}"
    return signer.sign(payload)


def validate_stream_token(token, match_id):
    """
    Validate token and match_id. Returns (True, user_id) if valid, else (False, None).
    """
    if not token or not match_id:
        return False, None
    signer = TimestampSigner()
    try:
        payload = signer.unsign(token, max_age=STREAM_TOKEN_MAX_AGE)
        # payload is "stream:match_id:user_id"
        parts = payload.split(":", 2)
        if len(parts) != 3 or parts[0] != "stream":
            return False, None
        token_match_id = int(parts[1])
        user_id = int(parts[2])
        if token_match_id != match_id:
            return False, None
        return True, user_id
    except (SignatureExpired, BadSignature, ValueError):
        return False, None
