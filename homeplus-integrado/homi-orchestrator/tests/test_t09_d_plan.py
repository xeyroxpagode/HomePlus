"""HOMI T09-D — ToolInvocationPlan, tool_call_id and the one-tool bound."""

from __future__ import annotations

import unittest

import t09_support
from t09_support import (
    SENTINEL_TOKEN,
    FakeExecutor,
    installed_executor,
    make_tool_request,
    run_invoke_with_tools,
    tool_transport,
)


def decision(
    kind: str,
    *,
    answer=None,
    question=None,
    tool_id=None,
    arguments=None,
) -> dict:
    return {
        "decision": kind,
        "answer": answer,
        "question": question,
        "tool_id": tool_id,
        "arguments": arguments,
    }


class ToolPlanTests(unittest.TestCase):

    def _run(self, payload, *, executor):
        transport = tool_transport(decision=payload)

        with installed_executor(executor):
            return run_invoke_with_tools(
                make_tool_request(suffix="t09dplan"),
                transport,
                authorization=f"Bearer {SENTINEL_TOKEN}",
            )

    def test_d_mints_the_tool_call_id(self) -> None:
        executor = FakeExecutor()

        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            ),
            executor=executor,
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        plan, _ = executor.calls[0]

        self.assertEqual(
            result.result.get("tool_call_id"),
            plan.tool_call_id,
        )

        self.assertTrue(
            plan.tool_call_id.startswith("tcall_")
        )

    def test_the_tool_call_id_is_deterministic(self) -> None:
        first = FakeExecutor()

        second = FakeExecutor()

        payload = decision(
            "tool_request",
            tool_id="planner.tasks.list",
            arguments={"limit": 5},
        )

        result_a = self._run(payload, executor=first)

        result_b = self._run(payload, executor=second)

        self.assertEqual(
            result_a.result.get("tool_call_id"),
            result_b.result.get("tool_call_id"),
        )

    def test_the_tool_call_id_depends_on_the_arguments(self) -> None:
        first = FakeExecutor()

        second = FakeExecutor()

        result_a = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            ),
            executor=first,
        )

        result_b = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 6},
            ),
            executor=second,
        )

        self.assertNotEqual(
            result_a.result.get("tool_call_id"),
            result_b.result.get("tool_call_id"),
        )

    def test_the_tool_call_id_depends_on_the_tool(self) -> None:
        first = FakeExecutor()

        second = FakeExecutor()

        result_a = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={
                    "limit": 5,
                },
            ),
            executor=first,
        )

        result_b = self._run(
            decision(
                "tool_request",
                tool_id="planner.events.list",
                arguments={},
            ),
            executor=second,
        )

        self.assertNotEqual(
            result_a.result.get("tool_call_id"),
            result_b.result.get("tool_call_id"),
        )

    def test_the_model_cannot_override_the_tool_call_id(self) -> None:
        executor = FakeExecutor()

        result = self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
                "tool_call_id": "tcall_model",
            },
            executor=executor,
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertEqual(
            len(executor.calls),
            0,
        )

    def test_the_plan_carries_no_credential(self) -> None:
        executor = FakeExecutor()

        self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            ),
            executor=executor,
        )

        plan, context = executor.calls[0]

        self.assertNotIn(
            SENTINEL_TOKEN,
            t09_support.serialized(plan),
        )

        self.assertEqual(
            context.bearer_token,
            SENTINEL_TOKEN,
        )

        self.assertEqual(
            set(plan.__dict__.keys()),
            {
                "tool_call_id",
                "tool_id",
                "arguments",
                "catalog_digest",
            },
        )

    def test_the_plan_carries_the_verified_catalog_digest(self) -> None:
        executor = FakeExecutor()

        self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            ),
            executor=executor,
        )

        plan, _ = executor.calls[0]

        self.assertEqual(
            plan.catalog_digest.upper(),
            "5DBB18A2B95E0A3F57A1746C6B0D7271"
            "A1617EE8BC4489C665988D6A26722151",
        )

    def test_exactly_one_tool_call_per_turn(self) -> None:
        executor = FakeExecutor()

        self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            ),
            executor=executor,
        )

        self.assertEqual(
            len(executor.calls),
            1,
        )

    def test_the_one_tool_bound_is_explicit(self) -> None:
        loop = t09_support.loop

        self.assertEqual(
            loop.MAX_TOOL_CALLS,
            1,
        )

        plan = loop.ToolInvocationPlan(
            tool_call_id="tcall_a",
            tool_id="planner.tasks.list",
            arguments={},
            catalog_digest="0" * 64,
        )

        loop.assert_tool_call_budget([plan])

        with self.assertRaises(loop.ToolLoopError):
            loop.assert_tool_call_budget([plan, plan])

    def test_a_turn_never_issues_two_model_calls(self) -> None:
        transport = tool_transport(
            decision=decision(
                "direct_response",
                answer="ok",
            )
        )

        run_invoke_with_tools(
            make_tool_request(suffix="t09donecall"),
            transport,
        )

        self.assertEqual(
            len(transport.calls),
            2,
        )

    def test_the_whole_catalogue_allow_list_is_accepted(self) -> None:
        from homi_tool_catalog import CANONICAL_TOOL_IDS

        self.assertEqual(
            len(CANONICAL_TOOL_IDS),
            8,
        )

        for tool_id in CANONICAL_TOOL_IDS:
            executor = FakeExecutor()

            result = self._run(
                decision(
                    "tool_request",
                    tool_id=tool_id,
                    arguments=(
                        t09_support.VALID_ARGUMENTS[tool_id]
                    ),
                ),
                executor=executor,
            )

            self.assertEqual(
                getattr(result, "status", None),
                "SUCCESS",
                tool_id,
            )

            self.assertEqual(
                len(executor.calls),
                1,
                tool_id,
            )


if __name__ == "__main__":
    unittest.main()
