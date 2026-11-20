from __future__ import annotations

import re
import unittest

import homi_tool_loop as loop
from homi_tool_catalog import CANONICAL_TOOL_IDS, catalog
from homi_tool_contract import ToolDecisionError, parse_decision, precheck_tool_arguments


class ModelProjectionCompatibilityTests(unittest.TestCase):
    def test_canonical_catalogue_remains_unchanged(self) -> None:
        canonical = catalog().require("planner.tasks.list")["inputSchema"]
        self.assertIn("status", canonical["properties"])
        self.assertNotIn(loop.MODEL_STATUS_ALIAS, canonical["properties"])

    def test_projection_is_explicitly_versioned(self) -> None:
        self.assertEqual(loop.MODEL_TOOL_PROJECTION_VERSION, "2.1.0")

    def test_read_projection_uses_provider_palette_and_status_alias(self) -> None:
        projection = loop._write_tool_catalog_projection(
            "Mostrame las tareas pendientes"
        )
        self.assertTrue(projection)
        self.assertLessEqual(len(projection), len(CANONICAL_TOOL_IDS))
        self.assertTrue(
            all(entry["tool_id"] in CANONICAL_TOOL_IDS for entry in projection)
        )
        task_list = next(
            entry
            for entry in projection
            if "tasks list" in entry["description"]
        )
        properties = task_list["input_schema"]["properties"]
        self.assertIn(loop.MODEL_STATUS_ALIAS, properties)
        self.assertNotIn("status", properties)

    def test_read_alias_is_mapped_to_canonical_tool_and_arguments(self) -> None:
        text = "Mostrame las tareas pendientes"
        aliases = loop._model_read_aliases(text)
        model_id = next(
            model
            for model, canonical in aliases.items()
            if canonical == "planner.tasks.list"
        )
        decision = loop._canonicalize_model_decision(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": model_id,
                "arguments": {loop.MODEL_STATUS_ALIAS: "pending"},
            },
            text,
        )
        self.assertEqual(decision["tool_id"], "planner.tasks.list")
        self.assertEqual(decision["arguments"], {"status": "pending"})
        self.assertEqual(
            precheck_tool_arguments(decision["tool_id"], decision["arguments"]),
            [],
        )

    def test_finance_and_inventory_aliases_map_back_to_real_tools(self) -> None:
        cases = (
            ("Mostrame el saldo de mis cuentas", "finance.accounts.list"),
            ("Que productos tengo en el inventario", "inventory.items.list"),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                aliases = loop._model_read_aliases(text)
                self.assertIn(expected, aliases.values())
                model_id = next(
                    model for model, canonical in aliases.items()
                    if canonical == expected
                )
                canonical = loop._canonicalize_model_decision(
                    {
                        "decision": "tool_request",
                        "answer": None,
                        "question": None,
                        "tool_id": model_id,
                        "arguments": {},
                    },
                    text,
                )
                self.assertEqual(canonical["tool_id"], expected)

    def test_explicit_search_exposes_only_canonical_search(self) -> None:
        text = "Busca la tarea Entidad QA inexistente 9f7c2"
        aliases = loop._model_read_aliases(text)
        self.assertEqual(
            aliases,
            {"planner.search.query": "planner.tasks.search"},
        )
        projection = loop._write_tool_catalog_projection(text)
        self.assertEqual(len(projection), 1)
        self.assertNotIn(
            "context",
            projection[0]["input_schema"]["properties"],
        )

    def test_read_null_write_fields_are_dropped_but_real_values_fail_closed(self) -> None:
        text = "¿Qué productos tengo en el inventario?"
        aliases = loop._model_read_aliases(text)
        model_id = next(
            model for model, canonical in aliases.items()
            if canonical == "inventory.items.list"
        )
        decision = loop._canonicalize_model_decision(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": model_id,
                "arguments": {
                    "query": "leche",
                    "target": None,
                    "checklist_patch": None,
                    "assign_member_name": None,
                    "proposal_edit_patch": None,
                    "proposal_action": None,
                },
            },
            text,
        )
        self.assertEqual(decision["arguments"], {"query": "leche"})
        self.assertEqual(
            precheck_tool_arguments(decision["tool_id"], decision["arguments"]),
            [],
        )

        non_null = loop._canonicalize_model_decision(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": model_id,
                "arguments": {"proposal_action": "confirm"},
            },
            text,
        )
        self.assertEqual(
            non_null["arguments"],
            {"proposal_action": "confirm"},
        )

    def test_write_projection_ids_are_provider_compatible(self) -> None:
        projection = loop._write_tool_catalog_projection(
            "Crea una tarea llamada QA"
        )
        self.assertTrue(projection)
        for entry in projection:
            self.assertRegex(
                entry["tool_id"],
                re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$"),
            )

    def test_identity_fields_are_never_transformed_away(self) -> None:
        text = "Mostrame mis tareas"
        model_id = next(
            model
            for model, canonical in loop._model_read_aliases(text).items()
            if canonical == "planner.tasks.list"
        )
        decision = loop._canonicalize_model_decision(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": model_id,
                "arguments": {"actor_id": "forged"},
            },
            text,
        )
        with self.assertRaises(ToolDecisionError):
            parse_decision(decision)

    def test_read_payload_uses_frozen_provider_shape_without_changing_catalog(self) -> None:
        payload = loop.build_decision_payload(
            "Mostrame el saldo de mis cuentas",
            decision_version="v2",
        )
        self.assertEqual(payload["decision_schema_version"], "1.0")
        self.assertEqual(
            payload["decision_schema_digest"],
            loop.THINK_READ_DECISION_SCHEMA_DIGEST,
        )
        self.assertEqual(payload["catalog_digest"], catalog().digest.upper())


if __name__ == "__main__":
    unittest.main()
