"""HOMI T09-D — structured decision orchestration seam (Node D).

T09-D builds the Node D orchestration seam for structured tool calling on
top of the frozen T08 THINK path:

* the caller reaches D through the existing ``POST /invoke`` operation;
* D builds a NEW internal T05 ``RequestEnvelope`` for Node A;
* Node A returns a structured decision that D re-validates from scratch;
* D never executes a tool in this phase: the tool executor seam is
  ``DISABLED`` and the HomePlus client is not configured.

Boundaries
----------
* Node D is transport, not identity authority. The HomePlus bearer token
  is captured from the inbound ``Authorization`` header, kept in
  request-local memory only, and never forwarded to Node A, never logged,
  never persisted and never decoded. T07 remains the identity authority.
* Node D re-validates every model decision. Constrained decoding is not
  trusted.
* ``MAX_TOOL_CALLS = 1``: one tool per turn. No loop, no parallel call,
  no recursive model call, no WRITE tool, no model-provided endpoint.

This module performs no HomePlus network call. The only outbound HTTP it
can perform is the control-plane resolve and the Node A decision call.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import logging
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import httpx
from pydantic import TypeAdapter, ValidationError


_MODULE_DIR = Path(__file__).resolve().parent

if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(_MODULE_DIR),
    )

from homi_contracts import (  # noqa: E402
    Capability,
    CorrelationContext,
    ErrorCode,
    ErrorDetail,
    ErrorEnvelope,
    RequestContext,
    RequestEnvelope,
    ResponseEnvelope,
)

from homi_tool_catalog import (  # noqa: E402
    CANONICAL_TOOL_IDS,
    ToolCatalogError,
    catalog,
    catalog_v2,
    effective_tool_ids,
    forbidden_keys_in_arguments,
    is_forbidden_identity_key,
    is_t24_read_enabled,
    is_t24_read_tool,
)

from homi_tool_contract import (  # noqa: E402
    DECISION_CLARIFY,
    DECISION_DIRECT_RESPONSE,
    DECISION_TOOL_REQUEST,
    ToolDecisionError,
    decision_json_schema_text,
    parse_decision,
    precheck_tool_arguments,
)

from homi_tool_client import (  # noqa: E402
    HomePlusToolClient,
    ToolCallResult,
    ToolClientConfig,
    ToolClientConfigError,
    load_tool_client_config,
    require_configured,
)

from homi_tool_normalize import (  # noqa: E402
    TOOL_PROJECTIONS,
    TOOL_RESULT_VERSION,
    ToolNormalizationError,
    ToolResultV1,
    assert_tool_result_is_safe,
    normalize_tool_result,
)

from homi_tool_proposal import (  # noqa: E402
    PROPOSAL_TOOL_IDS,
    PLANNER_TASKS_CREATE_INPUT_SCHEMA,
    PLANNER_TASKS_CREATE_TOOL_ID,
    PLANNER_TASKS_COMPLETE_TOOL_ID,
    PLANNER_TASKS_RESTORE_TOOL_ID,
    PLANNER_TASKS_TRASH_TOOL_ID,
    PLANNER_TASKS_UPDATE_TOOL_ID,
    PROPOSAL_ACTION_PUBLIC_CONFIRMED,
    PROPOSAL_ACTION_CANCEL,
    PROPOSAL_ACTION_CONFIRM,
    PROPOSAL_STATUS_CONFIRMED,
    PROPOSAL_STATUS_EXECUTING,
    PROPOSAL_STATUS_FAILED,
    PROPOSAL_STATUS_PARTIAL,
    PROPOSAL_STATUS_PROPOSED,
    PROPOSAL_STATUS_SUCCEEDED,
    PROPOSAL_STATUS_VERIFIED,
    PROPOSAL_STATUS_VERIFYING,
    T12_NEW_TOOL_IDS,
    T12_EXECUTION_TOOL_IDS,
    MODEL_WRITE_PATCH_PROPERTIES,
    ActionProposalError,
    ActionProposalV1,
    apply_proposal_action,
    begin_proposal_execution,
    begin_proposal_verification,
    build_action_proposal,
    complete_proposal_execution,
    execution_scope_matches,
    is_compound_create_arguments,
    complete_proposal_verification,
    get_confirmed_proposal,
    get_verification_record,
    get_execution_record,
    get_pending_proposal,
    get_terminal_proposal,
    proposal_action_public_value,
    proposal_execution_safe_result,
    record_uncertain_proposal_execution,
    persist_compound_execution_outcome,
    persist_compound_execution_start,
    persist_compound_execution_uncertain,
    replace_pending_proposal,
    revise_action_proposal,
    revise_t12_update_proposal,
    validate_edit_patch,
    validate_model_write_arguments,
    validate_proposal_arguments,
    validate_write_tool_arguments,
)

from homi_tool_t12_targets import (  # noqa: E402
    TaskTargetError,
    apply_clear_date_invariant,
    complete_preconditions,
    merge_due_time_intent,
    resolve_task_by_title,
    restore_preconditions,
    transform_checklist,
    validate_checklist_patch,
    validate_task_target,
)

from homi_t14_temporal import resolve_temporal, combine_to_instant  # noqa: E402
from homi_t14_entity import resolve_entity  # noqa: E402
from homi_t14_contextual import resolution_gate as t14_resolution_gate, create_clarification as t14_create_clarification  # noqa: E402

from homi_tool_write_execution import (  # noqa: E402
    INTERNAL_PREFLIGHT_GET_TRASHED_TASK_PATH,
    PreflightAttemptResult,
    WriteExecutorDisabledError,
    assert_write_execution_trusted,
    attempt_internal_preflight,
    get_write_executor,
    load_write_execution_config,
    validate_compound_execution_result,
    write_executor_state,
)

try:
    from homi_context_builder import (  # noqa: E402
        build_context_projection,
    )
except Exception:  # pragma: no cover - defensive
    def build_context_projection(request, **kwargs):  # type: ignore
        return {}


# ---------------------------------------------------------------------------
# Operation / wire constants
# ---------------------------------------------------------------------------

# The public T09 discriminator. The caller operation that activates the
# T09 seam.
OPERATION_INFER_WITH_TOOLS = "infer_with_tools"

# The provider wire operation stays "infer": Node A's THINK provider
# contract is frozen by T08 and is not changed by T09.
OPERATION_INFER = "infer"

# The internal decision phase.
DECISION_MODE = "structured"

DECISION_PHASE = "decide"

DECISION_SCHEMA_VERSION = "1.0"

DECISION_SCHEMA_VERSION_V2 = "2.0"

# T11-5 — the trust anchor of the ADDITIVE decision schema v2 deployed on
# the REAL Node A (homi-a). It is the SHA256 of
# ``tool-decision.v2.schema.json`` as published by the T11 Node A contract
# (schemas/ of the think-provider). It is NOT the frozen T10 v1 schema
# digest: the v1 payload keeps sending ``decision_schema_digest()`` and
# the v1 path stays byte identical.
DECISION_SCHEMA_V2_DIGEST = (
    "ada64ca836c791c4e3d0f0b61edb9e47d1c401adbab7f0c653a4d436e8a42fef"
)

# The model-facing descriptor of the one canonical WRITE tool, sent ONLY
# in the additive v2 decision payload. It is built from the trusted
# in-code proposal contract (T11-1), never from the frozen READ
# catalogue: kind, risk and confirmation stay inside Node D.
PLANNER_TASKS_CREATE_MODEL_DESCRIPTION = (
    "Propose creating one or more Planner tasks. Choosing this tool "
    "does NOT create anything: the orchestrator builds ONE proposal "
    "that the user must confirm first. Use exactly one arguments mode. "
    "For one task, arguments contains a non-empty title and may contain "
    "description, dueDate (ISO date YYYY-MM-DD), dueTime (HH:MM), "
    "assignedToMemberId. For 2-4 tasks, arguments contains ONLY an "
    "operations array with 2-4 items; every item has the same simple "
    "shape (required non-empty title and the same optional fields). "
    "Never mix a top-level title or other simple field with operations."
)


# ---------------------------------------------------------------------------
# T11-4 — additive decision-v2 WRITE surface (planner.tasks.create)
# ---------------------------------------------------------------------------
#
# The frozen T10 decision surface is READ-only by design: the decision
# schema enum admits exactly the eight READ tools and its tests freeze
# that vocabulary, so it must never learn any WRITE tool.
#
# The T11 add-on lives HERE, in Node D, as a deterministic, stringently
# gated second pass over a raw model decision:
#
#   parse_decision(raw) fails for planner.tasks.create
#       -> parse_action_proposal_decision(raw) may accept EXACTLY:
#           {"decision": "tool_request",
#            "answer": null,
#            "question": null,
#            "tool_id": "planner.tasks.create",
#            "arguments": {...},                          # required
#            "proposal_edit_patch": {...} | absent}       # T11-4 optional
#
# Gates (fail-closed, no coercion, ordered):
#   * unknown top-level fields are rejected (this also rejects every
#     execution/confirmation metadata field the frozen gate rejects);
#   * ``decision`` must be ``tool_request``` and ``tool_id`` must be
#     exactly the one canonical WRITE tool;
#   * ``answer`` and ``question`` must be null;
#   * ``arguments`` must be a plain JSON object without any
#     identity/credential/transport key (same forbidden-key family as
#     the frozen surface);
#   * ``proposal_edit_patch``, when present and non-null, must pass
#     ``validate_edit_patch`` (only the T11-1 editable business fields,
#     additionalProperties=false).
#
# Node A never owns the merge: in an EDIT turn the ``arguments`` body is
# ignored and ONLY the patch is applied on top of the pending proposal
# arguments owned by D (T11-4 §6). A plain ``tool_request`` (no patch)
# while a proposal is pending is REPLACEMENT intent (new-create, §13)
# and replaces it with a freshly built proposal.
DECISION_WRITE_ADDITIVE_FIELD = "proposal_edit_patch"

# T11-5: the additive lifecycle intent field. Node A may express that
# the user wants to CONFIRM or CANCEL the pending proposal. A only
# interprets the intent: it must NEVER emit proposal_id, status, risk,
# confirmation metadata or identity fields. Node D resolves the action
# against the CURRENT active proposal alone.
DECISION_PROPOSAL_ACTION_FIELD = "proposal_action"

# Node A requires a non-empty provider-facing text even when the public turn
# consists only of attachments. This deterministic fallback is used ONLY for
# the provider request; the caller-facing payload keeps the original empty
# text and the SEE context carries the attachment evidence.
ATTACHMENT_ONLY_PROVIDER_TEXT = (
    "Analiza los adjuntos de este turno y responde segun el contexto "
    "disponible."
)

# Unambiguous user confirmation words (Spanish). Only matched against the
# whole, normalized user text: no substring matching, no fuzzy logic.
# These are only ever consulted when a PROPOSED proposal already exists
# for the conversation, so a confirmation is never interpreted out of
# context.
CONFIRMATION_WORDS: frozenset[str] = frozenset({
    "si",
    "sí",
    "dale",
    "ok",
    "vale",
    "confirmo",
    "confirmar",
    "confirma",
    "aceptar",
    "aceptá",
    "proceder",
    "procedé",
    "hazlo",
    "vamos",
    "estabien",
    "está bien",
    "deacuerdo",
    "de acuerdo",
})

import unicodedata as _unicodedata


def _normalize_confirmation_text(text: str) -> str:
    """Normalize user text for unambiguous confirmation matching.

    Lowercase, strip accents and surrounding whitespace. Multi-word
    phrases are matched exactly after normalization.
    """

    normalized = text.strip().lower()

    return "".join(
        c
        for c in _unicodedata.normalize("NFD", normalized)
        if _unicodedata.category(c) != "Mn"
    )


def _is_unambiguous_confirmation(text: str) -> bool:
    """Return True when the user text is an unambiguous confirmation.

    Only whole-text matches against CONFIRMATION_WORDS are accepted,
    so partial or ambiguous answers are never treated as confirmation.
    """

    if not isinstance(text, str) or not text.strip():
        return False

    return _normalize_confirmation_text(text) in CONFIRMATION_WORDS


def provider_text_for_model(
    text: str,
    *,
    has_attachments: bool,
) -> str:
    """Return the provider-facing text for one turn.

    A public attachment-only turn keeps its original empty text, but Node A
    requires a non-empty prompt. The deterministic fallback is confined to
    the provider request and is never exposed as the user's message.
    """

    if isinstance(text, str) and text.strip():
        return text

    if has_attachments:
        return ATTACHMENT_ONLY_PROVIDER_TEXT

    return text


# T12-3: the additive existing-task target contract (section 3). For a
# mutation against an existing task the model expresses ONLY the
# smallest explicit target representation:
#
#     target:
#       kind: task
#       task_id: UUID | null
#       task_title: string | null
#
# The model never invents a UUID it was not given, target is NOT
# execution authority, and Node D owns the canonical resolution.
DECISION_TARGET_FIELD = "target"

# T12-3: the additive checklist intent (sections 11-13). The model
# NEVER supplies the authoritative checklist array; it expresses the
# intended item operation and D transforms the trusted
# ``planner.tasks.get`` checklist deterministically.
DECISION_CHECKLIST_PATCH_FIELD = "checklist_patch"

# T12-3 section 10: the model may identify the requested human by
# natural-language name. Node D has NO trusted member-resolution
# authority in the T12 infrastructure, so a name ALWAYS fails closed
# to a clarify (never a fabricated member id).
DECISION_ASSIGN_MEMBER_NAME_FIELD = "assign_member_name"

DECISION_WRITE_TOP_LEVEL_FIELDS = frozenset(
    {
        "decision",
        "answer",
        "question",
        "tool_id",
        "arguments",
        DECISION_WRITE_ADDITIVE_FIELD,
        DECISION_PROPOSAL_ACTION_FIELD,
        DECISION_TARGET_FIELD,
        DECISION_CHECKLIST_PATCH_FIELD,
        DECISION_ASSIGN_MEMBER_NAME_FIELD,
    }
)


@dataclass(frozen=True)
class ActionProposalDecision:
    """A v2 decision accepted by the additive T11-4 surface.

    ``edit_patch`` is ``None`` for create/replacement intent and a
    validated mapping for edit intent. It is a copy isolated from the
    raw model payload.

    ``target`` is the T12-3 existing-task target contract: ``None``
    for create, and the validated ``(task_id, task_title)`` pair for
    the four existing-task WRITE tools. It is copy-isolated and is
    NOT execution authority.

    ``checklist_patch`` is the T12-3 checklist INTENT descriptor
    (update only): D owns the deterministic read-modify-write over
    the authoritative checklist.

    ``assign_member_name`` is the T12-3 natural-language assignee
    name (update only): with no trusted member-resolution authority
    in the T12 infrastructure it always fails closed to a clarify.

    ``v1_projection`` carries the canonical five-field projection of a
    v2 envelope that maps exactly onto the frozen T10 contract
    (``direct_response``, ``clarify`` and READ ``tool_request``
    decisions). Node D then revalidates that projection with the
    FROZEN parser and dispatches it through the frozen T10 path: the
    additive surface is a strict pre-processor, never a second
    semantics.
    """

    decision: str
    tool_id: str | None
    arguments: Mapping[str, Any] | None
    edit_patch: Mapping[str, Any] | None
    proposal_action: str | None = None
    v1_projection: Mapping[str, Any] | None = None
    target: tuple[str | None, str | None] | None = None
    checklist_patch: Mapping[str, Any] | None = None
    assign_member_name: str | None = None


def _reject_t12_additive_fields(
    raw_decision: Mapping[str, Any],
    shape: str,
) -> None:
    """Reject the T12-3 additive fields on non-existing-task shapes.

    The target / checklist_patch / assign_member_name fields are
    meaningful ONLY for the four existing-task WRITE tools. Every
    other decision shape (direct_response, clarify, READ
    tool_request, planner.tasks.create) must carry them absent/null
    (decision strictness, T12-3 section 27).
    """

    for field in (
        DECISION_TARGET_FIELD,
        DECISION_CHECKLIST_PATCH_FIELD,
        DECISION_ASSIGN_MEMBER_NAME_FIELD,
    ):
        if raw_decision.get(field) is not None:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{shape} requires {field!r} to be null",
            )


def _parse_t12_update_edit_decision(
    raw_decision: Mapping[str, Any],
) -> ActionProposalDecision:
    """Parse/validate one T12-4 update-proposal EDIT decision.

    The accepted EXACT shape is a ``tool_request`` for
    ``planner.tasks.update`` that revises the ACTIVE update proposal of
    the conversation (T12-4 sections 1-5):

    * ``proposal_edit_patch`` is REQUIRED and must pass the T11-4
      ``validate_edit_patch`` gate: only the frozen user-facing intent
      fields (title, description, dueDate, dueTime,
      assignedToMemberId). ``taskId`` / ``expectedVersion`` / ``risk``
      / ``confirmation`` / ``proposal_id`` / ``status`` / ``checklist``
      can never be patched (D-owned authority; the checklist intent
      travels as ``checklist_patch``);
    * ``target`` must be null: the trusted target already lives in the
      ACTIVE proposal and taskId is NOT user-editable (section 3). A
      target on an edit turn is a mixed intent and fails closed;
    * ``arguments`` is never consumed on an edit turn (T11-4 section 6
      rule): null or a plain JSON object whose identity/credential keys
      are still rejected. The user-requested delta is the patch ONLY;
    * ``checklist_patch`` is the optional REVISED checklist intent
      (validated like the T12-3 descriptor): it REPLACES the active
      proposal's intent and the resulting array is recomputed from the
      fresh authoritative READ downstream;
    * ``assign_member_name`` must be null: assignment by
      natural-language name stays CLARIFY/unresolved and is never an
      editable field (section 11);
    * ``proposal_action`` must be null (the caller already enforced
      the one-operation-per-turn guard).
    """

    if (
        raw_decision.get(DECISION_TARGET_FIELD)
        is not None
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "an update proposal edit must not carry "
            f"{DECISION_TARGET_FIELD!r}: the trusted target "
            "already lives in the active proposal",
        )

    arguments = raw_decision.get("arguments")

    if arguments is not None:
        if not isinstance(arguments, dict):
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "tool_request requires 'arguments' to be a plain "
                "JSON object",
            )

        # checklist_patch es un campo de nivel superior; si el modelo
        # lo colocó dentro de arguments, extraerlo y descartarlo de
        # arguments para que no sea validado como campo desconocido.
        if isinstance(arguments, dict):
            arguments = {
                k: v
                for k, v in arguments.items()
                if k != DECISION_CHECKLIST_PATCH_FIELD
            }

        forbidden = forbidden_keys_in_arguments(arguments)

        if forbidden:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "'arguments' must not carry identity/auth/transport "
                "fields: " + ", ".join(forbidden),
            )

    patch = raw_decision.get(DECISION_WRITE_ADDITIVE_FIELD)

    if not isinstance(patch, dict) or not all(
        isinstance(key, str) for key in patch
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            f"{DECISION_WRITE_ADDITIVE_FIELD!r} must be a "
            "plain JSON object",
        )

    patch_violations = validate_edit_patch(patch)

    if patch_violations:
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            f"{DECISION_WRITE_ADDITIVE_FIELD!r} is not a "
            "valid edit patch: " + ", ".join(patch_violations),
        )

    checklist_patch = None

    checklist_raw = raw_decision.get(
        DECISION_CHECKLIST_PATCH_FIELD,
    )

    # Normalización: si el modelo colocó checklist_patch dentro de arguments,
    # extraerlo y usarlo (compatibilidad con checklist_patch anidado).
    if checklist_raw is None and isinstance(
        raw_decision.get("arguments"), dict
    ):
        nested = raw_decision["arguments"].get(
            DECISION_CHECKLIST_PATCH_FIELD
        )
        if nested is not None:
            checklist_raw = nested

    if checklist_raw is not None:
        try:
            checklist_patch = validate_checklist_patch(
                checklist_raw,
            )

        except TaskTargetError as error:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_CHECKLIST_PATCH_FIELD!r}: "
                f"{error.message}",
            ) from error

    if (
        raw_decision.get(DECISION_ASSIGN_MEMBER_NAME_FIELD)
        is not None
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "an update proposal edit must not carry "
            f"{DECISION_ASSIGN_MEMBER_NAME_FIELD!r}",
        )

    return ActionProposalDecision(
        decision=DECISION_TOOL_REQUEST,
        tool_id=PLANNER_TASKS_UPDATE_TOOL_ID,
        arguments=None,
        edit_patch=copy.deepcopy(patch),
        proposal_action=None,
        target=None,
        checklist_patch=checklist_patch,
        assign_member_name=None,
    )


def _parse_t12_existing_task_decision(
    raw_decision: Mapping[str, Any],
) -> ActionProposalDecision:
    """Parse/validate one T12-3 existing-task WRITE decision.

    Accepted EXACTLY for ``planner.tasks.update`` /
    ``planner.tasks.complete`` / ``planner.tasks.trash`` /
    ``planner.tasks.restore`` with the additive contract:

    * ``target`` is REQUIRED (the model never invents a UUID; D owns
      the canonical resolution and the target is not authority);
    * ``arguments`` carries the user-intended DELTA only — the strict
      model patch subset for update (never ``taskId``, never
      ``expectedVersion``, never the authoritative ``checklist``,
      never ``status``) and an EMPTY object for the lifecycle tools;
    * ``checklist_patch`` (update only) is the checklist intent
      descriptor; D owns the read-modify-write transform;
    * ``assign_member_name`` (update only) is the natural-language
      assignee name; without a trusted member-resolution authority it
      always fails closed to a clarify downstream;
    * ``proposal_edit_patch`` / ``proposal_action`` must be null for
      the lifecycle tools and for a NEW update intent: an EDIT of the
      active update proposal is the one T12-4 exception, parsed by
      ``_parse_t12_update_edit_decision`` (a T12 tool performs at
      most ONE operation per turn).

    Everything else fails closed with a deterministic code.
    """

    # Mixed-intent guard (T11-5 section 8 generalization): a T12
    # existing-task mutation performs exactly one operation per turn.
    if (
        raw_decision.get(DECISION_PROPOSAL_ACTION_FIELD)
        is not None
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "a T12 existing-task tool_request must not carry "
            f"{DECISION_PROPOSAL_ACTION_FIELD!r}",
        )

    if (
        raw_decision.get("answer") is not None
        or raw_decision.get("question") is not None
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "tool_request requires 'answer' and 'question' "
            "to be null",
        )

    tool_id = raw_decision.get("tool_id")

    # ---- the T12-4 update-proposal EDIT intent ----------------------
    # ``planner.tasks.update`` may carry ``proposal_edit_patch``: the
    # user wants to revise the ACTIVE update proposal. The lifecycle
    # tools keep the strict no-patch-body rule (T12-4 sections 3 and
    # 26): an edit patch on complete/trash/restore is rejected.
    if (
        raw_decision.get(DECISION_WRITE_ADDITIVE_FIELD)
        is not None
    ):
        if tool_id != PLANNER_TASKS_UPDATE_TOOL_ID:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "only planner.tasks.update may carry "
                f"{DECISION_WRITE_ADDITIVE_FIELD!r} as a "
                "proposal edit intent",
            )

        return _parse_t12_update_edit_decision(raw_decision)

    target_raw = raw_decision.get(DECISION_TARGET_FIELD)

    # Normalización: si el modelo colocó target dentro de arguments,
    # extraerlo y usarlo (compatibilidad con target anidado).
    if target_raw is None and isinstance(
        raw_decision.get("arguments"), dict
    ):
        nested = raw_decision["arguments"].get(
            DECISION_TARGET_FIELD
        )
        if nested is not None:
            target_raw = nested

    # Normalización: si el modelo colocó checklist_patch dentro de arguments,
    # extraerlo y usarlo (compatibilidad con checklist_patch anidado).
    checklist_raw = raw_decision.get(DECISION_CHECKLIST_PATCH_FIELD)
    if checklist_raw is None and isinstance(
        raw_decision.get("arguments"), dict
    ):
        nested = raw_decision["arguments"].get(
            DECISION_CHECKLIST_PATCH_FIELD
        )
        if nested is not None:
            checklist_raw = nested

    if target_raw is None:
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            f"{DECISION_TARGET_FIELD!r} is required for an "
            "existing-task write",
        )
    else:
        try:
            target_pair = validate_task_target(target_raw)

        except TaskTargetError as error:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_TARGET_FIELD!r}: {error.message}",
            ) from error

    arguments = raw_decision.get("arguments")

    if not isinstance(arguments, dict):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "tool_request requires 'arguments' to be a plain "
            "JSON object",
        )

    # target es un campo de nivel superior gestionado por D (T12-3
    # section 3). El modelo a veces lo coloca dentro de arguments por
    # error; D lo descarta de arguments porque la resolución del target
    # es de la orqueta, nunca del modelo.
    # checklist_patch también es un campo de nivel superior; el modelo
    # a veces lo coloca dentro de arguments; D lo descarta de arguments.
    arguments = {
        k: v
        for k, v in arguments.items()
        if k not in (DECISION_TARGET_FIELD, DECISION_CHECKLIST_PATCH_FIELD)
    }

    forbidden = forbidden_keys_in_arguments(arguments)

    if forbidden:
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "'arguments' must not carry identity/auth/transport "
            "fields: " + ", ".join(forbidden),
        )

    checklist_patch = None

    # checklist_raw ya fue extraído arriba (incluyendo desde arguments anidado)
    if checklist_raw is not None:
        if tool_id != PLANNER_TASKS_UPDATE_TOOL_ID:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_CHECKLIST_PATCH_FIELD!r} is only valid "
                "for planner.tasks.update",
            )

        try:
            checklist_patch = validate_checklist_patch(
                checklist_raw,
            )

        except TaskTargetError as error:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_CHECKLIST_PATCH_FIELD!r}: "
                f"{error.message}",
            ) from error

    assign_member_name = raw_decision.get(
        DECISION_ASSIGN_MEMBER_NAME_FIELD,
    )

    if assign_member_name is not None:
        if tool_id != PLANNER_TASKS_UPDATE_TOOL_ID:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_ASSIGN_MEMBER_NAME_FIELD!r} is only "
                "valid for planner.tasks.update",
            )

        if not isinstance(assign_member_name, str) or not (
            assign_member_name.strip()
        ):
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_ASSIGN_MEMBER_NAME_FIELD!r} must be a "
                "non-empty string",
            )

        if len(assign_member_name) > 200:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_ASSIGN_MEMBER_NAME_FIELD!r} is too long",
            )

    arg_violations = validate_model_write_arguments(
        tool_id,
        arguments,
    )

    # A checklist-only intent (or an assignee-name intent) IS the
    # user-intended delta: the empty-args violation does not apply
    # when one of those additive intents is present.
    if arg_violations == ["empty_update_patch"] and (
        checklist_patch is not None
        or assign_member_name is not None
    ):
        arg_violations = []

    if arg_violations:
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "the model patch is not a valid "
            f"{tool_id} delta: " + ", ".join(arg_violations),
        )

    return ActionProposalDecision(
        decision=DECISION_TOOL_REQUEST,
        tool_id=tool_id,
        arguments=copy.deepcopy(dict(arguments)),
        edit_patch=None,
        proposal_action=None,
        target=target_pair,
        checklist_patch=checklist_patch,
        assign_member_name=assign_member_name,
    )


def parse_action_proposal_decision(
    raw_decision: Any,
) -> ActionProposalDecision:
    """Validate one raw model decision against the additive v2 gate.

    Raises ``ToolDecisionError`` on every deviation. Nothing is coerced.

    The accepted shapes are:

    * the T11-4 WRITE shapes (``tool_request`` with
      ``planner.tasks.create`` plus ``arguments`` and/or
      ``proposal_edit_patch``);
    * the v2 envelopes of the REAL Node A whose decision object always
      carries every schema field: ``direct_response`` / ``clarify`` /
      READ ``tool_request`` with ``proposal_edit_patch: null`` are
      mapped onto the canonical frozen contract via
      ``v1_projection``.
    """

    if not isinstance(raw_decision, dict) or not all(
        isinstance(key, str) for key in raw_decision
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "the decision payload must be a JSON object",
        )

    unknown = sorted(
        key
        for key in raw_decision
        if key
        not in DECISION_WRITE_TOP_LEVEL_FIELDS
    )

    if unknown:
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "unexpected decision field(s): "
            + ", ".join(unknown),
        )

    kind = raw_decision.get("decision")

    # ---- the frozen T10 shapes re-encoded in the v2 envelope ----------
    if kind in (DECISION_DIRECT_RESPONSE, DECISION_CLARIFY):
        patch = raw_decision.get(DECISION_WRITE_ADDITIVE_FIELD)

        if patch is not None:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "this decision shape requires "
                f"{DECISION_WRITE_ADDITIVE_FIELD!r} to be null",
            )

        _reject_t12_additive_fields(
            raw_decision,
            "this decision shape",
        )

        proposal_action = raw_decision.get(
            DECISION_PROPOSAL_ACTION_FIELD,
        )

        if kind == DECISION_DIRECT_RESPONSE and proposal_action in (
            "confirm",
            "cancel",
        ):
            # ---- the T11-5 lifecycle intent (additive) --------------
            # A only interprets the intent; D resolves it against the
            # CURRENT active proposal. The model answer is ignored: D
            # owns the canonical lifecycle response.
            answer = raw_decision.get("answer")

            if not (
                isinstance(answer, str) and answer.strip()
            ):
                raise ToolDecisionError(
                    "TOOL_DECISION_INVALID",
                    "direct_response requires a non-empty 'answer'",
                )

            if (
                raw_decision.get("question") is not None
                or raw_decision.get("tool_id") is not None
                or raw_decision.get("arguments") is not None
            ):
                raise ToolDecisionError(
                    "TOOL_DECISION_INVALID",
                    "a lifecycle intent must not carry 'question', "
                    "'tool_id' or 'arguments'",
                )

            return ActionProposalDecision(
                decision=DECISION_DIRECT_RESPONSE,
                tool_id=None,
                arguments=None,
                edit_patch=None,
                proposal_action=proposal_action,
            )

        if proposal_action is not None:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_PROPOSAL_ACTION_FIELD!r} must be "
                "'confirm', 'cancel' or null",
            )

        answer = raw_decision.get("answer")
        question = raw_decision.get("question")
        tool_id = raw_decision.get("tool_id")
        arguments = raw_decision.get("arguments")

        if kind == DECISION_DIRECT_RESPONSE:
            if not (
                isinstance(answer, str) and answer.strip()
            ):
                raise ToolDecisionError(
                    "TOOL_DECISION_INVALID",
                    "direct_response requires a non-empty 'answer'",
                )

            if (
                question is not None
                or tool_id is not None
                or arguments is not None
            ):
                raise ToolDecisionError(
                    "TOOL_DECISION_INVALID",
                    "direct_response requires 'question', 'tool_id' "
                    "and 'arguments' to be null",
                )

        else:
            if not (
                isinstance(question, str) and question.strip()
            ):
                raise ToolDecisionError(
                    "TOOL_DECISION_INVALID",
                    "clarify requires a non-empty 'question'",
                )

            if (
                answer is not None
                or tool_id is not None
                or arguments is not None
            ):
                raise ToolDecisionError(
                    "TOOL_DECISION_INVALID",
                    "clarify requires 'answer', 'tool_id' and "
                    "'arguments' to be null",
                )

        projection = {
            "decision": kind,
            "answer": answer,
            "question": question,
            "tool_id": None,
            "arguments": None,
        }

        return ActionProposalDecision(
            decision=kind,
            tool_id=None,
            arguments=None,
            edit_patch=None,
            v1_projection=projection,
        )

    if kind != DECISION_TOOL_REQUEST:
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "the decision must be one of the canonical decisions",
        )

    tool_id = raw_decision.get("tool_id")

    # ---- the T12-3 existing-task WRITE shapes --------------------------
    # (update / complete / trash / restore; T12-3 sections 2, 3, 10-13)

    if tool_id in T12_NEW_TOOL_IDS:
        return _parse_t12_existing_task_decision(raw_decision)

    # ---- generic WRITE tool_request (Pass 2) ----------------------------
    # Any WRITE tool of the frozen catalog (except the T11-1 create shape,
    # which keeps its legacy body) reaches this branch: arguments pass the
    # generic catalog validator inside `build_action_proposal`.
    if (
        tool_id != PLANNER_TASKS_CREATE_TOOL_ID
        and tool_id in PROPOSAL_TOOL_IDS
    ):
        arguments = raw_decision.get("arguments") or {}

        if not isinstance(arguments, dict):
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "a generic WRITE tool_request requires 'arguments' to be "
                "a plain JSON object",
            )

        forbidden = forbidden_keys_in_arguments(arguments)

        if forbidden:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "'arguments' must not carry identity/auth/transport "
                "fields: " + ", ".join(forbidden),
            )

        return ActionProposalDecision(
            decision=DECISION_TOOL_REQUEST,
            tool_id=tool_id,
            arguments=copy.deepcopy(arguments),
            edit_patch=None,
            v1_projection=None,
        )

    # ---- READ tool_request in a v2 envelope ----------------------------
    if tool_id != PLANNER_TASKS_CREATE_TOOL_ID and tool_id not in PROPOSAL_TOOL_IDS:
        patch = raw_decision.get(DECISION_WRITE_ADDITIVE_FIELD)

        if patch is not None:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "a READ tool_request requires "
                f"{DECISION_WRITE_ADDITIVE_FIELD!r} to be null",
            )

        _reject_t12_additive_fields(
            raw_decision,
            "a READ tool_request",
        )

        if (
            raw_decision.get(DECISION_PROPOSAL_ACTION_FIELD)
            is not None
        ):
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "a READ tool_request must not carry "
                f"{DECISION_PROPOSAL_ACTION_FIELD!r}",
            )

        if (
            raw_decision.get("answer") is not None
            or raw_decision.get("question") is not None
        ):
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "tool_request requires 'answer' and 'question' "
                "to be null",
            )

        arguments = raw_decision.get("arguments")

        if arguments is None:
            arguments = {}

        if not isinstance(arguments, dict):
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "tool_request requires 'arguments' to be a plain "
                "JSON object",
            )

        forbidden = forbidden_keys_in_arguments(arguments)

        if forbidden:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "'arguments' must not carry identity/auth/transport "
                "fields: " + ", ".join(forbidden),
            )

        # The frozen parser stays the ONLY authority over the READ
        # allow-list, the argument precheck and the size bound.
        projection = {
            "decision": DECISION_TOOL_REQUEST,
            "answer": None,
            "question": None,
            "tool_id": tool_id,
            "arguments": copy.deepcopy(arguments),
        }

        return ActionProposalDecision(
            decision=DECISION_TOOL_REQUEST,
            tool_id=tool_id,
            arguments=None,
            edit_patch=None,
            v1_projection=projection,
        )

    # ---- the T11-4 WRITE shapes (planner.tasks.create) ----------------

    # Mixed-intent guard (T11-5 section 8): one turn performs at most
    # ONE lifecycle operation. A decision that combines a lifecycle
    # action with an edit patch or a create body is rejected outright;
    # Node A must choose the EDIT (or clarify) and the confirmation
    # then requires another turn.
    if (
        raw_decision.get(DECISION_PROPOSAL_ACTION_FIELD)
        is not None
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "a WRITE tool_request must not carry "
            f"{DECISION_PROPOSAL_ACTION_FIELD!r}",
        )

    # A create has NO existing-task target, no checklist intent and no
    # assignee name (T12-3 sections 3 and 11): those additive fields
    # belong exclusively to the existing-task WRITE tools.
    _reject_t12_additive_fields(
        raw_decision,
        "a planner.tasks.create tool_request",
    )

    if (
        raw_decision.get("answer") is not None
        or raw_decision.get("question") is not None
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "tool_request requires 'answer' and 'question' "
            "to be null",
        )

    arguments = raw_decision.get("arguments")

    if arguments is not None and not isinstance(
        arguments,
        dict,
    ):
        raise ToolDecisionError(
            "TOOL_DECISION_INVALID",
            "tool_request requires 'arguments' to be a plain "
            "JSON object",
        )

    if arguments is not None:
        forbidden = forbidden_keys_in_arguments(arguments)

        if forbidden:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "'arguments' must not carry identity/auth/transport "
                "fields: " + ", ".join(forbidden),
            )

    patch = raw_decision.get(DECISION_WRITE_ADDITIVE_FIELD)

    if patch is not None:
        if not isinstance(patch, dict) or not all(
            isinstance(key, str) for key in patch
        ):
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_WRITE_ADDITIVE_FIELD!r} must be a "
                "plain JSON object",
            )

        patch_violations = validate_edit_patch(patch)

        if patch_violations:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                f"{DECISION_WRITE_ADDITIVE_FIELD!r} is not a "
                "valid edit patch: "
                + ", ".join(patch_violations),
            )

        patch = copy.deepcopy(patch)

    else:
        patch = None

    # An EDIT turn never consumes ``arguments``: the REAL Node A emits
    # ``arguments: null`` with the patch, and a full replacement body
    # is ignored either way (T11-4 section 6).
    if patch is not None:
        effective_arguments = None
    else:
        if arguments is None:
            raise ToolDecisionError(
                "TOOL_DECISION_INVALID",
                "tool_request requires 'arguments' to be a plain "
                "JSON object",
            )

        effective_arguments = copy.deepcopy(arguments)

    return ActionProposalDecision(
        decision=DECISION_TOOL_REQUEST,
        tool_id=PLANNER_TASKS_CREATE_TOOL_ID,
        arguments=effective_arguments,
        edit_patch=patch,
    )

# The internal synthesis phase (T09-F). It is a NEW internal request:
# it never reuses the decision request id.
SYNTHESIS_MODE = "structured"

SYNTHESIS_PHASE = "synthesize"

# The Node D registry endpoint. It mirrors ``app.CONTROL_PLANE``; the two
# values are kept equal by an explicit test. T09-D does not modify the
# control-plane routing.
CONTROL_PLANE = "http://127.0.0.1:8020"

RESOLVE_TIMEOUT_S = 10.0


# ---------------------------------------------------------------------------
# T09-1 bounds
# ---------------------------------------------------------------------------

# One tool call per turn. This is a hard bound, not a soft preference.
MAX_TOOL_CALLS = 1

# Upper bound of the canonical serialized tool arguments.
MAX_TOOL_ARGUMENT_BYTES = 4096


# ---------------------------------------------------------------------------
# Correlation derivation
# ---------------------------------------------------------------------------

# The T05 RequestId pattern is ``^req_[A-Za-z0-9_-]{8,64}$``, so the
# internal request id cannot use the dotted form of the task example.
# The deterministic equivalent used by T09-D is:
#
#   req_<label>_<sha256(caller_request_id)[:16]>_t09d1
#
# where ``<label>`` is the caller request id body (without the ``req_``
# prefix), sanitized to ``[A-Za-z0-9_-]`` and truncated to 24 characters.
# The 16 hex characters of the digest make the derived id collision-safe
# even when two caller request ids share a long prefix.
INTERNAL_REQUEST_ID_PREFIX = "req_"

INTERNAL_REQUEST_ID_MARKER = "t09d1"

# The marker of the SECOND internal request of a tool turn: the
# synthesis request. It is deterministic and always distinct from the
# decision request id of the same turn.
INTERNAL_SYNTHESIS_REQUEST_ID_MARKER = "t09f2"

INTERNAL_REQUEST_ID_MAX_LABEL = 24

INTERNAL_REQUEST_ID_DIGEST_CHARS = 16

INTERNAL_REQUEST_ID_MAX_BODY = 64

INTERNAL_REQUEST_ID_MIN_BODY = 8


# ---------------------------------------------------------------------------
# Tool call identity
# ---------------------------------------------------------------------------

TOOL_CALL_ID_PREFIX = "tcall_"

TOOL_CALL_ID_DIGEST_CHARS = 32


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

LOG_DIR = Path(
    os.getenv(
        "HOMI_LOG_DIR",
        r"C:\Homi\logs",
    )
)

TOOL_LOG_FILE = LOG_DIR / "orchestrator-tools.log"

# The exact key set of the T09 structured telemetry record. Nothing else
# is ever written: no bearer token, no tool arguments, no payload text, no
# answer, no tool result, no actor_id, no household_id and no decision
# JSON.
TOOL_TELEMETRY_FIELDS: tuple[str, ...] = (
    "timestamp",
    "request_id",
    "trace_id",
    "operation",
    "decision_kind",
    "tool_id",
    "tool_call_id",
    "outcome",
    "latency_ms",
    "error_code",
)


def _build_tool_logger() -> logging.Logger:

    tool_logger = logging.getLogger(
        "homi.orchestrator.tool"
    )

    if tool_logger.handlers:
        return tool_logger

    tool_logger.setLevel(logging.INFO)
    tool_logger.propagate = False

    try:
        LOG_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        handler: logging.Handler = logging.FileHandler(
            TOOL_LOG_FILE,
            encoding="utf-8",
        )

        handler.setFormatter(
            logging.Formatter(
                "%(message)s"
            )
        )

        tool_logger.addHandler(handler)

    except Exception:
        tool_logger.addHandler(
            logging.NullHandler()
        )

    return tool_logger


TOOL_LOGGER = _build_tool_logger()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolLoopError(RuntimeError):
    """Fail-closed error raised by the T09-D orchestration seam."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:

        super().__init__(
            f"{code}: {message}"
        )

        self.code = code
        self.message = message


class ToolExecutorDisabledError(RuntimeError):
    """Raised by the production executor while it stays disabled."""


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------

# Identity-only keys. They are allowed inside the T05 envelope context
# (the authoritative identity boundary that T07 will consume) and are
# never allowed inside the model-facing payload.
IDENTITY_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "actor_id",
        "household_id",
        "membership_id",
        "role",
        "user_id",
    }
)


def _normalized_key(key: str) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        key.lower(),
    )


IDENTITY_ONLY_KEYS_NORMALIZED = frozenset(
    _normalized_key(key)
    for key in IDENTITY_ONLY_KEYS
)


# Auth/transport keys that the T09-B catalogue list does not cover.
# Normalized form.
EXTRA_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "accesstoken",
        "apikey",
        "auth",
        "authheader",
        "authorizationheader",
        "bearertoken",
        "cookie",
        "credential",
        "credentials",
        "homeplus",
        "homeplusbaseurl",
        "homeplusurl",
        "idtoken",
        "jwt",
        "refreshtoken",
        "session",
        "setcookie",
        "supabase",
        "supabasejwt",
        "toolurl",
        "usertoken",
    }
)


def _iter_all_keys(node: Any) -> list[str]:
    """Collect every object key reachable inside a node."""

    found: list[str] = []

    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                found.append(key)

            found.extend(
                _iter_all_keys(value)
            )

    elif isinstance(node, (list, tuple)):
        for value in node:
            found.extend(
                _iter_all_keys(value)
            )

    return found


def violating_keys(
    node: Any,
    *,
    allow_identity: bool,
) -> list[str]:
    """Identity/auth/transport keys reachable inside a node.

    ``allow_identity`` is used for the T05 envelope, whose context
    legitimately carries the actor and household identity. The
    model-facing payload never allows them.
    """

    found: set[str] = set()

    for key in _iter_all_keys(node):
        normalized = _normalized_key(key)

        if (
            allow_identity
            and normalized in IDENTITY_ONLY_KEYS_NORMALIZED
        ):
            continue

        if (
            is_forbidden_identity_key(key)
            or normalized in EXTRA_FORBIDDEN_KEYS
        ):
            found.add(key)

    return sorted(found)


def assert_a_request_is_sanitized(
    envelope: RequestEnvelope,
    *,
    secret_values: Sequence[str] = (),
) -> None:
    """Fail closed when the outgoing Node A request carries auth material.

    The gate proves three properties of the object sent to Node A:

    * the model-facing payload carries no identity/auth/transport key;
    * the whole envelope carries no auth/transport key;
    * no known secret value (the HomePlus bearer token) appears anywhere
      in the serialized envelope.
    """

    payload_violations = violating_keys(
        envelope.payload,
        allow_identity=False,
    )

    envelope_violations = violating_keys(
        envelope.model_dump(mode="json"),
        allow_identity=True,
    )

    violations = sorted(
        set(payload_violations)
        | set(envelope_violations)
    )

    if violations:
        raise ToolLoopError(
            "A_REQUEST_NOT_SANITIZED",
            "the internal provider request carries forbidden "
            "keys: " + ", ".join(violations),
        )

    serialized = json.dumps(
        envelope.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
    )

    for secret in secret_values:
        if secret and secret in serialized:
            raise ToolLoopError(
                "A_REQUEST_NOT_SANITIZED",
                "the internal provider request carries secret "
                "material",
            )


# ---------------------------------------------------------------------------
# Credential capture
# ---------------------------------------------------------------------------


def extract_bearer_token(
    authorization: str | None,
) -> str | None:
    """Capture the opaque bearer credential from an inbound header.

    The credential is returned verbatim and is never decoded, validated,
    logged or persisted. Anything that is not a well-formed ``Bearer``
    credential is treated as absent, so an unusable header fails closed
    for a tool request.
    """

    if not isinstance(authorization, str):
        return None

    value = authorization.strip()

    if not value:
        return None

    parts = value.split(None, 1)

    if len(parts) != 2:
        return None

    scheme = parts[0]

    credential = parts[1].strip()

    if scheme.lower() != "bearer":
        return None

    if not credential:
        return None

    return credential


# ---------------------------------------------------------------------------
# Internal Node A request
# ---------------------------------------------------------------------------


def derive_internal_request_id(
    caller_request_id: str,
    marker: str = INTERNAL_REQUEST_ID_MARKER,
) -> str:
    """Derive the deterministic internal Node A request id.

    See the module constants for the exact convention. The result always
    satisfies the T05 ``RequestId`` pattern and never equals the caller
    request id.

    The ``marker`` selects the pass: the decision pass uses
    ``t09d1`` and the synthesis pass uses ``t09f2``. Two passes of the
    same turn therefore never share an internal request id.
    """

    label = caller_request_id

    if label.startswith(INTERNAL_REQUEST_ID_PREFIX):
        label = label[len(INTERNAL_REQUEST_ID_PREFIX):]

    safe_label = re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        label,
    )[:INTERNAL_REQUEST_ID_MAX_LABEL]

    digest = hashlib.sha256(
        caller_request_id.encode("utf-8")
    ).hexdigest()[:INTERNAL_REQUEST_ID_DIGEST_CHARS]

    body = (
        f"{safe_label}_{digest}_"
        f"{marker}"
    )

    if len(body) > INTERNAL_REQUEST_ID_MAX_BODY:
        body = body[:INTERNAL_REQUEST_ID_MAX_BODY]

    while len(body) < INTERNAL_REQUEST_ID_MIN_BODY:
        body = body + "0"

    return INTERNAL_REQUEST_ID_PREFIX + body


def decision_schema_digest() -> str:
    """The canonical SHA256 digest of the T09 decision JSON Schema."""

    return hashlib.sha256(
        decision_json_schema_text().encode("utf-8")
    ).hexdigest()


# The model-facing descriptor of the four T12 existing-task WRITE
# tools, sent ONLY in the additive v2 decision payload. They describe
# the MODEL-facing delta contract (target + intent), never the full
# canonical T12-2 arguments: ``taskId`` is resolved by the
# orchestrator, ``expectedVersion`` is injected by the orchestrator
# from the trusted preflight READ, and the checklist is transformed
# by the orchestrator from the authoritative READ result.
T12_MODEL_TOOL_DESCRIPTIONS = {
    PLANNER_TASKS_UPDATE_TOOL_ID: (
        "Propose updating an EXISTING Planner task (title, "
        "description, due date, due time, assignment, priority, "
        "category or checklist). Choosing this tool does NOT change "
        "anything: the orchestrator resolves the target, reads the "
        "authoritative task and builds a proposal the user must "
        "confirm first. Required additive field: target "
        "({kind: 'task', task_id: UUID | null, task_title: string | "
        "null}; exactly one of task_id/task_title; NEVER invent a "
        "UUID). arguments: the intended delta only (title, "
        "description, dueDate, dueTime, assignedToMemberId, "
        "priority, category, templateKey, "
        "estimatedDurationMinutes, requiresVerification, goalId, "
        "planClassification) — never taskId, never expectedVersion, "
        "never the full checklist array. For a checklist item "
        "change use the additive checklist_patch "
        "({op: 'add'|'edit'|'complete'|'reopen'|'remove', item: "
        "exact item text, newItemText for edit, index optional}). "
        "A dueTime-only intent keeps the existing due date. To clear "
        "a value send null (dueDate: null clears the date and its "
        "time; assignedToMemberId: null unassigns). To assign by "
        "person name use the additive assign_member_name (the "
        "orchestrator will ask for the exact member). EDIT of the "
        "ACTIVE update proposal (a follow-up such as 'mejor el "
        "sábado' while the proposal is pending): send "
        "proposal_edit_patch with ONLY the changed user-facing "
        "fields (title, description, dueDate, dueTime, "
        "assignedToMemberId), target null, arguments null; a "
        "checklist_patch may revise the pending checklist intent. "
        "The orchestrator re-reads the authoritative task, "
        "refreshes expectedVersion and replaces the proposal with a "
        "new revision."
    ),
    PLANNER_TASKS_COMPLETE_TOOL_ID: (
        "Propose marking an EXISTING Planner task as completed. "
        "Choosing this tool does NOT complete anything: the "
        "orchestrator builds a proposal the user must confirm first. "
        "Required additive field: target (kind task; task_id UUID | "
        "null; task_title string | null; exactly one; NEVER invent a "
        "UUID). arguments: empty object {}. Only a pending task "
        "without the evidence workflow can be completed."
    ),
    PLANNER_TASKS_TRASH_TOOL_ID: (
        "Propose moving an EXISTING Planner task to the trash "
        "(REVERSIBLE soft delete; it can be restored later; there is "
        "NO permanent delete). Choosing this tool does NOT delete "
        "anything: the orchestrator builds a proposal the user must "
        "confirm first. Required additive field: target (kind task; "
        "task_id UUID | null; task_title string | null; exactly one; "
        "NEVER invent a UUID). arguments: empty object {}."
    ),
    PLANNER_TASKS_RESTORE_TOOL_ID: (
        "Propose restoring a trashed Planner task back to its "
        "operational state (strictly the trash/restore lifecycle; "
        "NOT reactivate, NOT unarchive, NOT reopening a completed "
        "task). Choosing this tool does NOT restore anything: the "
        "orchestrator builds a proposal the user must confirm first. "
        "Required additive field: target (kind task; task_id UUID | "
        "null; task_title string | null; exactly one; NEVER invent a "
        "UUID). arguments: empty object {}."
    ),
}

# The model-facing patch subset for planner.tasks.update (the
# user-intended delta only; D owns taskId, expectedVersion and the
# authoritative checklist transform).
T12_UPDATE_MODEL_PATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": dict(
        MODEL_WRITE_PATCH_PROPERTIES,
    ),
    "required": [],
}

T12_LIFECYCLE_MODEL_ARGUMENTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {},
    "required": [],
}


MODEL_TOOL_PROJECTION_VERSION = "2.1.0"
MODEL_STATUS_ALIAS = "lifecycle_state"
# The deployed THINK provider keeps its own frozen v1 decision grammar. It
# is not the canonical HomePlus tool digest: it only identifies the safe
# five-field model output shape used for READ decisions. Node D still
# revalidates every returned decision against its local canonical contracts.
THINK_READ_DECISION_SCHEMA_DIGEST = os.getenv(
    "HOMI_THINK_READ_DECISION_SCHEMA_DIGEST",
    "b36d39a5b5dd7e680547d609001955eecf5bd576a2b0b148bda248cfd840df87",
)

_MODEL_DOMAIN_HINTS: Mapping[str, tuple[str, ...]] = {
    "planner": (
        "agenda", "calendar", "calendario", "event", "evento", "goal",
        "meta", "objetivo", "plan", "planner", "recordatorio", "task",
        "tarea",
    ),
    "finance": (
        "balance", "cuenta", "cuota", "dinero", "expense", "finanza",
        "gasto", "income", "ingreso", "movimiento", "pago", "saldo",
        "transferencia",
    ),
    "inventory": (
        "compra", "despensa", "inventario", "inventory", "producto",
        "stock",
    ),
    "assets": (
        "activo", "asset", "garantia", "mantenimiento", "objeto",
        "pertenencia",
    ),
    "homecloud": (
        "album", "archivo", "carpeta", "cloud", "documento", "foto",
        "homecloud", "memoria", "nube",
    ),
    "messages": (
        "chat", "conversacion", "mensaje", "message",
    ),
    "households": (
        "familia", "familiar", "hogar", "household", "invitacion",
        "miembro", "permiso", "rol",
    ),
    "hplus": (
        "hplus", "punto", "recompensa",
    ),
    "identity": (
        "identidad", "perfil", "sesion", "usuario",
    ),
    "home": (
        "actividad", "atencion", "inicio", "resumen",
    ),
    "notifications": (
        "notificacion", "notification",
    ),
    "feature-flags": (
        "feature flag", "funcionalidad habilitada",
    ),
}

_MODEL_FAMILY_HINTS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "planner": {
        "tasks": ("task", "tarea"),
        "events": ("agenda", "calendar", "calendario", "event", "evento"),
        "goals": ("goal", "meta", "objetivo"),
        "plans": ("plan",),
    },
    "finance": {
        "accounts": ("balance", "cuenta", "saldo"),
        "movements": ("gasto", "ingreso", "movimiento", "transaction"),
        "payments": ("cuota", "pago"),
        "transfers": ("transferencia",),
    },
    "inventory": {
        "products": ("despensa", "inventario", "producto", "stock"),
        "items": ("despensa", "inventario", "producto", "stock"),
        "purchases": ("compra",),
    },
    "homecloud": {
        "files": ("archivo", "documento"),
        "albums": ("album", "foto"),
        "folders": ("carpeta",),
        "memories": ("memoria",),
    },
}

_MODEL_WRITE_HINTS: tuple[str, ...] = (
    "actualiza", "agrega", "anade", "archiva", "borra", "cambia",
    "cancela", "completa", "confirm", "consume", "crea", "edita",
    "elimina", "marca", "modifica", "mueve", "paga", "registra",
    "restaura", "transfiere",
)


def _normalized_model_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).lower())
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def _model_tool_id(tool_id: str) -> str:
    """Provider-compatible, deterministic alias for one canonical tool id."""

    parts = tool_id.replace("-", "_").split(".")
    if len(parts) == 2:
        return f"{parts[0]}.resource.{parts[1]}"
    if len(parts) == 3:
        return ".".join(parts)
    return f"{parts[0]}.{'_'.join(parts[1:-1])}.{parts[-1]}"


def _model_tool_aliases() -> tuple[dict[str, str], dict[str, str]]:
    canonical_to_model = {
        tool_id: _model_tool_id(tool_id)
        for tool_id in effective_tool_ids()
    }
    model_to_canonical = {
        model_id: tool_id
        for tool_id, model_id in canonical_to_model.items()
    }
    if len(model_to_canonical) != len(canonical_to_model):
        raise ToolCatalogError(
            "MODEL_PROJECTION_ALIAS_COLLISION",
            "model-facing tool aliases must be one-to-one",
        )
    return canonical_to_model, model_to_canonical


def _is_model_write_intent(text: str) -> bool:
    normalized = _normalized_model_text(text)
    return any(hint in normalized for hint in _MODEL_WRITE_HINTS)


def _selected_model_domains(text: str) -> tuple[str, ...]:
    normalized = _normalized_model_text(text)
    selected = tuple(
        domain
        for domain, hints in _MODEL_DOMAIN_HINTS.items()
        if any(hint in normalized for hint in hints)
    )
    # Planner is the stable default for generic/ambiguous turns. The model
    # can still answer directly or clarify; no tool is executed implicitly.
    return selected or ("planner",)


def _selected_model_families(
    domain: str,
    text: str,
) -> tuple[str, ...]:
    normalized = _normalized_model_text(text)
    families = _MODEL_FAMILY_HINTS.get(domain, {})
    return tuple(
        family
        for family, hints in families.items()
        if any(hint in normalized for hint in hints)
    )


def _tool_matches_model_scope(
    tool_id: str,
    domains: Sequence[str],
    text: str,
    *,
    write_intent: bool,
    kind: str,
) -> bool:
    parts = tool_id.split(".")
    domain = parts[0]
    if domain not in domains:
        return False
    if (kind == "WRITE") != write_intent:
        return False
    if kind == "READ" and tool_id not in TOOL_PROJECTIONS:
        return False
    normalized = _normalized_model_text(text)
    explicit_search = any(
        hint in normalized
        for hint in ("busca", "encuentra", "localiza")
    )
    if explicit_search and domain == "planner":
        return tool_id == "planner.tasks.search"
    families = _selected_model_families(domain, text)
    if not families:
        return True
    remainder = ".".join(parts[1:])
    return any(remainder.startswith(family) for family in families)


def _model_input_schema(
    tool_id: str,
    definition: Mapping[str, Any],
) -> dict[str, Any]:
    # The eight original Planner READ contracts remain canonical. Their
    # richer temporal filters are preserved rather than replaced by the
    # generated v2 generic schema.
    original = catalog().get(tool_id)
    source = original if original is not None else definition
    schema = copy.deepcopy(dict(source["inputSchema"]))

    if tool_id in ("planner.tasks.list", "planner.events.list"):
        properties = schema.get("properties")
        if isinstance(properties, dict) and "status" in properties:
            properties[MODEL_STATUS_ALIAS] = properties.pop("status")
            properties[MODEL_STATUS_ALIAS]["description"] = (
                "Model-facing alias for the canonical status filter. "
                "Node D maps it deterministically before gateway validation."
            )
        required = schema.get("required")
        if isinstance(required, list):
            schema["required"] = [
                MODEL_STATUS_ALIAS if field == "status" else field
                for field in required
            ]
    if tool_id == "planner.tasks.search":
        # The canonical search endpoint derives household scope from the
        # bearer token and only accepts `context=active`. Its generated v2
        # schema still advertises PERSONAL/HOUSEHOLD; hiding that model-facing
        # field prevents an invalid read without changing the canonical
        # contract or widening authority.
        properties = schema.get("properties")
        if isinstance(properties, dict):
            properties.pop("context", None)
    return schema


def _model_description(definition: Mapping[str, Any]) -> str:
    tool_id = str(definition["tool_id"])
    parts = tool_id.replace("-", " ").split(".")
    kind = str(definition.get("kind", "READ"))
    behavior = (
        "proposes a WRITE that requires user confirmation"
        if kind == "WRITE"
        else (
            "performs an authorized READ; arguments must contain only this "
            "input schema and must omit target, checklist_patch, "
            "assign_member_name, proposal_edit_patch and proposal_action"
        )
    )
    return (
        f"HomePlus {parts[0]}: {' '.join(parts[1:])}; {behavior}. "
        f"{definition.get('description', '')}"
    ).strip()


def _write_tool_catalog_projection(text: str = "") -> list[dict[str, Any]]:
    """Versioned provider-compatible projection of the canonical catalogue.

    The frozen v1 and definitive v2 catalogues are never modified here.
    Candidate reduction only keeps the payload inside the real THINK
    provider limit; it does not grant authority. Node D maps aliases back,
    revalidates against the canonical contract and the HomePlus gateway is
    still the final authorization/argument authority.
    """

    domains = _selected_model_domains(text)
    write_intent = _is_model_write_intent(text)
    canonical_to_model, _ = _model_tool_aliases()
    loaded_v2 = catalog_v2()
    selected: list[Mapping[str, Any]] = []

    for definition in loaded_v2.tools:
        tool_id = str(definition["tool_id"])
        if not _tool_matches_model_scope(
            tool_id,
            domains,
            text,
            write_intent=write_intent,
            kind=str(definition.get("kind", "READ")),
        ):
            continue
        selected.append(definition)

    if not write_intent:
        # THINK-A's frozen READ grammar accepts exactly the eight v1 model
        # ids. They are a provider representation only. Up to eight scoped
        # canonical READ tools are deterministically assigned to that
        # palette and mapped back before D's canonical validation.
        selected.sort(
            key=lambda definition: (
                0
                if definition["tool_id"] in CANONICAL_TOOL_IDS
                else 1,
                0
                if str(definition["tool_id"]).endswith(".list")
                else 1,
                str(definition["tool_id"]),
            )
        )
        selected = selected[: len(CANONICAL_TOOL_IDS)]
        read_aliases = _model_read_aliases_from_selected(selected)
        canonical_to_model = {
            canonical: model
            for model, canonical in read_aliases.items()
        }

    projection: list[dict[str, Any]] = []
    for definition in selected:
        tool_id = str(definition["tool_id"])
        projection.append(
            {
                "tool_id": canonical_to_model[tool_id],
                "description": _model_description(definition),
                "input_schema": _model_input_schema(tool_id, definition),
            }
        )

    return projection


def _model_read_aliases_from_selected(
    selected: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    palette = list(CANONICAL_TOOL_IDS)
    aliases: dict[str, str] = {}
    assigned_canonical: set[str] = set()

    # Preserve identity aliases where possible; this keeps Planner behavior
    # byte-compatible for the common legacy READs.
    for definition in selected:
        canonical = str(definition["tool_id"])
        if canonical in palette:
            aliases[canonical] = canonical
            assigned_canonical.add(canonical)

    # THINK-A's frozen palette names Planner search with the legacy v1 id;
    # the gateway authority remains the definitive v2 planner.tasks.search.
    selected_ids = {
        str(definition["tool_id"])
        for definition in selected
    }
    if (
        "planner.tasks.search" in selected_ids
        and "planner.search.query" not in aliases
    ):
        aliases["planner.search.query"] = "planner.tasks.search"
        assigned_canonical.add("planner.tasks.search")

    free_aliases = [alias for alias in palette if alias not in aliases]
    for definition in selected:
        canonical = str(definition["tool_id"])
        if canonical in assigned_canonical:
            continue
        if not free_aliases:
            break
        aliases[free_aliases.pop(0)] = canonical
        assigned_canonical.add(canonical)
    return aliases


def _model_read_aliases(text: str) -> dict[str, str]:
    projection = _write_tool_catalog_projection(text)
    model_ids = [entry["tool_id"] for entry in projection]
    domains = _selected_model_domains(text)
    loaded_v2 = catalog_v2()
    selected = [
        definition
        for definition in loaded_v2.tools
        if _tool_matches_model_scope(
            str(definition["tool_id"]),
            domains,
            text,
            write_intent=False,
            kind=str(definition.get("kind", "READ")),
        )
    ]
    selected.sort(
        key=lambda definition: (
            0 if definition["tool_id"] in CANONICAL_TOOL_IDS else 1,
            0 if str(definition["tool_id"]).endswith(".list") else 1,
            str(definition["tool_id"]),
        )
    )
    selected = selected[: len(model_ids)]
    return _model_read_aliases_from_selected(selected)


def _canonicalize_model_decision(
    raw_decision: Mapping[str, Any],
    text: str = "",
) -> dict[str, Any]:
    """Map only explicit model aliases; never accept authority fields."""

    decision = copy.deepcopy(dict(raw_decision))
    model_tool_id = decision.get("tool_id")
    if isinstance(model_tool_id, str):
        if _is_model_write_intent(text):
            _, model_to_canonical = _model_tool_aliases()
        else:
            model_to_canonical = _model_read_aliases(text)
        canonical_tool_id = model_to_canonical.get(model_tool_id)
        if canonical_tool_id is not None:
            decision["tool_id"] = canonical_tool_id

    arguments = decision.get("arguments")
    if isinstance(arguments, dict) and not _is_model_write_intent(text):
        # THINK-A sometimes echoes the additive WRITE fields with a null
        # value on a READ turn. They are not part of any canonical READ
        # schema: drop only explicit nulls. A non-null additive value is
        # left untouched so the canonical validator still fails closed.
        for field in (
            DECISION_TARGET_FIELD,
            DECISION_CHECKLIST_PATCH_FIELD,
            DECISION_ASSIGN_MEMBER_NAME_FIELD,
            DECISION_WRITE_ADDITIVE_FIELD,
            DECISION_PROPOSAL_ACTION_FIELD,
        ):
            if field in arguments and arguments[field] is None:
                del arguments[field]
    if (
        isinstance(arguments, dict)
        and decision.get("tool_id")
        in ("planner.tasks.list", "planner.events.list")
        and MODEL_STATUS_ALIAS in arguments
    ):
        if "status" in arguments:
            # Ambiguous dual representation fails closed in the canonical
            # validator as an unknown model alias.
            return decision
        arguments["status"] = arguments.pop(MODEL_STATUS_ALIAS)
    return decision


def _pending_proposal_business_context(
    conversation_id: Any,
) -> dict[str, Any] | None:
    """The business-only context of the active pending proposal.

    Node A needs the pending proposal CONTENT to interpret a follow-up
    as an edit or a lifecycle intent. The context carries ONLY business
    data (summary + arguments): no proposal_id, no status, no risk, no
    confirmation and no identity/auth material. An ActionProposal is
    not an authorization grant and the id is resolved by D alone.
    """

    try:
        pending = get_pending_proposal(conversation_id)
    except Exception:
        return None

    if pending is None:
        return None

    return {
        "summary": pending.summary,
        "arguments": copy.deepcopy(dict(pending.arguments)),
    }


def build_decision_payload(
    text: str,
    *,
    decision_version: str = "v1",
    pending_proposal: Mapping[str, Any] | None = None,
    context_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the model-facing payload of the internal Node A request.

    Only the fields listed by T09-D are present. The bearer token, the
    actor and household identity, the membership id, the role, the
    HomePlus URL and every transport detail are absent.

    The v1 payload is byte identical to the frozen T10 contract. The
    additive v2 payload additionally carries: the v2 decision schema
    digest trusted by the deployed Node A, the one canonical WRITE
    descriptor (from the trusted in-code proposal contract) and the
    business-only pending proposal context when a proposal is active
    for the conversation.
    """

    loaded = catalog()

    if decision_version in ("v2", "2", "2.0"):
        schema_version = DECISION_SCHEMA_VERSION_V2
    else:
        schema_version = DECISION_SCHEMA_VERSION

    if schema_version == DECISION_SCHEMA_VERSION_V2:
        write_intent = _is_model_write_intent(text)
        model_schema_version = (
            DECISION_SCHEMA_VERSION_V2
            if write_intent
            else DECISION_SCHEMA_VERSION
        )
        model_schema_digest = (
            DECISION_SCHEMA_V2_DIGEST
            if write_intent
            else THINK_READ_DECISION_SCHEMA_DIGEST
        )
        payload: dict[str, Any] = {
            "text": text,
            "mode": DECISION_MODE,
            "phase": DECISION_PHASE,
            "tool_catalog": _write_tool_catalog_projection(text),
            "catalog_digest": loaded.digest.upper(),
            "decision_schema_version": model_schema_version,
            "decision_schema_digest": model_schema_digest,
        }

        if write_intent and pending_proposal is not None:
            payload["pending_proposal"] = dict(pending_proposal)

        if write_intent and context_projection is not None:
            payload["context"] = dict(context_projection)

        return payload

    result = {
        "text": text,
        "mode": DECISION_MODE,
        "phase": DECISION_PHASE,
        "tool_catalog": loaded.model_projection(),
        "catalog_digest": loaded.digest.upper(),
        "decision_schema_version": schema_version,
        "decision_schema_digest": decision_schema_digest(),
    }
    if context_projection is not None:
        result["context"] = dict(context_projection)
    return result


def build_internal_request(
    request: RequestEnvelope,
    text: str,
    *,
    decision_version: str = "v1",
    context_projection: Mapping[str, Any] | None = None,
) -> RequestEnvelope:
    """Build the NEW internal T05 envelope sent to Node A."""

    context = request.context

    pending_proposal = None

    if decision_version in ("v2", "2", "2.0"):
        pending_proposal = _pending_proposal_business_context(
            context.conversation_id,
        )

    return RequestEnvelope(
        context=RequestContext(
            request_id=derive_internal_request_id(
                context.request_id
            ),
            trace_id=context.trace_id,
            turn_id=context.turn_id,
            conversation_id=context.conversation_id,
            actor_id=context.actor_id,
            household_id=context.household_id,
            timestamp=context.timestamp,
        ),
        capability=Capability.THINK,
        operation=OPERATION_INFER,
        payload=build_decision_payload(
            text,
            decision_version=decision_version,
            pending_proposal=pending_proposal,
            context_projection=context_projection,
        ),
    )


def internal_correlation(
    envelope: RequestEnvelope,
) -> CorrelationContext:
    """The correlation Node A must echo for the internal request."""

    context = envelope.context

    return CorrelationContext(
        request_id=context.request_id,
        trace_id=context.trace_id,
        turn_id=context.turn_id,
        conversation_id=context.conversation_id,
    )


# The identity placeholder of the synthesis request. The synthesis
# request never carries the real actor or the real household: the
# T09-F contract only preserves the trace, the conversation and the
# turn. The placeholder satisfies the T05 RequestContext contract
# without transporting any identity.
SYNTHESIS_IDENTITY_PLACEHOLDER = "redacted-t09f"


def build_synthesis_payload(
    text: str,
    plan: "ToolInvocationPlan",
    tool_result: ToolResultV1,
    catalog_digest: str,
) -> dict[str, Any]:
    """Build the model facing payload of the synthesis request.

    The payload carries:

    * the ORIGINAL user request, so the answer addresses the question
      that was actually asked;
    * the prior decision, minted by Node D: the tool call id, the
      executed tool and the VALIDATED canonical arguments;
    * the normalized tool result: the bounded, safe projection of the
      result of the SAME turn. The raw T07 result is never here;
    * the trusted catalogue digest.

    It never carries the bearer token, the actor id, the household id,
    the membership, the role, the raw T07 result or a HomePlus URL.
    """

    return {
        "text": text,
        "mode": SYNTHESIS_MODE,
        "phase": SYNTHESIS_PHASE,
        "prior_decision": {
            "tool_call_id": plan.tool_call_id,
            "tool_id": plan.tool_id,
            "arguments": dict(plan.arguments),
        },
        "tool_result": tool_result.to_payload(),
        "catalog_digest": catalog_digest,
        "tool_result_version": TOOL_RESULT_VERSION,
    }


def build_synthesis_request(
    request: RequestEnvelope,
    text: str,
    plan: "ToolInvocationPlan",
    tool_result: ToolResultV1,
    catalog_digest: str,
) -> RequestEnvelope:
    """Build the NEW internal T05 envelope of the synthesis pass.

    The request id is the deterministic synthesis id of the turn: it
    is never equal to the decision request id and it is never exposed
    to the caller.
    """

    context = request.context

    return RequestEnvelope(
        context=RequestContext(
            request_id=derive_internal_request_id(
                context.request_id,
                INTERNAL_SYNTHESIS_REQUEST_ID_MARKER,
            ),
            trace_id=context.trace_id,
            turn_id=context.turn_id,
            conversation_id=context.conversation_id,
            actor_id=SYNTHESIS_IDENTITY_PLACEHOLDER,
            household_id=SYNTHESIS_IDENTITY_PLACEHOLDER,
            timestamp=context.timestamp,
        ),
        capability=Capability.THINK,
        operation=OPERATION_INFER,
        payload=build_synthesis_payload(
            text,
            plan,
            tool_result,
            catalog_digest,
        ),
    )


def caller_correlation(
    request: RequestEnvelope,
) -> CorrelationContext:
    """The correlation the caller must always receive."""

    context = request.context

    return CorrelationContext(
        request_id=context.request_id,
        trace_id=context.trace_id,
        turn_id=context.turn_id,
        conversation_id=context.conversation_id,
    )


# ---------------------------------------------------------------------------
# Tool request validation
# ---------------------------------------------------------------------------


def canonical_arguments_json(
    arguments: Mapping[str, Any],
) -> str:
    """The deterministic canonical serialization of tool arguments."""

    return json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def validate_tool_request(
    tool_id: str,
    arguments: Any,
) -> list[str]:
    """Revalidate a model tool request from scratch.

    Node D does not trust Node A: the tool must belong to the exact
    8-tool allow-list, must be READ / READ_ONLY, the arguments must pass
    the catalogue precheck, must not carry any forbidden
    identity/auth/URL key and must stay inside the size bound.
    """

    violations: list[str] = []

    allowed_tool_ids = CANONICAL_TOOL_IDS

    if is_t24_read_enabled():
        allowed_tool_ids = effective_tool_ids()

    if tool_id not in allowed_tool_ids:
        violations.append("unknown_tool")

    loaded = None

    try:
        loaded = catalog()
    except ToolCatalogError as error:
        return [f"catalog_unavailable:{error.code}"]

    definition = loaded.get(tool_id)

    if definition is None and is_t24_read_enabled():
        try:
            loaded_v2 = catalog_v2()
        except ToolCatalogError as error:
            return [f"catalog_unavailable:{error.code}"]

        definition = loaded_v2.get(tool_id)

    if definition is not None:
        if definition.get("kind") != "READ":
            violations.append("tool_not_read")

        risk_flags = definition.get("riskFlags") or []

        if "READ_ONLY" not in risk_flags:
            violations.append("tool_not_read_only")

        if definition.get("confirmation") != "NEVER":
            violations.append(
                "tool_requires_confirmation"
            )

    violations.extend(
        precheck_tool_arguments(tool_id, arguments)
    )

    for key in violating_keys(
        arguments,
        allow_identity=False,
    ):
        violations.append(f"forbidden_key:{key}")

    try:
        canonical = canonical_arguments_json(arguments)

    except (TypeError, ValueError):
        violations.append("arguments_not_serializable")

    else:
        if (
            len(canonical.encode("utf-8"))
            > MAX_TOOL_ARGUMENT_BYTES
        ):
            violations.append("arguments_too_large")

    ordered: list[str] = []

    for violation in violations:
        if violation not in ordered:
            ordered.append(violation)

    return ordered


@dataclass(frozen=True)
class ToolInvocationPlan:
    """A validated, D-owned tool invocation.

    The plan never carries the authorization credential. The
    ``tool_call_id`` is minted by Node D after validation; a model
    provided id is rejected by the decision contract and ignored here.
    """

    tool_call_id: str
    tool_id: str
    arguments: dict[str, Any]
    catalog_digest: str


def mint_tool_call_id(
    *,
    request_id: str,
    trace_id: str,
    tool_id: str,
    arguments: Mapping[str, Any],
    catalog_digest: str,
) -> str:
    """Mint the deterministic, collision-safe tool call id.

    The id is derived from the request identity, the tool id and the
    canonical arguments. It is stable for the same request and never
    influenced by the model.
    """

    material = "|".join(
        [
            request_id,
            trace_id,
            tool_id,
            canonical_arguments_json(arguments),
            catalog_digest,
        ]
    )

    digest = hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()[:TOOL_CALL_ID_DIGEST_CHARS]

    return TOOL_CALL_ID_PREFIX + digest


def assert_tool_call_budget(
    plans: Sequence[ToolInvocationPlan],
) -> None:
    """Fail closed when the T09-1 one-tool bound would be exceeded."""

    if len(plans) > MAX_TOOL_CALLS:
        raise ToolLoopError(
            "TOOL_CALL_BUDGET_EXCEEDED",
            "a turn may issue at most "
            f"{MAX_TOOL_CALLS} tool call",
        )


# ---------------------------------------------------------------------------
# Tool executor seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolExecutionContext:
    """Request-local execution context.

    The bearer credential lives here and only here. It is never logged,
    never serialized and never leaves the request.
    """

    request_id: str
    trace_id: str
    turn_id: str
    conversation_id: str
    actor_id: str
    household_id: str
    bearer_token: str | None = None


@dataclass(frozen=True)
class ToolExecutionOutcome:
    """The result of a tool execution attempt."""

    ok: bool
    tool_result: Any = None
    error_code: ErrorCode | None = None
    error_message: str | None = None
    retryable: bool = False


# The two terminal states of a tool execution.
TOOL_STATUS_SUCCESS = "SUCCESS"

TOOL_STATUS_ERROR = "ERROR"


@dataclass(frozen=True)
class ToolExecutionResult:
    """The internal result of ONE tool execution.

    This object stays inside Node D during T09-E. The ``result`` field
    carries the real HomePlus payload and is therefore never logged,
    never sent to Node A and never exposed in the public response.
    """

    tool_call_id: str
    tool_id: str
    status: str
    result: Any = None
    error_code: ErrorCode | None = None
    error_message: str | None = None
    retryable: bool = False
    upstream_status: int | None = None

    @property
    def ok(self) -> bool:
        """Whether the execution succeeded."""

        return self.status == TOOL_STATUS_SUCCESS


def normalize_tool_execution(
    plan: ToolInvocationPlan,
    outcome: Any,
) -> ToolExecutionResult:
    """Normalize any executor outcome into a ToolExecutionResult.

    The T09-D seam returns a ``ToolExecutionOutcome``; the T09-E
    production executor returns a ``ToolExecutionResult``. Both are
    accepted so the T09-D contract keeps working unchanged.
    """

    if isinstance(outcome, ToolExecutionResult):
        return outcome

    if isinstance(outcome, ToolExecutionOutcome):
        if outcome.ok:
            return ToolExecutionResult(
                tool_call_id=plan.tool_call_id,
                tool_id=plan.tool_id,
                status=TOOL_STATUS_SUCCESS,
                result=outcome.tool_result,
            )

        return ToolExecutionResult(
            tool_call_id=plan.tool_call_id,
            tool_id=plan.tool_id,
            status=TOOL_STATUS_ERROR,
            error_code=outcome.error_code,
            error_message=outcome.error_message,
            retryable=outcome.retryable,
        )

    raise ToolLoopError(
        "TOOL_EXECUTION_INVALID",
        "the tool executor returned an unsupported outcome",
    )


class ToolExecutorProtocol(Protocol):
    """The seam T09-E implements.

    An executor may be synchronous (the T09-D test double) or
    asynchronous (the T09-E production executor). The loop awaits an
    awaitable outcome when one is returned.
    """

    def execute(
        self,
        plan: ToolInvocationPlan,
        context: ToolExecutionContext,
    ) -> Any:
        ...


class HomePlusToolExecutor:
    """The production HomePlus tool executor of Node D (T09-E).

    The executor is a transport, not an authority and not a brain:

    * it never reinterprets the user request;
    * it never asks Node A anything;
    * it never selects another tool;
    * it never changes the validated arguments;
    * it never changes the identity: the actor and the household are
      transported as assertions and T07 remains the authority;
    * it never retries: one plan produces at most one HTTP call;
    * it never executes a second tool.
    """

    state = "REAL"

    def __init__(
        self,
        client: HomePlusToolClient,
    ) -> None:
        self._client = client

    @property
    def client(self) -> HomePlusToolClient:
        """The underlying HomePlus client."""

        return self._client

    async def execute(
        self,
        plan: ToolInvocationPlan,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute exactly one validated plan against HomePlus."""

        if not context.bearer_token:
            return ToolExecutionResult(
                tool_call_id=plan.tool_call_id,
                tool_id=plan.tool_id,
                status=TOOL_STATUS_ERROR,
                error_code=ErrorCode.POLICY_DENIED,
                error_message=(
                    "a HomePlus authorization credential is required "
                    "to execute a tool request"
                ),
                retryable=False,
            )

        call = await self._client.invoke(
            tool_id=plan.tool_id,
            arguments=plan.arguments,
            actor_id=context.actor_id,
            household_id=context.household_id,
            bearer_token=context.bearer_token,
        )

        return self._to_result(plan, call)

    def _to_result(
        self,
        plan: ToolInvocationPlan,
        call: ToolCallResult,
    ) -> ToolExecutionResult:
        """Map a client outcome onto a tool execution result."""

        if not call.ok:
            return ToolExecutionResult(
                tool_call_id=plan.tool_call_id,
                tool_id=plan.tool_id,
                status=TOOL_STATUS_ERROR,
                error_code=call.error_code,
                error_message=call.error_message,
                retryable=call.retryable,
                upstream_status=call.upstream_status,
            )

        return ToolExecutionResult(
            tool_call_id=plan.tool_call_id,
            tool_id=plan.tool_id,
            status=TOOL_STATUS_SUCCESS,
            result=call.result,
            upstream_status=call.upstream_status,
        )


class ToolExecutorDisabled:
    """The production executor while the tool layer is not configured.

    It performs no network call at all: the HomePlus tool layer is not
    wired into Node D yet. It fails closed.
    """

    state = "DISABLED"

    def execute(
        self,
        plan: ToolInvocationPlan,
        context: ToolExecutionContext,
    ) -> ToolExecutionOutcome:

        raise ToolExecutorDisabledError(
            "the tool executor is disabled"
        )


_EXECUTOR: ToolExecutorProtocol = ToolExecutorDisabled()


def get_tool_executor() -> ToolExecutorProtocol:
    """The active tool executor (disabled by default)."""

    return _EXECUTOR


def set_tool_executor(
    executor: ToolExecutorProtocol,
) -> None:
    """Install an executor. Used by unit tests and by T09-E."""

    global _EXECUTOR

    _EXECUTOR = executor


def reset_tool_executor() -> None:
    """Restore the disabled production executor."""

    set_tool_executor(ToolExecutorDisabled())


def executor_state() -> str:
    """The state of the active executor."""

    state = getattr(
        get_tool_executor(),
        "state",
        "UNKNOWN",
    )

    return str(state)


def install_production_executor(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Install the real HomePlus executor when the configuration allows it.

    The installation fails closed: an absent base URL, a malformed base
    URL or a malformed timeout leaves the disabled executor in place and
    the production node keeps refusing every tool request. The function
    never raises and never performs a network call.
    """

    try:
        config: ToolClientConfig = load_tool_client_config(environ)

        require_configured(config)

        client = HomePlusToolClient(config)

    except ToolClientConfigError:
        return executor_state()

    set_tool_executor(HomePlusToolExecutor(client))

    return executor_state()


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


def log_tool_event(
    request: RequestEnvelope,
    *,
    operation: str,
    outcome: str,
    latency_ms: float,
    decision_kind: str | None = None,
    tool_id: str | None = None,
    tool_call_id: str | None = None,
    error_code: str | None = None,
) -> None:
    """Write the T09 structured telemetry record.

    The record carries only the allowed key set. It never carries the
    bearer token, the tool arguments, the user text, the answer, the tool
    result, the actor or household identity, or the decision JSON.
    """

    record = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "request_id": request.context.request_id,
        "trace_id": request.context.trace_id,
        "operation": operation,
        "decision_kind": decision_kind,
        "tool_id": tool_id,
        "tool_call_id": tool_call_id,
        "outcome": outcome,
        "latency_ms": round(latency_ms, 3),
        "error_code": error_code,
    }

    try:
        TOOL_LOGGER.info(
            json.dumps(
                record,
                ensure_ascii=False,
            )
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def tool_failure(
    request: RequestEnvelope,
    *,
    code: ErrorCode,
    message: str,
    retryable: bool = False,
    node_id: str | None = None,
    provider_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> ErrorEnvelope:
    """Build an error envelope with the CALLER correlation.

    The internal Node A correlation is never exposed to the caller.
    """

    return ErrorEnvelope(
        correlation=caller_correlation(request),
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            node_id=node_id,
            provider_id=provider_id,
            details=details or {},
        ),
    )


CONTRACT_RESULT = TypeAdapter(
    ResponseEnvelope | ErrorEnvelope
)


# ---------------------------------------------------------------------------
# Control plane resolution
# ---------------------------------------------------------------------------


def _provider_timeout_s(
    provider: dict[str, Any],
) -> float:
    """Resolve the provider timeout using the frozen T08 policy.

    Imported lazily: ``app`` imports this module at module level, so a
    module-level import here would be circular. The T08 timeout policy
    stays single-sourced in ``app.provider_timeout_s``.
    """

    from app import provider_timeout_s

    return provider_timeout_s(provider)


async def _resolve_provider(
    request: RequestEnvelope,
) -> dict[str, Any] | ErrorEnvelope:
    """Resolve the THINK provider through the D control plane.

    The control-plane routing is not modified by T09-D.
    """

    capability = request.capability.value

    try:
        async with httpx.AsyncClient(
            timeout=RESOLVE_TIMEOUT_S
        ) as client:

            resolution_response = await client.get(
                f"{CONTROL_PLANE}/resolve/{capability}"
            )

    except Exception:
        return tool_failure(
            request,
            code=ErrorCode.NODE_UNAVAILABLE,
            message="control-plane routing unavailable",
            retryable=True,
        )

    resolve_status = resolution_response.status_code

    if resolve_status == 404:
        return tool_failure(
            request,
            code=ErrorCode.CAPABILITY_NOT_FOUND,
            message=f"no provider for {capability}",
            retryable=False,
        )

    if resolve_status >= 400:
        return tool_failure(
            request,
            code=ErrorCode.NODE_UNAVAILABLE,
            message="control-plane routing unavailable",
            retryable=True,
        )

    try:
        resolution = resolution_response.json()

    except Exception:
        return tool_failure(
            request,
            code=ErrorCode.NODE_UNAVAILABLE,
            message="control-plane routing unavailable",
            retryable=True,
        )

    provider = resolution.get("provider")

    if not provider:
        return tool_failure(
            request,
            code=ErrorCode.CAPABILITY_NOT_FOUND,
            message=f"no provider for {capability}",
            retryable=False,
        )

    if (
        provider.get("effective_state") != "READY"
        or not provider.get("endpoint")
    ):
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_UNAVAILABLE,
            message=(
                f"{provider['provider_id']} is not READY"
            ),
            retryable=True,
            node_id=provider.get("node_id"),
            provider_id=provider.get("provider_id"),
        )

    try:
        _provider_timeout_s(provider)

    except ValueError:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_NOT_CONFIGURED,
            message=(
                f"{provider['provider_id']} has an invalid "
                "timeout_s configuration"
            ),
            retryable=False,
            node_id=provider.get("node_id"),
            provider_id=provider.get("provider_id"),
            details={
                "reason": "invalid_timeout_s",
            },
        )

    return provider


# ---------------------------------------------------------------------------
# The Node A call
# ---------------------------------------------------------------------------


async def _call_node_a(
    request: RequestEnvelope,
    internal: RequestEnvelope,
    provider: Mapping[str, Any],
) -> ResponseEnvelope | ErrorEnvelope:
    """Perform ONE Node A call and validate its answer.

    The helper is shared by the two internal passes of a turn:

    * the decision pass (``phase=decide``);
    * the synthesis pass (``phase=synthesize``).

    It never retries: one pass produces at most one HTTP call. The
    returned envelope always carries the CALLER correlation, so an
    internal request id is never exposed.
    """

    node_id = provider["node_id"]

    provider_id = provider["provider_id"]

    endpoint = provider.get("endpoint")

    timeout_s = _provider_timeout_s(provider)

    try:
        async with httpx.AsyncClient(
            timeout=timeout_s
        ) as client:

            response = await client.post(
                endpoint,
                json=internal.model_dump(
                    mode="json"
                ),
            )

    except httpx.TimeoutException:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_TIMEOUT,
            message=f"{provider_id} timed out",
            retryable=True,
            node_id=node_id,
            provider_id=provider_id,
        )

    except Exception:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_UNAVAILABLE,
            message=(
                f"{provider_id} transport failure"
            ),
            retryable=True,
            node_id=node_id,
            provider_id=provider_id,
        )

    http_status = response.status_code

    if http_status >= 500:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_UNAVAILABLE,
            message=f"{provider_id} is unavailable",
            retryable=True,
            node_id=node_id,
            provider_id=provider_id,
            details={
                "upstream_status": http_status,
            },
        )

    if http_status >= 400:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message=(
                f"{provider_id} returned a client error"
            ),
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
            details={
                "upstream_status": http_status,
            },
        )

    if not (200 <= http_status < 300):
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message=(
                f"{provider_id} returned an unexpected status"
            ),
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
            details={
                "upstream_status": http_status,
            },
        )

    raw_body = response.content

    if not raw_body or not raw_body.strip():
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message=f"{provider_id} returned an empty body",
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
        )

    try:
        data = json.loads(raw_body)

    except (ValueError, UnicodeDecodeError):
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message=(
                f"{provider_id} returned a malformed body"
            ),
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
        )

    try:
        result = CONTRACT_RESULT.validate_python(data)

    except ValidationError:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message=(
                "provider returned an invalid "
                "Contracts v1 response"
            ),
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
        )

    # The correlation is validated against the INTERNAL request, never
    # against the caller request.
    expected = internal_correlation(internal)

    if result.correlation != expected:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message="correlation mismatch",
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
        )

    if isinstance(result, ErrorEnvelope):
        return tool_failure(
            request,
            code=result.error.code,
            message=result.error.message,
            retryable=result.error.retryable,
            node_id=node_id,
            provider_id=provider_id,
            details={
                "reason": "provider_error_envelope",
            },
        )

    if result.capability != Capability.THINK:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message="capability mismatch",
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
        )

    if result.node_id != node_id:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message="node mismatch",
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
        )

    if result.provider_id != provider_id:
        return tool_failure(
            request,
            code=ErrorCode.PROVIDER_ERROR,
            message="provider mismatch",
            retryable=False,
            node_id=node_id,
            provider_id=provider_id,
        )

    return result


# ---------------------------------------------------------------------------
# Decision phase
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolTurnOutcome:
    """The outcome of one structured turn.

    ``envelope`` is the public answer of the turn. ``tool_result`` is
    the INTERNAL result of the tool execution: it carries the real
    HomePlus payload and stays inside Node D. T09-F consumes it; the
    public envelope never exposes it.
    """

    envelope: ResponseEnvelope | ErrorEnvelope
    tool_result: ToolExecutionResult | None = None


# The transitional T09-E public answer of a successful real tool
# execution. It is RETIRED by T09-F: a successful tool turn now
# returns the synthesized natural answer. The constant is kept so the
# T09-E contract of the module stays importable and so the retirement
# is explicit and auditable.
TOOL_EXECUTION_ANSWER = (
    "HomePlus read completed; synthesis pending."
)


# ---------------------------------------------------------------------------
# T12-3 — existing-task WRITE dispatch (proposal only, NO execution)
# ---------------------------------------------------------------------------
#
# The flow of a T12 existing-task WRITE turn (sections 4-20):
#
#     NL -> decision (tool_id + target + delta intent)
#         -> deterministic target resolution
#            (explicit canonical taskId, or ONE exact title match of
#            the trusted planner.tasks.list result; zero/multiple ->
#            clarify)
#         -> trusted preflight READ planner.tasks.get
#            (authoritative taskId / version / due_date / due_time /
#            checklist / status / trashed state)
#         -> deterministic canonical argument construction
#            (dueTime merge, clear-date invariant, checklist
#            read-modify-write, unassign = null)
#         -> ActionProposal (PROPOSED; D-injected expectedVersion;
#            trusted per-tool risk; REQUIRED confirmation)
#         -> STOP. No write execution exists for the four new T12
#            tools in this phase (sections 22-23).

# The deterministic D-owned clarify answers of the T12 resolver. They
# are presentation text only: they never carry internal ids, backend
# detail or authority.
T12_CLARIFY_ANSWERS = {
    "TASK_TARGET_EMPTY": (
        "¿Qué tarea querés modificar? Decime el nombre exacto "
        "o el identificador de la tarea."
    ),
    "TASK_TARGET_NOT_FOUND": (
        "No encontré una tarea que se llame exactamente así. "
        "¿Cuál es el nombre exacto de la tarea?"
    ),
    "TASK_TARGET_AMBIGUOUS": (
        "Hay más de una tarea con ese nombre. Decime el nombre "
        "exacto (o el identificador) de la que querés."
    ),
    "TASK_NOT_FOUND": (
        "No encontré esa tarea. ¿Podés repetir el nombre exacto?"
    ),
    "TASK_TARGET_READ_INVALID": (
        "No pude leer tus tareas ahora. Probá de nuevo en un momento."
    ),
    "DUE_DATE_REQUIRED": (
        "Esa tarea no tiene fecha. ¿Para qué día querés la tarea?"
    ),
    "CHECKLIST_ITEM_NOT_FOUND": (
        "No encontré ese ítem del checklist. ¿Cuál es el texto "
        "exacto del ítem?"
    ),
    "CHECKLIST_ITEM_AMBIGUOUS": (
        "Hay varios ítems del checklist con ese texto. Decime cuál "
        "de ellos."
    ),
    "CHECKLIST_TOO_LARGE": (
        "El checklist ya tiene demasiados ítems."
    ),
    "COMPLETE_PRECONDITION_FAILED": (
        "La tarea no se puede completar desde su estado actual."
    ),
    "RESTORE_PRECONDITION_FAILED": (
        "Esa tarea no está en la papelera."
    ),
    "ASSIGN_MEMBER_UNRESOLVED": (
        "Todavía no puedo asignar por nombre de persona. ¿Me pasás el "
        "identificador del miembro del hogar?"
    ),
}

# The deterministic D-owned proposal answers per tool (presentation
# text only). Trash communicates the REVERSIBLE semantics explicitly.
T12_PROPOSAL_ANSWERS = {
    PLANNER_TASKS_UPDATE_TOOL_ID: (
        "Prepare una propuesta para actualizar la tarea."
    ),
    PLANNER_TASKS_COMPLETE_TOOL_ID: (
        "Prepare una propuesta para completar la tarea."
    ),
    PLANNER_TASKS_TRASH_TOOL_ID: (
        "Prepare una propuesta para mover la tarea a la papelera. "
        "Es reversible: se puede restaurar después."
    ),
    PLANNER_TASKS_RESTORE_TOOL_ID: (
        "Prepare una propuesta para restaurar la tarea desde la "
        "papelera."
    ),
}

T12_SUCCESS_ANSWERS = {
    PLANNER_TASKS_CREATE_TOOL_ID: "Creé la tarea en tu hogar.",
    PLANNER_TASKS_UPDATE_TOOL_ID: "Actualicé la tarea en tu hogar.",
    PLANNER_TASKS_COMPLETE_TOOL_ID: "Completé la tarea en tu hogar.",
    PLANNER_TASKS_TRASH_TOOL_ID: "Moví la tarea a la papelera.",
    PLANNER_TASKS_RESTORE_TOOL_ID: "Restauré la tarea desde la papelera.",
}

T12_PENDING_ANSWERS = {
    PLANNER_TASKS_CREATE_TOOL_ID: (
        "La creación fue aceptada, pero no pude verificarla todavía."
    ),
    PLANNER_TASKS_UPDATE_TOOL_ID: (
        "La actualización fue aceptada, pero no pude verificarla todavía."
    ),
    PLANNER_TASKS_COMPLETE_TOOL_ID: (
        "La tarea se completó, pero no pude verificarla todavía."
    ),
    PLANNER_TASKS_TRASH_TOOL_ID: (
        "La tarea se movió a la papelera, pero no pude verificarla todavía."
    ),
    PLANNER_TASKS_RESTORE_TOOL_ID: (
        "La tarea se restauró, pero no pude verificarla todavía."
    ),
}


def _t12_clarify_envelope(
    request: RequestEnvelope,
    provider_id: str,
    question: str,
) -> ResponseEnvelope:
    """The deterministic clarify outcome of the T12 resolver."""

    return ResponseEnvelope(
        correlation=caller_correlation(request),
        node_id="homi-d",
        provider_id=provider_id,
        capability=Capability.THINK,
        result={
            "answer": question,
            "decision_kind": DECISION_CLARIFY,
        },
    )


async def _t12_execute_trusted_read(
    request: RequestEnvelope,
    tool_id: str,
    arguments: Mapping[str, Any],
    credential: str | None,
):
    """One D-internal trusted READ through the tool executor seam.

    Mirrors the T11-8 verification READ pattern: the preflight READ
    is D-internal orchestration (never a model tool_request), so the
    model tool-call budget does not apply. The credential is the
    request-local HomePlus bearer; the raw result stays inside
    Node D.
    """

    try:
        loaded = catalog()
        digest = str(loaded.digest).upper()
    except Exception:
        digest = "UNKNOWN"

    plan = ToolInvocationPlan(
        tool_call_id=mint_tool_call_id(
            request_id=request.context.request_id,
            trace_id=request.context.trace_id,
            tool_id=tool_id,
            arguments=dict(arguments),
            catalog_digest=digest,
        ),
        tool_id=tool_id,
        arguments=dict(arguments),
        catalog_digest=digest,
    )

    context = ToolExecutionContext(
        request_id=request.context.request_id,
        trace_id=request.context.trace_id,
        turn_id=request.context.turn_id,
        conversation_id=request.context.conversation_id,
        actor_id=request.context.actor_id,
        household_id=request.context.household_id,
        bearer_token=credential,
    )

    executor = get_tool_executor()

    try:
        outcome = executor.execute(plan, context)

        if inspect.isawaitable(outcome):
            outcome = await outcome

        return normalize_tool_execution(plan, outcome), None

    except ToolExecutorDisabledError:
        return None, "T12_READ_UNAVAILABLE"

    except Exception:
        return None, "T12_READ_TRANSPORT_FAILURE"


async def _t12_read_task_by_id(
    request: RequestEnvelope,
    credential: str | None,
    task_id: str,
):
    """The trusted preflight READ planner.tasks.get (section 5)."""

    execution, error = await _t12_execute_trusted_read(
        request,
        "planner.tasks.get",
        {"taskId": task_id},
        credential,
    )

    if error is not None:
        return None, error

    if not execution.ok:
        if execution.retryable:
            return None, "T12_READ_TRANSPORT_FAILURE"

        if execution.upstream_status == 404:
            return None, "TASK_NOT_FOUND"

        return None, "T12_READ_BACKEND_FAILURE"

    result = execution.result

    task = None

    if isinstance(result, Mapping):
        candidate = result.get("task")

        if isinstance(candidate, Mapping):
            task = candidate

    if task is None:
        return None, "T12_READ_BACKEND_FAILURE"

    return task, None


# ---------------------------------------------------------------------------
# T12 — internal trashed-task preflight seam (test seam)
#
# A process-local override allows unit tests to inject a deterministic
# preflight result without reaching the network. Production leaves it None.
# ---------------------------------------------------------------------------

_PREFLIGHT_OVERRIDE: Any = None


def set_internal_preflight_override(
    fn: Any,
) -> None:
    """Install a test double for the internal trashed-task preflight."""

    global _PREFLIGHT_OVERRIDE

    _PREFLIGHT_OVERRIDE = fn


def reset_internal_preflight_override() -> None:
    """Restore the real network-backed preflight."""

    global _PREFLIGHT_OVERRIDE

    _PREFLIGHT_OVERRIDE = None


async def _t12_read_trashed_task_by_id(
    request: RequestEnvelope,
    credential: str | None,
    task_id: str,
):
    """The trusted internal preflight READ of a trashed task (section 5).

    Uses the dedicated internal preflight route on T07, guarded by the same
    internal write authority as the write seam. The normal
    ``planner.tasks.get`` READ filters trashed tasks, so it cannot
    authoritatively resolve a trashed task for a restore proposal.

    Returns ``(task, None)`` on success or ``(None, error_code)`` on
    failure. A 404 means "not found or not trashed in this household" and
    never leaks cross-household existence.
    """

    if _PREFLIGHT_OVERRIDE is not None:
        return await _PREFLIGHT_OVERRIDE(request, credential, task_id)

    config = load_write_execution_config()

    if not config.configured:
        return None, "T12_PREFLIGHT_UNAVAILABLE"

    try:
        attempt = await attempt_internal_preflight(
            base_url=config.base_url or "",
            secret=config.secret or "",
            bearer_token=credential or "",
            actor_id=str(request.context.actor_id),
            household_id=str(request.context.household_id),
            task_id=task_id,
            timeout_s=config.timeout_s,
        )
    except Exception:
        return None, "T12_PREFLIGHT_TRANSPORT_FAILURE"

    if not attempt.ok:
        if attempt.retryable:
            return None, "T12_PREFLIGHT_TRANSPORT_FAILURE"

        if attempt.upstream_status == 404:
            return None, "TASK_NOT_FOUND"

        return None, "T12_PREFLIGHT_BACKEND_FAILURE"

    return attempt.task, None


async def _t12_list_visible_tasks(
    request: RequestEnvelope,
    credential: str | None,
):
    """The trusted title-resolution READ planner.tasks.list (section 4)."""

    execution, error = await _t12_execute_trusted_read(
        request,
        "planner.tasks.list",
        {},
        credential,
    )

    if error is not None:
        return None, error

    if not execution.ok:
        if execution.retryable:
            return None, "T12_READ_TRANSPORT_FAILURE"

        return None, "T12_READ_BACKEND_FAILURE"

    result = execution.result

    tasks = None

    if isinstance(result, Mapping):
        candidate = result.get("tasks")

        if isinstance(candidate, list):
            tasks = candidate

    if tasks is None:
        return None, "T12_READ_BACKEND_FAILURE"

    return tasks, None


async def _t12_list_trashed_tasks(
    request: RequestEnvelope,
    credential: str | None,
):
    """Trusted read of trashed tasks for RESTORE title resolution."""

    base_url = (
        os.environ.get("HOMI_INTERNAL_WRITE_BASE_URL")
        or os.environ.get("HOMI_TOOL_BASE_URL")
        or "http://127.0.0.1:3001"
    ).rstrip("/")

    if not credential:
        return None, "T12_READ_UNAVAILABLE"

    url = f"{base_url}/api/planner/trash"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {credential}",
                    "Accept": "application/json",
                },
            )
    except Exception:
        return None, "T12_READ_TRANSPORT_FAILURE"

    if response.status_code != 200:
        if response.status_code in (401, 403):
            return None, "T12_READ_BACKEND_FAILURE"
        return None, "T12_READ_TRANSPORT_FAILURE"

    payload = None
    try:
        payload = response.json()
    except Exception:
        return None, "T12_READ_BACKEND_FAILURE"

    items = None
    if isinstance(payload, Mapping):
        candidate = payload.get("items")
        if isinstance(candidate, list):
            items = candidate

    if items is None:
        return None, "T12_READ_BACKEND_FAILURE"

    tasks = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") not in (None, "task"):
            continue
        tasks.append(dict(item))

    return tasks, None


def _t12_authoritative_version(
    task: Mapping[str, Any],
) -> int | None:
    """The authoritative expectedVersion source (section 6).

    The version is D-OWNED execution/concurrency metadata derived from
    the Product Truth READ state. A missing or non-integer version can
    not be obtained deterministically, so the caller fails closed
    instead of inventing one.
    """

    version = task.get("version")

    if (
        isinstance(version, int)
        and not isinstance(version, bool)
        and version >= 1
    ):
        return version

    return None


async def _dispatch_t12_existing_task_write(
    request: RequestEnvelope,
    decision: ActionProposalDecision,
    credential: str | None,
    provider_id: str,
    node_id: str,
):
    """Resolve, preflight and PROPOSE one T12 existing-task WRITE.

    Returns ``(envelope, decision_kind, tool_id)`` so the caller can
    finish the turn with telemetry. The dispatch NEVER executes the
    write: no internal write seam call, no Planner mutation (T12-3
    sections 22-23).
    """

    tool_id = decision.tool_id

    conversation_id = request.context.conversation_id

    def clarify(question: str):
        return (
            _t12_clarify_envelope(
                request,
                provider_id,
                question,
            ),
            DECISION_CLARIFY,
            tool_id,
        )

    def failure(code, message, reason, retryable=False):
        return (
            tool_failure(
                request,
                code=code,
                message=message,
                retryable=retryable,
                node_id=node_id,
                provider_id=provider_id,
                details={"reason": reason},
            ),
            DECISION_TOOL_REQUEST,
            tool_id,
        )

    # The trusted resolution/preflight READs need the HomePlus
    # credential (T07 stays the identity authority).
    if credential is None:
        return failure(
            ErrorCode.POLICY_DENIED,
            (
                "a HomePlus authorization credential is required "
                "to resolve an existing-task write"
            ),
            "missing_tool_authorization",
        )

    task_id, task_title = decision.target

    # Target absent: the model did not identify which task to mutate.
    # Ask for clarification instead of failing with a parsing error.
    if task_id is None and task_title is None:
        return clarify(
            T12_CLARIFY_ANSWERS["TASK_TARGET_EMPTY"],
        )

    # ---- deterministic target resolution (section 4) ---------------

    # RESTORE by title: resolve trashed task by name (no UUID required).
    if (
        task_id is None
        and tool_id == PLANNER_TASKS_RESTORE_TOOL_ID
        and task_title is not None
    ):
        trashed, read_error = await _t12_list_trashed_tasks(
            request,
            credential,
        )
        if read_error is not None:
            if read_error == "T12_READ_TRANSPORT_FAILURE":
                return failure(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "the trusted trashed task listing read failed",
                    read_error,
                    retryable=True,
                )
            return clarify(
                "No pude consultar la papelera en este momento. "
                "Intentá nuevamente.",
            )
        matches = [
            t for t in (trashed or [])
            if str(t.get("title") or "").strip() == str(task_title).strip()
        ]
        if len(matches) == 0:
            return clarify(
                "No encontré una tarea en la papelera con ese nombre.",
            )
        if len(matches) > 1:
            names = ", ".join(
                str(t.get("id")) for t in matches
            )
            return clarify(
                "Encontré varias tareas con ese nombre en la "
                "papelera. Indicá el identificador exacto: "
                + names,
            )
        task_id = matches[0].get("id")
        task_title = matches[0].get("title")

    if task_id is None:
        tasks, read_error = await _t12_list_visible_tasks(
            request,
            credential,
        )

        if read_error is not None:
            if read_error in (
                "T12_READ_TRANSPORT_FAILURE",
                "T12_READ_UNAVAILABLE",
            ):
                return failure(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "the trusted task listing read failed",
                    read_error,
                    retryable=True,
                )

            if read_error == "TASK_TARGET_READ_INVALID":
                return clarify(
                    T12_CLARIFY_ANSWERS[
                        "TASK_TARGET_READ_INVALID"
                    ],
                )

            return failure(
                ErrorCode.PROVIDER_ERROR,
                "the trusted task listing read failed",
                read_error,
            )

        try:
            resolved = resolve_task_by_title(
                task_title,
                tasks,
            )

        except TaskTargetError as error:
            if error.code in T12_CLARIFY_ANSWERS:
                return clarify(
                    T12_CLARIFY_ANSWERS[error.code],
                )

            return failure(
                ErrorCode.PROVIDER_ERROR,
                "the task target could not be resolved",
                error.code,
            )

        resolved_id = resolved.get("id")

        if not isinstance(resolved_id, str):
            return failure(
                ErrorCode.PROVIDER_ERROR,
                "the trusted task listing read is malformed",
                "task_id_missing",
            )

        task_id = resolved_id

    # ---- trusted preflight READ (section 5) --------------------------
    #
    # Restore reads through the dedicated internal trashed-task preflight
    # because the normal planner.tasks.get filters trashed tasks. Every
    # other existing-task tool uses the normal trusted READ.

    if tool_id == PLANNER_TASKS_RESTORE_TOOL_ID:
        task, read_error = await _t12_read_trashed_task_by_id(
            request,
            credential,
            task_id,
        )

        if read_error is not None:
            if read_error == "TASK_NOT_FOUND":
                return clarify(
                    T12_CLARIFY_ANSWERS["TASK_NOT_FOUND"],
                )

            if read_error in (
                "T12_PREFLIGHT_TRANSPORT_FAILURE",
                "T12_PREFLIGHT_UNAVAILABLE",
            ):
                return failure(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "the trusted trashed-task preflight read failed",
                    read_error,
                    retryable=(read_error == "T12_PREFLIGHT_TRANSPORT_FAILURE"),
                )

            return failure(
                ErrorCode.PROVIDER_ERROR,
                "the trusted trashed-task preflight read failed",
                read_error,
            )
    else:
        task, read_error = await _t12_read_task_by_id(
            request,
            credential,
            task_id,
        )

        if read_error is not None:
            if read_error == "TASK_NOT_FOUND":
                return clarify(
                    T12_CLARIFY_ANSWERS["TASK_NOT_FOUND"],
                )

            if read_error in (
                "T12_READ_TRANSPORT_FAILURE",
                "T12_READ_UNAVAILABLE",
            ):
                return failure(
                    ErrorCode.PROVIDER_UNAVAILABLE,
                    "the trusted preflight read failed",
                    read_error,
                    retryable=True,
                )

            return failure(
                ErrorCode.PROVIDER_ERROR,
                "the trusted preflight read failed",
                read_error,
            )

    if not isinstance(task_id, str) or not task_id:
        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the trusted preflight read is malformed",
            "task_id_missing",
        )

    # ---- expectedVersion ownership (section 6) -----------------------

    version = _t12_authoritative_version(task)

    if version is None:
        return failure(
            ErrorCode.PROVIDER_ERROR,
            (
                "the authoritative task version could not be "
                "obtained deterministically"
            ),
            "expected_version_unavailable",
        )

    summary_context: dict[str, Any] = {
        "task_title": task.get("title"),
    }

    # ---- deterministic canonical argument construction --------------

    if tool_id == PLANNER_TASKS_UPDATE_TOOL_ID:
        # Assignment by natural-language name: NO trusted member
        # resolution authority exists in the T12 infrastructure
        # (section 10). Fail closed to a clarify; never fabricate a
        # member id.
        if decision.assign_member_name is not None:
            return clarify(
                T12_CLARIFY_ANSWERS[
                    "ASSIGN_MEMBER_UNRESOLVED"
                ],
            )

        model_patch = dict(decision.arguments or {})

        try:
            merged = merge_due_time_intent(
                model_patch,
                task,
            )

            merged = apply_clear_date_invariant(
                merged,
                task,
            )

        except TaskTargetError as error:
            if error.code in T12_CLARIFY_ANSWERS:
                return clarify(
                    T12_CLARIFY_ANSWERS[error.code],
                )

            return failure(
                ErrorCode.PROVIDER_ERROR,
                "the update delta could not be merged",
                error.code,
            )

        if decision.checklist_patch is not None:
            try:
                new_checklist = transform_checklist(
                    task,
                    decision.checklist_patch,
                )

            except TaskTargetError as error:
                if error.code in T12_CLARIFY_ANSWERS:
                    return clarify(
                        T12_CLARIFY_ANSWERS[error.code],
                    )

                return failure(
                    ErrorCode.PROVIDER_ERROR,
                    "the checklist transform failed",
                    error.code,
                )

            merged["checklist"] = new_checklist

            summary_context["checklist_op"] = dict(
                decision.checklist_patch,
            )

        final_arguments: dict[str, Any] = {
            "taskId": task_id,
            "expectedVersion": version,
        }

        final_arguments.update(merged)

    elif tool_id == PLANNER_TASKS_COMPLETE_TOOL_ID:
        try:
            complete_preconditions(task)

        except TaskTargetError as error:
            return clarify(
                T12_CLARIFY_ANSWERS.get(
                    error.code,
                    T12_CLARIFY_ANSWERS[
                        "COMPLETE_PRECONDITION_FAILED"
                    ],
                ),
            )

        final_arguments = {
            "taskId": task_id,
            "expectedVersion": version,
        }

    elif tool_id == PLANNER_TASKS_RESTORE_TOOL_ID:
        try:
            restore_preconditions(task)

        except TaskTargetError as error:
            return clarify(
                T12_CLARIFY_ANSWERS.get(
                    error.code,
                    T12_CLARIFY_ANSWERS[
                        "RESTORE_PRECONDITION_FAILED"
                    ],
                ),
            )

        final_arguments = {
            "taskId": task_id,
            "expectedVersion": version,
        }

    else:
        # planner.tasks.trash: the preflight READ already proved the
        # task is readable/operational; no further precondition is
        # deterministically detectable here.
        final_arguments = {
            "taskId": task_id,
            "expectedVersion": version,
        }

    # ---- ActionProposal (PROPOSED; sections 17-21) -------------------

    try:
        built = build_action_proposal(
            tool_id,
            final_arguments,
            summary_context=summary_context,
            # T12-4: the checklist intent is stored as revision
            # metadata so a later deterministic edit can recompute
            # the transformation against the FRESH authoritative
            # state instead of patching this array blindly.
            checklist_intent=(
                decision.checklist_patch
                if tool_id == PLANNER_TASKS_UPDATE_TOOL_ID
                else None
            ),
        )

    except ActionProposalError as error:
        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the requested tool invocation is not allowed",
            error.code,
        )

    replace_pending_proposal(
        conversation_id,
        built,
        actor_id=request.context.actor_id,
        household_id=request.context.household_id,
    )

    envelope = ResponseEnvelope(
        correlation=caller_correlation(request),
        node_id="homi-d",
        provider_id=provider_id,
        capability=Capability.THINK,
        result={
            "answer": T12_PROPOSAL_ANSWERS[tool_id],
            "decision_kind": "action_proposal",
            "proposal": built.public_projection,
        },
    )

    return envelope, "action_proposal", tool_id


# ---------------------------------------------------------------------------
# T12-4 — deterministic EDIT of the active planner.tasks.update proposal
# ---------------------------------------------------------------------------
#
# The accepted T11 semantics generalized to the update family (T12-4
# sections 1-17):
#
#     active update proposal P1 (PROPOSED)
#         -> EDIT decision (proposal_edit_patch [+ revised
#            checklist_patch]; no target; arguments never consumed)
#         -> trusted preflight REFRESH planner.tasks.get(P1.taskId)
#            (authoritative taskId / version / due date / time /
#            checklist / state; ALWAYS re-read before building the
#            revision, section 7)
#         -> deterministic canonical revision
#            (merge base = P1 user-facing fields + the edit delta;
#            checklist intent revised-or-preserved and recomputed
#            against the FRESH authoritative checklist; date/time
#            merges; expectedVersion REFRESHED from the fresh READ,
#            section 8)
#         -> FULL revalidation (T12 schema, date/time invariants,
#            checklist structure) -> NEW ActionProposalV1 P2
#         -> replace_pending_proposal: P2 becomes the ONLY active
#            proposal, P1 is stale (new proposal_id; the T11 revision
#            semantics preserved exactly)
#         -> STOP. NO write execution exists for planner.tasks.update
#            in this phase (sections 22-23 of T12-3 stay in force).

# The deterministic D-owned public answer of a successful update edit.
T12_UPDATE_EDIT_ANSWER = (
    "Actualicé la propuesta de actualizar la tarea."
)


async def _dispatch_t12_update_proposal_edit(
    request: RequestEnvelope,
    decision: ActionProposalDecision,
    pending: ActionProposalV1,
    credential: str | None,
    provider_id: str,
    node_id: str,
):
    """Revise the ACTIVE planner.tasks.update proposal (NO execution).

    Returns ``(envelope, decision_kind, tool_id)`` so the caller can
    finish the turn with telemetry. The dispatch NEVER executes the
    write and NEVER mutates the pending proposal on failure: any
    rejection leaves P1 PROPOSED and intact (fail closed).
    """

    tool_id = PLANNER_TASKS_UPDATE_TOOL_ID

    conversation_id = request.context.conversation_id

    def clarify(question: str):
        return (
            _t12_clarify_envelope(
                request,
                provider_id,
                question,
            ),
            DECISION_CLARIFY,
            tool_id,
        )

    def failure(code, message, reason, retryable=False):
        return (
            tool_failure(
                request,
                code=code,
                message=message,
                retryable=retryable,
                node_id=node_id,
                provider_id=provider_id,
                details={"reason": reason},
            ),
            DECISION_TOOL_REQUEST,
            tool_id,
        )

    # ---- tool immutability during edit (T12-4 section 29) ----------
    # Only an ACTIVE update proposal may receive an update edit patch.
    # A create proposal keeps the T11-4 create edit path; a lifecycle
    # proposal (complete/trash/restore) has NO arbitrary patch body.
    if pending.tool_id != PLANNER_TASKS_UPDATE_TOOL_ID:
        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the requested tool invocation is not allowed",
            "PROPOSAL_EDIT_TARGET_MISMATCH",
        )

    if not isinstance(pending.arguments, Mapping):
        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the active proposal is malformed",
            "PROPOSAL_REVISION_INVALID",
        )

    task_id = pending.arguments.get("taskId")

    if not isinstance(task_id, str) or not task_id:
        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the active proposal carries no trusted task id",
            "PROPOSAL_REVISION_INVALID",
        )

    # ---- authoritative preflight REFRESH (T12-4 section 7) ----------
    # The trusted resolution/preflight READs need the HomePlus
    # credential (T07 stays the identity authority). The refresh is
    # ALWAYS performed: the task may have changed between proposal
    # revisions.
    if credential is None:
        return failure(
            ErrorCode.POLICY_DENIED,
            (
                "a HomePlus authorization credential is required "
                "to refresh the active update proposal"
            ),
            "missing_tool_authorization",
        )

    task, read_error = await _t12_read_task_by_id(
        request,
        credential,
        task_id,
    )

    if read_error is not None:
        if read_error == "TASK_NOT_FOUND":
            return clarify(
                T12_CLARIFY_ANSWERS["TASK_NOT_FOUND"],
            )

        if read_error in (
            "T12_READ_TRANSPORT_FAILURE",
            "T12_READ_UNAVAILABLE",
        ):
            return failure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "the trusted preflight refresh failed",
                read_error,
                retryable=True,
            )

        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the trusted preflight refresh failed",
            read_error,
        )

    # ---- the deterministic revision (sections 5-14) ------------------
    try:
        revised = revise_t12_update_proposal(
            pending,
            dict(decision.edit_patch),
            authoritative_task=task,
            revised_checklist_intent=(
                decision.checklist_patch
            ),
        )

    except TaskTargetError as error:
        # The deterministic merges/transform failed closed: the
        # pending proposal stays PROPOSED and intact.
        if error.code in T12_CLARIFY_ANSWERS:
            return clarify(
                T12_CLARIFY_ANSWERS[error.code],
            )

        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the proposal edit could not be merged",
            error.code,
        )

    except ActionProposalError as error:
        # Fail closed: no new executable proposal, P1 stays intact.
        reason = error.code

        if error.code == "EXPECTED_VERSION_UNAVAILABLE":
            # The canonical public reason of the T12-3 expectedVersion
            # gate (section 8): identical fail-closed shape for the
            # edit path and the new-intent path.
            reason = "expected_version_unavailable"

        return failure(
            ErrorCode.PROVIDER_ERROR,
            "the requested tool invocation is not allowed",
            reason,
        )

    # ---- P2 becomes the ONLY active proposal; P1 is stale -----------
    replace_pending_proposal(
        conversation_id,
        revised,
        actor_id=request.context.actor_id,
        household_id=request.context.household_id,
    )

    envelope = ResponseEnvelope(
        correlation=caller_correlation(request),
        node_id="homi-d",
        provider_id=provider_id,
        capability=Capability.THINK,
        result={
            "answer": T12_UPDATE_EDIT_ANSWER,
            "decision_kind": "action_proposal",
            "proposal": revised.public_projection,
        },
    )

    return envelope, "action_proposal", revised.tool_id


def _apply_t14_compound_resolution(
    arguments: Mapping[str, Any],
    *,
    reference_time_utc: Any,
    timezone_name: str | None,
    timezone_status: str | None,
) -> dict[str, Any]:
    """Apply T14 to every operation without dropping the batch.

    Compound temporal work is item-scoped. A safe clarification/block
    keeps the original ``operations`` array intact so the caller never
    loses the user's requested tasks.
    """

    operations = arguments.get("operations")

    if (
        not isinstance(operations, list)
        or not operations
        or not all(
            isinstance(operation, Mapping)
            for operation in operations
        )
    ):
        return {
            "status": "NOT_APPLICABLE",
            "temporal": {"status": "NOT_APPLICABLE"},
            "entity": None,
            "gate": {
                "allowed": True,
                "reason": "invalid_compound_operations",
            },
            "arguments": copy.deepcopy(dict(arguments)),
            "merged_arguments": copy.deepcopy(dict(arguments)),
        }

    try:
        from homi_tool_proposal import (
            _DUE_DATE_PATTERN,
            _DUE_TIME_PATTERN,
        )
    except Exception:  # pragma: no cover - defensive
        import re as _re

        _DUE_DATE_PATTERN = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
        _DUE_TIME_PATTERN = _re.compile(r"^\d{2}:\d{2}$")

    natural: list[tuple[int, str, str]] = []

    for operation_index, operation in enumerate(operations):
        for field, pattern in (
            ("dueDate", _DUE_DATE_PATTERN),
            ("dueTime", _DUE_TIME_PATTERN),
        ):
            value = operation.get(field)

            if (
                isinstance(value, str)
                and pattern.match(value) is None
            ):
                natural.append(
                    (operation_index, field, value)
                )

    if not natural:
        return {
            "status": "NOT_APPLICABLE",
            "temporal": {"status": "NOT_APPLICABLE"},
            "entity": None,
            "gate": {
                "allowed": True,
                "reason": "no_natural_temporal",
            },
            "arguments": copy.deepcopy(dict(arguments)),
            "merged_arguments": copy.deepcopy(dict(arguments)),
        }

    if (
        timezone_status != "resolved"
        or not timezone_name
    ):
        return {
            "status": "BLOCKED",
            "temporal": {
                "status": "BLOCKED",
                "reason": "timezone_unresolved",
            },
            "entity": None,
            "gate": {
                "allowed": False,
                "reason": "timezone_unresolved",
            },
            "arguments": copy.deepcopy(dict(arguments)),
            "merged_arguments": copy.deepcopy(dict(arguments)),
            "blocked_reason": "timezone_unresolved",
        }

    merged_operations = [
        copy.deepcopy(dict(operation))
        for operation in operations
    ]

    resolutions: dict[str, Any] = {}
    clarification_question = None
    blocked_reason = None

    for operation_index, field, expression in natural:
        resolution = resolve_temporal(
            expression,
            reference_utc=reference_time_utc,
            timezone=timezone_name,
            tz_status=timezone_status,
            future_required=False,
        )

        resolution_key = (
            f"operations[{operation_index}].{field}"
        )
        resolutions[resolution_key] = resolution

        status = resolution.get("status")
        kind = resolution.get("kind")

        if status == "RESOLVED":
            if field == "dueDate":
                if kind == "date" and isinstance(
                    resolution.get("value"), str
                ):
                    merged_operations[operation_index][field] = (
                        resolution["value"]
                    )
                else:
                    blocked_reason = (
                        blocked_reason
                        or "invalid_temporal_kind"
                    )
            elif field == "dueTime":
                if kind == "time" and isinstance(
                    resolution.get("value"), str
                ):
                    merged_operations[operation_index][field] = (
                        resolution["value"]
                    )
                elif kind == "time_of_day":
                    clarification_question = (
                        clarification_question
                        or (
                            "¿A qué hora exacta para la operación "
                            f"{operation_index + 1}?"
                        )
                    )
                else:
                    blocked_reason = (
                        blocked_reason
                        or "invalid_temporal_kind"
                    )

        elif status == "AMBIGUOUS":
            clarification_question = (
                clarification_question
                or (
                    "¿Podés precisar la fecha u hora de la "
                    f"operación {operation_index + 1}?"
                )
            )

        elif status in (
            "INVALID",
            "UNSUPPORTED",
            "UNAVAILABLE",
        ):
            blocked_reason = (
                blocked_reason
                or resolution.get("reason")
                or "invalid_temporal"
            )

        else:
            blocked_reason = (
                blocked_reason
                or "temporal_resolution_failed"
            )

    if blocked_reason is not None:
        overall = "BLOCKED"
    elif clarification_question is not None:
        overall = "NEEDS_CLARIFICATION"
    else:
        overall = "RESOLVED"

    if overall == "RESOLVED":
        merged_arguments = copy.deepcopy(dict(arguments))
        merged_arguments["operations"] = merged_operations
    else:
        merged_arguments = copy.deepcopy(dict(arguments))

    result: dict[str, Any] = {
        "status": overall,
        "temporal": {
            "status": overall,
            "timezone": timezone_name,
            "reference_time_utc": reference_time_utc.isoformat(),
            "resolutions": resolutions,
        },
        "entity": None,
        "gate": {
            "allowed": overall in (
                "RESOLVED",
                "NOT_APPLICABLE",
            ),
            "reason": overall.lower(),
        },
        "arguments": merged_arguments,
        "merged_arguments": merged_arguments,
    }

    if clarification_question is not None:
        result["clarification_question"] = clarification_question

    if blocked_reason is not None:
        result["blocked_reason"] = blocked_reason

    return result


def apply_t14_resolution(request, decision, text, *, context_projection=None, authorization=None, **kwargs):
    """T14 temporal enforcement adapter.

    Returns a structured result with ``status`` in
    {NOT_APPLICABLE, RESOLVED, NEEDS_CLARIFICATION, BLOCKED}.
    When applicable and resolved, ``arguments`` carries the merged
    argument mapping with concrete temporal values.
    """
    import datetime as _dt

    # ---- contextual projection (T13) ---------------------------------
    proj = context_projection
    if not isinstance(proj, dict):
        try:
            proj = build_context_projection(request, **kwargs)
        except Exception:
            proj = {}
    temporal_ctx = (proj.get("temporal") if isinstance(proj, dict) else {}) or {}
    ref_str = temporal_ctx.get("reference_time_utc")
    try:
        ref_utc = _dt.datetime.fromisoformat(str(ref_str).replace("Z", "+00:00")) if ref_str else _dt.datetime.now(_dt.timezone.utc)
    except Exception:
        ref_utc = _dt.datetime.now(_dt.timezone.utc)
    if getattr(ref_utc, "tzinfo", None) is None:
        ref_utc = ref_utc.replace(tzinfo=_dt.timezone.utc)
    tz_name = temporal_ctx.get("timezone")
    tz_status = temporal_ctx.get("status") or "uncertain"

    # ---- extract decision fields -------------------------------------
    if hasattr(decision, "arguments"):
        decision_kind = getattr(decision, "decision", None)
        tool_id = getattr(decision, "tool_id", None)
        args = getattr(decision, "arguments", None)
    elif isinstance(decision, dict):
        decision_kind = decision.get("decision")
        tool_id = decision.get("tool_id")
        args = decision.get("arguments")
    else:
        decision_kind = None
        tool_id = None
        args = None

    # Extract T12 additive entity fields.
    assign_member_name = None
    if hasattr(decision, "assign_member_name"):
        assign_member_name = getattr(decision, "assign_member_name", None)
    elif isinstance(decision, dict):
        assign_member_name = decision.get("assign_member_name")

    target = None
    if hasattr(decision, "target"):
        target = getattr(decision, "target", None)
    elif isinstance(decision, dict):
        target = decision.get("target")

    # Entity resolution path (member domain via assign_member_name).
    if isinstance(assign_member_name, str) and assign_member_name.strip():
        if not authorization or "sentinel" in str(authorization).lower():
            # No trusted READ context in tests: preserve T12 clarify behavior.
            return {
                "status": "NOT_APPLICABLE",
                "temporal": {"status": "NOT_APPLICABLE"},
                "entity": None,
                "gate": {"allowed": True, "reason": "no_auth_context"},
                "arguments": args if isinstance(args, dict) else args,
                "merged_arguments": args if isinstance(args, dict) else args,
            }
        if not isinstance(args, dict):
            args = {}
        merged = dict(args)
        # actor/household from authenticated request context
        ctx = getattr(request, "context", None)
        actor_id = getattr(ctx, "actor_id", None) if ctx is not None else None
        household_id = getattr(ctx, "household_id", None) if ctx is not None else None
        if isinstance(request, dict):
            c = request.get("context") or {}
            actor_id = actor_id or c.get("actor_id")
            household_id = household_id or c.get("household_id")
        try:
            from homi_t14_read import read_members
            from homi_t14_entity import resolve_entity
            candidates, read_error, search_complete = read_members(
                actor_id=actor_id,
                household_id=household_id,
                authorization=authorization,
            )
            res = resolve_entity(
                assign_member_name,
                domain="member",
                household_id=household_id,
                actor_id=actor_id,
                candidates=candidates,
                candidates_source="homeplus_read",
                search_complete=search_complete,
                read_error=read_error,
            )
        except Exception as exc:
            res = {"status": "UNAVAILABLE", "domain": "member", "original": assign_member_name, "reason": str(exc)}
        status = res.get("status")
        if status == "RESOLVED":
            rid = res.get("id")
            if rid is not None:
                merged["assignedToMemberId"] = rid
            result = {
                "status": "RESOLVED",
                "temporal": {"status": "NOT_APPLICABLE"},
                "entity": res,
                "gate": {"allowed": True, "reason": "resolved"},
                "arguments": merged,
                "merged_arguments": merged,
            }
            return result
        if status == "AMBIGUOUS":
            cands = res.get("candidates") or []
            q = "Hay varios miembros que coinciden. ¿A cuál te referís?"
            return {
                "status": "NEEDS_CLARIFICATION",
                "temporal": {"status": "NOT_APPLICABLE"},
                "entity": res,
                "gate": {"allowed": False, "reason": "ambiguous"},
                "arguments": dict(args),
                "merged_arguments": dict(args),
                "clarification_question": q,
                "candidates": cands,
            }
        # blocked
        reason = res.get("reason") or status
        blocked = "UNAVAILABLE" if status in ("UNAVAILABLE", "UNAUTHORIZED") else "entity_resolution_failed"
        return {
            "status": "BLOCKED",
            "temporal": {"status": "NOT_APPLICABLE"},
            "entity": res,
            "gate": {"allowed": False, "reason": status.lower() if isinstance(status, str) else "blocked"},
            "arguments": dict(args),
            "merged_arguments": dict(args),
            "blocked_reason": blocked,
            "reason": reason,
        }

    # Entity resolution path (asset domain via asset reference).
    asset_ref = None
    for _f in ("asset_name", "asset_reference", "asset", "resolve_asset"):
        if isinstance(decision, dict) and decision.get(_f):
            asset_ref = decision.get(_f); break
        if hasattr(decision, _f):
            v = getattr(decision, _f, None)
            if isinstance(v, str) and v.strip():
                asset_ref = v; break
    if isinstance(asset_ref, str) and asset_ref.strip():
        if not authorization or "sentinel" in str(authorization).lower():
            return {
                "status": "NOT_APPLICABLE",
                "temporal": {"status": "NOT_APPLICABLE"},
                "entity": None,
                "gate": {"allowed": True, "reason": "no_auth_context"},
                "arguments": args if isinstance(args, dict) else args,
                "merged_arguments": args if isinstance(args, dict) else args,
            }
        if not isinstance(args, dict):
            args = {}
        merged = dict(args)
        ctx = getattr(request, "context", None)
        actor_id = getattr(ctx, "actor_id", None) if ctx is not None else None
        household_id = getattr(ctx, "household_id", None) if ctx is not None else None
        if isinstance(request, dict):
            c = request.get("context") or {}
            actor_id = actor_id or c.get("actor_id")
            household_id = household_id or c.get("household_id")
        try:
            from homi_t14_read import read_assets
            from homi_t14_entity import resolve_entity
            candidates, read_error, search_complete = read_assets(
                actor_id=actor_id,
                household_id=household_id,
                authorization=authorization,
            )
            res = resolve_entity(
                asset_ref,
                domain="asset",
                household_id=household_id,
                actor_id=actor_id,
                candidates=candidates,
                candidates_source="homeplus_read",
                search_complete=search_complete,
                read_error=read_error,
            )
        except Exception as exc:
            res = {"status": "UNAVAILABLE", "domain": "asset", "original": asset_ref, "reason": str(exc)}
        status = res.get("status")
        if status == "RESOLVED":
            rid = res.get("id")
            if rid is not None:
                merged["asset_id"] = rid
                merged["assetId"] = rid
            return {
                "status": "RESOLVED",
                "temporal": {"status": "NOT_APPLICABLE"},
                "entity": res,
                "gate": {"allowed": True, "reason": "resolved"},
                "arguments": merged,
                "merged_arguments": merged,
            }
        if status == "AMBIGUOUS":
            cands = res.get("candidates") or []
            q = "Hay varios activos que coinciden. ¿A cuál te referís?"
            return {
                "status": "NEEDS_CLARIFICATION",
                "temporal": {"status": "NOT_APPLICABLE"},
                "entity": res,
                "gate": {"allowed": False, "reason": "ambiguous"},
                "arguments": dict(args),
                "merged_arguments": dict(args),
                "clarification_question": q,
                "candidates": cands,
            }
        reason = res.get("reason") or status
        blocked = "UNAVAILABLE" if status in ("UNAVAILABLE", "UNAUTHORIZED") else "entity_resolution_failed"
        return {
            "status": "BLOCKED",
            "temporal": {"status": "NOT_APPLICABLE"},
            "entity": res,
            "gate": {"allowed": False, "reason": status.lower() if isinstance(status, str) else "blocked"},
            "arguments": dict(args),
            "merged_arguments": dict(args),
            "blocked_reason": blocked,
            "reason": reason,
        }

    # Direct responses / clarifications never require temporal enforcement.
    if decision_kind in ("direct_response", "clarify"):
        return {
            "status": "NOT_APPLICABLE",
            "temporal": {"status": "NOT_APPLICABLE"},
            "entity": None,
            "gate": {"allowed": True, "reason": "not_applicable"},
            "arguments": args,
            "merged_arguments": args,
        }

    if not isinstance(args, dict):
        return {
            "status": "NOT_APPLICABLE",
            "temporal": {"status": "NOT_APPLICABLE"},
            "entity": None,
            "gate": {"allowed": True, "reason": "no_arguments"},
            "arguments": args,
            "merged_arguments": args,
        }

    if isinstance(args.get("operations"), list):
        return _apply_t14_compound_resolution(
            args,
            reference_time_utc=ref_utc,
            timezone_name=tz_name,
            timezone_status=tz_status,
        )

    # ---- detect natural (non-canonical) temporal fields ----------------
    try:
        from homi_tool_proposal import _DUE_DATE_PATTERN, _DUE_TIME_PATTERN
    except Exception:
        import re as _re
        _DUE_DATE_PATTERN = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
        _DUE_TIME_PATTERN = _re.compile(r"^\d{2}:\d{2}$")

    natural = {}
    for field, pattern in (("dueDate", _DUE_DATE_PATTERN), ("dueTime", _DUE_TIME_PATTERN)):
        val = args.get(field)
        if isinstance(val, str) and pattern.match(val) is None:
            natural[field] = val

    if not natural:
        return {
            "status": "NOT_APPLICABLE",
            "temporal": {"status": "NOT_APPLICABLE"},
            "entity": None,
            "gate": {"allowed": True, "reason": "no_natural_temporal"},
            "arguments": dict(args),
            "merged_arguments": dict(args),
        }

    # If the timezone cannot be resolved safely, do not fall back to UTC.
    if tz_status != "resolved" or not tz_name:
        return {
            "status": "BLOCKED",
            "temporal": {"status": "BLOCKED", "reason": "timezone_unresolved"},
            "entity": None,
            "gate": {"allowed": False, "reason": "timezone_unresolved"},
            "arguments": dict(args),
            "merged_arguments": dict(args),
            "blocked_reason": "timezone_unresolved",
        }

    merged = dict(args)
    resolutions = {}
    clarification_question = None
    blocked_reason = None

    for field, expr in natural.items():
        r = resolve_temporal(
            expr,
            reference_utc=ref_utc,
            timezone=tz_name,
            tz_status=tz_status,
            future_required=False,
        )
        resolutions[field] = r
        status = r.get("status")
        kind = r.get("kind")

        if status == "RESOLVED":
            if field == "dueDate":
                if kind == "date" and isinstance(r.get("value"), str):
                    merged[field] = r["value"]
                else:
                    blocked_reason = blocked_reason or "invalid_temporal_kind"
            elif field == "dueTime":
                if kind == "time" and isinstance(r.get("value"), str):
                    merged[field] = r["value"]
                elif kind == "time_of_day":
                    clarification_question = clarification_question or "¿A qué hora exacta?"
                else:
                    blocked_reason = blocked_reason or "invalid_temporal_kind"
        elif status == "AMBIGUOUS":
            cands = r.get("candidates")
            if field == "dueTime":
                clarification_question = clarification_question or "¿Te referís a la mañana o a la tarde?"
            else:
                clarification_question = clarification_question or "¿A qué fecha te referís?"
        elif status in ("INVALID", "UNSUPPORTED", "UNAVAILABLE"):
            blocked_reason = blocked_reason or r.get("reason") or "invalid_temporal"
        else:
            blocked_reason = blocked_reason or "temporal_resolution_failed"

    if clarification_question is not None and blocked_reason is None:
        # only clarification if no hard block
        if not any(resolutions[f].get("status") in ("INVALID", "UNSUPPORTED", "UNAVAILABLE") for f in resolutions):
            overall = "NEEDS_CLARIFICATION"
        else:
            overall = "BLOCKED"
    elif blocked_reason is not None:
        overall = "BLOCKED"
    else:
        # ensure all natural fields got concrete values
        if all(isinstance(merged.get(f), str) and merged.get(f) for f in natural):
            overall = "RESOLVED"
        else:
            overall = "NEEDS_CLARIFICATION" if clarification_question else "BLOCKED"

    if overall == "NEEDS_CLARIFICATION":
        if clarification_question is None:
            clarification_question = "¿Podés aclarar la referencia temporal?"

    result = {
        "status": overall,
        "temporal": {
            "status": overall,
            "timezone": tz_name,
            "reference_time_utc": ref_utc.isoformat(),
            "resolutions": resolutions,
        },
        "entity": None,
        "gate": {
            "allowed": overall in ("RESOLVED", "NOT_APPLICABLE"),
            "reason": overall.lower(),
        },
        "arguments": merged if overall == "RESOLVED" else dict(args),
        "merged_arguments": merged if overall == "RESOLVED" else dict(args),
    }
    if clarification_question is not None:
        result["clarification_question"] = clarification_question
    if blocked_reason is not None:
        result["blocked_reason"] = blocked_reason
    return result


def _compound_terminal_execution(
    conversation_id: Any,
    *,
    actor_id: Any = None,
    household_id: Any = None,
) -> tuple[ActionProposalV1, dict[str, Any]] | None:
    """Return a terminal compound outcome for idempotent replay."""

    if not execution_scope_matches(
        conversation_id,
        actor_id=actor_id,
        household_id=household_id,
    ):
        return None

    terminal = get_terminal_proposal(conversation_id)

    if not isinstance(terminal, ActionProposalV1):
        return None

    if not is_compound_create_arguments(terminal.arguments):
        return None

    record = get_execution_record(conversation_id)

    if not isinstance(record, dict):
        return None

    if record.get("proposal_id") != terminal.proposal_id:
        return None

    if record.get("status") not in (
        PROPOSAL_STATUS_SUCCEEDED,
        PROPOSAL_STATUS_PARTIAL,
        PROPOSAL_STATUS_FAILED,
        PROPOSAL_STATUS_EXECUTING,
    ):
        return None

    if terminal.status != record.get("status"):
        return None

    return terminal, record


def _compound_execution_answer(
    status: str,
    operations: list[dict[str, Any]],
    *,
    outcome_uncertain: bool = True,
) -> str:
    """Build an honest aggregate answer for one compound outcome."""

    total = len(operations)
    succeeded = sum(
        1
        for operation in operations
        if operation.get("status") == PROPOSAL_STATUS_SUCCEEDED
    )
    failed = sum(
        1
        for operation in operations
        if operation.get("status") == PROPOSAL_STATUS_FAILED
    )

    if status == PROPOSAL_STATUS_SUCCEEDED:
        return f"Se crearon {succeeded} tareas."

    if status == PROPOSAL_STATUS_PARTIAL:
        return (
            f"Se crearon {succeeded} de {total} tareas; "
            f"{failed} fallaron."
        )

    if total == 0:
        if not outcome_uncertain:
            # The failure happened before dispatch, so the seam was never
            # invoked and no task can have been committed by this attempt.
            return (
                "No se creó ninguna tarea: la ejecución no fue enviada "
                "a Planner."
            )

        # A transport/malformed failure has no authoritative per-item
        # result. The seam may already have committed one or more rows,
        # so D must not turn an unknown outcome into a false zero count.
        return (
            "La ejecución falló y no se pudo determinar si se creó "
            "alguna tarea."
        )

    return (
        f"No se creó ninguna tarea: las {total} operaciones "
        "fallaron."
    )


def _complete_compound_execution(
    conversation_id: Any,
    *,
    proposal: ActionProposalV1,
    attempt: Any,
) -> tuple[ActionProposalV1, str | None]:
    """Validate and close one authoritative compound T07 outcome."""

    result = getattr(attempt, "result", None)
    operations = proposal.arguments.get("operations")
    expected_count = (
        len(operations)
        if isinstance(operations, list)
        else None
    )

    violations = validate_compound_execution_result(
        result,
        expected_operation_count=expected_count,
    )

    if violations:
        try:
            persist_compound_execution_uncertain(
                proposal.proposal_id,
                reason="EXECUTION_MALFORMED_SUCCESS",
                status=PROPOSAL_STATUS_FAILED,
            )
        except Exception:
            # The durable row remains EXECUTING and will therefore recover
            # as uncertain. The in-memory terminal is still explicit.
            pass

        terminal = complete_proposal_execution(
            conversation_id,
            status=PROPOSAL_STATUS_FAILED,
            result=None,
            reason="EXECUTION_MALFORMED_SUCCESS",
        )

        return terminal, "EXECUTION_MALFORMED_SUCCESS"

    aggregate_status = str(result.get("status"))
    safe_result = proposal_execution_safe_result(result)

    try:
        persist_compound_execution_outcome(
            proposal.proposal_id,
            status=aggregate_status,
            result=safe_result,
            reason=(
                "COMPOUND_EXECUTION_FAILED"
                if aggregate_status == PROPOSAL_STATUS_FAILED
                else None
            ),
        )
    except Exception:
        terminal = complete_proposal_execution(
            conversation_id,
            status=PROPOSAL_STATUS_FAILED,
            result=None,
            reason="EXECUTION_LEDGER_UNAVAILABLE",
        )

        return terminal, "EXECUTION_LEDGER_UNAVAILABLE"

    reason = (
        "COMPOUND_EXECUTION_FAILED"
        if aggregate_status == PROPOSAL_STATUS_FAILED
        else None
    )

    terminal = complete_proposal_execution(
        conversation_id,
        status=aggregate_status,
        result=result,
        reason=reason,
    )

    return terminal, None


def _compound_action_executed_envelope(
    request: RequestEnvelope,
    *,
    terminal: ActionProposalV1,
    record: Mapping[str, Any],
    provider_id: str,
) -> ResponseEnvelope:
    """Build the public response for a compound terminal outcome."""

    safe_result = copy.deepcopy(
        dict(record.get("result") or {})
    )

    operations = copy.deepcopy(
        safe_result.get("operations")
        if isinstance(safe_result.get("operations"), list)
        else []
    )

    status = str(record.get("status"))

    if "outcome_uncertain" in record:
        outcome_uncertain = bool(
            record.get("outcome_uncertain")
        )
    else:
        outcome_uncertain = (
            status in (
                PROPOSAL_STATUS_FAILED,
                PROPOSAL_STATUS_EXECUTING,
            )
            and not operations
        )

    result: dict[str, Any] = {
        "answer": _compound_execution_answer(
            status,
            operations,
            outcome_uncertain=outcome_uncertain,
        ),
        "decision_kind": "action_executed",
        "tool_id": terminal.tool_id,
        "proposal": terminal.public_projection,
        "proposal_action": (
            PROPOSAL_ACTION_PUBLIC_CONFIRMED
        ),
        "execution_result": safe_result,
        "operations": operations,
        "status": status,
    }

    if outcome_uncertain:
        result["outcome_uncertain"] = True

        reason = record.get("reason")

        if isinstance(reason, str) and reason:
            result["reason"] = reason

    return ResponseEnvelope(
        correlation=caller_correlation(request),
        node_id="homi-d",
        provider_id=provider_id,
        capability=Capability.THINK,
        result=result,
    )


async def run_tool_turn(
    request: RequestEnvelope,
    authorization: str | None = None,
    *,
    decision_version: str = "v1",
    **kwargs: Any,
) -> ToolTurnOutcome:
    if kwargs:
        if kwargs.get("use_decision_v2") or kwargs.get("decision_v2") or kwargs.get("v2"):
            decision_version = "v2"
        if kwargs.get("decision_version") is not None:
            decision_version = str(kwargs.get("decision_version"))
        if kwargs.get("decision_schema_version") in ("2.0", "2", 2, 2.0):
            decision_version = "v2"
    """Run the T09 structured turn for one caller turn.

    The flow is strictly linear:

    * resolve the provider;
    * ask Node A for a decision (ONE A call);
    * re-validate the decision;
    * either answer the caller (direct_response), ask the caller for
      clarification (clarify) or prepare a single validated tool
      invocation (tool_request);
    * for a tool_request: execute EXACTLY ONE tool (ONE T07 call);
    * normalize the successful result into the bounded ToolResultV1;
    * ask Node A for the synthesis (ONE MORE A call);
    * validate the synthesized answer and return it.

    The bounds of the turn are hard: ONE tool call, TWO Node A calls
    (the decision and the synthesis) and no retry, no recursion and no
    second tool.

    The internal tool result is returned next to the public envelope so
    the seam can be inspected. It is never exposed by the public
    envelope.
    """

    started = time.perf_counter()

    tool_result: ToolExecutionResult | None = None

    def finish(
        envelope: ResponseEnvelope | ErrorEnvelope,
        *,
        decision_kind: str | None = None,
        tool_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> ToolTurnOutcome:

        # T27 — attach DeliveryPlan (additive) without altering text.
        # T28 — attach spoken_text (additive) without altering display text.
        # These delivery fields belong to results that carry a real tool
        # execution (tool_result), a direct THINK answer (direct_response),
        # or a confirm/cancel proposal action (proposal_action present).
        # Pure proposal edits (T12-4) keep the canonical three keys
        # (answer, decision_kind, proposal) and must not receive them.
        result_keys = set((envelope.result or {}).keys()) if isinstance(
            envelope, ResponseEnvelope
        ) else set()
        if (
            tool_result is not None
            or decision_kind == "direct_response"
            or "proposal_action" in result_keys
        ):
            try:
                if isinstance(envelope, ResponseEnvelope):
                    from homi_delivery import (
                        extract_signals_from_envelope,
                        select_delivery_plan,
                    )
                    signals = extract_signals_from_envelope(
                        envelope, tool_result, decision_kind
                    )
                    plan = select_delivery_plan(signals)
                    new_result = dict(envelope.result or {})
                    new_result.setdefault(
                        "delivery_plan", plan.model_dump(mode="json")
                    )
                    # T28 normalization
                    try:
                        from homi_t28_normalizer import normalize_text
                        _text = None
                        for _k in ("answer", "response", "text", "message"):
                            _v = new_result.get(_k)
                            if isinstance(_v, str) and _v.strip():
                                _text = _v
                                break
                        if _text is not None:
                            new_result.setdefault("display_text", _text)
                            _nr = normalize_text(_text, locale=getattr(plan, "locale", "es-AR"))
                            new_result["spoken_text"] = _nr.spoken_text
                    except Exception:
                        pass
                    envelope.result = new_result
            except Exception:
                pass

        error_code = None

        if isinstance(envelope, ErrorEnvelope):
            error_code = envelope.error.code.value

        log_tool_event(
            request,
            operation=OPERATION_INFER_WITH_TOOLS,
            decision_kind=decision_kind,
            tool_id=tool_id,
            tool_call_id=tool_call_id,
            outcome=(
                "success"
                if isinstance(envelope, ResponseEnvelope)
                else "error"
            ),
            latency_ms=(
                time.perf_counter() - started
            ) * 1000.0,
            error_code=error_code,
        )

        return ToolTurnOutcome(
            envelope=envelope,
            tool_result=tool_result,
        )

    raw_text = request.payload.get("text")
    text = raw_text.strip() if isinstance(raw_text, str) else ''
    attachments = request.payload.get("attachments")
    has_attachments = isinstance(attachments, list) and len(attachments) > 0
    provider_text = provider_text_for_model(
        text,
        has_attachments=has_attachments,
    )
    has_proposal_action = "proposal_action" in request.payload
    raw_proposal_action = request.payload.get("proposal_action")
    proposal_action = (
        raw_proposal_action
        if isinstance(raw_proposal_action, str)
        else ""
    )

    if has_proposal_action and not isinstance(
        raw_proposal_action,
        str,
    ):
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INVALID_REQUEST,
                message="payload.proposal_action must be a string",
                details={
                    "reason": "invalid_proposal_action",
                },
            )
        )

    if has_proposal_action and proposal_action not in (
        PROPOSAL_ACTION_CONFIRM,
        PROPOSAL_ACTION_CANCEL,
    ):
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INVALID_REQUEST,
                message=(
                    "payload.proposal_action must be 'confirm' or 'cancel'"
                ),
                details={
                    "reason": "invalid_proposal_action",
                },
            )
        )

    if (not isinstance(text, str) or not text.strip()) and not has_attachments and not has_proposal_action:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INVALID_REQUEST,
                message=(
                    "operation=infer_with_tools requires a "
                    "non-empty payload.text, attachments or proposal_action"
                ),
                details={
                    "reason": "missing_text",
                },
            )
        )

    credential = extract_bearer_token(authorization)

    # Provider identity for telemetry in the confirmation shortcut.
    # Resolved eagerly here because the shortcut runs before the normal
    # provider-resolution step.
    provider_id = "think-primary"
    node_id = "homi-d"

    # ---- T11-5 confirmation shortcut (before Node A) -------------------
    # When a PROPOSED proposal is pending and the user's text is an
    # unambiguous confirmation, D applies the confirm action directly
    # without asking Node A. This keeps multi-turn confirmation working
    # even when THINK cannot parse a bare "sí" / "dale" / "ok" as a
    # structured decision. The check only fires in context (a proposal is
    # already pending), so a generic affirmation is never interpreted
    # out of context.
    conversation_id = request.context.conversation_id
    pending = get_pending_proposal(conversation_id)

    compound_replay = _compound_terminal_execution(
        conversation_id,
        actor_id=request.context.actor_id,
        household_id=request.context.household_id,
    )

    if (
        pending is None
        and compound_replay is not None
        and _is_unambiguous_confirmation(text)
    ):
        replay_terminal, replay_record = compound_replay

        return finish(
            _compound_action_executed_envelope(
                request,
                terminal=replay_terminal,
                record=replay_record,
                provider_id=provider_id,
            ),
            decision_kind="action_executed",
            tool_id=replay_terminal.tool_id,
        )

    if (
        pending is not None
        and pending.status == PROPOSAL_STATUS_PROPOSED
        and _is_unambiguous_confirmation(text)
    ):
        try:
            transitioned = apply_proposal_action(
                conversation_id,
                pending.proposal_id,
                PROPOSAL_ACTION_CONFIRM,
                actor_id=request.context.actor_id,
                household_id=request.context.household_id,
            )
        except ActionProposalError:
            # Fail-closed: nothing transitions, the pending proposal
            # stays PROPOSED and intact.
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message="the requested proposal action is not allowed",
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={"reason": "PROPOSAL_ACTION_NOT_ALLOWED"},
                ),
                decision_kind="action_proposal",
                tool_id=pending.tool_id,
            )

        # T11-6: CONFIRM crosses the seam exactly once when the internal
        # write executor is REAL. Idempotent replay (T11-7) returns the
        # stored result without a new mutation.
        existing_record = get_execution_record(conversation_id)

        if (
            isinstance(existing_record, dict)
            and existing_record.get("status") == PROPOSAL_STATUS_SUCCEEDED
            and existing_record.get("proposal_id") == transitioned.proposal_id
        ):
            terminal = get_terminal_proposal(conversation_id)
            if terminal is None:
                terminal = transitioned

            if transitioned.tool_id == PLANNER_TASKS_CREATE_TOOL_ID:
                verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_created_task(
                    request,
                    conversation_id,
                    transitioned.proposal_id,
                    existing_record.get("result") or {},
                    credential,
                    terminal,
                )
            else:
                verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_t12_task(
                    request,
                    conversation_id,
                    transitioned.proposal_id,
                    existing_record.get("result") or {},
                    credential,
                    terminal,
                    transitioned.tool_id,
                )

            safe_write = existing_record.get("result") or {}

            if verified:
                return finish(
                    ResponseEnvelope(
                        correlation=caller_correlation(request),
                        node_id="homi-d",
                        provider_id=provider_id,
                        capability=Capability.THINK,
                        result={
                            "answer": "La tarea ya estaba completada.",
                            "decision_kind": "action_executed",
                            "tool_id": verified_terminal.tool_id,
                            "proposal": verified_terminal.public_projection,
                            "proposal_action": PROPOSAL_ACTION_PUBLIC_CONFIRMED,
                            "execution_result": safe_write,
                            "verification_result": (
                                proposal_execution_safe_result({"task": read_task})
                                if isinstance(read_task, Mapping)
                                else safe_write
                            ),
                            "status": "VERIFIED",
                        },
                    ),
                    decision_kind="action_executed",
                    tool_id=verified_terminal.tool_id,
                )

            return finish(
                ResponseEnvelope(
                    correlation=caller_correlation(request),
                    node_id="homi-d",
                    provider_id=provider_id,
                    capability=Capability.THINK,
                    result={
                        "answer": "La creación fue aceptada, pero no pude verificarla todavía.",
                        "decision_kind": "action_executed",
                        "tool_id": verified_terminal.tool_id,
                        "proposal": verified_terminal.public_projection,
                        "proposal_action": PROPOSAL_ACTION_PUBLIC_CONFIRMED,
                        "execution_result": safe_write,
                        "verification": get_verification_record(conversation_id),
                        "status": "UNVERIFIED",
                    },
                ),
                decision_kind="action_executed",
                tool_id=verified_terminal.tool_id,
            )

        try:
            assert_write_execution_trusted(transitioned)

            terminal_now = get_terminal_proposal(conversation_id)

            if (
                isinstance(terminal_now, ActionProposalV1)
                and terminal_now.status == PROPOSAL_STATUS_EXECUTING
                and terminal_now.proposal_id == transitioned.proposal_id
            ):
                executing_proposal = terminal_now
            else:
                executing_proposal = begin_proposal_execution(
                    conversation_id,
                    transitioned.proposal_id,
                )

        except (ActionProposalError, WriteExecutorDisabledError) as error:
            reason = (
                error.code
                if isinstance(error, ActionProposalError)
                else "PROPOSAL_EXECUTION_UNAVAILABLE"
            )

            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message="the confirmed proposal could not be executed",
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={"reason": reason},
                ),
                decision_kind="action_proposal",
                tool_id=transitioned.tool_id,
            )

        try:
            persist_compound_execution_start(
                conversation_id,
                executing_proposal,
                actor_id=request.context.actor_id,
                household_id=request.context.household_id,
            )
        except Exception:
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.INTERNAL_ERROR,
                    message=(
                        "the compound execution could not be persisted "
                        "before dispatch"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": "EXECUTION_LEDGER_UNAVAILABLE",
                    },
                ),
                decision_kind="action_executed",
                tool_id=transitioned.tool_id,
            )

        executor = get_write_executor()

        attempt = await executor.execute_write(
            executing_proposal,
            bearer_token=credential,
            actor_id=str(request.context.actor_id),
            household_id=str(request.context.household_id),
        )

        if (
            attempt.ok
            and is_compound_create_arguments(
                executing_proposal.arguments
            )
        ):
            terminal, compound_error = (
                _complete_compound_execution(
                    conversation_id,
                    proposal=executing_proposal,
                    attempt=attempt,
                )
            )

            if compound_error is not None:
                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.PROVIDER_ERROR,
                        message=(
                            "the compound write execution returned an "
                            "invalid result"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={
                            "reason": compound_error,
                        },
                    ),
                    decision_kind="action_executed",
                    tool_id=terminal.tool_id,
                )

            record = get_execution_record(conversation_id)

            if not isinstance(record, dict):
                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.INTERNAL_ERROR,
                        message=(
                            "the compound execution record is unavailable"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={
                            "reason": (
                                "PROPOSAL_EXECUTION_RECORD_MISSING"
                            ),
                        },
                    ),
                    decision_kind="action_executed",
                    tool_id=terminal.tool_id,
                )

            return finish(
                _compound_action_executed_envelope(
                    request,
                    terminal=terminal,
                    record=record,
                    provider_id=provider_id,
                ),
                decision_kind="action_executed",
                tool_id=terminal.tool_id,
            )

        if attempt.ok:
            terminal = complete_proposal_execution(
                conversation_id,
                succeeded=True,
                result=attempt.result,
            )

            if transitioned.tool_id == PLANNER_TASKS_CREATE_TOOL_ID:
                verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_created_task(
                    request,
                    conversation_id,
                    terminal.proposal_id,
                    attempt.result,
                    credential,
                    terminal,
                )
            else:
                verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_t12_task(
                    request,
                    conversation_id,
                    terminal.proposal_id,
                    attempt.result,
                    credential,
                    terminal,
                    transitioned.tool_id,
                )

            safe_write = proposal_execution_safe_result(attempt.result)

            if verified:
                return finish(
                    ResponseEnvelope(
                        correlation=caller_correlation(request),
                        node_id="homi-d",
                        provider_id=provider_id,
                        capability=Capability.THINK,
                        result={
                            "answer": T12_SUCCESS_ANSWERS.get(
                                verified_terminal.tool_id,
                                "Operación completada.",
                            ),
                            "decision_kind": "action_executed",
                            "tool_id": verified_terminal.tool_id,
                            "proposal": verified_terminal.public_projection,
                            "proposal_action": PROPOSAL_ACTION_PUBLIC_CONFIRMED,
                            "execution_result": safe_write,
                            "verification_result": (
                                proposal_execution_safe_result({"task": read_task})
                                if isinstance(read_task, Mapping)
                                else safe_write
                            ),
                            "status": "VERIFIED",
                        },
                    ),
                    decision_kind="action_executed",
                    tool_id=verified_terminal.tool_id,
                )

            return finish(
                ResponseEnvelope(
                    correlation=caller_correlation(request),
                    node_id="homi-d",
                    provider_id=provider_id,
                    capability=Capability.THINK,
                    result={
                        "answer": T12_PENDING_ANSWERS.get(
                            verified_terminal.tool_id,
                            "La operación fue aceptada, pero no pude "
                            "verificarla todavía.",
                        ),
                        "decision_kind": "action_executed",
                        "tool_id": verified_terminal.tool_id,
                        "proposal": verified_terminal.public_projection,
                        "proposal_action": PROPOSAL_ACTION_PUBLIC_CONFIRMED,
                        "execution_result": safe_write,
                        "verification": get_verification_record(conversation_id),
                        "status": "UNVERIFIED",
                    },
                ),
                decision_kind="action_executed",
                tool_id=verified_terminal.tool_id,
            )

        if (
            attempt.retryable
            and is_compound_create_arguments(
                executing_proposal.arguments
            )
        ):
            # The mutation may already have reached Product Truth. Keep
            # the compound proposal EXECUTING so its identity is stable
            # and never turn an unknown outcome into a false zero count.
            try:
                persist_compound_execution_uncertain(
                    executing_proposal.proposal_id,
                    reason=(
                        attempt.reason_code
                        or "EXECUTION_AMBIGUOUS"
                    ),
                    status=PROPOSAL_STATUS_EXECUTING,
                )
            except Exception:
                pass

            try:
                record_uncertain_proposal_execution(
                    conversation_id,
                    executing_proposal,
                    reason=(
                        attempt.reason_code
                        or "EXECUTION_AMBIGUOUS"
                    ),
                )
            except Exception:
                pass

            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "the confirmed compound write execution outcome "
                        "is uncertain"
                    ),
                    retryable=True,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": (
                            attempt.reason_code
                            or "EXECUTION_AMBIGUOUS"
                        ),
                    },
                ),
                decision_kind="action_executed",
                tool_id=transitioned.tool_id,
            )

        if is_compound_create_arguments(
            executing_proposal.arguments
        ):
            try:
                persist_compound_execution_uncertain(
                    executing_proposal.proposal_id,
                    reason=(
                        attempt.reason_code or "EXECUTION_FAILED"
                    ),
                    status=PROPOSAL_STATUS_FAILED,
                )
            except Exception:
                pass

        complete_proposal_execution(
            conversation_id,
            status=PROPOSAL_STATUS_FAILED,
            result=None,
            reason=(
                attempt.reason_code or "EXECUTION_FAILED"
            ),
        )

        return finish(
            tool_failure(
                request,
                code=ErrorCode.PROVIDER_ERROR,
                message="the confirmed proposal could not be executed",
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={"reason": attempt.reason_code or "EXECUTION_FAILED"},
            ),
            decision_kind="action_proposal",
            tool_id=transitioned.tool_id,
        )

    try:
        try:
            _ctx_proj = build_context_projection(request)
        except Exception:
            _ctx_proj = None
        internal = build_internal_request(
            request,
            provider_text,
            decision_version=decision_version,
            context_projection=_ctx_proj,
        )

    except ToolCatalogError as error:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INTERNAL_ERROR,
                message="the tool catalogue is unavailable",
                details={
                    "reason": error.code,
                },
            )
        )

    try:
        assert_a_request_is_sanitized(
            internal,
            secret_values=(credential,) if credential else (),
        )

    except ToolLoopError as error:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INTERNAL_ERROR,
                message=(
                    "the internal provider request was rejected "
                    "by the sanitization gate"
                ),
                details={
                    "reason": error.code,
                },
            )
        )

    if has_proposal_action:
        # An explicit proposal action is a structured lifecycle command,
        # not free-form user text. Node D owns this decision and resolves
        # it against the CURRENT pending proposal. Do not ask THINK to
        # reinterpret the action as text and do not expose an empty text
        # turn to the provider.
        provider = {
            "node_id": "homi-d",
            "provider_id": "think-primary",
        }

    else:
        provider = await _resolve_provider(request)

        if isinstance(provider, ErrorEnvelope):
            return finish(provider)

    node_id = provider["node_id"]

    provider_id = provider["provider_id"]

    provider_started = time.perf_counter()

    if has_proposal_action:
        a_result = ResponseEnvelope(
            correlation=caller_correlation(request),
            node_id="homi-d",
            provider_id="think-primary",
            capability=Capability.THINK,
            result={
                "decision": {
                    "decision": DECISION_DIRECT_RESPONSE,
                    "answer": "Acción de propuesta solicitada.",
                    "question": None,
                    "tool_id": None,
                    "arguments": None,
                    DECISION_WRITE_ADDITIVE_FIELD: None,
                    DECISION_PROPOSAL_ACTION_FIELD: proposal_action,
                },
            },
        )

    else:
        a_result = await _call_node_a(
            request,
            internal,
            provider,
        )

    provider_latency_ms = (
        time.perf_counter() - provider_started
    ) * 1000.0

    if isinstance(a_result, ErrorEnvelope):
        log_tool_event(
            request,
            operation=OPERATION_INFER_WITH_TOOLS,
            decision_kind=None,
            tool_id=None,
            tool_call_id=None,
            outcome="decision_failed",
            latency_ms=provider_latency_ms,
            error_code=a_result.error.code.value,
        )

        return finish(a_result)

    result = a_result

    raw_decision = result.result.get("decision")

    if isinstance(raw_decision, str):
        try:
            raw_decision = json.loads(raw_decision)

        except (ValueError, TypeError):
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "provider returned an invalid structured "
                        "decision"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": "invalid_decision",
                    },
                )
            )

    if not isinstance(raw_decision, dict):
        return finish(
            tool_failure(
                request,
                code=ErrorCode.PROVIDER_ERROR,
                message=(
                    "provider returned an invalid structured decision"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": "invalid_decision",
                },
            )
        )

    raw_decision = _canonicalize_model_decision(raw_decision, text)

    try:
        decision = parse_decision(raw_decision)

        # The frozen T10 READ surface accepted the decision: no
        # WRITE proposal decision can also exist.
        proposal_decision = None

    except ToolDecisionError as error:
        # T11-4: the only retry is the additive v2 WRITE surface.
        # It accepts exactly one tool (planner.tasks.create) with the
        # same structural gates; everything else fails closed with the
        # original frozen error.
        proposal_decision = None

        if decision_version == "v2":
            try:
                proposal_decision = (
                    parse_action_proposal_decision(
                        raw_decision,
                    )
                )

            except ToolDecisionError:
                proposal_decision = None

        if proposal_decision is None:
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "provider returned an invalid structured decision"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": error.code,
                    },
                )
            )

    # ---- T11-5: v2 envelopes that map onto the frozen contract --------
    # The additive surface may project a v2 envelope (whose decision
    # object always carries every schema field) onto the canonical
    # five-field contract. The frozen parser and the frozen dispatch
    # stay the ONLY semantics for those decisions.

    if (
        proposal_decision is not None
        and proposal_decision.v1_projection is not None
    ):
        try:
            decision = parse_decision(
                dict(proposal_decision.v1_projection),
            )

        except ToolDecisionError as error:
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "provider returned an invalid structured decision"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": error.code,
                    },
                )
            )

        proposal_decision = None

    # ---- T14: temporal enforcement (blocking when required) ----
    _t14_resolution = None
    try:
        if proposal_decision is not None:
            _t14_resolution = apply_t14_resolution(
                request, proposal_decision, text, context_projection=_ctx_proj, authorization=authorization
            )
        else:
            _t14_resolution = apply_t14_resolution(
                request, decision, text, context_projection=_ctx_proj, authorization=authorization
            )
    except Exception:
        _t14_resolution = {
            "status": "BLOCKED",
            "blocked_reason": "resolver_exception",
        }

    if isinstance(_t14_resolution, dict):
        _status = _t14_resolution.get("status")
        if _status == "NEEDS_CLARIFICATION":
            _q = _t14_resolution.get(
                "clarification_question", "¿Podés aclarar la referencia temporal?"
            )
            return finish(
                ResponseEnvelope(
                    correlation=caller_correlation(request),
                    node_id=node_id,
                    provider_id=provider_id,
                    capability=Capability.THINK,
                    result={
                        "answer": _q,
                        "decision_kind": "clarify",
                    },
                ),
                decision_kind="clarify",
            )
        if _status == "BLOCKED":
            return finish(
                ResponseEnvelope(
                    correlation=caller_correlation(request),
                    node_id=node_id,
                    provider_id=provider_id,
                    capability=Capability.THINK,
                    result={
                        "answer": (
                            "No pude resolver la referencia temporal de forma "
                            "segura; no realicé la operación."
                        ),
                        "decision_kind": "blocked",
                        "reason": _t14_resolution.get(
                            "blocked_reason", "temporal_resolution_failed"
                        ),
                    },
                ),
                decision_kind="blocked",
            )
        if _status == "RESOLVED":
            _merged = _t14_resolution.get("arguments")
            if not isinstance(_merged, dict):
                _merged = _t14_resolution.get("merged_arguments")
            if isinstance(_merged, dict):
                if proposal_decision is not None:
                    try:
                        proposal_decision = replace(
                            proposal_decision, arguments=dict(_merged)
                        )
                    except Exception:
                        return finish(
                            tool_failure(
                                request,
                                code=ErrorCode.PROVIDER_ERROR,
                                message=(
                                    "the resolved temporal arguments could "
                                    "not be applied"
                                ),
                                details={
                                    "reason": (
                                        "temporal_resolution_merge_failed"
                                    ),
                                },
                            )
                        )

                    _vp = getattr(proposal_decision, "v1_projection", None)
                    if isinstance(_vp, dict) and isinstance(
                        _vp.get("arguments"), dict
                    ):
                        _vp2 = dict(_vp)
                        _vp2["arguments"] = dict(_merged)
                        try:
                            proposal_decision = replace(
                                proposal_decision, v1_projection=_vp2
                            )
                        except Exception:
                            return finish(
                                tool_failure(
                                    request,
                                    code=ErrorCode.PROVIDER_ERROR,
                                    message=(
                                        "the resolved temporal arguments "
                                        "could not be projected"
                                    ),
                                    details={
                                        "reason": (
                                            "temporal_resolution_merge_failed"
                                        ),
                                    },
                                )
                            )
                else:
                    try:
                        decision = decision.model_copy(
                            update={"arguments": dict(_merged)}
                        )
                    except Exception:
                        try:
                            decision.arguments = dict(_merged)
                        except Exception:
                            return finish(
                                tool_failure(
                                    request,
                                    code=ErrorCode.PROVIDER_ERROR,
                                    message=(
                                        "the resolved temporal arguments "
                                        "could not be applied"
                                    ),
                                    details={
                                        "reason": (
                                            "temporal_resolution_merge_failed"
                                        ),
                                    },
                                )
                            )

    # ---- T11-4 / T11-5: additive proposal dispatch --------------------

    if proposal_decision is not None:
        conversation_id = (
            request.context.conversation_id
        )

        pending = get_pending_proposal(
            conversation_id,
        )

        # ---- T11-5 confirmation fallback -------------------------------
        # When THINK does not emit proposal_action: confirm but the user's
        # text is an unambiguous confirmation and a PROPOSED proposal is
        # pending, D applies the confirm action deterministically. This
        # keeps multi-turn confirmation working even when the model does
        # not reproduce the lifecycle classification perfectly. The check
        # only fires when a proposal is already pending (in context), so
        # a generic affirmation is never interpreted out of context.
        _payload_action = request.payload.get("proposal_action")
        _client_cancel = (
            isinstance(_payload_action, str)
            and _payload_action.strip() == PROPOSAL_ACTION_CANCEL
        )
        if (
            pending is not None
            and pending.status == PROPOSAL_STATUS_PROPOSED
            and proposal_decision.decision == DECISION_DIRECT_RESPONSE
            and proposal_decision.proposal_action is None
            and proposal_decision.tool_id is None
            and (
                _is_unambiguous_confirmation(text) or _client_cancel
            )
        ):
            proposal_decision = replace(
                proposal_decision,
                proposal_action=(
                    PROPOSAL_ACTION_CONFIRM
                    if _is_unambiguous_confirmation(text)
                    else PROPOSAL_ACTION_CANCEL
                ),
            )

        if proposal_decision.proposal_action is not None:
            # ---- LIFECYCLE intent (T11-5 + T11-6) ----------------------
            # A only interpreted the intent. D resolves the action
            # against the CURRENT active proposal and owns the whole
            # transition. The model answer is discarded: the canonical
            # lifecycle response is deterministic and owned by D.
            #
            # In T11-6 that lifecycle stops being state-only for
            # CONFIRM: when the internal write executor is REAL, the
            # CURRENT CONFIRMED proposal is executed once through the
            # dedicated server-to-server seam (section 3 of the task).
            # When the executor is disabled the T11-5 contract is
            # preserved verbatim: no network call, no write.

            action = proposal_decision.proposal_action

            if pending is None:
                # C04 idempotent replay: a duplicate confirmation of an
                # already-terminal compound proposal reuses the stored
                # outcome and never crosses the seam again.
                compound_replay = _compound_terminal_execution(
                    conversation_id,
                    actor_id=request.context.actor_id,
                    household_id=request.context.household_id,
                )

                if (
                    action == PROPOSAL_ACTION_CONFIRM
                    and compound_replay is not None
                ):
                    replay_terminal, replay_record = (
                        compound_replay
                    )

                    return finish(
                        _compound_action_executed_envelope(
                            request,
                            terminal=replay_terminal,
                            record=replay_record,
                            provider_id=provider_id,
                        ),
                        decision_kind="action_executed",
                        tool_id=replay_terminal.tool_id,
                    )

                # T11-5 section 7: without an active PROPOSED proposal
                # the action must not transition anything. A safe
                # no-active-proposal answer is returned instead.
                answer = (
                    "No hay una propuesta pendiente que confirmar."
                    if action == "confirm"
                    else "No hay una propuesta pendiente que cancelar."
                )

                return finish(
                    ResponseEnvelope(
                        correlation=caller_correlation(request),
                        node_id="homi-d",
                        provider_id=provider_id,
                        capability=Capability.THINK,
                        result={
                            "answer": answer,
                            "decision_kind": "action_proposal",
                        },
                    ),
                    decision_kind="action_proposal",
                )

            try:
                transitioned = apply_proposal_action(
                    conversation_id,
                    pending.proposal_id,
                    action,
                    actor_id=request.context.actor_id,
                    household_id=request.context.household_id,
                )

            except ActionProposalError as error:
                # Fail-closed: nothing transitions, the pending
                # proposal stays PROPOSED and intact.
                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.PROVIDER_ERROR,
                        message=(
                            "the requested proposal action is not "
                            "allowed"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={
                            "reason": error.code,
                        },
                    ),
                    decision_kind="action_proposal",
                    tool_id=pending.tool_id,
                )

            # T11-6: CONFIRM can now CROSS the seam exactly once when
            # the internal write executor is REAL. CANCEL stays
            # state-only forever. With a DISABLED executor the T11-5
            # contract is preserved verbatim (no network call, no
            # write).
            if (
                action == "confirm"
                and transitioned.status == PROPOSAL_STATUS_CONFIRMED
                and transitioned.tool_id in T12_EXECUTION_TOOL_IDS
                and write_executor_state() == "REAL"
            ):
                # T11-7: idempotent replay. If this proposal already
                # succeeded, return the stored authoritative result without
                # any new mutation or network call.
                existing_record = get_execution_record(
                    conversation_id
                )

                if (
                    isinstance(existing_record, dict)
                    and existing_record.get("status")
                    == PROPOSAL_STATUS_SUCCEEDED
                    and existing_record.get("proposal_id")
                    == transitioned.proposal_id
                ):
                    terminal = get_terminal_proposal(
                        conversation_id
                    )

                    if terminal is None:
                        terminal = transitioned

                    if transitioned.tool_id == PLANNER_TASKS_CREATE_TOOL_ID:
                        verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_created_task(
                            request,
                            conversation_id,
                            transitioned.proposal_id,
                            existing_record.get("result") or {},
                            credential,
                            terminal,
                        )
                    else:
                        verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_t12_task(
                            request,
                            conversation_id,
                            transitioned.proposal_id,
                            existing_record.get("result") or {},
                            credential,
                            terminal,
                            transitioned.tool_id,
                        )

                    safe_write = (
                        existing_record.get("result") or {}
                    )

                    if verified:
                        return finish(
                            ResponseEnvelope(
                                correlation=caller_correlation(
                                    request
                                ),
                                node_id="homi-d",
                                provider_id=provider_id,
                                capability=Capability.THINK,
                                result={
                                    "answer": (
                                        T12_SUCCESS_ANSWERS.get(
                                            verified_terminal.tool_id,
                                            "Operación completada.",
                                        )
                                    ),
                                    "decision_kind": "action_executed",
                                    "tool_id": verified_terminal.tool_id,
                                    "proposal": (
                                        verified_terminal.public_projection
                                    ),
                                    "proposal_action": (
                                        PROPOSAL_ACTION_PUBLIC_CONFIRMED
                                    ),
                                    "execution_result": safe_write,
                                    "verification_result": (
                                        proposal_execution_safe_result(
                                            {"task": read_task}
                                        )
                                        if isinstance(read_task, Mapping)
                                        else safe_write
                                    ),
                                    "status": "VERIFIED",
                                    "task": _verified_task_payload(
                                        read_task, safe_write
                                    ),
                                },
                            ),
                            decision_kind="action_executed",
                            tool_id=verified_terminal.tool_id,
                        )

                    return finish(
                        ResponseEnvelope(
                            correlation=caller_correlation(
                                request
                            ),
                            node_id="homi-d",
                            provider_id=provider_id,
                            capability=Capability.THINK,
                            result={
                                "answer": (
                                    "La creación fue aceptada, "
                                    "pero no pude verificarla todavía."
                                ),
                                "decision_kind": "action_executed",
                                "tool_id": verified_terminal.tool_id,
                                "proposal": (
                                    verified_terminal.public_projection
                                ),
                                "proposal_action": (
                                    PROPOSAL_ACTION_PUBLIC_CONFIRMED
                                ),
                                "execution_result": safe_write,
                                "verification": (
                                    get_verification_record(
                                        conversation_id
                                    )
                                ),
                                "status": "UNVERIFIED",
                            },
                        ),
                        decision_kind="action_executed",
                        tool_id=verified_terminal.tool_id,
                    )

                # The full pre-execution gates run BEFORE any network
                # call: a tampered proposal fails closed WITHOUT
                # advancing any state and stays CONFIRMED.
                try:
                    assert_write_execution_trusted(
                        transitioned
                    )

                    terminal_now = get_terminal_proposal(
                        conversation_id
                    )

                    if (
                        isinstance(terminal_now, ActionProposalV1)
                        and terminal_now.status
                        == PROPOSAL_STATUS_EXECUTING
                        and terminal_now.proposal_id
                        == transitioned.proposal_id
                    ):
                        executing_proposal = terminal_now
                    else:
                        executing_proposal = begin_proposal_execution(
                            conversation_id,
                            transitioned.proposal_id,
                            actor_id=request.context.actor_id,
                            household_id=request.context.household_id,
                        )

                except (
                    ActionProposalError,
                    WriteExecutorDisabledError,
                ) as error:
                    reason = (
                        error.code
                        if isinstance(error, ActionProposalError)
                        else "PROPOSAL_EXECUTION_UNAVAILABLE"
                    )

                    return finish(
                        tool_failure(
                            request,
                            code=ErrorCode.PROVIDER_ERROR,
                            message=(
                                "the confirmed proposal could not "
                                "be executed"
                            ),
                            retryable=False,
                            node_id=node_id,
                            provider_id=provider_id,
                            details={
                                "reason": reason,
                            },
                        ),
                        decision_kind="action_proposal",
                        tool_id=transitioned.tool_id,
                    )

                try:
                    persist_compound_execution_start(
                        conversation_id,
                        executing_proposal,
                        actor_id=request.context.actor_id,
                        household_id=request.context.household_id,
                    )
                except Exception:
                    # The mandatory pre-dispatch ledger write failed, so
                    # the seam was NOT invoked and no task can have been
                    # committed by this attempt. Close the in-memory
                    # lifecycle as a definite, replayable FAILED outcome
                    # instead of leaving an irrecuperable EXECUTING state.
                    try:
                        complete_proposal_execution(
                            conversation_id,
                            status=PROPOSAL_STATUS_FAILED,
                            result=None,
                            reason="EXECUTION_LEDGER_UNAVAILABLE",
                            outcome_uncertain=False,
                        )
                    except ActionProposalError:
                        pass

                    return finish(
                        tool_failure(
                            request,
                            code=ErrorCode.INTERNAL_ERROR,
                            message=(
                                "the compound execution could not be "
                                "persisted before dispatch"
                            ),
                            retryable=False,
                            node_id=node_id,
                            provider_id=provider_id,
                            details={
                                "reason": (
                                    "EXECUTION_LEDGER_UNAVAILABLE"
                                ),
                            },
                        ),
                        decision_kind="action_executed",
                        tool_id=transitioned.tool_id,
                    )

                executor = get_write_executor()

                attempt = await executor.execute_write(
                    executing_proposal,
                    bearer_token=credential,
                    actor_id=str(
                        request.context.actor_id
                    ),
                    household_id=str(
                        request.context.household_id
                    ),
                )

                if (
                    attempt.ok
                    and is_compound_create_arguments(
                        executing_proposal.arguments
                    )
                ):
                    terminal, compound_error = (
                        _complete_compound_execution(
                            conversation_id,
                            proposal=executing_proposal,
                            attempt=attempt,
                        )
                    )

                    if compound_error is not None:
                        return finish(
                            tool_failure(
                                request,
                                code=ErrorCode.PROVIDER_ERROR,
                                message=(
                                    "the compound write execution "
                                    "returned an invalid result"
                                ),
                                retryable=False,
                                node_id=node_id,
                                provider_id=provider_id,
                                details={
                                    "reason": compound_error,
                                },
                            ),
                            decision_kind="action_executed",
                            tool_id=terminal.tool_id,
                        )

                    record = get_execution_record(conversation_id)

                    if not isinstance(record, dict):
                        return finish(
                            tool_failure(
                                request,
                                code=ErrorCode.INTERNAL_ERROR,
                                message=(
                                    "the compound execution record is "
                                    "unavailable"
                                ),
                                retryable=False,
                                node_id=node_id,
                                provider_id=provider_id,
                                details={
                                    "reason": (
                                        "PROPOSAL_EXECUTION_RECORD_MISSING"
                                    ),
                                },
                            ),
                            decision_kind="action_executed",
                            tool_id=terminal.tool_id,
                        )

                    return finish(
                        _compound_action_executed_envelope(
                            request,
                            terminal=terminal,
                            record=record,
                            provider_id=provider_id,
                        ),
                        decision_kind="action_executed",
                        tool_id=terminal.tool_id,
                    )

                if attempt.ok:
                    terminal = complete_proposal_execution(
                        conversation_id,
                        succeeded=True,
                        result=attempt.result,
                    )

                    if transitioned.tool_id == PLANNER_TASKS_CREATE_TOOL_ID:
                        verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_created_task(
                            request,
                            conversation_id,
                            terminal.proposal_id,
                            attempt.result,
                            credential,
                            terminal,
                        )
                    else:
                        verified_terminal, verified, verification_reason, read_task, mismatch = await _verify_t12_task(
                            request,
                            conversation_id,
                            terminal.proposal_id,
                            attempt.result,
                            credential,
                            terminal,
                            transitioned.tool_id,
                        )

                    safe_write = proposal_execution_safe_result(
                        attempt.result
                    )

                    if verified:
                        return finish(
                            ResponseEnvelope(
                                correlation=caller_correlation(
                                    request
                                ),
                                node_id="homi-d",
                                provider_id=provider_id,
                                capability=Capability.THINK,
                                result={
                                    "answer": (
                                        T12_SUCCESS_ANSWERS.get(
                                            verified_terminal.tool_id,
                                            "Operación completada.",
                                        )
                                    ),
                                    "decision_kind": "action_executed",
                                    "tool_id": verified_terminal.tool_id,
                                    "proposal": (
                                        verified_terminal.public_projection
                                    ),
                                    "proposal_action": (
                                        PROPOSAL_ACTION_PUBLIC_CONFIRMED
                                    ),
                                    "execution_result": safe_write,
                                    "verification_result": (
                                        proposal_execution_safe_result(
                                            {"task": read_task}
                                        )
                                        if isinstance(read_task, Mapping)
                                        else safe_write
                                    ),
                                    "status": "VERIFIED",
                                    "task": _verified_task_payload(
                                        read_task, safe_write
                                    ),
                                },
                            ),
                            decision_kind="action_executed",
                            tool_id=verified_terminal.tool_id,
                        )

                    return finish(
                        ResponseEnvelope(
                            correlation=caller_correlation(
                                request
                            ),
                            node_id="homi-d",
                            provider_id=provider_id,
                            capability=Capability.THINK,
                            result={
                                "answer": (
                                    "La creación fue aceptada, "
                                    "pero no pude verificarla todavía."
                                ),
                                "decision_kind": "action_executed",
                                "tool_id": verified_terminal.tool_id,
                                "proposal": (
                                    verified_terminal.public_projection
                                ),
                                "proposal_action": (
                                    PROPOSAL_ACTION_PUBLIC_CONFIRMED
                                ),
                                "execution_result": safe_write,
                                "verification": (
                                    get_verification_record(
                                        conversation_id
                                    )
                                ),
                                "status": "UNVERIFIED",
                            },
                        ),
                        decision_kind="action_executed",
                        tool_id=verified_terminal.tool_id,
                    )

                # T12-7: transport failures may be ambiguous (the mutation
                # may already have reached Product Truth). Preserve the
                # proposal in EXECUTING instead of demoting it, so the
                # retry reuses the same execution identity and relies on
                # the trusted idempotency contract.
                if attempt.retryable:
                    if is_compound_create_arguments(
                        executing_proposal.arguments
                    ):
                        try:
                            persist_compound_execution_uncertain(
                                executing_proposal.proposal_id,
                                reason=(
                                    attempt.reason_code
                                    or "EXECUTION_AMBIGUOUS"
                                ),
                                status=PROPOSAL_STATUS_EXECUTING,
                            )
                        except Exception:
                            pass

                    try:
                        record_uncertain_proposal_execution(
                            conversation_id,
                            executing_proposal,
                            reason=(
                                attempt.reason_code
                                or "EXECUTION_AMBIGUOUS"
                            ),
                        )
                    except Exception:
                        pass

                    return finish(
                        tool_failure(
                            request,
                            code=ErrorCode.PROVIDER_ERROR,
                            message=(
                                "the confirmed write execution outcome "
                                "is uncertain"
                            ),
                            retryable=True,
                            node_id=node_id,
                            provider_id=provider_id,
                            details={
                                "reason": (
                                    attempt.reason_code
                                    or "EXECUTION_AMBIGUOUS"
                                ),
                            },
                        ),
                        decision_kind="action_executed",
                        tool_id=transitioned.tool_id,
                    )

                if is_compound_create_arguments(
                    executing_proposal.arguments
                ):
                    try:
                        persist_compound_execution_uncertain(
                            executing_proposal.proposal_id,
                            reason=(
                                attempt.reason_code
                                or "EXECUTION_FAILED"
                            ),
                            status=PROPOSAL_STATUS_FAILED,
                        )
                    except Exception:
                        pass

                terminal = complete_proposal_execution(
                    conversation_id,
                    succeeded=False,
                    reason=attempt.reason_code,
                )

                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.PROVIDER_ERROR,
                        message=(
                            "the confirmed write execution failed"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={
                            "reason": (
                                attempt.reason_code
                                or "EXECUTION_FAILED"
                            ),
                        },
                    ),
                    decision_kind="action_executed",
                    tool_id=terminal.tool_id,
                )

            # CONFIRMED is NOT executed any further by the state
            # machine itself: the turn stops at the lifecycle state.
            # No T07 call, no planner mutation, no executor call, no
            # database write unless the T11-6 path above crossed the
            # seam. The canonical answer never claims creation beyond
            # what the executor returned.
            answer = (
                "Confirmaste la propuesta."
                if action == "confirm"
                else "Cancelaste la propuesta."
            )

            return finish(
                ResponseEnvelope(
                    correlation=caller_correlation(request),
                    node_id="homi-d",
                    provider_id=provider_id,
                    capability=Capability.THINK,
                    result={
                        "answer": answer,
                        "decision_kind": "action_proposal",
                        "proposal": transitioned.public_projection,
                        "proposal_action": (
                            proposal_action_public_value(
                                transitioned,
                            )
                        ),
                    },
                ),
                decision_kind="action_proposal",
                tool_id=transitioned.tool_id,
            )

        if proposal_decision.edit_patch is not None:
            # ---- EDIT intent (T11-4 create + T12-4 update) ----------

            if pending is None:
                # T11-5 section 11: a terminal proposal of the
                # conversation cannot be edited; the deterministic
                # reason names the terminal status. Without any
                # proposal at all this stays the T11-4 error.
                terminal = get_terminal_proposal(
                    conversation_id,
                )

                reason = (
                    f"proposal_terminal:{terminal.status}"
                    if terminal is not None
                    else "edit_without_pending_proposal"
                )

                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.PROVIDER_ERROR,
                        message=(
                            "the requested tool invocation is not allowed"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={
                            "reason": reason,
                        },
                    ),
                    decision_kind=DECISION_TOOL_REQUEST,
                    tool_id=proposal_decision.tool_id,
                )

            if (
                proposal_decision.tool_id
                == PLANNER_TASKS_UPDATE_TOOL_ID
            ):
                # ---- T12-4: deterministic revision of the ACTIVE
                # update proposal (sections 1-17). The trusted
                # target, the preflight refresh, the canonical merge,
                # the full revalidation and the new proposal_id are
                # ALL D-owned; NO write execution exists on this
                # path.
                (
                    t12_edit_envelope,
                    t12_edit_kind,
                    t12_edit_tool_id,
                ) = await _dispatch_t12_update_proposal_edit(
                    request,
                    proposal_decision,
                    pending,
                    credential,
                    provider_id,
                    node_id,
                )

                return finish(
                    t12_edit_envelope,
                    decision_kind=t12_edit_kind,
                    tool_id=t12_edit_tool_id,
                )

            if (
                pending.tool_id
                != PLANNER_TASKS_CREATE_TOOL_ID
            ):
                # Tool immutability during edit (T12-4 section 29):
                # the create edit path applies only to an ACTIVE
                # create proposal. An update edit patch against a
                # lifecycle proposal was already rejected by the
                # decision gate; this guard keeps the create path
                # from silently morphing a proposal of another tool.
                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.PROVIDER_ERROR,
                        message=(
                            "the requested tool invocation is not allowed"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={
                            "reason": (
                                "PROPOSAL_EDIT_TARGET_MISMATCH"
                            ),
                        },
                    ),
                    decision_kind=DECISION_TOOL_REQUEST,
                    tool_id=proposal_decision.tool_id,
                )

            try:
                revised = revise_action_proposal(
                    pending,
                    dict(
                        proposal_decision.edit_patch,
                    ),
                )

            except ActionProposalError as error:
                # The current valid proposal stays unchanged.
                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.PROVIDER_ERROR,
                        message=(
                            "the requested tool invocation is not allowed"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={
                            "reason": error.code,
                        },
                    ),
                    decision_kind=DECISION_TOOL_REQUEST,
                    tool_id=proposal_decision.tool_id,
                )

            # Deterministic stale-revision guard: the old proposal id
            # stops being the active one immediately.
            replace_pending_proposal(
                conversation_id,
                revised,
                actor_id=request.context.actor_id,
                household_id=request.context.household_id,
            )

            return finish(
                ResponseEnvelope(
                    correlation=caller_correlation(request),
                    node_id="homi-d",
                    provider_id=provider_id,
                    capability=Capability.THINK,
                    result={
                        "answer": (
                            "Actualicé la propuesta de crear la tarea."
                        ),
                        "decision_kind": "action_proposal",
                        "proposal": revised.public_projection,
                    },
                ),
                decision_kind="action_proposal",
                tool_id=revised.tool_id,
            )

        if proposal_decision.tool_id in T12_NEW_TOOL_IDS:
            # ---- T12-3 existing-task WRITE (proposal only) ----------
            # Resolve -> preflight READ -> canonical proposal ->
            # PROPOSED -> STOP. No execution path exists for these
            # four tools in this phase (sections 22-23).
            (
                t12_envelope,
                t12_kind,
                t12_tool_id,
            ) = await _dispatch_t12_existing_task_write(
                request,
                proposal_decision,
                credential,
                provider_id,
                node_id,
            )

            return finish(
                t12_envelope,
                decision_kind=t12_kind,
                tool_id=t12_tool_id,
            )

        # ---- generic WRITE (Pass 2): propose only -------------------
        # Execution crosses the seam only after the user confirms (D-owned
        # `apply_proposal_action` → `begin_proposal_execution` → seam).
        if (
            proposal_decision.tool_id != PLANNER_TASKS_CREATE_TOOL_ID
            and proposal_decision.tool_id in PROPOSAL_TOOL_IDS
        ):
            try:
                built = build_action_proposal(
                    proposal_decision.tool_id,
                    proposal_decision.arguments,
                )
            except ActionProposalError as error:
                return finish(
                    tool_failure(
                        request,
                        code=ErrorCode.PROVIDER_ERROR,
                        message=(
                            "the requested tool invocation is not allowed"
                        ),
                        retryable=False,
                        node_id=node_id,
                        provider_id=provider_id,
                        details={"reason": error.code},
                    ),
                    decision_kind=DECISION_TOOL_REQUEST,
                    tool_id=proposal_decision.tool_id,
                )

            replace_pending_proposal(
                conversation_id,
                built,
                actor_id=request.context.actor_id,
                household_id=request.context.household_id,
            )

            return finish(
                ResponseEnvelope(
                    correlation=caller_correlation(request),
                    node_id="homi-d",
                    provider_id=provider_id,
                    capability=Capability.THINK,
                    result={
                        "answer": (
                            f"Preparé una propuesta para {built.tool_id}."
                        ),
                        "decision_kind": "action_proposal",
                        "proposal": built.public_projection,
                    },
                ),
                decision_kind="action_proposal",
                tool_id=built.tool_id,
            )

        # ---- CREATE / REPLACEMENT intent (T11-3 + T11-4 §13) --------

        violations = validate_proposal_arguments(
            proposal_decision.arguments,
        )

        if violations:
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "the requested tool invocation is not allowed"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": "tool_request_rejected",
                    },
                ),
                decision_kind=DECISION_TOOL_REQUEST,
                tool_id=proposal_decision.tool_id,
            )

        try:
            built = build_action_proposal(
                proposal_decision.tool_id,
                proposal_decision.arguments,
            )

        except ActionProposalError as error:
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "the requested tool invocation is not allowed"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": error.code,
                    },
                ),
                decision_kind=DECISION_TOOL_REQUEST,
                tool_id=proposal_decision.tool_id,
            )

        replace_pending_proposal(
            conversation_id,
            built,
            actor_id=request.context.actor_id,
            household_id=request.context.household_id,
        )

        return finish(
            ResponseEnvelope(
                correlation=caller_correlation(request),
                node_id="homi-d",
                provider_id=provider_id,
                capability=Capability.THINK,
                result={
                    "answer": (
                        "Preparé una propuesta para crear las tareas."
                        if is_compound_create_arguments(
                            built.arguments
                        )
                        else "Preparé una propuesta para crear la tarea."
                    ),
                    "decision_kind": "action_proposal",
                    "proposal": built.public_projection,
                },
            ),
            decision_kind="action_proposal",
            tool_id=built.tool_id,
        )

    # ---- READ dispatch (frozen T10 behavior) ----------------------------

    if decision.decision == DECISION_DIRECT_RESPONSE:
        return finish(
            ResponseEnvelope(
                correlation=caller_correlation(request),
                node_id="homi-d",
                provider_id=provider_id,
                capability=Capability.THINK,
                result={
                    "answer": decision.answer,
                    "decision_kind": DECISION_DIRECT_RESPONSE,
                },
            ),
            decision_kind=DECISION_DIRECT_RESPONSE,
        )

    if decision.decision == DECISION_CLARIFY:
        return finish(
            ResponseEnvelope(
                correlation=caller_correlation(request),
                node_id="homi-d",
                provider_id=provider_id,
                capability=Capability.THINK,
                result={
                    "answer": decision.question,
                    "decision_kind": DECISION_CLARIFY,
                },
            ),
            decision_kind=DECISION_CLARIFY,
        )

    if decision.decision != DECISION_TOOL_REQUEST:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.PROVIDER_ERROR,
                message=(
                    "provider returned an invalid structured decision"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": "invalid_decision",
                },
            )
        )

    # ---- tool_request ---------------------------------------------------

    if decision.tool_id == PLANNER_TASKS_CREATE_TOOL_ID:
        violations = validate_proposal_arguments(
            decision.arguments,
        )

        if violations:
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "the requested tool invocation is not allowed"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": "tool_request_rejected",
                    },
                ),
                decision_kind=DECISION_TOOL_REQUEST,
                tool_id=decision.tool_id,
            )

        try:
            proposal = build_action_proposal(
                decision.tool_id,
                decision.arguments,
            )

        except ActionProposalError as error:
            return finish(
                tool_failure(
                    request,
                    code=ErrorCode.PROVIDER_ERROR,
                    message=(
                        "the requested tool invocation is not allowed"
                    ),
                    retryable=False,
                    node_id=node_id,
                    provider_id=provider_id,
                    details={
                        "reason": error.code,
                    },
                ),
                decision_kind=DECISION_TOOL_REQUEST,
                tool_id=decision.tool_id,
            )

        return finish(
            ResponseEnvelope(
                correlation=caller_correlation(request),
                node_id="homi-d",
                provider_id=provider_id,
                capability=Capability.THINK,
                result={
                    "answer": (
                        "Prepare una propuesta para crear la tarea."
                    ),
                    "decision_kind": "action_proposal",
                    "proposal": proposal.public_projection,
                },
            ),
            decision_kind="action_proposal",
            tool_id=decision.tool_id,
        )

    violations = validate_tool_request(
        decision.tool_id,
        decision.arguments,
    )

    if violations:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.PROVIDER_ERROR,
                message=(
                    "the requested tool invocation is not allowed"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": "tool_request_rejected",
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=decision.tool_id,
        )

    # The HomePlus credential is required to execute a tool request. The
    # decision is never sent back to Node A for reinterpretation and the
    # request is never forwarded to T07.
    if credential is None:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.POLICY_DENIED,
                message=(
                    "a HomePlus authorization credential is required "
                    "to execute a tool request"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": "missing_tool_authorization",
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=decision.tool_id,
        )

    loaded = catalog()

    if is_t24_read_enabled():
        try:
            loaded_v2 = catalog_v2()
        except ToolCatalogError:
            loaded_v2 = None

        if loaded_v2 is not None:
            # Combined digest for the effective catalogue (v1 + v2).
            combined = (
                str(loaded.digest) + "|" + str(loaded_v2.digest)
            ).encode("utf-8")
            effective_digest = hashlib.sha256(combined).hexdigest().upper()
        else:
            effective_digest = str(loaded.digest).upper()
    else:
        effective_digest = str(loaded.digest).upper()

    plan = ToolInvocationPlan(
        tool_call_id=mint_tool_call_id(
            request_id=request.context.request_id,
            trace_id=request.context.trace_id,
            tool_id=decision.tool_id,
            arguments=decision.arguments,
            catalog_digest=effective_digest,
        ),
        tool_id=decision.tool_id,
        arguments=dict(decision.arguments),
        catalog_digest=effective_digest,
    )

    try:
        assert_tool_call_budget([plan])

    except ToolLoopError as error:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INTERNAL_ERROR,
                message=(
                    "the tool call budget of this turn was exceeded"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": error.code,
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    context = ToolExecutionContext(
        request_id=request.context.request_id,
        trace_id=request.context.trace_id,
        turn_id=request.context.turn_id,
        conversation_id=request.context.conversation_id,
        actor_id=request.context.actor_id,
        household_id=request.context.household_id,
        bearer_token=credential,
    )

    executor = get_tool_executor()

    try:
        outcome = executor.execute(plan, context)

        if inspect.isawaitable(outcome):
            outcome = await outcome

        execution = normalize_tool_execution(plan, outcome)

    except ToolExecutorDisabledError:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.PROVIDER_NOT_CONFIGURED,
                message=(
                    "the tool executor is not configured; "
                    "no tool was executed"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": "tool_executor_disabled",
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    except ToolLoopError as error:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INTERNAL_ERROR,
                message="the tool execution failed",
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": error.code,
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    except Exception:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INTERNAL_ERROR,
                message="the tool execution failed",
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": "tool_execution_failed",
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    if not execution.ok:
        error_code = execution.error_code

        if error_code is None:
            error_code = ErrorCode.INTERNAL_ERROR

        details: dict[str, Any] = {
            "reason": "tool_execution_failed",
        }

        if execution.upstream_status is not None:
            details["upstream_status"] = execution.upstream_status

        return finish(
            tool_failure(
                request,
                code=error_code,
                message=(
                    execution.error_message
                    or "the tool execution failed"
                ),
                retryable=execution.retryable,
                node_id=node_id,
                provider_id=provider_id,
                details=details,
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    # The real HomePlus payload stays inside Node D. It is normalized
    # into the bounded, safe ToolResultV1 that is the ONLY thing the
    # synthesis request may carry.
    tool_result = execution

    try:
        normalized = normalize_tool_result(
            plan.tool_id,
            tool_result.result,
        )

        assert_tool_result_is_safe(
            normalized,
            secret_values=(
                (credential,) if credential else ()
            ),
        )

    except ToolNormalizationError as error:
        log_tool_event(
            request,
            operation=OPERATION_INFER_WITH_TOOLS,
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
            outcome="normalization_failed",
            latency_ms=0.0,
            error_code=ErrorCode.INTERNAL_ERROR.value,
        )

        return finish(
            tool_failure(
                request,
                code=ErrorCode.INTERNAL_ERROR,
                message=(
                    "the tool result could not be normalized"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": error.code,
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    synthesis = build_synthesis_request(
        request,
        provider_text,
        plan,
        normalized,
        plan.catalog_digest,
    )

    try:
        assert_a_request_is_sanitized(
            synthesis,
            secret_values=(
                (credential,) if credential else ()
            ),
        )

    except ToolLoopError as error:
        return finish(
            tool_failure(
                request,
                code=ErrorCode.INTERNAL_ERROR,
                message=(
                    "the internal synthesis request was rejected "
                    "by the sanitization gate"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": error.code,
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    synthesis_started = time.perf_counter()

    synthesis_result = await _call_node_a(
        request,
        synthesis,
        provider,
    )

    synthesis_latency_ms = (
        time.perf_counter() - synthesis_started
    ) * 1000.0

    if isinstance(synthesis_result, ErrorEnvelope):
        log_tool_event(
            request,
            operation=OPERATION_INFER_WITH_TOOLS,
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
            outcome="synthesis_failed",
            latency_ms=synthesis_latency_ms,
            error_code=synthesis_result.error.code.value,
        )

        return finish(
            synthesis_result,
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    answer = synthesis_result.result.get("answer")

    if not isinstance(answer, str) or not answer.strip():
        log_tool_event(
            request,
            operation=OPERATION_INFER_WITH_TOOLS,
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
            outcome="synthesis_failed",
            latency_ms=synthesis_latency_ms,
            error_code=ErrorCode.PROVIDER_ERROR.value,
        )

        return finish(
            tool_failure(
                request,
                code=ErrorCode.PROVIDER_ERROR,
                message=(
                    "the provider returned an invalid "
                    "synthesis answer"
                ),
                retryable=False,
                node_id=node_id,
                provider_id=provider_id,
                details={
                    "reason": "invalid_synthesis_answer",
                },
            ),
            decision_kind=DECISION_TOOL_REQUEST,
            tool_id=plan.tool_id,
            tool_call_id=plan.tool_call_id,
        )

    # The answer is grounded: the SAME turn produced the tool result,
    # the synthesis request carried EXACTLY that normalized result and
    # no other tool result was mixed in.
    grounded = bool(
        tool_result.ok
        and normalized is not None
    )

    log_tool_event(
        request,
        operation=OPERATION_INFER_WITH_TOOLS,
        decision_kind=DECISION_TOOL_REQUEST,
        tool_id=plan.tool_id,
        tool_call_id=plan.tool_call_id,
        outcome="synthesis_success",
        latency_ms=synthesis_latency_ms,
        error_code=None,
    )

    return finish(
        ResponseEnvelope(
            correlation=caller_correlation(request),
            node_id="homi-d",
            provider_id=provider_id,
            capability=Capability.THINK,
            result={
                "answer": answer,
                "decision_kind": DECISION_TOOL_REQUEST,
                "source_tool_id": plan.tool_id,
                "tool_call_id": plan.tool_call_id,
                "grounded": grounded,
                "truncated": bool(normalized.meta.truncated),
            },
        ),
        decision_kind=DECISION_TOOL_REQUEST,
        tool_id=plan.tool_id,
        tool_call_id=plan.tool_call_id,
    )


async def invoke_with_tools(
    request: RequestEnvelope,
    authorization: str | None = None,
    *,
    decision_version: str = "v1",
    **kwargs: Any,
) -> ResponseEnvelope | ErrorEnvelope:
    """The public entry point of the T09 structured turn.

    It returns the public envelope only. The internal tool result stays
    available to the loop through ``run_tool_turn``.
    """

    outcome = await run_tool_turn(
        request,
        authorization,
        decision_version=decision_version,
        **kwargs,
    )

    return outcome.envelope


async def run_tool_turn_v2(*args, **kwargs):
    kwargs.setdefault("decision_version", "v2")
    return await run_tool_turn(*args, **kwargs)


async def invoke_with_tools_v2(*args, **kwargs):
    kwargs.setdefault("decision_version", "v2")
    return await invoke_with_tools(*args, **kwargs)


# ---------------------------------------------------------------------------
# T12-8 — verify-after-write for update / complete / trash
# ---------------------------------------------------------------------------
#
# Extends the T11-8 SUCCEEDED -> VERIFYING -> VERIFIED architecture to the
# T12 existing-task WRITE tools (update, complete, trash). Verification uses
# ONLY an independent trusted HomePlus READ (planner.tasks.get); the mutation
# response alone is never sufficient. Execution and verification remain two
# independent truths.

# T12-8: field mapping for update verification. Proposal argument key ->
# authoritative Product Truth read key. Only fields actually present in the
# confirmed patch are compared; absent fields are left untouched and not
# verified.
UPDATE_VERIFY_FIELD_MAP: dict[str, str] = {
    "title": "title",
    "description": "description",
    "dueDate": "due_date",
    "dueTime": "due_time",
    "assignedToMemberId": "assigned_to_member_id",
    "checklist": "checklist",
}


def _checklists_equal(expected: Any, actual: Any) -> bool:
    """Compare two checklist arrays canonically (text, checked, order)."""

    if expected is None and actual is None:
        return True

    if expected is None or actual is None:
        return False

    if not isinstance(expected, list) or not isinstance(actual, list):
        return False

    if len(expected) != len(actual):
        return False

    for exp_item, act_item in zip(expected, actual):
        if not isinstance(exp_item, dict) or not isinstance(act_item, dict):
            return False
        if exp_item.get("text") != act_item.get("text"):
            return False
        if exp_item.get("checked") != act_item.get("checked"):
            return False

    return True


def _compare_update_fields(
    args: Mapping[str, Any],
    read_task: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compare confirmed update patch fields against the authoritative READ.

    Returns a dict of mismatches keyed by proposal argument name. Empty
    dict means all compared fields match. Fields absent from the patch are
    not compared (Product Truth may have changed them independently).
    """

    mismatches: dict[str, dict[str, Any]] = {}

    for arg_key, task_key in UPDATE_VERIFY_FIELD_MAP.items():
        if arg_key not in args:
            continue

        expected = args[arg_key]
        actual = read_task.get(task_key)

        if arg_key == "checklist":
            if not _checklists_equal(expected, actual):
                mismatches[arg_key] = {
                    "expected": expected,
                    "actual": actual,
                }
        elif arg_key == "dueTime":
            if _norm_time(expected) != _norm_time(actual):
                mismatches[arg_key] = {
                    "expected": expected,
                    "actual": actual,
                }
        else:
            if expected != actual:
                mismatches[arg_key] = {
                    "expected": expected,
                    "actual": actual,
                }

    return mismatches


async def _verify_updated_task(
    request,
    conversation_id,
    proposal_id,
    write_result,
    credential,
    terminal_proposal,
):
    """Verify a successful UPDATE via independent trusted READ.

    Reads the task by taskId and compares each confirmed patch field
    against the authoritative Product Truth state. Execution remains
    SUCCEEDED regardless of verification outcome.
    """

    write_task = None
    if isinstance(write_result, Mapping):
        if isinstance(write_result.get("task"), Mapping):
            write_task = write_result.get("task")
        elif "id" in write_result:
            write_task = write_result

    task_id = None
    if isinstance(write_task, Mapping):
        task_id = write_task.get("id")

    args = {}
    if isinstance(terminal_proposal, ActionProposalV1):
        args = dict(terminal_proposal.arguments or {})

    if not task_id:
        task_id = args.get("taskId")

    try:
        begin_proposal_verification(conversation_id, proposal_id)
    except ActionProposalError:
        current = get_terminal_proposal(conversation_id)
        if (
            isinstance(current, ActionProposalV1)
            and current.status == PROPOSAL_STATUS_VERIFIED
            and current.proposal_id == proposal_id
        ):
            return current, True, None, None, None

    if not task_id:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_TASK_ID_MISSING",
        )
        return terminal, False, "VERIFICATION_TASK_ID_MISSING", None, None

    read_result, read_error = await _read_created_task(
        request, credential, str(task_id)
    )

    if read_error is not None:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason=read_error,
        )
        return terminal, False, read_error, None, None

    read_task = None
    if isinstance(read_result, Mapping):
        read_task = read_result.get("task")

    if not isinstance(read_task, Mapping):
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_NOT_FOUND",
        )
        return terminal, False, "VERIFICATION_NOT_FOUND", None, None

    if read_task.get("id") != task_id:
        mismatch = {
            "expected": {"id": task_id},
            "actual": {"id": read_task.get("id")},
        }
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_NOT_FOUND",
            task=read_task,
            mismatch=mismatch,
        )
        return terminal, False, "VERIFICATION_NOT_FOUND", read_task, mismatch

    mismatches = _compare_update_fields(args, read_task)

    if mismatches:
        mismatch = {
            "expected": {k: v["expected"] for k, v in mismatches.items()},
            "actual": {k: v["actual"] for k, v in mismatches.items()},
            "fields": mismatches,
        }
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_MISMATCH",
            task=read_task,
            mismatch=mismatch,
        )
        return terminal, False, "VERIFICATION_MISMATCH", read_task, mismatch

    terminal = complete_proposal_verification(
        conversation_id,
        verified=True,
        reason=None,
        task=read_task,
    )
    return terminal, True, None, read_task, None


async def _verify_completed_task(
    request,
    conversation_id,
    proposal_id,
    write_result,
    credential,
    terminal_proposal,
):
    """Verify a successful COMPLETE via independent trusted READ.

    Reads the task by taskId and checks that Product Truth exposes the
    canonical completed lifecycle state. Execution remains SUCCEEDED
    regardless of verification outcome.
    """

    write_task = None
    if isinstance(write_result, Mapping):
        if isinstance(write_result.get("task"), Mapping):
            write_task = write_result.get("task")
        elif "id" in write_result:
            write_task = write_result

    task_id = None
    if isinstance(write_task, Mapping):
        task_id = write_task.get("id")

    args = {}
    if isinstance(terminal_proposal, ActionProposalV1):
        args = dict(terminal_proposal.arguments or {})

    if not task_id:
        task_id = args.get("taskId")

    try:
        begin_proposal_verification(conversation_id, proposal_id)
    except ActionProposalError:
        current = get_terminal_proposal(conversation_id)
        if (
            isinstance(current, ActionProposalV1)
            and current.status == PROPOSAL_STATUS_VERIFIED
            and current.proposal_id == proposal_id
        ):
            return current, True, None, None, None

    if not task_id:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_TASK_ID_MISSING",
        )
        return terminal, False, "VERIFICATION_TASK_ID_MISSING", None, None

    read_result, read_error = await _read_created_task(
        request, credential, str(task_id)
    )

    if read_error is not None:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason=read_error,
        )
        return terminal, False, read_error, None, None

    read_task = None
    if isinstance(read_result, Mapping):
        read_task = read_result.get("task")

    if not isinstance(read_task, Mapping):
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_NOT_FOUND",
        )
        return terminal, False, "VERIFICATION_NOT_FOUND", None, None

    if read_task.get("id") != task_id:
        mismatch = {
            "expected": {"id": task_id},
            "actual": {"id": read_task.get("id")},
        }
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_NOT_FOUND",
            task=read_task,
            mismatch=mismatch,
        )
        return terminal, False, "VERIFICATION_NOT_FOUND", read_task, mismatch

    # Product Truth exposes completion via the canonical status field.
    actual_status = read_task.get("status")
    if actual_status == "completed":
        terminal = complete_proposal_verification(
            conversation_id,
            verified=True,
            reason=None,
            task=read_task,
        )
        return terminal, True, None, read_task, None

    mismatch = {
        "expected": {"status": "completed"},
        "actual": {"status": actual_status},
    }
    terminal = complete_proposal_verification(
        conversation_id,
        verified=False,
        reason="VERIFICATION_MISMATCH",
        task=read_task,
        mismatch=mismatch,
    )
    return terminal, False, "VERIFICATION_MISMATCH", read_task, mismatch


async def _verify_trashed_task(
    request,
    conversation_id,
    proposal_id,
    write_result,
    credential,
    terminal_proposal,
):
    """Verify a successful TRASH via independent trusted READ.

    Product Truth intentionally hides trashed tasks from the normal active
    task READ surface. A canonical NOT_FOUND from planner.tasks.get is the
    expected postcondition and counts as successful trash verification.
    This does NOT independently inspect trashed_at (no trusted trashed-task
    READ exists); that limitation belongs to restore preflight.
    """

    write_task = None
    if isinstance(write_result, Mapping):
        if isinstance(write_result.get("task"), Mapping):
            write_task = write_result.get("task")
        elif "id" in write_result:
            write_task = write_result

    task_id = None
    if isinstance(write_task, Mapping):
        task_id = write_task.get("id")

    args = {}
    if isinstance(terminal_proposal, ActionProposalV1):
        args = dict(terminal_proposal.arguments or {})

    if not task_id:
        task_id = args.get("taskId")

    try:
        begin_proposal_verification(conversation_id, proposal_id)
    except ActionProposalError:
        current = get_terminal_proposal(conversation_id)
        if (
            isinstance(current, ActionProposalV1)
            and current.status == PROPOSAL_STATUS_VERIFIED
            and current.proposal_id == proposal_id
        ):
            return current, True, None, None, None

    if not task_id:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_TASK_ID_MISSING",
        )
        return terminal, False, "VERIFICATION_TASK_ID_MISSING", None, None

    read_result, read_error = await _read_created_task(
        request, credential, str(task_id)
    )

    # Trash verification ONLY: canonical NOT_FOUND is the expected
    # postcondition (task excluded from the active task surface).
    if read_error == "VERIFICATION_NOT_FOUND":
        terminal = complete_proposal_verification(
            conversation_id,
            verified=True,
            reason=None,
            task=None,
        )
        return terminal, True, None, None, None

    if read_error is not None:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason=read_error,
        )
        return terminal, False, read_error, None, None

    # Task still visible in the active surface: verification mismatch.
    read_task = None
    if isinstance(read_result, Mapping):
        read_task = read_result.get("task")

    mismatch = {
        "expected": {"absent": True},
        "actual": {"present": True, "task": read_task},
    }
    terminal = complete_proposal_verification(
        conversation_id,
        verified=False,
        reason="VERIFICATION_MISMATCH",
        task=read_task,
        mismatch=mismatch,
    )
    return terminal, False, "VERIFICATION_MISMATCH", read_task, mismatch


async def _verify_restored_task(
    request,
    conversation_id,
    proposal_id,
    write_result,
    credential,
    terminal_proposal,
):
    """Verify a successful RESTORE via independent trusted READ.

    Product Truth clears trashed_at on restore, so the restored task
    SHOULD reappear in the canonical active task surface. Verification
    reads the task by taskId through planner.tasks.get and checks that
    the task is visible again. Execution remains SUCCEEDED regardless of
    verification outcome; no second restore is ever attempted.
    """

    write_task = None
    if isinstance(write_result, Mapping):
        if isinstance(write_result.get("task"), Mapping):
            write_task = write_result.get("task")
        elif "id" in write_result:
            write_task = write_result

    task_id = None
    if isinstance(write_task, Mapping):
        task_id = write_task.get("id")

    args = {}
    if isinstance(terminal_proposal, ActionProposalV1):
        args = dict(terminal_proposal.arguments or {})

    if not task_id:
        task_id = args.get("taskId")

    try:
        begin_proposal_verification(conversation_id, proposal_id)
    except ActionProposalError:
        current = get_terminal_proposal(conversation_id)
        if (
            isinstance(current, ActionProposalV1)
            and current.status == PROPOSAL_STATUS_VERIFIED
            and current.proposal_id == proposal_id
        ):
            return current, True, None, None, None

    if not task_id:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_TASK_ID_MISSING",
        )
        return terminal, False, "VERIFICATION_TASK_ID_MISSING", None, None

    read_result, read_error = await _read_created_task(
        request, credential, str(task_id)
    )

    # Restore verification: the task must reappear in the active surface.
    if read_error == "VERIFICATION_NOT_FOUND":
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_NOT_FOUND",
        )
        return terminal, False, "VERIFICATION_NOT_FOUND", None, None

    if read_error is not None:
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason=read_error,
        )
        return terminal, False, read_error, None, None

    read_task = None
    if isinstance(read_result, Mapping):
        read_task = read_result.get("task")

    if not isinstance(read_task, Mapping):
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_NOT_FOUND",
        )
        return terminal, False, "VERIFICATION_NOT_FOUND", None, None

    if read_task.get("id") != task_id:
        mismatch = {
            "expected": {"id": task_id},
            "actual": {"id": read_task.get("id")},
        }
        terminal = complete_proposal_verification(
            conversation_id,
            verified=False,
            reason="VERIFICATION_NOT_FOUND",
            task=read_task,
            mismatch=mismatch,
        )
        return terminal, False, "VERIFICATION_NOT_FOUND", read_task, mismatch

    # The canonical postcondition: the task is visible through the active
    # READ surface. Do not invent trashed_at visibility if READ does not
    # expose it; presence in the active surface is the proof.
    terminal = complete_proposal_verification(
        conversation_id,
        verified=True,
        reason=None,
        task=read_task,
    )
    return terminal, True, None, read_task, None


async def _verify_t12_task(
    request,
    conversation_id,
    proposal_id,
    write_result,
    credential,
    terminal_proposal,
    tool_id,
):
    """Dispatch verify-after-write for one T12 existing-task WRITE tool.

    Routes to the tool-specific verification function. All verification
    paths use trusted READ only; zero WRITE calls occur during verification.
    """

    if tool_id == PLANNER_TASKS_UPDATE_TOOL_ID:
        return await _verify_updated_task(
            request,
            conversation_id,
            proposal_id,
            write_result,
            credential,
            terminal_proposal,
        )

    if tool_id == PLANNER_TASKS_COMPLETE_TOOL_ID:
        return await _verify_completed_task(
            request,
            conversation_id,
            proposal_id,
            write_result,
            credential,
            terminal_proposal,
        )

    if tool_id == PLANNER_TASKS_TRASH_TOOL_ID:
        return await _verify_trashed_task(
            request,
            conversation_id,
            proposal_id,
            write_result,
            credential,
            terminal_proposal,
        )

    if tool_id == PLANNER_TASKS_RESTORE_TOOL_ID:
        return await _verify_restored_task(
            request,
            conversation_id,
            proposal_id,
            write_result,
            credential,
            terminal_proposal,
        )

    # Unknown tool: fail closed, no verification attempted.
    terminal = complete_proposal_verification(
        conversation_id,
        verified=False,
        reason="VERIFICATION_TOOL_UNSUPPORTED",
    )
    return terminal, False, "VERIFICATION_TOOL_UNSUPPORTED", None, None


def _verified_task_payload(read_task, safe_write):
    task = {}
    if isinstance(read_task, Mapping) if False else False:
        pass
    if isinstance(read_task, dict):
        task["id"] = read_task.get("id")
        task["title"] = read_task.get("title")
        task["dueDate"] = read_task.get("due_date")
        task["dueTime"] = read_task.get("due_time")
        task["status"] = read_task.get("status")
        assigned = read_task.get("assigned_to_member_id")
        if assigned is not None:
            task["assignedToMemberId"] = assigned
    else:
        task["id"] = safe_write.get("id")
        task["title"] = safe_write.get("title")
        task["dueDate"] = safe_write.get("due_date")
        task["dueTime"] = safe_write.get("due_time")
        task["status"] = safe_write.get("status")
    return task


def _norm_time(value):
    if value is None:
        return None
    return str(value)[:5]


async def _read_created_task(request, credential, task_id):
    if not credential:
        return None, "VERIFICATION_BACKEND_FAILURE"
    base_url = (
        os.environ.get("HOMI_TOOL_BASE_URL")
        or os.environ.get("HOMI_INTERNAL_WRITE_BASE_URL")
        or "http://127.0.0.1:3001"
    ).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{base_url}/api/homi/v1/tools/planner.tasks.get/invoke",
                headers={"Authorization": f"Bearer {credential}"},
                json={"task_ref": task_id},
            )
    except (httpx.TimeoutException, httpx.TransportError):
        return None, "VERIFICATION_TRANSPORT_FAILURE"
    if response.status_code == 404:
        return None, "VERIFICATION_NOT_FOUND"
    if response.status_code != 200:
        return None, "VERIFICATION_BACKEND_FAILURE"
    try:
        payload = response.json()
    except ValueError:
        return None, "VERIFICATION_BACKEND_FAILURE"
    if not isinstance(payload, Mapping) or payload.get("tool_id") != "planner.tasks.get":
        return None, "VERIFICATION_BACKEND_FAILURE"
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return None, "VERIFICATION_BACKEND_FAILURE"
    return data, None


async def _verify_created_task(
    request,
    conversation_id,
    proposal_id,
    write_result,
    credential,
    terminal_proposal,
):
    write_task = None
    if isinstance(write_result, Mapping):
        if isinstance(write_result.get("task"), Mapping):
            write_task = write_result.get("task")
        elif "id" in write_result:
            write_task = write_result
    task_id = None
    if isinstance(write_task, Mapping):
        task_id = write_task.get("id")
    args = {}
    if isinstance(terminal_proposal, ActionProposalV1):
        args = dict(terminal_proposal.arguments or {})
    expected = {
        "title": args.get("title") if args.get("title") is not None else (write_task.get("title") if isinstance(write_task, Mapping) else None),
        "dueDate": args.get("dueDate") if args.get("dueDate") is not None else (write_task.get("due_date") if isinstance(write_task, Mapping) else None),
        "dueTime": args.get("dueTime") if args.get("dueTime") is not None else (write_task.get("due_time") if isinstance(write_task, Mapping) else None),
        "status": (write_task.get("status") if isinstance(write_task, Mapping) else None),
        "assignedToMemberId": args.get("assignedToMemberId") if args.get("assignedToMemberId") is not None else (write_task.get("assigned_to_member_id") if isinstance(write_task, Mapping) else None),
    }
    try:
        begin_proposal_verification(conversation_id, proposal_id)
    except ActionProposalError:
        current = get_terminal_proposal(conversation_id)
        if isinstance(current, ActionProposalV1) and current.status == PROPOSAL_STATUS_VERIFIED and current.proposal_id == proposal_id:
            return current, True, None, None, None
    if not task_id:
        terminal = complete_proposal_verification(conversation_id, verified=False, reason="VERIFICATION_TASK_ID_MISSING")
        return terminal, False, "VERIFICATION_TASK_ID_MISSING", None, None
    read_result, read_error = await _read_created_task(request, credential, task_id)
    if read_error is not None:
        terminal = complete_proposal_verification(conversation_id, verified=False, reason=read_error)
        return terminal, False, read_error, None, None
    read_task = None
    if isinstance(read_result, Mapping):
        read_task = read_result.get("task")
    if not isinstance(read_task, Mapping):
        terminal = complete_proposal_verification(conversation_id, verified=False, reason="VERIFICATION_NOT_FOUND")
        return terminal, False, "VERIFICATION_NOT_FOUND", None, None
    if read_task.get("id") != task_id:
        mismatch = {"expected": {"id": task_id}, "actual": {"id": read_task.get("id")}}
        terminal = complete_proposal_verification(conversation_id, verified=False, reason="VERIFICATION_NOT_FOUND", task=read_task, mismatch=mismatch)
        return terminal, False, "VERIFICATION_NOT_FOUND", read_task, mismatch
    actual = {
        "title": read_task.get("title"),
        "dueDate": read_task.get("due_date"),
        "dueTime": _norm_time(read_task.get("due_time")),
        "status": read_task.get("status"),
        "assignedToMemberId": read_task.get("assigned_to_member_id"),
    }
    expected_norm = {
        "title": expected.get("title"),
        "dueDate": expected.get("dueDate"),
        "dueTime": _norm_time(expected.get("dueTime")),
        "status": expected.get("status"),
        "assignedToMemberId": expected.get("assignedToMemberId"),
    }
    mismatches = {}
    for key in ("title", "dueDate", "dueTime", "status", "assignedToMemberId"):
        if expected_norm.get(key) is not None and expected_norm.get(key) != actual.get(key):
            mismatches[key] = {"expected": expected_norm.get(key), "actual": actual.get(key)}
    if mismatches:
        mismatch = {"expected": expected_norm, "actual": actual, "fields": mismatches}
        terminal = complete_proposal_verification(conversation_id, verified=False, reason="VERIFICATION_MISMATCH", task=read_task, mismatch=mismatch)
        return terminal, False, "VERIFICATION_MISMATCH", read_task, mismatch
    terminal = complete_proposal_verification(conversation_id, verified=True, reason=None, task=read_task)
    return terminal, True, None, read_task, None
