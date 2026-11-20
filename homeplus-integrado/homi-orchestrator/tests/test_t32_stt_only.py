"""HOMI V1 — endpoint STT-only (decision de Actor A).

La transcripcion es semanticamente read-only: usa el STT real de HOMI-C pero
NUNCA abre un turno semantico, invoca THINK, ejecuta herramientas, sintetiza
audio ni escribe el ledger. Los proveedores se sustituyen SOLO en el limite
para verificar el contrato; esto no certifica E2E real.
"""

import contextlib

import pytest
from fastapi.testclient import TestClient

import app as orchestrator_app

HEADERS = {
    "Authorization": "Bearer t32-contract-token",
    "X-Household-Id": "hh-t32-test",
    "X-Actor-Id": "actor-t32-test",
}
TRANSCRIPT = "Hola Homi, necesito revisar el Planner"


@pytest.fixture
def client():
    with TestClient(orchestrator_app.app) as test_client:
        yield test_client


def _stub_stt(monkeypatch, transcript=TRANSCRIPT):
    monkeypatch.setattr(
        orchestrator_app, "canonicalize", lambda audio, declared: (b"WAV-canonico", "wav")
    )
    monkeypatch.setattr(orchestrator_app, "_wav_duration_s", lambda wav: 1.0)
    monkeypatch.setattr(orchestrator_app, "is_duplicate", lambda request_id: False)
    monkeypatch.setattr(orchestrator_app, "mark_seen", lambda request_id: None)

    async def _transcribe(audio, audio_format, request_id):
        return transcript, {
            "engine": "faster-whisper",
            "model": "small.multilingual",
            "duration_s": 1.0,
        }

    monkeypatch.setattr(orchestrator_app, "transcribe_real", _transcribe)

    @contextlib.asynccontextmanager
    async def _no_lock():
        yield

    monkeypatch.setattr(orchestrator_app, "voice_pipeline_lock", _no_lock)


def _forbid_semantic_side_effects(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("STT-only no debe invocar esta funcion")

    monkeypatch.setattr(orchestrator_app, "invoke_with_tools_v2", _forbidden)
    monkeypatch.setattr(orchestrator_app, "speak_real", _forbidden)
    monkeypatch.setattr(orchestrator_app, "get_turn_authority", _forbidden)
    monkeypatch.setattr(orchestrator_app.homi_voice_store, "store_audio", _forbidden)


def test_transcript_is_read_only(client, monkeypatch):
    _stub_stt(monkeypatch)
    _forbid_semantic_side_effects(monkeypatch)

    response = client.post(
        "/v1/voice/transcript",
        files={"file": ("dictacion.m4a", b"audio-real", "audio/mp4")},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["transcript"] == TRANSCRIPT
    assert body["semantic_turn"] is False
    assert body["tools_executed"] is False
    assert body["tts_generated"] is False
    assert body["stt"]["engine"] == "faster-whisper"
    # No semantic state is created or echoed back to the client.
    for forbidden in ("generation_id", "turn_id", "audio_id", "answer", "proposal"):
        assert forbidden not in body


def test_empty_audio_is_rejected(client, monkeypatch):
    _stub_stt(monkeypatch)
    response = client.post(
        "/v1/voice/transcript",
        files={"file": ("dictacion.m4a", b"", "audio/mp4")},
        headers=HEADERS,
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "audio_vacio"


def test_too_long_audio_is_rejected(client, monkeypatch):
    _stub_stt(monkeypatch)
    monkeypatch.setattr(orchestrator_app, "_wav_duration_s", lambda wav: 121.0)
    response = client.post(
        "/v1/voice/transcript",
        files={"file": ("dictacion.m4a", b"audio-real", "audio/mp4")},
        headers=HEADERS,
    )
    assert response.status_code == 413, response.text
    assert response.json()["detail"] == "audio_demasiado_largo"


def test_duplicate_request_does_not_run_stt(client, monkeypatch):
    _stub_stt(monkeypatch)
    monkeypatch.setattr(orchestrator_app, "is_duplicate", lambda request_id: True)

    async def _no_stt(*args, **kwargs):
        raise AssertionError("un request duplicado no debe repetir la inferencia STT")

    monkeypatch.setattr(orchestrator_app, "transcribe_real", _no_stt)

    response = client.post(
        "/v1/voice/transcript",
        files={"file": ("dictacion.m4a", b"audio-real", "audio/mp4")},
        headers={**HEADERS, "X-Request-Id": "req_duplicado"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "duplicate"
    assert response.json()["transcript"] == ""
