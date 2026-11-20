"""T29 — SPEAK client (HOMI-D side): authenticated request to HOMI-C."""
from __future__ import annotations

import base64
import json
import os
import urllib.request

import httpx
from dataclasses import dataclass
from typing import Any, Optional

HOMI_C_BASE = os.getenv("HOMI_C_BASE", "http://homi-c:8010")
SPEAK_PATH = "/speak"


@dataclass
class SpeakResult:
    ok: bool
    audio_b64: Optional[str] = None
    sample_rate: Optional[int] = None
    format: str = "wav"
    duration_s: Optional[float] = None
    error: Optional[str] = None
    typed_error: Optional[str] = None
    node_id: Optional[str] = None


def speak_request(
    *,
    text: str,
    profile: str = "neutral",
    locale: str = "es-AR",
    auth_token: Optional[str] = None,
    timeout: float = 120.0,
) -> SpeakResult:
    payload = {
        "text": text,
        "profile": profile,
        "locale": locale,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    req = urllib.request.Request(
        HOMI_C_BASE + SPEAK_PATH,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return SpeakResult(
                ok=True,
                audio_b64=data.get("audio_b64"),
                sample_rate=data.get("sample_rate"),
                format=data.get("format", "wav"),
                duration_s=data.get("duration_s"),
                node_id=data.get("node_id"),
            )
    except urllib.error.HTTPError as exc:
        try:
            err = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err = {"error": str(exc)}
        return SpeakResult(
            ok=False,
            error=err.get("error", str(exc)),
            typed_error=err.get("typed_error", "SPEAK_FAILED"),
        )
    except Exception as exc:
        return SpeakResult(
            ok=False,
            error=str(exc),
            typed_error="SPEAK_TRANSPORT_ERROR",
        )


async def speak_request_async(
    *,
    text: str,
    profile: str = "neutral",
    locale: str = "es-AR",
    timeout: float = 120.0,
) -> SpeakResult:
    """Async SPEAK client used by the voice pipeline.

    urllib inside uvicorn's Proactor event loop stalls against the Windows
    TTS service; httpx.AsyncClient performs the same authenticated request
    without blocking the loop and with a real, bounded timeout.
    """
    payload = {"text": text, "profile": profile, "locale": locale}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(HOMI_C_BASE + SPEAK_PATH, json=payload)
        if resp.status_code >= 400:
            return SpeakResult(ok=False, error=resp.text[:300], typed_error="SPEAK_FAILED")
        data = resp.json()
        return SpeakResult(
            ok=True,
            audio_b64=data.get("audio_b64"),
            sample_rate=data.get("sample_rate"),
            format=data.get("format", "wav"),
            duration_s=data.get("duration_s"),
            node_id=data.get("node_id"),
        )
    except Exception as exc:
        return SpeakResult(ok=False, error=str(exc), typed_error="SPEAK_TRANSPORT_ERROR")


def speak_chunks(
    chunks: list[dict],
    *,
    profile: str = "neutral",
    auth_token: Optional[str] = None,
) -> list[SpeakResult]:
    results: list[SpeakResult] = []
    for c in chunks:
        r = speak_request(
            text=c["text"],
            profile=c.get("profile", profile),
            auth_token=auth_token,
        )
        results.append(r)
        if not r.ok:
            break
    return results