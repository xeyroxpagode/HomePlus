"""HOMI T12-3 — existing-task WRITE proposal tests (Node D).

Coverage of the T12-3 task matrix (sections 17-27 and the D-side test
matrix of section 30):

* decision-v2 knows EXACTLY the five frozen WRITE tools (8 READ + 5
  WRITE); the frozen v1 surface never learns them;
* the additive target contract is gated strictly (no invented UUIDs,
  no unknown fields, no model-provided taskId/expectedVersion/
  checklist/status);
* D resolves explicit/unique-exact task targets deterministically and
  clarifies on zero/multiple matches;
* D performs the trusted preflight READ planner.tasks.get and owns
  expectedVersion;
* the dueTime merge rule, the clear-date invariant, unassign = null,
  assign-by-name = clarify;
* the checklist read-modify-write transform produces the FULL
  resulting array from the authoritative READ state;
* ActionProposal supports all five tools with the trusted per-tool
  risk matrix (trash = MODERATE_MUTATION) and REQUIRED confirmation;
* the four new T12 tools stay NON-EXECUTABLE: confirm fails closed
  (PROPOSAL_CONFIRM_NOT_ENABLED), the write executor is never called;
* create/READ/direct/clarify T11/T10 regressions stay intact.

ZERO MUTATION: every trusted READ result is an injected fixture; no
test performs any Planner mutation, no test crosses the internal
write seam.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ORCHESTRATOR_ROOT = Path(
    __file__).resolve().parent.parent

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

sys.path.insert(
    0,
    str(ORCHESTRATOR_ROOT / "tests"),
)

from homi_contracts import ErrorCode  # noqa: E402

import homi_tool_loop as loop  # noqa: E402
import homi_tool_proposal as proposal  # noqa: E402
import homi_tool_t12_targets as targets  # noqa: E402
import t09f_support as f  # noqa: E402
from support import patched  # noqa: E402

from homi_tool_loop import (  # noqa: E402
    ToolExecutionOutcome,
    ToolExecutionResult,
    reset_internal_preflight_override,
    set_internal_preflight_override,
)


FIXED_CREATED_AT = "2026-10-26T12:00:00+00:00"

TASK_ID = "dd93db9c-4ac6-4e64-a069-63ded69b25e4"

OTHER_TASK_ID = (
    "11111111-2222-3333-4444-555555555555"
)

MEMBER_ID = "57878678-a192-4a52-8ff3-151cbe4de460"

AUTH = "Bearer t12f-sentinel-credential"


def task_row(
    **overrides,
):
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


def title_target(title: str) -> dict:
    return {
        "kind": "task",
        "task_id": None,
        "task_title": title,
    }


def id_target(task_id: str = TASK_ID) -> dict:
    return {
        "kind": "task",
        "task_id": task_id,
        "task_title": None,
    }


def v2_update_decision(
    target: dict,
    patch: dict | None = None,
    *,
    checklist_patch: dict | None = None,
    assign_member_name: str | None = None,
) -> dict:
    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": "planner.tasks.update",
        "arguments": dict(patch or {}),
        "proposal_edit_patch": None,
        "proposal_action": None,
        "target": dict(target),
        "checklist_patch": checklist_patch,
        "assign_member_name": assign_member_name,
    }


def v2_lifecycle_decision(
    tool_id: str,
    target: dict,
) -> dict:
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


WRITE_CREATE_V2_ENVELOPE = {
    "decision": "tool_request",
    "answer": None,
    "question": None,
    "tool_id": "planner.tasks.create",
    "arguments": {"title": "Comprar leche"},
    "proposal_edit_patch": None,
    "proposal_action": None,
}

READ_TASKS_V2_ENVELOPE = {
    "decision": "tool_request",
    "answer": None,
    "question": None,
    "tool_id": "planner.tasks.list",
    "arguments": {},
    "proposal_edit_patch": None,
    "proposal_action": None,
}

DIRECT_RESPONSE_V2 = {
    "decision": "direct_response",
    "answer": "Hola! En qué te ayudo?",
    "question": None,
    "tool_id": None,
    "arguments": None,
    "proposal_edit_patch": None,
    "proposal_action": None,
}


class T12FakeExecutor:
    """A phase-aware fake READ executor.

    It answers ONLY the trusted READ tools of the T12-3 preflight and
    records every call so the tests can prove ZERO WRITE mutation:
    any WRITE tool plan raises immediately.
    """

    state = "FAKE"

    def __init__(
        self,
        *,
        tasks: list | None = None,
        task: dict | None = None,
        get_not_found: bool = False,
        get_retryable: bool = False,
    ) -> None:
        self.calls: list = []
        self.tasks = tasks if tasks is not None else []
        self.task = task
        self.get_not_found = get_not_found
        self.get_retryable = get_retryable

    def execute(self, plan, context):
        self.calls.append((plan, context))

        if plan.tool_id == "planner.tasks.list":
            return ToolExecutionOutcome(
                ok=True,
                tool_result={"tasks": self.tasks},
            )

        if plan.tool_id == "planner.tasks.get":
            if self.get_not_found:
                return ToolExecutionResult(
                    tool_call_id=plan.tool_call_id,
                    tool_id=plan.tool_id,
                    status="ERROR",
                    error_code=ErrorCode.PROVIDER_ERROR,
                    error_message="Tarea no encontrada.",
                    upstream_status=404,
                )

            if self.get_retryable:
                return ToolExecutionResult(
                    tool_call_id=plan.tool_call_id,
                    tool_id=plan.tool_id,
                    status="ERROR",
                    error_code=ErrorCode.PROVIDER_UNAVAILABLE,
                    retryable=True,
                )

            return ToolExecutionOutcome(
                ok=True,
                tool_result={"task": self.task},
            )

        raise AssertionError(
            "ZERO-MUTATION violation: unexpected tool "
            f"{plan.tool_id!r} reached the executor"
        )


# ---------------------------------------------------------------------------
# The proposal contract layer
# ---------------------------------------------------------------------------


class T12CatalogTests(unittest.TestCase):
    """The frozen five-tool WRITE catalog and risk matrix."""

    def test_decision_v2_knows_exactly_five_write_tools(self) -> None:
        self.assertEqual(
            proposal.PROPOSAL_TOOL_IDS,
            (
                "planner.tasks.create",
                "planner.tasks.update",
                "planner.tasks.complete",
                "planner.tasks.trash",
                "planner.tasks.restore",
            ),
        )

    def test_no_other_planner_write_exists(self) -> None:
        for forbidden in (
            "planner.tasks.reopen",
            "planner.tasks.cancel",
            "planner.tasks.verify",
            "planner.tasks.reactivate",
            "planner.tasks.delete",
            "planner.tasks.checklist.add",
            "planner.events.create",
        ):
            self.assertNotIn(
                forbidden,
                proposal.PROPOSAL_TOOL_IDS,
            )

            self.assertIsNone(
                proposal.write_tool_contract(forbidden),
            )

    def test_risk_matrix_is_deterministic_by_tool(self) -> None:
        expected = {
            "planner.tasks.create": ("LOW_MUTATION",),
            "planner.tasks.update": ("LOW_MUTATION",),
            "planner.tasks.complete": ("LOW_MUTATION",),
            "planner.tasks.trash": (
                "MODERATE_MUTATION",
            ),
            "planner.tasks.restore": ("LOW_MUTATION",),
        }

        for tool_id, risk in expected.items():
            contract = proposal.write_tool_contract(tool_id)

            self.assertEqual(contract.risk_flags, risk)
            self.assertEqual(contract.confirmation, "REQUIRED")
            self.assertEqual(contract.kind, "WRITE")

    def test_all_five_require_confirmation(self) -> None:
        for tool_id in proposal.PROPOSAL_TOOL_IDS:
            self.assertEqual(
                proposal.write_tool_contract(
                    tool_id,
                ).confirmation,
                "REQUIRED",
            )

    def test_the_write_tools_are_not_in_the_read_catalogue(
        self,
    ) -> None:
        for tool_id in proposal.PROPOSAL_TOOL_IDS:
            self.assertNotIn(
                tool_id,
                loop.CANONICAL_TOOL_IDS,
            )

    def test_authority_anchor_passes(self) -> None:
        proposal.assert_proposal_authority()


class ModelPatchGateTests(unittest.TestCase):
    """The model-facing delta gate of the four new tools."""

    def test_valid_update_patch_passes(self) -> None:
        self.assertEqual(
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {"title": "Nuevo título"},
            ),
            [],
        )

    def test_task_id_is_d_owned_and_forbidden(self) -> None:
        self.assertIn(
            "forbidden_argument:taskId",
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {"taskId": TASK_ID, "title": "x"},
            ),
        )

    def test_expected_version_is_d_owned_and_forbidden(self) -> None:
        self.assertIn(
            "forbidden_argument:expectedVersion",
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {"expectedVersion": 3},
            ),
        )

    def test_authoritative_checklist_is_forbidden_from_the_model(
        self,
    ) -> None:
        self.assertIn(
            "forbidden_argument:checklist",
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {
                    "checklist": [
                        {"text": "x", "checked": False}
                    ]
                },
            ),
        )

    def test_status_is_forbidden(self) -> None:
        self.assertIn(
            "forbidden_argument:status",
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {"status": "completed"},
            ),
        )

    def test_empty_update_patch_is_rejected(self) -> None:
        self.assertIn(
            "empty_update_patch",
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {},
            ),
        )

    def test_unknown_update_argument_is_rejected(self) -> None:
        self.assertIn(
            "unknown_argument:dueDateTime",
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {"dueDateTime": "2026-10-30T18:00"},
            ),
        )

    def test_time_without_date_is_valid_at_model_level(self) -> None:
        # The merge with the authoritative date belongs to the loop.
        self.assertEqual(
            proposal.validate_model_write_arguments(
                "planner.tasks.update",
                {"dueTime": "18:00"},
            ),
            [],
        )

    def test_lifecycle_tools_accept_only_an_empty_body(self) -> None:
        for tool_id in (
            "planner.tasks.complete",
            "planner.tasks.trash",
            "planner.tasks.restore",
        ):
            self.assertEqual(
                proposal.validate_model_write_arguments(
                    tool_id,
                    {},
                ),
                [],
            )

            self.assertEqual(
                proposal.validate_model_write_arguments(
                    tool_id,
                    {"title": "x"},
                ),
                ["unexpected_argument:title"],
            )


class FinalArgumentsTests(unittest.TestCase):
    """The final canonical argument validation of the proposals."""

    def test_valid_update_final_arguments_pass(self) -> None:
        self.assertEqual(
            proposal.validate_write_tool_arguments(
                "planner.tasks.update",
                {
                    "taskId": TASK_ID,
                    "expectedVersion": 3,
                    "title": "Nuevo título",
                },
            ),
            [],
        )

    def test_missing_task_id_is_rejected(self) -> None:
        self.assertIn(
            "missing_required:taskId",
            proposal.validate_write_tool_arguments(
                "planner.tasks.update",
                {"expectedVersion": 3, "title": "x"},
            ),
        )

    def test_missing_expected_version_is_rejected(self) -> None:
        self.assertIn(
            "missing_required:expectedVersion",
            proposal.validate_write_tool_arguments(
                "planner.tasks.update",
                {"taskId": TASK_ID, "title": "x"},
            ),
        )

    def test_invalid_version_is_rejected(self) -> None:
        self.assertIn(
            "below_minimum:expectedVersion",
            proposal.validate_write_tool_arguments(
                "planner.tasks.update",
                {
                    "taskId": TASK_ID,
                    "expectedVersion": 0,
                    "title": "x",
                },
            ),
        )

    def test_non_canonical_task_id_is_rejected(self) -> None:
        self.assertIn(
            "pattern_mismatch:taskId",
            proposal.validate_write_tool_arguments(
                "planner.tasks.update",
                {
                    "taskId": "not-a-uuid",
                    "expectedVersion": 3,
                    "title": "x",
                },
            ),
        )

    def test_due_time_without_due_date_is_rejected(self) -> None:
        self.assertIn(
            "due_time_without_due_date",
            proposal.validate_write_tool_arguments(
                "planner.tasks.update",
                {
                    "taskId": TASK_ID,
                    "expectedVersion": 3,
                    "dueTime": "18:00",
                },
            ),
        )

    def test_checklist_item_shape_is_validated(self) -> None:
        self.assertIn(
            "invalid_type:checklist[0].checked",
            proposal.validate_write_tool_arguments(
                "planner.tasks.update",
                {
                    "taskId": TASK_ID,
                    "expectedVersion": 3,
                    "checklist": [
                        {"text": "x", "checked": "yes"}
                    ],
                },
            ),
        )

    def test_lifecycle_body_is_exactly_task_id_and_version(
        self,
    ) -> None:
        for tool_id in (
            "planner.tasks.complete",
            "planner.tasks.trash",
            "planner.tasks.restore",
        ):
            self.assertEqual(
                proposal.validate_write_tool_arguments(
                    tool_id,
                    {
                        "taskId": TASK_ID,
                        "expectedVersion": 3,
                    },
                ),
                [],
            )

            self.assertEqual(
                proposal.validate_write_tool_arguments(
                    tool_id,
                    {
                        "taskId": TASK_ID,
                        "expectedVersion": 3,
                        "title": "x",
                    },
                ),
                ["unknown_argument:title"],
            )

    def test_unknown_tool_fails_closed(self) -> None:
        self.assertEqual(
            proposal.validate_write_tool_arguments(
                "planner.tasks.reopen",
                {},
            ),
            ["unknown_tool"],
        )

    def test_create_keeps_the_t11_validation(self) -> None:
        self.assertEqual(
            proposal.validate_write_tool_arguments(
                "planner.tasks.create",
                {"title": "Comprar leche"},
            ),
            [],
        )

        self.assertIn(
            "missing_required:title",
            proposal.validate_write_tool_arguments(
                "planner.tasks.create",
                {},
            ),
        )


class T12ProposalBuilderTests(unittest.TestCase):
    """ActionProposal for all five tools (sections 17-21)."""

    def build(
        self,
        tool_id: str,
        arguments: dict,
        summary_context: dict | None = None,
    ):
        return proposal.build_action_proposal(
            tool_id,
            arguments,
            created_at=FIXED_CREATED_AT,
            summary_context=summary_context,
        )

    def test_update_proposal_is_proposed_low_mutation(self) -> None:
        built = self.build(
            "planner.tasks.update",
            {
                "taskId": TASK_ID,
                "expectedVersion": 3,
                "dueDate": "2026-10-30",
            },
            {"task_title": "Comprar materiales"},
        )

        self.assertEqual(built.status, "PROPOSED")
        self.assertEqual(built.tool_id, "planner.tasks.update")
        self.assertEqual(
            built.risk_flags,
            ("LOW_MUTATION",),
        )
        self.assertEqual(built.confirmation, "REQUIRED")
        self.assertTrue(built.proposal_id.startswith("prop_"))
        self.assertEqual(built.created_at, FIXED_CREATED_AT)

    def test_update_summary_matches_the_frozen_example(self) -> None:
        built = self.build(
            "planner.tasks.update",
            {
                "taskId": TASK_ID,
                "expectedVersion": 3,
                "dueDate": "2026-10-30",
            },
            {"task_title": "Comprar materiales"},
        )

        self.assertEqual(
            built.summary,
            (
                "Actualizar tarea\n"
                "Título: Comprar materiales\n"
                "Fecha: 30/10/2026"
            ),
        )

    def test_complete_summary_matches_the_frozen_example(self) -> None:
        built = self.build(
            "planner.tasks.complete",
            {"taskId": TASK_ID, "expectedVersion": 3},
            {"task_title": "Comprar materiales"},
        )

        self.assertEqual(
            built.summary,
            "Completar tarea\nComprar materiales",
        )

    def test_trash_summary_matches_the_frozen_example(self) -> None:
        built = self.build(
            "planner.tasks.trash",
            {"taskId": TASK_ID, "expectedVersion": 3},
            {"task_title": "Comprar materiales"},
        )

        self.assertEqual(
            built.summary,
            "Mover a papelera\nComprar materiales",
        )

    def test_restore_summary_matches_the_frozen_example(self) -> None:
        built = self.build(
            "planner.tasks.restore",
            {"taskId": TASK_ID, "expectedVersion": 3},
            {"task_title": "Comprar materiales"},
        )

        self.assertEqual(
            built.summary,
            "Restaurar tarea\nComprar materiales",
        )

    def test_checklist_summary_matches_the_frozen_example(
        self,
    ) -> None:
        built = self.build(
            "planner.tasks.update",
            {
                "taskId": TASK_ID,
                "expectedVersion": 3,
                "checklist": [
                    {"text": "Comprar cartulina", "checked": False}
                ],
            },
            {
                "task_title": "Preparar maqueta",
                "checklist_op": {
                    "op": "add",
                    "item": "Comprar cartulina",
                },
            },
        )

        self.assertEqual(
            built.summary,
            (
                'Checklist\n'
                'Agregar "Comprar cartulina"\n'
                'a "Preparar maqueta"'
            ),
        )

    def test_trash_proposal_carries_moderate_mutation(self) -> None:
        built = self.build(
            "planner.tasks.trash",
            {"taskId": TASK_ID, "expectedVersion": 3},
            {"task_title": "Comprar materiales"},
        )

        self.assertEqual(
            built.risk_flags,
            ("MODERATE_MUTATION",),
        )

    def test_arguments_snapshot_is_read_only(self) -> None:
        built = self.build(
            "planner.tasks.update",
            {
                "taskId": TASK_ID,
                "expectedVersion": 3,
                "title": "Nuevo título",
            },
            {"task_title": "Comprar materiales"},
        )

        with self.assertRaises(TypeError):
            built.arguments["title"] = "otro"  # type: ignore[index]

    def test_summary_context_never_enters_the_arguments(self) -> None:
        built = self.build(
            "planner.tasks.update",
            {
                "taskId": TASK_ID,
                "expectedVersion": 3,
                "title": "Nuevo título",
            },
            {
                "task_title": "Comprar materiales",
                "checklist_op": {"op": "add", "item": "x"},
            },
        )

        self.assertNotIn("task_title", built.arguments)
        self.assertNotIn("checklist_op", built.arguments)


class T12ConfirmBoundaryTests(unittest.TestCase):
    """Confirmation of the four new tools fails closed (section 22)."""

    CONVERSATION = "conv_t123confirm_aaaa"

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def pending_update_proposal(self):
        return proposal.build_action_proposal(
            "planner.tasks.update",
            {
                "taskId": TASK_ID,
                "expectedVersion": 3,
                "title": "Nuevo título",
            },
            created_at=FIXED_CREATED_AT,
            summary_context={"task_title": "Comprar materiales"},
        )

    def test_confirm_of_a_new_t12_tool_fails_closed(self) -> None:
        for tool_id, args in (
            (
                "planner.tasks.update",
                {
                    "taskId": TASK_ID,
                    "expectedVersion": 3,
                    "title": "x",
                },
            ),
            (
                "planner.tasks.complete",
                {"taskId": TASK_ID, "expectedVersion": 3},
            ),
            (
                "planner.tasks.trash",
                {"taskId": TASK_ID, "expectedVersion": 3},
            ),
            (
                "planner.tasks.restore",
                {"taskId": TASK_ID, "expectedVersion": 3},
            ),
        ):
            built = proposal.build_action_proposal(
                tool_id,
                args,
                created_at=FIXED_CREATED_AT,
            )

            proposal.register_pending_proposal(
                self.CONVERSATION,
                built,
            )

            transitioned = proposal.apply_proposal_action(
                self.CONVERSATION,
                built.proposal_id,
                "confirm",
            )

            self.assertEqual(
                transitioned.status,
                "CONFIRMED",
            )
            self.assertEqual(
                transitioned.proposal_id,
                built.proposal_id,
            )

            still = proposal.get_pending_proposal(
                self.CONVERSATION,
            )

            self.assertIsNone(still)

            terminal = proposal.get_terminal_proposal(
                self.CONVERSATION,
            )

            self.assertIsNotNone(terminal)
            self.assertEqual(terminal.status, "CONFIRMED")

            reset_state()

    def test_cancel_of_a_new_t12_tool_keeps_t11_behavior(self) -> None:
        built = self.pending_update_proposal()

        proposal.register_pending_proposal(
            self.CONVERSATION,
            built,
        )

        transitioned = proposal.apply_proposal_action(
            self.CONVERSATION,
            built.proposal_id,
            "cancel",
        )

        self.assertEqual(transitioned.status, "CANCELLED")

    def test_execution_state_machine_admits_restore(self) -> None:
        # T12-6_RESTORE_DEFERRED is removed: restore is execution-capable.
        built = proposal.build_action_proposal(
            "planner.tasks.restore",
            {"taskId": TASK_ID, "expectedVersion": 3},
            created_at=FIXED_CREATED_AT,
        )

        from dataclasses import replace as dc_replace

        confirmed = dc_replace(
            built,
            status=proposal.PROPOSAL_STATUS_CONFIRMED,
        )

        proposal._TERMINAL_PROPOSALS[self.CONVERSATION] = confirmed

        executing = proposal.begin_proposal_execution(
            self.CONVERSATION,
            confirmed.proposal_id,
        )

        self.assertEqual(
            executing.status,
            proposal.PROPOSAL_STATUS_EXECUTING,
        )
        self.assertEqual(
            executing.proposal_id,
            confirmed.proposal_id,
        )

    def test_non_catalog_tool_still_refused_execution(self) -> None:
        # A tool outside the frozen write catalog must never enter execution.
        from dataclasses import replace as dc_replace

        built = proposal.build_action_proposal(
            "planner.tasks.restore",
            {"taskId": TASK_ID, "expectedVersion": 3},
            created_at=FIXED_CREATED_AT,
        )

        confirmed = dc_replace(
            built,
            status=proposal.PROPOSAL_STATUS_CONFIRMED,
        )

        proposal._TERMINAL_PROPOSALS[self.CONVERSATION] = confirmed

        # Tamper the tool id to a non-catalog write tool.
        tampered = dc_replace(
            confirmed,
            tool_id="planner.tasks.reopen",
        )
        proposal._TERMINAL_PROPOSALS[self.CONVERSATION] = tampered

        try:
            proposal.begin_proposal_execution(
                self.CONVERSATION,
                tampered.proposal_id,
            )

        except proposal.ActionProposalError as error:
            self.assertEqual(
                error.code,
                "PROPOSAL_EXECUTION_GATES_FAILED",
            )

        else:
            raise AssertionError(
                "a non-catalog tool must not enter execution",
            )

    def test_create_confirm_path_is_unchanged(self) -> None:
        built = proposal.build_action_proposal(
            "planner.tasks.create",
            {"title": "Comprar leche"},
            created_at=FIXED_CREATED_AT,
        )

        proposal.register_pending_proposal(
            self.CONVERSATION,
            built,
        )

        transitioned = proposal.apply_proposal_action(
            self.CONVERSATION,
            built.proposal_id,
            "confirm",
        )

        self.assertEqual(transitioned.status, "CONFIRMED")


# ---------------------------------------------------------------------------
# The additive v2 decision gate
# ---------------------------------------------------------------------------


class V2DecisionGateTests(unittest.TestCase):
    """The strict parse gate of the T12 additive decision fields."""

    def parse(self, raw: dict):
        return loop.parse_action_proposal_decision(raw)

    def expect_invalid(self, raw: dict) -> None:
        from homi_tool_contract import ToolDecisionError

        with self.assertRaises(ToolDecisionError):
            self.parse(raw)

    def test_update_decision_with_target_and_patch_is_accepted(
        self,
    ) -> None:
        parsed = self.parse(
            v2_update_decision(
                title_target("Comprar materiales"),
                {"title": "Nuevo título"},
            ),
        )

        self.assertEqual(
            parsed.tool_id,
            "planner.tasks.update",
        )
        self.assertEqual(
            parsed.target,
            (None, "Comprar materiales"),
        )
        self.assertEqual(
            parsed.arguments,
            {"title": "Nuevo título"},
        )
        self.assertIsNone(parsed.edit_patch)
        self.assertIsNone(parsed.proposal_action)

    def test_lifecycle_decision_with_id_target_is_accepted(self) -> None:
        parsed = self.parse(
            v2_lifecycle_decision(
                "planner.tasks.complete",
                id_target(),
            ),
        )

        self.assertEqual(
            parsed.target,
            (TASK_ID, None),
        )
        self.assertEqual(parsed.arguments, {})

    def test_missing_target_is_rejected(self) -> None:
        raw = v2_update_decision(
            title_target("x"),
            {"title": "y"},
        )

        del raw["target"]

        self.expect_invalid(raw)

    def test_target_with_both_id_and_title_is_rejected(self) -> None:
        raw = v2_update_decision(
            {
                "kind": "task",
                "task_id": TASK_ID,
                "task_title": "Comprar materiales",
            },
            {"title": "y"},
        )

        self.expect_invalid(raw)

    def test_target_with_a_fabricated_non_uuid_id_is_rejected(
        self,
    ) -> None:
        raw = v2_update_decision(
            {
                "kind": "task",
                "task_id": "la-tarea-de-ayer",
                "task_title": None,
            },
            {"title": "y"},
        )

        self.expect_invalid(raw)

    def test_target_with_unknown_field_is_rejected(self) -> None:
        raw = v2_update_decision(
            {
                "kind": "task",
                "task_id": None,
                "task_title": "x",
                "version": 3,
            },
            {"title": "y"},
        )

        self.expect_invalid(raw)

    def test_model_expected_version_in_arguments_is_rejected(
        self,
    ) -> None:
        raw = v2_update_decision(
            title_target("x"),
            {"expectedVersion": 3},
        )

        self.expect_invalid(raw)

    def test_model_task_id_in_arguments_is_rejected(self) -> None:
        raw = v2_update_decision(
            title_target("x"),
            {"taskId": TASK_ID},
        )

        self.expect_invalid(raw)

    def test_model_full_checklist_is_rejected(self) -> None:
        raw = v2_update_decision(
            title_target("x"),
            {
                "checklist": [
                    {"text": "a", "checked": False}
                ]
            },
        )

        self.expect_invalid(raw)

    def test_checklist_patch_on_complete_is_rejected(self) -> None:
        raw = v2_lifecycle_decision(
            "planner.tasks.complete",
            id_target(),
        )

        raw["checklist_patch"] = {"op": "add", "item": "x"}

        self.expect_invalid(raw)

    def test_assign_member_name_on_trash_is_rejected(self) -> None:
        raw = v2_lifecycle_decision(
            "planner.tasks.trash",
            id_target(),
        )

        raw["assign_member_name"] = "Juli"

        self.expect_invalid(raw)

    def test_create_with_target_is_rejected(self) -> None:
        raw = dict(WRITE_CREATE_V2_ENVELOPE)

        raw["target"] = title_target("Comprar materiales")

        self.expect_invalid(raw)

    def test_read_tool_with_target_is_rejected(self) -> None:
        raw = dict(READ_TASKS_V2_ENVELOPE)

        raw["target"] = id_target()

        self.expect_invalid(raw)

    def test_direct_response_with_checklist_patch_is_rejected(
        self,
    ) -> None:
        raw = dict(DIRECT_RESPONSE_V2)

        raw["checklist_patch"] = {"op": "add", "item": "x"}

        self.expect_invalid(raw)

    def test_t12_tool_with_proposal_action_is_rejected(self) -> None:
        raw = v2_lifecycle_decision(
            "planner.tasks.trash",
            id_target(),
        )

        raw["proposal_action"] = "confirm"

        self.expect_invalid(raw)

    def test_valid_checklist_patch_is_accepted(self) -> None:
        raw = v2_update_decision(
            title_target("Preparar maqueta"),
            {},
            checklist_patch={
                "op": "add",
                "item": "Comprar cartulina",
            },
        )

        parsed = self.parse(raw)

        self.assertEqual(
            parsed.checklist_patch,
            {
                "op": "add",
                "item": "Comprar cartulina",
                "newItemText": None,
                "index": None,
            },
        )

    def test_unknown_write_tool_is_rejected(self) -> None:
        for tool_id in (
            "planner.tasks.reopen",
            "planner.tasks.delete",
            "planner.tasks.cancel",
            "planner.tasks.verify",
            "planner.tasks.checklist.add",
        ):
            raw = v2_lifecycle_decision(tool_id, id_target())

            self.expect_invalid(raw)

    def test_frozen_v1_never_learns_the_new_tools(self) -> None:
        from homi_tool_contract import (
            ToolDecisionError,
            parse_decision,
        )

        with self.assertRaises(ToolDecisionError):
            parse_decision(
                {
                    "decision": "tool_request",
                    "answer": None,
                    "question": None,
                    "tool_id": "planner.tasks.update",
                    "arguments": {"taskId": TASK_ID},
                },
            )

        with self.assertRaises(ToolDecisionError):
            parse_decision(
                {
                    "decision": "tool_request",
                    "answer": None,
                    "question": None,
                    "tool_id": "planner.tasks.list",
                    "arguments": {},
                    "target": id_target(),
                },
            )


# ---------------------------------------------------------------------------
# Loop dispatch (fake Node A, fake trusted READs, ZERO mutation)
# ---------------------------------------------------------------------------


class T12LoopTestBase(unittest.TestCase):

    suffix = "t123loop"

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def conversation_id(self) -> str:
        return f"conv_{self.suffix}_aaaaaaaa"

    def run_turn(
        self,
        decision: dict,
        executor: T12FakeExecutor,
        *,
        suffix: str | None = None,
        authorization: str | None = AUTH,
    ):
        transport = f.tool_transport(decision=decision)

        request = f.make_tool_request(
            suffix=self.suffix
            if suffix is None
            else suffix,
        )

        def call():
            with patched(transport):
                return asyncio.run(
                    loop.invoke_with_tools_v2(
                        request,
                        authorization,
                    )
                )

        with f.installed_executor(executor):
            envelope = call()

        return envelope, executor

    def proposal_body(self, envelope):
        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        self.assertEqual(
            envelope.result["decision_kind"],
            "action_proposal",
        )

        return envelope.result["proposal"]["proposal"]

    def clarify_body(self, envelope):
        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        self.assertEqual(
            envelope.result["decision_kind"],
            "clarify",
        )

        self.assertIsInstance(
            envelope.result["answer"],
            str,
        )

        return envelope.result["answer"]


class T12UpdateDispatchTests(T12LoopTestBase):
    """planner.tasks.update proposal behavior (sections 4-9)."""

    def executor(
        self,
        *,
        tasks=None,
        task=None,
    ) -> T12FakeExecutor:
        return T12FakeExecutor(
            tasks=(
                [task_row()] if tasks is None else tasks
            ),
            task=(
                task_row(due_date="2026-10-30")
                if task is None
                else task
            ),
        )

    def test_update_by_unique_exact_title_proposes(
        self,
    ) -> None:
        executor = self.executor()

        envelope, executor = self.run_turn(
            v2_update_decision(
                title_target("Comprar materiales"),
                {"title": "Comprar materiales y herramientas"},
            ),
            executor,
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["tool_id"],
            "planner.tasks.update",
        )
        self.assertEqual(body["status"], "PROPOSED")
        self.assertEqual(
            body["arguments"],
            {
                "taskId": TASK_ID,
                "expectedVersion": 3,
                "title": (
                    "Comprar materiales y herramientas"
                ),
            },
        )

        pending = proposal.get_pending_proposal(
            self.conversation_id(),
        )

        self.assertEqual(
            pending.proposal_id,
            body["proposal_id"],
        )

        executed = [plan.tool_id for plan, _ in executor.calls]

        self.assertEqual(
            executed,
            ["planner.tasks.list", "planner.tasks.get"],
        )

    def test_update_by_explicit_task_id_skips_the_listing(
        self,
    ) -> None:
        executor = self.executor()

        envelope, executor = self.run_turn(
            v2_update_decision(
                id_target(),
                {"description": "Detalle nuevo"},
            ),
            executor,
        )

        self.proposal_body(envelope)

        executed = [plan.tool_id for plan, _ in executor.calls]

        self.assertEqual(executed, ["planner.tasks.get"])

    def test_zero_title_match_clarifies(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                title_target("Comprar cartulina"),
                {"title": "x"},
            ),
            self.executor(),
        )

        answer = self.clarify_body(envelope)

        self.assertIn("No encontré", answer)

        self.assertIsNone(
            proposal.get_pending_proposal(
                self.conversation_id(),
            ),
        )

    def test_multiple_title_matches_clarify(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                title_target("Comprar materiales"),
                {"title": "x"},
            ),
            self.executor(
                tasks=[
                    task_row(),
                    task_row(id=OTHER_TASK_ID),
                ],
            ),
        )

        answer = self.clarify_body(envelope)

        self.assertIn("más de una tarea", answer)

    def test_time_only_intent_merges_the_authoritative_date(
        self,
    ) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"dueTime": "18:00"},
            ),
            self.executor(
                task=task_row(
                    due_date="2026-10-30",
                    due_time=None,
                ),
            ),
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"]["dueDate"],
            "2026-10-30",
        )
        self.assertEqual(
            body["arguments"]["dueTime"],
            "18:00",
        )

    def test_time_only_intent_without_a_date_clarifies(
        self,
    ) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"dueTime": "18:00"},
            ),
            self.executor(
                task=task_row(
                    due_date=None,
                    due_time=None,
                ),
            ),
        )

        answer = self.clarify_body(envelope)

        self.assertIn("no tiene fecha", answer)

    def test_clear_time_proposes_due_time_null(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"dueTime": None},
            ),
            self.executor(
                task=task_row(
                    due_date="2026-10-30",
                    due_time="18:00:00",
                ),
            ),
        )

        body = self.proposal_body(envelope)

        self.assertIsNone(body["arguments"]["dueTime"])
        self.assertNotIn("dueDate", body["arguments"])

    def test_clear_date_clears_the_time_invariant(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"dueDate": None},
            ),
            self.executor(
                task=task_row(
                    due_date="2026-10-30",
                    due_time="18:00:00",
                ),
            ),
        )

        body = self.proposal_body(envelope)

        self.assertIsNone(body["arguments"]["dueDate"])
        self.assertIsNone(body["arguments"]["dueTime"])

    def test_unassign_proposes_null_assignee(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"assignedToMemberId": None},
            ),
            self.executor(
                task=task_row(
                    assigned_to_member_id=MEMBER_ID,
                ),
            ),
        )

        body = self.proposal_body(envelope)

        self.assertIsNone(
            body["arguments"]["assignedToMemberId"],
        )

    def test_assign_by_explicit_uuid_passes_through(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"assignedToMemberId": MEMBER_ID},
            ),
            self.executor(),
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"]["assignedToMemberId"],
            MEMBER_ID,
        )

    def test_assign_by_natural_language_name_clarifies(
        self,
    ) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {},
                assign_member_name="Juli",
            ),
            self.executor(),
        )

        answer = self.clarify_body(envelope)

        self.assertIn("no puedo asignar por nombre", answer)

    def test_preflight_not_found_clarifies(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"title": "x"},
            ),
            T12FakeExecutor(get_not_found=True),
        )

        answer = self.clarify_body(envelope)

        self.assertIn("No encontré esa tarea", answer)

    def test_missing_credential_fails_closed(self) -> None:
        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"title": "x"},
            ),
            self.executor(),
            authorization=None,
        )

        self.assertEqual(envelope.status.value, "ERROR")

        self.assertEqual(
            envelope.error.details.get("reason"),
            "missing_tool_authorization",
        )

    def test_update_replaces_the_single_active_proposal(
        self,
    ) -> None:
        executor = self.executor()

        first, _ = self.run_turn(
            dict(WRITE_CREATE_V2_ENVELOPE),
            executor,
            suffix="t123repl1",
        )

        first_body = first.result["proposal"]["proposal"]

        second, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {"title": "x"},
            ),
            executor,
            suffix="t123repl1",
        )

        second_body = self.proposal_body(second)

        conversation = "conv_t123repl1_aaaaaaaa"

        active = proposal.get_pending_proposal(conversation)

        self.assertEqual(
            active.proposal_id,
            second_body["proposal_id"],
        )

        self.assertNotEqual(
            active.proposal_id,
            first_body["proposal_id"],
        )


class T12ChecklistDispatchTests(T12LoopTestBase):
    """The checklist read-modify-write proposals (sections 11-13)."""

    CHECKLIST = [
        {"text": "Comprar cartulina", "checked": False},
        {"text": "Cortar la cartulina", "checked": True},
        {"text": "Pegar la maqueta", "checked": False},
    ]

    def executor(self, checklist=None) -> T12FakeExecutor:
        return T12FakeExecutor(
            task=task_row(
                checklist=(
                    [dict(e) for e in self.CHECKLIST]
                    if checklist is None
                    else checklist
                ),
            ),
        )

    def run_checklist_turn(self, checklist_patch: dict):
        return self.run_turn(
            v2_update_decision(
                id_target(),
                {},
                checklist_patch=checklist_patch,
            ),
            self.executor(),
        )

    def test_checklist_add_transform(self) -> None:
        envelope, _ = self.run_checklist_turn(
            {"op": "add", "item": "Comprar pegamento"},
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"]["checklist"],
            self.CHECKLIST
            + [
                {
                    "text": "Comprar pegamento",
                    "checked": False,
                }
            ],
        )

        self.assertEqual(
            body["summary"],
            (
                'Checklist\n'
                'Agregar "Comprar pegamento"\n'
                'a "Comprar materiales"'
            ),
        )

    def test_checklist_edit_transform(self) -> None:
        envelope, _ = self.run_checklist_turn(
            {
                "op": "edit",
                "item": "Comprar cartulina",
                "newItemText": "Comprar cartulina gruesa",
            },
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"]["checklist"][0],
            {
                "text": "Comprar cartulina gruesa",
                "checked": False,
            },
        )
        self.assertEqual(
            body["arguments"]["checklist"][1],
            self.CHECKLIST[1],
        )
        self.assertEqual(
            body["arguments"]["checklist"][2],
            self.CHECKLIST[2],
        )

    def test_checklist_complete_transform(self) -> None:
        envelope, _ = self.run_checklist_turn(
            {"op": "complete", "item": "Pegar la maqueta"},
        )

        body = self.proposal_body(envelope)

        self.assertTrue(
            body["arguments"]["checklist"][2]["checked"],
        )

    def test_checklist_reopen_transform(self) -> None:
        envelope, _ = self.run_checklist_turn(
            {"op": "reopen", "item": "Cortar la cartulina"},
        )

        body = self.proposal_body(envelope)

        self.assertFalse(
            body["arguments"]["checklist"][1]["checked"],
        )

    def test_checklist_remove_transform(self) -> None:
        envelope, _ = self.run_checklist_turn(
            {"op": "remove", "item": "Cortar la cartulina"},
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"]["checklist"],
            [self.CHECKLIST[0], self.CHECKLIST[2]],
        )

    def test_duplicate_checklist_match_clarifies(self) -> None:
        executor = T12FakeExecutor(
            task=task_row(
                checklist=[
                    {"text": "Comprar cartulina", "checked": False},
                    {"text": "comprar cartulina", "checked": True},
                ],
            ),
        )

        envelope, _ = self.run_turn(
            v2_update_decision(
                id_target(),
                {},
                checklist_patch={
                    "op": "remove",
                    "item": "Comprar Cartulina",
                },
            ),
            executor,
        )

        answer = self.clarify_body(envelope)

        self.assertIn("varios ítems", answer)

    def test_checklist_zero_match_clarifies(self) -> None:
        envelope, _ = self.run_checklist_turn(
            {"op": "complete", "item": "Pintar todo"},
        )

        answer = self.clarify_body(envelope)

        self.assertIn("No encontré ese ítem", answer)


class T12LifecycleDispatchTests(T12LoopTestBase):
    """complete / trash / restore proposal behavior (sections 14-16)."""

    def test_complete_proposal(self) -> None:
        executor = T12FakeExecutor(
            task=task_row(status="pending"),
        )

        envelope, executor = self.run_turn(
            v2_lifecycle_decision(
                "planner.tasks.complete",
                id_target(),
            ),
            executor,
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["tool_id"],
            "planner.tasks.complete",
        )
        self.assertEqual(
            body["arguments"],
            {"taskId": TASK_ID, "expectedVersion": 3},
        )
        self.assertEqual(body["risk"], ["LOW_MUTATION"])
        self.assertEqual(body["confirmation"], "REQUIRED")
        self.assertEqual(body["status"], "PROPOSED")
        self.assertEqual(
            body["summary"],
            "Completar tarea\nComprar materiales",
        )

    def test_complete_of_a_completed_task_clarifies(self) -> None:
        envelope, _ = self.run_turn(
            v2_lifecycle_decision(
                "planner.tasks.complete",
                id_target(),
            ),
            T12FakeExecutor(
                task=task_row(status="completed"),
            ),
        )

        answer = self.clarify_body(envelope)

        self.assertIn("no se puede completar", answer)

    def test_complete_of_an_evidence_task_clarifies(self) -> None:
        envelope, _ = self.run_turn(
            v2_lifecycle_decision(
                "planner.tasks.complete",
                id_target(),
            ),
            T12FakeExecutor(
                task=task_row(
                    status="pending",
                    requires_verification=True,
                ),
            ),
        )

        answer = self.clarify_body(envelope)

        self.assertIn("no se puede completar", answer)

    def test_trash_proposal_is_moderate_mutation(self) -> None:
        executor = T12FakeExecutor(task=task_row())

        envelope, executor = self.run_turn(
            v2_lifecycle_decision(
                "planner.tasks.trash",
                id_target(),
            ),
            executor,
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["tool_id"],
            "planner.tasks.trash",
        )
        self.assertEqual(
            body["risk"],
            ["MODERATE_MUTATION"],
        )
        self.assertEqual(body["confirmation"], "REQUIRED")
        self.assertEqual(
            body["arguments"],
            {"taskId": TASK_ID, "expectedVersion": 3},
        )
        self.assertEqual(
            body["summary"],
            "Mover a papelera\nComprar materiales",
        )

        self.assertIn(
            "reversible",
            envelope.result["answer"],
        )

    async def _restore_preflight_trashed(self, request, credential, task_id):
        return task_row(
            trashed_at="2026-10-25T10:00:00+00:00",
        ), None

    async def _restore_preflight_operational(self, request, credential, task_id):
        return task_row(trashed_at=None), None

    async def _restore_preflight_not_found(self, request, credential, task_id):
        return None, "TASK_NOT_FOUND"

    def test_restore_proposal_of_a_trashed_task(self) -> None:
        set_internal_preflight_override(self._restore_preflight_trashed)

        try:
            envelope, _ = self.run_turn(
                v2_lifecycle_decision(
                    "planner.tasks.restore",
                    id_target(),
                ),
                T12FakeExecutor(),
            )

            body = self.proposal_body(envelope)

            self.assertEqual(
                body["tool_id"],
                "planner.tasks.restore",
            )
            self.assertEqual(body["risk"], ["LOW_MUTATION"])
            self.assertEqual(
                body["arguments"],
                {"taskId": TASK_ID, "expectedVersion": 3},
            )
            self.assertEqual(
                body["summary"],
                "Restaurar tarea\nComprar materiales",
            )
        finally:
            reset_internal_preflight_override()

    def test_restore_of_an_operational_task_clarifies(self) -> None:
        set_internal_preflight_override(self._restore_preflight_operational)

        try:
            envelope, _ = self.run_turn(
                v2_lifecycle_decision(
                    "planner.tasks.restore",
                    id_target(),
                ),
                T12FakeExecutor(),
            )

            answer = self.clarify_body(envelope)

            self.assertIn("no está en la papelera", answer)
        finally:
            reset_internal_preflight_override()

    def test_restore_preflight_not_found_clarifies(self) -> None:
        """With the frozen READ surface a trashed task is invisible.

        The 404 of ``planner.tasks.get`` can not distinguish "trashed"
        from "does not exist", so the expectedVersion can not be
        obtained deterministically and the turn fails closed to a
        clarify (T12-3 section 6 fail-closed rule; the trash READ
        surface gap is documented in the handoff).
        """

        set_internal_preflight_override(self._restore_preflight_not_found)

        try:
            envelope, _ = self.run_turn(
                v2_lifecycle_decision(
                    "planner.tasks.restore",
                    id_target(),
                ),
                T12FakeExecutor(),
            )

            answer = self.clarify_body(envelope)

            self.assertIn("No encontré esa tarea", answer)
        finally:
            reset_internal_preflight_override()

    def test_version_unavailable_fails_closed(self) -> None:
        envelope, _ = self.run_turn(
            v2_lifecycle_decision(
                "planner.tasks.trash",
                id_target(),
            ),
            T12FakeExecutor(
                task=task_row(version=None),
            ),
        )

        self.assertEqual(envelope.status.value, "ERROR")

        self.assertEqual(
            envelope.error.details.get("reason"),
            "expected_version_unavailable",
        )


class T12ExecutionBoundaryLoopTests(T12LoopTestBase):
    """The four new tools can not execute through the loop (§22-23)."""

    NL_CONFIRM = {
        "decision": "direct_response",
        "answer": "Dale, confirmo.",
        "question": None,
        "tool_id": None,
        "arguments": None,
        "proposal_edit_patch": None,
        "proposal_action": "confirm",
    }

    def test_confirm_of_a_t12_proposal_fails_closed_in_the_loop(
        self,
    ) -> None:
        executor = T12FakeExecutor(task=task_row())

        first, executor = self.run_turn(
            v2_lifecycle_decision(
                "planner.tasks.trash",
                id_target(),
            ),
            executor,
        )

        body = self.proposal_body(first)

        second, _ = self.run_turn(
            dict(self.NL_CONFIRM),
            executor,
        )

        self.assertEqual(second.status.value, "SUCCESS")

        self.assertEqual(
            second.result.get("proposal_action"),
            "confirmed",
        )

        transitioned = second.result["proposal"]["proposal"]

        self.assertEqual(
            transitioned["proposal_id"],
            body["proposal_id"],
        )
        self.assertEqual(transitioned["status"], "CONFIRMED")

        pending = proposal.get_pending_proposal(
            self.conversation_id(),
        )

        self.assertIsNone(pending)

        terminal = proposal.get_terminal_proposal(
            self.conversation_id(),
        )

        self.assertIsNotNone(terminal)
        self.assertEqual(terminal.status, "CONFIRMED")

        # ZERO MUTATION: no write tool executed; only trusted READ
        # calls of the preflight.
        executed = [plan.tool_id for plan, _ in executor.calls]

        self.assertNotIn("planner.tasks.trash", executed)
        self.assertNotIn("planner.tasks.update", executed)
        self.assertNotIn("planner.tasks.complete", executed)
        self.assertNotIn("planner.tasks.restore", executed)

    def test_cancel_of_a_t12_proposal_keeps_t11_behavior(
        self,
    ) -> None:
        executor = T12FakeExecutor(task=task_row())

        self.run_turn(
            v2_lifecycle_decision(
                "planner.tasks.update",
                id_target(),
                tool_id_override=None,
            )
            if False
            else v2_update_decision(
                id_target(),
                {"title": "x"},
            ),
            executor,
        )

        cancel = {
            "decision": "direct_response",
            "answer": "No, cancelalo.",
            "question": None,
            "tool_id": None,
            "arguments": None,
            "proposal_edit_patch": None,
            "proposal_action": "cancel",
        }

        envelope, _ = self.run_turn(cancel, executor)

        self.assertEqual(envelope.status.value, "SUCCESS")

        self.assertEqual(
            envelope.result["proposal_action"],
            "cancelled",
        )

        self.assertIsNone(
            proposal.get_pending_proposal(
                self.conversation_id(),
            ),
        )


class T12RegressionTests(T12LoopTestBase):
    """T11 create, READ and direct/clarify regressions (§24-26)."""

    def test_create_flow_is_unchanged(self) -> None:
        executor = T12FakeExecutor()

        envelope, executor = self.run_turn(
            dict(WRITE_CREATE_V2_ENVELOPE),
            executor,
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["tool_id"],
            "planner.tasks.create",
        )
        self.assertEqual(
            body["arguments"],
            {"title": "Comprar leche"},
        )
        self.assertEqual(body["risk"], ["LOW_MUTATION"])

        executed = [plan.tool_id for plan, _ in executor.calls]

        self.assertEqual(executed, [])

    def test_read_turn_stays_a_read(self) -> None:
        executor = T12FakeExecutor(tasks=[task_row()])

        envelope, executor = self.run_turn(
            dict(READ_TASKS_V2_ENVELOPE),
            executor,
        )

        self.assertEqual(envelope.status.value, "SUCCESS")

        self.assertEqual(
            envelope.result["decision_kind"],
            "tool_request",
        )

        executed = [plan.tool_id for plan, _ in executor.calls]

        self.assertEqual(executed, ["planner.tasks.list"])

        self.assertNotIn("proposal", envelope.result)

    def test_direct_response_stays_direct(self) -> None:
        executor = T12FakeExecutor()

        envelope, _ = self.run_turn(
            dict(DIRECT_RESPONSE_V2),
            executor,
        )

        self.assertEqual(envelope.status.value, "SUCCESS")

        self.assertEqual(
            envelope.result["decision_kind"],
            "direct_response",
        )

    def test_unsupported_reopen_does_not_map_to_a_fake_tool(
        self,
    ) -> None:
        executor = T12FakeExecutor(task=task_row())

        reopen_decision = {
            "decision": "tool_request",
            "answer": None,
            "question": None,
            "tool_id": "planner.tasks.reopen",
            "arguments": {},
            "proposal_edit_patch": None,
            "proposal_action": None,
            "target": id_target(),
        }

        envelope, _ = self.run_turn(
            reopen_decision,
            executor,
        )

        self.assertEqual(envelope.status.value, "ERROR")

        self.assertIsNone(
            proposal.get_pending_proposal(
                self.conversation_id(),
            ),
        )

    def test_hard_delete_is_not_emitted(self) -> None:
        executor = T12FakeExecutor(task=task_row())

        delete_decision = {
            "decision": "tool_request",
            "answer": None,
            "question": None,
            "tool_id": "planner.tasks.delete",
            "arguments": {},
            "proposal_edit_patch": None,
            "proposal_action": None,
            "target": id_target(),
        }

        envelope, _ = self.run_turn(
            delete_decision,
            executor,
        )

        self.assertEqual(envelope.status.value, "ERROR")

        self.assertIsNone(
            proposal.get_pending_proposal(
                self.conversation_id(),
            ),
        )


if __name__ == "__main__":
    unittest.main()
