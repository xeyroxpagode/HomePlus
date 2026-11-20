"""T31 — VAD, endpointing y barge-in del bridge HOMI-C.

Pruebas unitarias del acumulador con reloj controlado. No usan proveedores
reales ni certifican E2E.
"""

import array
from types import SimpleNamespace

import bridge_c
import pytest


def _frame(amplitude: int, samples: int = 320) -> bytes:
    return array.array("h", [amplitude] * samples).tobytes()


@pytest.fixture
def clock(monkeypatch):
    now = [1_700_000_000.0]
    monkeypatch.setattr(bridge_c, "time", SimpleNamespace(time=lambda: now[0]))
    return now


def test_noise_does_not_open_a_turn(clock):
    acc = bridge_c.TurnAccumulator()
    for _ in range(20):
        assert acc.push(_frame(100)) is False
    assert acc.speaking is False
    assert acc.speech_candidate == 0


def test_conservative_onset_and_endpoint(clock):
    acc = bridge_c.TurnAccumulator()
    # Only two loud frames: not enough for the conservative onset.
    acc.push(_frame(3000))
    clock[0] += 0.1
    acc.push(_frame(3000))
    clock[0] += 0.1
    assert acc.speaking is False

    acc.push(_frame(3000))
    clock[0] += 0.1
    assert acc.speaking is True

    # Sustained speech, then a pause shorter than SILENCE_SECONDS: no endpoint.
    for _ in range(7):
        acc.push(_frame(3000))
        clock[0] += 0.1
    clock[0] += 0.5
    acc.push(_frame(0))
    assert acc.push(_frame(0)) is False

    # A real pause closes exactly one endpoint.
    clock[0] += bridge_c.SILENCE_SECONDS + 0.2
    assert acc.push(_frame(0)) is True
    captured = acc.take()
    assert 0 < len(captured) < bridge_c.MIN_TURN_BYTES  # short synthetic utterance
    assert acc.speaking is False
    assert acc.take() == b""


def test_barge_in_requires_high_sustained_speech_outside_guard(clock):
    acc = bridge_c.TurnAccumulator()
    acc.playback_active = True
    acc.playback_started_at = clock[0]

    # Loud enough for normal speech, but below BARGE_IN_RMS: no barge-in.
    for _ in range(20):
        assert acc.push(_frame(1000)) is False
    assert acc.barge_in is False

    # Above BARGE_IN_RMS but inside the echo guard window: still no barge-in.
    clock[0] += 0.2
    for _ in range(10):
        acc.push(_frame(3000))
    assert acc.barge_in is False

    # Outside the guard, sustained loud speech triggers barge-in.
    clock[0] += bridge_c.BARGE_IN_GUARD_S + 0.1
    for _ in range(10):
        acc.push(_frame(3000))
        clock[0] += 0.08
    assert acc.barge_in is True
    # Playback never produces an endpoint: the buffer awaits the next turn.
    clock[0] += 5.0
    assert acc.push(_frame(0)) is False
