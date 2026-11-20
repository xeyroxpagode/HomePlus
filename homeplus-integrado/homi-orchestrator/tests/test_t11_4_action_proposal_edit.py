"""HOMI T11-4 — proposal edit + deterministic revalidation (Node D).

Scope covered by this suite:

* the strict edit patch contract (only T11-1 editable business fields);
* the deterministic merge owned by D;
* full canonical revalidation after every edit;
* the pending proposal state (one active proposal per conversation);
* the revision model: every accepted edit builds a NEW proposal
  (new D-minted proposal_id) with re-derived trusted metadata;
* the stale-revision guard: after a successful revision the previous
  proposal id stops being active;
* zero-execution: no proposal flow ever reaches the tool executor.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import unittest
from pathlib import Path
from unittest import mock

ORCHESTRATOR_ROOT = Path(
    __file__
).resolve().parent.parent

import sys  # noqa: E402

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

sys.path.insert(
    0,
    str(ORCHESTRATOR_ROOT / "tests"),
)

import homi_tool_loop as loop  # noqa: E402
import homi_tool_proposal as proposal  # noqa: E402
import t09f_support as f  # noqa: E402
from support import patched  # noqa: E402


FIXED_CREATED_AT = "2026-10-22T16:00:00+00:00"

P1_ARGUMENTS = {
    "title": "Comprar leche",
    "dueDate": "2026-10-23",
}


def build(
    arguments: dict | None = None,
) -> proposal.ActionProposalV1:
    return proposal.build_action_proposal(
        "planner.tasks.create",
        P1_ARGUMENTS
        if arguments is None
        else arguments,
        created_at=FIXED_CREATED_AT,
    )


def reset_state() -> None:
    proposal._PENDING_PROPOSALS.clear()
    proposal._PROPOSAL_REVISIONS.clear()


# ---------------------------------------------------------------------------
# E — the strict edit patch contract
# ---------------------------------------------------------------------------


class EditPatchContractTests(unittest.TestCase):
    """Node A may only ask for explicit business-field deltas."""

    def setUp(self) -> None:
        reset_state()

    def test_editable_field_scope_is_exactly_the_t11_1_business_fields(
        self,
    ) -> None:

        self.assertEqual(
            proposal.EDITABLE_PROPOSAL_FIELDS,
            (
                "title",
                "description",
                "dueDate",
                "dueTime",
                "assignedToMemberId",
            ),
        )

    def test_patch_of_every_editable_field_is_accepted(self) -> None:

        self.assertEqual(
            proposal.validate_edit_patch(
                {
                    "title": "Comprar leche y pan",
                    "description": "Y el pan",
                    "dueDate": "2026-10-24",
                    "dueTime": "18:00",
                    "assignedToMemberId": "member-abc",
                },
            ),
            [],
        )

    def test_unknown_field_is_rejected(self) -> None:

        self.assertIn(
            "unknown_patch_field:origin_entity_id",
            proposal.validate_edit_patch(
                {"origin_entity_id": "x"},
            ),
        )

    def test_identity_tamper_is_rejected(self) -> None:

        self.assertIn(
            "forbidden_key:household_id",
            proposal.validate_edit_patch(
                {"household_id": "h"},
            ),
        )

    def test_trusted_metadata_fields_are_not_editable(self) -> None:

        for name, value in (
            ("risk", ["LOW_MUTATION"]),
            ("confirmation", "NEVER"),
            ("status", "CONFIRMED"),
            ("tool_id", "planner.tasks.list"),
            ("proposal_id", "prop_hijacked0000"),
        ):

            with self.subTest(trusted=name):
                violations = proposal.validate_edit_patch(
                    {name: value},
                )

                self.assertIn(
                    f"forbidden_patch_field:{name}",
                    violations,
                )

    def test_non_object_patch_is_rejected(self) -> None:

        self.assertEqual(
            proposal.validate_edit_patch(["dueDate"]),
            ["patch_not_object"],
        )

    def test_empty_title_patch_is_rejected(self) -> None:

        self.assertIn(
            "invalid_patch:title",
            proposal.validate_edit_patch({"title": ""}),
        )

    def test_patch_validation_does_not_coerce(self) -> None:

        self.assertEqual(
            proposal.validate_edit_patch(
                {"dueDate ": "2026-10-24"},
            ),
            ["unknown_patch_field:dueDate "],
        )


# ---------------------------------------------------------------------------
# G — deterministic merge owned by D
# ---------------------------------------------------------------------------


class MergeTests(unittest.TestCase):
    """Only explicitly supplied fields change; untouched stay identical."""

    def setUp(self) -> None:
        reset_state()

    def test_merge_replaces_only_supplied_keys(self) -> None:

        current = build().arguments

        candidate = proposal.merge_proposal_arguments(
            current,
            {"dueDate": "2026-10-24"},
        )

        self.assertEqual(
            candidate,
            {
                "title": "Comprar leche",
                "dueDate": "2026-10-24",
            },
        )

    def test_merged_original_arguments_stay_unchanged(self) -> None:

        arguments = dict(P1_ARGUMENTS)

        proposal.merge_proposal_arguments(
            arguments,
            {"title": "Otro"},
        )

        self.assertEqual(
            arguments,
            P1_ARGUMENTS,
        )

    def test_invalid_patch_fails_closed(self) -> None:

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:
            proposal.merge_proposal_arguments(
                build().arguments,
                {"risk": ["LOW_MUTATION"]},
            )

        self.assertEqual(
            ctx.exception.code,
            "PROPOSAL_EDIT_PATCH_INVALID",
        )


# ---------------------------------------------------------------------------
# D / F / H — revision semantics + full canonical revalidation
# ---------------------------------------------------------------------------


class RevisionTests(unittest.TestCase):
    """existing proposal -> revised proposal; stale old representation."""

    def setUp(self) -> None:
        reset_state()

    def test_successful_revision_builds_a_new_proposal(self) -> None:

        existing = build()

        revised = proposal.revise_action_proposal(
            existing,
            {"dueDate": "2026-10-24"},
        )

        self.assertNotEqual(
            revised.proposal_id,
            existing.proposal_id,
        )

        self.assertEqual(
            revised.status,
            "PROPOSED",
        )

    def test_only_requested_fields_change(self) -> None:

        existing = build(
            {
                "title": "Comprar leche",
                "description": "Y pan",
                "dueDate": "2026-10-23",
                "dueTime": "14:30",
            },
        )

        revised = proposal.revise_action_proposal(
            existing,
            {"dueDate": "2026-10-24", "dueTime": "18:00"},
        )

        self.assertEqual(
            revised.arguments["description"],
            "Y pan",
        )

        self.assertNotEqual(
            existing.arguments,
            revised.arguments,
        )

    def test_trusted_metadata_is_re_derived_never_copied(self) -> None:

        existing = build()

        revised = proposal.revise_action_proposal(
            existing,
            {"dueDate": "2026-10-24"},
        )

        self.assertEqual(
            revised.risk_flags,
            ("LOW_MUTATION",),
        )

        self.assertEqual(
            revised.confirmation,
            "REQUIRED",
        )

    def test_summary_is_rebuilt_from_new_arguments(self) -> None:

        existing = build()

        revised = proposal.revise_action_proposal(
            existing,
            {"dueDate": "2026-10-24"},
        )

        self.assertIn(
            "24/10/2026",
            revised.summary,
        )

    def test_due_time_without_due_date_is_rejected(self) -> None:

        existing = build({"title": "X"})

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:
            proposal.revise_action_proposal(
                existing,
                {"dueTime": "18:00"},
            )

        self.assertEqual(
            ctx.exception.code,
            "PROPOSAL_ARGUMENTS_INVALID",
        )

        self.assertIn(
            "due_time_without_due_date",
            str(ctx.exception.message),
        )

    def test_invalid_date_edit_is_rejected(self) -> None:

        existing = build()

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:
            proposal.revise_action_proposal(
                existing,
                {"dueDate": "2026-13-99"},
            )

        self.assertEqual(
            ctx.exception.code,
            "PROPOSAL_ARGUMENTS_INVALID",
        )

    def test_invalid_time_edit_is_rejected(self) -> None:

        existing = build(
            {
                "title": "X",
                "dueDate": "2026-10-23",
            },
        )

        with self.assertRaises(
            proposal.ActionProposalError,
        ):
            proposal.revise_action_proposal(
                existing,
                {"dueTime": "99:00"},
            )

    def test_empty_title_edit_is_rejected(self) -> None:

        existing = build()

        with self.assertRaises(
            proposal.ActionProposalError,
        ):
            proposal.revise_action_proposal(
                existing,
                {"title": ""},
            )

    def test_invalid_edit_leaves_existing_untouched(self) -> None:

        existing = build()

        with self.assertRaises(
            proposal.ActionProposalError,
        ):
            proposal.revise_action_proposal(
                existing,
                {"dueDate": "2026-13-99"},
            )

        self.assertEqual(
            dict(existing.arguments),
            P1_ARGUMENTS,
        )


# ---------------------------------------------------------------------------
# C — pending proposal state (one active per conversation)
# ---------------------------------------------------------------------------


class PendingStateTests(unittest.TestCase):
    """In-memory, conversation-scoped, one active proposal."""

    def setUp(self) -> None:
        reset_state()

    def test_register_lookup_and_clear(self) -> None:

        prop = build()

        proposal.register_pending_proposal("conv-a", prop)

        self.assertIs(
            proposal.get_pending_proposal("conv-a"),
            prop,
        )

        self.assertTrue(
            proposal.has_pending_proposal("conv-a"),
        )

        proposal.clear_pending_proposal("conv-a")

        self.assertIsNone(
            proposal.get_pending_proposal("conv-a"),
        )

    def test_one_active_proposal_per_conversation(self) -> None:

        first = build()
        second = build()

        proposal.register_pending_proposal("conv-a", first)
        proposal.replace_pending_proposal(
            "conv-a",
            second,
        )

        self.assertIs(
            proposal.get_pending_proposal("conv-a"),
            second,
        )

        self.assertTrue(
            proposal.is_proposal_stale(first, "conv-a"),
        )

        self.assertFalse(
            proposal.is_proposal_stale(second, "conv-a"),
        )

    def test_revision_counter_is_monotonic_per_conversation(
        self,
    ) -> None:

        prop = build()

        proposal.register_pending_proposal("conv-a", prop)

        self.assertEqual(
            proposal.proposal_revision("conv-a"),
            1,
        )

        revised = proposal.revise_action_proposal(
            prop,
            {"dueDate": "2026-10-24"},
        )

        proposal.replace_pending_proposal(
            "conv-a",
            revised,
        )

        self.assertEqual(
            proposal.proposal_revision("conv-a"),
            2,
        )

    def test_registry_rejects_a_non_proposal_object(self) -> None:

        with self.assertRaises(
            proposal.ActionProposalError,
        ):
            proposal.register_pending_proposal(
                "conv-a",
                {"proposal": "forged"},
            )

    def test_stale_guard_fails_closed_after_revision(self) -> None:

        prop = build()

        proposal.register_pending_proposal("conv-a", prop)

        revised = proposal.revise_action_proposal(
            prop,
            {"dueDate": "2026-10-24"},
        )

        proposal.replace_pending_proposal(
            "conv-a",
            revised,
        )

        self.assertTrue(
            proposal.stale_proposal_guard(
                "conv-a",
                prop.proposal_id,
            ),
        )

        self.assertFalse(
            proposal.stale_proposal_guard(
                "conv-a",
                revised.proposal_id,
            ),
        )


# ---------------------------------------------------------------------------
# Loop integration (mock Node A, frozen T10 READ surface untouched)
# ---------------------------------------------------------------------------


WRITE_CREATE = {
    "decision": "tool_request",
    "answer": None,
    "question": None,
    "tool_id": "planner.tasks.create",
    "arguments": dict(P1_ARGUMENTS),
}


def write_edit(patch: dict) -> dict:

    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": "planner.tasks.create",
        "arguments": dict(P1_ARGUMENTS),
        "proposal_edit_patch": dict(patch),
    }


class LoopEditFlowTestBase(unittest.TestCase):

    suffix = "t11floop"

    def setUp(self) -> None:
        reset_state()

        self.executor = f.FakeExecutor()

    def tearDown(self) -> None:
        reset_state()

    def conversation_id(self) -> str:

        return f"conv_{self.suffix}_aaaaaaaa"

    def run_turn(
        self,
        decision: dict,
        *,
        suffix: str | None = None,
        decision_version: str = "v2",
        authorization: str | None = None,
    ):
        """Run one structured turn; returns the public envelope."""

        posts: list = []

        transport = f.tool_transport(
            decision=decision,
            posts=posts,
        )

        request = f.make_tool_request(
            suffix=self.suffix
            if suffix is None
            else suffix,
        )

        def call():
            with patched(transport):
                fn = (
                    loop.invoke_with_tools_v2
                    if decision_version == "v2"
                    else loop.invoke_with_tools
                )

                return asyncio.run(
                    fn(
                        request,
                        authorization,
                    )
                )

        with f.installed_executor(self.executor):
            envelope = call()

        self.posts = posts

        return envelope

    def pending(self):

        return proposal.get_pending_proposal(
            self.conversation_id(),
        )

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

        self.assertEqual(
            envelope.result["proposal"]["kind"],
            "action_proposal",
        )

        return envelope.result["proposal"]["proposal"]


class LoopEditFlowTests(LoopEditFlowTestBase):
    """INITIAL / EDIT-DATE / EDIT-TIME / MULTI-FIELD / UNCHANGED."""

    def test_initial_create_proposes_and_registers(self) -> None:

        envelope = self.run_turn(WRITE_CREATE)

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"],
            P1_ARGUMENTS,
        )

        self.assertEqual(
            body["status"],
            "PROPOSED",
        )

        pending = self.pending()

        self.assertEqual(
            pending.proposal_id,
            body["proposal_id"],
        )

        self.assertEqual(
            len(self.posts),
            1,
        )

    def test_edit_date_changes_only_due_date(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"dueDate": "2026-10-24"}),
        )

        body = self.proposal_body(envelope)

        self.assertNotEqual(
            body["proposal_id"],
            first["proposal_id"],
        )

        self.assertEqual(
            body["arguments"],
            {
                "title": "Comprar leche",
                "dueDate": "2026-10-24",
            },
        )

        self.assertEqual(
            body["status"],
            "PROPOSED",
        )

    def test_edit_title_changes_only_title(self) -> None:

        self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"title": "Comprar leche y pan"}),
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"],
            {
                "title": "Comprar leche y pan",
                "dueDate": "2026-10-23",
            },
        )

    def test_edit_time_adds_due_time_only(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"dueTime": "18:00"}),
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"],
            {
                "title": "Comprar leche",
                "dueDate": "2026-10-23",
                "dueTime": "18:00",
            },
        )

    def test_multi_field_edit_changes_date_and_time(self) -> None:

        self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit(
                {"dueDate": "2026-10-24", "dueTime": "18:00"},
            ),
        )

        body = self.proposal_body(envelope)

        self.assertEqual(
            body["arguments"],
            {
                "title": "Comprar leche",
                "dueDate": "2026-10-24",
                "dueTime": "18:00",
            },
        )

    def test_unchanged_fields_stay_identical(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        body = self.proposal_body(
            self.run_turn(
                write_edit({"dueDate": "2026-10-24"}),
            ),
        )

        untouched = {
            key: value
            for key, value in body["arguments"].items()
            if key != "dueDate"
        }

        expected = {
            key: value
            for key, value in first["arguments"].items()
            if key != "dueDate"
        }

        self.assertEqual(
            untouched,
            expected,
        )

    def test_trusted_metadata_and_summary_follow_the_revision(
        self,
    ) -> None:

        self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        body = self.proposal_body(
            self.run_turn(
                write_edit({"dueDate": "2026-10-24"}),
            ),
        )

        self.assertEqual(
            body["risk"],
            ["LOW_MUTATION"],
        )

        self.assertEqual(
            body["confirmation"],
            "REQUIRED",
        )

        self.assertIn(
            "24/10/2026",
            body["summary"],
        )


class LoopInvalidEditTests(LoopEditFlowTestBase):
    """Invalid edits keep the current valid proposal unchanged."""

    def test_invalid_date_edit_is_rejected_and_keeps_pending(
        self,
    ) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"dueDate": "2026-13-99"}),
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
            envelope,
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "PROPOSAL_ARGUMENTS_INVALID",
        )

        pending = self.pending()

        self.assertEqual(
            pending.proposal_id,
            first["proposal_id"],
        )

        self.assertEqual(
            dict(pending.arguments),
            P1_ARGUMENTS,
        )

    def test_invalid_time_edit_keeps_pending(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"dueTime": "99:00"}),
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "PROPOSAL_ARGUMENTS_INVALID",
        )

        self.assertEqual(
            self.pending().proposal_id,
            first["proposal_id"],
        )

    def test_empty_title_edit_keeps_pending(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"title": ""}),
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        # Fail-closed at the decision gate, before any merge: an empty
        # title can never reach the merge step.
        self.assertEqual(
            envelope.error.details.get("reason"),
            "TOOL_DECISION_INVALID",
        )

        self.assertEqual(
            self.pending().proposal_id,
            first["proposal_id"],
        )

    def test_identity_tampering_is_never_parsed(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"household_id": "h"}),
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "TOOL_DECISION_INVALID",
        )

        self.assertEqual(
            self.pending().proposal_id,
            first["proposal_id"],
        )

    def test_risk_tampering_never_reaches_the_proposal(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"risk": ["HIGH"]}),
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            self.pending().proposal_id,
            first["proposal_id"],
        )

    def test_unknown_patch_field_is_rejected(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            write_edit({"provider": "evil"}),
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "TOOL_DECISION_INVALID",
        )

        self.assertEqual(
            self.pending().proposal_id,
            first["proposal_id"],
        )

    def test_edit_without_pending_proposal_fails_closed(self) -> None:

        envelope = self.run_turn(
            write_edit({"dueDate": "2026-10-24"}),
            suffix="t11fresh",
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "edit_without_pending_proposal",
        )

        self.assertIsNone(
            proposal.get_pending_proposal(
                "conv_t11fresh_aaaaaaaa",
            ),
        )


class LoopReplacementPolicyTests(LoopEditFlowTestBase):
    """§13: an explicit new-create request replaces the pending one."""

    def test_explicit_new_create_replaces_the_pending_proposal(
        self,
    ) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.create",
                "arguments": {
                    "title": "Llamar a Juan",
                    "dueDate": "2026-10-25",
                },
            },
        )

        body = self.proposal_body(envelope)

        pending = self.pending()

        self.assertEqual(
            pending.proposal_id,
            body["proposal_id"],
        )

        self.assertNotEqual(
            body["proposal_id"],
            first["proposal_id"],
        )

        self.assertTrue(
            proposal.stale_proposal_guard(
                self.conversation_id(),
                first["proposal_id"],
            ),
        )

        self.assertFalse(
            proposal.stale_proposal_guard(
                self.conversation_id(),
                body["proposal_id"],
            ),
        )

    def test_only_one_active_proposal_after_replacement(self) -> None:

        self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        second = self.proposal_body(
            self.run_turn(
                {
                    "decision": "tool_request",
                    "answer": None,
                    "question": None,
                    "tool_id": "planner.tasks.create",
                    "arguments": {
                        "title": "Llamar a Juan",
                    },
                },
            ),
        )

        pending = self.pending()

        self.assertEqual(
            pending.proposal_id,
            second["proposal_id"],
        )

        self.assertEqual(
            dict(pending.arguments),
            {"title": "Llamar a Juan"},
        )

        self.assertEqual(
            proposal.proposal_revision(self.conversation_id()),
            2,
        )


class LoopStaleRevisionTests(LoopEditFlowTestBase):
    """After every accepted revision the old id stops being active."""

    def test_old_id_is_stale_after_revision(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        second = self.proposal_body(
            self.run_turn(
                write_edit({"dueDate": "2026-10-24"}),
            ),
        )

        third = self.proposal_body(
            self.run_turn(
                write_edit({"dueTime": "18:00"}),
            ),
        )

        pending = self.pending()

        self.assertEqual(
            pending.proposal_id,
            third["proposal_id"],
        )

        self.assertNotEqual(
            second["proposal_id"],
            first["proposal_id"],
        )

        self.assertNotEqual(
            third["proposal_id"],
            second["proposal_id"],
        )

        self.assertTrue(
            proposal.stale_proposal_guard(
                self.conversation_id(),
                first["proposal_id"],
            ),
        )

        self.assertTrue(
            proposal.stale_proposal_guard(
                self.conversation_id(),
                second["proposal_id"],
            ),
        )

        self.assertFalse(
            proposal.stale_proposal_guard(
                self.conversation_id(),
                third["proposal_id"],
            ),
        )


class LoopSafetyTests(LoopEditFlowTestBase):
    """§14 — confirm phrases and READ turns never mutate the proposal."""

    def test_confirm_phrase_does_not_execute_and_keeps_pending(
        self,
    ) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            {
                "decision": "direct_response",
                "answer": "Sí",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
        )

        self.assertEqual(
            envelope.result["answer"],
            "Sí",
        )

        self.assertEqual(
            envelope.result["decision_kind"],
            "direct_response",
        )

        self.assertEqual(
            self.executor.calls,
            [],
        )

        pending = self.pending()

        self.assertIsNotNone(pending)

        self.assertEqual(
            pending.proposal_id,
            first["proposal_id"],
        )

    def test_clarify_with_pending_does_not_mutate(self) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            {
                "decision": "clarify",
                "answer": None,
                "question": "¿Confirmar o editar?",
                "tool_id": None,
                "arguments": None,
            },
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
        )

        self.assertEqual(
            self.pending().proposal_id,
            first["proposal_id"],
        )

        self.assertEqual(
            self.executor.calls,
            [],
        )

    def test_read_question_with_pending_is_executed_and_safe(
        self,
    ) -> None:

        first = self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
            },
            authorization=f"Bearer {f.T09F_SENTINEL_TOKEN}",
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        self.assertEqual(
            envelope.result["decision_kind"],
            "tool_request",
            envelope.result,
        )

        pending = self.pending()

        self.assertEqual(
            pending.proposal_id,
            first["proposal_id"],
        )

        self.assertEqual(
            dict(pending.arguments),
            P1_ARGUMENTS,
        )

        # The READ call stays allowed; the WRITE path never is.
        self.assertEqual(
            [
                plan.tool_id
                for plan, _ in self.executor.calls
            ],
            ["planner.tasks.list"],
        )


class LoopFrozenSurfaceTests(LoopEditFlowTestBase):
    """The v1 decision surface keeps rejecting the WRITE decision."""

    def test_v1_surface_still_rejects_the_write_tool(self) -> None:

        envelope = self.run_turn(
            WRITE_CREATE,
            suffix="t11v1block",
            decision_version="v1",
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "TOOL_DECISION_INVALID",
        )

        self.assertIsNone(
            proposal.get_pending_proposal(
                "conv_t11v1block_aaaaaaaa",
            ),
        )

    def test_v2_surface_rejects_a_foreign_write_tool(self) -> None:

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "shopping.create",
                "arguments": {"title": "x"},
            },
            suffix="t11foreign",
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "TOOL_DECISION_INVALID",
        )

    def test_v2_surface_rejects_answer_on_tool_request(self) -> None:

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": "hacked",
                "question": None,
                "tool_id": "planner.tasks.create",
                "arguments": {"title": "x"},
            },
            suffix="t11answer",
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

    def test_v2_surface_rejects_extra_top_level_fields(self) -> None:

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.create",
                "arguments": {"title": "x"},
                "execute": True,
            },
            suffix="t11extra",
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

    def test_v2_surface_rejects_patch_not_object(self) -> None:

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.create",
                "arguments": {"title": "x"},
                "proposal_edit_patch": ["dueDate"],
            },
            suffix="t11badpatch",
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

    def test_public_revision_shape_has_no_identity_metadata(
        self,
    ) -> None:

        self.proposal_body(
            self.run_turn(WRITE_CREATE),
        )

        body = self.proposal_body(
            self.run_turn(
                write_edit({"dueDate": "2026-10-24"}),
            ),
        )

        text = json.dumps(body, sort_keys=True)

        forbidden = f.T09F_SENTINEL_TOKEN

        self.assertNotIn(
            forbidden,
            text,
        )

        self.assertNotIn(
            "household",
            text,
        )

        self.assertNotIn(
            "actor",
            text,
        )


# ---------------------------------------------------------------------------
# M — zero-execution proof
# ---------------------------------------------------------------------------


class ZeroExecutionTests(unittest.TestCase):
    """No proposal flow reaches the executor or the planner."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_every_proposal_flow_never_calls_the_executor(
        self,
    ) -> None:

        for method_name in (
            "test_initial_create_proposes_and_registers",
            "test_edit_date_changes_only_due_date",
            "test_multi_field_edit_changes_date_and_time",
            "test_invalid_date_edit_is_rejected_and_keeps_pending",
            "test_confirm_phrase_does_not_execute_and_keeps_pending",
        ):

            case = LoopEditFlowTests(method_name) if method_name.startswith(
                "test_initial"
            ) or method_name.startswith("test_edit_date") or method_name.startswith(
                "test_multi"
            ) else (
                LoopInvalidEditTests(method_name)
                if method_name.startswith("test_invalid")
                else LoopSafetyTests(method_name)
            )

            case.setUp()

            try:
                getattr(case, method_name)()

            finally:
                self.assertEqual(
                    case.executor.calls,
                    [],
                    method_name,
                )
                case.tearDown()

    def test_the_write_stay_firewalled_from_the_read_route(self) -> None:

        self.assertNotIn(
            "planner.tasks.create",
            loop.CANONICAL_TOOL_IDS,
        )

        self.assertIn(
            "unknown_tool",
            loop.validate_tool_request(
                "planner.tasks.create",
                {"title": "x"},
            ),
        )

    def test_execution_stays_disabled(self) -> None:

        self.assertIs(
            proposal.EXECUTION_ENABLED,
            False,
        )

        contract = proposal.write_tool_contract(
            "planner.tasks.create",
        )

        self.assertIs(
            contract.execution_enabled,
            False,
        )

    def test_the_proposal_module_carries_no_execution_seam(self) -> None:

        text = (ORCHESTRATOR_ROOT / "homi_tool_proposal.py").read_text(
            encoding="utf-8",
        )

        self.assertNotIn(
            "HomePlusToolClient",
            text,
        )

        self.assertNotIn(
            "httpx",
            text,
        )

        self.assertNotIn(
            "normalize_tool_result",
            text,
        )


if __name__ == "__main__":
    unittest.main()
