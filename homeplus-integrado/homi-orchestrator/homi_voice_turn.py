"""T30 - Voice turn pipeline (HOMI-D side, Expo Go / HTTP transport).

One single semantic turn per intervention:

    audio (any format)
      -> server side canonicalisation (mono 16 kHz PCM WAV, FFmpeg)
      -> HOMI-C STT (real faster-whisper, ONE inference)
      -> semantic turn through the canonical THINK pipeline (HOMI-A real)
      -> HOMI-C SPEAK (real Chatterbox ES-AR)
      -> answer audio stored for an AUTHENTICATED binary download

There is exactly ONE STT inference and exactly ONE semantic turn per
intervention. The THINK fixture is NEVER used here: the fixture is an
evaluation-only seam and this module fails closed instead of faking a
semantic answer.

The transport (HTTP turns or LiveKit) only decides HOW the audio arrives;
it never changes the semantic pipeline.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from typing import Any, Optional

import httpx

import homi_audio
from homi_speak import speak_request, speak_request_async

STT_TIMEOUT_S = float(os.getenv("HOMI_STT_TIMEOUT_S", "120"))
SPEAK_TIMEOUT_S = float(os.getenv("HOMI_SPEAK_TIMEOUT_S", "120"))
MAX_AUDIO_BYTES = 50 * 1024 * 1024

# HOMI-C runs the STT (faster-whisper, CUDA) and the TTS (Chatterbox ES-AR,
# CUDA) on the SAME 6 GB GPU. Two concurrent voice turns would make both
# models fight for the VRAM and fail with OOM / timeouts. The pipeline is
# therefore serialized: one voice turn at a time, STT and SPEAK never
# overlap with another turn.
_VOICE_PIPELINE_LOCK = asyncio.Lock()


def voice_pipeline_lock():
    """Return the global voice pipeline lock."""
    return _VOICE_PIPELINE_LOCK


class VoiceTurnError(Exception):
    """Raised when the voice turn cannot be completed."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _stt_endpoint() -> str:
    base = os.getenv("HOMI_STT_BASE_URL", "http://homi-c:8010").rstrip("/")
    return f"{base}/transcribe"


async def transcribe_real(
    audio: bytes,
    audio_format: str,
    request_id: str,
) -> tuple[str, dict[str, Any]]:
    """Run the REAL STT of HOMI-C over an already canonical WAV payload."""
    headers = {
        "Authorization": f"Bearer {os.getenv('HOMI_STT_TOKEN', 'homi-stt-token-2026')}",
        "X-Request-Id": request_id,
        "X-Audio-Format": "wav",
        "Content-Type": "application/octet-stream",
    }
    async with httpx.AsyncClient(timeout=STT_TIMEOUT_S) as client:
        resp = await client.post(_stt_endpoint(), content=audio, headers=headers)
    resp.raise_for_status()
    payload = resp.json()

    text = (payload.get("text") or "").strip()
    if payload.get("status") != "success" or not text:
        raise VoiceTurnError(
            "stt_empty",
            "HOMI-C no produjo una transcripcion final.",
            status_code=422,
        )
    return text, payload


def canonicalize(audio: bytes, declared_format: str) -> tuple[bytes, str]:
    """Convert an uploaded payload to the canonical STT format.

    The real format is detected from the magic bytes; the client hint is
    only a fallback. The conversion happens on the SERVER so the phone
    never has to produce a WAV.
    """
    if not audio:
        raise VoiceTurnError("audio_empty", "El audio enviado esta vacio.")

    if len(audio) > MAX_AUDIO_BYTES:
        raise VoiceTurnError(
            "audio_too_large",
            "El audio supera el limite de 50 MB.",
            status_code=413,
        )

    real_format = homi_audio.detect_format(audio, declared_format)
    converted, error = homi_audio.to_canonical_wav(audio, real_format)
    if converted is None:
        raise VoiceTurnError(
            "audio_conversion_failed",
            f"No se pudo convertir el audio ({error}).",
            status_code=415,
        )
    return converted, real_format


async def speak_real(text: str) -> tuple[Optional[bytes], Optional[int], Optional[float]]:
    """Run the REAL SPEAK of HOMI-C (Chatterbox ES-AR) over a text."""
    if not text.strip():
        return None, None, None

    result = await speak_request_async(
        text=text,
        profile="neutral",
        locale="es-AR",
        timeout=SPEAK_TIMEOUT_S,
    )
    if not result.ok:
        raise VoiceTurnError(
            "speak_failed",
            f"HOMI-C no pudo sintetizar la respuesta ({result.typed_error}).",
            status_code=502,
        )
    if not result.audio_b64:
        raise VoiceTurnError(
            "speak_empty",
            "HOMI-C devolvio una respuesta sin audio.",
            status_code=502,
        )

    audio = base64.b64decode(result.audio_b64)

    # The answer audio is normalized to 16 bit PCM so it can be played by
    # iOS and published as a LiveKit track without a client side codec.
    normalized, error = homi_audio.to_pcm16_wav(audio)
    if normalized:
        audio = normalized
    else:
        # Fall back to the original payload: the download route still works.
        pass

    return audio, result.sample_rate, result.duration_s


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def now_ms() -> int:
    return int(time.time() * 1000)
