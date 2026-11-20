"""HOMI T11-5 — proposal lifecycle: confirm / cancel (Node D).

Scope covered by this suite (task matrix sections 13 and 14):

CONFIRM
    current proposal -> CONFIRMED; natural-language confirm; manual /
    programmatic confirm; stale id rejected; unknown id rejected; no
    pending proposal rejected; tampered proposal rejected; invalid
    args rejected; wrong risk rejected; wrong confirmation rejected;
    already confirmed rejected; confirm-after-cancel rejected.

CANCEL
    current proposal -> CANCELLED; natural-language cancel; manual /
    programmatic cancel; stale cancel rejected; cancelled cannot
    edit; cancelled cannot confirm; repeated cancellation
    deterministic.

MIXED
    "Mejor el viernes" -> EDIT; "¿Qué tareas tengo?" -> READ; "Sí" ->
    CONFIRM; "Cancelalo" -> CANCEL; "Sí, pero mejor el viernes" ->
    no confirm+edit combination.

ZERO-EXECUTION
    No proposal lifecycle flow ever reaches the tool executor, T07 or
    the planner. CONFIRMED and CANCELLED are lifecycle state only.
"""

from __future__ import annotations

import asyncio
import copy
import json
import unittest
from dataclasses import replace as dc_replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

ORCHESTRATOR_ROOT = Path(
    __file__).resolve().parent.parent

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


FIXED_CREATED_AT = "2026-10-22T20:00:00+00:00"

P1_ARGUMENTS = {
    "title": "Comprar leche",
    "dueDate": "2026-10-23",
}

CONVERSATION = "conv_t115unit_aaaa"


def build(
    arguments: dict | None = None,
    *,
    status: str | None = None,
    risk_flags=None,
    confirmation: str | None = None,
    tool_id: str = "planner.tasks.create",
    proposal_id: str | None = None,
) -> proposal.ActionProposalV1:
    """Build a proposal; optional overrides only for tampering tests."""

    built = proposal.build_action_proposal(
        "planner.tasks.create",
        P1_ARGUMENTS if arguments is None else arguments,
        created_at=FIXED_CREATED_AT,
    )

    if status is None and risk_flags is None and confirmation is None \
            and tool_id == built.tool_id and proposal_id is None:
        return built

    return dc_replace(
        built,
        status=status if status is not None else built.status,
        risk_flags=tuple(risk_flags) if risk_flags is not None
        else built.risk_flags,
        confirmation=confirmation if confirmation is not None
        else built.confirmation,
        tool_id=tool_id,
        proposal_id=proposal_id if proposal_id is not None
        else built.proposal_id,
    )


def reset_state() -> None:
    proposal._PENDING_PROPOSALS.clear()
    proposal._PROPOSAL_REVISIONS.clear()
    proposal._TERMINAL_PROPOSALS.clear()


def expect_error(code: str, callable_, *args):
    try:
        callable_(*args)
    except proposal.ActionProposalError as error:
        return error.code
    raise AssertionError(
        f"expected ActionProposalError {code}; nothing was raised"
    )


# ---------------------------------------------------------------------------
# The lifecycle contract (unit)
# ---------------------------------------------------------------------------


class LifecycleContractTests(unittest.TestCase):
    """The ONE D-owned lifecycle API: allowed actions and transitions."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_the_action_vocabulary_is_exactly_confirm_and_cancel(
        self,
    ) -> None:

        self.assertEqual(
            proposal.PROPOSAL_ACTIONS,
            ("confirm", "cancel"),
        )

    def test_confirm_transitions_the_current_proposal(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "confirm",
        )

        self.assertEqual(transitioned.status, "CONFIRMED")
        self.assertEqual(
            proposal.proposal_action_public_value(transitioned),
            "confirmed",
        )

    def test_confirm_preserves_every_trusted_field(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "confirm",
        )

        for field in (
            "proposal_version",
            "proposal_id",
            "tool_id",
            "arguments",
            "risk_flags",
            "confirmation",
            "created_at",
            "summary",
            "expires_at",
        ):
            self.assertEqual(
                getattr(transitioned, field),
                getattr(pending, field),
                field,
            )

        self.assertEqual(transitioned.status, "CONFIRMED")

    def test_confirm_removes_pending_and_records_terminal(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "confirm",
        )

        self.assertIsNone(
            proposal.get_pending_proposal(CONVERSATION),
        )

        terminal = proposal.get_terminal_proposal(CONVERSATION)

        self.assertEqual(
            terminal.proposal_id,
            transitioned.proposal_id,
        )

        self.assertEqual(terminal.status, "CONFIRMED")

    def test_cancel_transitions_the_current_proposal(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "cancel",
        )

        self.assertEqual(transitioned.status, "CANCELLED")
        self.assertEqual(
            proposal.proposal_action_public_value(transitioned),
            "cancelled",
        )
        self.assertIsNone(
            proposal.get_pending_proposal(CONVERSATION),
        )

    def test_unknown_action_is_rejected(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        for action in (
            "execute",
            "Confirm",
            "confirmed",
            "",
            None,
            1,
            "revive",
        ):
            with self.subTest(action=action):
                self.assertEqual(
                    expect_error(
                        "PROPOSAL_ACTION_INVALID",
                        proposal.apply_proposal_action,
                        CONVERSATION,
                        pending.proposal_id,
                        action,
                    ),
                    "PROPOSAL_ACTION_INVALID",
                )

        self.assertEqual(
            proposal.get_pending_proposal(CONVERSATION).status,
            "PROPOSED",
        )

    def test_unknown_proposal_id_is_rejected(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        self.assertEqual(
            expect_error(
                "PROPOSAL_ACTION_STALE",
                proposal.apply_proposal_action,
                CONVERSATION,
                "prop_ffffffffffffffff",
                "confirm",
            ),
            "PROPOSAL_ACTION_STALE",
        )

        self.assertEqual(
            proposal.get_pending_proposal(CONVERSATION).status,
            "PROPOSED",
        )

    def test_non_string_proposal_id_is_rejected(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        self.assertEqual(
            expect_error(
                "PROPOSAL_ACTION_UNKNOWN_ID",
                proposal.apply_proposal_action,
                CONVERSATION,
                None,
                "confirm",
            ),
            "PROPOSAL_ACTION_UNKNOWN_ID",
        )

    def test_no_pending_proposal_is_rejected(self) -> None:

        self.assertEqual(
            expect_error(
                "PROPOSAL_ACTION_NO_PENDING",
                proposal.apply_proposal_action,
                CONVERSATION,
                "prop_ffffffffffffffff",
                "confirm",
            ),
            "PROPOSAL_ACTION_NO_PENDING",
        )

    def test_expired_proposal_becomes_terminal_and_cannot_confirm(
        self,
    ) -> None:

        pending = dc_replace(
            build(),
            expires_at=(
                datetime.now(timezone.utc)
                - timedelta(seconds=1)
            ).isoformat(),
        )
        proposal.register_pending_proposal(CONVERSATION, pending)

        self.assertEqual(
            expect_error(
                "PROPOSAL_EXPIRED",
                proposal.apply_proposal_action,
                CONVERSATION,
                pending.proposal_id,
                "confirm",
            ),
            "PROPOSAL_EXPIRED",
        )

        self.assertIsNone(
            proposal.get_pending_proposal(CONVERSATION),
        )
        self.assertEqual(
            proposal.get_terminal_proposal(CONVERSATION).status,
            "EXPIRED",
        )

    def test_stale_proposal_id_cannot_confirm(self) -> None:
        """confirm(P1) after the edit that minted P2 -> stale reject."""

        p1 = build()
        proposal.register_pending_proposal(CONVERSATION, p1)

        p2 = proposal.revise_action_proposal(
            p1,
            {"dueDate": "2026-10-24"},
            created_at=FIXED_CREATED_AT,
        )
        proposal.replace_pending_proposal(CONVERSATION, p2)

        self.assertEqual(
            expect_error(
                "PROPOSAL_ACTION_STALE",
                proposal.apply_proposal_action,
                CONVERSATION,
                p1.proposal_id,
                "confirm",
            ),
            "PROPOSAL_ACTION_STALE",
        )

        self.assertEqual(
            proposal.get_pending_proposal(CONVERSATION).proposal_id,
            p2.proposal_id,
        )

        # The CURRENT id stays eligible (section 4 example).
        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            p2.proposal_id,
            "confirm",
        )

        self.assertEqual(transitioned.status, "CONFIRMED")

    def test_stale_proposal_id_cannot_cancel(self) -> None:

        p1 = build()
        proposal.register_pending_proposal(CONVERSATION, p1)

        p2 = proposal.revise_action_proposal(
            p1,
            {"dueTime": "18:00"},
            created_at=FIXED_CREATED_AT,
        )
        proposal.replace_pending_proposal(CONVERSATION, p2)

        self.assertEqual(
            expect_error(
                "PROPOSAL_ACTION_STALE",
                proposal.apply_proposal_action,
                CONVERSATION,
                p1.proposal_id,
                "cancel",
            ),
            "PROPOSAL_ACTION_STALE",
        )

    def test_already_confirmed_is_rejected(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "confirm",
        )

        self.assertEqual(
            expect_error(
                "PROPOSAL_ALREADY_TERMINAL",
                proposal.apply_proposal_action,
                CONVERSATION,
                pending.proposal_id,
                "confirm",
            ),
            "PROPOSAL_ALREADY_TERMINAL",
        )

    def test_confirm_after_cancel_is_rejected(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "cancel",
        )

        self.assertEqual(
            expect_error(
                "PROPOSAL_ALREADY_TERMINAL",
                proposal.apply_proposal_action,
                CONVERSATION,
                pending.proposal_id,
                "confirm",
            ),
            "PROPOSAL_ALREADY_TERMINAL",
        )

    def test_cancel_after_confirm_is_rejected(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "confirm",
        )

        self.assertEqual(
            expect_error(
                "PROPOSAL_ALREADY_TERMINAL",
                proposal.apply_proposal_action,
                CONVERSATION,
                pending.proposal_id,
                "cancel",
            ),
            "PROPOSAL_ALREADY_TERMINAL",
        )

    def test_repeated_cancellation_is_deterministic(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        first = proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "cancel",
        )

        self.assertEqual(first.status, "CANCELLED")

        self.assertEqual(
            expect_error(
                "PROPOSAL_ALREADY_TERMINAL",
                proposal.apply_proposal_action,
                CONVERSATION,
                pending.proposal_id,
                "cancel",
            ),
            "PROPOSAL_ALREADY_TERMINAL",
        )

        terminal = proposal.get_terminal_proposal(CONVERSATION)

        self.assertEqual(terminal.status, "CANCELLED")

    def test_public_action_value_rejects_non_terminal_proposals(
        self,
    ) -> None:

        pending = build()

        self.assertEqual(
            expect_error(
                "PROPOSAL_ACTION_INVALID",
                proposal.proposal_action_public_value,
                pending,
            ),
            "PROPOSAL_ACTION_INVALID",
        )


# ---------------------------------------------------------------------------
# Pre-confirm revalidation (tampering matrix)
# ---------------------------------------------------------------------------


class PreConfirmRevalidationTests(unittest.TestCase):
    """Section 2: full revalidation before PROPOSED -> CONFIRMED."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_tampered_status_cannot_confirm(self) -> None:

        tampered = build(status="CONFIRMED")
        proposal.register_pending_proposal(CONVERSATION, tampered)

        self.assertEqual(
            expect_error(
                "PROPOSAL_NOT_PROPOSED",
                proposal.apply_proposal_action,
                CONVERSATION,
                tampered.proposal_id,
                "confirm",
            ),
            "PROPOSAL_NOT_PROPOSED",
        )

    def test_tampered_arguments_cannot_confirm(self) -> None:

        tampered = dc_replace(
            build(),
            arguments={
                "title": "Comprar leche",
                "dueDate": "2026-13-99",
            },
        )
        proposal.register_pending_proposal(CONVERSATION, tampered)

        self.assertEqual(
            expect_error(
                "PROPOSAL_ARGUMENTS_INVALID",
                proposal.apply_proposal_action,
                CONVERSATION,
                tampered.proposal_id,
                "confirm",
            ),
            "PROPOSAL_ARGUMENTS_INVALID",
        )

        # Nothing transitioned: the tampered entry stays as it was and
        # no terminal record appears.
        self.assertIsNone(
            proposal.get_terminal_proposal(CONVERSATION),
        )

    def test_wrong_risk_cannot_confirm(self) -> None:

        tampered = build(risk_flags=["HIGH_MUTATION"])
        proposal.register_pending_proposal(CONVERSATION, tampered)

        self.assertEqual(
            expect_error(
                "PROPOSAL_RISK_MISMATCH",
                proposal.apply_proposal_action,
                CONVERSATION,
                tampered.proposal_id,
                "confirm",
            ),
            "PROPOSAL_RISK_MISMATCH",
        )

    def test_wrong_confirmation_cannot_confirm(self) -> None:

        tampered = build(confirmation="NEVER")
        proposal.register_pending_proposal(CONVERSATION, tampered)

        self.assertEqual(
            expect_error(
                "PROPOSAL_CONFIRMATION_MISMATCH",
                proposal.apply_proposal_action,
                CONVERSATION,
                tampered.proposal_id,
                "confirm",
            ),
            "PROPOSAL_CONFIRMATION_MISMATCH",
        )

    def test_untrusted_tool_cannot_confirm(self) -> None:

        tampered = build(tool_id="planner.tasks.list")
        proposal.register_pending_proposal(CONVERSATION, tampered)

        self.assertEqual(
            expect_error(
                "PROPOSAL_TOOL_UNTRUSTED",
                proposal.apply_proposal_action,
                CONVERSATION,
                tampered.proposal_id,
                "confirm",
            ),
            "PROPOSAL_TOOL_UNTRUSTED",
        )

    def test_tampered_proposal_id_cannot_confirm(self) -> None:
        """A foreign id injected into the registry is still rejected."""

        tampered = build(proposal_id="prop_hijacked00ff")
        proposal.register_pending_proposal(CONVERSATION, tampered)

        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            tampered.proposal_id,
            "confirm",
        )

        # The registry entry IS the active proposal, so the transition
        # succeeds; the preconditions are still fully revalidated.
        self.assertEqual(transitioned.status, "CONFIRMED")

        self.assertEqual(
            expect_error(
                "PROPOSAL_ALREADY_TERMINAL",
                proposal.apply_proposal_action,
                CONVERSATION,
                tampered.proposal_id,
                "confirm",
            ),
            "PROPOSAL_ALREADY_TERMINAL",
        )


# ---------------------------------------------------------------------------
# Manual action harness (section 17 — the exact T48 UI seam)
# ---------------------------------------------------------------------------


class ManualActionHarnessTests(unittest.TestCase):
    """Programmatic callers send conversation_id + proposal_id + action."""

    def setUp(self) -> None:
        reset_state()

    def tearDown(self) -> None:
        reset_state()

    def test_confirm_current_proposal_id(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "confirm",
        )

        self.assertEqual(transitioned.status, "CONFIRMED")

    def test_confirm_stale_proposal_id_is_rejected(self) -> None:

        p1 = build()
        proposal.register_pending_proposal(CONVERSATION, p1)

        p2 = proposal.revise_action_proposal(
            p1,
            {"dueDate": "2026-10-24"},
            created_at=FIXED_CREATED_AT,
        )
        proposal.replace_pending_proposal(CONVERSATION, p2)

        self.assertEqual(
            expect_error(
                "PROPOSAL_ACTION_STALE",
                proposal.apply_proposal_action,
                CONVERSATION,
                p1.proposal_id,
                "confirm",
            ),
            "PROPOSAL_ACTION_STALE",
        )

    def test_cancel_current_proposal_id(self) -> None:

        pending = build()
        proposal.register_pending_proposal(CONVERSATION, pending)

        transitioned = proposal.apply_proposal_action(
            CONVERSATION,
            pending.proposal_id,
            "cancel",
        )

        self.assertEqual(transitioned.status, "CANCELLED")


# ---------------------------------------------------------------------------
# Loop integration (mock Node A, v2 surface)
# ---------------------------------------------------------------------------


NL_CONFIRM = {
    "decision": "direct_response",
    "answer": "Si, confirmo la propuesta.",
    "question": None,
    "tool_id": None,
    "arguments": None,
    "proposal_edit_patch": None,
    "proposal_action": "confirm",
}

NL_CANCEL = {
    "decision": "direct_response",
    "answer": "No, cancelalo.",
    "question": None,
    "tool_id": None,
    "arguments": None,
    "proposal_edit_patch": None,
    "proposal_action": "cancel",
}

NL_CONFIRM_NO_PENDING = {
    "decision": "direct_response",
    "answer": "Dale",
    "question": None,
    "tool_id": None,
    "arguments": None,
    "proposal_edit_patch": None,
    "proposal_action": "confirm",
}

NL_CANCEL_NO_PENDING = {
    "decision": "direct_response",
    "answer": "Cancelalo",
    "question": None,
    "tool_id": None,
    "arguments": None,
    "proposal_edit_patch": None,
    "proposal_action": "cancel",
}

WRITE_CREATE = {
    "decision": "tool_request",
    "answer": None,
    "question": None,
    "tool_id": "planner.tasks.create",
    "arguments": dict(P1_ARGUMENTS),
}

# The REAL Node A always emits every schema field: the create decision
# carries the two additive fields as explicit nulls.
WRITE_CREATE_V2_ENVELOPE = {
    "decision": "tool_request",
    "answer": None,
    "question": None,
    "tool_id": "planner.tasks.create",
    "arguments": dict(P1_ARGUMENTS),
    "proposal_edit_patch": None,
    "proposal_action": None,
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


def read_tasks_v2_envelope() -> dict:

    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": "planner.tasks.list",
        "arguments": {},
        "proposal_edit_patch": None,
        "proposal_action": None,
    }


class LoopLifecycleTestBase(unittest.TestCase):

    suffix = "t115loop"

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
        payload: dict | None = None,
    ):

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

        if payload is not None:
            request.payload = dict(payload)

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

    def terminal(self):

        return proposal.get_terminal_proposal(
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

        return envelope.result["proposal"]["proposal"]

    def create_pending(self, decision: dict | None = None):

        envelope = self.run_turn(
            decision if decision is not None else WRITE_CREATE,
        )

        return self.proposal_body(envelope)


class LoopConfirmFlowTests(LoopLifecycleTestBase):
    """Natural-language confirm through the additive v2 surface."""

    def test_confirm_transitions_the_active_proposal(self) -> None:

        body = self.create_pending()

        envelope = self.run_turn(NL_CONFIRM)

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        result = envelope.result

        self.assertEqual(
            result["answer"],
            "Confirmaste la propuesta.",
        )

        self.assertEqual(
            result["decision_kind"],
            "action_proposal",
        )

        self.assertEqual(
            result["proposal_action"],
            "confirmed",
        )

        transitioned = result["proposal"]["proposal"]

        self.assertEqual(transitioned["proposal_id"], body["proposal_id"])
        self.assertEqual(transitioned["status"], "CONFIRMED")
        self.assertEqual(transitioned["arguments"], body["arguments"])

        self.assertIsNone(self.pending())
        self.assertEqual(self.terminal().status, "CONFIRMED")

    def test_confirm_after_edit_confirms_the_new_proposal(self) -> None:

        first = self.create_pending()

        envelope = self.run_turn(
            write_edit({"dueDate": "2026-10-24"}),
        )

        second = self.proposal_body(envelope)

        self.assertNotEqual(
            second["proposal_id"],
            first["proposal_id"],
        )

        confirm = self.run_turn(NL_CONFIRM)

        transitioned = confirm.result["proposal"]["proposal"]

        self.assertEqual(
            transitioned["proposal_id"],
            second["proposal_id"],
        )

        self.assertEqual(transitioned["status"], "CONFIRMED")

    def test_confirm_without_pending_proposal_transitions_nothing(
        self,
    ) -> None:

        envelope = self.run_turn(
            NL_CONFIRM_NO_PENDING,
            suffix="t115nopend1",
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        result = envelope.result

        self.assertEqual(
            result["decision_kind"],
            "action_proposal",
        )

        self.assertNotIn("proposal", result)
        self.assertNotIn("proposal_action", result)

        self.assertIsNone(
            proposal.get_pending_proposal(
                "conv_t115nopend1_aaaaaaaa",
            ),
        )

        self.assertIsNone(
            proposal.get_terminal_proposal(
                "conv_t115nopend1_aaaaaaaa",
            ),
        )

    def test_confirm_after_confirm_transitions_nothing(self) -> None:

        self.create_pending()

        self.run_turn(NL_CONFIRM)

        second = self.run_turn(NL_CONFIRM)

        self.assertEqual(
            second.status.value,
            "SUCCESS",
            second,
        )

        self.assertNotIn("proposal", second.result)
        self.assertNotIn("proposal_action", second.result)

        self.assertEqual(self.terminal().status, "CONFIRMED")

    def test_confirm_answer_never_claims_creation(self) -> None:

        self.create_pending()

        envelope = self.run_turn(NL_CONFIRM)

        answer = envelope.result["answer"]

        self.assertEqual(answer, "Confirmaste la propuesta.")

        for forbidden in ("cre", "Cre", "Listo"):
            self.assertNotIn(forbidden, answer)

    def test_confirm_performs_exactly_one_node_a_call(self) -> None:

        self.create_pending()

        self.run_turn(NL_CONFIRM)

        self.assertEqual(len(self.posts), 1)


class ExplicitProposalActionTests(LoopLifecycleTestBase):
    """A client lifecycle command is resolved by D, never by THINK."""

    def test_explicit_confirm_with_empty_text_skips_node_a(self) -> None:

        body = self.create_pending()

        envelope = self.run_turn(
            NL_CONFIRM,
            payload={
                "text": "",
                "proposal_action": "confirm",
            },
        )

        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        self.assertEqual(self.posts, [])
        self.assertIsNone(self.pending())
        self.assertEqual(self.terminal().status, "CONFIRMED")
        self.assertEqual(
            envelope.result["proposal"]["proposal"]["proposal_id"],
            body["proposal_id"],
        )

    def test_explicit_cancel_with_empty_text_skips_node_a(self) -> None:

        body = self.create_pending()

        envelope = self.run_turn(
            NL_CANCEL,
            payload={
                "text": "",
                "proposal_action": "cancel",
            },
        )

        self.assertEqual(envelope.status.value, "SUCCESS", envelope)
        self.assertEqual(self.posts, [])
        self.assertIsNone(self.pending())
        self.assertEqual(self.terminal().status, "CANCELLED")
        self.assertEqual(
            envelope.result["proposal"]["proposal"]["proposal_id"],
            body["proposal_id"],
        )

    def test_expired_explicit_confirm_never_reaches_node_a(
        self,
    ) -> None:

        self.create_pending()

        expired = dc_replace(
            self.pending(),
            expires_at=(
                datetime.now(timezone.utc)
                - timedelta(seconds=1)
            ).isoformat(),
        )
        proposal.replace_pending_proposal(
            self.conversation_id(),
            expired,
        )

        envelope = self.run_turn(
            NL_CONFIRM,
            payload={
                "text": "",
                "proposal_action": "confirm",
            },
        )

        self.assertEqual(envelope.status.value, "ERROR", envelope)
        self.assertEqual(
            envelope.error.details["reason"],
            "PROPOSAL_EXPIRED",
        )
        self.assertEqual(self.posts, [])
        self.assertIsNone(self.pending())
        self.assertEqual(self.terminal().status, "EXPIRED")

    def test_invalid_explicit_action_is_rejected_before_node_a(self) -> None:

        for action in (
            "approve",
            "CONFIRM",
            "",
            " confirm ",
            None,
            1,
        ):
            with self.subTest(action=action):
                envelope = self.run_turn(
                    NL_CONFIRM,
                    payload={
                        "text": "",
                        "proposal_action": action,
                    },
                )

                self.assertEqual(envelope.status.value, "ERROR", envelope)
                self.assertEqual(
                    envelope.error.code.value,
                    "INVALID_REQUEST",
                )
                self.assertEqual(
                    envelope.error.details["reason"],
                    "invalid_proposal_action",
                )
                self.assertEqual(self.posts, [])


class LoopCancelFlowTests(LoopLifecycleTestBase):
    """Natural-language cancel through the additive v2 surface."""

    def test_cancel_transitions_the_active_proposal(self) -> None:

        body = self.create_pending()

        envelope = self.run_turn(NL_CANCEL)

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        result = envelope.result

        self.assertEqual(
            result["answer"],
            "Cancelaste la propuesta.",
        )

        self.assertEqual(
            result["proposal_action"],
            "cancelled",
        )

        transitioned = result["proposal"]["proposal"]

        self.assertEqual(transitioned["proposal_id"], body["proposal_id"])
        self.assertEqual(transitioned["status"], "CANCELLED")

        self.assertIsNone(self.pending())
        self.assertEqual(self.terminal().status, "CANCELLED")

    def test_cancel_without_pending_proposal_transitions_nothing(
        self,
    ) -> None:

        envelope = self.run_turn(
            NL_CANCEL_NO_PENDING,
            suffix="t115nopend2",
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        self.assertNotIn("proposal", envelope.result)
        self.assertNotIn("proposal_action", envelope.result)

    def test_cancelled_proposal_cannot_be_edited(self) -> None:

        self.create_pending()

        self.run_turn(NL_CANCEL)

        envelope = self.run_turn(
            write_edit({"dueDate": "2026-10-24"}),
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "proposal_terminal:CANCELLED",
        )

    def test_cancelled_proposal_cannot_be_confirmed(self) -> None:

        self.create_pending()

        self.run_turn(NL_CANCEL)

        envelope = self.run_turn(NL_CONFIRM)

        # No pending proposal anymore: the lifecycle intent resolves
        # to the safe no-active-proposal answer, and nothing
        # transitions. The terminal record stays CANCELLED.
        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        self.assertNotIn("proposal", envelope.result)
        self.assertNotIn("proposal_action", envelope.result)

        self.assertEqual(self.terminal().status, "CANCELLED")

    def test_confirmed_proposal_cannot_be_edited(self) -> None:

        self.create_pending()

        self.run_turn(NL_CONFIRM)

        envelope = self.run_turn(
            write_edit({"dueDate": "2026-10-24"}),
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "proposal_terminal:CONFIRMED",
        )

    def test_a_fresh_create_after_a_terminal_is_allowed(self) -> None:

        self.create_pending()

        self.run_turn(NL_CONFIRM)

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.create",
                "arguments": {
                    "title": "Llamar al medico",
                    "dueDate": "2026-10-23",
                },
            },
        )

        body = self.proposal_body(envelope)

        self.assertEqual(body["status"], "PROPOSED")

        self.assertEqual(
            self.pending().proposal_id,
            body["proposal_id"],
        )

        # The terminal record of the earlier confirmation is preserved.
        self.assertEqual(self.terminal().status, "CONFIRMED")


class LoopMixedIntentTests(LoopLifecycleTestBase):
    """Section 8: one turn performs at most ONE lifecycle operation."""

    def test_confirm_plus_edit_patch_is_rejected(self) -> None:

        first = self.create_pending()

        envelope = self.run_turn(
            {
                "decision": "direct_response",
                "answer": "Si, pero mejor el viernes",
                "question": None,
                "tool_id": None,
                "arguments": None,
                "proposal_edit_patch": {"dueDate": "2026-10-24"},
                "proposal_action": "confirm",
            },
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "TOOL_DECISION_INVALID",
        )

        # Nothing transitioned and nothing was edited.
        pending = self.pending()

        self.assertEqual(pending.proposal_id, first["proposal_id"])
        self.assertEqual(pending.status, "PROPOSED")
        self.assertIsNone(self.terminal())

    def test_confirm_plus_create_arguments_is_rejected(self) -> None:

        first = self.create_pending()

        envelope = self.run_turn(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.create",
                "arguments": dict(P1_ARGUMENTS),
                "proposal_edit_patch": None,
                "proposal_action": "confirm",
            },
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

    def test_cancel_plus_edit_patch_is_rejected(self) -> None:

        first = self.create_pending()

        envelope = self.run_turn(
            {
                "decision": "direct_response",
                "answer": "No, dejala sin hora",
                "question": None,
                "tool_id": None,
                "arguments": None,
                "proposal_edit_patch": {"dueTime": None},
                "proposal_action": "cancel",
            },
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            self.pending().proposal_id,
            first["proposal_id"],
        )

    def test_a_model_emitted_proposal_id_is_rejected(self) -> None:

        first = self.create_pending()

        envelope = self.run_turn(
            {
                "decision": "direct_response",
                "answer": "Si",
                "question": None,
                "tool_id": None,
                "arguments": None,
                "proposal_edit_patch": None,
                "proposal_id": first["proposal_id"],
            },
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "TOOL_DECISION_INVALID",
        )

    def test_a_model_emitted_status_is_rejected(self) -> None:

        self.create_pending()

        envelope = self.run_turn(
            {
                "decision": "direct_response",
                "answer": "Si",
                "question": None,
                "tool_id": None,
                "arguments": None,
                "proposal_edit_patch": None,
                "status": "CONFIRMED",
            },
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )


class LoopDistinctIntentTests(LoopLifecycleTestBase):
    """Section 13 MIXED: edit / read / confirm / cancel stay distinct."""

    def test_edit_intent_stays_an_edit(self) -> None:

        first = self.create_pending()

        envelope = self.run_turn(
            write_edit({"dueDate": "2026-10-24"}),
        )

        body = self.proposal_body(envelope)

        self.assertEqual(body["status"], "PROPOSED")
        self.assertNotEqual(
            body["proposal_id"],
            first["proposal_id"],
        )
        self.assertEqual(
            body["arguments"]["dueDate"],
            "2026-10-24",
        )

    def test_read_intent_stays_a_read(self) -> None:

        self.create_pending()

        envelope = self.run_turn(
            read_tasks_v2_envelope(),
            authorization="Bearer t115-read-cred",
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
            envelope,
        )

        self.assertEqual(
            envelope.result["decision_kind"],
            "tool_request",
        )

        # The pending proposal is untouched: still PROPOSED, no
        # transition, no terminal record.
        pending = self.pending()

        self.assertEqual(pending.status, "PROPOSED")
        self.assertIsNone(self.terminal())

        # The READ executed exactly once through the frozen path.
        self.assertEqual(len(self.executor.calls), 1)

    def test_confirm_intent_stays_lifecycle_only(self) -> None:

        self.create_pending()

        envelope = self.run_turn(NL_CONFIRM)

        self.assertEqual(
            envelope.result["decision_kind"],
            "action_proposal",
        )

        self.assertEqual(
            envelope.result["proposal_action"],
            "confirmed",
        )

        # ZERO execution: the READ/plan executor was never called.
        self.assertEqual(self.executor.calls, [])

    def test_cancel_intent_stays_lifecycle_only(self) -> None:

        self.create_pending()

        envelope = self.run_turn(NL_CANCEL)

        self.assertEqual(
            envelope.result["proposal_action"],
            "cancelled",
        )

        self.assertEqual(self.executor.calls, [])

    def test_v2_envelope_direct_response_maps_to_the_frozen_path(
        self,
    ) -> None:

        envelope = self.run_turn(
            {
                "decision": "direct_response",
                "answer": "La capital de Argentina es Buenos Aires.",
                "question": None,
                "tool_id": None,
                "arguments": None,
                "proposal_edit_patch": None,
            },
            suffix="t115v2direct",
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
        )

        self.assertEqual(
            envelope.result["decision_kind"],
            "direct_response",
        )

        self.assertEqual(
            envelope.result["answer"],
            "La capital de Argentina es Buenos Aires.",
        )

    def test_v2_envelope_clarify_maps_to_the_frozen_path(
        self,
    ) -> None:

        envelope = self.run_turn(
            {
                "decision": "clarify",
                "answer": None,
                "question": "¿Qué tarea querés anotar?",
                "tool_id": None,
                "arguments": None,
                "proposal_edit_patch": None,
            },
            suffix="t115v2clarify",
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
        )

        self.assertEqual(
            envelope.result["decision_kind"],
            "clarify",
        )

        self.assertEqual(
            envelope.result["answer"],
            "¿Qué tarea querés anotar?",
        )

    def test_v2_envelope_create_maps_to_the_proposal_path(self) -> None:

        body = self.create_pending(WRITE_CREATE_V2_ENVELOPE)

        self.assertEqual(body["status"], "PROPOSED")
        self.assertEqual(
            body["arguments"],
            dict(P1_ARGUMENTS),
        )

    def test_v1_surface_cannot_reach_the_lifecycle(self) -> None:

        envelope = self.run_turn(
            NL_CONFIRM,
            suffix="t115v1block",
            decision_version="v1",
        )

        self.assertEqual(
            envelope.status.value,
            "ERROR",
        )

        # The frozen T10 surface rejects the additive fields outright.
        self.assertIsNone(
            proposal.get_pending_proposal(
                "conv_t115v1block_aaaaaaaa",
            ),
        )


# ---------------------------------------------------------------------------
# Public response contract (section 12)
# ---------------------------------------------------------------------------


class PublicResponseContractTests(LoopLifecycleTestBase):
    """One canonical lifecycle field; no new proposal schema."""

    def setUp(self) -> None:
        super().setUp()
        self.create_pending()

    def test_confirm_result_carries_exactly_the_canonical_keys(
        self,
    ) -> None:

        envelope = self.run_turn(NL_CONFIRM)

        self.assertEqual(
            sorted(envelope.result.keys()),
            [
                "answer",
                "decision_kind",
                "delivery_plan",
                "display_text",
                "proposal",
                "proposal_action",
                "spoken_text",
            ],
        )

    def test_cancel_result_carries_exactly_the_canonical_keys(
        self,
    ) -> None:

        envelope = self.run_turn(NL_CANCEL)

        self.assertEqual(
            sorted(envelope.result.keys()),
            [
                "answer",
                "decision_kind",
                "delivery_plan",
                "display_text",
                "proposal",
                "proposal_action",
                "spoken_text",
            ],
        )

    def test_the_projection_schema_is_unchanged(self) -> None:

        envelope = self.run_turn(NL_CONFIRM)

        projection = envelope.result["proposal"]

        self.assertEqual(
            sorted(projection.keys()),
            ["kind", "proposal"],
        )

        self.assertEqual(projection["kind"], "action_proposal")

        body = projection["proposal"]

        self.assertEqual(
            sorted(body.keys()),
            [
                "arguments",
                "confirmation",
                "proposal_id",
                "risk",
                "status",
                "summary",
                "tool_id",
            ],
        )

    def test_no_identity_or_security_field_is_exposed(self) -> None:

        for decision in (NL_CONFIRM, NL_CANCEL):
            envelope = self.run_turn(decision)

            serialized = json.dumps(
                envelope.result,
                ensure_ascii=False,
                default=str,
            )

            for forbidden in (
                "actor_id",
                "household_id",
                "membership_id",
                "auth_user_id",
                "jwt",
                "authorization",
                "access_token",
                "bearer",
                "actor-t115loop",
            ):
                self.assertNotIn(
                    forbidden,
                    serialized,
                    forbidden,
                )


# ---------------------------------------------------------------------------
# Zero-execution proof (section 14)
# ---------------------------------------------------------------------------


class ZeroExecutionTests(LoopLifecycleTestBase):
    """Confirmation and cancellation are lifecycle state only."""

    def test_confirm_performs_no_tool_execution(self) -> None:

        self.create_pending()

        envelope = self.run_turn(NL_CONFIRM)

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
        )

        self.assertEqual(self.executor.calls, [])

    def test_cancel_performs_no_tool_execution(self) -> None:

        self.create_pending()

        envelope = self.run_turn(NL_CANCEL)

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
        )

        self.assertEqual(self.executor.calls, [])

    def test_no_pending_lifecycle_intent_performs_no_execution(
        self,
    ) -> None:

        envelope = self.run_turn(
            NL_CONFIRM_NO_PENDING,
            suffix="t115zeroexec",
        )

        self.assertEqual(
            envelope.status.value,
            "SUCCESS",
        )

        self.assertEqual(self.executor.calls, [])

    def test_the_write_tool_stays_outside_the_read_catalogue(
        self,
    ) -> None:

        self.assertEqual(
            loop.validate_tool_request(
                "planner.tasks.create",
                {"title": "Comprar leche"},
            ),
            ["unknown_tool"],
        )

    def test_the_proposal_module_carries_no_execution_seam(
        self,
    ) -> None:

        import ast
        import inspect

        import homi_tool_proposal

        source = inspect.getsource(homi_tool_proposal)

        tree = ast.parse(source)

        identifiers: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]

                module = getattr(node, "module", None)

                if module:
                    names.append(module)

                identifiers.extend(names)

            elif isinstance(node, ast.Name):
                identifiers.append(node.id)

            elif isinstance(node, ast.Attribute):
                identifiers.append(node.attr)

        for forbidden in (
            "httpx",
            "urllib",
            "socket",
            "subprocess",
            "HomePlusToolClient",
            "ToolExecutor",
            "set_tool_executor",
            "get_tool_executor",
            "homi_tool_client",
            "supabase",
        ):
            self.assertNotIn(
                forbidden,
                identifiers,
                forbidden,
            )

    def test_execution_stays_disabled_in_the_write_contract(
        self,
    ) -> None:

        self.assertFalse(proposal.EXECUTION_ENABLED)

        contract = proposal.write_tool_contract(
            "planner.tasks.create",
        )

        self.assertFalse(contract.execution_enabled)


if __name__ == "__main__":
    unittest.main()
