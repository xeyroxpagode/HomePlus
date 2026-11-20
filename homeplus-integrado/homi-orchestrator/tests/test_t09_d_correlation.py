"""HOMI T09-D — internal correlation derivation and validation."""

from __future__ import annotations

import unittest

import t09_support
from t09_support import (
    SENTINEL_TOKEN,
    make_tool_request,
    run_invoke_with_tools,
    tool_transport,
)

from homi_contracts import RequestContext


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


class CorrelationTests(unittest.TestCase):

    def test_internal_request_id_is_derived(self) -> None:
        derive = t09_support.loop.derive_internal_request_id

        internal = derive("req_abc")

        self.assertTrue(internal.startswith("req_"))
        self.assertNotEqual(internal, "req_abc")
        self.assertIn("t09d1", internal)

    def test_internal_request_id_is_deterministic(self) -> None:
        derive = t09_support.loop.derive_internal_request_id

        first = derive("req_unit_aaaaaaaa")

        second = derive("req_unit_aaaaaaaa")

        self.assertEqual(first, second)

    def test_internal_request_id_is_collision_safe(self) -> None:
        derive = t09_support.loop.derive_internal_request_id

        first = derive("req_" + "a" * 60)

        second = derive("req_" + "a" * 59 + "b")

        self.assertNotEqual(first, second)

    def test_internal_request_id_satisfies_the_t05_pattern(
        self,
    ) -> None:
        derive = t09_support.loop.derive_internal_request_id

        for caller in [
            "req_abc",
            "req_unit_aaaaaaaa",
            "req_" + "z" * 64,
            "req_x",
        ]:
            internal = derive(caller)

            context = RequestContext(
                request_id=internal,
                trace_id="trc_unit_aaaaaaaa",
                turn_id="turn_unit_aaaaaaaa",
                conversation_id="conv_unit_aaaaaaaa",
                actor_id="actor-unit-test",
                household_id="household-unit-test",
            )

            self.assertEqual(
                context.request_id,
                internal,
            )

    def test_the_internal_request_preserves_the_caller_identity(
        self,
    ) -> None:
        request = make_tool_request(suffix="t09dcorr")

        posts: list[dict] = []

        transport = tool_transport(
            decision=decision(
                "direct_response",
                answer="ok",
            ),
            posts=posts,
        )

        run_invoke_with_tools(request, transport)

        internal = posts[0]["json"]["context"]

        self.assertEqual(
            internal["trace_id"],
            request.context.trace_id,
        )

        self.assertEqual(
            internal["turn_id"],
            request.context.turn_id,
        )

        self.assertEqual(
            internal["conversation_id"],
            request.context.conversation_id,
        )

        self.assertNotEqual(
            internal["request_id"],
            request.context.request_id,
        )

    def test_a_is_validated_against_the_internal_request(
        self,
    ) -> None:
        request = make_tool_request(suffix="t09dmismatch")

        def handler(method, url, **kwargs):
            from support import json_response

            return json_response(
                {
                    "contract_version": "1.0.0",
                    "correlation": {
                        "request_id": request.context.request_id,
                        "trace_id": request.context.trace_id,
                        "turn_id": request.context.turn_id,
                        "conversation_id": (
                            request.context.conversation_id
                        ),
                    },
                    "node_id": "homi-a",
                    "provider_id": "think-primary",
                    "capability": "think",
                    "status": "SUCCESS",
                    "timestamp": "2026-10-20T16:00:00+00:00",
                    "result": {
                        "decision": decision(
                            "direct_response",
                            answer="ok",
                        )
                    },
                }
            )

        transport = tool_transport(handler=handler)

        result = run_invoke_with_tools(request, transport)

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertEqual(
            result.error.message,
            "correlation mismatch",
        )

    def test_the_caller_always_receives_the_original_correlation(
        self,
    ) -> None:
        request = make_tool_request(suffix="t09dcaller")

        transport = tool_transport(
            decision=decision(
                "direct_response",
                answer="ok",
            )
        )

        result = run_invoke_with_tools(
            request,
            transport,
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.correlation.request_id,
            request.context.request_id,
        )

        self.assertEqual(
            result.correlation.trace_id,
            request.context.trace_id,
        )

        self.assertEqual(
            result.correlation.turn_id,
            request.context.turn_id,
        )

        self.assertEqual(
            result.correlation.conversation_id,
            request.context.conversation_id,
        )

    def test_the_internal_request_id_is_never_exposed(self) -> None:
        request = make_tool_request(suffix="t09dhidden")

        transport = tool_transport(
            decision=decision(
                "direct_response",
                answer="ok",
            )
        )

        result = run_invoke_with_tools(request, transport)

        internal_id = t09_support.loop.derive_internal_request_id(
            request.context.request_id
        )

        serialized = t09_support.serialized(result)

        self.assertNotIn(internal_id, serialized)

    def test_a_provider_error_never_exposes_the_internal_id(
        self,
    ) -> None:
        request = make_tool_request(suffix="t09derrenv")

        from support import json_response

        def handler(method, url, **kwargs):
            body = kwargs.get("json") or {}

            context = body.get("context") or {}

            return json_response(
                {
                    "contract_version": "1.0.0",
                    "correlation": {
                        "request_id": context.get("request_id"),
                        "trace_id": context.get("trace_id"),
                        "turn_id": context.get("turn_id"),
                        "conversation_id": context.get(
                            "conversation_id"
                        ),
                    },
                    "status": "ERROR",
                    "timestamp": "2026-10-20T16:00:00+00:00",
                    "error": {
                        "code": "PROVIDER_ERROR",
                        "message": "model not ready",
                        "retryable": False,
                        "node_id": "homi-a",
                        "provider_id": "think-primary",
                        "details": {},
                    },
                }
            )

        transport = tool_transport(handler=handler)

        result = run_invoke_with_tools(request, transport)

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        internal_id = t09_support.loop.derive_internal_request_id(
            request.context.request_id
        )

        self.assertNotIn(
            internal_id,
            t09_support.serialized(result),
        )

        self.assertEqual(
            result.correlation.request_id,
            request.context.request_id,
        )


if __name__ == "__main__":
    unittest.main()
