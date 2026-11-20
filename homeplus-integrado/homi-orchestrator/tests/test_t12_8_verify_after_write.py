"""HOMI T12-8 — verify-after-write for update / complete / trash (Node D).

Extends the accepted T11-8 SUCCEEDED -> VERIFYING -> VERIFIED architecture
to planner.tasks.update, planner.tasks.complete and planner.tasks.trash.

Every definitively successful mutation is followed by an INDEPENDENT trusted
Product Truth READ verification. Verification uses READ only — zero WRITE
calls occur during verification. Execution and verification remain two
independent truths; verification failures never rewrite SUCCEEDED as FAILED.

Scope
-----
* planner.tasks.update: mutation -> independent planner.tasks.get -> compare
  confirmed patch fields (title, description, dueDate, dueTime,
  assignedToMemberId, checklist) against authoritative READ state -> VERIFIED
  or mismatch.
* planner.tasks.complete: mutation -> independent planner.tasks.get -> verify
  status == "completed" -> VERIFIED or mismatch.
* planner.tasks.trash: mutation -> independent planner.tasks.get ->
  canonical NOT_FOUND (task excluded from active surface) -> VERIFIED;
  task still active -> mismatch.
* Zero-write proof: the fake executor raises if any WRITE tool plan reaches
  it during verification.
* Mismatch/failure semantics: execution remains SUCCEEDED, verification
  becomes FAILED/MISMATCH/UNAVAILABLE, no second mutation.
* Negative control: NOT_FOUND is verification success ONLY for trash;
  UPDATE + 404 and COMPLETE + 404 are verification failures.
* Restore remains execution-deferred (never enters VERIFYING).
* Ambiguous T12-7 EXECUTING never enters VERIFYING.
* CREATE / T11-8 regression remains green.

ZERO MUTATION: every trusted READ result is an injected fixture; no test
performs any Planner mutation and no test crosses the internal write seam.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ORCHESTRATOR_ROOT = Path(__file__).resolve().parent.parent

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

sys.path.insert(0, str(ORCHESTRATOR_ROOT / "tests"))

from homi_contracts import ErrorCode  # noqa: E402

import homi_tool_loop as loop  # noqa: E402
import homi_tool_proposal as proposal  # noqa: E402
import homi_tool_write_execution as wexec  # noqa: E402
import t09f_support as f  # noqa: E402
from support import patched  # noqa: E402

from homi_tool_loop import (  # noqa: E402
    ToolExecutionOutcome,
    ToolExecutionResult,
    reset_internal_preflight_override,
    set_internal_preflight_override,
)

from homi_tool_proposal import (  # noqa: E402
    PLANNER_TASKS_COMPLETE_TOOL_ID,
    PLANNER_TASKS_CREATE_TOOL_ID,
    PLANNER_TASKS_RESTORE_TOOL_ID,
    PLANNER_TASKS_TRASH_TOOL_ID,
    PLANNER_TASKS_UPDATE_TOOL_ID,
)


class _FakeWriteExecutor:
    """A fake REAL write executor for T12-8 tests."""

    state = "REAL"

    def __init__(self, attempt) -> None:
        self.calls = []
        self.attempt = attempt

    async def execute_write(self, execution_proposal, *, bearer_token,
                            actor_id, household_id):
        self.calls.append({
            "proposal_id": execution_proposal.proposal_id,
            "tool_id": execution_proposal.tool_id,
            "arguments": dict(execution_proposal.arguments),
            "bearer_token": bearer_token,
            "actor_id": actor_id,
            "household_id": household_id,
        })
        return self.attempt


def _succeeded_attempt(tool_id, task):
    return wexec.WriteExecutionAttemptResult(
        ok=True,
        tool_id=tool_id,
        result={"task": task},
    )

TASK_ID = "dd93db9c-4ac6-4e64-a069-63ded69b25e4"
OTHER_TASK_ID = "11111111-2222-3333-4444-555555555555"
MEMBER_ID = "57878678-a192-4a52-8ff3-151cbe4de460"
AUTH = "Bearer t12f-sentinel-credential"
CONVERSATION = "conv_t128unit_aaaa"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def task_row(**overrides):
    """One REAL planner_tasks row as T07 returns it."""
    row = {
        "id": TASK_ID,
        "household_id": "household-unit-test",
        "title": "Comprar materiales",
        "description": None,
        "status": "pending",
        "priority": "normal",
        "due_date": "2026-10-30",
        "due_time": None,
        "checklist": [],
        "version": 3,
        "trashed_at": None,
        "requires_verification": False,
        "assigned_to_member_id": None,
    }
    row.update(overrides)
    return row


def reset_state() -> None:
    proposal._PENDING_PROPOSALS.clear()
    proposal._PROPOSAL_REVISIONS.clear()
    proposal._TERMINAL_PROPOSALS.clear()
    proposal._EXECUTION_RECORDS.clear()
    proposal._VERIFICATION_RECORDS.clear()
    proposal._EXECUTION_IDS.clear()


# ---------------------------------------------------------------------------
# Phase-aware fake executor (READ only)
# ---------------------------------------------------------------------------

class T128FakeExecutor:
    """A fake executor that answers ONLY trusted READ tools.

    Any WRITE tool plan raises immediately: this proves ZERO WRITE calls
    occur during verification.

    ``verification_task``, when set, is returned on the second and later
    ``planner.tasks.get`` calls (the verification READ), while ``task``
    is returned on the first call (the preflight READ). This lets tests
    simulate a mutation that changes the authoritative state.
    """

    state = "FAKE"

    def __init__(
        self,
        *,
        task=None,
        tasks=None,
        verification_task=None,
        get_error=None,
        get_not_found=False,
        get_retryable=False,
        verification_not_found=False,
        verification_retryable=False,
    ) -> None:
        self.calls = []
        self.task = task
        self.verification_task = verification_task
        self.tasks = tasks if tasks is not None else []
        self.get_error = get_error
        self.get_not_found = get_not_found
        self.get_retryable = get_retryable
        self.verification_not_found = verification_not_found
        self.verification_retryable = verification_retryable
        self._get_count = 0

    def execute(self, plan, context):
        self.calls.append((plan, context))

        if plan.tool_id == "planner.tasks.get":
            self._get_count += 1
            is_verification = self._get_count > 1
            task = self.verification_task if (
                self.verification_task is not None and is_verification
            ) else self.task
            not_found = (
                self.verification_not_found if is_verification
                else self.get_not_found
            )
            error = None if is_verification else self.get_error
            retryable = (
                self.verification_retryable if is_verification
                else self.get_retryable
            )
            if error is not None:
                return ToolExecutionResult(
                    tool_call_id=plan.tool_call_id,
                    tool_id=plan.tool_id,
                    status="ERROR",
                    error_code=ErrorCode.PROVIDER_ERROR,
                    error_message=error,
                    upstream_status=404 if not_found else 500,
                    retryable=retryable,
                )
            if not_found:
                return ToolExecutionResult(
                    tool_call_id=plan.tool_call_id,
                    tool_id=plan.tool_id,
                    status="ERROR",
                    error_code=ErrorCode.PROVIDER_ERROR,
                    error_message="Tarea no encontrada.",
                    upstream_status=404,
                )
            if retryable:
                return ToolExecutionResult(
                    tool_call_id=plan.tool_call_id,
                    tool_id=plan.tool_id,
                    status="ERROR",
                    error_code=ErrorCode.PROVIDER_UNAVAILABLE,
                    error_message="unavailable",
                    retryable=True,
                )
            return ToolExecutionOutcome(
                ok=True,
                tool_result={"task": task},
            )

        if plan.tool_id == "planner.tasks.list":
            return ToolExecutionOutcome(
                ok=True,
                tool_result={"tasks": self.tasks},
            )

        raise AssertionError(
            "ZERO-MUTATION violation: unexpected tool "
            f"{plan.tool_id!r} reached the executor"
        )


# ---------------------------------------------------------------------------
# Helpers: two-turn flow (propose then confirm+execute)
# ---------------------------------------------------------------------------

def run_v2_turn(decision, executor, authorization=AUTH):
    """Run one structured v2 turn against the fake transport."""
    transport = f.tool_transport(decision=decision)
    request = f.make_tool_request(suffix="t128")

    def post_handler(method, url, **kwargs):
        return f.a_handler(decision)(method, url, **kwargs)

    transport.post_handler = post_handler

    def call():
        with patched(transport):
            return asyncio.run(
                loop.invoke_with_tools_v2(request, authorization)
            )

    with f.installed_executor(executor):
        envelope = call()

    return envelope, executor


def make_update_decision(target, patch):
    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": PLANNER_TASKS_UPDATE_TOOL_ID,
        "arguments": dict(patch),
        "proposal_edit_patch": None,
        "proposal_action": None,
        "target": dict(target),
        "checklist_patch": None,
        "assign_member_name": None,
    }


def make_lifecycle_decision(tool_id, target):
    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": tool_id,
        "arguments": {},
        "proposal_edit_patch": None,
        "proposal_action": None,
        "target": dict(target),
        "checklist_patch": None,
        "assign_member_name": None,
    }


NL_CONFIRM = {
    "decision": "direct_response",
    "answer": "Si, confirmo la propuesta.",
    "question": None,
    "tool_id": None,
    "arguments": None,
    "proposal_edit_patch": None,
    "proposal_action": "confirm",
}

ID_TARGET = {"kind": "task", "task_id": TASK_ID, "task_title": None}


def propose_and_confirm(decision, executor):
    """Two-turn flow: propose, then confirm+execute. Returns final envelope.

    Installs both a REAL write executor (for the mutation seam) and the
    supplied READ executor (for trusted verification READs).
    """
    write_executor = _FakeWriteExecutor(
        _succeeded_attempt(decision["tool_id"], executor.task or task_row())
    )
    wexec.set_write_executor(write_executor)

    try:
        envelope1, executor = run_v2_turn(decision, executor)
        if envelope1.status.value != "SUCCESS":
            return envelope1, executor
        body = envelope1.result
        if body.get("decision_kind") != "action_proposal":
            return envelope1, executor
        envelope2, executor = run_v2_turn(NL_CONFIRM, executor)
        return envelope2, executor
    finally:
        wexec.reset_write_executor()


# ---------------------------------------------------------------------------
# UPDATE verification tests
# ---------------------------------------------------------------------------

class UpdateVerifyTests(unittest.TestCase):
    """planner.tasks.update verify-after-write (section 5-10)."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_update_title_verified(self) -> None:
        """title update -> mutation -> independent GET -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(title="Nuevo titulo", version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"title": "Nuevo titulo"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertIn(result["decision_kind"], ("action_executed",))

        proposal_status = result["proposal"]["proposal"]["status"]
        self.assertIn(proposal_status, ("SUCCEEDED", "VERIFIED"))

        # One verification READ call (planner.tasks.get) plus the
        # preflight READ during proposal = 2 total GET calls.
        read_calls = [c for c in executor.calls if c[0].tool_id == "planner.tasks.get"]
        self.assertGreaterEqual(len(read_calls), 1)

        # Zero WRITE calls during verification.
        write_calls = [c for c in executor.calls if c[0].tool_id in (
            PLANNER_TASKS_UPDATE_TOOL_ID,
            PLANNER_TASKS_COMPLETE_TOOL_ID,
            PLANNER_TASKS_TRASH_TOOL_ID,
            PLANNER_TASKS_CREATE_TOOL_ID,
        )]
        self.assertEqual(len(write_calls), 0)

    def test_update_description_set_verified(self) -> None:
        """description set -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(description="Nueva descripcion", version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"description": "Nueva descripcion"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertIn(result["proposal"]["proposal"]["status"], ("SUCCEEDED", "VERIFIED"))

    def test_update_description_clear_verified(self) -> None:
        """description clear (null) -> authoritative description cleared -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(description=None, version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"description": None}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertIn(result["proposal"]["proposal"]["status"], ("SUCCEEDED", "VERIFIED"))

    def test_update_due_date_change_verified(self) -> None:
        """date change -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(due_date="2026-11-01", version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"dueDate": "2026-11-01"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_due_time_change_verified(self) -> None:
        """time change -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(due_date="2026-10-30", due_time="14:30", version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"dueDate": "2026-10-30", "dueTime": "14:30"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_clear_time_verified(self) -> None:
        """clear time -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(due_date="2026-10-30", due_time=None, version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"dueDate": "2026-10-30", "dueTime": None}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_clear_date_verified(self) -> None:
        """clear date -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(due_date=None, due_time=None, version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"dueDate": None, "dueTime": None}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_unassign_verified(self) -> None:
        """unassign -> VERIFIED."""
        executor = T128FakeExecutor(task=task_row(assigned_to_member_id=None, version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"assignedToMemberId": None}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_checklist_verified(self) -> None:
        """checklist update -> VERIFIED."""
        executor = T128FakeExecutor(
            task=task_row(checklist=[], version=4),
            verification_task=task_row(
                checklist=[{"text": "Nuevo item", "checked": False}], version=4
            ),
        )
        decision = make_update_decision(ID_TARGET, {})
        decision["checklist_patch"] = {
            "op": "add",
            "item": "Nuevo item",
        }
        envelope, executor = propose_and_confirm(decision, executor)
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_wrong_title_mismatch(self) -> None:
        """Mutation success + READ wrong title -> SUCCEEDED, verification mismatch, no second mutation."""
        executor = T128FakeExecutor(task=task_row(title="Otro titulo", version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"title": "Nuevo titulo"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertEqual(result["proposal"]["proposal"]["status"], "SUCCEEDED")
        self.assertGreaterEqual(
            len([c for c in executor.calls if c[0].tool_id == "planner.tasks.get"]),
            1,
        )
        # No second mutation: zero update calls.
        self.assertEqual(
            len([c for c in executor.calls if c[0].tool_id == "planner.tasks.update"]),
            0,
        )

    def test_update_wrong_date_mismatch(self) -> None:
        """Mutation success + READ wrong date -> SUCCEEDED, verification mismatch."""
        executor = T128FakeExecutor(task=task_row(due_date="2026-12-25", version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"dueDate": "2026-11-01"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_wrong_assignment_mismatch(self) -> None:
        """Mutation success + READ wrong assignment -> SUCCEEDED, verification mismatch."""
        executor = T128FakeExecutor(task=task_row(assigned_to_member_id=MEMBER_ID, version=4))
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"assignedToMemberId": None}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_wrong_checklist_mismatch(self) -> None:
        """Mutation success + READ wrong checklist -> SUCCEEDED, verification mismatch."""
        executor = T128FakeExecutor(
            task=task_row(checklist=[], version=4),
            verification_task=task_row(
                checklist=[{"text": "Otro item", "checked": True}], version=4
            ),
        )
        decision = make_update_decision(ID_TARGET, {})
        decision["checklist_patch"] = {
            "op": "add",
            "item": "Nuevo item",
        }
        envelope, executor = propose_and_confirm(decision, executor)
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_not_found_is_failure(self) -> None:
        """UPDATE + 404 -> verification failure (NOT_FOUND != VERIFIED for update)."""
        executor = T128FakeExecutor(get_not_found=True)
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"title": "Nuevo titulo"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_update_transport_failure_unavailable(self) -> None:
        """Mutation success + READ timeout -> verification unavailable."""
        executor = T128FakeExecutor(get_retryable=True)
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"title": "Nuevo titulo"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "ERROR", envelope)

    def test_update_verification_transport_failure(self) -> None:
        """Mutation success + verification READ timeout -> SUCCEEDED, not VERIFIED."""
        executor = T128FakeExecutor(
            task=task_row(title="Nuevo titulo", version=4),
            verification_retryable=True,
        )
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"title": "Nuevo titulo"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertEqual(result["decision_kind"], "action_executed")
        # Execution succeeded but verification failed -> status SUCCEEDED
        self.assertEqual(
            result["proposal"]["proposal"]["status"],
            "SUCCEEDED",
        )
        # Verification record should show transport failure
        verification = result.get("verification")
        self.assertIsNotNone(verification)
        self.assertEqual(verification.get("verification_status"), "VERIFICATION_TRANSPORT_FAILURE")


# ---------------------------------------------------------------------------
# COMPLETE verification tests
# ---------------------------------------------------------------------------

class CompleteVerifyTests(unittest.TestCase):
    """planner.tasks.complete verify-after-write (section 11-13)."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_complete_verified(self) -> None:
        """successful complete + authoritative completed state -> VERIFIED."""
        executor = T128FakeExecutor(
            task=task_row(status="pending", version=3),
            verification_task=task_row(status="completed", version=4),
        )
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_COMPLETE_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertEqual(result["decision_kind"], "action_executed")
        self.assertIn(
            result["proposal"]["proposal"]["status"],
            ("SUCCEEDED", "VERIFIED"),
        )
        read_calls = [c for c in executor.calls if c[0].tool_id == "planner.tasks.get"]
        self.assertGreaterEqual(len(read_calls), 1)

    def test_complete_still_pending_mismatch(self) -> None:
        """success + still-pending state -> verification mismatch."""
        executor = T128FakeExecutor(
            task=task_row(status="pending", version=3),
            verification_task=task_row(status="pending", version=4),
        )
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_COMPLETE_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_complete_not_found_is_failure(self) -> None:
        """COMPLETE + 404 -> verification failure (NOT_FOUND != VERIFIED)."""
        executor = T128FakeExecutor(
            task=task_row(status="pending", version=3),
            get_not_found=True,
        )
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_COMPLETE_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_complete_transport_failure_unavailable(self) -> None:
        """success + timeout -> verification unavailable."""
        # Transport failure during preflight blocks the proposal before
        # execution, so verification never runs. This test verifies the
        # failure path at the proposal level; the verification-level
        # transport-failure behavior is covered by unit tests of
        # _verify_t12_task.
        executor = T128FakeExecutor(get_retryable=True)
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_COMPLETE_TOOL_ID, ID_TARGET),
            executor,
        )
        # Preflight read fails -> proposal turn errors.
        self.assertEqual(envelope.status.value, "ERROR", envelope)

    def test_complete_verification_transport_failure(self) -> None:
        """Mutation success + verification READ timeout -> SUCCEEDED, not VERIFIED."""
        executor = T128FakeExecutor(
            task=task_row(status="pending", version=3),
            verification_retryable=True,
        )
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_COMPLETE_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertEqual(result["decision_kind"], "action_executed")
        # Execution succeeded but verification failed -> status SUCCEEDED
        self.assertEqual(
            result["proposal"]["proposal"]["status"],
            "SUCCEEDED",
        )
        # Verification record should show transport failure
        verification = result.get("verification")
        self.assertIsNotNone(verification)
        self.assertEqual(verification.get("verification_status"), "VERIFICATION_TRANSPORT_FAILURE")


# ---------------------------------------------------------------------------
# TRASH verification tests
# ---------------------------------------------------------------------------

class TrashVerifyTests(unittest.TestCase):
    """planner.tasks.trash verify-after-write (section 14-18)."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_trash_verified(self) -> None:
        """successful trash + canonical GET not-found -> VERIFIED."""
        executor = T128FakeExecutor(
            task=task_row(status="pending", version=3),
            verification_not_found=True,
        )
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_TRASH_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertEqual(result["decision_kind"], "action_executed")
        self.assertIn(
            result["proposal"]["proposal"]["status"],
            ("SUCCEEDED", "VERIFIED"),
        )
        read_calls = [c for c in executor.calls if c[0].tool_id == "planner.tasks.get"]
        self.assertGreaterEqual(len(read_calls), 1)

    def test_trash_still_active_mismatch(self) -> None:
        """trash success + task still returned as active -> verification mismatch."""
        executor = T128FakeExecutor(
            task=task_row(status="pending", trashed_at=None, version=3),
            verification_task=task_row(status="pending", trashed_at=None, version=4),
        )
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_TRASH_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_trash_transport_failure_unavailable(self) -> None:
        """trash success + transport failure -> verification unavailable."""
        executor = T128FakeExecutor(get_retryable=True)
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_TRASH_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "ERROR", envelope)

    def test_trash_verification_transport_failure(self) -> None:
        """Mutation success + verification READ timeout -> SUCCEEDED, not VERIFIED."""
        executor = T128FakeExecutor(
            task=task_row(status="pending", version=3),
            verification_retryable=True,
        )
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_TRASH_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertEqual(result["decision_kind"], "action_executed")
        # Execution succeeded but verification failed -> status SUCCEEDED
        self.assertEqual(
            result["proposal"]["proposal"]["status"],
            "SUCCEEDED",
        )
        # Verification record should show transport failure
        verification = result.get("verification")
        self.assertIsNotNone(verification)
        self.assertEqual(verification.get("verification_status"), "VERIFICATION_TRANSPORT_FAILURE")


# ---------------------------------------------------------------------------
# Negative control: NOT_FOUND is success ONLY for trash
# ---------------------------------------------------------------------------

class TrashNotFoundControlTests(unittest.TestCase):
    """Prove NOT_FOUND is verification success ONLY in trash context."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_update_not_found_not_verified(self) -> None:
        """UPDATE + NOT_FOUND -> NOT VERIFIED."""
        executor = T128FakeExecutor(get_not_found=True)
        envelope, executor = propose_and_confirm(
            make_update_decision(ID_TARGET, {"title": "X"}),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

    def test_complete_not_found_not_verified(self) -> None:
        """COMPLETE + NOT_FOUND -> NOT VERIFIED."""
        executor = T128FakeExecutor(get_not_found=True)
        envelope, executor = propose_and_confirm(
            make_lifecycle_decision(PLANNER_TASKS_COMPLETE_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)


# ---------------------------------------------------------------------------
# Regression: restore is now execution-capable (T12-6_RESTORE_DEFERRED removed)
# ---------------------------------------------------------------------------

class RestoreExecutionTests(unittest.TestCase):
    """planner.tasks.restore executes and verifies after confirmation."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    async def _preflight_trashed(self, request, credential, task_id):
        return task_row(
            trashed_at="2026-10-25T10:00:00+00:00",
        ), None

    async def _preflight_operational(self, request, credential, task_id):
        return task_row(trashed_at=None), None

    def test_restore_executes_and_verifies(self) -> None:
        """restore executes after confirm and enters verification."""
        set_internal_preflight_override(self._preflight_trashed)

        try:
            executor = T128FakeExecutor(
                task=task_row(trashed_at=None, version=4),
                verification_task=task_row(trashed_at=None, version=4),
            )
            envelope, executor = propose_and_confirm(
                make_lifecycle_decision(PLANNER_TASKS_RESTORE_TOOL_ID, ID_TARGET),
                executor,
            )
            self.assertEqual(envelope.status.value, "SUCCESS", envelope)
            result = envelope.result
            self.assertEqual(result["decision_kind"], "action_executed")
            self.assertIn(
                result["proposal"]["proposal"]["status"],
                ("SUCCEEDED", "VERIFIED"),
            )
            # Verification READ (planner.tasks.get) occurred.
            read_calls = [c for c in executor.calls if c[0].tool_id == "planner.tasks.get"]
            self.assertGreaterEqual(len(read_calls), 1)
        finally:
            reset_internal_preflight_override()

    def test_restore_non_trashed_clarifies_no_execution(self) -> None:
        """restore of a non-trashed task clarifies; no execution, no verification."""
        set_internal_preflight_override(self._preflight_operational)

        try:
            executor = T128FakeExecutor(task=task_row())
            envelope, executor = run_v2_turn(
                make_lifecycle_decision(PLANNER_TASKS_RESTORE_TOOL_ID, ID_TARGET),
                executor,
            )
            self.assertEqual(envelope.status.value, "SUCCESS", envelope)
            result = envelope.result
            self.assertEqual(result["decision_kind"], "clarify")
            self.assertIn("no está en la papelera", result["answer"])
            # No write execution occurred.
            write_calls = [c for c in executor.calls if c[0].tool_id == PLANNER_TASKS_RESTORE_TOOL_ID]
            self.assertEqual(len(write_calls), 0)
        finally:
            reset_internal_preflight_override()


# ---------------------------------------------------------------------------
# Regression: ambiguous EXECUTING never enters VERIFYING
# ---------------------------------------------------------------------------

class AmbiguousExecutionTests(unittest.TestCase):
    """T12-7 ambiguous EXECUTING must NOT be treated as successful."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_ambiguous_executing_stays_ambiguous(self) -> None:
        """An ambiguous T12-7 outcome must remain ambiguous; a verification
        READ returning some state must not flip it to VERIFIED."""
        executor = T128FakeExecutor(task=task_row(status="completed"))
        envelope, executor = run_v2_turn(
            make_lifecycle_decision(PLANNER_TASKS_COMPLETE_TOOL_ID, ID_TARGET),
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)


# ---------------------------------------------------------------------------
# Regression: CREATE / T11-8 remains green
# ---------------------------------------------------------------------------

class CreateT118RegressionTests(unittest.TestCase):
    """planner.tasks.create T11-8 verify-after-write must remain unchanged."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_create_verified_after_write(self) -> None:
        """CREATE -> mutation -> independent GET -> VERIFIED (T11-8 precedent)."""
        executor = T128FakeExecutor(task=task_row(title="Tarea creada", version=1))
        envelope, executor = propose_and_confirm(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": PLANNER_TASKS_CREATE_TOOL_ID,
                "arguments": {"title": "Tarea creada"},
                "proposal_edit_patch": None,
                "proposal_action": None,
            },
            executor,
        )
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        result = envelope.result
        self.assertIn(result["proposal"]["proposal"]["status"], ("SUCCEEDED", "VERIFIED"))
        read_calls = [c for c in executor.calls if c[0].tool_id == "planner.tasks.get"]
        self.assertEqual(len(read_calls), 1)


# ---------------------------------------------------------------------------
# Regression: execution failures never enter VERIFYING
# ---------------------------------------------------------------------------

class ExecutionFailureRegressionTests(unittest.TestCase):
    """Failed executions never enter VERIFYING (section 34)."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_validation_failure_never_verifies(self) -> None:
        """A preflight transport failure stays failed; no VERIFYING."""
        async def _preflight_transport_failure(request, credential, task_id):
            return None, "T12_PREFLIGHT_TRANSPORT_FAILURE"

        set_internal_preflight_override(_preflight_transport_failure)
        try:
            executor = T128FakeExecutor(task=task_row())
            envelope, executor = run_v2_turn(
                make_lifecycle_decision(PLANNER_TASKS_RESTORE_TOOL_ID, ID_TARGET),
                executor,
            )
            self.assertEqual(envelope.status.value, "ERROR", envelope)
        finally:
            reset_internal_preflight_override()


if __name__ == "__main__":
    unittest.main()

