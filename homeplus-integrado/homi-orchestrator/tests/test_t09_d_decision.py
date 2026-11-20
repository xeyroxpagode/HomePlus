"""HOMI T09-D — structured decision validation on Node D."""

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


class DecisionTests(unittest.TestCase):

    def _run(
        self,
        payload,
        *,
        authorization=None,
        executor=None,
    ):
        transport = tool_transport(decision=payload)

        if executor is None:
            result = run_invoke_with_tools(
                make_tool_request(suffix="t09ddec"),
                transport,
                authorization=authorization,
            )

        else:
            with installed_executor(executor):
                result = run_invoke_with_tools(
                    make_tool_request(suffix="t09ddec"),
                    transport,
                    authorization=authorization,
                )

        return result

    def test_direct_response_is_answered(self) -> None:
        result = self._run(
            decision(
                "direct_response",
                answer="La capital de Argentina es Buenos Aires.",
            )
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            result.result.get("answer"),
            "La capital de Argentina es Buenos Aires.",
        )

        self.assertEqual(
            result.result.get("decision_kind"),
            "direct_response",
        )

    def test_clarify_is_answered(self) -> None:
        result = self._run(
            decision(
                "clarify",
                question="Que tareas quieres revisar?",
            )
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            result.result.get("answer"),
            "Que tareas quieres revisar?",
        )

        self.assertEqual(
            result.result.get("decision_kind"),
            "clarify",
        )

    def test_valid_tool_request_is_accepted(self) -> None:
        executor = FakeExecutor()

        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
            executor=executor,
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
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
            result.result.get("tool_call_id")
        )

        self.assertEqual(
            len(executor.calls),
            1,
        )

    def test_unknown_tool_is_rejected(self) -> None:
        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.unknown.tool",
                arguments={},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertFalse(result.error.retryable)

    def test_write_tool_name_is_rejected(self) -> None:
        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.create",
                arguments={"title": "nueva"},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_invalid_arguments_are_rejected(self) -> None:
        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"unknown_arg": 1},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_missing_required_argument_is_rejected(self) -> None:
        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.get",
                arguments={},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_identity_key_injected_in_arguments_is_rejected(
        self,
    ) -> None:
        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"actor_id": "attacker"},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_endpoint_injected_in_arguments_is_rejected(self) -> None:
        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"endpoint": "http://evil.invalid"},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_url_injected_in_arguments_is_rejected(self) -> None:
        result = self._run(
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"url": "http://evil.invalid"},
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_malformed_decision_is_rejected(self) -> None:
        result = self._run(
            {"decision": "direct_response"}
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_missing_decision_is_rejected(self) -> None:
        transport = tool_transport(
            handler=t09_support.decision_handler(
                None,
                raw_result={"answer": "sin decision"},
            )
        )

        result = run_invoke_with_tools(
            make_tool_request(suffix="t09dnodec"),
            transport,
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_model_cannot_mint_the_tool_call_id(self) -> None:
        result = self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
                "tool_call_id": "tcall_model_supplied",
            },
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertNotIn(
            "tcall_model_supplied",
            t09_support.serialized(result),
        )

    def test_model_cannot_inject_the_catalog_digest(self) -> None:
        result = self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
                "catalog_digest": "0" * 64,
            },
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

    def test_the_catalogue_is_never_exposed_to_the_caller(self) -> None:
        result = self._run(
            decision(
                "direct_response",
                answer="ok",
            )
        )

        serialized = t09_support.serialized(result)

        self.assertNotIn("planner.tasks.list", serialized)
        self.assertNotIn("input_schema", serialized)
        self.assertNotIn("READ_ONLY", serialized)

    def test_missing_text_is_an_invalid_request(self) -> None:
        transport = tool_transport(
            decision=decision(
                "direct_response",
                answer="ok",
            )
        )

        result = run_invoke_with_tools(
            make_tool_request(
                suffix="t09dnotext",
                payload={},
            ),
            transport,
        )

        self.assertEqual(
            result.error.code.value,
            "INVALID_REQUEST",
        )

    def test_a_json_string_decision_is_accepted(self) -> None:
        import json

        transport = tool_transport(
            handler=t09_support.decision_handler(
                json.dumps(
                    decision(
                        "direct_response",
                        answer="ok",
                    )
                )
            )
        )

        result = run_invoke_with_tools(
            make_tool_request(suffix="t09djsonstr"),
            transport,
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            result.result.get("answer"),
            "ok",
        )

    def test_a_malformed_json_string_decision_is_rejected(self) -> None:
        transport = tool_transport(
            handler=t09_support.decision_handler(
                "{not json"
            )
        )

        result = run_invoke_with_tools(
            make_tool_request(suffix="t09dbadjson"),
            transport,
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )


if __name__ == "__main__":
    unittest.main()
