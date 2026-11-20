"""T31 — pruebas unitarias de la autoridad de turnos de HOMI-D.

No sustituyen al E2E real: cubren el contrato del estado conversacional.
"""

import pytest

from homi_t31_turns import (
    STATE_DELIVERED,
    STATE_INTERRUPTED,
    STATE_SYNTHESIZED,
    TurnAuthority,
    TurnAuthorityError,
)


@pytest.fixture
def authority():
    unit = TurnAuthority(max_conversations=8)
    unit.clear()
    return unit


def _conv(authority, cid="conv_t31_unit_test_01"):
    return authority.begin_turn(
        cid, "turn_1", household_id="hh-test", actor_id="actor-test"
    )


def test_partial_is_ui_only_and_never_opens_a_semantic_turn(authority):
    opened = _conv(authority)
    assert authority.partial_transcript(opened["conversation_id"], "turn_1", "hola") is True

    snapshot = authority.snapshot(opened["conversation_id"])
    assert snapshot["last_partial"] == "hola"
    assert snapshot["current"]["speech_state"] == "generated"
    # The partial text is not a final transcript: no tool/THINK seam is exposed.
    assert snapshot["current"]["turn_version"] == 1

    # A partial for an unknown turn cannot create a generation.
    unknown = authority.partial_transcript("conv_t31_unit_test_01", "turn_other", "ruido")
    assert unknown is False
    assert authority.snapshot("conv_t31_unit_test_01")["version"] == 1


def test_one_final_per_turn_and_empty_is_rejected(authority):
    opened = _conv(authority)
    cid = opened["conversation_id"]

    first = authority.final_transcript(cid, "turn_1", "¿Qué tareas tengo?")
    assert first["status"] == "accepted"
    assert first["generation_id"] == "gen_1"

    duplicate = authority.final_transcript(cid, "turn_1", "¿Qué tareas tengo?")
    assert duplicate["status"] == "duplicate"
    assert authority.snapshot(cid)["version"] == 1

    with pytest.raises(TurnAuthorityError) as exc:
        authority.final_transcript(cid, "turn_2", "   ")
    assert exc.value.code == "final_transcript_empty"


def test_interrupt_invalidates_generation_and_drops_late_audio(authority):
    opened = _conv(authority)
    cid, gen = opened["conversation_id"], opened["generation_id"]
    authority.final_transcript(cid, "turn_1", "Hola Homi")

    assert authority.interrupt(cid, gen) is True
    assert authority.generation_is_current(cid, gen) is False
    # Repeated/stale interrupts are no-ops.
    assert authority.interrupt(cid, gen) is False

    # A generation invalidated before synthesis must not become audio.
    assert authority.mark_synthesized(cid, gen, audio_id="va_late") is False
    authority.mark_delivered(cid, gen, delivered_s=0.2, interrupted=True)
    assert authority.speech_status(cid, gen) == STATE_INTERRUPTED
    assert authority.snapshot(cid)["current"]["speech_status"] == STATE_INTERRUPTED


def test_delivered_is_only_recorded_for_a_current_generation(authority):
    opened = _conv(authority)
    cid, gen = opened["conversation_id"], opened["generation_id"]
    authority.final_transcript(cid, "turn_1", "Hola")
    authority.attach_result(cid, gen, decision_kind="direct_response")
    assert authority.mark_synthesized(cid, gen, audio_id="va_ok", duration_s=2.5) is True
    assert authority.generation_is_current(cid, gen) is True

    authority.mark_delivered(cid, gen, delivered_s=2.5)
    assert authority.speech_status(cid, gen) == STATE_DELIVERED
    assert authority.snapshot(cid)["current"]["speech_state"] == STATE_DELIVERED


def test_continuity_keeps_conversation_and_context_across_turns(authority):
    first = _conv(authority)
    cid = first["conversation_id"]
    authority.final_transcript(cid, "turn_1", "Creame una tarea")
    authority.attach_result(
        cid,
        first["generation_id"],
        decision_kind="action_proposal",
        proposal={"tool_id": "planner.tasks.create", "status": "PROPOSED"},
    )
    authority.interrupt(cid, first["generation_id"])

    second = authority.begin_turn(cid, "turn_2", household_id="hh-test", actor_id="actor-test")
    assert second["conversation_id"] == cid
    assert second["turn_version"] == 2
    assert second["generation_id"] == "gen_2"
    assert authority.generation_is_current(cid, first["generation_id"]) is False

    snapshot = authority.snapshot(cid)
    assert snapshot["last_decision_kind"] == "action_proposal"
    assert snapshot["last_proposal"]["tool_id"] == "planner.tasks.create"


def test_http_path_can_finalize_without_explicit_begin(authority):
    cid = "conv_t31_unit_http"
    result = authority.final_transcript(
        cid,
        "turn_http_1",
        "Hola desde HTTP",
        household_id="hh-test",
        actor_id="actor-test",
    )
    assert result["status"] == "accepted"
    assert result["generation_id"] == "gen_1"
    assert authority.snapshot(cid)["current_turn_id"] == "turn_http_1"


def test_input_validation_fail_closed(authority):
    with pytest.raises(TurnAuthorityError) as exc:
        authority.begin_turn("bad", "turn_1")
    assert exc.value.code == "conversation_id_invalido"

    with pytest.raises(TurnAuthorityError) as exc:
        authority.begin_turn("conv_t31_unit_test_02", "!!")
    assert exc.value.code == "turn_id_invalido"


def test_conversations_are_bounded(authority):
    for index in range(12):
        authority.begin_turn(f"conv_t31_bound_{index:02d}", f"turn_{index}")
    assert authority.snapshot("conv_t31_bound_00")["exists"] is False
    assert authority.snapshot("conv_t31_bound_11")["exists"] is True
