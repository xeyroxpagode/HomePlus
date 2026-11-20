"""HOMI-D HEAR adapter (T26): audio -> STT (HOMI-C) -> transcript.

Responsabilidad minima: validar audio, llamar al STT de HOMI-C y devolver
el texto transcrito. No interpreta intencion ni ejecuta herramientas.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Optional

import httpx

STT_BASE_URL = os.getenv("HOMI_STT_BASE_URL", "http://homi-c:8010")
STT_TOKEN = os.getenv("HOMI_STT_TOKEN", "homi-stt-token-2026")
STT_TIMEOUT_S = float(os.getenv("HOMI_STT_TIMEOUT_S", "120"))

# Deduplicacion en memoria (limitada al proceso; no persistente tras reinicio).
_SEEN_REQUESTS: set[str] = set()


def is_duplicate(request_id: str) -> bool:
    return request_id in _SEEN_REQUESTS


def mark_seen(request_id: str) -> None:
    _SEEN_REQUESTS.add(request_id)


async def transcribe_audio(
    audio_bytes: bytes,
    audio_format: str,
    request_id: str,
) -> dict:
    """Llama al STT de HOMI-C y retorna el dict de respuesta (stt-result-1.0)."""
    url = f"{STT_BASE_URL.rstrip('/')}/transcribe"
    headers = {
        "Authorization": f"Bearer {STT_TOKEN}",
        "X-Request-Id": request_id,
        "X-Audio-Format": audio_format,
        "Content-Type": "application/octet-stream",
    }
    async with httpx.AsyncClient(timeout=STT_TIMEOUT_S) as client:
        resp = await client.post(url, content=audio_bytes, headers=headers)
    resp.raise_for_status()
    return resp.json()