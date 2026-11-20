"""HOMI C04 — anchored compound Planner result contract.

This module is the single source of truth for the strict result returned by
T07 in compound ``planner.tasks.create`` mode.  It owns the result states,
field allow-lists, branch rules, public projection, canonical authority
document and SHA-256 trust anchor.

The compound result has its own trust domain.  It is deliberately not
folded into ``PROPOSAL_AUTHORITY_SHA256``: the proposal/input authority and
the result authority can be reviewed and re-anchored independently.

The runtime payload is never hashed.  Only the static contract below is
hashed, using deterministic UTF-8 JSON with sorted object keys and compact
separators.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


COMPOUND_CREATE_TOOL_ID = "planner.tasks.create"

COMPOUND_CREATE_TOOL_VERSION = "1.1.0"

COMPOUND_RESULT_STATUSES: frozenset[str] = frozenset(
    {
        "FAILED",
        "PARTIAL",
        "SUCCEEDED",
    },
)

COMPOUND_OPERATION_RESULT_STATUSES: frozenset[str] = frozenset(
    {
        "FAILED",
        "SUCCEEDED",
    },
)

COMPOUND_RESULT_FIELDS: frozenset[str] = frozenset(
    {
        "operations",
        "status",
    },
)

COMPOUND_OPERATION_RESULT_FIELDS: frozenset[str] = frozenset(
    {
        "correlation",
        "error",
        "index",
        "status",
        "task",
    },
)

COMPOUND_OPERATION_ERROR_FIELDS: frozenset[str] = frozenset(
    {
        "code",
        "status",
    },
)

COMPOUND_OPERATION_MIN_COUNT = 2

COMPOUND_OPERATION_MAX_COUNT = 4

COMPOUND_TASK_REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "status",
    "title",
)

# Public scalar task fields shared by simple and compound execution
# records.  The compound projection never exposes any other task field.
EXECUTION_RESULT_PUBLIC_TASK_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "title",
        "status",
        "due_date",
        "due_time",
        "description",
        "created_at",
        "version",
    },
)

# The reviewed SHA-256 of ``compound_result_authority_document()``.
# This value is intentionally separate from the proposal/input anchor.
COMPOUND_RESULT_AUTHORITY_SHA256 = (
    "77ebaf4ab52b44602786818faa15e0a6fd5e6e3af75ec0c9f775db67cc0abf97"
)


class CompoundResultAuthorityError(RuntimeError):
    """Fail-closed local integrity error of the compound result anchor."""

    code = "COMPOUND_RESULT_AUTHORITY_ANCHOR_MISMATCH"


def compound_result_authority_document() -> dict[str, Any]:
    """Return the canonical, static compound result authority document."""

    return {
        "tool": {
            "id": COMPOUND_CREATE_TOOL_ID,
            "version": COMPOUND_CREATE_TOOL_VERSION,
        },
        "result": {
            "additional_properties": False,
            "fields": sorted(COMPOUND_RESULT_FIELDS),
            "required": [
                "operations",
                "status",
            ],
            "status_aggregate": {
                "FAILED": "all_failed",
                "PARTIAL": "mixed",
                "SUCCEEDED": "all_succeeded",
            },
            "statuses": sorted(COMPOUND_RESULT_STATUSES),
            "terminal_status_matches_result_status": True,
        },
        "operations": {
            "maximum": COMPOUND_OPERATION_MAX_COUNT,
            "minimum": COMPOUND_OPERATION_MIN_COUNT,
        },
        "operation": {
            "additional_properties": False,
            "fields": sorted(COMPOUND_OPERATION_RESULT_FIELDS),
            "required": [
                "index",
                "status",
            ],
            "statuses": sorted(COMPOUND_OPERATION_RESULT_STATUSES),
            "index": {
                "minimum": 0,
                "ordering": "dense_zero_based",
                "type": "integer",
            },
            "payload_by_status": {
                "FAILED": "error",
                "SUCCEEDED": "task",
            },
            "task": {
                "additional_properties": True,
                "field_types": {
                    "id": "string",
                    "status": "string",
                    "title": "string",
                },
                "required": list(COMPOUND_TASK_REQUIRED_FIELDS),
                "type": "object",
            },
            "error": {
                "additional_properties": False,
                "fields": sorted(COMPOUND_OPERATION_ERROR_FIELDS),
                "required": [
                    "code",
                    "status",
                ],
                "code": {
                    "min_length": 1,
                    "non_whitespace": True,
                    "type": "string",
                },
                "status": {
                    "maximum": 599,
                    "minimum": 400,
                    "type": "integer",
                },
                "type": "object",
            },
            "correlation": {
                "additional_properties": True,
                "optional": True,
                "type": "object",
            },
        },
        "public_projection": {
            "drops": [
                "correlation",
                "unknown_fields",
            ],
            "error_fields": sorted(COMPOUND_OPERATION_ERROR_FIELDS),
            "operation_fields": [
                "error",
                "index",
                "status",
                "task",
            ],
            "task_fields": sorted(EXECUTION_RESULT_PUBLIC_TASK_FIELDS),
            "top_level_fields": [
                "operations",
                "status",
            ],
        },
    }


def compound_result_authority_digest() -> str:
    """Return the SHA-256 digest of the canonical authority document."""

    canonical = json.dumps(
        compound_result_authority_document(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def assert_compound_result_authority() -> str:
    """Fail closed when the in-code compound result authority drifted."""

    digest = compound_result_authority_digest()

    if digest != COMPOUND_RESULT_AUTHORITY_SHA256.lower():
        raise CompoundResultAuthorityError(
            "the in-code compound result authority does not match "
            "its trust anchor"
        )

    return digest


def validate_compound_execution_result(
    result: Any,
    *,
    expected_operation_count: int | None = None,
) -> list[str]:
    """Validate one strict C04 compound result returned by T07.

    The raw result never leaves Node D.  The validator never coerces a
    value and never includes an upstream body, stack or secret in its
    diagnostics.  A local authority mismatch is an integrity error and is
    raised separately from malformed upstream data.
    """

    assert_compound_result_authority()

    violations: list[str] = []

    if not isinstance(result, dict):
        return ["invalid_type:compound_result"]

    unknown = sorted(
        key
        for key in result
        if key not in COMPOUND_RESULT_FIELDS
    )

    for key in unknown:
        violations.append(f"unknown_result_field:{key}")

    status = result.get("status")

    if status not in COMPOUND_RESULT_STATUSES:
        violations.append("invalid_result_status")

    operations = result.get("operations")

    if not isinstance(operations, list):
        violations.append("invalid_type:operations")
        return violations

    if (
        len(operations) < COMPOUND_OPERATION_MIN_COUNT
        or len(operations) > COMPOUND_OPERATION_MAX_COUNT
    ):
        violations.append("invalid_operations_count")

    if (
        expected_operation_count is not None
        and len(operations) != expected_operation_count
    ):
        violations.append("operations_count_mismatch")

    operation_statuses: list[str] = []

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            violations.append(
                f"invalid_type:operations[{index}]"
            )
            continue

        unknown_item = sorted(
            key
            for key in operation
            if key not in COMPOUND_OPERATION_RESULT_FIELDS
        )

        for key in unknown_item:
            violations.append(
                f"unknown_operation_field:{key}"
            )

        operation_index = operation.get("index")

        if (
            not isinstance(operation_index, int)
            or isinstance(operation_index, bool)
            or operation_index < 0
        ):
            violations.append(
                f"invalid_operation_index:{index}"
            )
        elif operation_index != index:
            violations.append("operation_index_mismatch")

        operation_status = operation.get("status")

        if operation_status not in COMPOUND_OPERATION_RESULT_STATUSES:
            violations.append(
                f"invalid_operation_status:{index}"
            )
        else:
            operation_statuses.append(operation_status)

        task_present = "task" in operation
        error_present = "error" in operation
        task = operation.get("task")
        error = operation.get("error")

        if operation_status == "SUCCEEDED":
            if not task_present or task is None:
                violations.append("missing_operation_task")
            elif not isinstance(task, dict):
                violations.append(
                    f"invalid_type:operations[{index}].task"
                )
            else:
                for field in COMPOUND_TASK_REQUIRED_FIELDS:
                    if field not in task:
                        violations.append(
                            f"missing_operation_task_{field}"
                        )
                    elif not isinstance(task[field], str):
                        violations.append(
                            f"invalid_operation_task_{field}"
                        )

            if error_present:
                violations.append("unexpected_operation_error")

        elif operation_status == "FAILED":
            if not error_present or error is None:
                violations.append("missing_operation_error")
            elif not isinstance(error, dict):
                violations.append(
                    f"invalid_type:operations[{index}].error"
                )
            else:
                for key in sorted(
                    set(error) - COMPOUND_OPERATION_ERROR_FIELDS
                ):
                    violations.append(
                        f"unknown_operation_error_field:{key}"
                    )

                code = error.get("code")

                if "code" not in error:
                    violations.append("missing_operation_error_code")
                elif not isinstance(code, str) or not code.strip():
                    violations.append("invalid_operation_error_code")

                status_code = error.get("status")

                if "status" not in error:
                    violations.append("missing_operation_error_status")
                elif (
                    not isinstance(status_code, int)
                    or isinstance(status_code, bool)
                    or status_code < 400
                    or status_code > 599
                ):
                    violations.append(
                        "invalid_operation_error_status"
                    )

            if task_present:
                violations.append("unexpected_operation_task")

        if "correlation" in operation:
            correlation = operation.get("correlation")

            if not isinstance(correlation, dict):
                violations.append(
                    f"invalid_type:operations[{index}].correlation"
                )

    if len(operation_statuses) == len(operations):
        succeeded_count = operation_statuses.count("SUCCEEDED")
        failed_count = operation_statuses.count("FAILED")

        if status == "SUCCEEDED" and failed_count:
            violations.append("aggregate_status_mismatch")

        if status == "FAILED" and succeeded_count:
            violations.append("aggregate_status_mismatch")

        if status == "PARTIAL" and not (
            succeeded_count and failed_count
        ):
            violations.append("aggregate_status_mismatch")

    ordered: list[str] = []

    for violation in violations:
        if violation not in ordered:
            ordered.append(violation)

    return ordered


def _safe_task_projection(task: Any) -> dict[str, Any]:
    """Project one task onto the public scalar allow-list."""

    if not isinstance(task, Mapping):
        return {}

    safe: dict[str, Any] = {}

    for key in sorted(EXECUTION_RESULT_PUBLIC_TASK_FIELDS):
        value = task.get(key)

        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value

    return safe


def project_compound_execution_result(result: Any) -> dict[str, Any]:
    """Project a compound result onto its deterministic public shape."""

    if not isinstance(result, Mapping):
        return {}

    status = result.get("status")
    operations = result.get("operations")

    if (
        status not in COMPOUND_RESULT_STATUSES
        or not isinstance(operations, list)
    ):
        return {}

    safe_operations: list[dict[str, Any]] = []

    for operation in operations:
        if not isinstance(operation, Mapping):
            continue

        index = operation.get("index")
        operation_status = operation.get("status")

        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or operation_status
            not in COMPOUND_OPERATION_RESULT_STATUSES
        ):
            continue

        safe_operation: dict[str, Any] = {
            "index": index,
            "status": operation_status,
        }

        if operation_status == "SUCCEEDED":
            task = _safe_task_projection(operation.get("task"))

            if task:
                safe_operation["task"] = task

        else:
            error = operation.get("error")

            if isinstance(error, Mapping):
                safe_error: dict[str, Any] = {}

                for key in sorted(COMPOUND_OPERATION_ERROR_FIELDS):
                    if key not in error:
                        continue

                    value = error[key]

                    if (
                        isinstance(
                            value,
                            (str, int, float, bool),
                        )
                        or value is None
                    ):
                        safe_error[key] = value

                if safe_error:
                    safe_operation["error"] = safe_error

        safe_operations.append(safe_operation)

    return {
        "status": status,
        "operations": safe_operations,
    }
