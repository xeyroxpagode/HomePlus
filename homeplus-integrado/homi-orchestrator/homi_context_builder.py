"""HOMI T13 — Context Builder (Actor, Household, Session, Temporal, Surface).

This module adds an additive, per-turn context preparation layer on top of
the existing HOMI-D orchestration. It does NOT replace authentication,
authorization, session management, proposals or the tool layer. It builds a
trusted internal ContextEnvelope and a minimal safe projection for THINK.

Design notes
------------
* The envelope is a per-turn snapshot (dict-based, immutable-ish).
* All identity fields are sourced from the authenticated request context;
  never from message text, model output or unvalidated client metadata.
* Timezone resolution follows the documented precedence:
  1. validated user preference (if present in payload metadata)
  2. household-configured zone (if present)
  3. application default (HOMI_DEFAULT_TIMEZONE env, else UTC)
  4. explicit uncertainty when none is trustworthy.
* Surface is validated against a known set; unknown -> "unknown".
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Known application surfaces (extend via env/config if needed).
KNOWN_SURFACES = frozenset({
    "home",
    "planner",
    "calendar",
    "family",
    "finances",
    "homecloud",
})

# IANA zone validation helper.
_IANA_RE = re.compile(
    r"^(?:UTC|Etc/UTC|"
    r"(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific)"
    r"/[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)?)$"
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_valid_iana(tz: Any) -> bool:
    if not isinstance(tz, str) or not tz.strip():
        return False
    tz = tz.strip()
    if not _IANA_RE.match(tz):
        return False
    # UTC is always valid
    if tz == "UTC":
        return True
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError, ModuleNotFoundError):
        # tzdata may be unavailable; accept well-formed IANA names
        return True
    return True


@dataclass
class ContextEnvelope:
    context_version: str = "1.0"
    request_id: str | None = None
    received_at_utc: str | None = None
    actor: dict[str, Any] = field(default_factory=dict)
    household: dict[str, Any] = field(default_factory=dict)
    session: dict[str, Any] = field(default_factory=dict)
    temporal: dict[str, Any] = field(default_factory=dict)
    surface: dict[str, Any] = field(default_factory=dict)
    pending_proposal: dict[str, Any] = field(default_factory=dict)
    see_results: list[dict[str, Any]] = field(default_factory=list)
    completeness: str = "complete"
    warnings: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_version": self.context_version,
            "request": {
                "request_id": self.request_id,
                "received_at_utc": self.received_at_utc,
            },
            "actor": self.actor,
            "household": self.household,
            "session": self.session,
            "temporal": self.temporal,
            "surface": self.surface,
            "pending_proposal": self.pending_proposal,
            "completeness": self.completeness,
            "warnings": list(self.warnings),
            "sources": dict(self.sources),
        }


def resolve_timezone(
    *,
    user_tz: Any = None,
    household_tz: Any = None,
    app_default: str | None = None,
) -> tuple[str | None, str, str]:
    """Return (tz_name_or_None, source, status).

    status in {"resolved", "uncertain"}.
    """
    # 1. validated user preference
    if _is_valid_iana(user_tz):
        return user_tz.strip(), "user_preference", "resolved"
    # 2. household configured
    if _is_valid_iana(household_tz):
        return household_tz.strip(), "household_config", "resolved"
    # 3. app default
    default = app_default or os.getenv("HOMI_DEFAULT_TIMEZONE", "UTC")
    if _is_valid_iana(default):
        if default == "UTC":
            return default, "app_default", "resolved"
        return default, "app_default", "resolved"
    # 4. uncertain
    return None, "none", "uncertain"


def validate_surface(value: Any) -> tuple[str | None, str]:
    """Return (surface_or_None, status)."""
    if value is None:
        return None, "unknown"
    if not isinstance(value, str):
        return None, "unknown"
    v = value.strip().lower()
    if v in KNOWN_SURFACES:
        return v, "valid"
    return None, "unknown"


def build_context(
    request: Any,
    *,
    client_metadata: Mapping[str, Any] | None = None,
    household_timezone: Any = None,
    user_timezone: Any = None,
) -> ContextEnvelope:
    """Build the per-turn ContextEnvelope.

    `request` is expected to be a RequestEnvelope-like object with a `.context`
    attribute exposing request_id, actor_id, household_id, conversation_id,
    turn_id, timestamp.
    """
    ctx = getattr(request, "context", None)
    env = ContextEnvelope()

    # request
    rid = getattr(ctx, "request_id", None) if ctx is not None else None
    env.request_id = str(rid) if rid is not None else None
    received = _utc_now()
    env.received_at_utc = received.isoformat()

    # actor
    actor_id = getattr(ctx, "actor_id", None) if ctx is not None else None
    env.actor = {
        "id": str(actor_id) if actor_id is not None else None,
        "status": "VALID" if actor_id is not None else "INVALID",
    }

    # household
    household_id = getattr(ctx, "household_id", None) if ctx is not None else None
    env.household = {
        "id": str(household_id) if household_id is not None else None,
        "status": "VALID" if household_id is not None else "MISSING",
    }

    # session
    conversation_id = getattr(ctx, "conversation_id", None) if ctx is not None else None
    turn_id = getattr(ctx, "turn_id", None) if ctx is not None else None
    env.session = {
        "id": str(conversation_id) if conversation_id is not None else None,
        "turn_id": str(turn_id) if turn_id is not None else None,
        "status": "VALID" if conversation_id is not None else "INVALID",
    }

    # temporal
    meta = dict(client_metadata or {})
    payload = getattr(request, "payload", None)
    if isinstance(payload, Mapping):
        if "client_metadata" in payload and isinstance(payload["client_metadata"], Mapping):
            meta.update(payload["client_metadata"])
        if "metadata" in payload and isinstance(payload["metadata"], Mapping):
            meta.update(payload["metadata"])
        # timezone hints from payload
        if user_timezone is None:
            user_timezone = payload.get("timezone") or payload.get("tz") or payload.get("user_timezone")
        if household_timezone is None:
            household_timezone = payload.get("household_timezone")
        # surface hints from payload
        surface_hint = payload.get("surface") or payload.get("surface_kind") or payload.get("view")
        # See results estructurados orquestados por HOMI-D (T23)
        see_results_payload = payload.get("_see_results")
        if isinstance(see_results_payload, list):
            env.see_results = [dict(item) for item in see_results_payload]
        elif see_results_payload is not None:
            env.see_results = [dict(see_results_payload)]
    else:
        surface_hint = None

    # also from metadata
    if user_timezone is None:
        user_timezone = meta.get("timezone") or meta.get("tz") or meta.get("user_timezone")
    if household_timezone is None:
        household_timezone = meta.get("household_timezone")
    if surface_hint is None:
        surface_hint = meta.get("surface") or meta.get("surface_kind") or meta.get("view")

    # override with explicit args (validated preferences)
    if user_timezone is None and isinstance(user_timezone, str) is False:
        pass

    # Actually apply explicit overrides if provided
    # (already handled by params)

    tz_name, tz_source, tz_status = resolve_timezone(
        user_tz=user_timezone,
        household_tz=household_timezone or household_timezone,
        app_default=os.getenv("HOMI_DEFAULT_TIMEZONE"),
    )
    # if household_timezone param provided, prefer it over env? already

    ref_time = None
    if ctx is not None and getattr(ctx, "timestamp", None) is not None:
        ref_time = ctx.timestamp
    if not isinstance(ref_time, datetime):
        ref_time = received
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)

    if tz_name:
        try:
            zi = ZoneInfo(tz_name)
            local = ref_time.astimezone(zi)
            local_date = local.date().isoformat()
            local_time = local.timetz().replace(microsecond=0).isoformat()
        except Exception:
            # tzdata may be unavailable or zone unsupported: keep the
            # resolved name but derive date/time from the UTC reference.
            local_date = ref_time.date().isoformat()
            local_time = ref_time.timetz().replace(microsecond=0).isoformat()
    else:
        local_date = ref_time.date().isoformat()
        local_time = ref_time.timetz().replace(microsecond=0).isoformat()

    env.temporal = {
        "reference_time_utc": ref_time.isoformat(),
        "timezone": tz_name,
        "local_date": local_date,
        "local_time": local_time,
        "timezone_source": tz_source,
        "status": tz_status,
    }
    env.sources["temporal"] = tz_source

    # surface
    surf, surf_status = validate_surface(surface_hint)
    view = None
    if isinstance(surface_hint, str) and "/" in surface_hint:
        parts = surface_hint.split("/", 1)
        if parts[0].strip().lower() in KNOWN_SURFACES:
            surf = parts[0].strip().lower()
            view = parts[1].strip()
    # also allow metadata view
    if view is None:
        view = meta.get("view")
    env.surface = {
        "kind": surf,
        "view": view,
        "status": "VALID" if surf is not None else "UNKNOWN",
    }
    if surf_status == "unknown" and surface_hint is not None:
        env.warnings.append("unknown_surface")

    # pending proposal
    pending_info = {"available": False, "proposal_id": None, "operation": None, "status": "NONE"}
    try:
        from homi_tool_proposal import get_pending_proposal
        conv = conversation_id
        pending = get_pending_proposal(conv) if conv is not None else None
    except Exception:
        pending = None
    if pending is not None:
        pending_info = {
            "available": True,
            "proposal_id": getattr(pending, "proposal_id", None),
            "operation": getattr(pending, "operation", None) or getattr(pending, "tool_id", None),
            "status": getattr(pending, "status", None),
        }
    env.pending_proposal = pending_info

    # completeness
    warnings = []
    if env.actor.get("status") != "VALID":
        warnings.append("actor_invalid")
    if env.household.get("status") != "VALID":
        warnings.append("household_missing")
    if tz_status != "resolved":
        warnings.append("timezone_uncertain")
    env.warnings = warnings + env.warnings
    if warnings:
        env.completeness = "partial"
    else:
        env.completeness = "complete"

    env.sources["actor"] = "auth_context"
    env.sources["household"] = "auth_context"
    env.sources["session"] = "request_context"
    env.sources["surface"] = "client_metadata" if surface_hint is not None else "none"

    return env


def project_for_think(envelope: ContextEnvelope) -> dict[str, Any]:
    """Minimal safe projection for THINK. No secrets, no JWT, no full permissions."""
    out: dict[str, Any] = {}
    # temporal
    t = envelope.temporal or {}
    out["temporal"] = {
        "reference_time_utc": t.get("reference_time_utc"),
        "timezone": t.get("timezone"),
        "local_date": t.get("local_date"),
        "local_time": t.get("local_time"),
        "timezone_source": t.get("timezone_source"),
        "status": t.get("status"),
    }
    # surface
    s = envelope.surface or {}
    out["surface"] = {
        "kind": s.get("kind"),
        "view": s.get("view"),
        "status": s.get("status"),
    }
    # pending proposal minimal
    p = envelope.pending_proposal or {}
    out["pending_proposal"] = {
        "available": bool(p.get("available")),
        "operation": p.get("operation"),
        "status": p.get("status"),
    }
    # actor/household only as status, not ids? Include ids as they are not secrets but contextual. Keep minimal: ids are needed for context but THINK must not use as authority. Include.
    out["actor_status"] = (envelope.actor or {}).get("status")
    out["household_status"] = (envelope.household or {}).get("status")
    out["completeness"] = envelope.completeness
    if envelope.warnings:
        out["warnings"] = list(envelope.warnings)
    # See results estructurados (T23): contexto consumible por THINK.
    # Nunca se envían archivos binarios, solo el resultado normalizado de SEE.
    if envelope.see_results:
        out["see_results"] = list(envelope.see_results)
    return out


def build_context_projection(request: Any, **kwargs: Any) -> dict[str, Any]:
    env = build_context(request, **kwargs)
    return project_for_think(env)
