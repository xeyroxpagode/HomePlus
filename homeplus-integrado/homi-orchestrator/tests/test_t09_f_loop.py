"""HOMI T09-F — the synthesis loop of Node D.

A successful READ tool turn is now:

    decision -> plan -> T07 -> normalize -> A synthesize -> answer

These tests cover the second Node A call, the deterministic error
paths, the call bounds, the public response, the grounding flag and
the correlation of the two internal passes.
"""

from __future__ import annotations

import json
import unittest

import t09f_support as f
from t09f_support import (
    T09F_ACTOR_ID,
    T09F_HOUSEHOLD_ID,
    T09F_SENTINEL_TOKEN,
    T09F_TASK_ID,
    FakeExecutor,
    a_handler,
    a_payloads,
    installed_executor,
    make_tool_request,
    real_tasks_list_result,
    run_invoke_with_tools,
    tool_transport,
)

from homi_contracts import ErrorCode
from homi_tool_loop import (
    INTERNAL_SYNTHESIS_REQUEST_ID_MARKER,
    ToolExecutionOutcome,
)


def tool_decision(
    tool_id: str = "planner.tasks.list",
    arguments: dict | None = None,
) -> dict:
    """The Node A decision of a tool request."""

    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": tool_id,
        "arguments": (
            dict(arguments)
            if arguments is not None
            else {"limit": 5}
        ),
    }


def run_tool_turn(
    *,
    decision: dict | None = None,
    handler=None,
    executor: FakeExecutor | None = None,
    authorization: str | None = (
        f"Bearer {T09F_SENTINEL_TOKEN}"
    ),
    suffix: str = "t09floop",
    posts: list | None = None,
):
    """Run one structured turn and return (envelope, posts, executor)."""

    if posts is None:
        posts = []

    transport = tool_transport(
        decision=decision if decision is not None else tool_decision(),
        handler=handler,
        posts=posts,
    )

    if executor is None:
        executor = FakeExecutor()

    with installed_executor(executor):
        envelope = run_invoke_with_tools(
            make_tool_request(suffix=suffix),
            transport,
            authorization=authorization,
        )

    return envelope, posts, executor


class SynthesisCallTests(unittest.TestCase):
    """A successful tool turn performs the second Node A call."""

    def test_a_successful_tool_turn_calls_node_a_twice(self) -> None:
        envelope, posts, _ = run_tool_turn()

        self.assertEqual(
            getattr(envelope, "status", None),
            "SUCCESS",
        )

        self.assertEqual(len(posts), 2)

        phases = [
            payload.get("phase")
            for payload in a_payloads(posts)
        ]

        self.assertEqual(phases, ["decide", "synthesize"])

    def test_the_synthesis_payload_carries_the_tool_result(self) -> None:
        _, posts, _ = run_tool_turn()

        synthesis = a_payloads(posts)[1]

        self.assertEqual(
            synthesis["mode"],
            "structured",
        )

        self.assertEqual(
            synthesis["phase"],
            "synthesize",
        )

        self.assertEqual(
            synthesis["text"],
            "¿Qué tareas tengo pendientes?",
        )

        self.assertEqual(
            synthesis["tool_result_version"],
            "1.0",
        )

        tool_result = synthesis["tool_result"]

        self.assertEqual(
            sorted(tool_result),
            ["data", "meta", "status", "tool_id"],
        )

        self.assertEqual(
            tool_result["tool_id"],
            "planner.tasks.list",
        )

        self.assertEqual(
            tool_result["status"],
            "SUCCESS",
        )

        self.assertEqual(
            tool_result["data"]["tasks"][0]["title"],
            "Hacer las compras",
        )

        self.assertEqual(
            tool_result["meta"]["returned_count"],
            1,
        )

    def test_the_prior_decision_carries_the_minted_identity(self) -> None:
        _, posts, _ = run_tool_turn()

        prior = a_payloads(posts)[1]["prior_decision"]

        self.assertEqual(
            prior["tool_id"],
            "planner.tasks.list",
        )

        self.assertTrue(
            prior["tool_call_id"].startswith("tcall_")
        )

        self.assertEqual(
            prior["arguments"],
            {"limit": 5},
        )

    def test_the_catalog_digest_is_the_trusted_one(self) -> None:
        _, posts, _ = run_tool_turn()

        for payload in a_payloads(posts):
            self.assertEqual(
                payload["catalog_digest"],
                (
                    "5DBB18A2B95E0A3F57A1746C6B0D7271A"
                    "1617EE8BC4489C665988D6A26722151"
                ),
            )


class ErrorPathTests(unittest.TestCase):
    """An error tool path never reaches the synthesis."""

    def test_a_tool_error_performs_no_second_node_a_call(self) -> None:
        executor = FakeExecutor(
            outcome=ToolExecutionOutcome(
                ok=False,
                error_code=ErrorCode.PROVIDER_ERROR,
                error_message="the tool layer refused",
                retryable=False,
            )
        )

        envelope, posts, _ = run_tool_turn(executor=executor)

        self.assertEqual(
            getattr(envelope, "status", None),
            "ERROR",
        )

        self.assertEqual(
            envelope.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertEqual(len(posts), 1)

    def test_a_missing_credential_performs_no_tool_and_no_synthesis(
        self,
    ) -> None:
        envelope, posts, executor = run_tool_turn(
            authorization=None,
        )

        self.assertEqual(
            envelope.error.code.value,
            "POLICY_DENIED",
        )

        self.assertEqual(len(posts), 1)

        self.assertEqual(len(executor.calls), 0)

    def test_a_direct_response_performs_no_tool_and_no_synthesis(self) -> None:
        envelope, posts, executor = run_tool_turn(
            decision={
                "decision": "direct_response",
                "answer": "HOMI es un e-commerce.",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
        )

        self.assertEqual(
            getattr(envelope, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            envelope.result.get("decision_kind"),
            "direct_response",
        )

        self.assertNotIn(
            "grounded",
            envelope.result,
        )

        self.assertEqual(len(posts), 1)

        self.assertEqual(len(executor.calls), 0)

    def test_a_clarify_performs_no_tool_and_no_synthesis(self) -> None:
        envelope, posts, executor = run_tool_turn(
            decision={
                "decision": "clarify",
                "answer": None,
                "question": "¿Que tareas quieres revisar?",
                "tool_id": None,
                "arguments": None,
            },
        )

        self.assertEqual(
            getattr(envelope, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            envelope.result.get("decision_kind"),
            "clarify",
        )

        self.assertNotIn(
            "grounded",
            envelope.result,
        )

        self.assertEqual(len(posts), 1)

        self.assertEqual(len(executor.calls), 0)

    def test_a_rejected_synthesis_is_a_deterministic_error(self) -> None:
        def handler(method, url, **kwargs):
            body = kwargs.get("json") or {}

            payload = body.get("payload") or {}

            if payload.get("phase") == "synthesize":
                envelope = {
                    "contract_version": "1.0.0",
                    "correlation": {
                        "request_id": (
                            body.get("context") or {}
                        ).get("request_id"),
                        "trace_id": (
                            body.get("context") or {}
                        ).get("trace_id"),
                        "turn_id": (
                            body.get("context") or {}
                        ).get("turn_id"),
                        "conversation_id": (
                            body.get("context") or {}
                        ).get("conversation_id"),
                    },
                    "status": "ERROR",
                    "timestamp": "2026-10-20T16:00:00+00:00",
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "unknown phase",
                        "retryable": False,
                        "node_id": "homi-a",
                        "provider_id": "think-primary",
                        "details": {},
                    },
                }

            else:
                envelope = {
                    "contract_version": "1.0.0",
                    "correlation": {
                        "request_id": (
                            body.get("context") or {}
                        ).get("request_id"),
                        "trace_id": (
                            body.get("context") or {}
                        ).get("trace_id"),
                        "turn_id": (
                            body.get("context") or {}
                        ).get("turn_id"),
                        "conversation_id": (
                            body.get("context") or {}
                        ).get("conversation_id"),
                    },
                    "node_id": "homi-a",
                    "provider_id": "think-primary",
                    "capability": "think",
                    "status": "SUCCESS",
                    "timestamp": "2026-10-20T16:00:00+00:00",
                    "result": {"decision": tool_decision()},
                }

            from support import json_response

            return json_response(envelope)

        envelope, posts, _ = run_tool_turn(handler=handler)

        self.assertEqual(
            getattr(envelope, "status", None),
            "ERROR",
        )

        self.assertEqual(
            envelope.error.code.value,
            "INVALID_REQUEST",
        )

        self.assertEqual(len(posts), 2)

    def test_an_empty_synthesis_answer_is_a_deterministic_error(self) -> None:
        envelope, posts, _ = run_tool_turn(
            handler=a_handler(
                tool_decision(),
                synthesis_answer="   ",
            ),
        )

        self.assertEqual(
            getattr(envelope, "status", None),
            "ERROR",
        )

        self.assertEqual(
            envelope.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertEqual(
            envelope.error.details.get("reason"),
            "invalid_synthesis_answer",
        )

        self.assertEqual(len(posts), 2)

    def test_a_malformed_tool_result_performs_no_synthesis(self) -> None:
        executor = FakeExecutor(
            outcome=ToolExecutionOutcome(
                ok=True,
                tool_result="not-an-object",
            )
        )

        envelope, posts, _ = run_tool_turn(executor=executor)

        self.assertEqual(
            getattr(envelope, "status", None),
            "ERROR",
        )

        self.assertEqual(
            envelope.error.code.value,
            "INTERNAL_ERROR",
        )

        self.assertEqual(len(posts), 1)


class BoundTests(unittest.TestCase):
    """The hard bounds of the turn."""

    def test_a_tool_turn_performs_exactly_one_tool_call(self) -> None:
        _, _, executor = run_tool_turn()

        self.assertEqual(len(executor.calls), 1)

    def test_a_tool_turn_performs_exactly_two_node_a_calls(self) -> None:
        _, posts, _ = run_tool_turn()

        self.assertEqual(len(posts), 2)

    def test_a_direct_response_performs_exactly_one_node_a_call(self) -> None:
        _, posts, _ = run_tool_turn(
            decision={
                "decision": "direct_response",
                "answer": "HOMI",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
        )

        self.assertEqual(len(posts), 1)

    def test_a_clarify_performs_exactly_one_node_a_call(self) -> None:
        _, posts, _ = run_tool_turn(
            decision={
                "decision": "clarify",
                "answer": None,
                "question": "¿Cual?",
                "tool_id": None,
                "arguments": None,
            },
        )

        self.assertEqual(len(posts), 1)

    def test_the_turn_never_executes_a_second_tool(self) -> None:
        _, _, executor = run_tool_turn()

        self.assertEqual(len(executor.calls), 1)

    def test_the_turn_never_retries_the_tool(self) -> None:
        _, _, executor = run_tool_turn()

        self.assertEqual(len(executor.calls), 1)


class PublicResponseTests(unittest.TestCase):
    """The public answer of a successful tool turn."""

    def test_the_public_answer_is_the_synthesized_answer(self) -> None:
        envelope, _, _ = run_tool_turn(
            handler=a_handler(
                tool_decision(),
                synthesis_answer="Tenes una tarea pendiente.",
            ),
        )

        self.assertEqual(
            envelope.result.get("answer"),
            "Tenes una tarea pendiente.",
        )

    def test_the_public_result_carries_the_safe_metadata(self) -> None:
        envelope, _, _ = run_tool_turn()

        result = envelope.result

        self.assertEqual(
            result.get("decision_kind"),
            "tool_request",
        )

        self.assertEqual(
            result.get("source_tool_id"),
            "planner.tasks.list",
        )

        self.assertTrue(
            result.get("tool_call_id")
        )

        self.assertTrue(
            result.get("grounded")
        )

        self.assertFalse(
            result.get("truncated")
        )

    def test_the_public_result_never_carries_the_transitional_flag(
        self,
    ) -> None:
        envelope, _, _ = run_tool_turn()

        self.assertNotIn(
            "synthesis_pending",
            envelope.result,
        )

    def test_the_public_result_never_carries_the_raw_tool_result(
        self,
    ) -> None:
        envelope, _, _ = run_tool_turn()

        serialized = json.dumps(
            envelope.model_dump(mode="json"),
            default=str,
        )

        self.assertNotIn("tool_result", serialized)

        self.assertNotIn(T09F_TASK_ID, serialized)

        self.assertNotIn(T09F_HOUSEHOLD_ID, serialized)

        self.assertNotIn(T09F_ACTOR_ID, serialized)

    def test_the_public_result_never_carries_the_tool_arguments(
        self,
    ) -> None:
        envelope, _, _ = run_tool_turn()

        serialized = json.dumps(
            envelope.model_dump(mode="json"),
            default=str,
        )

        self.assertNotIn("arguments", serialized)

    def test_the_grounding_flag_is_true_for_a_real_tool_turn(self) -> None:
        envelope, _, _ = run_tool_turn()

        self.assertTrue(envelope.result.get("grounded"))

    def test_the_truncation_flag_follows_the_normalized_result(
        self,
    ) -> None:
        raw = real_tasks_list_result(rows=100)

        envelope, _, _ = run_tool_turn(
            executor=FakeExecutor(result=raw),
        )

        self.assertTrue(
            envelope.result.get("truncated")
        )

    def test_a_direct_response_does_not_claim_homeplus_grounding(
        self,
    ) -> None:
        envelope, _, _ = run_tool_turn(
            decision={
                "decision": "direct_response",
                "answer": "HOMI es un e-commerce.",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
        )

        self.assertNotIn(
            "grounded",
            envelope.result,
        )


class CorrelationTests(unittest.TestCase):
    """The correlation of the two internal passes."""

    def test_the_two_internal_request_ids_are_distinct(self) -> None:
        _, posts, _ = run_tool_turn()

        decision_id = (
            posts[0]["json"].get("context") or {}
        ).get("request_id")

        synthesis_id = (
            posts[1]["json"].get("context") or {}
        ).get("request_id")

        self.assertNotEqual(decision_id, synthesis_id)

        self.assertTrue(
            decision_id.endswith("_t09d1"),
            decision_id,
        )

        self.assertTrue(
            synthesis_id.endswith("_t09f2"),
            synthesis_id,
        )

    def test_the_internal_request_ids_are_deterministic(self) -> None:
        _, first, _ = run_tool_turn(suffix="t09fdet")

        _, second, _ = run_tool_turn(suffix="t09fdet")

        self.assertEqual(
            first[0]["json"]["context"]["request_id"],
            second[0]["json"]["context"]["request_id"],
        )

        self.assertEqual(
            first[1]["json"]["context"]["request_id"],
            second[1]["json"]["context"]["request_id"],
        )

    def test_the_trace_the_turn_and_the_conversation_are_preserved(
        self,
    ) -> None:
        _, posts, _ = run_tool_turn()

        for post in posts:
            context = post["json"]["context"]

            self.assertTrue(
                context["trace_id"].startswith("trc_")
            )

            self.assertTrue(
                context["turn_id"].startswith("turn_")
            )

            self.assertTrue(
                context["conversation_id"].startswith("conv_")
            )

    def test_the_caller_correlation_is_unchanged(self) -> None:
        request = make_tool_request(suffix="t09fcorr")

        transport = tool_transport(decision=tool_decision())

        with installed_executor(FakeExecutor()):
            envelope = run_invoke_with_tools(
                request,
                transport,
                authorization=f"Bearer {T09F_SENTINEL_TOKEN}",
            )

        self.assertEqual(
            envelope.correlation.request_id,
            request.context.request_id,
        )

        self.assertEqual(
            envelope.correlation.trace_id,
            request.context.trace_id,
        )

        self.assertEqual(
            envelope.correlation.turn_id,
            request.context.turn_id,
        )

        self.assertEqual(
            envelope.correlation.conversation_id,
            request.context.conversation_id,
        )

    def test_the_internal_request_id_is_never_exposed(self) -> None:
        envelope, posts, _ = run_tool_turn()

        serialized = json.dumps(
            envelope.model_dump(mode="json"),
            default=str,
        )

        internal_id = (
            posts[1]["json"].get("context") or {}
        ).get("request_id")

        self.assertNotIn(internal_id, serialized)

    def test_the_synthesis_marker_is_the_expected_one(self) -> None:
        self.assertEqual(
            INTERNAL_SYNTHESIS_REQUEST_ID_MARKER,
            "t09f2",
        )


if __name__ == "__main__":
    unittest.main()
