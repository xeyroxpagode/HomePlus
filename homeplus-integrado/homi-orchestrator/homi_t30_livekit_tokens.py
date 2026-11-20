"""T30 — LiveKit token issuance seam (backend-authenticated).

No LiveKit server is deployed in this environment yet. This module is a
skeleton that issues a JWT only when the required env vars are present:

    HOMI_LIVEKIT_URL
    HOMI_LIVEKIT_API_KEY
    HOMI_LIVEKIT_API_SECRET

Without them it reports disabled and returns None, so callers can fail
closed. It does not open or configure any public service.
"""

from __future__ import annotations

import os
import time
from typing import Optional


def is_configured() -> bool:
    return bool(
        os.getenv("HOMI_LIVEKIT_URL")
        and os.getenv("HOMI_LIVEKIT_API_KEY")
        and os.getenv("HOMI_LIVEKIT_API_SECRET")
    )


def issue_token(room: str, identity: str, ttl_s: int = 3600) -> Optional[str]:
    if not is_configured():
        return None
    try:
        import jwt  # PyJWT
    except Exception:
        return None
    now = int(time.time())
    payload = {
        "iss": os.environ["HOMI_LIVEKIT_API_KEY"],
        "sub": identity,
        "iat": now,
        "exp": now + ttl_s,
        "nbf": now,
        "video": {
            "room": room,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
            # T31 — the bridge publishes turn events (voice_start/end,
            # speech_start/end, barge_in) over the LiveKit data channel.
            "canPublishData": True,
        },
    }
    return jwt.encode(
        payload,
        os.environ["HOMI_LIVEKIT_API_SECRET"],
        algorithm="HS256",
        headers={"kid": os.environ["HOMI_LIVEKIT_API_KEY"]},
    )
