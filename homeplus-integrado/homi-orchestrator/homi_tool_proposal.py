"""HOMI T11-2 — canonical ActionProposal V1 contract (Node D).

An ActionProposal represents a validated WRITE that Homi is proposing to
perform but has NOT performed:

    validated planner.tasks.create arguments
        -> ActionProposalV1
        -> public proposal representation
        -> STOP

Hard boundaries of this stage
-----------------------------
* NO write execution path exists. The proposal is inert data. There is no
  code path ActionProposal -> ToolExecutor -> T07 -> Planner mutation.
* The contract authority for ``planner.tasks.create`` is the canonical
  T11-1 handoff document
  (``T11_1_PLANNER_TASKS_CREATE_CONTRACT.md`` in the T07 worktree). It is
  re-encoded here, in-code, without reinterpretation:
  tool_id ``planner.tasks.create``, kind ``WRITE``, risk flags
  ``[LOW_MUTATION]``, confirmation ``REQUIRED``, contract version 1.1.0,
  domain planner, EXECUTION_ENABLED = false.
* The proposal owns a D-minted ``proposal_id`` and a D-minted
  ``created_at``. The model, the user and the frontend may never provide
  or choose either one.
* ``arguments`` is a deep-copy, copy-isolated snapshot of arguments that
  passed strict validation. Unknown fields, missing required fields,
  wrong types, identity/credential fields, nested structure and malformed
  dates are rejected without any best-effort coercion.
* ``risk`` and ``confirmation`` always come from the trusted in-code tool
  metadata. A caller can never downgrade them.
* Identity never enters the proposal: actor, household, membership,
  credential and role stay in the RequestContext / server-derived
  authority. An ActionProposal is not an authorization grant.
* No database persistence is introduced in T11-2: proposals are
  transient, in-memory artifacts. Lifecycle/persistence is a decision for
  a later T11 stage.
* No WRITE-intent model path is built here. Node A remains frozen by T10
  and still cannot request ``planner.tasks.create``; the future seam is:
  WRITE intent/plan -> validated planner.tasks.create arguments -> the
  ActionProposal builder in this module.

This module is inert: no HTTP, no HomePlus authentication, no tool
execution, no model call, no executor seam.
"""

from __future__ import annotations

import uuid

import copy
import threading
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

# T12-4: the deterministic date/time merges and the checklist
# read-modify-write transform are pure in-code functions owned by the
# T12-3 target layer. The proposal module reuses them for the T12-4
# deterministic update-proposal revision; the dependency is acyclic
# (``homi_tool_t12_targets`` imports nothing local) and no new
# execution seam is introduced.
from homi_tool_t12_targets import (  # noqa: E402
    apply_clear_date_invariant,
    merge_due_time_intent,
    transform_checklist,
    validate_checklist_patch,
)
from homi_tool_compound_result_contract import (  # noqa: E402
    COMPOUND_OPERATION_RESULT_STATUSES,
    COMPOUND_RESULT_STATUSES,
    EXECUTION_RESULT_PUBLIC_TASK_FIELDS,
    CompoundResultAuthorityError,
    project_compound_execution_result,
    validate_compound_execution_result,
)
from homi_write_schemas import (  # noqa: E402
    WRITE_CONTRACTS,
    WRITE_TOOL_IDS,
    generic_validate_arguments,
)


# ---------------------------------------------------------------------------
# Contract authority (T11-1, re-encoded verbatim, not reinterpreted)
# ---------------------------------------------------------------------------

PROPOSAL_VERSION = "1.0"

# A pending WRITE proposal is valid for fifteen minutes. The deadline is
# minted by D with the proposal and is independent from the model, the
# frontend and the caller. A proposal that reaches the deadline becomes
# terminal EXPIRED and can never cross the write seam.
PROPOSAL_TTL_SECONDS = 15 * 60

# The canonical write-tool allow-list of D proposals. Pass 2 (V1 full
# scope) extends the T11 allow-list with the complete WRITE set of the
# final tool catalog: 193 tools with contracts derived from the frozen
# `homi-tools.v2.json` (regenerated from `04_TOOL_CATALOG_FINAL.json`
# by `_gen_write_schemas.py`). Planner tasks keep their T12-2 typed
# schemas; all other WRITEs use the generic catalog-derived validator.
PROPOSAL_TOOL_IDS: tuple[str, ...] = WRITE_TOOL_IDS

PLANNER_TASKS_CREATE_TOOL_ID = "planner.tasks.create"

PLANNER_TASKS_UPDATE_TOOL_ID = "planner.tasks.update"

PLANNER_TASKS_COMPLETE_TOOL_ID = "planner.tasks.complete"

PLANNER_TASKS_TRASH_TOOL_ID = "planner.tasks.trash"

PLANNER_TASKS_RESTORE_TOOL_ID = "planner.tasks.restore"

PLANNER_TASKS_CREATE_KIND = "WRITE"

PLANNER_TASKS_CREATE_RISK_FLAGS: tuple[str, ...] = (
    "LOW_MUTATION",
)

PLANNER_TASKS_CREATE_CONFIRMATION = "REQUIRED"

PLANNER_TASKS_CREATE_CONTRACT_VERSION = "1.1.0"

# T12-3: the four existing-task WRITE tools. They are PROPOSABLE in
# T12-3 but their CONFIRM/EXECUTION path fails closed until the later
# execution phase explicitly enables them (T12-3 sections 22 and 23).
# Pass 2: no legacy-only shapes are needed anymore; every WRITE tool has a
# generic typed contract from the frozen catalog, so nothing is excluded
# from the new WRITE path.
T12_NEW_TOOL_IDS: tuple[str, ...] = (
    PLANNER_TASKS_UPDATE_TOOL_ID,
    PLANNER_TASKS_COMPLETE_TOOL_ID,
    PLANNER_TASKS_TRASH_TOOL_ID,
    PLANNER_TASKS_RESTORE_TOOL_ID,
)

# The T12-3 confirm boundary (sections 22 and 23): a pending proposal
# of one of the four new tools can NOT be confirmed yet. The confirm
# path fails closed with PROPOSAL_CONFIRM_NOT_ENABLED and the pending
# proposal stays PROPOSED and intact. The T12 execution phase flips
# this flag (an explicit, reviewed, anchored change).
T12_CONFIRM_EXECUTION_ENABLED = False

# ---------------------------------------------------------------------------
# T12-5D — confirmation is independent from execution.
# ---------------------------------------------------------------------------
# Confirmation-capable proposal tools (lifecycle approval only). This is
# intentionally wider than the execution allow-list: the four new T12
# tools may be CONFIRMED but never EXECUTED in this phase.
T12_CONFIRMATION_TOOL_IDS: tuple[str, ...] = PROPOSAL_TOOL_IDS

T12_CONFIRMATION_CAPABLE_TOOL_IDS = T12_CONFIRMATION_TOOL_IDS
CONFIRMATION_CAPABLE_TOOL_IDS = T12_CONFIRMATION_TOOL_IDS
CONFIRMATION_TOOL_IDS = T12_CONFIRMATION_TOOL_IDS
CAN_CONFIRM_TOOL_IDS = T12_CONFIRMATION_TOOL_IDS

# Execution-capable proposal tools. Kept in sync with
# WRITE_EXECUTION_TOOL_IDS in homi_tool_write_execution.py; D-owned here
# so the proposal module never imports the write seam (which imports it).
T12_EXECUTION_TOOL_IDS: tuple[str, ...] = PROPOSAL_TOOL_IDS
EXECUTION_CAPABLE_TOOL_IDS = T12_EXECUTION_TOOL_IDS
CAN_EXECUTE_TOOL_IDS = T12_EXECUTION_TOOL_IDS

# Neutral capability helpers (conceptual CAN_CONFIRM / CAN_EXECUTE).
def can_confirm(tool_id: Any) -> bool:
    return str(tool_id) in T12_CONFIRMATION_TOOL_IDS

def can_execute(tool_id: Any) -> bool:
    return str(tool_id) in T12_EXECUTION_TOOL_IDS

CAN_CONFIRM = can_confirm
CAN_EXECUTE = can_execute

# Explicit, non-global aliases so the separation stays readable. These
# do NOT enable real mutation: execution remains gated by
# WRITE_EXECUTION_TOOL_IDS (create only).
T12_CONFIRMATION_ENABLED = True
T12_EXECUTION_ENABLED_FOR_NEW_TOOLS = True

# T12-2 risk matrix (T12-1 freeze section F): create/update/complete/
# restore are LOW_MUTATION; trash is the only MODERATE_MUTATION
# (destructive-adjacent but reversible).
T12_TOOL_RISK_FLAGS: dict[str, tuple[str, ...]] = {
    PLANNER_TASKS_UPDATE_TOOL_ID: ("LOW_MUTATION",),
    PLANNER_TASKS_COMPLETE_TOOL_ID: ("LOW_MUTATION",),
    PLANNER_TASKS_TRASH_TOOL_ID: ("MODERATE_MUTATION",),
    PLANNER_TASKS_RESTORE_TOOL_ID: ("LOW_MUTATION",),
}

# The canonical T12-2 UUID pattern (HomePlus plannerWriteTools.js).
TASK_ID_ONLY_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)

# The T11-1 execution gate. No WRITE execution path exists in T11-2.
EXECUTION_ENABLED = False

# T07 remains the final argument authority. C04 extends the D-side
# model-facing schema with the compound ``operations`` mode. The
# top-level ``required`` list is intentionally EMPTY: JSON Schema cannot
# express the two mutually-exclusive create modes with the keywords
# accepted by every deployed validator. Node D therefore applies the
# strict semantic mode gate below (simple OR compound, never mixed).
PLANNER_TASKS_CREATE_SIMPLE_PROPERTIES: Mapping[str, Any] = {
    "title": {
        "type": "string",
        "minLength": 1,
        "maxLength": 500,
    },
    "description": {
        "type": ["string", "null"],
        "maxLength": 2000,
    },
    "dueDate": {
        "type": ["string", "null"],
        "pattern": r"^\d{4}-\d{2}-\d{2}$",
    },
    "dueTime": {
        "type": ["string", "null"],
        "pattern": r"^\d{2}:\d{2}(:\d{2})?$",
    },
    "assignedToMemberId": {
        "type": ["string", "null"],
        "maxLength": 128,
    },
}

PLANNER_TASKS_CREATE_OPERATION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title"],
    "properties": copy.deepcopy(
        dict(PLANNER_TASKS_CREATE_SIMPLE_PROPERTIES),
    ),
}

PLANNER_TASKS_CREATE_INPUT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [],
    "properties": {
        **copy.deepcopy(
            dict(PLANNER_TASKS_CREATE_SIMPLE_PROPERTIES),
        ),
        "operations": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": copy.deepcopy(
                dict(PLANNER_TASKS_CREATE_OPERATION_SCHEMA),
            ),
        },
    },
}

PLANNER_TASKS_CREATE_MIN_OPERATIONS = 2

PLANNER_TASKS_CREATE_MAX_OPERATIONS = 4

# ... and anchored by this in-code trust anchor, as T09-B does for the
# READ catalogue. Any in-code change to the schema, the metadata or the
# bounds fails closed the next time the write authority is used.
# C04 reviewed re-anchor: the document now covers the five frozen
# WRITE contracts (T11-1 create + the four T12-2 tools), the per-tool
# risk matrix, the model-forbidden argument keys, the T12 confirm
# boundary and the C04 compound create schema (contract version 1.1.0).
# The digest is calculated from the canonical JSON document built by
# ``assert_proposal_authority`` below.
PROPOSAL_AUTHORITY_SHA256 = (
    "83cdcb4e3c0b848b65e57ca5ee698fd0997c32126b381d535a780ca9ccdef27a"
)

# Deterministic upper bounds for the proposal payload (T11-2).
MAX_PROPOSAL_TOOL_ARGUMENTS_BYTES = 4096
MAX_TITLE_CHARS = 500
MAX_DESCRIPTION_CHARS = 2000
MAX_ASSIGNED_MEMBER_CHARS = 128
MAX_SUMMARY_CHARS = 500
MAX_PROPOSAL_JSON_BYTES = 8192


# ---------------------------------------------------------------------------
# T12-3 — the frozen T12-2 existing-task WRITE input schemas
# ---------------------------------------------------------------------------
#
# Re-encoded in-code from the READ-ONLY T12-2 truth
# (HomePlus ``backend/src/homi/tools/plannerWriteTools.js``, tool
# contract version 1.0.0) without reinterpretation. ``taskId`` and
# ``expectedVersion`` are D-OWNED: the model may never supply either
# one (T12-3 sections 3 and 6), so the MODEL-facing patch schema is a
# strict subset of these (see MODEL_WRITE_PATCH_PROPERTIES).

# The canonical checklist item shape of the Product Truth: the
# ``planner_tasks.checklist`` JSONB column stores ``[{text, checked}]``
# and is replaced wholesale on every mutation.
T12_CHECKLIST_ITEM_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {
            "type": "string",
            "minLength": 1,
        },
        "checked": {
            "type": "boolean",
        },
    },
    "required": ["text", "checked"],
}

T12_EXPECTED_VERSION_PROPERTY: Mapping[str, Any] = {
    "type": ["integer", "null"],
    "minimum": 1,
}

PLANNER_TASKS_UPDATE_INPUT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["taskId"],
    "properties": {
        "taskId": {
            "type": "string",
            "pattern": TASK_ID_ONLY_PATTERN,
        },
        "title": {
            "type": "string",
            "minLength": 1,
        },
        "description": {
            "type": ["string", "null"],
        },
        "dueDate": {
            "type": ["string", "null"],
            "pattern": r"^\d{4}-\d{2}-\d{2}$",
        },
        "dueTime": {
            "type": ["string", "null"],
            "pattern": r"^\d{2}:\d{2}(:\d{2})?$",
        },
        "assignedToMemberId": {
            "type": ["string", "null"],
            "pattern": TASK_ID_ONLY_PATTERN,
        },
        "priority": {
            "type": "string",
        },
        "category": {
            "type": ["string", "null"],
        },
        "templateKey": {
            "type": ["string", "null"],
        },
        "estimatedDurationMinutes": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 10080,
        },
        "requiresVerification": {
            "type": "boolean",
        },
        "checklist": {
            "type": ["array", "null"],
            "items": T12_CHECKLIST_ITEM_SCHEMA,
        },
        "goalId": {
            "type": ["string", "null"],
            "pattern": TASK_ID_ONLY_PATTERN,
        },
        "planClassification": {
            "type": ["string", "null"],
            "enum": ["necessary", "supporting"],
        },
        "expectedVersion": T12_EXPECTED_VERSION_PROPERTY,
    },
}

PLANNER_TASKS_LIFECYCLE_INPUT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["taskId"],
    "properties": {
        "taskId": {
            "type": "string",
            "pattern": TASK_ID_ONLY_PATTERN,
        },
        "expectedVersion": T12_EXPECTED_VERSION_PROPERTY,
    },
}

# The model-facing patch subset of the update schema. The model NEVER
# supplies ``taskId`` (target resolution is D-owned), ``expectedVersion``
# (D injects it from the trusted preflight READ) or ``checklist`` (the
# checklist intent travels as the additive ``checklist_patch`` and D
# owns the read-modify-write transform).
MODEL_WRITE_FORBIDDEN_ARGUMENT_KEYS: tuple[str, ...] = (
    "taskId",
    "expectedVersion",
    "checklist",
    "status",
    "version",
    "trashedAt",
    "trashed_at",
    "householdId",
    "household_id",
    "createdByMemberId",
    "created_by_member_id",
)

MODEL_WRITE_PATCH_PROPERTIES: Mapping[str, Any] = {
    "title": {
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_TITLE_CHARS,
    },
    "description": {
        "type": ["string", "null"],
        "maxLength": MAX_DESCRIPTION_CHARS,
    },
    "dueDate": {
        "type": ["string", "null"],
        "pattern": r"^\d{4}-\d{2}-\d{2}$",
    },
    "dueTime": {
        "type": ["string", "null"],
        "pattern": r"^\d{2}:\d{2}(:\d{2})?$",
    },
    "assignedToMemberId": {
        "type": ["string", "null"],
        "pattern": TASK_ID_ONLY_PATTERN,
        "maxLength": MAX_ASSIGNED_MEMBER_CHARS,
    },
    "priority": {"type": "string"},
    "category": {"type": ["string", "null"]},
    "templateKey": {"type": ["string", "null"]},
    "estimatedDurationMinutes": {
        "type": ["integer", "null"],
        "minimum": 1,
        "maximum": 10080,
    },
    "requiresVerification": {"type": "boolean"},
    "goalId": {
        "type": ["string", "null"],
        "pattern": TASK_ID_ONLY_PATTERN,
    },
    "planClassification": {
        "type": ["string", "null"],
        "enum": ["necessary", "supporting"],
    },
}


@dataclass(frozen=True)
class WriteToolContract:
    """Trusted, D-owned metadata of one canonical WRITE tool."""

    tool_id: str
    kind: str
    risk_flags: tuple[str, ...]
    confirmation: str
    contract_version: str
    input_schema: Mapping[str, Any]
    execution_enabled: bool
    domain_binding: str = ""


PLANNER_TASKS_UPDATE_DOMAIN_BINDING = (
    "backend/src/services/planner.tasks.service.js :: updateTask / "
    "buildTaskPatch; HTTP backing route: PATCH /api/planner/tasks/:id; "
    "capability: task.edit_own (creator) or task.edit_any (non-creator)"
)

PLANNER_TASKS_COMPLETE_DOMAIN_BINDING = (
    "backend/src/services/planner.tasks.service.js :: completeTask; "
    "HTTP backing route: POST /api/planner/tasks/:id/complete; "
    "capability: task.complete_assigned/complete_unassigned/"
    "complete_any"
)

PLANNER_TASKS_TRASH_DOMAIN_BINDING = (
    "backend/src/services/planner.tasks.service.js :: trashTask; "
    "HTTP backing route: POST /api/planner/tasks/:id/trash; "
    "capability: task.restore"
)

PLANNER_TASKS_RESTORE_DOMAIN_BINDING = (
    "backend/src/services/planner.tasks.service.js :: restoreTask; "
    "HTTP backing route: POST /api/planner/tasks/:id/restore; "
    "capability: task.restore"
)

PLANNER_TASKS_CREATE_DOMAIN_BINDING_VALUE = (
    "backend/src/services/planner.tasks.service.js :: "
    "createTask(context, body, correlation); "
    "HTTP backing route: POST /api/planner/tasks; "
    "capability: task.create_household"
)

PLANNER_TASKS_CREATE_DOMAIN_BINDING = (
    PLANNER_TASKS_CREATE_DOMAIN_BINDING_VALUE
)


PLANNER_TASKS_WRITE_TOOL_IDS: frozenset[str] = frozenset(
    {
        PLANNER_TASKS_CREATE_TOOL_ID,
        PLANNER_TASKS_UPDATE_TOOL_ID,
        PLANNER_TASKS_COMPLETE_TOOL_ID,
        PLANNER_TASKS_TRASH_TOOL_ID,
        PLANNER_TASKS_RESTORE_TOOL_ID,
    }
)

# Generic contracts for every non-planner WRITE tool, derived from the
# frozen catalog (`homi_write_schemas.WRITE_CONTRACTS`). Risk flags and
# input schemas come from the frozen artifacts; execution stays enabled.
_GENERIC_TOOL_CONTRACTS: Mapping[str, WriteToolContract] = {
    tool_id: WriteToolContract(
        tool_id=tool_id,
        kind="WRITE",
        risk_flags=tuple(contract["risk_flags"]),
        confirmation="REQUIRED",
        contract_version="2.0.0",
        input_schema=contract["input_schema"],
        execution_enabled=True,
        domain_binding=str(contract.get("domain_binding", "")),
    )
    for tool_id, contract in sorted(WRITE_CONTRACTS.items())
    if tool_id not in PLANNER_TASKS_WRITE_TOOL_IDS
}

_TOOL_CONTRACTS: Mapping[str, WriteToolContract] = {
    **_GENERIC_TOOL_CONTRACTS,
    PLANNER_TASKS_CREATE_TOOL_ID: WriteToolContract(
        tool_id=PLANNER_TASKS_CREATE_TOOL_ID,
        kind=PLANNER_TASKS_CREATE_KIND,
        risk_flags=PLANNER_TASKS_CREATE_RISK_FLAGS,
        confirmation=PLANNER_TASKS_CREATE_CONFIRMATION,
        contract_version=PLANNER_TASKS_CREATE_CONTRACT_VERSION,
        input_schema=PLANNER_TASKS_CREATE_INPUT_SCHEMA,
        execution_enabled=False,
        domain_binding=PLANNER_TASKS_CREATE_DOMAIN_BINDING_VALUE,
    ),
    PLANNER_TASKS_UPDATE_TOOL_ID: WriteToolContract(
        tool_id=PLANNER_TASKS_UPDATE_TOOL_ID,
        kind="WRITE",
        risk_flags=T12_TOOL_RISK_FLAGS[
            PLANNER_TASKS_UPDATE_TOOL_ID
        ],
        confirmation="REQUIRED",
        contract_version="1.0.0",
        input_schema=PLANNER_TASKS_UPDATE_INPUT_SCHEMA,
        execution_enabled=False,
        domain_binding=PLANNER_TASKS_UPDATE_DOMAIN_BINDING,
    ),
    PLANNER_TASKS_COMPLETE_TOOL_ID: WriteToolContract(
        tool_id=PLANNER_TASKS_COMPLETE_TOOL_ID,
        kind="WRITE",
        risk_flags=T12_TOOL_RISK_FLAGS[
            PLANNER_TASKS_COMPLETE_TOOL_ID
        ],
        confirmation="REQUIRED",
        contract_version="1.0.0",
        input_schema=PLANNER_TASKS_LIFECYCLE_INPUT_SCHEMA,
        execution_enabled=False,
        domain_binding=PLANNER_TASKS_COMPLETE_DOMAIN_BINDING,
    ),
    PLANNER_TASKS_TRASH_TOOL_ID: WriteToolContract(
        tool_id=PLANNER_TASKS_TRASH_TOOL_ID,
        kind="WRITE",
        risk_flags=T12_TOOL_RISK_FLAGS[
            PLANNER_TASKS_TRASH_TOOL_ID
        ],
        confirmation="REQUIRED",
        contract_version="1.0.0",
        input_schema=PLANNER_TASKS_LIFECYCLE_INPUT_SCHEMA,
        execution_enabled=False,
        domain_binding=PLANNER_TASKS_TRASH_DOMAIN_BINDING,
    ),
    PLANNER_TASKS_RESTORE_TOOL_ID: WriteToolContract(
        tool_id=PLANNER_TASKS_RESTORE_TOOL_ID,
        kind="WRITE",
        risk_flags=T12_TOOL_RISK_FLAGS[
            PLANNER_TASKS_RESTORE_TOOL_ID
        ],
        confirmation="REQUIRED",
        contract_version="1.0.0",
        input_schema=PLANNER_TASKS_LIFECYCLE_INPUT_SCHEMA,
        execution_enabled=False,
        domain_binding=PLANNER_TASKS_RESTORE_DOMAIN_BINDING,
    ),
}


def write_tool_contract(
    tool_id: str,
) -> WriteToolContract | None:
    """The trusted contract of a canonical WRITE tool, or None."""

    return _TOOL_CONTRACTS.get(tool_id)


def assert_proposal_authority() -> None:
    """Fail closed when the in-code write authority was modified.

    T11-2 anchored the T11-1 ``planner.tasks.create`` schema, the
    trusted metadata and the deterministic bounds. T12-3 extends the
    anchored document additively with the four frozen T12-2 contracts
    (update / complete / trash / restore), their per-tool risk matrix
    (trash = MODERATE_MUTATION), the D-owned fields the model may
    never supply and the confirm-disabled boundary of the four new
    tools. Any unreviewed change to any anchored constant fails
    closed here.
    """

    def _contract_document(tool_id: str) -> dict[str, Any]:
        contract = _TOOL_CONTRACTS[tool_id]

        return {
            "kind": contract.kind,
            "risk_flags": list(contract.risk_flags),
            "confirmation": contract.confirmation,
            "contract_version": contract.contract_version,
            "execution_enabled": contract.execution_enabled,
            "input_schema": json.loads(
                json.dumps(contract.input_schema),
            ),
        }

    document = {
        "proposal_version": PROPOSAL_VERSION,
        "tool_ids": list(PROPOSAL_TOOL_IDS),
        "t12_confirm_enabled": T12_CONFIRM_EXECUTION_ENABLED,
        "tools": {
            tool_id: _contract_document(tool_id)
            for tool_id in PROPOSAL_TOOL_IDS
        },
        "model_forbidden_argument_keys": list(
            MODEL_WRITE_FORBIDDEN_ARGUMENT_KEYS,
        ),
        "model_write_patch_properties": json.loads(
            json.dumps(MODEL_WRITE_PATCH_PROPERTIES),
        ),
        "bounds": {
            "max_title_chars": MAX_TITLE_CHARS,
            "max_description_chars": MAX_DESCRIPTION_CHARS,
            "max_assigned_member_chars": (
                MAX_ASSIGNED_MEMBER_CHARS
            ),
            "max_summary_chars": MAX_SUMMARY_CHARS,
            "max_proposal_json_bytes": (
                MAX_PROPOSAL_JSON_BYTES
            ),
            "max_tool_arguments_bytes": (
                MAX_PROPOSAL_TOOL_ARGUMENTS_BYTES
            ),
        },
    }

    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    digest = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    if digest != PROPOSAL_AUTHORITY_SHA256.lower():
        raise ActionProposalError(
            "PROPOSAL_AUTHORITY_ANCHOR_MISMATCH",
            "the in-code write authority does not match the "
            f"trust anchor: {digest}",
        )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ActionProposalError(ValueError):
    """Fail-closed error of the T11-2 proposal layer."""

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


# ---------------------------------------------------------------------------
# Identity / credential boundary
# ---------------------------------------------------------------------------

# The proposal surface must never carry identity, credential or transport
# control fields. Identity stays in the RequestContext; the credential
# stays in the request-local executor context that is NOT part of T11-2.
PROPOSAL_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "actor_id",
        "household_id",
        "membership_id",
        "auth_user_id",
        "created_by",
        "jwt",
        "authorization",
        "access_token",
        "role",
        "token",
        "bearer",
        "password",
        "secret",
        "api_key",
        "url",
        "endpoint",
        "host",
    }
)


def _normalized_key(
    key: str,
) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        key.lower(),
    )


PROPOSAL_FORBIDDEN_KEYS_NORMALIZED = frozenset(
    _normalized_key(key)
    for key in PROPOSAL_FORBIDDEN_KEYS
)


def is_forbidden_proposal_key(
    key: str,
) -> bool:
    """Whether a key is an identity/credential/transport field."""

    if key in PROPOSAL_FORBIDDEN_KEYS:
        return True

    return (
        _normalized_key(key)
        in PROPOSAL_FORBIDDEN_KEYS_NORMALIZED
    )


# ---------------------------------------------------------------------------
# Argument validation (strict, no coercion, no silent changes)
# ---------------------------------------------------------------------------

_DUE_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}$",
)

_DUE_TIME_PATTERN = re.compile(
    r"^\d{2}:\d{2}(:\d{2})?$",
)


_CREATE_SIMPLE_ARGUMENT_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "dueDate",
        "dueTime",
        "assignedToMemberId",
    },
)


def is_compound_create_arguments(
    arguments: Any,
) -> bool:
    """Whether the create arguments select the compound mode."""

    return (
        isinstance(arguments, Mapping)
        and "operations" in arguments
    )


def _validate_compound_create_arguments(
    arguments: Mapping[str, Any],
) -> list[str]:
    """Validate the complete compound create batch, without coercion."""

    violations: list[str] = []

    mixed_fields = sorted(
        key
        for key in arguments
        if key in _CREATE_SIMPLE_ARGUMENT_FIELDS
    )

    if mixed_fields:
        violations.append("mixed_create_modes")

    for key in sorted(arguments):
        if (
            key != "operations"
            and key not in _CREATE_SIMPLE_ARGUMENT_FIELDS
        ):
            violations.append(f"unknown_argument:{key}")

        if is_forbidden_proposal_key(key):
            violations.append(f"forbidden_key:{key}")

    operations = arguments.get("operations")

    if not isinstance(operations, list):
        violations.append("invalid_type:operations")

        return _dedupe(violations)

    if len(operations) < PLANNER_TASKS_CREATE_MIN_OPERATIONS:
        violations.append("too_few_operations")

    if len(operations) > PLANNER_TASKS_CREATE_MAX_OPERATIONS:
        violations.append("too_many_operations")

    # Validate EVERY item before a proposal can exist. A malformed item
    # never becomes a partial proposal and can never reach the seam.
    for index, operation in enumerate(operations):
        prefix = f"operations[{index}]."

        if not (
            isinstance(operation, Mapping)
            and all(
                isinstance(key, str)
                for key in operation
            )
        ):
            violations.append(
                f"invalid_type:operations[{index}]"
            )
            continue

        for key in sorted(operation):
            if key not in _CREATE_SIMPLE_ARGUMENT_FIELDS:
                violations.append(
                    f"unknown_argument:{prefix}{key}"
                )

            if is_forbidden_proposal_key(key):
                violations.append(
                    f"forbidden_key:{prefix}{key}"
                )

        if "title" not in operation:
            violations.append(
                f"missing_required:{prefix}title"
            )

        if "title" in operation:
            title = operation["title"]

            if not isinstance(title, str):
                violations.append(
                    f"invalid_type:{prefix}title"
                )
            else:
                if len(title) < 1 or not title.strip():
                    violations.append(
                        f"too_short:{prefix}title"
                    )

                if len(title) > MAX_TITLE_CHARS:
                    violations.append(
                        f"too_long:{prefix}title"
                    )

        if "description" in operation:
            description = operation["description"]

            if description is not None and not isinstance(
                description, str
            ):
                violations.append(
                    f"invalid_type:{prefix}description"
                )
            elif isinstance(description, str):
                if len(description) > MAX_DESCRIPTION_CHARS:
                    violations.append(
                        f"too_long:{prefix}description"
                    )

        if "dueDate" in operation:
            due_date = operation["dueDate"]

            if due_date is not None and not isinstance(
                due_date, str
            ):
                violations.append(
                    f"invalid_type:{prefix}dueDate"
                )
            elif isinstance(due_date, str):
                if _DUE_DATE_PATTERN.match(due_date) is None:
                    violations.append(
                        f"pattern_mismatch:{prefix}dueDate"
                    )
                elif not _is_valid_calendar_date(due_date):
                    violations.append(
                        f"invalid_date:{prefix}dueDate"
                    )

        if "dueTime" in operation:
            due_time = operation["dueTime"]

            if due_time is not None and not isinstance(
                due_time, str
            ):
                violations.append(
                    f"invalid_type:{prefix}dueTime"
                )
            elif isinstance(due_time, str):
                if _DUE_TIME_PATTERN.match(due_time) is None:
                    violations.append(
                        f"pattern_mismatch:{prefix}dueTime"
                    )
                elif not _is_valid_wall_clock_time(due_time):
                    violations.append(
                        f"invalid_date:{prefix}dueTime"
                    )

        if "assignedToMemberId" in operation:
            member_id = operation["assignedToMemberId"]

            if member_id is not None and not isinstance(
                member_id, str
            ):
                violations.append(
                    f"invalid_type:{prefix}assignedToMemberId"
                )
            elif isinstance(member_id, str):
                if len(member_id) > MAX_ASSIGNED_MEMBER_CHARS:
                    violations.append(
                        f"too_long:{prefix}assignedToMemberId"
                    )

        if (
            "dueTime" in operation
            and operation["dueTime"] is not None
            and operation.get("dueDate") is None
        ):
            violations.append(
                f"{prefix}due_time_without_due_date"
            )

    return _dedupe(violations)


def validate_proposal_arguments(
    arguments: Any,
) -> list[str]:
    """Deterministic strict validation of proposal arguments.

    ``planner.tasks.create`` has exactly two mutually-exclusive modes:
    one simple create body, or ``operations`` with 2..4 simple bodies.
    The compound mode never mixes top-level simple fields. Every item
    is validated before a proposal or a write can exist. Nothing is
    coerced and nothing is changed.
    """

    violations: list[str] = []

    if not (
        isinstance(arguments, Mapping)
        and all(isinstance(key, str) for key in arguments)
    ):
        return [
            "arguments_not_object",
        ]

    tool = _TOOL_CONTRACTS[PLANNER_TASKS_CREATE_TOOL_ID]

    if is_compound_create_arguments(arguments):
        violations.extend(
            _validate_compound_create_arguments(arguments)
        )

        try:
            canonical = proposal_arguments_json(
                dict(arguments),
            )

        except (TypeError, ValueError):
            violations.append("arguments_not_serializable")

        else:
            if len(canonical.encode("utf-8")) > (
                MAX_PROPOSAL_TOOL_ARGUMENTS_BYTES
            ):
                violations.append("arguments_too_large")

        return _dedupe(violations)

    properties = tool.input_schema["properties"]

    for key in sorted(arguments):
        if key not in properties:
            violations.append(f"unknown_argument:{key}")

        if is_forbidden_proposal_key(key):
            violations.append(f"forbidden_key:{key}")

    # The model-facing schema has no top-level required field because it
    # also describes the compound mode. The simple mode still requires
    # title in D's semantic validation.
    for name in ("title",):
        if name not in arguments:
            violations.append(f"missing_required:{name}")

    if "title" in arguments:
        value = arguments["title"]

        if not isinstance(value, str):
            violations.append("invalid_type:title")
        else:
            if len(value) < 1 or not value.strip():
                violations.append("too_short:title")

            if len(value) > MAX_TITLE_CHARS:
                violations.append("too_long:title")

    if "description" in arguments:
        value = arguments["description"]

        if value is not None and not isinstance(
            value, str
        ):
            violations.append(
                "invalid_type:description"
            )
        elif isinstance(value, str):
            if len(value) > MAX_DESCRIPTION_CHARS:
                violations.append(
                    "too_long:description"
                )

    if "dueDate" in arguments:
        value = arguments["dueDate"]

        if value is not None and not isinstance(
            value, str
        ):
            violations.append("invalid_type:dueDate")
        elif isinstance(value, str):
            if _DUE_DATE_PATTERN.match(value) is None:
                violations.append(
                    "pattern_mismatch:dueDate"
                )
            elif not _is_valid_calendar_date(value):
                violations.append(
                    "invalid_date:dueDate"
                )

    if "dueTime" in arguments:
        value = arguments["dueTime"]

        if value is not None and not isinstance(
            value, str
        ):
            violations.append("invalid_type:dueTime")
        elif isinstance(value, str):
            if _DUE_TIME_PATTERN.match(value) is None:
                violations.append(
                    "pattern_mismatch:dueTime"
                )
            elif not _is_valid_wall_clock_time(value):
                violations.append(
                    "invalid_date:dueTime"
                )

    if "assignedToMemberId" in arguments:
        value = arguments["assignedToMemberId"]

        if value is not None and not isinstance(
            value, str
        ):
            violations.append(
                "invalid_type:assignedToMemberId"
            )
        elif isinstance(value, str):
            if len(value) > MAX_ASSIGNED_MEMBER_CHARS:
                violations.append(
                    "too_long:assignedToMemberId"
                )

    # dueTime requires dueDate in the T11-1 contract.
    if (
        "dueTime" in arguments
        and arguments["dueTime"] is not None
        and arguments.get("dueDate") is None
    ):
        violations.append("due_time_without_due_date")

    try:
        canonical = proposal_arguments_json(
            dict(arguments),
        )

    except (TypeError, ValueError):
        violations.append("arguments_not_serializable")

    else:
        if len(canonical.encode("utf-8")) > (
            MAX_PROPOSAL_TOOL_ARGUMENTS_BYTES
        ):
            violations.append("arguments_too_large")

    ordered: list[str] = []

    for violation in violations:
        if violation not in ordered:
            ordered.append(violation)

    return ordered


def _is_valid_calendar_date(
    value: str,
) -> bool:
    """Whether the string is a valid calendar YYYY-MM-DD date.

    The T11-1 pattern alone would accept ``2026-13-45``. The calendar
    check is a deterministic, fail-closed refinement, not a coercion.
    """

    try:
        datetime.strptime(value, "%Y-%m-%d")

    except ValueError:
        return False

    return True


def _is_valid_wall_clock_time(
    value: str,
) -> bool:
    """Whether the string is a valid HH:MM or HH:MM:SS clock time."""

    fields = value.split(":")

    if not 2 <= len(fields) <= 3:
        return False

    hours, minutes = int(fields[0]), int(fields[1])

    if hours > 23:
        return False

    if minutes > 59:
        return False

    if len(fields) == 3:
        seconds = int(fields[2])

        if seconds > 59:
            return False

    return True


def proposal_arguments_json(
    arguments: Mapping[str, Any],
) -> str:
    """The deterministic canonical serialization of the arguments."""

    return json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).strip()


# ---------------------------------------------------------------------------
# T12-3 — per-tool WRITE argument validation (strict, no coercion)
# ---------------------------------------------------------------------------


def _check_t12_primitive(
    name: str,
    value: Any,
    schema: Mapping[str, Any],
) -> list[str]:
    """The deterministic primitive checks of one T12 argument.

    Mirrors the checks ``homi_tool_contract._check_primitive`` performs
    for the READ catalogue (type, enum, minimum, maximum, minLength,
    pattern) so the T12 tools get the same fail-closed style.
    """

    violations: list[str] = []

    declared_type = schema.get("type")

    if declared_type is not None:
        types = (
            declared_type
            if isinstance(declared_type, list)
            else [declared_type]
        )

        matched = False

        for candidate in types:
            if candidate == "string" and isinstance(value, str):
                matched = True
            elif candidate == "boolean" and isinstance(
                value,
                bool,
            ):
                matched = True
            elif candidate == "integer" and (
                isinstance(value, int)
                and not isinstance(value, bool)
            ):
                matched = True
            elif candidate == "null" and value is None:
                matched = True
            elif candidate == "array" and isinstance(
                value,
                list,
            ):
                matched = True

        if not matched:
            violations.append(f"invalid_type:{name}")

            return violations

    enum_values = schema.get("enum")

    if (
        isinstance(enum_values, list)
        and value not in enum_values
    ):
        violations.append(f"not_in_enum:{name}")

    minimum = schema.get("minimum")

    if (
        isinstance(minimum, (int, float))
        and not isinstance(minimum, bool)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value < minimum
    ):
        violations.append(f"below_minimum:{name}")

    maximum = schema.get("maximum")

    if (
        isinstance(maximum, (int, float))
        and not isinstance(maximum, bool)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > maximum
    ):
        violations.append(f"above_maximum:{name}")

    min_length = schema.get("minLength")

    if (
        isinstance(min_length, int)
        and not isinstance(min_length, bool)
        and isinstance(value, str)
        and len(value) < min_length
    ):
        violations.append(f"too_short:{name}")

    max_length = schema.get("maxLength")

    if (
        isinstance(max_length, int)
        and not isinstance(max_length, bool)
        and isinstance(value, str)
        and len(value) > max_length
    ):
        violations.append(f"too_long:{name}")

    pattern = schema.get("pattern")

    if (
        isinstance(pattern, str)
        and isinstance(value, str)
        and re.search(pattern, value) is None
    ):
        violations.append(f"pattern_mismatch:{name}")

    return violations


def _validate_t12_checklist(
    value: Any,
) -> list[str]:
    """Strict whole-array checklist validation (T12-2 item shape)."""

    if not isinstance(value, list):
        return ["invalid_type:checklist"]

    violations: list[str] = []

    for position, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            violations.append(
                f"invalid_type:checklist[{position}]"
            )

            continue

        unknown = sorted(
            key
            for key in entry
            if key not in ("text", "checked")
        )

        for key in unknown:
            violations.append(
                f"unknown_argument:checklist[{position}].{key}"
            )

        text = entry.get("text")

        if not isinstance(text, str):
            violations.append(
                f"invalid_type:checklist[{position}].text"
            )
        elif not text.strip():
            violations.append(
                f"too_short:checklist[{position}].text"
            )

        if not isinstance(entry.get("checked"), bool):
            violations.append(
                f"invalid_type:checklist[{position}].checked"
            )

    return violations


def validate_model_write_arguments(
    tool_id: str,
    arguments: Any,
) -> list[str]:
    """Validate the MODEL-supplied patch of a T12 existing-task WRITE.

    The model expresses the user-intended DELTA only:

    * ``complete`` / ``trash`` / ``restore`` accept an EMPTY object
      (no mutable body fields exist; the target identifies the task);
    * ``update`` accepts the strict patch subset
      (MODEL_WRITE_PATCH_PROPERTIES) — never ``taskId`` (D owns target
      resolution), never ``expectedVersion`` (D owns the concurrency
      token), never ``checklist`` (the checklist intent travels as the
      additive ``checklist_patch``; D owns the read-modify-write) and
      never ``status`` (not patchable by the Product Truth).

    A time-without-date patch is VALID here: the deterministic merge
    with the authoritative due date (or the clarify when none exists)
    belongs to the loop, not to the model gate.
    """

    violations: list[str] = []

    if not isinstance(arguments, Mapping):
        return ["arguments_not_object"]

    if tool_id == PLANNER_TASKS_UPDATE_TOOL_ID:
        properties = MODEL_WRITE_PATCH_PROPERTIES

        for key in sorted(arguments):
            if key not in properties:
                violations.append(f"unknown_argument:{key}")

            if key in MODEL_WRITE_FORBIDDEN_ARGUMENT_KEYS:
                violations.append(
                    f"forbidden_argument:{key}"
                )

            if is_forbidden_proposal_key(key):
                violations.append(f"forbidden_key:{key}")

        mutation_fields = [
            key
            for key in arguments
            if key in properties
        ]

        if not mutation_fields:
            violations.append("empty_update_patch")

        for name in sorted(arguments):
            if name not in properties:
                continue

            violations.extend(
                _check_t12_primitive(
                    name,
                    arguments[name],
                    properties[name],
                )
            )

            if name in ("dueDate",) and isinstance(
                arguments[name],
                str,
            ):
                if not _is_valid_calendar_date(arguments[name]):
                    violations.append("invalid_date:dueDate")

            if name == "dueTime" and isinstance(
                arguments[name],
                str,
            ):
                if not _is_valid_wall_clock_time(arguments[name]):
                    violations.append("invalid_date:dueTime")

            if name == "title" and isinstance(
                arguments[name],
                str,
            ) and not arguments[name].strip():
                violations.append("invalid_patch:title")

        return _dedupe(violations)

    # complete / trash / restore: strict empty-object lifecycle body.
    for key in sorted(arguments):
        violations.append(f"unexpected_argument:{key}")

    return _dedupe(violations)


def validate_write_tool_arguments(
    tool_id: str,
    arguments: Any,
) -> list[str]:
    """Validate the FINAL canonical arguments of a T12 WRITE proposal.

    These are the arguments D built after target resolution, the
    trusted preflight READ and the deterministic merges:

    * every tool: ``taskId`` is a canonical UUID and
      ``expectedVersion`` is an integer >= 1 — both D-OWNED (the model
      can never supply them; T12-3 section 6);
    * ``update``: at least one mutation field besides
      taskId/expectedVersion; the strict T12-2 patch fields only;
      ``dueTime`` requires a non-null ``dueDate`` (Product Truth
      invariant; the loop already merged the authoritative date);
      the ``checklist`` is the complete resulting array of the
      deterministic read-modify-write;
    * ``complete`` / ``trash`` / ``restore``: EXACTLY taskId +
      expectedVersion (the T12-2 strict empty-object lifecycle body).
    """

    if tool_id == PLANNER_TASKS_CREATE_TOOL_ID:
        return validate_proposal_arguments(arguments)

    if tool_id not in PROPOSAL_TOOL_IDS:
        return ["unknown_tool"]

    if tool_id not in T12_NEW_TOOL_IDS and tool_id not in PLANNER_TASKS_WRITE_TOOL_IDS:
        # Generic WRITE (Pass 2): validate against the frozen catalog schema.
        return generic_validate_arguments(tool_id, arguments)

    violations: list[str] = []

    if not isinstance(arguments, Mapping):
        return ["arguments_not_object"]

    contract = _TOOL_CONTRACTS[tool_id]

    schema_properties = contract.input_schema["properties"]

    for key in sorted(arguments):
        if key not in schema_properties:
            violations.append(f"unknown_argument:{key}")

        if is_forbidden_proposal_key(key):
            violations.append(f"forbidden_key:{key}")

    for name in ("taskId", "expectedVersion"):
        if name not in arguments:
            violations.append(f"missing_required:{name}")

    if "taskId" in arguments:
        task_id = arguments["taskId"]

        if not isinstance(task_id, str):
            violations.append("invalid_type:taskId")
        elif re.search(TASK_ID_ONLY_PATTERN, task_id) is None:
            violations.append("pattern_mismatch:taskId")

    if "expectedVersion" in arguments:
        version = arguments["expectedVersion"]

        if not isinstance(version, int) or isinstance(
            version,
            bool,
        ):
            violations.append("invalid_type:expectedVersion")
        elif version < 1:
            violations.append(
                "below_minimum:expectedVersion"
            )

    if tool_id == PLANNER_TASKS_UPDATE_TOOL_ID:
        mutation_fields = [
            key
            for key in arguments
            if key not in ("taskId", "expectedVersion")
        ]

        if not mutation_fields:
            violations.append("empty_update_patch")

        for name in sorted(arguments):
            if name not in schema_properties:
                continue

            if name == "checklist":
                violations.extend(
                    _validate_t12_checklist(arguments[name])
                )

                continue

            violations.extend(
                _check_t12_primitive(
                    name,
                    arguments[name],
                    schema_properties[name],
                )
            )

            if name == "dueDate" and isinstance(
                arguments[name],
                str,
            ):
                if not _is_valid_calendar_date(arguments[name]):
                    violations.append("invalid_date:dueDate")

            if name == "dueTime" and isinstance(
                arguments[name],
                str,
            ):
                if not _is_valid_wall_clock_time(arguments[name]):
                    violations.append("invalid_date:dueTime")

            if name == "title" and isinstance(
                arguments[name],
                str,
            ) and not arguments[name].strip():
                violations.append("invalid_patch:title")

        if (
            "dueTime" in arguments
            and arguments["dueTime"] is not None
            and arguments.get("dueDate") is None
        ):
            violations.append("due_time_without_due_date")

    else:
        # complete / trash / restore: the strict T12-2 lifecycle body
        # is EXACTLY taskId + expectedVersion. Any other key was
        # already reported as unknown_argument by the schema loop
        # above; no second code is emitted.
        pass

    try:
        canonical = proposal_arguments_json(
            dict(arguments),
        )

    except (TypeError, ValueError):
        violations.append("arguments_not_serializable")

    else:
        if len(canonical.encode("utf-8")) > (
            MAX_PROPOSAL_TOOL_ARGUMENTS_BYTES
        ):
            violations.append("arguments_too_large")

    return _dedupe(violations)


def _dedupe(
    violations: list[str],
) -> list[str]:
    ordered: list[str] = []

    for violation in violations:
        if violation not in ordered:
            ordered.append(violation)

    return ordered


# ---------------------------------------------------------------------------
# Argument snapshot projection (anti-injection, deterministic)
# ---------------------------------------------------------------------------

_ARGUMENT_SANITIZE = re.compile(
    r"[\x00-\x1f\x7f\ud800-\udfff]",
)


def _plain(
    value: str,
) -> str:
    """Sanitize one user text for the D representation.

    User text stays DATA: it is only stripped of control characters. No
    markdown, HTML or URL is interpreted and nothing is executed, so a
    hostile string remains plain data in the proposal.
    """

    return _ARGUMENT_SANITIZE.sub("", value)


def proposal_summary(
    arguments: Mapping[str, Any],
) -> str:
    """The human-facing summary derived ONLY from the arguments.

    Deterministic, plain text, no model call. Only facts actually
    present are included. The output is presentation metadata and never
    execution authority.
    """

    if is_compound_create_arguments(arguments):
        operations = arguments.get("operations")

        if not isinstance(operations, list) or not operations:
            return "Crear tareas"

        header = f"Crear {len(operations)} tareas"
        prefixes = [
            f"{index}. Título: "
            for index in range(1, len(operations) + 1)
        ]

        # Every task receives a visible line. Long titles may be
        # abbreviated, but no task may disappear from the summary.
        fixed_chars = len(header) + max(
            0,
            len(operations) - 1,
        ) + sum(len(prefix) for prefix in prefixes)

        available = max(
            len(operations),
            MAX_SUMMARY_CHARS - fixed_chars,
        )

        per_title = max(1, available // len(operations))

        lines = [header]

        for index, (prefix, operation) in enumerate(
            zip(prefixes, operations),
            start=1,
        ):
            title = (
                operation.get("title")
                if isinstance(operation, Mapping)
                else None
            )

            plain_title = _plain(
                title if isinstance(title, str) else "(sin título)"
            )

            if len(plain_title) > per_title:
                plain_title = (
                    plain_title[: max(1, per_title - 1)] + "…"
                )

            lines.append(prefix + plain_title)

        summary = "\n".join(lines)

        if len(summary) > MAX_SUMMARY_CHARS:
            summary = summary[: MAX_SUMMARY_CHARS - 1] + "…"

        return summary

    lines: list[str] = ["Crear tarea"]

    if "title" in arguments:
        lines.append(
            "Título: "
            + _plain(str(arguments["title"]))
        )

    if "description" in arguments:
        value = arguments["description"]

        if value is not None:
            lines.append(
                "Descripción: "
                + _plain(str(value))
            )

    if "dueDate" in arguments:
        value = arguments["dueDate"]

        if value is not None:
            lines.append(
                "Fecha: "
                + _format_date_human(str(value))
            )

    if "dueTime" in arguments:
        value = arguments["dueTime"]

        if value is not None:
            lines.append(
                "Hora: "
                + str(value)[:5]
            )

    if "assignedToMemberId" in arguments:
        value = arguments["assignedToMemberId"]

        if value is not None:
            lines.append(
                "Asignada a: "
                + _plain(str(value))
            )

    summary = "\n".join(lines)

    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 1] + "…"

    return summary


def _format_date_human(
    value: str,
) -> str:
    """``2026-10-23`` -> ``23/10/2026`` (deterministic)."""

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d",
        )

    except ValueError:
        return value

    return parsed.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# T12-3 — deterministic per-tool proposal summaries
# ---------------------------------------------------------------------------

# The canonical Spanish operation words of the checklist intent
# (T12-3 section 20). Presentation metadata only, never authority.
_CHECKLIST_OP_WORDS = {
    "add": "Agregar",
    "edit": "Cambiar",
    "complete": "Completar",
    "reopen": "Reabrir",
    "remove": "Quitar",
}


def t12_proposal_summary(
    tool_id: str,
    arguments: Mapping[str, Any],
    summary_context: Mapping[str, Any] | None,
) -> str:
    """The deterministic user-readable summary of a T12 WRITE proposal.

    The summary is derived ONLY from the canonical proposal arguments
    and the D-owned summary context (the authoritative task title from
    the trusted preflight READ and the resolved checklist intent).
    The model never generates the authoritative summary text.

    Examples (T12-3 section 20)::

        Actualizar tarea
        Título: Comprar materiales
        Fecha: 30/10/2026

        Completar tarea
        Comprar materiales

        Mover a papelera
        Comprar materiales

        Restaurar tarea
        Comprar materiales

        Checklist
        Agregar "Comprar cartulina"
        a "Preparar maqueta"
    """

    context = summary_context or {}

    task_title = context.get("task_title")

    checklist_op = context.get("checklist_op")

    if tool_id == PLANNER_TASKS_COMPLETE_TOOL_ID:
        lines = ["Completar tarea"]

    elif tool_id == PLANNER_TASKS_TRASH_TOOL_ID:
        lines = ["Mover a papelera"]

    elif tool_id == PLANNER_TASKS_RESTORE_TOOL_ID:
        lines = ["Restaurar tarea"]

    elif isinstance(checklist_op, Mapping) and checklist_op.get(
        "op",
    ) in _CHECKLIST_OP_WORDS:
        op_word = _CHECKLIST_OP_WORDS[checklist_op["op"]]

        item = checklist_op.get("item") or ""

        lines = [
            "Checklist",
            f'{op_word} "{_plain(str(item))}"',
            f'a "{_plain(str(task_title or ""))}"',
        ]

        if checklist_op.get("op") == "edit" and checklist_op.get(
            "newItemText",
        ):
            lines[1] = (
                f'{op_word} "{_plain(str(item))}" '
                f'a "{_plain(str(checklist_op["newItemText"]))}"'
            )

        summary = "\n".join(lines)

        if len(summary) > MAX_SUMMARY_CHARS:
            summary = summary[: MAX_SUMMARY_CHARS - 1] + "…"

        return summary

    else:
        lines = ["Actualizar tarea"]

        title = arguments.get("title")

        display_title = (
            title if isinstance(title, str) else task_title
        )

        if isinstance(display_title, str) and display_title:
            lines.append(
                "Título: " + _plain(display_title)
            )

    if (
        tool_id == PLANNER_TASKS_UPDATE_TOOL_ID
        and not isinstance(checklist_op, Mapping)
    ):
        if "description" in arguments:
            value = arguments["description"]

            lines.append(
                "Descripción: "
                + (
                    _plain(str(value))
                    if value is not None
                    else "(vacía)"
                )
            )

        if "dueDate" in arguments:
            value = arguments["dueDate"]

            lines.append(
                "Fecha: "
                + (
                    _format_date_human(str(value))
                    if value is not None
                    else "(sin fecha)"
                )
            )

        if "dueTime" in arguments:
            value = arguments["dueTime"]

            lines.append(
                "Hora: "
                + (
                    str(value)[:5]
                    if value is not None
                    else "(sin hora)"
                )
            )

        if "assignedToMemberId" in arguments:
            value = arguments["assignedToMemberId"]

            lines.append(
                "Asignada a: "
                + (
                    _plain(str(value))
                    if value is not None
                    else "nadie (sin asignar)"
                )
            )

        if "priority" in arguments:
            lines.append(
                "Prioridad: " + _plain(str(arguments["priority"]))
            )

    if (
        tool_id
        in (
            PLANNER_TASKS_COMPLETE_TOOL_ID,
            PLANNER_TASKS_TRASH_TOOL_ID,
            PLANNER_TASKS_RESTORE_TOOL_ID,
        )
        and isinstance(task_title, str)
        and task_title
    ):
        lines.append(_plain(task_title))

    summary = "\n".join(lines)

    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[: MAX_SUMMARY_CHARS - 1] + "…"

    return summary


# ---------------------------------------------------------------------------
# Proposal identity (D-owned)
# ---------------------------------------------------------------------------

_PROPOSAL_ID_PATTERN = re.compile(
    r"^prop_[a-z0-9]{16}$",
)


def _mint_proposal_id() -> str:
    """Mint a D-owned, bounded, collision-safe proposal id.

    The id is derived from trusted random material, never from user
    text. It is URL-safe, 20 characters long and matches the Homi
    trusted-id convention (``<prefix>_<token hex>``).
    """

    return f"prop_{secrets.token_hex(8)}"


def _present_iso8601_utc() -> str:
    """The D-minted trusted timestamp in ISO-8601 UTC."""

    return datetime.now(
        timezone.utc
    ).isoformat()


def _proposal_expiry_iso8601_utc() -> str:
    """The D-minted absolute deadline of one pending proposal."""

    return (
        datetime.now(timezone.utc)
        + timedelta(seconds=PROPOSAL_TTL_SECONDS)
    ).isoformat()


def _proposal_is_expired(proposal_obj: ActionProposalV1) -> bool:
    """Return whether a proposal deadline has elapsed.

    A missing deadline is treated as non-expiring for compatibility with
    legacy proposals. A malformed deadline fails closed as expired.
    """

    expires_at = proposal_obj.expires_at

    if expires_at is None:
        return False

    try:
        deadline = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return True

    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) >= deadline


# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------

PROPOSAL_STATUS_PROPOSED = "PROPOSED"

PROPOSAL_STATUS_CONFIRMED = "CONFIRMED"

PROPOSAL_STATUS_CANCELLED = "CANCELLED"

# The T11-6 execution states. They are part of the declared vocabulary
# above and are owned by the T11-6 execution state machine ONLY.
PROPOSAL_STATUS_EXECUTING = "EXECUTING"

PROPOSAL_STATUS_SUCCEEDED = "SUCCEEDED"

# C04: a compound create can finish honestly with some individual
# creates succeeded and others failed. PARTIAL is terminal and never
# implies rollback or atomicity.
PROPOSAL_STATUS_PARTIAL = "PARTIAL"

PROPOSAL_STATUS_FAILED = "FAILED"

PROPOSAL_STATUS_EXPIRED = "EXPIRED"

PROPOSAL_STATUS_VERIFYING = "VERIFYING"

PROPOSAL_STATUS_VERIFIED = "VERIFIED"

# The full vocabulary a later T11 stage may extend the lifecycle with.
# T11-2 implements ONLY ``PROPOSED``: there are no transitions and no
# confirmation endpoint in this stage.
PROPOSAL_STATUS_VOCABULARY: tuple[str, ...] = (
    "PROPOSED",
    "CONFIRMED",
    "CANCELLED",
    "EXECUTING",
    "SUCCEEDED",
    PROPOSAL_STATUS_PARTIAL,
    "FAILED",
    PROPOSAL_STATUS_EXPIRED,
    "VERIFYING",
    "VERIFIED",
)


# ---------------------------------------------------------------------------
# ActionProposalV1
# ---------------------------------------------------------------------------


class _FrozenDict(dict):
    """A dict snapshot that rejects every in-place mutation."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("proposal snapshots are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> "_FrozenDict":
        return self


class _FrozenList(list):
    """A list snapshot that rejects every in-place mutation."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("proposal snapshots are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> "_FrozenList":
        return self


def _freeze_snapshot(value: Any) -> Any:
    """Return one recursively immutable proposal snapshot."""

    if isinstance(value, Mapping):
        return _FrozenDict(
            {
                key: _freeze_snapshot(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, list):
        return _FrozenList(
            _freeze_snapshot(item) for item in value
        )

    if isinstance(value, tuple):
        return tuple(_freeze_snapshot(item) for item in value)

    return copy.deepcopy(value)


def _thaw_snapshot(value: Any) -> Any:
    """Return one plain, isolated copy of a proposal snapshot."""

    if isinstance(value, Mapping):
        return {
            key: _thaw_snapshot(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_thaw_snapshot(item) for item in value]

    return copy.deepcopy(value)


def proposal_arguments_copy(arguments: Any) -> dict[str, Any]:
    """Return a plain deep copy suitable for a wire body or public view."""

    copied = _thaw_snapshot(arguments)
    return copied if isinstance(copied, dict) else {}


@dataclass(frozen=True)
class ActionProposalV1:
    """The canonical D-owned write proposal, version 1.

    Invariants
    ----------
    * ``proposal_version`` is ``"1.0"``.
    * ``proposal_id`` and ``created_at`` are D-minted trusted fields.
    * ``tool_id`` belongs to the canonical WRITE allow-list.
    * ``arguments`` is a copy-isolated, read-only snapshot that passed
      the strict T11-1 validation.
    * ``risk`` and ``confirmation`` come from the trusted tool contract.
    * ``status`` is ``PROPOSED`` in T11-2.
    * The proposal never carries identity, credentials or any code path
      that could execute the write.
    """

    proposal_version: str
    proposal_id: str
    tool_id: str
    arguments: Mapping[str, Any]
    risk_flags: tuple[str, ...]
    confirmation: str
    status: str
    created_at: str
    summary: str
    expires_at: str | None = None

    # T12-4: the D-owned record of the checklist INTENT that produced
    # the proposal's authoritative ``checklist`` array (update only).
    # It is REVISION METADATA, never execution authority: the
    # authoritative array stays in ``arguments`` and the intent only
    # lets a later deterministic revision recompute the transformation
    # against the FRESH authoritative READ state (T12-4 sections 12
    # and 13) instead of patching the previous array blindly. It is
    # internal: it never enters the public projection.
    checklist_intent: Mapping[str, Any] | None = None

    @property
    def public_projection(self) -> dict[str, Any]:
        """The safe public representation for a future HomePlus UI."""

        return {
            "kind": "action_proposal",
            "proposal": {
                "proposal_id": self.proposal_id,
                "tool_id": self.tool_id,
                "summary": self.summary,
                "arguments": proposal_arguments_copy(
                    self.arguments,
                ),
                "risk": list(self.risk_flags),
                "confirmation": self.confirmation,
                "status": self.status,
            },
        }

    def to_json(self) -> str:
        """Deterministic, bounded JSON text of the projection.

        The digest of the proposal should be computed from this text.
        If the content ever exceeds the deterministic bound it fails
        closed instead of producing an unbounded payload.
        """

        text = json.dumps(
            self.public_projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        if len(text.encode("utf-8")) > (
            MAX_PROPOSAL_JSON_BYTES
        ):
            raise ActionProposalError(
                "PROPOSAL_JSON_TOO_LARGE",
                "the deterministic proposal JSON exceeded "
                f"{MAX_PROPOSAL_JSON_BYTES} bytes",
            )

        return text


def build_action_proposal(
    tool_id: str,
    arguments: Any,
    *,
    created_at: str | None = None,
    summary_context: Mapping[str, Any] | None = None,
    checklist_intent: Mapping[str, Any] | None = None,
) -> ActionProposalV1:
    """Build the canonical ActionProposalV1 from validated arguments.

    The builder is the seam between a validated WRITE plan and the
    inert proposal object:

    * ``tool_id`` must belong to the canonical WRITE allow-list and its
      contract must exist; nothing else is accepted.
    * ``arguments`` must pass the strict per-tool validation
      (``validate_write_tool_arguments``; ``planner.tasks.create`` keeps
      the byte-identical T11-1 validation); no coercion, no silent
      changes, no best-effort repair.
    * ``risk`` and ``confirmation`` are copied from the trusted in-code
      tool contract; the caller has no parameters to send them and can
      never downgrade them.
    * ``proposal_id`` and ``created_at`` are minted by Node D. There is
      no parameter to provide them.
    * ``status`` is always ``PROPOSED``.
    * ``summary_context`` is D-owned PRESENTATION context only (the
      authoritative task title of the trusted preflight READ and the
      resolved checklist intent); it never enters the arguments, is
      never authority and can never change the proposal semantics.
    * ``checklist_intent`` (T12-4) is the optional D-owned revision
      metadata of an update proposal built from a checklist intent: the
      validated ``{op, item, newItemText, index}`` descriptor the
      deterministic read-modify-write consumed. It is accepted ONLY
      for ``planner.tasks.update`` (a lifecycle proposal has no
      patch body), is revalidated here and is never exposed in the
      public projection.

    The builder performs no HTTP call and never touches the tool
    executor seam.
    """

    assert_proposal_authority()

    if tool_id not in PROPOSAL_TOOL_IDS:
        raise ActionProposalError(
            "PROPOSAL_TOOL_UNKNOWN",
            f"tool {tool_id!r} is not a canonical proposal "
            "tool",
        )

    contract = write_tool_contract(tool_id)

    if contract is None:
        raise ActionProposalError(
            "PROPOSAL_TOOL_UNKNOWN",
            f"tool {tool_id!r} has no canonical write "
            "contract",
        )

    if contract.kind != "WRITE":
        raise ActionProposalError(
            "PROPOSAL_TOOL_NOT_WRITE",
            f"tool {tool_id!r} is not a WRITE tool",
        )

    stored_intent: Mapping[str, Any] | None = None

    if checklist_intent is not None:
        if tool_id != PLANNER_TASKS_UPDATE_TOOL_ID:
            raise ActionProposalError(
                "PROPOSAL_CHECKLIST_INTENT_INVALID",
                "a checklist intent is only valid for "
                f"{PLANNER_TASKS_UPDATE_TOOL_ID}",
            )

        try:
            normalized_intent = validate_checklist_patch(
                checklist_intent,
            )

        except Exception as error:
            raise ActionProposalError(
                "PROPOSAL_CHECKLIST_INTENT_INVALID",
                f"the checklist intent is invalid: {error}",
            ) from error

        stored_intent = _freeze_snapshot(
            copy.deepcopy(dict(normalized_intent)),
        )

    violations = validate_write_tool_arguments(
        tool_id,
        arguments,
    )

    if violations:
        raise ActionProposalError(
            "PROPOSAL_ARGUMENTS_INVALID",
            f"{tool_id}: " + ", ".join(violations),
        )

    if created_at is None:
        created_at = _present_iso8601_utc()

    snapshot = _freeze_snapshot(
        copy.deepcopy(
            dict(arguments),
        ),
    )

    if tool_id == PLANNER_TASKS_CREATE_TOOL_ID:
        summary = proposal_summary(
            dict(arguments),
        )
    else:
        summary = t12_proposal_summary(
            tool_id,
            dict(arguments),
            summary_context,
        )

    return ActionProposalV1(
        proposal_version=PROPOSAL_VERSION,
        tool_id=contract.tool_id,
        arguments=snapshot,
        risk_flags=contract.risk_flags,
        confirmation=contract.confirmation,
        status=PROPOSAL_STATUS_PROPOSED,
        proposal_id=_mint_proposal_id(),
        created_at=created_at,
        expires_at=_proposal_expiry_iso8601_utc(),
        summary=summary,
        checklist_intent=stored_intent,
    )


# --- T11-4 additions ---



# ---------------------------------------------------------------------------
# T11-4 — pending proposal state + deterministic revision
# ---------------------------------------------------------------------------

EDITABLE_PROPOSAL_FIELDS = (
    "title",
    "description",
    "dueDate",
    "dueTime",
    "assignedToMemberId",
)

EDIT_PATCH_ALLOWED_FIELDS = frozenset(EDITABLE_PROPOSAL_FIELDS)


def validate_edit_patch(patch):
    violations = []
    if not isinstance(patch, dict) or not all(isinstance(k, str) for k in patch):
        return ["patch_not_object"]
    for key in sorted(patch):
        if key not in EDIT_PATCH_ALLOWED_FIELDS:
            violations.append(f"unknown_patch_field:{key}")
        if is_forbidden_proposal_key(key):
            violations.append(f"forbidden_key:{key}")
    for forbidden in ("proposal_id", "tool_id", "risk", "confirmation", "status"):
        if forbidden in patch:
            violations.append(f"forbidden_patch_field:{forbidden}")
    if "title" in patch and (not isinstance(patch["title"], str) or len(patch["title"]) < 1):
        violations.append("invalid_patch:title")
    ordered = []
    for v in violations:
        if v not in ordered:
            ordered.append(v)
    return ordered


validate_proposal_edit_patch = validate_edit_patch
validate_patch = validate_edit_patch


def merge_proposal_arguments(current, patch):
    if not isinstance(current, Mapping):
        raise ActionProposalError("PROPOSAL_ARGUMENTS_INVALID", "current arguments must be a mapping")
    violations = validate_edit_patch(patch)
    if violations:
        raise ActionProposalError("PROPOSAL_EDIT_PATCH_INVALID", ", ".join(violations))
    candidate = copy.deepcopy(dict(current))
    for key, value in (patch or {}).items():
        candidate[key] = copy.deepcopy(value)
    return candidate


merge_arguments = merge_proposal_arguments
merge_patch = merge_proposal_arguments


def revise_action_proposal(existing, edit_patch, *, created_at=None, tool_id=PLANNER_TASKS_CREATE_TOOL_ID):
    if not isinstance(existing, ActionProposalV1):
        raise ActionProposalError("PROPOSAL_REVISION_INVALID", "existing proposal must be ActionProposalV1")

    # C04 deliberately does not implement a partial edit of a compound
    # proposal. A simple edit patch can never be merged into the
    # top-level ``operations`` mode: that would mix modes. Until (and
    # unless) a reviewed strict whole-array replacement is implemented,
    # every compound edit fails closed and leaves the proposal intact.
    if is_compound_create_arguments(existing.arguments):
        raise ActionProposalError(
            "PROPOSAL_EDIT_PATCH_INVALID",
            "a compound create proposal does not accept an edit patch",
        )

    patch_violations = validate_edit_patch(edit_patch)
    if patch_violations:
        raise ActionProposalError("PROPOSAL_EDIT_PATCH_INVALID", ", ".join(patch_violations))
    candidate = merge_proposal_arguments(existing.arguments, edit_patch)
    arg_violations = validate_proposal_arguments(candidate)
    if arg_violations:
        raise ActionProposalError("PROPOSAL_ARGUMENTS_INVALID", ", ".join(arg_violations))
    new_proposal = build_action_proposal(tool_id, candidate, created_at=created_at)
    return new_proposal


revise_proposal = revise_action_proposal
build_revised_proposal = revise_action_proposal
apply_proposal_edit = revise_action_proposal
apply_edit = revise_action_proposal


# ---------------------------------------------------------------------------
# T12-4 — per-tool editability matrix + deterministic update revision
# ---------------------------------------------------------------------------
#
# Frozen T12-4 decisions (sections 1, 3, 10, 11 and 12):
#
# * ``planner.tasks.create``: the T11-4 editable business fields, byte
#   identical (title, description, dueDate, dueTime,
#   assignedToMemberId). No regression is acceptable.
# * ``planner.tasks.update``: the SAME five user-facing intent fields
#   plus the checklist intent expressed through the additive
#   ``checklist_patch``. A revised checklist intent REPLACES the
#   active one; the resulting authoritative array is ALWAYS recomputed
#   from the FRESH trusted ``planner.tasks.get`` state, never patched
#   blindly from the previous proposal's array (sections 12-14).
# * ``planner.tasks.complete`` / ``trash`` / ``restore``: NO arbitrary
#   patch body exists. A lifecycle proposal has no user-editable
#   fields: the only deterministic follow-ups are CANCEL and a NEW
#   intent (the replacement flow of sections 15 and 16).
#
# ``taskId``, ``expectedVersion``, ``risk``, ``confirmation``,
# ``proposal_id`` and ``status`` are D-OWNED authority fields and are
# never editable on ANY tool (sections 3 and 4). The model may express
# a user-requested DELTA only; it can never replace the full proposal.
T12_UPDATE_EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "dueDate",
    "dueTime",
    "assignedToMemberId",
)

T12_LIFECYCLE_EDITABLE_FIELDS: tuple[str, ...] = ()

T12_EDITABLE_FIELDS_BY_TOOL: Mapping[str, tuple[str, ...]] = {
    PLANNER_TASKS_UPDATE_TOOL_ID: T12_UPDATE_EDITABLE_FIELDS,
    PLANNER_TASKS_COMPLETE_TOOL_ID: T12_LIFECYCLE_EDITABLE_FIELDS,
    PLANNER_TASKS_TRASH_TOOL_ID: T12_LIFECYCLE_EDITABLE_FIELDS,
    PLANNER_TASKS_RESTORE_TOOL_ID: T12_LIFECYCLE_EDITABLE_FIELDS,
}

# The keys the deterministic update revision never takes from the
# previous proposal: taskId/expectedVersion are D-owned and refreshed
# (section 8), the derived checklist array is recomputed (section 12).
_T12_REVISION_EXCLUDED_KEYS = frozenset(
    {
        "taskId",
        "expectedVersion",
        "checklist",
    }
)


def revise_t12_update_proposal(
    existing: Any,
    edit_patch: Any,
    *,
    authoritative_task: Mapping[str, Any],
    revised_checklist_intent: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> ActionProposalV1:
    """Deterministically revise an ACTIVE planner.tasks.update proposal.

    T12-4 sections 5-14. The caller (the loop) refreshes the trusted
    ``planner.tasks.get`` state and injects it here; this function is
    PURE (no HTTP, no persistence) and builds the NEW canonical
    proposal:

    * the merge base is the CURRENT proposal's user-facing fields
      (``taskId`` / ``expectedVersion`` / the derived ``checklist``
      never enter the base) plus the user-requested edit delta; only
      explicitly changed user-facing fields may differ and everything
      unrelated stays stable (section 5);
    * the checklist intent is the REVISED intent when the decision
      carries one and the PRESERVED intent of the active proposal
      otherwise; the resulting array is recomputed against the FRESH
      authoritative checklist either way, so a concurrent authoritative
      change is never overwritten and a revised ``add`` never
      duplicates the previous item (sections 13-14);
    * the date/time deterministic merges run over the merged base with
      the FRESH authoritative task: a time-only intent keeps the
      intended/authoritative date, no date at all clarifies, and
      clearing the date clears the time (section 9);
    * ``expectedVersion`` is REFRESHED from the fresh authoritative
      ``version``; if it cannot be obtained the revision fails closed
      and no new executable proposal is emitted (section 8);
    * the full final arguments are revalidated from scratch by the
      builder (section 6) and a NEW ``proposal_id`` is minted: the old
      proposal becomes stale through the pending registry, exactly
      like the accepted T11 edit semantics (section 1).

    ``TaskTargetError`` (DUE_DATE_REQUIRED, checklist item not found /
    ambiguous / too large) propagates to the caller, which owns the
    clarify answers. ``ActionProposalError`` fails closed.
    """

    if not isinstance(existing, ActionProposalV1):
        raise ActionProposalError(
            "PROPOSAL_REVISION_INVALID",
            "existing proposal must be ActionProposalV1",
        )

    if existing.tool_id != PLANNER_TASKS_UPDATE_TOOL_ID:
        raise ActionProposalError(
            "PROPOSAL_REVISION_INVALID",
            "a proposal of "
            f"{existing.tool_id!r} cannot receive an update "
            "edit patch",
        )

    if not isinstance(authoritative_task, Mapping):
        raise ActionProposalError(
            "PROPOSAL_REVISION_INVALID",
            "the authoritative preflight task must be a mapping",
        )

    if not isinstance(existing.arguments, Mapping):
        raise ActionProposalError(
            "PROPOSAL_REVISION_INVALID",
            "the existing proposal arguments are malformed",
        )

    task_id = existing.arguments.get("taskId")

    if (
        not isinstance(task_id, str)
        or re.search(TASK_ID_ONLY_PATTERN, task_id) is None
    ):
        raise ActionProposalError(
            "PROPOSAL_REVISION_INVALID",
            "the active proposal carries no canonical taskId",
        )

    patch_violations = validate_edit_patch(edit_patch)

    if patch_violations:
        raise ActionProposalError(
            "PROPOSAL_EDIT_PATCH_INVALID",
            ", ".join(patch_violations),
        )

    # ---- merge base: user-facing fields + the requested delta -----
    candidate: dict[str, Any] = {
        key: copy.deepcopy(value)
        for key, value in existing.arguments.items()
        if key not in _T12_REVISION_EXCLUDED_KEYS
    }

    for key, value in (edit_patch or {}).items():
        candidate[key] = copy.deepcopy(value)

    # ---- the checklist intent: revised or preserved (sections 12-14)
    intent: dict[str, Any] | None = None

    if revised_checklist_intent is not None:
        if not isinstance(revised_checklist_intent, Mapping):
            raise ActionProposalError(
                "PROPOSAL_REVISION_INVALID",
                "the revised checklist intent is malformed",
            )

        intent = copy.deepcopy(
            dict(revised_checklist_intent),
        )

    elif isinstance(existing.checklist_intent, Mapping):
        intent = copy.deepcopy(
            dict(existing.checklist_intent),
        )

    # Defense in depth: an update proposal that carries a derived
    # ``checklist`` array but NO revision intent can not exist through
    # the canonical build path (the T12-3 dispatch always stores the
    # intent). Rather than silently DROPPING the checklist from the
    # revision, the revision fails closed.
    if (
        "checklist" in existing.arguments
        and intent is None
    ):
        raise ActionProposalError(
            "PROPOSAL_REVISION_INVALID",
            "the active proposal carries a derived checklist "
            "without a revision intent",
        )

    # ---- deterministic date/time merges over the FRESH state -------
    merged = merge_due_time_intent(
        candidate,
        authoritative_task,
    )

    merged = apply_clear_date_invariant(
        merged,
        authoritative_task,
    )

    # ---- the checklist array is RECOMPUTED from the CURRENT state --
    if intent is not None:
        merged["checklist"] = transform_checklist(
            authoritative_task,
            intent,
        )

    # ---- expectedVersion: refreshed, D-owned, fail closed (§8) -----
    version = authoritative_task.get("version")

    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise ActionProposalError(
            "EXPECTED_VERSION_UNAVAILABLE",
            "the authoritative task version could not be "
            "obtained deterministically",
        )

    final_arguments: dict[str, Any] = {
        "taskId": task_id,
        "expectedVersion": version,
    }

    final_arguments.update(merged)

    task_title = authoritative_task.get("title")

    summary_context: dict[str, Any] = {
        "task_title": (
            task_title
            if isinstance(task_title, str)
            else None
        ),
        "checklist_op": (
            dict(intent) if intent is not None else None
        ),
    }

    return build_action_proposal(
        PLANNER_TASKS_UPDATE_TOOL_ID,
        final_arguments,
        created_at=created_at,
        summary_context=summary_context,
        checklist_intent=intent,
    )



# ---------------------------------------------------------------------------
# T11-4 — pending proposal state (documented contract)
# ---------------------------------------------------------------------------
#
# State mechanism: ONE module-level in-memory registry mapping a
# conversation key to THE single active pending ActionProposalV1.
#
# * Ownership: Node D (this module) owns and mutates the state. Neither
#   the model (Node A), nor the user, nor the frontend may register,
#   replace or read it through any other surface; all mutation flows go
#   through the deterministic D-side decisions (create / replacement /
#   edit) and the functions below.
# * Lookup key: ``str(request.context.conversation_id)`` — the logical
#   conversation scope. The identity authority NEVER moves into the
#   proposal: an ActionProposal is still not an authorization grant and
#   the actor/household/context stay in the T05 RequestContext.
# * Lifecycle: created by an accepted create/replacement decision,
#   replaced atomically by every accepted revision (and by an explicit
#   replacement create), and cleared only by the D-side clearing
#   functions. There is no expiry in T11-4 (T11-3+ may add one).
# * Process-restart behavior: the registry is TRANSIENT by design. On
#   process restart it is empty; every follow-up then behaves as
#   "no pending proposal". No persistence is introduced in this stage.
# * Concurrency assumptions: single-process, single-threaded event loop
#   (the current orchestrator runtime). No cross-process locking: the
#   in-memory registry is NOT safe for concurrent writers across
#   processes; proposals are frozen/copy-isolated so in-process readers
#   can never mutate an accepted proposal.
#
_PENDING_PROPOSALS = {}
_PROPOSAL_REVISIONS = {}


def _conv_key(conversation_id):
    return str(conversation_id)


def utc_now_iso() -> str:
    """Return one UTC ISO-8601 timestamp."""

    return datetime.now(timezone.utc).isoformat()


def _durable_snapshot(proposal_obj: ActionProposalV1) -> dict[str, Any]:
    """Build the durable snapshot of one proposal.

    The snapshot carries everything needed to rebuild the proposal after
    a restart: the trusted identity, the validated arguments, the risk
    flags, the confirmation policy and the TTL.
    """

    return {
        "proposal_version": proposal_obj.proposal_version,
        "proposal_id": proposal_obj.proposal_id,
        "tool_id": proposal_obj.tool_id,
        "arguments": proposal_arguments_copy(proposal_obj.arguments),
        "risk_flags": list(proposal_obj.risk_flags),
        "confirmation": proposal_obj.confirmation,
        "summary": proposal_obj.summary,
        "created_at": proposal_obj.created_at,
        "expires_at": proposal_obj.expires_at,
    }


def _persist_proposal_lifecycle(
    conversation_id: Any,
    proposal_obj: ActionProposalV1,
    *,
    status: str,
    actor_id: Any = None,
    household_id: Any = None,
    **extra: Any,
) -> None:
    """Write the durable lifecycle row of one proposal.

    The durable state lives in PostgreSQL. A persistence failure is
    fail-closed: the caller never continues with an unrecorded proposal.
    """

    from homi_db import DatabaseError  # noqa: PLC0415
    from homi_tool_execution_ledger import (  # noqa: PLC0415
        ExecutionLedgerError,
        actor_reference,
        get_ledger,
        scope_reference,
    )

    snapshot = _durable_snapshot(proposal_obj)

    try:
        get_ledger().persist_proposal_state(
            proposal_obj.proposal_id,
            conversation_id=str(conversation_id),
            tool_id=proposal_obj.tool_id,
            status=status,
            snapshot=snapshot,
            actor_ref=(
                actor_reference(actor_id)
                if actor_id is not None
                else None
            ),
            scope_ref=(
                scope_reference(household_id)
                if household_id is not None
                else None
            ),
            payload_hash_value=hashlib.sha256(
                json.dumps(
                    snapshot["arguments"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
            expires_at=proposal_obj.expires_at,
            **extra,
        )

    except (ExecutionLedgerError, DatabaseError) as error:
        raise ActionProposalError(
            "PROPOSAL_PERSISTENCE_UNAVAILABLE",
            "the proposal state could not be persisted",
        ) from error


def register_pending_proposal(
    conversation_id,
    proposal_obj,
    *,
    actor_id=None,
    household_id=None,
):
    key = _conv_key(conversation_id)
    if not isinstance(proposal_obj, ActionProposalV1):
        raise ActionProposalError("PROPOSAL_INVALID", "proposal must be ActionProposalV1")
    _PENDING_PROPOSALS[key] = proposal_obj
    _PROPOSAL_REVISIONS[key] = _PROPOSAL_REVISIONS.get(key, 0) + 1
    _persist_proposal_lifecycle(
        conversation_id,
        proposal_obj,
        status=PROPOSAL_STATUS_PROPOSED,
        actor_id=actor_id,
        household_id=household_id,
    )
    return proposal_obj


set_pending_proposal = register_pending_proposal
store_pending_proposal = register_pending_proposal
put_pending_proposal = register_pending_proposal
save_pending_proposal = register_pending_proposal


def get_pending_proposal(conversation_id):
    return _PENDING_PROPOSALS.get(_conv_key(conversation_id))


lookup_pending_proposal = get_pending_proposal
find_pending_proposal = get_pending_proposal
pending_proposal = get_pending_proposal


def clear_pending_proposal(conversation_id):
    key = _conv_key(conversation_id)
    removed = _PENDING_PROPOSALS.pop(key, None)
    _PROPOSAL_REVISIONS.pop(key, None)

    if removed is not None:
        _persist_proposal_lifecycle(
            conversation_id,
            removed,
            status=PROPOSAL_STATUS_CANCELLED,
        )

    return removed


remove_pending_proposal = clear_pending_proposal
delete_pending_proposal = clear_pending_proposal
discard_pending_proposal = clear_pending_proposal


def has_pending_proposal(conversation_id):
    return _conv_key(conversation_id) in _PENDING_PROPOSALS


pending_proposal_exists = has_pending_proposal


def active_proposal_id(conversation_id):
    p = get_pending_proposal(conversation_id)
    return p.proposal_id if p is not None else None


def is_stale_proposal(proposal_obj, conversation_id=None):
    if conversation_id is None:
        return False
    active = get_pending_proposal(conversation_id)
    if active is None:
        return True
    if not isinstance(proposal_obj, ActionProposalV1):
        return True
    return proposal_obj.proposal_id != active.proposal_id


is_proposal_stale = is_stale_proposal
is_stale = is_stale_proposal
proposal_is_stale = is_stale_proposal


def stale_proposal_guard(conversation_id, proposal_id):
    active = active_proposal_id(conversation_id)
    return active is not None and active != proposal_id


def replace_pending_proposal(
    conversation_id,
    proposal_obj,
    *,
    actor_id=None,
    household_id=None,
):
    # §13 replacement policy: the new proposal becomes the ONLY active
    # one. The revision counter is monotonically increasing: it is per
    # conversation and reflects every accepted proposal (create,
    # replacement and revision), so a revision/replacement never makes
    # the count go backwards.
    replaced = _PENDING_PROPOSALS.pop(_conv_key(conversation_id), None)

    if replaced is not None:
        # The replaced proposal must never be restorable as pending.
        _persist_proposal_lifecycle(
            conversation_id,
            replaced,
            status=PROPOSAL_STATUS_CANCELLED,
        )

    return register_pending_proposal(
        conversation_id,
        proposal_obj,
        actor_id=actor_id,
        household_id=household_id,
    )


replace_proposal = replace_pending_proposal


def proposal_revision(conversation_id):
    return _PROPOSAL_REVISIONS.get(_conv_key(conversation_id), 0)


revision_counter = proposal_revision


# ---------------------------------------------------------------------------
# T11-5 — the D-owned proposal lifecycle (confirm / cancel)
# ---------------------------------------------------------------------------
#
# Boundary decisions (T11-5 sections 1-12):
#
# * ONE lifecycle API: ``apply_proposal_action(conversation_id,
#   proposal_id, action)``. Allowed actions are EXACTLY ``confirm`` and
#   ``cancel``; every other action fails closed. Node D owns every
#   transition: neither the model, nor the user, nor the frontend can
#   set a proposal status directly. This same function is the seam a
#   future HomePlus UI consumes ([Cancelar] [Confirmar]): a manual
#   caller sends conversation_id + proposal_id + action and nothing
#   else, and D validates everything.
# * Allowed transitions: PROPOSED -> CONFIRMED (confirm) and
#   PROPOSED -> CANCELLED (cancel). Nothing else.
# * CONFIRM performs a FULL pre-confirm revalidation: the proposal
#   must be the CURRENT active pending proposal of the conversation
#   (stale guard reused from T11-4), must be PROPOSED, its arguments
#   must still pass the complete strict validation, its tool must be
#   the trusted canonical WRITE contract, and its risk / confirmation
#   must still equal the values re-derived from the trusted in-code
#   contract (LOW_MUTATION / REQUIRED). Any failure rejects
#   fail-closed and transitions NOTHING.
# * CONFIRMED and CANCELLED are TERMINAL: a terminal proposal cannot
#   be edited, cannot be confirmed, cannot be cancelled again, cannot
#   be executed and cannot be revived. A later explicit NEW create may
#   still open a fresh proposal for the conversation; the terminal
#   record stays as the deterministic audit trail.
# * The lifecycle is STATE ONLY. There is no execution path here:
#   this module performs no HTTP call, no HomePlus authentication, no
#   tool execution and no database mutation. WRITE execution belongs
#   to the dedicated T11-6 seam: the ``homi_tool_write_execution``
#   module and the T07 internal write endpoint. This module owns
#   ONLY the deterministic execution state machine (EXECUTING /
#   SUCCEEDED / FAILED) that the seam drives.

PROPOSAL_ACTION_CONFIRM = "confirm"

PROPOSAL_ACTION_CANCEL = "cancel"

PROPOSAL_ACTIONS: tuple[str, ...] = (
    PROPOSAL_ACTION_CONFIRM,
    PROPOSAL_ACTION_CANCEL,
)

# The one canonical public lifecycle field of the proposal response
# (T11-5 section 12). It is derived from the transitioned status, never
# accepted from a caller.
PROPOSAL_ACTION_PUBLIC_CONFIRMED = "confirmed"

PROPOSAL_ACTION_PUBLIC_CANCELLED = "cancelled"


def proposal_action_public_value(
    proposal_obj,
) -> str:
    """The canonical public lifecycle word of a transitioned proposal."""

    if (
        isinstance(proposal_obj, ActionProposalV1)
        and proposal_obj.status == PROPOSAL_STATUS_CONFIRMED
    ):
        return PROPOSAL_ACTION_PUBLIC_CONFIRMED

    if (
        isinstance(proposal_obj, ActionProposalV1)
        and proposal_obj.status == PROPOSAL_STATUS_CANCELLED
    ):
        return PROPOSAL_ACTION_PUBLIC_CANCELLED

    raise ActionProposalError(
        "PROPOSAL_ACTION_INVALID",
        "the proposal has no public lifecycle action",
    )


# The terminal registry: conversation key -> the frozen transitioned
# proposal (CONFIRMED or CANCELLED). Same in-memory, single-process
# contract as the pending registry: transient by design, D-owned, never
# exposed to the model or the frontend.
_TERMINAL_PROPOSALS: dict[str, ActionProposalV1] = {}


def get_terminal_proposal_by_id(proposal_id: str) -> ActionProposalV1 | None:
    """Internal lookup by proposal_id (used by the write-execution seam)."""

    if not isinstance(proposal_id, str) or not proposal_id:
        return None
    for proposal in _TERMINAL_PROPOSALS.values():
        if proposal.proposal_id == proposal_id:
            return proposal
    return None


def get_terminal_proposal(conversation_id):
    """The last terminal (CONFIRMED/CANCELLED) proposal of a conversation."""

    return _TERMINAL_PROPOSALS.get(_conv_key(conversation_id))


terminal_proposal = get_terminal_proposal


def clear_terminal_proposal(conversation_id):
    """Drop the terminal record of a conversation (test/hygiene only)."""

    _TERMINAL_PROPOSALS.pop(_conv_key(conversation_id), None)


def clear_all_proposal_state(conversation_id):
    """Drop every proposal record of a conversation (test/hygiene only)."""

    clear_pending_proposal(conversation_id)
    clear_terminal_proposal(conversation_id)
    _EXECUTION_RECORDS.pop(_conv_key(conversation_id), None)
    _EXECUTION_IDS.pop(_conv_key(conversation_id), None)
    _EXECUTION_SCOPES.pop(_conv_key(conversation_id), None)
    _VERIFICATION_RECORDS.pop(_conv_key(conversation_id), None)


def _transition(
    proposal_obj: ActionProposalV1,
    status: str,
) -> ActionProposalV1:
    """Build the NEW frozen proposal with the transitioned status.

    Every trusted field stays D-owned and byte-identical: proposal_id,
    created_at, tool_id, arguments snapshot, risk, confirmation and
    summary. Only the status changes.
    """

    return replace(
        proposal_obj,
        status=status,
    )


def _validate_confirm_preconditions(
    pending: ActionProposalV1,
) -> None:
    """The full deterministic pre-confirm revalidation (fail-closed).

    Ordered checks; the first violation rejects the transition and the
    pending proposal stays PROPOSED and intact.

    T12-3 section 22: a pending proposal of one of the four new T12
    tools (update / complete / trash / restore) can NOT be confirmed
    yet. The confirm fails closed with
    ``PROPOSAL_CONFIRM_NOT_ENABLED`` and the pending proposal stays
    PROPOSED and intact; the T12 execution phase flips the anchored
    ``T12_CONFIRM_EXECUTION_ENABLED`` flag (an explicit, reviewed
    change). CANCEL keeps its T11-5 behavior for every tool.
    """

    contract = write_tool_contract(pending.tool_id)

    if contract is None or contract.kind != "WRITE":
        raise ActionProposalError(
            "PROPOSAL_TOOL_UNTRUSTED",
            "the proposal tool has no trusted canonical WRITE contract",
        )

    # T12-5D: confirmation and execution are independent. The four new
    # T12 tools are confirmation-capable even though they remain
    # execution-disabled. Arbitrary tools still fail closed.
    if not can_confirm(pending.tool_id):
        raise ActionProposalError(
            "PROPOSAL_CONFIRM_NOT_ENABLED",
            "the proposal tool is not confirmation-capable: "
            f"{pending.tool_id}",
        )

    if tuple(pending.risk_flags) != tuple(contract.risk_flags):
        raise ActionProposalError(
            "PROPOSAL_RISK_MISMATCH",
            "the proposal risk does not match the trusted contract",
        )

    # Risk is per-tool (trash stays MODERATE_MUTATION); only the
    # contract equality above is enforced. No global downgrade to
    # LOW_MUTATION.

    if pending.confirmation != contract.confirmation:
        raise ActionProposalError(
            "PROPOSAL_CONFIRMATION_MISMATCH",
            "the proposal confirmation does not match the trusted "
            "contract",
        )

    if pending.confirmation != "REQUIRED":
        raise ActionProposalError(
            "PROPOSAL_CONFIRMATION_MISMATCH",
            "the trusted contract confirmation is not REQUIRED",
        )

    violations = validate_write_tool_arguments(
        pending.tool_id,
        pending.arguments,
    )

    if violations:
        raise ActionProposalError(
            "PROPOSAL_ARGUMENTS_INVALID",
            ", ".join(violations),
        )


def apply_proposal_action(
    conversation_id,
    proposal_id,
    action,
    *,
    actor_id=None,
    household_id=None,
) -> ActionProposalV1:
    """Apply ONE lifecycle action to the CURRENT pending proposal.

    This is the single D-owned lifecycle API of T11-5:

    * ``action`` must be exactly ``"confirm"`` or ``"cancel"``;
    * the conversation must have an active pending proposal;
    * ``proposal_id`` must be the CURRENT active proposal id (the
      T11-4 stale guard: a stale or unknown id is rejected);
    * the proposal status must be PROPOSED;
    * ``confirm`` additionally revalidates EVERYTHING from scratch
      (arguments, trusted tool, re-derived risk and confirmation).

    On success the pending proposal transitions to CONFIRMED or
    CANCELLED (a NEW frozen object with the same trusted identity),
    the pending registry entry is removed and the terminal registry
    records the transitioned proposal. On a validation failure nothing
    transitions: the pending proposal stays PROPOSED and intact. The
    only exception is an elapsed deadline: that deterministic terminal
    transition moves the proposal to EXPIRED before the
    ``PROPOSAL_EXPIRED`` rejection is raised.

    The transition is lifecycle STATE ONLY: this function performs no
    tool execution, no HTTP call and no database mutation. Returning
    the CONFIRMED proposal does NOT mean the write happened; the WRITE
    execution belongs to a later T11 stage.

    Raises ``ActionProposalError`` with a deterministic code on every
    rejection.
    """

    if action not in PROPOSAL_ACTIONS:
        raise ActionProposalError(
            "PROPOSAL_ACTION_INVALID",
            f"the only lifecycle actions are {list(PROPOSAL_ACTIONS)}",
        )

    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ActionProposalError(
            "PROPOSAL_ACTION_UNKNOWN_ID",
            "the proposal id must be a non-empty string",
        )

    key = _conv_key(conversation_id)

    pending = _PENDING_PROPOSALS.get(key)

    if pending is None:
        terminal = _TERMINAL_PROPOSALS.get(key)

        if (
            terminal is not None
            and terminal.proposal_id == proposal_id
        ):
            raise ActionProposalError(
                "PROPOSAL_ALREADY_TERMINAL",
                "the proposal is already terminal with status "
                f"{terminal.status}",
            )

        raise ActionProposalError(
            "PROPOSAL_ACTION_NO_PENDING",
            "the conversation has no pending proposal",
        )

    if pending.proposal_id != proposal_id:
        raise ActionProposalError(
            "PROPOSAL_ACTION_STALE",
            "the proposal id is not the current active proposal",
        )

    if pending.status != PROPOSAL_STATUS_PROPOSED:
        raise ActionProposalError(
            "PROPOSAL_NOT_PROPOSED",
            f"the proposal status is {pending.status}",
        )

    if _proposal_is_expired(pending):
        expired = _transition(
            pending,
            PROPOSAL_STATUS_EXPIRED,
        )

        _PENDING_PROPOSALS.pop(key, None)
        _TERMINAL_PROPOSALS[key] = expired

        _persist_proposal_lifecycle(
            conversation_id,
            expired,
            status=PROPOSAL_STATUS_EXPIRED,
            actor_id=actor_id,
            household_id=household_id,
        )

        raise ActionProposalError(
            "PROPOSAL_EXPIRED",
            "the proposal deadline elapsed before the action",
        )

    if action == PROPOSAL_ACTION_CONFIRM:
        _validate_confirm_preconditions(pending)

        transitioned = _transition(
            pending,
            PROPOSAL_STATUS_CONFIRMED,
        )

    else:
        transitioned = _transition(
            pending,
            PROPOSAL_STATUS_CANCELLED,
        )

    _PENDING_PROPOSALS.pop(key, None)

    _TERMINAL_PROPOSALS[key] = transitioned

    _persist_proposal_lifecycle(
        conversation_id,
        transitioned,
        status=(
            PROPOSAL_STATUS_CONFIRMED
            if action == PROPOSAL_ACTION_CONFIRM
            else PROPOSAL_STATUS_CANCELLED
        ),
        actor_id=actor_id,
        household_id=household_id,
        confirmed_at=(
            utc_now_iso()
            if action == PROPOSAL_ACTION_CONFIRM
            else None
        ),
    )

    return transitioned


# Read-only aliases for the manual/UI seam documentation; they add no
# new surface, only readable names for the two allowed actions.
confirm_proposal_action = PROPOSAL_ACTION_CONFIRM
cancel_proposal_action = PROPOSAL_ACTION_CANCEL


# ---------------------------------------------------------------------------
# T11-6 — the CONFIRMED -> EXECUTING -> SUCCEEDED|FAILED execution state
# machine (STATE ONLY: no HTTP, no T07, no database from this module)
# ---------------------------------------------------------------------------
#
# Boundary decisions (T11-6):
#
# * The executor effort itself lives in ``homi_tool_write_execution.py``
#   and the T07 internal write seam. This module owns ONLY the
#   deterministic lifecycle state of an execution:
#
#       CONFIRMED -> EXECUTING
#       EXECUTING -> SUCCEEDED
#       EXECUTING -> FAILED
#
# * ``begin_proposal_execution`` is the single entry into EXECUTING. It
#   must be called with the CURRENT terminal proposal of the
#   conversation, the CURRENT proposal id and ONLY while the status is
#   exactly CONFIRMED. A proposal already marked EXECUTING or SUCCEEDED
#   can never begin a second execution (single-execution state guard).
#   Full pre-execution gates (trusted WRITE contract, LOW_MUTATION,
#   REQUIRED, strict argument revalidation) run here and fail closed
#   WITHOUT advancing any state.
# * ``complete_proposal_execution`` closes an EXECUTING proposal. A
#   successful terminal create result promotes EXECUTING -> SUCCEEDED
#   and stores the safe, bounded public result that T07 returned. A
#   deterministic definite failure demotes EXECUTING -> FAILED and
#   stores the reason code. T11-6 does NOT implement automatic retry,
#   transport retry or dedup protocols (T11-7 owns those); an
#   absent/ambiguous outcome is recorded as FAILED with its reason.
# * No execution result of the form "VERIFIED" exists in T11-6:
#   SUCCEEDED means "the authoritative create response said ok". The
#   independent post-write verification belongs to T11-8.
# * The registry stays in-memory, single-process and D-owned, exactly
#   like the pending and terminal registries. No result leaves these
#   registries except through the explicit public accessors below.

PROPOSAL_EXECUTION_RESULT_VERSION = "1.0"

# The deterministic safety projection of a stored execution result.
# Only these scalar fields are ever replicated into the public record;
# everything else (JWT, service-role material, SQL/RPC detail, internal
# membership bookkeeping) is dropped.
EXECUTION_RESULT_SAFE_KEYS: frozenset[str] = (
    EXECUTION_RESULT_PUBLIC_TASK_FIELDS
)

_EXECUTION_RECORDS: dict[str, dict[str, Any]] = {}

# Process-local lock for mutation of proposal/execution registries.
_STATE_LOCK = threading.RLock()

_EXECUTION_IDS: dict[str, str] = {}

# C04: private actor/household references for durable compound execution
# replay. The raw identities stay in the request context and are never
# persisted in this registry.
_EXECUTION_SCOPES: dict[str, dict[str, str]] = {}

_VERIFICATION_RECORDS: dict[str, dict[str, Any]] = {}


def _execution_record(
    proposal: ActionProposalV1,
    *,
    status: str,
    result: Any = None,
    reason: str | None = None,
    execution_id: str | None = None,
    outcome_uncertain: bool | None = None,
) -> dict[str, Any]:
    """The deterministic execution record of a completed transition."""

    safe_result = None

    if isinstance(result, Mapping):
        projected = proposal_execution_safe_result(result)

        if status in (
            PROPOSAL_STATUS_SUCCEEDED,
            PROPOSAL_STATUS_PARTIAL,
        ):
            safe_result = projected

        elif (
            status == PROPOSAL_STATUS_FAILED
            and "operations" in projected
        ):
            # An all-failed compound result keeps the individual safe
            # errors, but it never contains a task.
            safe_result = projected

    if outcome_uncertain is None:
        outcome_uncertain = (
            status in (
                PROPOSAL_STATUS_FAILED,
                PROPOSAL_STATUS_EXECUTING,
            )
            and not (
                isinstance(safe_result, Mapping)
                and isinstance(safe_result.get("operations"), list)
            )
        )

    return {
        "proposal_id": proposal.proposal_id,
        "tool_id": proposal.tool_id,
        "execution_id": execution_id,
        "status": status,
        "result": safe_result,
        "reason": reason,
        "outcome_uncertain": bool(outcome_uncertain),
    }


def _compound_ledger_snapshot(
    conversation_id: Any,
    proposal_obj: ActionProposalV1,
) -> dict[str, Any]:
    """Build the private durable snapshot of one compound proposal."""

    return {
        "proposal_version": proposal_obj.proposal_version,
        "proposal_id": proposal_obj.proposal_id,
        "conversation_id": str(conversation_id),
        "tool_id": proposal_obj.tool_id,
        "arguments": proposal_arguments_copy(
            proposal_obj.arguments,
        ),
        "risk_flags": list(proposal_obj.risk_flags),
        "confirmation": proposal_obj.confirmation,
        "status": proposal_obj.status,
        "created_at": proposal_obj.created_at,
        "summary": proposal_obj.summary,
        "expires_at": proposal_obj.expires_at,
    }


def persist_compound_execution_start(
    conversation_id: Any,
    proposal_obj: ActionProposalV1,
    *,
    actor_id: Any,
    household_id: Any,
) -> Any:
    """Persist one compound execution BEFORE its seam call.

    The durable write is mandatory for compound execution. A persistence
    failure must stop the caller before the network boundary.
    """

    if not is_compound_create_arguments(proposal_obj.arguments):
        return None

    from homi_tool_execution_ledger import (  # noqa: PLC0415
        get_ledger,
    )

    record = get_ledger().start_execution(
        proposal_snapshot=_compound_ledger_snapshot(
            conversation_id,
            proposal_obj,
        ),
        actor_id=actor_id,
        household_id=household_id,
        execution_id=str(
            get_execution_id(conversation_id) or ""
        ),
    )
    _EXECUTION_SCOPES[_conv_key(conversation_id)] = {
        "actor_ref": record.actor_ref,
        "scope_ref": record.scope_ref,
    }

    return record


def _validate_anchored_compound_result(
    result: Any,
    *,
    status: str,
    expected_operation_count: int,
    error_code: str = "PROPOSAL_EXECUTION_RESULT_INVALID",
) -> None:
    """Validate one authoritative compound result before state mutation."""

    if not isinstance(result, Mapping):
        raise ActionProposalError(
            error_code,
            "the compound execution result must be an object",
        )

    try:
        violations = validate_compound_execution_result(
            result,
            expected_operation_count=expected_operation_count,
        )

    except CompoundResultAuthorityError as error:
        raise ActionProposalError(
            "COMPOUND_RESULT_AUTHORITY_ANCHOR_MISMATCH",
            "the compound result authority failed its integrity check",
        ) from error

    if violations:
        raise ActionProposalError(
            error_code,
            "the compound execution result does not match the "
            "anchored contract",
        )

    if result.get("status") != status:
        raise ActionProposalError(
            error_code,
            "the compound execution result status does not match "
            "the terminal status",
        )


def persist_compound_execution_outcome(
    proposal_id: str,
    *,
    status: str,
    result: Mapping[str, Any] | None = None,
    reason: str | None = None,
    outcome_uncertain: bool = False,
) -> Any:
    """Persist one authoritative or uncertain compound outcome."""

    from homi_tool_execution_ledger import (  # noqa: PLC0415
        get_ledger,
    )

    ledger = get_ledger()

    if not outcome_uncertain:
        existing = ledger.get(str(proposal_id))

        if existing is None:
            raise ActionProposalError(
                "EXECUTION_LEDGER_RECORD_MISSING",
                "the compound execution was not started",
            )

        arguments = existing.proposal_snapshot.get("arguments")
        operations = (
            arguments.get("operations")
            if isinstance(arguments, Mapping)
            else None
        )

        if not isinstance(operations, list) or not operations:
            raise ActionProposalError(
                "EXECUTION_LEDGER_RESULT_INVALID",
                "the durable compound proposal has no operation count",
            )

        _validate_anchored_compound_result(
            result,
            status=status,
            expected_operation_count=len(operations),
            error_code="EXECUTION_LEDGER_RESULT_INVALID",
        )

    return ledger.record_outcome(
        proposal_id=str(proposal_id),
        status=status,
        result=result,
        reason=reason,
        outcome_uncertain=outcome_uncertain,
    )


def persist_compound_execution_uncertain(
    proposal_id: str,
    *,
    reason: str,
    status: str = PROPOSAL_STATUS_FAILED,
) -> Any:
    """Persist an outcome that cannot safely claim a zero-task count."""

    return persist_compound_execution_outcome(
        proposal_id,
        status=status,
        result=None,
        reason=reason,
        outcome_uncertain=True,
    )


def recover_execution_state() -> int:
    """Restore durable proposals and compound outcomes after a restart.

    Recovery is state-only. It never calls the write seam and never
    retries a pending, partial or uncertain execution.

    A proposal that was still PROPOSED is restored as pending, so the
    user can still confirm or cancel it after the restart. A proposal
    that was already CONFIRMED when the process died is restored as
    pending too: the confirmation must be explicit and in context, and
    the idempotency identity of the proposal makes a re-confirmation
    safe (the write authority replays the previous outcome instead of
    writing again).
    """

    from homi_tool_execution_ledger import (  # noqa: PLC0415
        get_ledger,
    )

    records = get_ledger().list_executions()
    restored = 0

    for record in records:
        snapshot = record.proposal_snapshot
        arguments = snapshot.get("arguments")
        compound = (
            record.tool_id == PLANNER_TASKS_CREATE_TOOL_ID
            and isinstance(arguments, Mapping)
            and is_compound_create_arguments(arguments)
        )

        if record.status not in (
            PROPOSAL_STATUS_PROPOSED,
            PROPOSAL_STATUS_CONFIRMED,
            PROPOSAL_STATUS_CANCELLED,
            PROPOSAL_STATUS_EXPIRED,
            PROPOSAL_STATUS_EXECUTING,
            PROPOSAL_STATUS_SUCCEEDED,
            PROPOSAL_STATUS_PARTIAL,
            PROPOSAL_STATUS_FAILED,
            PROPOSAL_STATUS_VERIFYING,
            PROPOSAL_STATUS_VERIFIED,
        ):
            raise ActionProposalError(
                "EXECUTION_LEDGER_RECOVERY_INVALID",
                "the durable execution has an unsupported status",
            )

        if compound:
            operations = arguments.get("operations")

            if not isinstance(operations, list) or not operations:
                raise ActionProposalError(
                    "EXECUTION_LEDGER_RECOVERY_INVALID",
                    "the durable compound proposal has no operation count",
                )

            if record.status in (
                PROPOSAL_STATUS_SUCCEEDED,
                PROPOSAL_STATUS_PARTIAL,
            ) and record.outcome_uncertain:
                raise ActionProposalError(
                    "EXECUTION_LEDGER_RECOVERY_INVALID",
                    "the durable execution cannot be both authoritative "
                    "and uncertain",
                )

            if (
                record.status in COMPOUND_EXECUTION_STATUSES
                and not record.outcome_uncertain
            ):
                _validate_anchored_compound_result(
                    record.result,
                    status=record.status,
                    expected_operation_count=len(operations),
                    error_code="EXECUTION_LEDGER_RECOVERY_INVALID",
                )

            elif (
                record.status == PROPOSAL_STATUS_FAILED
                and record.outcome_uncertain
                and record.result is not None
            ):
                raise ActionProposalError(
                    "EXECUTION_LEDGER_RECOVERY_INVALID",
                    "the uncertain durable execution carries an "
                    "authoritative result",
                )

        try:
            recovered = ActionProposalV1(
                proposal_version=str(
                    snapshot.get("proposal_version") or ""
                ),
                proposal_id=str(snapshot.get("proposal_id") or ""),
                tool_id=record.tool_id,
                arguments=copy.deepcopy(
                    dict(arguments)
                    if isinstance(arguments, Mapping)
                    else {}
                ),
                risk_flags=tuple(
                    snapshot.get("risk_flags") or ()
                ),
                confirmation=str(
                    snapshot.get("confirmation") or ""
                ),
                status=record.status,
                created_at=str(snapshot.get("created_at") or ""),
                summary=str(snapshot.get("summary") or ""),
                expires_at=(
                    str(snapshot["expires_at"])
                    if snapshot.get("expires_at") is not None
                    else None
                ),
            )
        except (TypeError, ValueError) as error:
            raise ActionProposalError(
                "EXECUTION_LEDGER_RECOVERY_INVALID",
                "the durable proposal snapshot is malformed",
            ) from error

        key = _conv_key(record.conversation_id)

        if record.status in (
            PROPOSAL_STATUS_PROPOSED,
            PROPOSAL_STATUS_CONFIRMED,
        ):
            if _proposal_is_expired(recovered):
                expired = _transition(
                    recovered,
                    PROPOSAL_STATUS_EXPIRED,
                )
                _TERMINAL_PROPOSALS[key] = expired
            else:
                restorable = _transition(
                    recovered,
                    PROPOSAL_STATUS_PROPOSED,
                )
                _PENDING_PROPOSALS[key] = restorable
                _PROPOSAL_REVISIONS[key] = (
                    _PROPOSAL_REVISIONS.get(key, 0) + 1
                )

            continue

        _TERMINAL_PROPOSALS[key] = recovered
        _EXECUTION_IDS[key] = record.execution_id
        _EXECUTION_SCOPES[key] = {
            "actor_ref": record.actor_ref,
            "scope_ref": record.scope_ref,
        }
        _EXECUTION_RECORDS[key] = _execution_record(
            recovered,
            status=record.status,
            result=record.result,
            reason=record.reason,
            execution_id=record.execution_id,
            outcome_uncertain=record.outcome_uncertain,
        )
        restored += 1

    return restored


def execution_scope_matches(
    conversation_id: Any,
    *,
    actor_id: Any,
    household_id: Any,
) -> bool:
    """Return whether a replay belongs to the current actor and household."""

    scope = _EXECUTION_SCOPES.get(_conv_key(conversation_id))

    if not isinstance(scope, Mapping):
        # Non-ledger/unit-test executions retain the historical in-memory
        # behavior. Durable executions always carry a scope.
        return True

    from homi_tool_execution_ledger import (  # noqa: PLC0415
        actor_reference,
        scope_reference,
    )

    return (
        scope.get("actor_ref") == actor_reference(actor_id)
        and scope.get("scope_ref") == scope_reference(household_id)
    )


COMPOUND_EXECUTION_STATUSES: frozenset[str] = (
    COMPOUND_RESULT_STATUSES
)

COMPOUND_OPERATION_STATUSES: frozenset[str] = (
    COMPOUND_OPERATION_RESULT_STATUSES
)


def _safe_task_projection(
    task: Any,
) -> dict[str, Any]:
    """Project one task onto the public scalar allow-list."""

    if not isinstance(task, Mapping):
        return {}

    safe: dict[str, Any] = {}

    for key in sorted(EXECUTION_RESULT_SAFE_KEYS):
        value = task.get(key)

        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value

    return safe


def proposal_execution_safe_result(
    result: Any,
) -> dict[str, Any]:
    """Project a raw T07 execution result onto the safe allow-list.

    The raw Planner payload stays inside Node D forever. A simple create
    exposes only the allow-listed scalar fields of its task. A compound
    create exposes only ``status`` and the individual ``operations``
    projections: each operation keeps its index/status and, when
    applicable, an allow-listed task or an error containing only
    ``code``/``status``. Correlation, raw bodies, stacks and every other
    field are dropped.
    """

    if not isinstance(result, Mapping):
        return {}

    if (
        "operations" in result
        or "status" in result
    ):
        return project_compound_execution_result(result)

    task = result.get("task")

    if not isinstance(task, Mapping):
        return {}

    return _safe_task_projection(task)


def get_execution_record(
    conversation_id,
) -> dict[str, Any] | None:
    """The execution record of the conversation, or None."""

    return _EXECUTION_RECORDS.get(_conv_key(conversation_id))


def get_execution_id(
    conversation_id,
) -> str | None:
    """The stable D-owned execution id of the conversation, or None."""

    return _EXECUTION_IDS.get(_conv_key(conversation_id))


def get_confirmed_proposal(
    conversation_id,
) -> ActionProposalV1 | None:
    """The CURRENT terminal proposal when it is exactly CONFIRMED."""

    terminal = _TERMINAL_PROPOSALS.get(_conv_key(conversation_id))

    if (
        isinstance(terminal, ActionProposalV1)
        and terminal.status == PROPOSAL_STATUS_CONFIRMED
    ):
        return terminal

    return None


def _validate_execution_preconditions(
    confirmed: ActionProposalV1,
) -> None:
    """The full deterministic pre-execution gates (fail-closed).
 
    Identical revalidation to ``_validate_confirm_preconditions`` plus
    the CURRENT-status requirement. Any violation raises BEFORE the
    state machine advances: no EXECUTING, no network call.
    """
 
    # Confirm gates first (trusted contract, risk, arguments, etc.).
    _validate_confirm_preconditions(confirmed)

    # T12-5D: execution is independent from confirmation. Only the
    # execution-capable tools (create only in this phase) may enter
    # EXECUTING.
    if not can_execute(confirmed.tool_id):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_NOT_ENABLED",
            f"tool {confirmed.tool_id!r} is not executable in this "
            "phase",
        )


def begin_proposal_execution(
    conversation_id,
    proposal_id,
    *,
    actor_id=None,
    household_id=None,
) -> ActionProposalV1:
    """Advance the CURRENT CONFIRMED proposal into EXECUTING.

    Ordered fail-closed gates; the FIRST violation raises and the
    proposal state does NOT change:

    1. ``proposal_id`` must be a non-empty string;
    2. the conversation must have a terminal proposal with status
       exactly CONFIRMED (``PROPOSAL_EXECUTION_NO_CONFIRMED``);
    3. the supplied id must be the CURRENT proposal id
       (``PROPOSAL_EXECUTION_STALE``);
    4. the status must be exactly CONFIRMED — a proposal already
       EXECUTING or SUCCEEDED can never begin a second execution
       (single-execution guard, ``PROPOSAL_EXECUTION_NOT_CONFIRMED``);
    5. the full pre-execution revalidation must pass (trusted WRITE
       contract, LOW_MUTATION, REQUIRED, strict arguments) — a
       tampered proposal fails here (``PROPOSAL_EXECUTION_GATES_FAILED``).

    On success the terminal registry record transitions CONFIRMED ->
    EXECUTING (a NEW frozen object with the same trusted identity) and
    the function returns the transitioned proposal. The network call,
    if any, happens ONLY after this function returned successfully.
    """

    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_UNKNOWN_ID",
            "the proposal id must be a non-empty string",
        )

    key = _conv_key(conversation_id)

    current = _TERMINAL_PROPOSALS.get(key)

    # T12-7: ambiguous retry reuses the SAME execution identity.
    if (
        isinstance(current, ActionProposalV1)
        and current.proposal_id == proposal_id
        and current.status == PROPOSAL_STATUS_EXECUTING
    ):
        return current

    if (
        isinstance(current, ActionProposalV1)
        and current.proposal_id == proposal_id
        and current.status in (
            PROPOSAL_STATUS_SUCCEEDED,
            PROPOSAL_STATUS_PARTIAL,
            PROPOSAL_STATUS_FAILED,
            PROPOSAL_STATUS_VERIFIED,
        )
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_NOT_CONFIRMED",
            "the proposal already entered a terminal execution state "
            f"with status {current.status}",
        )

    if (
        isinstance(current, ActionProposalV1)
        and current.proposal_id == proposal_id
        and current.status != PROPOSAL_STATUS_CONFIRMED
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_NOT_CONFIRMED",
            "the proposal already entered an execution state with "
            f"status {current.status}",
        )

    confirmed = current

    if not (
        isinstance(confirmed, ActionProposalV1)
        and confirmed.status == PROPOSAL_STATUS_CONFIRMED
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_NO_CONFIRMED",
            "the conversation has no current CONFIRMED proposal",
        )

    if confirmed.proposal_id != proposal_id:
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_STALE",
            "the proposal id is not the current CONFIRMED proposal",
        )

    try:
        _validate_execution_preconditions(confirmed)

    except ActionProposalError as error:
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_GATES_FAILED",
            f"{error.code}: {error.message}",
        ) from error

    executing = _transition(
        confirmed,
        PROPOSAL_STATUS_EXECUTING,
    )

    _TERMINAL_PROPOSALS[key] = executing

    _persist_proposal_lifecycle(
        conversation_id,
        executing,
        status=PROPOSAL_STATUS_EXECUTING,
        actor_id=actor_id,
        household_id=household_id,
        started_at=utc_now_iso(),
    )

    if key not in _EXECUTION_IDS:
        _EXECUTION_IDS[key] = f"exec_{uuid.uuid4().hex}"

    return executing


def complete_proposal_execution(
    conversation_id,
    *,
    succeeded: bool | None = None,
    result=None,
    reason=None,
    status: str | None = None,
    outcome_uncertain: bool | None = None,
) -> ActionProposalV1:
    """Close the CURRENT EXECUTING proposal with a terminal outcome.

    The conversation must have a terminal proposal with status exactly
    EXECUTING (``PROPOSAL_EXECUTION_NOT_EXECUTING`` otherwise). A
    successful outcome promotes EXECUTING -> SUCCEEDED. A compound batch
    may finish honestly as PARTIAL; that state is terminal, preserves
    the sanitized individual results and never implies rollback. A
    definite failure promotes EXECUTING -> FAILED and stores the
    deterministic reason code.

    T11-6 records no "VERIFIED" state: SUCCEEDED means the create
    response was authoritative, nothing more and nothing less.
    """

    key = _conv_key(conversation_id)

    executing = _TERMINAL_PROPOSALS.get(key)

    if not (
        isinstance(executing, ActionProposalV1)
        and executing.status == PROPOSAL_STATUS_EXECUTING
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_NOT_EXECUTING",
            "the conversation has no current EXECUTING proposal",
        )

    if status is None:
        if not isinstance(succeeded, bool):
            raise ActionProposalError(
                "PROPOSAL_EXECUTION_STATUS_INVALID",
                "an execution outcome requires succeeded or status",
            )

        status = (
            PROPOSAL_STATUS_SUCCEEDED
            if succeeded
            else PROPOSAL_STATUS_FAILED
        )

    elif succeeded is not None:
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_STATUS_INVALID",
            "succeeded and status are mutually exclusive",
        )

    elif status not in (
        PROPOSAL_STATUS_SUCCEEDED,
        PROPOSAL_STATUS_PARTIAL,
        PROPOSAL_STATUS_FAILED,
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_STATUS_INVALID",
            f"unsupported execution terminal status {status!r}",
        )

    if is_compound_create_arguments(executing.arguments):
        operations = executing.arguments.get("operations")
        expected_operation_count = (
            len(operations)
            if isinstance(operations, list)
            else 0
        )

        if (
            status in (
                PROPOSAL_STATUS_SUCCEEDED,
                PROPOSAL_STATUS_PARTIAL,
            )
            or result is not None
        ):
            _validate_anchored_compound_result(
                result,
                status=status,
                expected_operation_count=expected_operation_count,
            )

    if (
        status in (
            PROPOSAL_STATUS_SUCCEEDED,
            PROPOSAL_STATUS_PARTIAL,
        )
        and not isinstance(result, Mapping)
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_RESULT_INVALID",
            "a successful or partial execution requires an "
            "authoritative result",
        )

    if (
        status == PROPOSAL_STATUS_PARTIAL
        and not (
            isinstance(result, Mapping)
            and isinstance(result.get("operations"), list)
        )
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_RESULT_INVALID",
            "a partial execution requires individual operation results",
        )

    terminal = _transition(
        executing,
        status,
    )

    _TERMINAL_PROPOSALS[key] = terminal

    _EXECUTION_RECORDS[key] = _execution_record(
        terminal,
        status=status,
        result=result,
        reason=(
            reason
            if status == PROPOSAL_STATUS_FAILED
            else None
        ),
        execution_id=_EXECUTION_IDS.get(key),
        outcome_uncertain=outcome_uncertain,
    )

    safe_result = (
        proposal_execution_safe_result(result)
        if isinstance(result, Mapping)
        else None
    )

    if outcome_uncertain is None:
        outcome_uncertain = (
            status in (
                PROPOSAL_STATUS_FAILED,
                PROPOSAL_STATUS_EXECUTING,
            )
            and not (
                isinstance(safe_result, Mapping)
                and isinstance(safe_result.get("operations"), list)
            )
        )

    _persist_proposal_lifecycle(
        conversation_id,
        terminal,
        status=status,
        execution_id=_EXECUTION_IDS.get(key),
        result=safe_result,
        reason=(
            reason if status == PROPOSAL_STATUS_FAILED else None
        ),
        outcome_uncertain=bool(outcome_uncertain),
        completed_at=utc_now_iso(),
    )

    return terminal


def record_uncertain_proposal_execution(
    conversation_id: Any,
    proposal_obj: ActionProposalV1,
    *,
    reason: str,
) -> dict[str, Any]:
    """Store a replayable, explicitly uncertain EXECUTING outcome.

    The proposal remains EXECUTING because the seam may have committed one
    or more items before the fatal failure. The record lets a duplicate
    confirmation explain that uncertainty without another seam call.
    """

    key = _conv_key(conversation_id)
    current = _TERMINAL_PROPOSALS.get(key)

    if (
        not isinstance(current, ActionProposalV1)
        or current.proposal_id != proposal_obj.proposal_id
        or current.status != PROPOSAL_STATUS_EXECUTING
    ):
        raise ActionProposalError(
            "PROPOSAL_EXECUTION_NOT_EXECUTING",
            "the conversation has no current EXECUTING proposal",
        )

    record = _execution_record(
        current,
        status=PROPOSAL_STATUS_EXECUTING,
        result=None,
        reason=reason,
        execution_id=_EXECUTION_IDS.get(key),
        outcome_uncertain=True,
    )
    _EXECUTION_RECORDS[key] = record
    return record


# ---------------------------------------------------------------------------
# T11-8 — independent verification after write (state only)
# ---------------------------------------------------------------------------


def get_verification_record(conversation_id):
    """The verification record of the conversation, or None."""

    return _VERIFICATION_RECORDS.get(_conv_key(conversation_id))


def begin_proposal_verification(conversation_id, proposal_id):
    """Advance the CURRENT SUCCEEDED proposal into VERIFYING.

    Fail-closed: only a SUCCEEDED proposal may enter verification. A
    proposal already VERIFIED is returned without a transition.
    """

    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ActionProposalError(
            "PROPOSAL_VERIFICATION_UNKNOWN_ID",
            "the proposal id must be a non-empty string",
        )

    key = _conv_key(conversation_id)

    current = _TERMINAL_PROPOSALS.get(key)

    if (
        isinstance(current, ActionProposalV1)
        and current.status == PROPOSAL_STATUS_VERIFIED
        and current.proposal_id == proposal_id
    ):
        return current

    if not (
        isinstance(current, ActionProposalV1)
        and current.status == PROPOSAL_STATUS_SUCCEEDED
    ):
        raise ActionProposalError(
            "PROPOSAL_VERIFICATION_NOT_SUCCEEDED",
            "the conversation has no current SUCCEEDED proposal",
        )

    if current.proposal_id != proposal_id:
        raise ActionProposalError(
            "PROPOSAL_VERIFICATION_STALE",
            "the proposal id is not the current SUCCEEDED proposal",
        )

    verifying = _transition(
        current,
        PROPOSAL_STATUS_VERIFYING,
    )

    _TERMINAL_PROPOSALS[key] = verifying

    _persist_proposal_lifecycle(
        conversation_id,
        verifying,
        status=PROPOSAL_STATUS_VERIFYING,
    )

    return verifying


def complete_proposal_verification(
    conversation_id,
    *,
    verified,
    result=None,
    reason=None,
    task=None,
    mismatch=None,
):
    """Close the CURRENT VERIFYING proposal as VERIFIED or back to SUCCEEDED.

    A verified outcome promotes VERIFYING -> VERIFIED. Any other outcome
    reverts VERIFYING -> SUCCEEDED so the mutation outcome is preserved.
    """

    key = _conv_key(conversation_id)

    current = _TERMINAL_PROPOSALS.get(key)

    if not (
        isinstance(current, ActionProposalV1)
        and current.status in (
            PROPOSAL_STATUS_VERIFYING,
            PROPOSAL_STATUS_SUCCEEDED,
            PROPOSAL_STATUS_VERIFIED,
        )
    ):
        raise ActionProposalError(
            "PROPOSAL_VERIFICATION_NOT_VERIFYING",
            "the conversation has no current VERIFYING proposal",
        )

    status = (
        PROPOSAL_STATUS_VERIFIED
        if verified
        else PROPOSAL_STATUS_SUCCEEDED
    )

    terminal = _transition(current, status)

    _TERMINAL_PROPOSALS[key] = terminal

    _persist_proposal_lifecycle(
        conversation_id,
        terminal,
        status=status,
    )

    safe_task = None

    if isinstance(task, Mapping):
        safe_task = proposal_execution_safe_result(
            {"task": task},
        )

    record = {
        "proposal_id": current.proposal_id,
        "execution_id": _EXECUTION_IDS.get(key),
        "verified": bool(verified),
        "verification_status": (
            "VERIFIED" if verified else (reason or "UNVERIFIED")
        ),
        "verification_reason": reason,
        "mismatch": mismatch,
        "task": safe_task,
    }

    _VERIFICATION_RECORDS[key] = record

    exec_record = _EXECUTION_RECORDS.get(key)

    if isinstance(exec_record, dict):
        exec_record["verification"] = record
        exec_record["verified"] = bool(verified)

        if verified and isinstance(safe_task, dict):
            exec_record["verified_task"] = safe_task

    return terminal
