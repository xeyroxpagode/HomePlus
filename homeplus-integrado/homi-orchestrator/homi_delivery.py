"""HOMI T27 — Delivery Planner.

Deterministic, structured selection of how a semantic response should be
expressed orally. Does NOT modify the semantic text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping
from pydantic import BaseModel, Field, ConfigDict

POLICY_VERSION = "delivery-policy-1.0"
CONTRACT_VERSION = "delivery-plan-1.0"

Intent = Literal["neutral", "confirmation", "question", "warning"]
Urgency = Literal["low", "normal", "high"]
Energy = Literal["low", "medium", "high"]
Pace = Literal["slow", "normal", "brisk"]
Profile = Literal["neutral", "confirmation", "question", "warning"]

ReasonCode = Literal[
    "DEFAULT_NEUTRAL",
    "VERIFIED_SUCCESS",
    "CLARIFICATION_REQUIRED",
    "CONFIRMATION_PENDING",
    "OPERATION_DENIED",
    "OPERATION_FAILED",
    "PARTIAL_FAILURE",
    "VERIFIED_WARNING",
]


class DeliveryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_VERSION
    policy_version: str = POLICY_VERSION
    intent: Intent
    urgency: Urgency
    energy: Energy
    pace: Pace
    locale: str = "es-AR"
    profile: Profile
    reason_code: ReasonCode
    requested_profile: Profile | None = None
    applied_profile: Profile | None = None
    fallback_reason: str | None = None
    missing_capability: str | None = None


@dataclass(frozen=True)
class DeliverySignals:
    # operational truth
    verified_success: bool = False
    clarification_required: bool = False
    confirmation_pending: bool = False
    operation_failed: bool = False
    operation_denied: bool = False
    partial_failure: bool = False
    typed_warning: bool = False
    # decision kind hint
    decision_kind: str | None = None


# Matrix frozen V1
_MATRIX: dict[str, tuple[Intent, Urgency, Energy, Pace, ReasonCode]] = {
    "partial_failure": ("warning", "high", "low", "slow", "PARTIAL_FAILURE"),
    "operation_failed": ("warning", "high", "low", "slow", "OPERATION_FAILED"),
    "operation_denied": ("warning", "normal", "low", "normal", "OPERATION_DENIED"),
    "typed_warning": ("warning", "high", "low", "slow", "VERIFIED_WARNING"),
    "confirmation_pending": ("question", "normal", "medium", "slow", "CONFIRMATION_PENDING"),
    "clarification_required": ("question", "normal", "medium", "normal", "CLARIFICATION_REQUIRED"),
    "verified_success": ("confirmation", "low", "medium", "normal", "VERIFIED_SUCCESS"),
}


def select_delivery_plan(signals: DeliverySignals | Mapping[str, Any] | None = None, **kwargs: Any) -> DeliveryPlan:
    if signals is None:
        signals = DeliverySignals()
    if isinstance(signals, Mapping):
        # allow construction from dict
        s = DeliverySignals(**{k: v for k, v in signals.items() if k in DeliverySignals.__dataclass_fields__})
        # merge kwargs
        for k, v in kwargs.items():
            if k in DeliverySignals.__dataclass_fields__:
                setattr(s, k, v)
        signals = s
    elif kwargs:
        # update dataclass (frozen? it is frozen) -> rebuild
        base = {f: getattr(signals, f) for f in DeliverySignals.__dataclass_fields__}
        base.update({k: v for k, v in kwargs.items() if k in base})
        signals = DeliverySignals(**base)

    # precedence
    if signals.partial_failure:
        key = "partial_failure"
    elif signals.operation_failed:
        key = "operation_failed"
    elif signals.operation_denied:
        key = "operation_denied"
    elif signals.typed_warning:
        key = "typed_warning"
    elif signals.confirmation_pending:
        key = "confirmation_pending"
    elif signals.clarification_required:
        key = "clarification_required"
    elif signals.verified_success:
        key = "verified_success"
    else:
        # decision kind hints
        dk = (signals.decision_kind or "").lower()
        if dk == "clarify":
            key = "clarification_required"
        else:
            key = None

    if key is None:
        intent: Intent = "neutral"
        urgency: Urgency = "normal"
        energy: Energy = "medium"
        pace: Pace = "normal"
        reason: ReasonCode = "DEFAULT_NEUTRAL"
    else:
        intent, urgency, energy, pace, reason = _MATRIX[key]

    profile: Profile = intent  # logical profile coincides with intent

    return DeliveryPlan(
        intent=intent,
        urgency=urgency,
        energy=energy,
        pace=pace,
        profile=profile,
        reason_code=reason,
        requested_profile=profile,
        applied_profile=profile,
    )


def tts_map(plan: DeliveryPlan, capabilities: set[str] | None = None) -> dict[str, Any]:
    """Map DeliveryPlan to TTS adapter output using real capabilities.

    capabilities: set of supported logical profiles by provider.
    """
    caps = capabilities or set()
    requested = plan.profile
    if caps and requested not in caps:
        applied = "neutral" if "neutral" in caps else (sorted(caps)[0] if caps else "neutral")
        fallback_reason = "profile_not_supported"
        missing = requested
    elif not caps:
        # provider exposes no profiles -> neutral fallback
        applied = "neutral"
        fallback_reason = "no_profiles"
        missing = requested
    else:
        applied = requested
        fallback_reason = None
        missing = None

    # if provider completely down handled by caller (no caps maybe)
    return {
        "logical_profile": plan.profile,
        "applied_profile": applied,
        "fallback_reason": fallback_reason,
        "missing_capability": missing,
        "request": {"profile": applied, "locale": plan.locale},
    }


def extract_signals_from_envelope(envelope: Any, tool_result: Any = None, decision_kind: str | None = None) -> DeliverySignals:
    """Best-effort structured signal extraction from a response envelope."""
    result = {}
    if hasattr(envelope, "result") and isinstance(envelope.result, dict):
        result = envelope.result
    dk = result.get("decision_kind")
    if decision_kind is not None:
        dk = decision_kind
    # verified success: tool turns that completed & verified
    verified = False
    failed = False
    partial = False
    denied = False
    clarification = dk == "clarify"
    confirmation_pending = False
    typed_warning = False

    # tool result status
    tr = tool_result
    if tr is not None:
        ok = getattr(tr, "ok", None)
        if ok is False:
            failed = True
        if ok is True:
            # check verification
            verified = True

    # result-level hints
    if isinstance(result, dict):
        status = result.get("status") or result.get("verification_status")
        if status in ("FAILED", "ERROR", "failed", "error"):
            failed = True
        if status in ("PARTIAL", "partial"):
            partial = True
        if result.get("grounded") is False and dk == "tool_request":
            # not necessarily failure; keep neutral-ish but not success
            verified = False
        # confirmation pending hint
        proposal_status = result.get("proposal_status") or (result.get("proposal") or {}).get("status") if isinstance(result.get("proposal"), dict) else None
        if proposal_status in ("proposed", "PROPOSED", "pending"):
            confirmation_pending = True
        # typed warnings
        if result.get("warnings") or result.get("error"):
            # only treat as warning if error present
            if result.get("error"):
                typed_warning = True

    # denied detection via error code? envelope is success here, so no.

    # clarification via question field
    if result.get("question"):
        clarification = True

    # verified success only if direct answer present and no tool failure
    if dk in (None, "direct_response") and not failed and not clarification:
        # ordinary info unless tool verified
        if not (tool_result is not None):
            verified = False

    # If a tool was executed and verified
    if tool_result is not None and getattr(tool_result, "ok", False):
        # check verification record if available
        vr = None
        try:
            vr = getattr(tool_result, "verification", None)
        except Exception:
            vr = None
        if vr is None:
            verified = True
        else:
            verified = bool(vr)

    if failed:
        verified = False

    return DeliverySignals(
        verified_success=verified and not clarification and not confirmation_pending,
        clarification_required=clarification,
        confirmation_pending=confirmation_pending,
        operation_failed=failed,
        operation_denied=denied,
        partial_failure=partial,
        typed_warning=typed_warning,
        decision_kind=dk,
    )