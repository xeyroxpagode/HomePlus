"""T31 — contrato HTTP de los endpoints de turno de HOMI-D.

Los proveedores reales (STT/THINK/TTS) se sustituyen SOLO en el limite para
verificar el protocolo. Este archivo NO certifica E2E real.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

import app as orchestrator_app
from homi_t31_turns import get_turn_authority

HEADERS = {
    "Authorization": "Bearer t31-contract-token",
    "X-Household-Id": "hh-t31-test",
    "X-Actor-Id": "actor-t31-test",
}
CID = "conv_t31_http_integration"


@pytest.fixture
def client():
    get_turn_authority().clear()
    with TestClient(orchestrator_app.app) as test_client:
        yield test_client
    get_turn_authority().clear()


def test_begin_partial_and_interrupt_contract(client, monkeypatch):
    opened = client.post(
        "/v1/voice/turn/begin",
        json={"conversation_id": CID, "turn_id": "turn_t31_integration_01"},
        headers=HEADERS,
    )
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["generation_id"] == "gen_1"
    assert body["turn_version"] == 1

    def _no_think(*args, **kwargs):
        raise AssertionError("un partial nunca debe invocar THINK/tools")

    monkeypatch.setattr(orchestrator_app, "invoke_with_tools_v2", _no_think)
    partial = client.post(
        "/v1/voice/transcript/partial",
        json={
            "conversation_id": CID,
            "turn_id": "turn_t31_integration_01",
            "text": "estoy hablando",
        },
        headers=HEADERS,
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["semantic_turn"] is False
    assert partial.json()["tools_executed"] is False

    interrupted = client.post(
        "/v1/voice/interrupt",
        json={"conversation_id": CID, "generation_id": "gen_1"},
        headers=HEADERS,
    )
    assert interrupted.status_code == 200, interrupted.text
    assert interrupted.json()["status"] == "accepted"
    assert interrupted.json()["current"] is False


def test_stale_generation_never_reaches_a_provider(client, monkeypatch):
    client.post(
        "/v1/voice/turn/begin",
        json={"conversation_id": CID, "turn_id": "turn_t31_integration_02"},
        headers=HEADERS,
    )
    client.post(
        "/v1/voice/interrupt",
        json={"conversation_id": CID, "generation_id": "gen_1"},
        headers=HEADERS,
    )

    def _no_provider(*args, **kwargs):
        raise AssertionError("una generacion invalidada no debe llamar a proveedores")

    monkeypatch.setattr(orchestrator_app, "transcribe_real", _no_provider)
    monkeypatch.setattr(orchestrator_app, "speak_real", _no_provider)

    response = client.post(
        "/v1/voice/transcribe",
        data={
            "conversation_id": CID,
            "turn_id": "turn_t31_integration_02",
            "generation_id": "gen_1",
        },
        files={"file": ("turn.wav", b"RIFF-not-real", "audio/wav")},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "interrupted"
    assert response.json()["speech_status"] == "interrupted"


def test_current_generation_produces_audio_and_speech_status(client, monkeypatch):
    client.post(
        "/v1/voice/turn/begin",
        json={"conversation_id": CID, "turn_id": "turn_t31_integration_03"},
        headers=HEADERS,
    )

    async def _stt(audio, audio_format, request_id):
        return "Hola Homi", {"engine": "contract", "model": "contract", "duration_s": 1.0}

    async def _speak(text):
        return b"RIFF-contract-audio", 24000, 1.0

    class _Result:
        def model_dump(self, mode="json"):
            return {
                "status": "SUCCESS",
                "result": {
                    "answer": "Hola",
                    "spoken_text": "Hola",
                    "decision_kind": "direct_response",
                },
            }

    async def _think(*args, **kwargs):
        return _Result()

    monkeypatch.setattr(orchestrator_app, "canonicalize", lambda audio, fmt: (b"wav", "wav"))
    monkeypatch.setattr(orchestrator_app, "transcribe_real", _stt)
    monkeypatch.setattr(orchestrator_app, "speak_real", _speak)
    monkeypatch.setattr(orchestrator_app, "invoke_with_tools_v2", _think)

    response = client.post(
        "/v1/voice/transcribe",
        data={
            "conversation_id": CID,
            "turn_id": "turn_t31_integration_03",
            "generation_id": "gen_1",
        },
        files={"file": ("turn.wav", b"RIFF-contract", "audio/wav")},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["generation_id"] == "gen_1"
    assert body["speech_status"] == "synthesized"
    assert body["audio_id"]


def test_think_stage_timeout_is_typed_and_bounded(client, monkeypatch):
    """A slow THINK provider must fail fast with 'think_timeout'."""
    async def _stt(audio, audio_format, request_id):
        return "Hola Homi", {"engine": "contract", "model": "contract"}

    async def _speak(text):
        return b"RIFF-contract-audio", 24000, 1.0

    async def _slow_think(*args, **kwargs):
        await asyncio.sleep(0.4)
        raise AssertionError("THINK should have been cancelled by its stage timeout")

    monkeypatch.setattr(orchestrator_app, "canonicalize", lambda audio, fmt: (b"wav", "wav"))
    monkeypatch.setattr(orchestrator_app, "transcribe_real", _stt)
    monkeypatch.setattr(orchestrator_app, "speak_real", _speak)
    monkeypatch.setattr(orchestrator_app, "invoke_with_tools_v2", _slow_think)
    monkeypatch.setattr(orchestrator_app, "HOMI_THINK_TIMEOUT_S", 0.1)

    response = client.post(
        "/v1/voice/transcribe",
        data={
            "conversation_id": CID,
            "turn_id": "turn_t31_think_timeout",
        },
        files={"file": ("turn.wav", b"RIFF-contract", "audio/wav")},
        headers=HEADERS,
    )
    assert response.status_code == 502
    assert "think_timeout" in response.json()["detail"]


def test_interrupted_delivery_is_never_marked_delivered(client):
    client.post(
        "/v1/voice/turn/begin",
        json={"conversation_id": CID, "turn_id": "turn_t31_integration_04"},
        headers=HEADERS,
    )
    client.post(
        "/v1/voice/interrupt",
        json={"conversation_id": CID, "generation_id": "gen_1"},
        headers=HEADERS,
    )
    delivered = client.post(
        "/v1/voice/delivery",
        json={
            "conversation_id": CID,
            "generation_id": "gen_1",
            "delivered_s": 1.25,
            "interrupted": True,
        },
        headers=HEADERS,
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["speech_status"] == "interrupted"
