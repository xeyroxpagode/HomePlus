"""T30 - Voice answer store (HOMI-D side).

Stores the generated answer audio (real Chatterbox ES-AR output) for a short
period so a client can download it through an AUTHENTICATED binary route
instead of carrying a large base64 blob inside the JSON turn response.

The store is process local and bounded:

* TTL (default 10 minutes) per entry.
* Maximum number of entries (default 32).
* Maximum audio size per entry (default 8 MB).

The audio id is opaque and random. It is NOT an authorization: the binary
route still requires the same authenticated session context as the turn
itself, and the entry records the household/actor that produced it.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional

TTL_S = float(os.getenv("HOMI_VOICE_AUDIO_TTL_S", "600"))
MAX_ENTRIES = int(os.getenv("HOMI_VOICE_AUDIO_MAX_ENTRIES", "32"))
MAX_BYTES = int(os.getenv("HOMI_VOICE_AUDIO_MAX_BYTES", str(8 * 1024 * 1024)))


@dataclass
class VoiceAudioEntry:
    audio_id: str
    audio: bytes
    mime_type: str
    sample_rate: Optional[int]
    duration_s: Optional[float]
    household_id: str
    actor_id: str
    created_at: float


_LOCK = threading.Lock()
_ENTRIES: dict[str, VoiceAudioEntry] = {}


def _purge_expired(now: float) -> None:
    expired = [key for key, entry in _ENTRIES.items() if now - entry.created_at > TTL_S]
    for key in expired:
        _ENTRIES.pop(key, None)


def store_audio(
    *,
    audio: bytes,
    household_id: str,
    actor_id: str,
    mime_type: str = "audio/wav",
    sample_rate: Optional[int] = None,
    duration_s: Optional[float] = None,
) -> Optional[str]:
    """Store the answer audio and return its opaque id, or None."""
    if not audio or len(audio) > MAX_BYTES:
        return None

    now = time.time()
    audio_id = "va_" + secrets.token_urlsafe(18)

    with _LOCK:
        _purge_expired(now)
        _ENTRIES[audio_id] = VoiceAudioEntry(
            audio_id=audio_id,
            audio=audio,
            mime_type=mime_type,
            sample_rate=sample_rate,
            duration_s=duration_s,
            household_id=household_id,
            actor_id=actor_id,
            created_at=now,
        )
        while len(_ENTRIES) > MAX_ENTRIES:
            oldest = min(_ENTRIES.values(), key=lambda item: item.created_at)
            _ENTRIES.pop(oldest.audio_id, None)

    return audio_id


def get_audio(audio_id: str) -> Optional[VoiceAudioEntry]:
    """Return the stored entry when it exists and did not expire."""
    now = time.time()
    with _LOCK:
        _purge_expired(now)
        return _ENTRIES.get(audio_id)


def release(audio_id: str) -> bool:
    with _LOCK:
        return _ENTRIES.pop(audio_id, None) is not None


def clear() -> None:
    with _LOCK:
        _ENTRIES.clear()
