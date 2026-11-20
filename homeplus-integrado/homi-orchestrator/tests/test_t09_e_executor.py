"""HOMI T09-E — the production HomePlus tool executor of Node D.

The executor is exercised over a REAL loopback HTTP server that plays
the HomePlus tool layer, and the Node A leg is a double, so the test
never depends on a live model. The real user JWT is never used here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import unittest
from io import StringIO

import t09e_support
from t09e_support import (
    T09E_SENTINEL_TOKEN,
    FakeT07Server,
    a_decision_response,
    a_synthesis_response,
    make_context,
    make_plan,
    make_tool_request,
    patched_routing_client,
    t07_error,
    t07_success,
    tool_decision,
)

import homi_tool_loop as loop

from homi_contracts import ErrorCode
from homi_tool_client import (
    HomePlusToolClient,
    ToolClientConfig,
)
from homi_tool_loop import (
    HomePlusToolExecutor,
    ToolExecutionResult,
    executor_state,
    install_production_executor,
    reset_tool_executor,
    run_tool_turn,
)


def executor_for(
    base_url: str,
    timeout_s: float = 20.0,
) -> HomePlusToolExecutor:
    return HomePlusToolExecutor(
        HomePlusToolClient(
            ToolClientConfig(
                base_url=base_url,
                timeout_s=timeout_s,
            )
        )
    )


def a_handler(decision: dict):
    """Build the Node A double of one decision.

    The double answers the control plane resolve with a resolution
    document and the decision call with the structured decision. It
    always echoes the correlation of the request Node D actually sent,
    so it can never mask a correlation defect.

    It is PHASE AWARE: the decision pass answers with the structured
    decision and the synthesis pass answers with the natural language
    answer.
    """

    resolution = {
        "capability": "think",
        "selected_node": {
            "node_id": "homi-a",
            "role": "THINK",
            "base_url": "http://homi-a:8010",
            "node_state": "AVAILABLE",
            "node_ready": True,
            "capability_status": "READY",
            "provider": "think-primary",
        },
        "provider": {
            "provider_id": "think-primary",
            "capability": "think",
            "node_id": "homi-a",
            "state": "READY",
            "implementation": "real-v1",
            "endpoint": "http://homi-a:8011/invoke",
            "node_reachable": True,
            "effective_state": "READY",
            "timeout_s": 180,
        },
        "timestamp": "2026-10-20T16:00:00+00:00",
    }

    def handler(method: str, url: str, **kwargs):
        from t09e_support import FakeResponse

        if method == "GET":
            return FakeResponse(
                status_code=200,
                content=json.dumps(resolution).encode("utf-8"),
            )

        body = kwargs.get("json") or {}

        context = body.get("context") or {}

        payload = body.get("payload") or {}

        if payload.get("phase") == "synthesize":
            document = a_synthesis_response()

        else:
            document = a_decision_response(decision)

        document["correlation"] = {
            "request_id": context.get("request_id"),
            "trace_id": context.get("trace_id"),
            "turn_id": context.get("turn_id"),
            "conversation_id": context.get("conversation_id"),
        }

        return FakeResponse(
            status_code=200,
            content=json.dumps(document).encode("utf-8"),
        )

    return handler


def run_turn(
    request,
    executor,
    server,
    *,
    a_calls: list | None = None,
    authorization: str | None = (
        f"Bearer {T09E_SENTINEL_TOKEN}"
    ),
):
    """Run one full structured turn against the fake T07 server."""

    calls = a_calls if a_calls is not None else []

    with patched_routing_client(
        a_handler(
            tool_decision(
                "planner.tasks.list",
                {"limit": 5},
            )
        ),
        calls,
    ):
        with t09e_support.installed_executor(executor):
            return asyncio.run(
                run_tool_turn(request, authorization)
            )


class ExecutorContractTests(unittest.TestCase):
    """The executor is a transport, not a brain and not an authority."""

    def setUp(self) -> None:
        reset_tool_executor()

    def tearDown(self) -> None:
        reset_tool_executor()

    def test_the_executor_is_marked_as_real(self) -> None:
        self.assertEqual(
            HomePlusToolExecutor.state,
            "REAL",
        )

    def test_a_successful_execution_returns_a_tool_execution_result(
        self,
    ) -> None:
        with FakeT07Server(
            responses=[
                (
                    200,
                    t07_success(
                        "planner.tasks.list",
                        {"items": [{"id": "task-1"}]},
                    ),
                    0.0,
                )
            ]
        ) as server:

            executor = executor_for(server.base_url)

            plan = make_plan(arguments={"limit": 5})

            result = asyncio.run(
                executor.execute(plan, make_context())
            )

            self.assertIsInstance(
                result,
                ToolExecutionResult,
            )

            self.assertEqual(
                result.status,
                "SUCCESS",
            )
            self.assertTrue(result.ok)

            self.assertEqual(
                result.tool_call_id,
                plan.tool_call_id,
            )
            self.assertEqual(
                result.tool_id,
                plan.tool_id,
            )
            self.assertEqual(
                result.result,
                {"items": [{"id": "task-1"}]},
            )

    def test_the_executor_transports_the_identity_unchanged(
        self,
    ) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            executor = executor_for(server.base_url)

            asyncio.run(
                executor.execute(
                    make_plan(),
                    make_context(
                        actor_id="actor-real",
                        household_id="household-real",
                    ),
                )
            )

            body = json.loads(
                server.last_request()["body"]
            )

            self.assertEqual(
                body["actor_id"],
                "actor-real",
            )
            self.assertEqual(
                body["household_id"],
                "household-real",
            )

    def test_the_executor_transports_the_arguments_unchanged(
        self,
    ) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            executor = executor_for(server.base_url)

            asyncio.run(
                executor.execute(
                    make_plan(
                        tool_id="planner.search.query",
                        arguments={"query": "T09-E"},
                    ),
                    make_context(),
                )
            )

            request = server.last_request()

            self.assertEqual(
                request["path"],
                "/api/homi/v1/tools/planner.search.query/invoke",
            )

            self.assertEqual(
                json.loads(request["body"])["args"],
                {"query": "T09-E"},
            )

    def test_a_missing_credential_never_reaches_homeplus(
        self,
    ) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            executor = executor_for(server.base_url)

            result = asyncio.run(
                executor.execute(
                    make_plan(),
                    make_context(bearer_token=None),
                )
            )

            self.assertFalse(result.ok)
            self.assertEqual(
                result.error_code,
                ErrorCode.POLICY_DENIED,
            )
            self.assertEqual(server.call_count, 0)

    def test_a_rejected_credential_is_a_policy_denial(self) -> None:
        with FakeT07Server(
            responses=[
                (401, t07_error("token_invalid"), 0.0)
            ]
        ) as server:

            executor = executor_for(server.base_url)

            result = asyncio.run(
                executor.execute(make_plan(), make_context())
            )

            self.assertFalse(result.ok)
            self.assertEqual(
                result.error_code,
                ErrorCode.POLICY_DENIED,
            )
            self.assertFalse(result.retryable)
            self.assertEqual(server.call_count, 1)


class TurnBoundTests(unittest.TestCase):
    """One tool per turn, two Node A calls per tool turn."""

    def setUp(self) -> None:
        reset_tool_executor()

    def tearDown(self) -> None:
        reset_tool_executor()

    def test_a_turn_issues_exactly_one_tool_call(self) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            outcome = run_turn(
                make_tool_request(suffix="t09ebound"),
                executor_for(server.base_url),
                server,
            )

            self.assertEqual(server.call_count, 1)

            self.assertIsNotNone(outcome.tool_result)

    def test_a_tool_turn_issues_exactly_two_node_a_calls(self) -> None:
        """T09-F: the decision call and the synthesis call."""

        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            calls: list = []

            run_turn(
                make_tool_request(suffix="t09eacall"),
                executor_for(server.base_url),
                server,
                a_calls=calls,
            )

            self.assertEqual(len(calls), 2)

            for call in calls:
                self.assertEqual(
                    call["url"],
                    "http://homi-a:8011/invoke",
                )

            phases = [
                (call["json"].get("payload") or {}).get("phase")
                for call in calls
            ]

            self.assertEqual(phases, ["decide", "synthesize"])

    def test_the_credential_never_reaches_node_a(self) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            calls: list = []

            run_turn(
                make_tool_request(suffix="t09eacred"),
                executor_for(server.base_url),
                server,
                a_calls=calls,
            )

            serialized = json.dumps(calls)

            self.assertNotIn(
                T09E_SENTINEL_TOKEN,
                serialized,
            )

            self.assertNotIn(
                "Authorization",
                serialized,
            )


class PublicResponseTests(unittest.TestCase):
    """The T09-F public answer is the synthesized natural answer."""

    def setUp(self) -> None:
        reset_tool_executor()

    def tearDown(self) -> None:
        reset_tool_executor()

    def test_a_successful_turn_is_a_grounded_success(self) -> None:
        with FakeT07Server(
            responses=[
                (
                    200,
                    t07_success(
                        "planner.tasks.list",
                        {"items": [{"id": "task-1"}]},
                    ),
                    0.0,
                )
            ]
        ) as server:

            outcome = run_turn(
                make_tool_request(suffix="t09epub"),
                executor_for(server.base_url),
                server,
            )

            envelope = outcome.envelope

            self.assertEqual(
                getattr(envelope, "status", None),
                "SUCCESS",
            )

            result = envelope.result

            self.assertEqual(
                result.get("answer"),
                t09e_support.DEFAULT_SYNTHESIS_ANSWER,
            )
            self.assertTrue(
                result.get("answer", "").strip()
            )

            self.assertEqual(
                result.get("decision_kind"),
                "tool_request",
            )

            self.assertEqual(
                result.get("source_tool_id"),
                "planner.tasks.list",
            )

            self.assertTrue(
                result.get("grounded")
            )

            self.assertFalse(
                result.get("truncated")
            )

            self.assertNotIn(
                "synthesis_pending",
                result,
            )

            self.assertNotIn(
                "tool_execution",
                result,
            )

    def test_the_raw_homeplus_result_is_never_public(self) -> None:
        with FakeT07Server(
            responses=[
                (
                    200,
                    t07_success(
                        "planner.tasks.list",
                        {
                            "tasks": [
                                {
                                    "id": "task-1",
                                    "title": "T09-E TASK ALFA",
                                    "household_id": (
                                        "household-secret"
                                    ),
                                    "assigned_to_member_id": (
                                        "member-secret"
                                    ),
                                }
                            ]
                        },
                    ),
                    0.0,
                )
            ]
        ) as server:

            outcome = run_turn(
                make_tool_request(suffix="t09eraw"),
                executor_for(server.base_url),
                server,
            )

            serialized = json.dumps(
                outcome.envelope.model_dump(mode="json")
            )

            self.assertNotIn("T09-E TASK ALFA", serialized)
            self.assertNotIn("household-secret", serialized)
            self.assertNotIn("member-secret", serialized)
            self.assertNotIn("task-1", serialized)

            # The internal result keeps the real payload.
            self.assertIsNotNone(outcome.tool_result)
            self.assertEqual(
                outcome.tool_result.result["tasks"][0]["id"],
                "task-1",
            )

    def test_a_rejected_credential_is_a_policy_denial(self) -> None:
        with FakeT07Server(
            responses=[
                (401, t07_error("token_invalid"), 0.0)
            ]
        ) as server:

            outcome = run_turn(
                make_tool_request(suffix="t09e401"),
                executor_for(server.base_url),
                server,
            )

            envelope = outcome.envelope

            self.assertEqual(
                getattr(envelope, "status", None),
                "ERROR",
            )
            self.assertEqual(
                envelope.error.code.value,
                "POLICY_DENIED",
            )
            self.assertFalse(envelope.error.retryable)

    def test_a_rejected_context_is_a_policy_denial(self) -> None:
        with FakeT07Server(
            responses=[
                (
                    403,
                    t07_error("HOMI_CONTEXT_MISMATCH"),
                    0.0,
                )
            ]
        ) as server:

            outcome = run_turn(
                make_tool_request(suffix="t09e403"),
                executor_for(server.base_url),
                server,
            )

            self.assertEqual(
                outcome.envelope.error.code.value,
                "POLICY_DENIED",
            )

    def test_a_missing_credential_never_calls_homeplus(self) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            outcome = run_turn(
                make_tool_request(suffix="t09enocred"),
                executor_for(server.base_url),
                server,
                authorization=None,
            )

            self.assertEqual(
                outcome.envelope.error.code.value,
                "POLICY_DENIED",
            )
            self.assertEqual(server.call_count, 0)


class TelemetryPrivacyTests(unittest.TestCase):
    """Neither the credential nor the result reaches a log."""

    def setUp(self) -> None:
        reset_tool_executor()

    def tearDown(self) -> None:
        reset_tool_executor()

    def test_the_telemetry_never_carries_the_credential(
        self,
    ) -> None:
        records: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record) -> None:
                records.append(record.getMessage())

        logger = loop.TOOL_LOGGER

        handler = Capture()

        logger.addHandler(handler)

        try:
            with FakeT07Server(
                responses=[
                    (
                        200,
                        t07_success(
                            "planner.tasks.list",
                            {"items": [{"id": "task-1"}]},
                        ),
                        0.0,
                    )
                ]
            ) as server:

                run_turn(
                    make_tool_request(suffix="t09elog"),
                    executor_for(server.base_url),
                    server,
                )

        finally:
            logger.removeHandler(handler)

        serialized = "\n".join(records)

        self.assertNotIn(T09E_SENTINEL_TOKEN, serialized)
        self.assertNotIn("task-1", serialized)
        self.assertNotIn("items", serialized)
        self.assertNotIn("Authorization", serialized)

    def test_the_credential_never_reaches_the_plan_or_the_arguments(
        self,
    ) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 0.0)]
        ) as server:

            run_turn(
                make_tool_request(suffix="t09eplan"),
                executor_for(server.base_url),
                server,
            )

            request = server.last_request()

            self.assertNotIn(
                T09E_SENTINEL_TOKEN,
                request["body"],
            )


class ProductionInstallationTests(unittest.TestCase):
    """The production installation fails closed."""

    def setUp(self) -> None:
        reset_tool_executor()

    def tearDown(self) -> None:
        reset_tool_executor()

    def test_an_absent_base_url_keeps_the_executor_disabled(
        self,
    ) -> None:
        state = install_production_executor({})

        self.assertEqual(state, "DISABLED")
        self.assertEqual(executor_state(), "DISABLED")

    def test_a_malformed_base_url_keeps_the_executor_disabled(
        self,
    ) -> None:
        state = install_production_executor(
            {"HOMI_TOOL_BASE_URL": "not-a-url"}
        )

        self.assertEqual(state, "DISABLED")
        self.assertEqual(executor_state(), "DISABLED")

    def test_a_valid_base_url_installs_the_real_executor(self) -> None:
        state = install_production_executor(
            {
                "HOMI_TOOL_BASE_URL": "http://127.0.0.1:3001",
                "HOMI_TOOL_TIMEOUT_S": "20",
            }
        )

        self.assertEqual(state, "REAL")
        self.assertEqual(executor_state(), "REAL")

        self.assertIsInstance(
            loop.get_tool_executor(),
            HomePlusToolExecutor,
        )

    def test_the_installation_never_performs_a_network_call(
        self,
    ) -> None:
        with FakeT07Server() as server:

            install_production_executor(
                {
                    "HOMI_TOOL_BASE_URL": server.base_url,
                }
            )

            self.assertEqual(server.call_count, 0)


if __name__ == "__main__":
    unittest.main()
