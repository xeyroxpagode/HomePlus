"""HOMI T09-D — the tool executor seam stays disabled."""

from __future__ import annotations

import unittest

import t09_support
from t09_support import (
    DEFAULT_SYNTHESIS_ANSWER,
    SENTINEL_TOKEN,
    FakeExecutor,
    installed_executor,
    make_tool_request,
    run_invoke_with_tools,
    tool_transport,
)

from homi_contracts import ErrorCode
from homi_tool_client import (
    DEFAULT_TOOL_TIMEOUT_S,
    ToolClientConfigError,
    load_tool_client_config,
    require_configured,
)
from homi_tool_loop import (
    ToolExecutionOutcome,
    ToolExecutorDisabled,
    ToolExecutorDisabledError,
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


class ExecutorSeamTests(unittest.TestCase):

    def setUp(self) -> None:
        t09_support.loop.reset_tool_executor()

    def tearDown(self) -> None:
        t09_support.loop.reset_tool_executor()

    def test_the_production_executor_is_disabled(self) -> None:
        self.assertEqual(
            t09_support.loop.executor_state(),
            "DISABLED",
        )

        self.assertIsInstance(
            t09_support.loop.get_tool_executor(),
            ToolExecutorDisabled,
        )

    def test_the_disabled_executor_refuses_to_execute(self) -> None:
        executor = t09_support.loop.get_tool_executor()

        plan = t09_support.loop.ToolInvocationPlan(
            tool_call_id="tcall_a",
            tool_id="planner.tasks.list",
            arguments={},
            catalog_digest="0" * 64,
        )

        context = t09_support.loop.ToolExecutionContext(
            request_id="req_unit_aaaaaaaa",
            trace_id="trc_unit_aaaaaaaa",
            turn_id="turn_unit_aaaaaaaa",
            conversation_id="conv_unit_aaaaaaaa",
            actor_id="actor-unit-test",
            household_id="household-unit-test",
            bearer_token=SENTINEL_TOKEN,
        )

        with self.assertRaises(ToolExecutorDisabledError):
            executor.execute(plan, context)

    def test_a_tool_request_fails_closed_with_the_disabled_executor(
        self,
    ) -> None:
        transport = tool_transport(
            decision=decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            )
        )

        result = run_invoke_with_tools(
            make_tool_request(suffix="t09dexec"),
            transport,
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_NOT_CONFIGURED",
        )

        self.assertFalse(result.error.retryable)

        self.assertEqual(
            result.error.details.get("reason"),
            "tool_executor_disabled",
        )

    def test_no_real_homeplus_call_is_performed(self) -> None:
        transport = tool_transport(
            decision=decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            )
        )

        run_invoke_with_tools(
            make_tool_request(suffix="t09dnocall"),
            transport,
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            len(transport.calls),
            2,
        )

        for _, url in transport.calls:
            self.assertNotIn("homeplus", url.lower())
            self.assertNotIn(":8012", url)
            self.assertNotIn(":8013", url)

        self.assertEqual(
            transport.calls[1],
            ("POST", "http://homi-a:8011/invoke"),
        )

    def test_a_fake_executor_can_be_injected(self) -> None:
        executor = FakeExecutor()

        transport = tool_transport(
            decision=decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            )
        )

        with installed_executor(executor):
            result = run_invoke_with_tools(
                make_tool_request(suffix="t09dfake"),
                transport,
                authorization=f"Bearer {SENTINEL_TOKEN}",
            )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            len(executor.calls),
            1,
        )

        # T09-F: the public envelope of a successful tool turn is the
        # synthesized natural answer. The raw tool result is NEVER
        # public: it stays inside Node D and only the normalized,
        # bounded projection reaches Node A.
        self.assertNotIn(
            "tool_result",
            result.result,
        )

        self.assertEqual(
            result.result.get("answer"),
            DEFAULT_SYNTHESIS_ANSWER,
        )

        self.assertEqual(
            result.result.get("decision_kind"),
            "tool_request",
        )

        self.assertEqual(
            result.result.get("source_tool_id"),
            "planner.tasks.list",
        )

        self.assertTrue(
            result.result.get("grounded")
        )

        self.assertFalse(
            result.result.get("truncated")
        )

        self.assertNotIn(
            "synthesis_pending",
            result.result,
        )

    def test_a_failing_executor_is_reported(self) -> None:
        executor = FakeExecutor(
            outcome=ToolExecutionOutcome(
                ok=False,
                error_code=ErrorCode.PROVIDER_ERROR,
                error_message="tool layer refused",
                retryable=False,
            )
        )

        transport = tool_transport(
            decision=decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            )
        )

        with installed_executor(executor):
            result = run_invoke_with_tools(
                make_tool_request(suffix="t09dfail"),
                transport,
                authorization=f"Bearer {SENTINEL_TOKEN}",
            )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_the_executor_is_reset_after_the_test(self) -> None:
        executor = FakeExecutor()

        with installed_executor(executor):
            self.assertEqual(
                t09_support.loop.executor_state(),
                "FAKE",
            )

        self.assertEqual(
            t09_support.loop.executor_state(),
            "DISABLED",
        )


class ToolClientConfigTests(unittest.TestCase):

    def test_the_base_url_is_required(self) -> None:
        config = load_tool_client_config({})

        self.assertFalse(config.configured)
        self.assertIsNone(config.base_url)

        with self.assertRaises(ToolClientConfigError):
            require_configured(config)

    def test_no_default_url_is_invented(self) -> None:
        config = load_tool_client_config({})

        self.assertEqual(
            config.describe()["base_url_present"],
            False,
        )

    def test_the_default_timeout_is_twenty_seconds(self) -> None:
        config = load_tool_client_config({})

        self.assertEqual(
            config.timeout_s,
            DEFAULT_TOOL_TIMEOUT_S,
        )

        self.assertEqual(
            DEFAULT_TOOL_TIMEOUT_S,
            20.0,
        )

    def test_a_configured_base_url_is_accepted(self) -> None:
        config = load_tool_client_config(
            {
                "HOMI_TOOL_BASE_URL": "http://127.0.0.1:8012",
            }
        )

        self.assertTrue(config.configured)
        self.assertEqual(
            config.base_url,
            "http://127.0.0.1:8012",
        )

    def test_a_malformed_base_url_fails_closed(self) -> None:
        with self.assertRaises(ToolClientConfigError):
            load_tool_client_config(
                {
                    "HOMI_TOOL_BASE_URL": "not-a-url",
                }
            )

    def test_a_malformed_timeout_fails_closed(self) -> None:
        with self.assertRaises(ToolClientConfigError):
            load_tool_client_config(
                {
                    "HOMI_TOOL_TIMEOUT_S": "abc",
                }
            )

        with self.assertRaises(ToolClientConfigError):
            load_tool_client_config(
                {
                    "HOMI_TOOL_TIMEOUT_S": "-1",
                }
            )

    def test_the_frozen_provider_timeouts_are_untouched(self) -> None:
        from support import resolution_document

        document = resolution_document(
            extra_provider={"timeout_s": 180}
        )

        self.assertEqual(
            document["provider"]["timeout_s"],
            180,
        )

        self.assertEqual(
            t09_support.loop.RESOLVE_TIMEOUT_S,
            10.0,
        )


if __name__ == "__main__":
    unittest.main()
