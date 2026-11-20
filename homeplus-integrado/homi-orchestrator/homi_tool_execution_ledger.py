"""C04 — durable compound execution ledger owned by HOMI-D.

This module is the ONLY owner of the SQL of the ``homi`` schema inside
the existing HomePlus PostgreSQL database.  It stores the execution
identity, the proposal lifecycle state and the per-operation outcome of
the reviewed compound ``planner.tasks.create`` mode.

Durability contract
-------------------

* PostgreSQL is the only durable engine.  There is no SQLite database,
  no local ledger file and no second source of truth.
* One row of ``homi.execution_runs`` holds the proposal lifecycle
  (snapshot, confirmation, expiry) and the execution aggregate.
* One row of ``homi.execution_steps`` per compound operation holds the
  individual result of the batch.
* The execution rows are written BEFORE the internal seam is called.
* The EFFECT truth stays in ``public.planner_idempotency_keys`` and
  ``public.planner_tasks``, owned by HomePlus/T07.  HOMI-D never writes
  them: the rows below are the orchestration trace of what the write
  authority reported.
* Recovery restores state only.  It never retries the seam and never
  turns an uncertain outcome into a second write.
* Actor and household are stored as one-way server references, never as
  raw identity fields.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from homi_db import Database, DatabaseError, get_database
from homi_tool_compound_result_contract import (
    CompoundResultAuthorityError,
    validate_compound_execution_result,
)


LEDGER_SCHEMA_VERSION = "1"

EXECUTION_STATUS_EXECUTING = "EXECUTING"
EXECUTION_STATUS_SUCCEEDED = "SUCCEEDED"
EXECUTION_STATUS_PARTIAL = "PARTIAL"
EXECUTION_STATUS_FAILED = "FAILED"

PROPOSAL_STATUS_PROPOSED = "PROPOSED"

TERMINAL_EXECUTION_STATUSES = frozenset(
    {
        EXECUTION_STATUS_SUCCEEDED,
        EXECUTION_STATUS_PARTIAL,
        EXECUTION_STATUS_FAILED,
    },
)

OPERATION_STATUS_PENDING = "PENDING"
OPERATION_STATUS_SUCCEEDED = "SUCCEEDED"
OPERATION_STATUS_FAILED = "FAILED"
OPERATION_STATUS_UNKNOWN = "UNKNOWN"

PROPOSAL_LIFECYCLE_STATUSES = frozenset(
    {
        "PROPOSED",
        "CONFIRMED",
        "CANCELLED",
        "EXPIRED",
        "EXECUTING",
        "SUCCEEDED",
        "PARTIAL",
        "FAILED",
        "VERIFYING",
        "VERIFIED",
    },
)


class ExecutionLedgerError(RuntimeError):
    """A fail-closed ledger persistence or recovery failure."""


class ExecutionLedgerConflictError(ExecutionLedgerError):
    """The same proposal identity was reused with a different payload."""


def utc_now() -> str:
    """Return one UTC ISO-8601 timestamp."""

    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    """Serialize one JSON value deterministically."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def payload_hash(value: Any) -> str:
    """Return the SHA-256 of one canonical JSON payload."""

    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def actor_reference(actor_id: Any) -> str:
    """Return a private, one-way server reference for an actor."""

    return payload_hash({"domain": "actor", "value": str(actor_id)})


def scope_reference(household_id: Any) -> str:
    """Return a private, one-way server reference for a household."""

    return payload_hash(
        {"domain": "household", "value": str(household_id)}
    )


def base_idempotency_key(proposal_id: str) -> str:
    """Return the exact T07 base idempotency key of one proposal."""

    return f"homi-write-{proposal_id}"


def operation_idempotency_key(proposal_id: str, index: int) -> str:
    """Return the exact T07 per-operation idempotency key."""

    return f"{base_idempotency_key(proposal_id)}-op-{index}"


def base_mutation_id(proposal_id: str) -> str:
    """Return the exact T07 base mutation id of one proposal."""

    return f"homi-exec-{proposal_id}"


def operation_mutation_id(proposal_id: str, index: int) -> str:
    """Return the exact T07 per-operation mutation id."""

    return f"{base_mutation_id(proposal_id)}-op-{index}"


@dataclass(frozen=True)
class LedgerOperation:
    """The durable state of one item in a compound create."""

    proposal_id: str
    index: int
    status: str
    idempotency_key: str
    mutation_id: str
    task_id: str | None
    error_code: str | None
    error_status: int | None
    updated_at: str


@dataclass(frozen=True)
class LedgerExecution:
    """The durable state of one logical compound execution."""

    proposal_id: str
    conversation_id: str
    tool_id: str
    actor_ref: str
    scope_ref: str
    payload_hash: str
    proposal_snapshot: Mapping[str, Any]
    status: str
    execution_id: str
    idempotency_key: str
    created_at: str
    confirmed_at: str | None
    expires_at: str | None
    started_at: str
    completed_at: str | None
    result_code: str | None
    reason: str | None
    outcome_uncertain: bool
    result: Mapping[str, Any] | None
    operations: tuple[LedgerOperation, ...]


class ExecutionLedger:
    """The PostgreSQL ledger of HOMI-D for compound Planner creates."""

    def __init__(
        self,
        schema: str | None = None,
        *,
        database: Database | None = None,
    ) -> None:
        self._database = database or get_database()
        self.schema = schema or self._database.config.schema

    # -- helpers ---------------------------------------------------------

    def _table(self, name: str) -> str:
        return f'"{self.schema}"."{name}"'

    def _required_tables(self) -> None:
        missing = [
            name
            for name in (
                "execution_runs",
                "execution_steps",
            )
            if not self._database.table_exists(name)
            and self._database.config.schema == self.schema
        ]

        if missing:
            raise ExecutionLedgerError(
                "the homi schema is not available in PostgreSQL"
            )

    def _now(self) -> str:
        return utc_now()

    # -- writes ----------------------------------------------------------

    def persist_proposal_state(
        self,
        proposal_id: str,
        *,
        conversation_id: str,
        tool_id: str,
        status: str,
        snapshot: Mapping[str, Any],
        actor_ref: str | None = None,
        scope_ref: str | None = None,
        payload_hash_value: str | None = None,
        execution_id: str | None = None,
        idempotency_key: str | None = None,
        result: Mapping[str, Any] | None = None,
        reason: str | None = None,
        outcome_uncertain: bool | None = None,
        confirmed_at: str | None = None,
        expires_at: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        """Upsert the durable lifecycle row of one proposal.

        Only the columns that belong to the caller are written, so the
        proposal layer and the execution layer never clobber each other.
        """

        if status not in PROPOSAL_LIFECYCLE_STATUSES:
            raise ExecutionLedgerError(
                f"unsupported proposal status {status!r}"
            )

        self._required_tables()

        now = self._now()

        try:
            self._database.execute(
                f"""
                insert into {self._table('execution_runs')} (
                    proposal_id, conversation_id, tool_id, status,
                    proposal_snapshot, payload_hash, actor_ref, scope_ref,
                    execution_id, idempotency_key, result_json, reason,
                    outcome_uncertain, confirmed_at, expires_at,
                    started_at, completed_at, created_at, updated_at
                ) values (
                    %s, %s, %s, %s,
                    %s::jsonb, %s,
                    coalesce(%s, (select actor_ref from {self._table('execution_runs')} where proposal_id = %s)),
                    coalesce(%s, (select scope_ref from {self._table('execution_runs')} where proposal_id = %s)),
                    %s, %s, %s::jsonb, %s,
                    coalesce(%s, false), %s, %s,
                    %s, %s, %s, %s
                )
                on conflict (proposal_id) do update set
                    status = excluded.status,
                    proposal_snapshot = excluded.proposal_snapshot,
                    payload_hash = coalesce(
                        excluded.payload_hash,
                        {self._table('execution_runs')}.payload_hash
                    ),
                    actor_ref = coalesce(
                        excluded.actor_ref,
                        {self._table('execution_runs')}.actor_ref
                    ),
                    scope_ref = coalesce(
                        excluded.scope_ref,
                        {self._table('execution_runs')}.scope_ref
                    ),
                    execution_id = coalesce(
                        excluded.execution_id,
                        {self._table('execution_runs')}.execution_id
                    ),
                    idempotency_key = coalesce(
                        excluded.idempotency_key,
                        {self._table('execution_runs')}.idempotency_key
                    ),
                    result_json = coalesce(
                        excluded.result_json,
                        {self._table('execution_runs')}.result_json
                    ),
                    reason = coalesce(
                        excluded.reason,
                        {self._table('execution_runs')}.reason
                    ),
                    outcome_uncertain = coalesce(
                        excluded.outcome_uncertain,
                        {self._table('execution_runs')}.outcome_uncertain
                    ),
                    confirmed_at = coalesce(
                        excluded.confirmed_at,
                        {self._table('execution_runs')}.confirmed_at
                    ),
                    expires_at = coalesce(
                        excluded.expires_at,
                        {self._table('execution_runs')}.expires_at
                    ),
                    started_at = coalesce(
                        excluded.started_at,
                        {self._table('execution_runs')}.started_at
                    ),
                    completed_at = coalesce(
                        excluded.completed_at,
                        {self._table('execution_runs')}.completed_at
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    str(proposal_id),
                    str(conversation_id),
                    str(tool_id),
                    str(status),
                    canonical_json(dict(snapshot)),
                    payload_hash_value,
                    actor_ref,
                    str(proposal_id),
                    scope_ref,
                    str(proposal_id),
                    execution_id,
                    idempotency_key,
                    (
                        canonical_json(dict(result))
                        if isinstance(result, Mapping)
                        else None
                    ),
                    reason,
                    outcome_uncertain,
                    confirmed_at,
                    expires_at,
                    started_at,
                    completed_at,
                    now,
                    now,
                ),
            )

        except DatabaseError as error:
            raise ExecutionLedgerError(
                "the durable proposal state could not be persisted"
            ) from error

    def start_execution(
        self,
        *,
        proposal_snapshot: Mapping[str, Any],
        actor_id: Any,
        household_id: Any,
        execution_id: str,
    ) -> LedgerExecution:
        """Durably record one execution before the seam may be called.

        Replaying the same proposal and payload is idempotent. Reusing
        the same proposal id with a different payload fails closed.
        """

        proposal_id = str(proposal_snapshot.get("proposal_id") or "")
        conversation_id = str(
            proposal_snapshot.get("conversation_id") or ""
        )
        tool_id = str(proposal_snapshot.get("tool_id") or "")
        arguments = proposal_snapshot.get("arguments")

        if not proposal_id or not conversation_id or not tool_id:
            raise ExecutionLedgerError(
                "the ledger snapshot is missing its trusted identity"
            )

        if not isinstance(arguments, Mapping):
            raise ExecutionLedgerError(
                "the ledger snapshot arguments must be an object"
            )

        operations = arguments.get("operations")

        if not isinstance(operations, list) or not operations:
            raise ExecutionLedgerError(
                "the ledger snapshot has no compound operations"
            )

        digest = payload_hash(arguments)
        now = self._now()
        actor_ref = actor_reference(actor_id)
        scope_ref = scope_reference(household_id)
        base_key = base_idempotency_key(proposal_id)

        existing = self._read_execution(proposal_id)

        if existing is not None:
            if existing.payload_hash != digest:
                raise ExecutionLedgerConflictError(
                    "the proposal identity already has a different "
                    "payload"
                )

            if existing.status in (
                EXECUTION_STATUS_SUCCEEDED,
                EXECUTION_STATUS_PARTIAL,
                EXECUTION_STATUS_FAILED,
            ):
                raise ExecutionLedgerError(
                    "the durable execution cannot be re-executed from "
                    f"terminal status {existing.status}"
                )

            # Ensure the execution is EXECUTING and that every operation
            # step exists (idempotent: steps already present are kept).
            if existing.status == PROPOSAL_STATUS_PROPOSED:
                self._database.execute(
                    f"""
                    update {self._table('execution_runs')}
                    set status = %s,
                        actor_ref = coalesce(%s, actor_ref),
                        scope_ref = coalesce(%s, scope_ref),
                        execution_id = coalesce(%s, execution_id),
                        idempotency_key = coalesce(%s, idempotency_key),
                        started_at = coalesce(%s, started_at),
                        updated_at = %s
                    where proposal_id = %s
                      and status = %s
                    """,
                    (
                        EXECUTION_STATUS_EXECUTING,
                        actor_ref,
                        scope_ref,
                        str(execution_id),
                        base_key,
                        now,
                        now,
                        str(proposal_id),
                        PROPOSAL_STATUS_PROPOSED,
                    ),
                )

            self._database.execute_many(
                f"""
                insert into {self._table('execution_steps')} (
                    run_id, proposal_id, operation_index, status,
                    idempotency_key, mutation_id, updated_at
                ) values ((select id from {self._table('execution_runs')} where proposal_id = %s), %s, %s, %s, %s, %s, %s)
                on conflict (proposal_id, operation_index) do nothing
                """,
                [
                    (
                        proposal_id,
                        proposal_id,
                        index,
                        OPERATION_STATUS_PENDING,
                        operation_idempotency_key(proposal_id, index),
                        operation_mutation_id(proposal_id, index),
                        now,
                    )
                    for index in range(len(operations))
                ],
            )

            return self._read_execution(proposal_id)

        self.persist_proposal_state(
            proposal_id,
            conversation_id=conversation_id,
            tool_id=tool_id,
            status=EXECUTION_STATUS_EXECUTING,
            snapshot=proposal_snapshot,
            actor_ref=actor_ref,
            scope_ref=scope_ref,
            payload_hash_value=digest,
            execution_id=str(execution_id),
            idempotency_key=base_key,
            started_at=now,
            confirmed_at=now,
        )

        self._database.execute_many(
            f"""
            insert into {self._table('execution_steps')} (
                run_id, proposal_id, operation_index, status,
                idempotency_key, mutation_id, updated_at
            ) values ((select id from {self._table('execution_runs')} where proposal_id = %s), %s, %s, %s, %s, %s, %s)
            on conflict (proposal_id, operation_index) do nothing
            """,
            [
                (
                    proposal_id,
                    proposal_id,
                    index,
                    OPERATION_STATUS_PENDING,
                    operation_idempotency_key(proposal_id, index),
                    operation_mutation_id(proposal_id, index),
                    now,
                )
                for index in range(len(operations))
            ],
        )

        record = self._read_execution(proposal_id)

        if record is None:
            raise ExecutionLedgerError(
                "the durable execution could not be read after commit"
            )

        return record

    def record_outcome(
        self,
        *,
        proposal_id: str,
        status: str,
        result: Mapping[str, Any] | None = None,
        reason: str | None = None,
        outcome_uncertain: bool = False,
    ) -> LedgerExecution:
        """Durably store one authoritative or uncertain compound outcome."""

        if status not in (
            EXECUTION_STATUS_EXECUTING,
            EXECUTION_STATUS_SUCCEEDED,
            EXECUTION_STATUS_PARTIAL,
            EXECUTION_STATUS_FAILED,
        ):
            raise ExecutionLedgerError(
                f"unsupported ledger execution status {status!r}"
            )

        existing = self._read_execution(str(proposal_id))

        if existing is None:
            raise ExecutionLedgerError(
                "the compound execution was not started"
            )

        if (
            existing.status in TERMINAL_EXECUTION_STATUSES
            and existing.status != status
        ):
            raise ExecutionLedgerConflictError(
                "the compound execution already has another terminal "
                "status"
            )

        safe_result = (
            dict(result)
            if isinstance(result, Mapping)
            else None
        )

        if (
            status in TERMINAL_EXECUTION_STATUSES
            and not outcome_uncertain
        ):
            self._validate_authoritative_result(
                existing,
                status=status,
                result=safe_result,
            )

        now = self._now()

        self._database.execute(
            f"""
            update {self._table('execution_runs')}
            set status = %s,
                result_code = %s,
                reason = %s,
                outcome_uncertain = %s,
                result_json = %s::jsonb,
                completed_at = %s,
                updated_at = %s
            where proposal_id = %s
            """,
            (
                status,
                status,
                reason,
                outcome_uncertain,
                (
                    canonical_json(safe_result)
                    if safe_result is not None
                    else None
                ),
                now,
                now,
                str(proposal_id),
            ),
        )

        operation_results: Sequence[Mapping[str, Any]] = ()

        if (
            safe_result is not None
            and not outcome_uncertain
            and isinstance(safe_result.get("operations"), list)
        ):
            operation_results = safe_result["operations"]

        if operation_results:
            for operation in operation_results:
                if not isinstance(operation, Mapping):
                    continue

                index = operation.get("index")

                if (
                    not isinstance(index, int)
                    or isinstance(index, bool)
                ):
                    continue

                operation_status = operation.get("status")
                task = operation.get("task")
                error = operation.get("error")
                task_id = None
                error_code = None
                error_status = None

                if isinstance(task, Mapping):
                    raw_task_id = task.get("id")

                    if isinstance(raw_task_id, str):
                        task_id = raw_task_id

                if isinstance(error, Mapping):
                    raw_code = error.get("code")
                    raw_status = error.get("status")

                    if isinstance(raw_code, str):
                        error_code = raw_code

                    if (
                        isinstance(raw_status, int)
                        and not isinstance(raw_status, bool)
                    ):
                        error_status = raw_status

                if operation_status not in (
                    OPERATION_STATUS_SUCCEEDED,
                    OPERATION_STATUS_FAILED,
                ):
                    operation_status = OPERATION_STATUS_UNKNOWN

                self._database.execute(
                    f"""
                    update {self._table('execution_steps')}
                    set status = %s,
                        task_id = %s,
                        error_code = %s,
                        error_status = %s,
                        updated_at = %s
                    where proposal_id = %s and operation_index = %s
                    """,
                    (
                        operation_status,
                        task_id,
                        error_code,
                        error_status,
                        now,
                        str(proposal_id),
                        index,
                    ),
                )

        else:
            self._database.execute(
                f"""
                update {self._table('execution_steps')}
                set status = %s,
                    task_id = NULL,
                    error_code = NULL,
                    error_status = NULL,
                    updated_at = %s
                where proposal_id = %s
                """,
                (OPERATION_STATUS_UNKNOWN, now, str(proposal_id)),
            )

        record = self._read_execution(str(proposal_id))

        if record is None:
            raise ExecutionLedgerError(
                "the durable execution could not be read after commit"
            )

        return record

    def _validate_authoritative_result(
        self,
        existing: LedgerExecution,
        *,
        status: str,
        result: Mapping[str, Any] | None,
    ) -> None:
        """Fail closed when an authoritative outcome breaks the contract."""

        snapshot = existing.proposal_snapshot
        arguments = (
            snapshot.get("arguments")
            if isinstance(snapshot, Mapping)
            else None
        )
        operations = (
            arguments.get("operations")
            if isinstance(arguments, Mapping)
            else None
        )

        if not isinstance(operations, list) or not operations:
            raise ExecutionLedgerError(
                "the durable compound proposal has no operation count"
            )

        try:
            violations = validate_compound_execution_result(
                result,
                expected_operation_count=len(operations),
            )

        except CompoundResultAuthorityError as error:
            raise ExecutionLedgerError(
                "the compound result authority failed its integrity check"
            ) from error

        if violations:
            raise ExecutionLedgerError(
                "the compound result does not match the anchored contract"
            )

        if (
            isinstance(result, Mapping)
            and result.get("status") != status
        ):
            raise ExecutionLedgerError(
                "the compound result status does not match the terminal "
                "ledger status"
            )

    # -- reads -----------------------------------------------------------

    def get(self, proposal_id: str) -> LedgerExecution | None:
        """Return one durable execution by proposal id."""

        return self._read_execution(str(proposal_id))

    def list_executions(
        self,
        *,
        statuses: Sequence[str] | None = None,
    ) -> tuple[LedgerExecution, ...]:
        """Return every durable execution, oldest first."""

        if statuses:
            placeholders = ", ".join(["%s"] * len(statuses))
            rows = self._database.query(
                "select proposal_id from "
                f"{self._table('execution_runs')} "
                f"where status in ({placeholders}) "
                "order by created_at asc, proposal_id asc",
                tuple(statuses),
            )

        else:
            rows = self._database.query(
                "select proposal_id from "
                f"{self._table('execution_runs')} "
                "order by created_at asc, proposal_id asc"
            )

        records: list[LedgerExecution] = []

        for row in rows:
            record = self._read_execution(str(row["proposal_id"]))

            if record is not None:
                records.append(record)

        return tuple(records)

    def scope_matches(
        self,
        *,
        proposal_id: str,
        actor_id: Any,
        household_id: Any,
    ) -> bool:
        """Return whether one execution belongs to the current scope."""

        record = self.get(str(proposal_id))

        if record is None:
            return False

        return (
            record.actor_ref == actor_reference(actor_id)
            and record.scope_ref == scope_reference(household_id)
        )

    def delete_execution(self, proposal_id: str) -> None:
        """Delete one fixture row. This is not part of the runtime contract."""

        self._database.execute(
            "delete from "
            f"{self._table('execution_runs')} "
            "where proposal_id = %s",
            (str(proposal_id),),
        )

    def purge_all(self) -> None:
        """Delete every execution row. Test-only helper."""
        self._required_tables()
        self._database.execute(
            f"delete from {self._table('execution_steps')}"
        )
        self._database.execute(
            f"delete from {self._table('execution_runs')}"
        )

    def _read_execution(
        self,
        proposal_id: str,
    ) -> LedgerExecution | None:
        row = self._database.query_one(
            "select * from "
            f"{self._table('execution_runs')} "
            "where proposal_id = %s",
            (str(proposal_id),),
        )

        if row is None:
            return None

        operation_rows = self._database.query(
            "select * from "
            f"{self._table('execution_steps')} "
            "where proposal_id = %s "
            "order by operation_index asc",
            (str(proposal_id),),
        )

        operations = tuple(
            LedgerOperation(
                proposal_id=str(operation["proposal_id"]),
                index=int(operation["operation_index"]),
                status=str(operation["status"]),
                idempotency_key=str(operation["idempotency_key"]),
                mutation_id=str(operation["mutation_id"]),
                task_id=(
                    str(operation["task_id"])
                    if operation["task_id"] is not None
                    else None
                ),
                error_code=(
                    str(operation["error_code"])
                    if operation["error_code"] is not None
                    else None
                ),
                error_status=(
                    int(operation["error_status"])
                    if operation["error_status"] is not None
                    else None
                ),
                updated_at=str(operation["updated_at"]),
            )
            for operation in operation_rows
        )

        result = row.get("result_json")
        snapshot = row.get("proposal_snapshot") or {}

        if isinstance(result, str):
            try:
                result = json.loads(result)

            except (TypeError, ValueError):
                result = None

        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)

            except (TypeError, ValueError):
                snapshot = {}

        if not isinstance(snapshot, Mapping):
            snapshot = {}

        return LedgerExecution(
            proposal_id=str(row["proposal_id"]),
            conversation_id=str(row["conversation_id"]),
            tool_id=str(row["tool_id"]),
            actor_ref=str(row["actor_ref"] or ""),
            scope_ref=str(row["scope_ref"] or ""),
            payload_hash=str(row["payload_hash"] or ""),
            proposal_snapshot=(
                snapshot if isinstance(snapshot, Mapping) else {}
            ),
            status=str(row["status"]),
            execution_id=str(row["execution_id"] or ""),
            idempotency_key=str(row["idempotency_key"] or ""),
            created_at=str(row["created_at"]),
            confirmed_at=(
                str(row["confirmed_at"])
                if row["confirmed_at"] is not None
                else None
            ),
            expires_at=(
                str(row["expires_at"])
                if row["expires_at"] is not None
                else None
            ),
            started_at=str(row["started_at"]),
            completed_at=(
                str(row["completed_at"])
                if row["completed_at"] is not None
                else None
            ),
            result_code=(
                str(row["result_code"])
                if row["result_code"] is not None
                else None
            ),
            reason=(
                str(row["reason"])
                if row["reason"] is not None
                else None
            ),
            outcome_uncertain=bool(row["outcome_uncertain"]),
            result=result if isinstance(result, Mapping) else None,
            operations=operations,
        )


_LEDGER: ExecutionLedger | None = None
_LEDGER_SCHEMA: str | None = None
_LEDGER_LOCK = threading.RLock()


def get_ledger() -> ExecutionLedger:
    """Return the process ledger."""

    global _LEDGER

    with _LEDGER_LOCK:
        if _LEDGER is None:
            _LEDGER = ExecutionLedger()

        return _LEDGER


def configure_ledger(
    schema: str | None = None,
    *,
    database: Database | None = None,
) -> ExecutionLedger:
    """Configure an explicit ledger, primarily for isolated tests."""

    global _LEDGER, _LEDGER_SCHEMA

    with _LEDGER_LOCK:
        _LEDGER = ExecutionLedger(schema, database=database)
        _LEDGER_SCHEMA = schema

        return _LEDGER


def reset_ledger() -> None:
    """Close and forget the process ledger."""

    global _LEDGER, _LEDGER_SCHEMA

    with _LEDGER_LOCK:
        _LEDGER = None
        _LEDGER_SCHEMA = None
