"""T30 — deterministic THINK fixture (evaluation-only, local).

HOMI-A is temporarily disconnected. This module provides an isolated,
deterministic substitute for the Node A decision seam so that the media
pipeline (mic -> LiveKit -> STT -> D -> SPEAK -> speaker) can be exercised
end-to-end without a real THINK.

Safety
------
* Disabled by default. Enabled only when ``HOMI_T30_THINK_FIXTURE=1``.
* Never executes a planner write. Never converts a mock into a real tool
  result. Returns a direct text response only.
* Must not be enabled in production.
"""

from __future__ import annotations

import os
from typing import Any


def is_enabled() -> bool:
    return os.getenv("HOMI_T30_THINK_FIXTURE", "").strip() == "1"


def fixture_response(text: str) -> dict[str, Any]:
    """Return a deterministic direct-response payload for the given transcript."""
    return {
        "decision": "DIRECT_RESPONSE",
        "reply_text": f"Respuesta de prueba T30 para: {text}",
        "tool_calls": [],
        "fixture": "t30-think-fixture",
    }
