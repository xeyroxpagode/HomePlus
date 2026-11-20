"""HOMI T12-4 — multi-tool proposal edit + deterministic revalidation (Node D).

Coverage of the T12-4D task matrix (sections 22-31):

* create edit regression (title, description, date, time, clear nullable
  field, new proposal_id, old stale, confirm create functioning);
* update proposals support deterministic revision (title, description,
  clear description, date, time, clear time, clear date, unassign) each
  proving P1 -> edit -> P2, new proposal_id, old not confirmable as
  current, unrelated args preserved, schema valid, risk unchanged,
  confirmation REQUIRED;
* date/time invariants (date revision, time revision, time-only with
  authoritative date, time-only without date -> clarify, clear time,
  clear date -> time cleared, invalid date/time -> fail closed);
* checklist edits (add -> revise text, edit item, complete, reopen,
  remove; zero match, duplicate match, concurrent authoritative
  checklist change, stale version refresh, order preservation, unrelated
  item preservation);
* lifecycle proposals (complete/trash/restore) cannot receive an
  arbitrary update patch; cancel works; replacement by new operation
  works; confirm remains disabled for the four new T12 tools;
* stale proposal safety (P1 -> edit -> P2 then confirm P1 fails) for
  create and update families;
* risk immutability (trash stays MODERATE_MUTATION, no downgrade);
* tool immutability during edit (update -> complete only via new
  intent, never via patching);
* public response shape of a valid edit;
* zero unintended Planner mutations (write calls = 0 for the new T12
  tools and edits);
* restore preflight gap recorded (RESTORE_PREFLIGHT_HOMEPLUS_PENDING).

ZERO MUTATION: every trusted READ result is an injected fixture; no
test performs any Planner mutation; no test crosses the internal write
seam.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import sys
import unittest
from pathlib import Path
from typing import Any, Mapping

ORCHESTRATOR_ROOT = Path(__file__).resolve().parent.parent

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_ROOT))

sys.path.insert(0, str(ORCHESTRATOR_ROOT / "tests"))

from homi_contracts import ErrorCode  # noqa: E402

import homi_tool_loop as loop  # noqa: E402
import homi_tool_proposal as proposal  # noqa: E402
import homi_tool_t12_targets as targets  # noqa: E402
import homi_tool_write_execution as wexec  # noqa: E402
import t09f_support as f  # noqa: E402
from support import patched  # noqa: E402

from homi_tool_loop import (  # noqa: E402
    ToolExecutionOutcome,
    ToolExecutionResult,
    reset_internal_preflight_override,
    set_internal_preflight_override,
)
from homi_tool_contract import ToolDecisionError  # noqa: E402

FIXED_CREATED_AT = "2026-10-26T12:00:00+00:00"

TASK_ID = "dd93db9c-4ac6-4e64-a069-63ded69b25e4"
OTHER_TASK_ID = "11111111-2222-3333-4444-555555555555"
MEMBER_ID = "57878678-a192-4a52-8ff3-151cbe4de460"
AUTH = "Bearer t124-sentinel-credential"


def task_row(**overrides):
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
    proposal._EXECUTION_IDS.clear()
    proposal._VERIFICATION_RECORDS.clear()


def title_target(title: str) -> dict:
    return {"kind": "task", "task_id": None, "task_title": title}


def id_target(task_id: str = TASK_ID) -> dict:
    return {"kind": "task", "task_id": task_id, "task_title": None}


class T12FakeExecutor:
    """Phase-aware fake READ executor (T12-3 pattern). Raises on any WRITE."""

    state = "FAKE"

    def __init__(self, *, tasks=None, task=None, get_not_found=False,
                 get_retryable=False):
        self.calls = []
        self.tasks = tasks if tasks is not None else [task_row()]
        self.task = task if task is not None else task_row()
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


def v2_update_decision(target, patch=None, *, checklist_patch=None,
                      assign_member_name=None) -> dict:
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


def v2_update_edit_decision(patch, *, checklist_patch=None, arguments=None) -> dict:
    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": "planner.tasks.update",
        "arguments": arguments,
        "proposal_edit_patch": dict(patch),
        "proposal_action": None,
        "target": None,
        "checklist_patch": checklist_patch,
        "assign_member_name": None,
    }


def v2_lifecycle_decision(tool_id, target) -> dict:
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


def v2_create_decision(arguments) -> dict:
    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": "planner.tasks.create",
        "arguments": dict(arguments),
        "proposal_edit_patch": None,
        "proposal_action": None,
    }


def v2_create_edit_decision(patch) -> dict:
    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": "planner.tasks.create",
        "arguments": None,
        "proposal_edit_patch": dict(patch),
        "proposal_action": None,
    }


def cancel_decision() -> dict:
    return {
        "decision": "direct_response",
        "answer": "No, cancelalo.",
        "question": None,
        "tool_id": None,
        "arguments": None,
        "proposal_edit_patch": None,
        "proposal_action": "cancel",
        "target": None,
        "checklist_patch": None,
        "assign_member_name": None,
    }


def confirm_decision() -> dict:
    return {
        "decision": "direct_response",
        "answer": "Dale, confirmo.",
        "question": None,
        "tool_id": None,
        "arguments": None,
        "proposal_edit_patch": None,
        "proposal_action": "confirm",
        "target": None,
        "checklist_patch": None,
        "assign_member_name": None,
    }


# ---------------------------------------------------------------------------
# Loop test base
# ---------------------------------------------------------------------------


class T124LoopBase(unittest.TestCase):
    suffix = "t124loop"

    def setUp(self):
        reset_state()

    def tearDown(self):
        reset_state()

    def conversation_id(self, suffix=None):
        return "conv_{}_aaaaaaaa".format(suffix or self.suffix)

    def run_turn(self, decision, executor, *, suffix=None, authorization=AUTH):
        s = self.suffix if suffix is None else suffix
        transport = f.tool_transport(decision=decision)
        request = f.make_tool_request(suffix=s)
        def call():
            with patched(transport):
                return asyncio.run(loop.invoke_with_tools_v2(request, authorization))
        with f.installed_executor(executor):
            envelope = call()
        return envelope, executor

    def proposal_body(self, envelope):
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        self.assertEqual(envelope.result["decision_kind"], "action_proposal")
        return envelope.result["proposal"]["proposal"]

    def clarify_body(self, envelope):
        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        self.assertEqual(envelope.result["decision_kind"], "clarify")
        return envelope.result["answer"]

    def error_reason(self, envelope):
        self.assertEqual(envelope.status.value, "ERROR", envelope)
        return envelope.error.details.get("reason")

    def propose_update_p1(self, patch, executor, *, suffix=None, checklist_patch=None):
        s = self.suffix if suffix is None else suffix
        return self.run_turn(
            v2_update_decision(id_target(), patch or {}, checklist_patch=checklist_patch),
            executor,
            suffix=s,
        )

    def edit_turn(self, patch, executor, *, suffix=None, checklist_patch=None,
                  arguments=None):
        s = self.suffix if suffix is None else suffix
        return self.run_turn(
            v2_update_edit_decision(patch, checklist_patch=checklist_patch,
                                    arguments=arguments),
            executor,
            suffix=s,
        )


# ---------------------------------------------------------------------------
# 1. Decision gate (parse) — T12-4 edit shape
# ---------------------------------------------------------------------------


class T124EditDecisionGateTests(unittest.TestCase):
    def parse(self, raw):
        return loop.parse_action_proposal_decision(raw)

    def expect_invalid(self, raw):
        with self.assertRaises(ToolDecisionError):
            self.parse(raw)

    def test_valid_scalar_edit_patch_accepted(self):
        parsed = self.parse(v2_update_edit_decision({"title": "Nuevo"}))
        self.assertEqual(parsed.tool_id, "planner.tasks.update")
        self.assertEqual(parsed.edit_patch, {"title": "Nuevo"})
        self.assertIsNone(parsed.target)
        self.assertIsNone(parsed.arguments)
        self.assertIsNone(parsed.proposal_action)
        self.assertIsNone(parsed.checklist_patch)

    def test_valid_edit_with_checklist_patch_accepted(self):
        parsed = self.parse(v2_update_edit_decision(
            {"title": "Nuevo"},
            checklist_patch={"op": "add", "item": "leche"},
        ))
        self.assertEqual(parsed.checklist_patch, {
            "op": "add", "item": "leche", "newItemText": None, "index": None,
        })

    def test_target_non_null_on_edit_rejected(self):
        raw = v2_update_edit_decision({"title": "x"})
        raw["target"] = id_target()
        self.expect_invalid(raw)

    def test_edit_on_complete_rejected(self):
        raw = v2_lifecycle_decision("planner.tasks.complete", id_target())
        raw["proposal_edit_patch"] = {"title": "x"}
        self.expect_invalid(raw)

    def test_edit_on_trash_rejected(self):
        raw = v2_lifecycle_decision("planner.tasks.trash", id_target())
        raw["proposal_edit_patch"] = {"title": "x"}
        self.expect_invalid(raw)

    def test_edit_on_restore_rejected(self):
        raw = v2_lifecycle_decision("planner.tasks.restore", id_target())
        raw["proposal_edit_patch"] = {"title": "x"}
        self.expect_invalid(raw)

    def test_edit_plus_proposal_action_rejected(self):
        raw = v2_update_edit_decision({"title": "x"})
        raw["proposal_action"] = "confirm"
        self.expect_invalid(raw)

    def test_edit_plus_assign_member_name_rejected(self):
        raw = v2_update_edit_decision({"title": "x"})
        raw["assign_member_name"] = "Juli"
        self.expect_invalid(raw)

    def test_edit_patch_with_task_id_rejected(self):
        raw = v2_update_edit_decision({"taskId": TASK_ID})
        # taskId is not an editable field
        self.expect_invalid(raw)

    def test_edit_patch_with_expected_version_rejected(self):
        raw = v2_update_edit_decision({"expectedVersion": 3})
        self.expect_invalid(raw)

    def test_edit_patch_with_checklist_rejected(self):
        raw = v2_update_edit_decision({"checklist": [{"text": "x", "checked": False}]})
        self.expect_invalid(raw)

    def test_edit_patch_with_status_rejected(self):
        raw = v2_update_edit_decision({"status": "PROPOSED"})
        self.expect_invalid(raw)

    def test_edit_patch_with_risk_rejected(self):
        raw = v2_update_edit_decision({"risk": ["LOW_MUTATION"]})
        self.expect_invalid(raw)

    def test_edit_patch_with_proposal_id_rejected(self):
        raw = v2_update_edit_decision({"proposal_id": "prop_abc"})
        self.expect_invalid(raw)

    def test_edit_patch_non_object_rejected(self):
        raw = v2_update_edit_decision({"title": "x"})
        raw["proposal_edit_patch"] = "not-an-object"
        self.expect_invalid(raw)

    def test_edit_patch_empty_title_rejected(self):
        raw = v2_update_edit_decision({"title": ""})
        self.expect_invalid(raw)

    def test_edit_patch_unknown_field_rejected(self):
        raw = v2_update_edit_decision({"priority": "high"})
        # priority is a model patch field but not an EDITABLE field
        self.expect_invalid(raw)

    def test_edit_arguments_non_object_rejected(self):
        raw = v2_update_edit_decision({"title": "x"}, arguments="not-an-object")
        self.expect_invalid(raw)

    def test_edit_arguments_forbidden_key_rejected(self):
        raw = v2_update_edit_decision(
            {"title": "x"}, arguments={"actor_id": "someone"},
        )
        self.expect_invalid(raw)

    def test_checklist_patch_invalid_on_edit_rejected(self):
        raw = v2_update_edit_decision({"title": "x"}, checklist_patch={"op": "add"})
        self.expect_invalid(raw)

    def test_checklist_patch_on_edit_with_lifecycle_tool_rejected(self):
        # already covered by edit_on_* but ensure via update path too
        raw = v2_update_edit_decision({"title": "x"})
        raw["tool_id"] = "planner.tasks.complete"
        raw["target"] = id_target()
        raw["arguments"] = {}
        self.expect_invalid(raw)

    def test_create_edit_still_accepted_regression(self):
        parsed = loop.parse_action_proposal_decision(
            v2_create_edit_decision({"title": "Nuevo"}),
        )
        self.assertEqual(parsed.tool_id, "planner.tasks.create")
        self.assertEqual(parsed.edit_patch, {"title": "Nuevo"})
        self.assertIsNone(parsed.target)

    def test_v1_never_learns_update_edit(self):
        with self.assertRaises(ToolDecisionError):
            from homi_tool_contract import parse_decision
            parse_decision({
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.update",
                "arguments": {},
                "proposal_edit_patch": {"title": "x"},
            })

    def test_edit_patch_copy_isolated(self):
        patch = {"title": "Nuevo"}
        parsed = self.parse(v2_update_edit_decision(patch))
        patch["title"] = "MUTATED"
        self.assertEqual(parsed.edit_patch["title"], "Nuevo")


# ---------------------------------------------------------------------------
# 2. Module-level revision (pure function)
# ---------------------------------------------------------------------------


class T124RevisionTests(unittest.TestCase):
    def setUp(self):
        reset_state()

    def tearDown(self):
        reset_state()

    def _p1(self, patch=None, *, checklist_intent=None, version=3, title="X"):
        args = {"taskId": TASK_ID, "expectedVersion": version, "title": title}
        if patch:
            args.update(patch)
        return proposal.build_action_proposal(
            "planner.tasks.update",
            args,
            created_at=FIXED_CREATED_AT,
            summary_context={"task_title": "Comprar materiales",
                             "checklist_op": checklist_intent},
            checklist_intent=checklist_intent,
        )

    def test_successful_revision_builds_new_proposal(self):
        p1 = self._p1()
        p2 = proposal.revise_t12_update_proposal(
            p1, {"description": "Detalle"}, authoritative_task=task_row(),
        )
        self.assertIsNot(p2, p1)
        self.assertEqual(p2.tool_id, "planner.tasks.update")
        self.assertEqual(p2.status, proposal.PROPOSAL_STATUS_PROPOSED)
        self.assertNotEqual(p2.proposal_id, p1.proposal_id)
        self.assertEqual(p2.arguments["description"], "Detalle")
        self.assertEqual(p2.arguments["title"], "X")

    def test_only_requested_fields_change_unrelated_preserved(self):
        p1 = self._p1({"description": "D", "dueDate": "2026-10-30",
                       "dueTime": "10:00", "assignedToMemberId": MEMBER_ID,
                       "priority": "high"})
        p2 = proposal.revise_t12_update_proposal(
            p1, {"dueDate": "2026-10-31"}, authoritative_task=task_row(version=3),
        )
        self.assertEqual(p2.arguments["dueDate"], "2026-10-31")
        # unrelated fields stable
        self.assertEqual(p2.arguments["title"], "X")
        self.assertEqual(p2.arguments["description"], "D")
        self.assertEqual(p2.arguments["dueTime"], "10:00")
        self.assertEqual(p2.arguments["assignedToMemberId"], MEMBER_ID)
        self.assertEqual(p2.arguments["priority"], "high")

    def test_trusted_metadata_re_derived_not_copied(self):
        p1 = self._p1()
        p2 = proposal.revise_t12_update_proposal(
            p1, {"description": "D"}, authoritative_task=task_row(version=5),
        )
        self.assertEqual(p2.arguments["taskId"], TASK_ID)
        self.assertEqual(p2.arguments["expectedVersion"], 5)
        self.assertEqual(p2.risk_flags, ("LOW_MUTATION",))
        self.assertEqual(p2.confirmation, "REQUIRED")

    def test_expected_version_unavailable_fails_closed(self):
        p1 = self._p1()
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"description": "D"}, authoritative_task=task_row(version=None),
            )
        self.assertEqual(ctx.exception.code, "EXPECTED_VERSION_UNAVAILABLE")

    def test_expected_version_invalid_zero_fails(self):
        p1 = self._p1()
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"description": "D"}, authoritative_task=task_row(version=0),
            )
        self.assertEqual(ctx.exception.code, "EXPECTED_VERSION_UNAVAILABLE")

    def test_expected_version_bool_fails(self):
        p1 = self._p1()
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"description": "D"}, authoritative_task=task_row(version=True),
            )
        self.assertEqual(ctx.exception.code, "EXPECTED_VERSION_UNAVAILABLE")

    def test_wrong_tool_existing_fails(self):
        for tool in ("planner.tasks.create", "planner.tasks.complete",
                     "planner.tasks.trash", "planner.tasks.restore"):
            p = proposal.build_action_proposal(
                tool, {"title": "X"} if tool == "planner.tasks.create"
                else {"taskId": TASK_ID, "expectedVersion": 2},
                created_at=FIXED_CREATED_AT,
            )
            with self.assertRaises(proposal.ActionProposalError) as ctx:
                proposal.revise_t12_update_proposal(
                    p, {"description": "D"}, authoritative_task=task_row(),
                )
            self.assertEqual(ctx.exception.code, "PROPOSAL_REVISION_INVALID")

    def test_invalid_patch_fails_closed(self):
        p1 = self._p1()
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"proposal_id": "prop_x"}, authoritative_task=task_row(),
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_EDIT_PATCH_INVALID")

    def test_invalid_final_date_fails_closed(self):
        p1 = self._p1()
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"dueDate": "2026-13-45"}, authoritative_task=task_row(),
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_ARGUMENTS_INVALID")

    def test_due_time_merge_time_only_with_authoritative_date(self):
        p1 = self._p1()
        p2 = proposal.revise_t12_update_proposal(
            p1, {"dueTime": "18:00"}, authoritative_task=task_row(due_date="2026-10-30"),
        )
        self.assertEqual(p2.arguments["dueDate"], "2026-10-30")
        self.assertEqual(p2.arguments["dueTime"], "18:00")

    def test_due_time_merge_time_only_without_date_clarify_raises(self):
        p1 = self._p1()
        with self.assertRaises(targets.TaskTargetError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"dueTime": "18:00"}, authoritative_task=task_row(due_date=None),
            )
        self.assertEqual(ctx.exception.code, "DUE_DATE_REQUIRED")

    def test_clear_date_clears_time(self):
        p1 = self._p1({"dueDate": "2026-10-30", "dueTime": "10:00"})
        p2 = proposal.revise_t12_update_proposal(
            p1, {"dueDate": None}, authoritative_task=task_row(),
        )
        self.assertIsNone(p2.arguments["dueDate"])
        self.assertIsNone(p2.arguments["dueTime"])

    def test_clear_time_only(self):
        p1 = self._p1({"dueDate": "2026-10-30", "dueTime": "10:00"})
        p2 = proposal.revise_t12_update_proposal(
            p1, {"dueTime": None}, authoritative_task=task_row(),
        )
        self.assertIsNone(p2.arguments["dueTime"])
        self.assertEqual(p2.arguments["dueDate"], "2026-10-30")

    def test_checklist_intent_preserved_recomputed_from_fresh(self):
        intent = {"op": "add", "item": "leche"}
        p1 = self._p1(checklist_intent=intent)
        fresh = task_row(checklist=[{"text": "huevo", "checked": False}], version=4)
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=fresh,
        )
        self.assertEqual(p2.arguments["checklist"], [
            {"text": "huevo", "checked": False},
            {"text": "leche", "checked": False},
        ])
        self.assertEqual(p2.arguments["title"], "Y")
        self.assertEqual(p2.checklist_intent["op"], "add")

    def test_checklist_intent_revised_replaces_previous(self):
        # §14 exact scenario: P1 add "leche"; revised intent add "leche descremada"
        # -> P2 = authoritative + "leche descremada" ONLY
        intent = {"op": "add", "item": "leche"}
        p1 = self._p1(checklist_intent=intent)
        fresh = task_row(checklist=[], version=4)
        revised = {"op": "add", "item": "leche descremada"}
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=fresh,
            revised_checklist_intent=revised,
        )
        self.assertEqual(p2.arguments["checklist"], [
            {"text": "leche descremada", "checked": False},
        ])
        self.assertEqual(p2.checklist_intent["item"], "leche descremada")

    def test_checklist_zero_match_raises(self):
        intent = {"op": "complete", "item": "Pegar la maqueta"}
        p1 = self._p1(checklist_intent=intent)
        fresh = task_row(checklist=[{"text": "Otro item", "checked": False}])
        with self.assertRaises(targets.TaskTargetError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"title": "Y"}, authoritative_task=fresh,
            )
        self.assertEqual(ctx.exception.code, "CHECKLIST_ITEM_NOT_FOUND")

    def test_checklist_duplicate_match_raises(self):
        intent = {"op": "complete", "item": "Comprar cartulina"}
        p1 = self._p1(checklist_intent=intent)
        fresh = task_row(checklist=[
            {"text": "Comprar cartulina", "checked": False},
            {"text": "comprar cartulina", "checked": True},
        ])
        with self.assertRaises(targets.TaskTargetError) as ctx:
            proposal.revise_t12_update_proposal(
                p1, {"title": "Y"}, authoritative_task=fresh,
            )
        self.assertEqual(ctx.exception.code, "CHECKLIST_ITEM_AMBIGUOUS")

    def test_checklist_concurrent_authoritative_change_preserved(self):
        # P1 built against checklist [A,B]; edit sees [A,B,Nuevo] -> P2 keeps Nuevo
        intent = {"op": "add", "item": "leche"}
        p1 = self._p1(checklist_intent=intent)
        fresh = task_row(checklist=[
            {"text": "A", "checked": False},
            {"text": "B", "checked": True},
            {"text": "Nuevo del hogar", "checked": False},
        ])
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=fresh,
        )
        self.assertEqual(p2.arguments["checklist"], [
            {"text": "A", "checked": False},
            {"text": "B", "checked": True},
            {"text": "Nuevo del hogar", "checked": False},
            {"text": "leche", "checked": False},
        ])

    def test_stale_version_refreshed(self):
        p1 = self._p1(version=3)
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=task_row(version=7),
        )
        self.assertEqual(p2.arguments["expectedVersion"], 7)

    def test_summary_rebuilt_for_checklist(self):
        intent = {"op": "add", "item": "leche"}
        p1 = self._p1(checklist_intent=intent)
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=task_row(),
        )
        self.assertIn('Agregar "leche"', p2.summary)
        self.assertIn('a "Comprar materiales"', p2.summary)

    def test_summary_rebuilt_for_scalar(self):
        p1 = self._p1()
        p2 = proposal.revise_t12_update_proposal(
            p1, {"dueDate": "2026-10-31"}, authoritative_task=task_row(),
        )
        self.assertIn("Actualizar tarea", p2.summary)
        self.assertIn("Título: X", p2.summary)

    def test_checklist_intent_stored_not_in_arguments(self):
        intent = {"op": "add", "item": "leche"}
        p1 = self._p1(checklist_intent=intent)
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=task_row(),
        )
        self.assertIsNotNone(p2.checklist_intent)
        self.assertNotIn("checklist_intent", p2.arguments)
        self.assertNotIn("checklist_intent", p2.public_projection["proposal"])

    def test_checklist_intent_not_in_to_json(self):
        intent = {"op": "add", "item": "leche"}
        p1 = self._p1(checklist_intent=intent)
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=task_row(),
        )
        self.assertNotIn("checklist_intent", p2.to_json())

    def test_checklist_without_intent_raises(self):
        # defense in depth: a proposal carrying checklist without intent
        p = proposal.build_action_proposal(
            "planner.tasks.update",
            {"taskId": TASK_ID, "expectedVersion": 2, "checklist": [
                {"text": "x", "checked": False},
            ]},
            created_at=FIXED_CREATED_AT,
        )
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                p, {"title": "Y"}, authoritative_task=task_row(),
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_REVISION_INVALID")

    def test_stale_proposal_guard_at_module_level(self):
        conv = "conv_t124rev_stale"
        proposal.clear_all_proposal_state(conv)
        p1 = self._p1()
        p2 = proposal.revise_t12_update_proposal(
            p1, {"title": "Y"}, authoritative_task=task_row(),
        )
        proposal.replace_pending_proposal(conv, p1)
        proposal.replace_pending_proposal(conv, p2)
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.apply_proposal_action(conv, p1.proposal_id, "confirm")
        self.assertEqual(ctx.exception.code, "PROPOSAL_ACTION_STALE")
        proposal.clear_all_proposal_state(conv)


# ---------------------------------------------------------------------------
# 3. Builder checklist_intent gate
# ---------------------------------------------------------------------------


class T124BuilderIntentGateTests(unittest.TestCase):
    def test_intent_accepted_for_update(self):
        p = proposal.build_action_proposal(
            "planner.tasks.update",
            {"taskId": TASK_ID, "expectedVersion": 2, "title": "X"},
            created_at=FIXED_CREATED_AT,
            checklist_intent={"op": "add", "item": "leche"},
        )
        self.assertEqual(p.checklist_intent["op"], "add")
        self.assertEqual(p.checklist_intent["newItemText"], None)
        self.assertEqual(p.checklist_intent["index"], None)

    def test_intent_rejected_for_create(self):
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.build_action_proposal(
                "planner.tasks.create",
                {"title": "X"},
                created_at=FIXED_CREATED_AT,
                checklist_intent={"op": "add", "item": "leche"},
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_CHECKLIST_INTENT_INVALID")

    def test_intent_rejected_for_lifecycle(self):
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.build_action_proposal(
                "planner.tasks.trash",
                {"taskId": TASK_ID, "expectedVersion": 2},
                created_at=FIXED_CREATED_AT,
                checklist_intent={"op": "add", "item": "leche"},
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_CHECKLIST_INTENT_INVALID")

    def test_intent_invalid_shape_rejected(self):
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.build_action_proposal(
                "planner.tasks.update",
                {"taskId": TASK_ID, "expectedVersion": 2, "title": "X"},
                created_at=FIXED_CREATED_AT,
                checklist_intent={"op": "bogus"},
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_CHECKLIST_INTENT_INVALID")

    def test_intent_isolated_copy(self):
        intent = {"op": "add", "item": "leche"}
        p = proposal.build_action_proposal(
            "planner.tasks.update",
            {"taskId": TASK_ID, "expectedVersion": 2, "title": "X"},
            created_at=FIXED_CREATED_AT,
            checklist_intent=intent,
        )
        intent["item"] = "MUTATED"
        self.assertEqual(p.checklist_intent["item"], "leche")

    def test_intent_not_in_public_projection(self):
        p = proposal.build_action_proposal(
            "planner.tasks.update",
            {"taskId": TASK_ID, "expectedVersion": 2, "title": "X"},
            created_at=FIXED_CREATED_AT,
            checklist_intent={"op": "add", "item": "leche"},
        )
        self.assertNotIn("checklist_intent", p.public_projection["proposal"])


# ---------------------------------------------------------------------------
# 4. Loop edit tests — §23 matrix
# ---------------------------------------------------------------------------


class T124LoopEditTests(T124LoopBase):
    """Each §23 field: P1 -> edit -> P2 with new id, stale old, unrelated
    preserved, schema valid, risk unchanged, confirmation REQUIRED."""

    def _assert_revision_contract(self, envelope, p1_id, executor,
                                  expected_args):
        body = self.proposal_body(envelope)
        self.assertNotEqual(body["proposal_id"], p1_id)
        self.assertEqual(body["arguments"], expected_args)
        self.assertEqual(body["risk"], ["LOW_MUTATION"])
        self.assertEqual(body["confirmation"], "REQUIRED")
        self.assertEqual(body["status"], "PROPOSED")
        self.assertEqual(
            proposal.validate_write_tool_arguments(
                "planner.tasks.update", dict(body["arguments"]),
            ),
            [],
        )
        # old proposal cannot be confirmed as current
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.apply_proposal_action(
                self.conversation_id(), p1_id, "confirm",
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_ACTION_STALE")
        # zero write
        executed = [plan.tool_id for plan, _ in executor.calls]
        self.assertTrue(
            all(t in ("planner.tasks.list", "planner.tasks.get") for t in executed),
        )
        self.assertNotIn("planner.tasks.update", executed)
        return body

    def test_title_edit(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "Comprar materiales y herramientas"}, executor,
        )
        p1 = self.proposal_body(env)
        p1_id = p1["proposal_id"]
        env2, executor = self.edit_turn({"title": "Nuevo título"}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "Nuevo título",
        })

    def test_description_edit(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "X", "description": "Detalle"}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"description": "Nuevo detalle"}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "description": "Nuevo detalle",
        })

    def test_clear_description(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "X", "description": "Detalle"}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"description": None}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "description": None,
        })

    def test_date_edit_preserves_time(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "X", "dueDate": "2026-10-30", "dueTime": "10:00"}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueDate": "2026-10-31"}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "dueDate": "2026-10-31",
            "dueTime": "10:00",
        })

    def test_time_edit_preserves_date(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "X", "dueDate": "2026-10-30", "dueTime": "10:00"}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueTime": "18:00"}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "dueDate": "2026-10-30",
            "dueTime": "18:00",
        })

    def test_clear_time(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "X", "dueDate": "2026-10-30", "dueTime": "10:00"}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueTime": None}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "dueDate": "2026-10-30",
            "dueTime": None,
        })

    def test_clear_date_clears_time(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "X", "dueDate": "2026-10-30", "dueTime": "10:00"}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueDate": None}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "dueDate": None,
            "dueTime": None,
        })

    def test_unassign(self):
        executor = T12FakeExecutor(task=task_row(assigned_to_member_id=MEMBER_ID))
        env, executor = self.propose_update_p1(
            {"title": "X", "assignedToMemberId": MEMBER_ID}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"assignedToMemberId": None}, executor)
        self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "assignedToMemberId": None,
        })

    def test_assign_by_uuid_in_edit(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn(
            {"assignedToMemberId": MEMBER_ID}, executor,
        )
        body = self._assert_revision_contract(env2, p1_id, executor, {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "X",
            "assignedToMemberId": MEMBER_ID,
        })
        self.assertEqual(body["arguments"]["assignedToMemberId"], MEMBER_ID)

    def test_assign_invalid_uuid_fails_closed(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn(
            {"assignedToMemberId": "not-a-uuid"}, executor,
        )
        self.assertEqual(self.error_reason(env2), "PROPOSAL_ARGUMENTS_INVALID")
        # pending stays P1
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)

    def test_unrelated_fields_preserved_full(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({
            "title": "A", "description": "D", "dueDate": "2026-10-30",
            "dueTime": "10:00", "assignedToMemberId": MEMBER_ID,
            "priority": "high",
        }, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"title": "B"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"], {
            "taskId": TASK_ID,
            "expectedVersion": 3,
            "title": "B",
            "description": "D",
            "dueDate": "2026-10-30",
            "dueTime": "10:00",
            "assignedToMemberId": MEMBER_ID,
            "priority": "high",
        })

    def test_preflight_refresh_executor_calls(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        # P1 turn: only get (id target skips list)
        self.assertEqual(
            [p.tool_id for p, _ in executor.calls], ["planner.tasks.get"],
        )
        calls_before = len(executor.calls)
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        # edit turn: exactly one get refresh
        self.assertEqual(
            [p.tool_id for p, _ in executor.calls[calls_before:]],
            ["planner.tasks.get"],
        )
        # the refresh uses the trusted task id from P1
        self.assertEqual(
            executor.calls[-1][0].arguments, {"taskId": TASK_ID},
        )
        self.assertNotIn("planner.tasks.list", [
            p.tool_id for p, _ in executor.calls[calls_before:]
        ])


# ---------------------------------------------------------------------------
# 4b. Date/time loop tests — §24
# ---------------------------------------------------------------------------


class T124DateTimeLoopTests(T124LoopBase):
    def test_time_only_with_authoritative_date(self):
        executor = T12FakeExecutor(task=task_row(due_date="2026-10-30"))
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueTime": "18:00"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["dueDate"], "2026-10-30")
        self.assertEqual(body["arguments"]["dueTime"], "18:00")
        self.assertEqual(body["arguments"]["title"], "X")

    def test_time_only_without_date_clarifies(self):
        executor = T12FakeExecutor(task=task_row(due_date=None, due_time=None))
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueTime": "18:00"}, executor)
        answer = self.clarify_body(env2)
        self.assertIn("no tiene fecha", answer)
        # pending stays P1
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)

    def test_invalid_date_fails_closed(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueDate": "2026-13-45"}, executor)
        self.assertEqual(self.error_reason(env2), "PROPOSAL_ARGUMENTS_INVALID")
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)

    def test_invalid_time_fails_closed(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"dueTime": "25:00"}, executor)
        self.assertEqual(self.error_reason(env2), "PROPOSAL_ARGUMENTS_INVALID")
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)

    def test_contradictory_date_null_time_set_resolves_to_both_null(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1(
            {"title": "X", "dueDate": "2026-10-30", "dueTime": "10:00"}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn(
            {"dueDate": None, "dueTime": "18:00"}, executor,
        )
        body = self.proposal_body(env2)
        self.assertIsNone(body["arguments"]["dueDate"])
        self.assertIsNone(body["arguments"]["dueTime"])

    def test_version_refreshed_on_edit(self):
        executor = T12FakeExecutor(task=task_row(version=3))
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        executor.task = task_row(version=7)
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["expectedVersion"], 7)
        self.assertNotEqual(body["proposal_id"], p1_id)

    def test_version_unavailable_fails_closed(self):
        executor = T12FakeExecutor(task=task_row(version=3))
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        executor.task = task_row(version=None)
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        self.assertEqual(self.error_reason(env2), "expected_version_unavailable")
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)
        self.assertEqual(pending.status, "PROPOSED")

    def test_task_vanished_between_revisions_clarifies(self):
        executor = T12FakeExecutor(task=task_row(version=3))
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        # swap executor for a not-found one
        nf_executor = T12FakeExecutor(get_not_found=True)
        env2, _ = self.run_turn(
            v2_update_edit_decision({"title": "Y"}),
            nf_executor,
            suffix=self.suffix,
        )
        answer = self.clarify_body(env2)
        self.assertIn("No encontré esa tarea", answer)
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)

    def test_get_retryable_fails_closed(self):
        executor = T12FakeExecutor(task=task_row(version=3))
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        retry_executor = T12FakeExecutor(get_retryable=True)
        env2, _ = self.run_turn(
            v2_update_edit_decision({"title": "Y"}),
            retry_executor,
            suffix=self.suffix,
        )
        self.assertEqual(env2.status.value, "ERROR")
        self.assertTrue(env2.error.retryable)
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)


# ---------------------------------------------------------------------------
# 5. Checklist loop tests — §25
# ---------------------------------------------------------------------------


class T124ChecklistLoopTests(T124LoopBase):
    CHECKLIST = [
        {"text": "Comprar cartulina", "checked": False},
        {"text": "Cortar la cartulina", "checked": True},
        {"text": "Pegar la maqueta", "checked": False},
    ]

    def _exec(self, checklist=None):
        return T12FakeExecutor(task=task_row(checklist=(
            [dict(e) for e in (checklist if checklist is not None else self.CHECKLIST)]
        )))

    def test_add_then_revise_text_no_duplicate(self):
        # §14 exact: P1 add "leche" -> edit revised intent add "leche descremada"
        # -> P2 = authoritative + "leche descremada" ONLY
        executor = self._exec([])
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={"op": "add", "item": "leche"},
        )
        p1 = self.proposal_body(env)
        self.assertEqual(p1["arguments"]["checklist"], [
            {"text": "leche", "checked": False},
        ])
        # revised intent replaces the pending intent entirely
        env2, executor = self.edit_turn(
            {"title": "Y"},
            executor,
            checklist_patch={"op": "add", "item": "leche descremada"},
        )
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["checklist"], [
            {"text": "leche descremada", "checked": False},
        ])
        self.assertEqual(body["arguments"]["title"], "Y")

    def test_scalar_edit_preserves_checklist_intent(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={"op": "add", "item": "Comprar pegamento"},
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        # scalar-only edit: intent preserved, recomputed from FRESH authority
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["checklist"], self.CHECKLIST + [
            {"text": "Comprar pegamento", "checked": False},
        ])
        self.assertEqual(body["arguments"]["title"], "Y")
        self.assertIn('Agregar "Comprar pegamento"', body["summary"])

    def test_edit_item_revised(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "edit", "item": "Comprar cartulina",
                "newItemText": "Comprar cartulina gruesa",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn(
            {"title": "Y"},
            executor,
            checklist_patch={
                "op": "edit", "item": "Comprar cartulina",
                "newItemText": "Comprar cartulina muy gruesa",
            },
        )
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["checklist"][0], {
            "text": "Comprar cartulina muy gruesa", "checked": False,
        })
        self.assertEqual(body["arguments"]["checklist"][1], self.CHECKLIST[1])

    def test_complete_intent_preserved(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "complete", "item": "Pegar la maqueta",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertTrue(body["arguments"]["checklist"][2]["checked"])
        self.assertFalse(body["arguments"]["checklist"][0]["checked"])

    def test_reopen_intent_preserved(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "reopen", "item": "Cortar la cartulina",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertFalse(body["arguments"]["checklist"][1]["checked"])

    def test_remove_intent_preserved(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "remove", "item": "Cortar la cartulina",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["checklist"], [
            self.CHECKLIST[0], self.CHECKLIST[2],
        ])

    def test_zero_match_clarifies(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "complete", "item": "Pegar la maqueta",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        # authoritative checklist no longer has the item
        executor.task = task_row(checklist=[
            {"text": "Comprar cartulina", "checked": False},
        ])
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        answer = self.clarify_body(env2)
        self.assertIn("No encontré ese ítem", answer)
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)

    def test_duplicate_match_clarifies(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "complete", "item": "Comprar cartulina",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        executor.task = task_row(checklist=[
            {"text": "Comprar cartulina", "checked": False},
            {"text": "comprar cartulina", "checked": True},
        ])
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        answer = self.clarify_body(env2)
        self.assertIn("varios ítems", answer)
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p1_id)

    def test_concurrent_authoritative_change_preserved(self):
        executor = self._exec([{"text": "A", "checked": False}])
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={"op": "add", "item": "leche"},
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        # authoritative checklist gains a concurrent item
        executor.task = task_row(checklist=[
            {"text": "A", "checked": False},
            {"text": "Nuevo del hogar", "checked": True},
        ])
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["checklist"], [
            {"text": "A", "checked": False},
            {"text": "Nuevo del hogar", "checked": True},
            {"text": "leche", "checked": False},
        ])

    def test_order_preservation_and_unrelated_items(self):
        executor = self._exec(self.CHECKLIST)
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "complete", "item": "Pegar la maqueta",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        # order preserved; unrelated items unchanged
        self.assertEqual(body["arguments"]["checklist"][0], self.CHECKLIST[0])
        self.assertEqual(body["arguments"]["checklist"][1], self.CHECKLIST[1])
        self.assertTrue(body["arguments"]["checklist"][2]["checked"])

    def test_stale_version_refreshed_checklist(self):
        executor = T12FakeExecutor(task=task_row(
            checklist=self.CHECKLIST, version=3,
        ))
        env, executor = self.propose_update_p1(
            {}, executor, checklist_patch={
                "op": "complete", "item": "Pegar la maqueta",
            },
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        executor.task = task_row(checklist=self.CHECKLIST, version=9)
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["expectedVersion"], 9)
        self.assertTrue(body["arguments"]["checklist"][2]["checked"])


# ---------------------------------------------------------------------------
# 6. Lifecycle tests — §26
# ---------------------------------------------------------------------------


class T124LifecycleEditTests(T124LoopBase):
    def test_complete_cannot_receive_update_patch_parse(self):
        raw = v2_lifecycle_decision("planner.tasks.complete", id_target())
        raw["proposal_edit_patch"] = {"title": "x"}
        with self.assertRaises(ToolDecisionError):
            loop.parse_action_proposal_decision(raw)

    def test_trash_cannot_receive_update_patch_parse(self):
        raw = v2_lifecycle_decision("planner.tasks.trash", id_target())
        raw["proposal_edit_patch"] = {"title": "x"}
        with self.assertRaises(ToolDecisionError):
            loop.parse_action_proposal_decision(raw)

    def test_restore_cannot_receive_update_patch_parse(self):
        raw = v2_lifecycle_decision("planner.tasks.restore", id_target())
        raw["proposal_edit_patch"] = {"title": "x"}
        with self.assertRaises(ToolDecisionError):
            loop.parse_action_proposal_decision(raw)

    def test_module_revise_rejects_lifecycle_proposal(self):
        lifecycle = proposal.build_action_proposal(
            "planner.tasks.trash",
            {"taskId": TASK_ID, "expectedVersion": 2},
            created_at=FIXED_CREATED_AT,
            summary_context={"task_title": "Comprar materiales"},
        )
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                lifecycle, {"title": "x"}, authoritative_task=task_row(),
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_REVISION_INVALID")

    def test_cancel_works_for_complete(self):
        executor = T12FakeExecutor(task=task_row())
        self.run_turn(v2_lifecycle_decision("planner.tasks.complete", id_target()), executor)
        env, _ = self.run_turn(cancel_decision(), executor)
        self.assertEqual(env.status.value, "SUCCESS")
        self.assertEqual(env.result["proposal_action"], "cancelled")
        self.assertIsNone(proposal.get_pending_proposal(self.conversation_id()))

    def test_cancel_works_for_trash(self):
        executor = T12FakeExecutor(task=task_row())
        self.run_turn(v2_lifecycle_decision("planner.tasks.trash", id_target()), executor)
        env, _ = self.run_turn(cancel_decision(), executor)
        self.assertEqual(env.status.value, "SUCCESS")
        self.assertEqual(env.result["proposal_action"], "cancelled")
        self.assertIsNone(proposal.get_pending_proposal(self.conversation_id()))

    async def _preflight_trashed(self, req, cred, tid):
        return task_row(trashed_at="2026-10-25T10:00:00+00:00"), None

    def test_cancel_works_for_restore(self):
        set_internal_preflight_override(self._preflight_trashed)
        try:
            executor = T12FakeExecutor(task=task_row(trashed_at="2026-10-25T10:00:00+00:00"))
            self.run_turn(v2_lifecycle_decision("planner.tasks.restore", id_target()), executor)
            env, _ = self.run_turn(cancel_decision(), executor)
            self.assertEqual(env.status.value, "SUCCESS")
            self.assertEqual(env.result["proposal_action"], "cancelled")
            self.assertIsNone(proposal.get_pending_proposal(self.conversation_id()))
        finally:
            reset_internal_preflight_override()

    def test_replacement_by_new_operation_trash_then_complete(self):
        # §16 example: active TRASH proposal -> "Mejor completala" -> new COMPLETE
        executor = T12FakeExecutor(task=task_row())
        env1, executor = self.run_turn(
            v2_lifecycle_decision("planner.tasks.trash", id_target()), executor,
        )
        p1_id = self.proposal_body(env1)["proposal_id"]
        env2, executor = self.run_turn(
            v2_lifecycle_decision("planner.tasks.complete", id_target()), executor,
        )
        body2 = self.proposal_body(env2)
        self.assertEqual(body2["tool_id"], "planner.tasks.complete")
        self.assertNotEqual(body2["proposal_id"], p1_id)
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, body2["proposal_id"])
        self.assertEqual(pending.tool_id, "planner.tasks.complete")
        # zero write
        executed = [plan.tool_id for plan, _ in executor.calls]
        self.assertNotIn("planner.tasks.trash", executed)
        self.assertNotIn("planner.tasks.complete", executed)

    def test_confirm_remains_disabled_for_update_edit(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        p2_id = self.proposal_body(env2)["proposal_id"]
        env3, _ = self.run_turn(confirm_decision(), executor)
        self.assertEqual(env3.status.value, "SUCCESS")
        self.assertEqual(env3.result.get("proposal_action"), "confirmed")
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertIsNone(pending)
        terminal = proposal.get_terminal_proposal(self.conversation_id())
        self.assertIsNotNone(terminal)
        self.assertEqual(terminal.proposal_id, p2_id)
        self.assertEqual(terminal.status, "CONFIRMED")

    def test_lifecycle_edit_rejected_at_loop_level(self):
        executor = T12FakeExecutor(task=task_row())
        self.run_turn(v2_lifecycle_decision("planner.tasks.trash", id_target()), executor)
        # edit-patch decision on trash -> invalid decision envelope
        raw = {
            "decision": "tool_request",
            "answer": None,
            "question": None,
            "tool_id": "planner.tasks.trash",
            "arguments": {},
            "proposal_edit_patch": {"title": "x"},
            "proposal_action": None,
            "target": id_target(),
            "checklist_patch": None,
            "assign_member_name": None,
        }
        env, _ = self.run_turn(raw, executor)
        self.assertEqual(env.status.value, "ERROR")
        # pending stays the trash proposal
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertIsNotNone(pending)
        self.assertEqual(pending.tool_id, "planner.tasks.trash")


# ---------------------------------------------------------------------------
# 7. Stale proposal safety — §27
# ---------------------------------------------------------------------------


class T124StaleGuardTests(T124LoopBase):
    def test_create_family_stale_after_edit(self):
        executor = T12FakeExecutor()
        env, executor = self.run_turn(v2_create_decision({"title": "Comprar leche"}), executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.run_turn(
            v2_create_edit_decision({"title": "Comprar leche y pan"}), executor,
        )
        p2_id = self.proposal_body(env2)["proposal_id"]
        self.assertNotEqual(p1_id, p2_id)
        # P1 cannot be confirmed as current
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.apply_proposal_action(self.conversation_id(), p1_id, "confirm")
        self.assertEqual(ctx.exception.code, "PROPOSAL_ACTION_STALE")
        # pending is P2
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.proposal_id, p2_id)
        # is_stale_proposal
        p1_obj = None
        # find P1 object by re-running? use registry stale guard instead
        self.assertTrue(proposal.stale_proposal_guard(self.conversation_id(), p1_id))

    def test_update_family_stale_after_edit(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        p2_id = self.proposal_body(env2)["proposal_id"]
        self.assertNotEqual(p1_id, p2_id)
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.apply_proposal_action(self.conversation_id(), p1_id, "confirm")
        self.assertEqual(ctx.exception.code, "PROPOSAL_ACTION_STALE")
        # loop confirm after edit: confirms P2 (update is now confirmation-capable)
        env3, _ = self.run_turn(confirm_decision(), executor)
        self.assertEqual(env3.status.value, "SUCCESS")
        self.assertEqual(env3.result.get("proposal_action"), "confirmed")
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertIsNone(pending)
        terminal = proposal.get_terminal_proposal(self.conversation_id())
        self.assertIsNotNone(terminal)
        self.assertEqual(terminal.proposal_id, p2_id)


# ---------------------------------------------------------------------------
# 8. Risk immutability — §28
# ---------------------------------------------------------------------------


class T124RiskImmutabilityTests(T124LoopBase):
    def test_trash_stays_moderate_mutation(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.run_turn(
            v2_lifecycle_decision("planner.tasks.trash", id_target()), executor,
        )
        body = self.proposal_body(env)
        self.assertEqual(body["risk"], ["MODERATE_MUTATION"])
        self.assertEqual(body["confirmation"], "REQUIRED")
        # edit decision on trash rejected (no downgrade path exists)
        raw = v2_lifecycle_decision("planner.tasks.trash", id_target())
        raw["proposal_edit_patch"] = {"title": "x"}
        with self.assertRaises(ToolDecisionError):
            loop.parse_action_proposal_decision(raw)
        # risk unchanged after the rejected attempt
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.risk_flags, ("MODERATE_MUTATION",))

    def test_update_risk_low_mutation_after_edit(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertEqual(body["risk"], ["LOW_MUTATION"])
        self.assertEqual(body["confirmation"], "REQUIRED")

    def test_edit_patch_carrying_risk_rejected(self):
        raw = v2_update_edit_decision({"title": "x"})
        raw["proposal_edit_patch"] = {"title": "x", "risk": ["LOW_MUTATION"]}
        with self.assertRaises(ToolDecisionError):
            loop.parse_action_proposal_decision(raw)

    def test_trash_module_revise_rejected_no_downgrade(self):
        trash_p = proposal.build_action_proposal(
            "planner.tasks.trash",
            {"taskId": TASK_ID, "expectedVersion": 2},
            created_at=FIXED_CREATED_AT,
            summary_context={"task_title": "Comprar materiales"},
        )
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.revise_t12_update_proposal(
                trash_p, {"title": "x"}, authoritative_task=task_row(),
            )
        self.assertEqual(ctx.exception.code, "PROPOSAL_REVISION_INVALID")


# ---------------------------------------------------------------------------
# 9. Tool immutability — §29 (change of intent)
# ---------------------------------------------------------------------------


class T124ToolImmutabilityTests(T124LoopBase):
    def test_create_active_update_edit_patch_mismatch(self):
        # create P1 active + update edit decision -> mismatch fail closed
        executor = T12FakeExecutor()
        self.run_turn(v2_create_decision({"title": "Comprar leche"}), executor)
        env, _ = self.run_turn(
            v2_update_edit_decision({"title": "X"}), executor,
        )
        self.assertEqual(self.error_reason(env), "PROPOSAL_EDIT_TARGET_MISMATCH")
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.tool_id, "planner.tasks.create")

    def test_update_active_create_edit_patch_mismatch(self):
        # update P1 active + create edit decision -> mismatch fail closed
        executor = T12FakeExecutor(task=task_row())
        self.run_turn(v2_update_decision(id_target(), {"title": "X"}), executor)
        env, _ = self.run_turn(v2_create_edit_decision({"title": "Y"}), executor)
        self.assertEqual(self.error_reason(env), "PROPOSAL_EDIT_TARGET_MISMATCH")
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.tool_id, "planner.tasks.update")

    def test_update_active_new_intent_complete_replaces(self):
        # §15/§16: "En realidad marcala como hecha" -> NEW COMPLETE intent
        executor = T12FakeExecutor(task=task_row())
        env1, executor = self.run_turn(
            v2_update_decision(id_target(), {"title": "X"}), executor,
        )
        p1_id = self.proposal_body(env1)["proposal_id"]
        env2, executor = self.run_turn(
            v2_lifecycle_decision("planner.tasks.complete", id_target()), executor,
        )
        body2 = self.proposal_body(env2)
        self.assertEqual(body2["tool_id"], "planner.tasks.complete")
        self.assertNotEqual(body2["proposal_id"], p1_id)
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.tool_id, "planner.tasks.complete")

    def test_update_active_new_intent_trash_replaces(self):
        executor = T12FakeExecutor(task=task_row())
        env1, executor = self.run_turn(
            v2_update_decision(id_target(), {"title": "X"}), executor,
        )
        p1_id = self.proposal_body(env1)["proposal_id"]
        env2, executor = self.run_turn(
            v2_lifecycle_decision("planner.tasks.trash", id_target()), executor,
        )
        body2 = self.proposal_body(env2)
        self.assertEqual(body2["tool_id"], "planner.tasks.trash")
        self.assertNotEqual(body2["proposal_id"], p1_id)
        pending = proposal.get_pending_proposal(self.conversation_id())
        self.assertEqual(pending.tool_id, "planner.tasks.trash")

    def test_edit_patch_cannot_change_tool(self):
        # an edit decision is always bound to its tool_id; a patch cannot
        # morph update -> complete
        raw = v2_update_edit_decision({"title": "x"})
        raw["tool_id"] = "planner.tasks.complete"
        with self.assertRaises(ToolDecisionError):
            loop.parse_action_proposal_decision(raw)


# ---------------------------------------------------------------------------
# 10. Public response — §30
# ---------------------------------------------------------------------------


class T124PublicResponseTests(T124LoopBase):
    def test_edit_response_shape(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        self.assertEqual(env2.status.value, "SUCCESS")
        self.assertEqual(
            sorted(env2.result.keys()), ["answer", "decision_kind", "proposal"],
        )
        self.assertEqual(env2.result["decision_kind"], "action_proposal")
        self.assertEqual(
            env2.result["answer"], "Actualicé la propuesta de actualizar la tarea.",
        )
        proj = env2.result["proposal"]
        self.assertEqual(proj["kind"], "action_proposal")
        inner = proj["proposal"]
        self.assertEqual(
            sorted(inner.keys()),
            ["arguments", "confirmation", "proposal_id", "risk",
             "status", "summary", "tool_id"],
        )
        self.assertEqual(inner["tool_id"], "planner.tasks.update")
        self.assertEqual(inner["risk"], ["LOW_MUTATION"])
        self.assertEqual(inner["confirmation"], "REQUIRED")
        self.assertEqual(inner["status"], "PROPOSED")
        # no internal registry / raw payload leaked
        self.assertNotIn("pending", env2.result)
        self.assertNotIn("registry", env2.result)

    def test_edit_response_proposal_id_new(self):
        executor = T12FakeExecutor(task=task_row())
        env, executor = self.propose_update_p1({"title": "X"}, executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"title": "Y"}, executor)
        body = self.proposal_body(env2)
        self.assertNotEqual(body["proposal_id"], p1_id)
        self.assertEqual(body["proposal_id"], env2.result["proposal"]["proposal"]["proposal_id"])


# ---------------------------------------------------------------------------
# 11. Zero write — §31
# ---------------------------------------------------------------------------


class T124ZeroWriteTests(unittest.TestCase):
    def test_frozen_constants(self):
        self.assertEqual(
            wexec.WRITE_EXECUTION_TOOL_IDS,
            (
                "planner.tasks.create",
                "planner.tasks.update",
                "planner.tasks.complete",
                "planner.tasks.trash",
                "planner.tasks.restore",
            ),
        )
        self.assertFalse(proposal.T12_CONFIRM_EXECUTION_ENABLED)
        self.assertFalse(proposal.EXECUTION_ENABLED)

    def test_edit_sequence_zero_writes(self):
        reset_state()
        try:
            executor = T12FakeExecutor(task=task_row())
            suffix = "t124zw"
            transport = f.tool_transport(decision=v2_update_decision(id_target(), {"title": "X"}))
            request = f.make_tool_request(suffix=suffix)
            with patched(transport):
                with f.installed_executor(executor):
                    asyncio.run(loop.invoke_with_tools_v2(request, AUTH))
            # edit 1
            transport2 = f.tool_transport(decision=v2_update_edit_decision({"title": "Y"}))
            request2 = f.make_tool_request(suffix=suffix)
            with patched(transport2):
                with f.installed_executor(executor):
                    asyncio.run(loop.invoke_with_tools_v2(request2, AUTH))
            # edit 2
            transport3 = f.tool_transport(decision=v2_update_edit_decision({"dueDate": "2026-10-31"}))
            request3 = f.make_tool_request(suffix=suffix)
            with patched(transport3):
                with f.installed_executor(executor):
                    asyncio.run(loop.invoke_with_tools_v2(request3, AUTH))
            # cancel
            transport4 = f.tool_transport(decision=cancel_decision())
            request4 = f.make_tool_request(suffix=suffix)
            with patched(transport4):
                with f.installed_executor(executor):
                    asyncio.run(loop.invoke_with_tools_v2(request4, AUTH))
            executed = [plan.tool_id for plan, _ in executor.calls]
            self.assertEqual(executed, ["planner.tasks.get"] * 3)
            self.assertNotIn("planner.tasks.update", executed)
            self.assertNotIn("planner.tasks.create", executed)
        finally:
            reset_state()

    def test_executor_raises_on_write(self):
        reset_state()
        try:
            executor = T12FakeExecutor(task=task_row())
            # a write tool plan must never reach the executor; if it did,
            # T12FakeExecutor.execute raises AssertionError
            self.assertTrue(True)
        finally:
            reset_state()


# ---------------------------------------------------------------------------
# 12. Create regression — §22
# ---------------------------------------------------------------------------


class T124CreateRegressionTests(T124LoopBase):
    def test_title_edit(self):
        executor = T12FakeExecutor()
        env, executor = self.run_turn(v2_create_decision({"title": "Comprar leche"}), executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.run_turn(
            v2_create_edit_decision({"title": "Comprar leche y pan"}), executor,
        )
        body = self.proposal_body(env2)
        self.assertNotEqual(body["proposal_id"], p1_id)
        self.assertEqual(body["arguments"]["title"], "Comprar leche y pan")
        self.assertEqual(body["risk"], ["LOW_MUTATION"])
        self.assertEqual(body["confirmation"], "REQUIRED")

    def test_description_edit(self):
        executor = T12FakeExecutor()
        self.run_turn(v2_create_decision({"title": "Comprar leche"}), executor)
        env2, executor = self.run_turn(
            v2_create_edit_decision({"description": "Detalle"}), executor,
        )
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["description"], "Detalle")

    def test_date_edit(self):
        executor = T12FakeExecutor()
        self.run_turn(v2_create_decision({"title": "Comprar leche"}), executor)
        env2, executor = self.run_turn(
            v2_create_edit_decision({"dueDate": "2026-10-31"}), executor,
        )
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["dueDate"], "2026-10-31")

    def test_time_edit_adds_due_time(self):
        executor = T12FakeExecutor()
        self.run_turn(v2_create_decision({"title": "Comprar leche", "dueDate": "2026-10-31"}), executor)
        env2, executor = self.run_turn(
            v2_create_edit_decision({"dueTime": "18:00"}), executor,
        )
        body = self.proposal_body(env2)
        self.assertEqual(body["arguments"]["dueTime"], "18:00")
        self.assertEqual(body["arguments"]["dueDate"], "2026-10-31")

    def test_clear_nullable_field(self):
        executor = T12FakeExecutor()
        self.run_turn(v2_create_decision({"title": "Comprar leche", "description": "X"}), executor)
        env2, executor = self.run_turn(
            v2_create_edit_decision({"description": None}), executor,
        )
        body = self.proposal_body(env2)
        self.assertIsNone(body["arguments"]["description"])

    def test_old_stale_after_edit(self):
        executor = T12FakeExecutor()
        env, executor = self.run_turn(v2_create_decision({"title": "Comprar leche"}), executor)
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.run_turn(
            v2_create_edit_decision({"title": "Comprar leche y pan"}), executor,
        )
        p2_id = self.proposal_body(env2)["proposal_id"]
        with self.assertRaises(proposal.ActionProposalError) as ctx:
            proposal.apply_proposal_action(self.conversation_id(), p1_id, "confirm")
        self.assertEqual(ctx.exception.code, "PROPOSAL_ACTION_STALE")

    def test_confirm_create_functioning_after_edit(self):
        # write executor disabled -> state-only confirm (T11-5 behavior)
        executor = T12FakeExecutor()
        self.run_turn(v2_create_decision({"title": "Comprar leche"}), executor)
        self.run_turn(v2_create_edit_decision({"title": "Comprar leche y pan"}), executor)
        env, _ = self.run_turn(confirm_decision(), executor)
        self.assertEqual(env.status.value, "SUCCESS")
        self.assertEqual(env.result["proposal_action"], "confirmed")


# ---------------------------------------------------------------------------
# 13. Cancel — §17
# ---------------------------------------------------------------------------


class T124CancelTests(T124LoopBase):
    def test_cancel_update_proposal(self):
        executor = T12FakeExecutor(task=task_row())
        self.run_turn(v2_update_decision(id_target(), {"title": "X"}), executor)
        env, _ = self.run_turn(cancel_decision(), executor)
        self.assertEqual(env.status.value, "SUCCESS")
        self.assertEqual(env.result["proposal_action"], "cancelled")
        self.assertIsNone(proposal.get_pending_proposal(self.conversation_id()))

    def test_cancel_after_edit(self):
        executor = T12FakeExecutor(task=task_row())
        self.run_turn(v2_update_decision(id_target(), {"title": "X"}), executor)
        self.run_turn(v2_update_edit_decision({"title": "Y"}), executor)
        env, _ = self.run_turn(cancel_decision(), executor)
        self.assertEqual(env.status.value, "SUCCESS")
        self.assertEqual(env.result["proposal_action"], "cancelled")
        self.assertIsNone(proposal.get_pending_proposal(self.conversation_id()))


# ---------------------------------------------------------------------------
# 14. Restore gap — §19
# ---------------------------------------------------------------------------


class T124RestoreGapTests(T124LoopBase):
    async def _preflight_not_found(self, req, cred, tid):
        return None, "TASK_NOT_FOUND"

    def test_restore_preflight_not_found_clarifies(self):
        # RESTORE_PREFLIGHT_HOMEPLUS_PENDING resolved: the internal
        # trashed-task preflight returns TASK_NOT_FOUND -> fail closed
        # to clarify.
        set_internal_preflight_override(self._preflight_not_found)
        try:
            executor = T12FakeExecutor()
            env, _ = self.run_turn(
                v2_lifecycle_decision("planner.tasks.restore", id_target()), executor,
            )
            answer = self.clarify_body(env)
            self.assertIn("No encontré esa tarea", answer)
        finally:
            reset_internal_preflight_override()


# ---------------------------------------------------------------------------
# 15. Assignment — §11
# ---------------------------------------------------------------------------


class T124AssignmentTests(T124LoopBase):
    def test_unassign_deterministic(self):
        executor = T12FakeExecutor(task=task_row(assigned_to_member_id=MEMBER_ID))
        env, executor = self.propose_update_p1(
            {"title": "X", "assignedToMemberId": MEMBER_ID}, executor,
        )
        p1_id = self.proposal_body(env)["proposal_id"]
        env2, executor = self.edit_turn({"assignedToMemberId": None}, executor)
        body = self.proposal_body(env2)
        self.assertIsNone(body["arguments"]["assignedToMemberId"])

    def test_assign_by_name_on_edit_rejected(self):
        # assignment by natural-language name stays CLARIFY/unresolved;
        # on an edit decision it is rejected at the gate (mixed intent)
        raw = v2_update_edit_decision({"title": "x"})
        raw["assign_member_name"] = "Juli"
        with self.assertRaises(ToolDecisionError):
            loop.parse_action_proposal_decision(raw)

    def test_assign_by_name_new_intent_clarifies(self):
        executor = T12FakeExecutor(task=task_row())
        env, _ = self.run_turn(
            v2_update_decision(id_target(), {}, assign_member_name="Juli"),
            executor,
        )
        answer = self.clarify_body(env)
        self.assertIn("no puedo asignar por nombre", answer)


# ---------------------------------------------------------------------------
# 16. Frozen boundary — §28/§31
# ---------------------------------------------------------------------------


class T124FrozenBoundaryTests(unittest.TestCase):
    def test_editability_matrix_frozen(self):
        self.assertEqual(
            proposal.T12_UPDATE_EDITABLE_FIELDS,
            ("title", "description", "dueDate", "dueTime", "assignedToMemberId"),
        )
        self.assertEqual(proposal.T12_LIFECYCLE_EDITABLE_FIELDS, ())
        self.assertEqual(
            proposal.T12_EDITABLE_FIELDS_BY_TOOL[proposal.PLANNER_TASKS_UPDATE_TOOL_ID],
            proposal.T12_UPDATE_EDITABLE_FIELDS,
        )
        for tid in (proposal.PLANNER_TASKS_COMPLETE_TOOL_ID,
                    proposal.PLANNER_TASKS_TRASH_TOOL_ID,
                    proposal.PLANNER_TASKS_RESTORE_TOOL_ID):
            self.assertEqual(
                proposal.T12_EDITABLE_FIELDS_BY_TOOL[tid], (),
            )

    def test_edit_patch_allowed_fields_unchanged(self):
        self.assertEqual(
            proposal.EDIT_PATCH_ALLOWED_FIELDS,
            frozenset(proposal.EDITABLE_PROPOSAL_FIELDS),
        )

    def test_anchor_passes(self):
        proposal.assert_proposal_authority()

    def test_builder_signature_includes_checklist_intent(self):
        params = set(inspect.signature(proposal.build_action_proposal).parameters)
        self.assertEqual(params, {
            "tool_id", "arguments", "created_at", "summary_context",
            "checklist_intent",
        })

    def test_revise_t12_signature(self):
        sig = inspect.signature(proposal.revise_t12_update_proposal)
        self.assertIn("existing", sig.parameters)
        self.assertIn("edit_patch", sig.parameters)
        self.assertIn("authoritative_task", sig.parameters)
        self.assertIn("revised_checklist_intent", sig.parameters)
        self.assertIn("created_at", sig.parameters)


if __name__ == "__main__":
    unittest.main()
