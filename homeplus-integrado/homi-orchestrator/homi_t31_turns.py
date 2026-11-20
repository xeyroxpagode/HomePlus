"""T31 - Autoridad de turnos de HOMI-D.

Estado conversacional autoritativo y process-local. HOMI-D es el UNICO dueño
del turno semantico: los eventos de VAD de HOMI-C solo informan actividad y
nunca escriben en HomePlus ni ejecutan herramientas.

Contrato:
    * un texto PARCIAL es solo informacion de interfaz;
    * un texto FINAL habilita exactamente UN turno (por turn_id);
    * cada respuesta pertenece a un generation_id monotonico por conversacion;
    * interrumpir invalida una generacion, sin tocar herramientas ni propuestas;
    * el audio de una generacion invalidada nunca se sintetiza ni se publica.

La deduplicacion de tools/ledger existente NO se modifica: este modulo solo
gobierna el ciclo de vida del turno hablado.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

MAX_CONVERSATIONS = int(os.getenv("HOMI_T31_MAX_CONVERSATIONS", "64"))
CONVERSATION_ID_RE = re.compile(r"^conv_[A-Za-z0-9_-]{8,64}$")
TURN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,96}$")

STATE_GENERATED = "generated"
STATE_SYNTHESIZED = "synthesized"
STATE_DELIVERED = "delivered"
STATE_INTERRUPTED = "interrupted"


class TurnAuthorityError(ValueError):
    """Error de contrato del turno (id invalidado, duplicado, vacio)."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass
class Generation:
    generation_id: str
    turn_id: str
    version: int
    final_text: Optional[str] = None
    partial_text: Optional[str] = None
    state: str = STATE_GENERATED
    valid: bool = True
    audio_id: Optional[str] = None
    duration_s: Optional[float] = None
    delivered_s: float = 0.0
    created_at: float = field(default_factory=time.time)
    interrupted_at: Optional[float] = None
    last_decision_kind: Optional[str] = None
    last_proposal: Optional[dict] = None


@dataclass
class ConversationState:
    conversation_id: str
    household_id: str
    actor_id: str
    version: int = 0
    current_turn_id: Optional[str] = None
    current_generation_id: Optional[str] = None
    last_partial: Optional[str] = None
    generations: dict[str, Generation] = field(default_factory=dict)
    last_decision_kind: Optional[str] = None
    last_proposal: Optional[dict] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TurnAuthority:
    """Registro autoritativo de turnos, con una sola instancia por proceso."""

    def __init__(self, max_conversations: int | None = None) -> None:
        self._max = max_conversations or MAX_CONVERSATIONS
        self._lock = threading.RLock()
        self._conversations: dict[str, ConversationState] = {}

    # ------------------------------------------------------------------ #
    # Helpers internos (siempre bajo self._lock)
    # ------------------------------------------------------------------ #
    def _validate(self, conversation_id: str, turn_id: str | None = None) -> None:
        if not isinstance(conversation_id, str) or not CONVERSATION_ID_RE.match(conversation_id):
            raise TurnAuthorityError("conversation_id_invalido")
        if turn_id is not None and (
            not isinstance(turn_id, str) or not TURN_ID_RE.match(turn_id)
        ):
            raise TurnAuthorityError("turn_id_invalido")

    def _get_or_create(
        self,
        conversation_id: str,
        household_id: str,
        actor_id: str,
    ) -> ConversationState:
        state = self._conversations.get(conversation_id)
        if state is None:
            if len(self._conversations) >= self._max:
                oldest = min(
                    self._conversations.values(), key=lambda item: item.updated_at
                )
                self._conversations.pop(oldest.conversation_id, None)
            state = ConversationState(
                conversation_id=conversation_id,
                household_id=household_id or "",
                actor_id=actor_id or "",
            )
            self._conversations[conversation_id] = state
        return state

    def _generation(
        self, conversation_id: str, generation_id: str | None
    ) -> tuple[ConversationState, Generation]:
        state = self._conversations.get(conversation_id)
        if state is None or not generation_id:
            raise TurnAuthorityError("generation_not_found")
        generation = state.generations.get(generation_id)
        if generation is None:
            raise TurnAuthorityError("generation_not_found")
        return state, generation

    # ------------------------------------------------------------------ #
    # API publica
    # ------------------------------------------------------------------ #
    def begin_turn(
        self,
        conversation_id: str,
        turn_id: str,
        *,
        household_id: str = "",
        actor_id: str = "",
    ) -> dict:
        """Abre un turno. Idempotente para el mismo turn_id vigente."""
        self._validate(conversation_id, turn_id)
        with self._lock:
            state = self._get_or_create(conversation_id, household_id, actor_id)
            if state.current_turn_id == turn_id and state.current_generation_id:
                generation = state.generations[state.current_generation_id]
                return self._generation_view(state, generation, status="existing")

            state.version += 1
            state.updated_at = time.time()
            state.current_turn_id = turn_id
            state.last_partial = None
            generation_id = f"gen_{state.version}"
            generation = Generation(
                generation_id=generation_id,
                turn_id=turn_id,
                version=state.version,
            )
            state.generations[generation_id] = generation
            state.current_generation_id = generation_id
            # Bounded: only the last 16 generations are kept for introspection.
            while len(state.generations) > 16:
                oldest_id = min(
                    state.generations,
                    key=lambda key: state.generations[key].created_at,
                )
                state.generations.pop(oldest_id, None)
            return self._generation_view(state, generation, status="created")

    def partial_transcript(
        self,
        conversation_id: str,
        turn_id: str,
        text: str,
    ) -> bool:
        """Registra texto PROVISIONAL. Nunca habilita un turno semantico."""
        self._validate(conversation_id, turn_id)
        if not isinstance(text, str) or not text.strip():
            return False
        with self._lock:
            state = self._conversations.get(conversation_id)
            if state is None or state.current_turn_id != turn_id:
                return False
            state.last_partial = text.strip()
            generation_id = state.current_generation_id
            if generation_id and generation_id in state.generations:
                state.generations[generation_id].partial_text = text.strip()
            return True

    def final_transcript(
        self,
        conversation_id: str,
        turn_id: str,
        text: str,
        *,
        household_id: str = "",
        actor_id: str = "",
    ) -> dict:
        """Cierra la frase. Un solo final por turn_id habilita un turno."""
        self._validate(conversation_id, turn_id)
        clean = text.strip() if isinstance(text, str) else ""
        if not clean:
            raise TurnAuthorityError("final_transcript_empty")

        with self._lock:
            # El canal HTTP puede no llamar a begin_turn: lo hacemos aqui.
            state = self._conversations.get(conversation_id)
            if state is None or state.current_turn_id != turn_id:
                opened = self.begin_turn(
                    conversation_id,
                    turn_id,
                    household_id=household_id,
                    actor_id=actor_id,
                )
                generation_id = opened["generation_id"]
                # begin_turn may have created the conversation: refresh views.
                state = self._conversations[conversation_id]
            else:
                generation_id = state.current_generation_id
            generation = state.generations[generation_id]

            if generation.final_text is not None:
                return self._generation_view(state, generation, status="duplicate")
            if not generation.valid:
                return self._generation_view(state, generation, status="stale")

            generation.final_text = clean
            generation.partial_text = None
            generation.state = STATE_GENERATED
            state.updated_at = time.time()
            return self._generation_view(state, generation, status="accepted")

    def attach_result(
        self,
        conversation_id: str,
        generation_id: str,
        *,
        decision_kind: str | None = None,
        proposal: dict | None = None,
    ) -> bool:
        """Guarda contexto del resultado para continuidad. No ejecuta nada."""
        with self._lock:
            state, generation = self._generation(conversation_id, generation_id)
            if decision_kind is not None:
                generation.last_decision_kind = decision_kind
                state.last_decision_kind = decision_kind
            if proposal is not None:
                generation.last_proposal = proposal
                state.last_proposal = proposal
            state.updated_at = time.time()
            return True

    def mark_synthesized(
        self,
        conversation_id: str,
        generation_id: str,
        *,
        audio_id: str | None = None,
        duration_s: float | None = None,
    ) -> bool:
        """Solo una generacion vigente puede convertirse en audio entregable."""
        with self._lock:
            state, generation = self._generation(conversation_id, generation_id)
            if generation_id != state.current_generation_id or not generation.valid:
                return False
            generation.audio_id = audio_id
            generation.duration_s = duration_s
            generation.state = STATE_SYNTHESIZED
            state.updated_at = time.time()
            return True

    def generation_is_current(
        self, conversation_id: str, generation_id: str | None
    ) -> bool:
        if not generation_id:
            return False
        with self._lock:
            state = self._conversations.get(conversation_id)
            if state is None:
                return False
            generation = state.generations.get(generation_id)
            return bool(
                generation
                and generation.valid
                and state.current_generation_id == generation_id
            )

    def interrupt(self, conversation_id: str, generation_id: str) -> bool:
        """Invalida una generacion. No toca tools, ledger ni propuestas."""
        with self._lock:
            state, generation = self._generation(conversation_id, generation_id)
            if not generation.valid or generation_id != state.current_generation_id:
                return False
            generation.valid = False
            generation.state = STATE_INTERRUPTED
            generation.interrupted_at = time.time()
            state.updated_at = time.time()
            return True

    def mark_delivered(
        self,
        conversation_id: str,
        generation_id: str,
        *,
        delivered_s: float = 0.0,
        duration_s: float | None = None,
        interrupted: bool = False,
    ) -> bool:
        """Registra generated vs delivered. Interrumpida NUNCA es delivered."""
        with self._lock:
            state, generation = self._generation(conversation_id, generation_id)
            try:
                delivered = max(0.0, float(delivered_s))
            except (TypeError, ValueError):
                delivered = 0.0
            generation.delivered_s = delivered
            if duration_s is not None:
                try:
                    generation.duration_s = max(0.0, float(duration_s))
                except (TypeError, ValueError):
                    pass
            if interrupted or not generation.valid:
                generation.state = STATE_INTERRUPTED
            else:
                generation.state = STATE_DELIVERED
            state.updated_at = time.time()
            return True

    def speech_status(
        self, conversation_id: str, generation_id: str
    ) -> str:
        _, generation = self._generation(conversation_id, generation_id)
        return generation.state

    def snapshot(self, conversation_id: str) -> dict:
        with self._lock:
            state = self._conversations.get(conversation_id)
            if state is None:
                return {"conversation_id": conversation_id, "exists": False}
            current = None
            if state.current_generation_id:
                current = self._generation_view(
                    state, state.generations[state.current_generation_id], status="current"
                )
            return {
                "conversation_id": conversation_id,
                "exists": True,
                "version": state.version,
                "current_turn_id": state.current_turn_id,
                "current_generation_id": state.current_generation_id,
                "last_partial": state.last_partial,
                "last_decision_kind": state.last_decision_kind,
                "last_proposal": state.last_proposal,
                "current": current,
            }

    def clear(self) -> None:
        with self._lock:
            self._conversations.clear()

    # ------------------------------------------------------------------ #
    def _generation_view(
        self, state: ConversationState, generation: Generation, *, status: str
    ) -> dict:
        return {
            "status": status,
            "conversation_id": state.conversation_id,
            "turn_id": generation.turn_id,
            "generation_id": generation.generation_id,
            "turn_version": generation.version,
            "speech_state": generation.state,
            "speech_status": (
                STATE_INTERRUPTED
                if not generation.valid
                else generation.state
            ),
        }


_AUTHORITY: TurnAuthority | None = None
_AUTHORITY_LOCK = threading.Lock()


def get_turn_authority() -> TurnAuthority:
    """Singleton de proceso, equivalente a los demas stores de HOMI-D."""
    global _AUTHORITY
    with _AUTHORITY_LOCK:
        if _AUTHORITY is None:
            _AUTHORITY = TurnAuthority()
        return _AUTHORITY
