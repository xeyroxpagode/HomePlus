"""Shared helpers for the HOMI T09-D test suite (Node D).

This module is test-only. It does not modify the frozen T08 test
support module.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator

ORCHESTRATOR_ROOT = Path(
    __file__
).resolve().parent.parent

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

import app as orch  # noqa: E402
import homi_tool_loop as loop  # noqa: E402

from support import (  # noqa: E402
    FakeTransport,
    json_response,
    make_request,
    patched,
    resolution_document,
)

from homi_contracts import RequestEnvelope  # noqa: E402
from homi_tool_loop import (  # noqa: E402
    ToolExecutionOutcome,
)


SENTINEL_TOKEN = (
    "SUPER_SECRET_T09_TOKEN_SHOULD_NEVER_REACH_A"
)

THINK_TIMEOUT_S = 180.0

# Valid arguments per canonical tool, so a test can exercise every tool
# of the allow-list without inventing an invalid request.
VALID_ARGUMENTS: dict[str, dict[str, Any]] = {
    "planner.attention.get": {},
    "planner.calendar.get": {},
    "planner.events.get": {"eventId": "evt_0001"},
    "planner.events.list": {},
    "planner.search.query": {"query": "reunion"},
    "planner.summary.get": {},
    "planner.tasks.get": {"taskId": "task_0001"},
    "planner.tasks.list": {"limit": 5},
}


def make_tool_request(
    *,
    text: str = "Quelles sont mes taches pendientes ?",
    suffix: str = "t09d",
    payload: dict[str, Any] | None = None,
) -> RequestEnvelope:

    return make_request(
        capability="think",
        operation="infer_with_tools",
        text=text,
        suffix=suffix,
        payload=payload,
    )


def think_resolution() -> dict[str, Any]:

    return resolution_document(
        capability="think",
        node_id="homi-a",
        provider_id="think-primary",
        endpoint="http://homi-a:8011/invoke",
        extra_provider={"timeout_s": 180},
    )


# The default synthesized answer of the Node A double.
DEFAULT_SYNTHESIS_ANSWER = (
    "Tenes una tarea pendiente: Hacer las compras."
)


def decision_handler(
    decision: Any,
    *,
    node_id: str = "homi-a",
    provider_id: str = "think-primary",
    status_code: int = 200,
    raw_result: dict[str, Any] | None = None,
    synthesis_answer: str = DEFAULT_SYNTHESIS_ANSWER,
):
    """Build a fake Node A handler that echoes the internal correlation.

    The handler always answers with the correlation of the request Node
    D actually sent, so the fake can never mask a correlation defect.

    It is PHASE AWARE: the decision pass (``phase=decide``) answers
    with the structured decision and the synthesis pass
    (``phase=synthesize``) answers with the natural language answer.
    """

    def handler(method, url, **kwargs):
        body = kwargs.get("json") or {}

        context = body.get("context") or {}

        correlation = {
            "request_id": context.get("request_id"),
            "trace_id": context.get("trace_id"),
            "turn_id": context.get("turn_id"),
            "conversation_id": context.get("conversation_id"),
        }

        payload = body.get("payload") or {}

        if payload.get("phase") == "synthesize":
            result: dict[str, Any] = {
                "answer": synthesis_answer,
            }

        else:
            result = (
                raw_result
                if raw_result is not None
                else {"decision": decision}
            )

        envelope = {
            "contract_version": "1.0.0",
            "correlation": correlation,
            "node_id": node_id,
            "provider_id": provider_id,
            "capability": "think",
            "status": "SUCCESS",
            "timestamp": "2026-10-20T16:00:00+00:00",
            "result": result,
        }

        return json_response(
            envelope,
            status_code=status_code,
        )

    return handler


def tool_transport(
    *,
    decision: Any = None,
    handler=None,
    resolution: dict[str, Any] | None = None,
    posts: list[dict[str, Any]] | None = None,
) -> FakeTransport:

    transport = FakeTransport()

    transport.get_handler = (
        lambda method, url, **kwargs: json_response(
            resolution
            if resolution is not None
            else think_resolution()
        )
    )

    inner = (
        handler
        if handler is not None
        else decision_handler(decision)
    )

    def post_handler(method, url, **kwargs):
        if posts is not None:
            posts.append(
                {
                    "url": url,
                    "json": kwargs.get("json"),
                    "headers": kwargs.get("headers"),
                }
            )

        return inner(method, url, **kwargs)

    transport.post_handler = post_handler

    return transport


def run_invoke_with_tools(
    request: RequestEnvelope,
    transport: FakeTransport,
    authorization: str | None = None,
):
    with patched(transport):
        return asyncio.run(
            orch.invoke(request, authorization)
        )


class FakeExecutor:
    """A fake tool executor for unit tests."""

    state = "FAKE"

    def __init__(
        self,
        outcome: ToolExecutionOutcome | None = None,
    ) -> None:
        self.calls: list[tuple[Any, Any]] = []
        self.outcome = outcome

    def execute(self, plan, context):
        self.calls.append((plan, context))

        if self.outcome is not None:
            return self.outcome

        return ToolExecutionOutcome(
            ok=True,
            tool_result={"items": []},
        )


@contextlib.contextmanager
def installed_executor(
    executor: Any,
) -> Iterator[Any]:
    loop.set_tool_executor(executor)

    try:
        yield executor

    finally:
        loop.reset_tool_executor()


def serialized(value: Any) -> str:
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json()

    return json.dumps(value, default=str)
