from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any


ORCHESTRATOR_ROOT = (
    Path(__file__).resolve().parent.parent
)

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

import homi_tool_contract as contract  # noqa: E402


CANONICAL_TOOL_IDS = (
    "planner.attention.get",
    "planner.calendar.get",
    "planner.events.get",
    "planner.events.list",
    "planner.search.query",
    "planner.summary.get",
    "planner.tasks.get",
    "planner.tasks.list",
)


def direct_response(
    answer: str = "La lista de tareas esta vacia.",
) -> dict[str, Any]:
    return {
        "decision": "direct_response",
        "answer": answer,
        "question": None,
        "tool_id": None,
        "arguments": None,
    }


def clarify(
    question: str = "Que periodo quieres revisar?",
) -> dict[str, Any]:
    return {
        "decision": "clarify",
        "answer": None,
        "question": question,
        "tool_id": None,
        "arguments": None,
    }


def tool_request(
    tool_id: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": tool_id,
        "arguments": (
            arguments if arguments is not None else {}
        ),
    }


class DecisionShapeTests(unittest.TestCase):
    """The three decision shapes are valid and mutually exclusive."""

    def test_valid_direct_response(self) -> None:
        decision = contract.parse_decision(
            direct_response()
        )

        self.assertEqual(
            decision.decision,
            "direct_response",
        )

        self.assertEqual(
            decision.answer,
            "La lista de tareas esta vacia.",
        )

        self.assertIsNone(decision.question)
        self.assertIsNone(decision.tool_id)
        self.assertIsNone(decision.arguments)

    def test_valid_clarify(self) -> None:
        decision = contract.parse_decision(
            clarify()
        )

        self.assertEqual(
            decision.decision,
            "clarify",
        )

        self.assertEqual(
            decision.question,
            "Que periodo quieres revisar?",
        )

        self.assertIsNone(decision.answer)
        self.assertIsNone(decision.tool_id)
        self.assertIsNone(decision.arguments)

    def test_valid_tool_request_for_every_target_tool_id(self) -> None:
        from homi_tool_catalog import effective_tool_ids

        for tool_id in effective_tool_ids():
            with self.subTest(tool_id=tool_id):
                decision = contract.parse_decision(
                    tool_request(tool_id)
                )

                self.assertEqual(
                    decision.decision,
                    "tool_request",
                )

                self.assertEqual(
                    decision.tool_id,
                    tool_id,
                )

                self.assertEqual(
                    decision.arguments,
                    {},
                )

                self.assertIsNone(decision.answer)
                self.assertIsNone(decision.question)

    def test_valid_tool_request_with_arguments(self) -> None:
        decision = contract.parse_decision(
            tool_request(
                "planner.tasks.list",
                {"limit": 10, "status": "pending"},
            )
        )

        self.assertEqual(
            decision.arguments,
            {"limit": 10, "status": "pending"},
        )

    def test_unknown_decision_is_rejected(self) -> None:
        payload = direct_response()

        payload["decision"] = "execute"

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_unknown_tool_is_rejected(self) -> None:
        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(
                tool_request("planner.calendar")
            )

    def test_obsolete_tool_ids_are_rejected(self) -> None:
        for obsolete in (
            "planner.calendar",
            "planner.summary",
            "planner.attention",
            "search.query",
        ):
            with self.subTest(tool_id=obsolete):
                with self.assertRaises(
                    contract.ToolDecisionError
                ):
                    contract.parse_decision(
                        tool_request(obsolete)
                    )

    def test_extra_top_level_field_is_rejected(self) -> None:
        payload = direct_response()

        payload["confidence"] = 0.9

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_execution_metadata_is_rejected(self) -> None:
        for field in contract.MODEL_FORBIDDEN_FIELDS:
            with self.subTest(field=field):
                payload = tool_request("planner.tasks.list")

                payload[field] = "anything"

                with self.assertRaises(
                    contract.ToolDecisionError
                ):
                    contract.parse_decision(payload)

    def test_direct_response_with_tool_is_rejected(self) -> None:
        payload = direct_response()

        payload["tool_id"] = "planner.tasks.list"

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_direct_response_with_arguments_is_rejected(self) -> None:
        payload = direct_response()

        payload["arguments"] = {}

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_direct_response_with_question_is_rejected(self) -> None:
        payload = direct_response()

        payload["question"] = "Por que?"

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_direct_response_with_blank_answer_is_rejected(self) -> None:
        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(
                direct_response("   \n\t ")
            )

    def test_tool_request_with_answer_is_rejected(self) -> None:
        payload = tool_request("planner.tasks.list")

        payload["answer"] = "HOMI"

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_tool_request_with_question_is_rejected(self) -> None:
        payload = tool_request("planner.tasks.list")

        payload["question"] = "Por que?"

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_tool_request_without_arguments_is_rejected(self) -> None:
        payload = tool_request("planner.tasks.list")

        payload["arguments"] = None

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_clarify_with_blank_question_is_rejected(self) -> None:
        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(
                clarify("   ")
            )

    def test_clarify_with_answer_is_rejected(self) -> None:
        payload = clarify()

        payload["answer"] = "HOMI"

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_clarify_with_tool_is_rejected(self) -> None:
        payload = clarify()

        payload["tool_id"] = "planner.tasks.list"

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_missing_required_top_level_field_is_rejected(self) -> None:
        for field in contract.DECISION_FIELDS:
            with self.subTest(field=field):
                payload = direct_response()

                payload.pop(field)

                with self.assertRaises(
                    contract.ToolDecisionError
                ):
                    contract.parse_decision(payload)

    def test_null_required_field_is_rejected_for_direct_response(
        self,
    ) -> None:
        payload = direct_response()

        payload["answer"] = None

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_arguments_non_object_is_rejected(self) -> None:
        for arguments in (
            "planner.tasks.list",
            42,
            ["planner.tasks.list"],
            True,
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(
                    contract.ToolDecisionError
                ):
                    contract.parse_decision(
                        tool_request(
                            "planner.tasks.list",
                            arguments,  # type: ignore[arg-type]
                        )
                    )

    def test_forbidden_auth_argument_is_rejected(self) -> None:
        for key in (
            "actor_id",
            "household_id",
            "membership_id",
            "role",
            "token",
            "authorization",
            "url",
            "sql",
        ):
            with self.subTest(key=key):
                with self.assertRaises(
                    contract.ToolDecisionError
                ):
                    contract.parse_decision(
                        tool_request(
                            "planner.tasks.list",
                            {key: "x"},
                        )
                    )

    def test_non_object_payload_is_rejected(self) -> None:
        for payload in (
            None,
            "direct_response",
            ["direct_response"],
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(
                    contract.ToolDecisionError
                ):
                    contract.parse_decision(payload)

    def test_invalid_model_output_is_never_coerced(self) -> None:
        payload = direct_response()

        payload["answer"] = 42

        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.parse_decision(payload)

    def test_decision_model_forbids_extra_fields(self) -> None:
        self.assertEqual(
            contract.ToolDecisionV1.model_config.get(
                "extra"
            ),
            "forbid",
        )


class DecisionJsonSchemaTests(unittest.TestCase):
    """The decision JSON Schema is flat and deterministic."""

    def test_schema_is_a_closed_object(self) -> None:
        schema = contract.decision_json_schema()

        self.assertEqual(
            schema["type"],
            "object",
        )

        self.assertIs(
            schema["additionalProperties"],
            False,
        )

    def test_schema_requires_the_five_decision_fields(self) -> None:
        schema = contract.decision_json_schema()

        self.assertEqual(
            sorted(schema["required"]),
            [
                "answer",
                "arguments",
                "decision",
                "question",
                "tool_id",
            ],
        )

        self.assertEqual(
            len(schema["required"]),
            5,
        )

    def test_schema_declares_exactly_the_five_properties(self) -> None:
        schema = contract.decision_json_schema()

        self.assertEqual(
            sorted(schema["properties"].keys()),
            [
                "answer",
                "arguments",
                "decision",
                "question",
                "tool_id",
            ],
        )

    def test_decision_enum_is_exact(self) -> None:
        schema = contract.decision_json_schema()

        self.assertEqual(
            schema["properties"]["decision"]["enum"],
            [
                "direct_response",
                "tool_request",
                "clarify",
            ],
        )

    def test_tool_id_enum_is_the_effective_tool_ids_plus_null(
        self,
    ) -> None:
        from homi_tool_catalog import effective_tool_ids

        schema = contract.decision_json_schema()

        self.assertEqual(
            schema["properties"]["tool_id"]["enum"],
            [
                *effective_tool_ids(),
                None,
            ],
        )

    def test_answer_and_question_are_nullable_strings(self) -> None:
        schema = contract.decision_json_schema()

        self.assertEqual(
            schema["properties"]["answer"]["type"],
            ["string", "null"],
        )

        self.assertEqual(
            schema["properties"]["question"]["type"],
            ["string", "null"],
        )

    def test_arguments_is_a_nullable_object(self) -> None:
        schema = contract.decision_json_schema()

        self.assertEqual(
            schema["properties"]["arguments"]["type"],
            ["object", "null"],
        )

    def test_schema_is_flat(self) -> None:
        schema = contract.decision_json_schema()

        serialized = json.dumps(schema)

        for forbidden in (
            "oneOf",
            "allOf",
            "$ref",
            "anyOf",
        ):
            self.assertNotIn(
                forbidden,
                serialized,
            )

    def test_schema_does_not_depend_on_strict_flag(self) -> None:
        schema = contract.decision_json_schema()

        self.assertNotIn(
            "strict",
            json.dumps(schema),
        )

    def test_schema_is_deterministic(self) -> None:
        self.assertEqual(
            contract.decision_json_schema_text(),
            contract.decision_json_schema_text(),
        )

    def test_schema_text_is_stable_json(self) -> None:
        parsed = json.loads(
            contract.decision_json_schema_text()
        )

        self.assertEqual(
            parsed,
            contract.decision_json_schema(),
        )

    def test_schema_exposes_no_execution_metadata(self) -> None:
        serialized = contract.decision_json_schema_text()

        for forbidden in (
            "tool_call_id",
            "catalog_digest",
            "request_id",
            "trace_id",
            "actor_id",
            "household_id",
            "authorization",
        ):
            self.assertNotIn(
                forbidden,
                serialized,
            )


class ArgumentPrecheckTests(unittest.TestCase):
    """The argument precheck is a cheap, reusable, fail-closed layer."""

    def test_valid_arguments_pass(self) -> None:
        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"limit": 10, "status": "pending"},
            ),
            [],
        )

    def test_unknown_tool_is_reported(self) -> None:
        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.calendar",
                {},
            ),
            ["unknown_tool"],
        )

    def test_non_object_arguments_are_reported(self) -> None:
        for arguments in (
            None,
            "x",
            1,
            ["x"],
        ):
            with self.subTest(arguments=arguments):
                self.assertEqual(
                    contract.precheck_tool_arguments(
                        "planner.tasks.list",
                        arguments,
                    ),
                    ["arguments_not_object"],
                )

    def test_forbidden_identity_argument_is_reported(self) -> None:
        violations = contract.precheck_tool_arguments(
            "planner.tasks.list",
            {"actor_id": "x"},
        )

        self.assertIn(
            "forbidden_key:actor_id",
            violations,
        )

    def test_unknown_argument_name_is_reported(self) -> None:
        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"unknown": 1},
            ),
            ["unknown_argument:unknown"],
        )

    def test_missing_required_argument_is_reported(self) -> None:
        violations = contract.precheck_tool_arguments(
            "planner.tasks.get",
            {},
        )

        self.assertEqual(
            violations,
            ["missing_required:taskId"],
        )

    def test_primitive_checks_are_reported(self) -> None:
        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"limit": 0},
            ),
            ["below_minimum:limit"],
        )

        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"limit": 1000},
            ),
            ["above_maximum:limit"],
        )

        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"status": "unknown-status"},
            ),
            ["not_in_enum:status"],
        )

        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"limit": "10"},
            ),
            ["invalid_type:limit"],
        )

        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"from": "20-10-2026"},
            ),
            ["pattern_mismatch:from"],
        )

        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.get",
                {"taskId": ""},
            ),
            ["too_short:taskId"],
        )

    def test_boolean_arguments_are_accepted(self) -> None:
        self.assertEqual(
            contract.precheck_tool_arguments(
                "planner.tasks.list",
                {"includeCancelled": True},
            ),
            [],
        )

    def test_assert_tool_arguments_fails_closed(self) -> None:
        with self.assertRaises(
            contract.ToolDecisionError
        ):
            contract.assert_tool_arguments(
                "planner.tasks.get",
                {},
            )

    def test_assert_tool_arguments_accepts_valid_arguments(self) -> None:
        contract.assert_tool_arguments(
            "planner.tasks.get",
            {"taskId": "abc"},
        )


if __name__ == "__main__":
    unittest.main()
