"""HOMI T09-F — the tool result normalizer of Node D.

The normalizer turns ONE successful T07 READ result into the bounded,
safe, model facing ToolResultV1. These tests cover the eight
projections, the field allow-lists, the internal id stripping, the
string caps, the item caps, the byte cap, the truncation metadata, the
empty result and the malformed raw result.
"""

from __future__ import annotations

import json
import unittest

import t09f_support as f
from t09f_support import (
    T09F_ACTOR_ID,
    T09F_EVENT_ID,
    T09F_HOUSEHOLD_ID,
    T09F_MEMBER_ID,
    T09F_PERSON_ID,
    T09F_TASK_ID,
)

from homi_tool_normalize import (
    MAX_ATTENTION_ITEMS,
    MAX_CALENDAR_ITEMS,
    MAX_DESCRIPTION_CHARS,
    MAX_EVENTS_LIST_ITEMS,
    MAX_FREE_TEXT_CHARS,
    MAX_SEARCH_GROUPS,
    MAX_SEARCH_RESULTS_PER_GROUP,
    MAX_SUMMARY_CHARS,
    MAX_TASKS_LIST_ITEMS,
    MAX_TOOL_RESULT_BYTES,
    MAX_TITLE_CHARS,
    TOOL_RESULT_VERSION,
    TOOL_STATUS_SUCCESS,
    ToolNormalizationError,
    assert_tool_result_is_safe,
    canonical_serialization,
    canonical_size,
    forbidden_keys_in,
    normalize_tool_result,
    strip_internal_keys,
)


CANONICAL_TOOLS: tuple[str, ...] = (
    "planner.attention.get",
    "planner.calendar.get",
    "planner.events.get",
    "planner.events.list",
    "planner.search.query",
    "planner.summary.get",
    "planner.tasks.get",
    "planner.tasks.list",
)


class ToolResultShapeTests(unittest.TestCase):
    """The shape of the model facing result."""

    def test_the_result_carries_the_exact_model_facing_shape(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(),
        )

        payload = result.to_payload()

        self.assertEqual(
            sorted(payload),
            ["data", "meta", "status", "tool_id"],
        )

        self.assertEqual(
            payload["tool_id"],
            "planner.tasks.list",
        )

        self.assertEqual(
            payload["status"],
            TOOL_STATUS_SUCCESS,
        )

        self.assertEqual(
            sorted(payload["meta"]),
            [
                "omitted_count",
                "returned_count",
                "total_count",
                "truncated",
                "truncation_reason",
            ],
        )

    def test_the_version_of_the_result_is_exposed(self) -> None:
        self.assertEqual(TOOL_RESULT_VERSION, "1.0")

    def test_every_canonical_tool_has_a_projection(self) -> None:
        fixtures = {
            "planner.attention.get": f.real_attention_result(),
            "planner.calendar.get": f.real_calendar_result(),
            "planner.events.get": f.real_event_get_result(),
            "planner.events.list": f.real_events_list_result(),
            "planner.search.query": f.real_search_result(),
            "planner.summary.get": f.real_summary_result(),
            "planner.tasks.get": f.real_task_get_result(),
            "planner.tasks.list": f.real_tasks_list_result(),
        }

        self.assertEqual(
            sorted(fixtures),
            sorted(CANONICAL_TOOLS),
        )

        for tool_id, raw in fixtures.items():
            result = normalize_tool_result(tool_id, raw)

            self.assertEqual(result.tool_id, tool_id)

            self.assertEqual(result.status, TOOL_STATUS_SUCCESS)

            self.assertIsInstance(result.data, dict)

    def test_an_unknown_tool_is_rejected(self) -> None:
        with self.assertRaises(ToolNormalizationError) as ctx:
            normalize_tool_result(
                "planner.unknown.tool",
                {},
            )

        self.assertEqual(
            ctx.exception.code,
            "TOOL_RESULT_UNSUPPORTED",
        )

    def test_a_malformed_raw_result_is_rejected(self) -> None:
        for raw in (
            None,
            [],
            "not-an-object",
            42,
        ):
            with self.assertRaises(ToolNormalizationError) as ctx:
                normalize_tool_result(
                    "planner.tasks.list",
                    raw,
                )

            self.assertEqual(
                ctx.exception.code,
                "TOOL_RESULT_MALFORMED",
            )


class ProjectionTests(unittest.TestCase):
    """The positive per tool projection."""

    def test_the_task_projection_keeps_the_answerable_fields(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(),
        )

        task = result.data["tasks"][0]

        self.assertEqual(task["id"], T09F_TASK_ID)

        self.assertEqual(task["title"], "Hacer las compras")

        self.assertEqual(task["status"], "pending")

        self.assertEqual(task["priority"], "normal")

        self.assertIn("description", task)

        self.assertIn("due_date", task)

        self.assertIn("requires_verification", task)

    def test_the_event_projection_keeps_the_answerable_fields(self) -> None:
        result = normalize_tool_result(
            "planner.events.list",
            f.real_events_list_result(),
        )

        event = result.data["events"][0]

        self.assertEqual(event["id"], T09F_EVENT_ID)

        self.assertEqual(event["title"], "Evento numero 0")

        self.assertEqual(event["starts_at"], "2026-10-25T14:00:00+00:00")

        self.assertEqual(event["ends_at"], "2026-10-25T15:00:00+00:00")

        self.assertEqual(event["status"], "scheduled")

        self.assertEqual(event["all_day"], False)

        self.assertEqual(event["location_name"], "Casa")

    def test_the_single_entity_tools_keep_one_entity(self) -> None:
        task = normalize_tool_result(
            "planner.tasks.get",
            f.real_task_get_result(),
        )

        self.assertEqual(task.data["task"]["id"], T09F_TASK_ID)

        event = normalize_tool_result(
            "planner.events.get",
            f.real_event_get_result(),
        )

        self.assertEqual(event.data["event"]["id"], T09F_EVENT_ID)

    def test_the_calendar_projection_keeps_the_range(self) -> None:
        result = normalize_tool_result(
            "planner.calendar.get",
            f.real_calendar_result(),
        )

        self.assertEqual(result.data["view"], "month")

        self.assertEqual(result.data["date"], "2026-10-21")

        self.assertEqual(
            result.data["range"]["from"],
            "2026-10-01T00:00:00.000Z",
        )

        self.assertEqual(
            result.data["items"][0]["title"],
            "T09-E EVENTO BETA",
        )

    def test_the_summary_projection_keeps_the_counts(self) -> None:
        result = normalize_tool_result(
            "planner.summary.get",
            f.real_summary_result(),
        )

        self.assertEqual(
            result.data["counts"],
            {"tasks": 1, "events": 0, "goals": 0},
        )

        self.assertEqual(
            result.data["tasks"][0]["title"],
            "Hacer las compras",
        )

    def test_the_summary_projection_drops_the_briefing_text(self) -> None:
        # The source briefing_text counts the tasks that are DUE
        # TODAY, while counts.tasks counts the pending tasks of the
        # household. Both are truthful but they describe different
        # populations, so only the structured facts reach the model.
        result = normalize_tool_result(
            "planner.summary.get",
            f.real_summary_result(),
        )

        self.assertNotIn("briefing_text", result.data)

        self.assertEqual(
            sorted(result.data),
            [
                "counts",
                "events",
                "generated_at",
                "goal",
                "projection_version",
                "tasks",
            ],
        )

        # The structured facts carry everything the narrative carried.
        self.assertEqual(
            result.data["counts"]["tasks"],
            1,
        )

        self.assertEqual(
            result.data["tasks"][0]["due_date"],
            None,
        )

    def test_the_attention_projection_keeps_the_reason(self) -> None:
        result = normalize_tool_result(
            "planner.attention.get",
            f.real_attention_result(rows=1, total=1),
        )

        item = result.data["items"][0]

        self.assertEqual(item["title"], "Hacer las compras")

        self.assertEqual(item["reason"], "Vence manana.")

        self.assertEqual(item["severity"], "medium")

        self.assertEqual(item["entityId"], T09F_TASK_ID)

    def test_the_search_projection_keeps_the_groups(self) -> None:
        result = normalize_tool_result(
            "planner.search.query",
            f.real_search_result(),
        )

        groups = result.data["groups"]

        self.assertEqual(len(groups), 3)

        self.assertEqual(groups[0]["entityType"], "task")

        self.assertEqual(groups[0]["label"], "Tareas")

        self.assertEqual(
            groups[0]["results"][0]["title"],
            "T09-E TASK ALFA",
        )

        self.assertEqual(
            groups[0]["results"][0]["metadata"]["status"],
            "pending",
        )


class InternalIdStrippingTests(unittest.TestCase):
    """No internal, identity or auth field ever reaches the model."""

    def test_the_task_projection_strips_the_household_id(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(),
        )

        serialized = canonical_serialization(result.to_payload())

        self.assertNotIn(T09F_HOUSEHOLD_ID, serialized)

        self.assertNotIn("household_id", serialized)

    def test_the_task_projection_strips_the_member_foreign_keys(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(),
        )

        serialized = canonical_serialization(result.to_payload())

        self.assertNotIn(T09F_MEMBER_ID, serialized)

        self.assertNotIn(T09F_PERSON_ID, serialized)

        self.assertNotIn("member_id", serialized)

        self.assertNotIn("person_id", serialized)

        self.assertNotIn("assigned_member", serialized)

    def test_the_summary_projection_strips_the_household_id(self) -> None:
        result = normalize_tool_result(
            "planner.summary.get",
            f.real_summary_result(),
        )

        serialized = canonical_serialization(result.to_payload())

        self.assertNotIn(T09F_HOUSEHOLD_ID, serialized)

        self.assertNotIn("partial_errors", serialized)

        self.assertNotIn("summary_goals_failed", serialized)

    def test_the_database_implementation_fields_are_stripped(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(),
        )

        serialized = canonical_serialization(result.to_payload())

        for forbidden in (
            "template_key",
            "origin_module",
            "origin_entity_type",
            "responsibility_id",
            "plan_classification",
            "checklist",
            "trashed_at",
            "cancelled_at",
            "estimated_duration_minutes",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_the_search_projection_strips_the_navigation_descriptor(
        self,
    ) -> None:
        result = normalize_tool_result(
            "planner.search.query",
            f.real_search_result(),
        )

        serialized = canonical_serialization(result.to_payload())

        self.assertNotIn("destination", serialized)

        self.assertNotIn("surfaceOrigin", serialized)

    def test_the_attention_projection_strips_the_internal_keys(self) -> None:
        result = normalize_tool_result(
            "planner.attention.get",
            f.real_attention_result(rows=1, total=1),
        )

        serialized = canonical_serialization(result.to_payload())

        self.assertNotIn("attentionId", serialized)

        self.assertNotIn("dedupeKey", serialized)

    def test_the_recursive_strip_removes_a_nested_identity_key(self) -> None:
        cleaned = strip_internal_keys(
            {
                "a": {
                    "household_id": "x",
                    "b": [
                        {"actor_id": "y"},
                    ],
                },
                "c": 1,
            }
        )

        self.assertEqual(
            cleaned,
            {"a": {"b": [{}]}, "c": 1},
        )

    def test_no_forbidden_key_is_reachable_in_any_projection(self) -> None:
        fixtures = {
            "planner.attention.get": f.real_attention_result(1, 1),
            "planner.calendar.get": f.real_calendar_result(),
            "planner.events.get": f.real_event_get_result(),
            "planner.events.list": f.real_events_list_result(),
            "planner.search.query": f.real_search_result(),
            "planner.summary.get": f.real_summary_result(),
            "planner.tasks.get": f.real_task_get_result(),
            "planner.tasks.list": f.real_tasks_list_result(),
        }

        for tool_id, raw in fixtures.items():
            result = normalize_tool_result(tool_id, raw)

            self.assertEqual(
                forbidden_keys_in(result.to_payload()),
                [],
                tool_id,
            )

    def test_the_safety_gate_rejects_a_forbidden_key(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(),
        )

        assert_tool_result_is_safe(result)

        broken = normalize_tool_result(
            "planner.tasks.list",
            {"tasks": [{"title": "x"}]},
        )

        payload = broken.to_payload()

        payload["data"]["tasks"][0]["household_id"] = "leak"

        with self.assertRaises(ToolNormalizationError) as ctx:
            assert_tool_result_is_safe(broken)

        self.assertEqual(
            ctx.exception.code,
            "TOOL_RESULT_NOT_SAFE",
        )

    def test_the_safety_gate_rejects_a_secret_value(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(),
        )

        with self.assertRaises(ToolNormalizationError) as ctx:
            assert_tool_result_is_safe(
                result,
                secret_values=("Hacer las compras",),
            )

        self.assertEqual(
            ctx.exception.code,
            "TOOL_RESULT_NOT_SAFE",
        )


class StringCapTests(unittest.TestCase):
    """The free text of the source is bounded."""

    def test_the_title_is_capped(self) -> None:
        raw = f.real_tasks_list_result()

        raw["tasks"][0]["title"] = "T" * 5000

        result = normalize_tool_result("planner.tasks.list", raw)

        self.assertEqual(
            len(result.data["tasks"][0]["title"]),
            MAX_TITLE_CHARS,
        )

        self.assertTrue(result.meta.truncated)

        self.assertEqual(
            result.meta.truncation_reason,
            "string_cap",
        )

    def test_the_description_is_capped(self) -> None:
        raw = f.real_tasks_list_result()

        raw["tasks"][0]["description"] = "D" * 5000

        result = normalize_tool_result("planner.tasks.list", raw)

        self.assertEqual(
            len(result.data["tasks"][0]["description"]),
            MAX_DESCRIPTION_CHARS,
        )

    def test_the_summary_and_the_reason_are_capped(self) -> None:
        raw = f.real_attention_result(rows=1, total=1)

        raw["items"][0]["summary"] = "S" * 5000

        raw["items"][0]["reason"] = "R" * 5000

        result = normalize_tool_result("planner.attention.get", raw)

        self.assertEqual(
            len(result.data["items"][0]["summary"]),
            MAX_SUMMARY_CHARS,
        )

        self.assertEqual(
            len(result.data["items"][0]["reason"]),
            MAX_SUMMARY_CHARS,
        )

    def test_any_other_free_text_is_capped_conservatively(self) -> None:
        raw = f.real_tasks_list_result()

        raw["tasks"][0]["category"] = "C" * 5000

        result = normalize_tool_result("planner.tasks.list", raw)

        self.assertEqual(
            len(result.data["tasks"][0]["category"]),
            MAX_FREE_TEXT_CHARS,
        )


class ItemCapTests(unittest.TestCase):
    """The item count of every tool is bounded."""

    def test_the_task_list_is_capped(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(rows=100),
        )

        self.assertEqual(
            len(result.data["tasks"]),
            MAX_TASKS_LIST_ITEMS,
        )

        self.assertTrue(result.meta.truncated)

        self.assertEqual(
            result.meta.truncation_reason,
            "item_cap",
        )

        self.assertEqual(result.meta.returned_count, 20)

        self.assertEqual(result.meta.omitted_count, 80)

        self.assertIsNone(result.meta.total_count)

    def test_the_event_list_is_capped(self) -> None:
        result = normalize_tool_result(
            "planner.events.list",
            f.real_events_list_result(rows=100),
        )

        self.assertEqual(
            len(result.data["events"]),
            MAX_EVENTS_LIST_ITEMS,
        )

        self.assertEqual(result.meta.omitted_count, 80)

    def test_the_calendar_is_capped(self) -> None:
        result = normalize_tool_result(
            "planner.calendar.get",
            f.real_calendar_result(rows=100),
        )

        self.assertEqual(
            len(result.data["items"]),
            MAX_CALENDAR_ITEMS,
        )

        self.assertEqual(result.meta.omitted_count, 70)

    def test_the_attention_list_is_capped(self) -> None:
        result = normalize_tool_result(
            "planner.attention.get",
            f.real_attention_result(rows=100, total=100),
        )

        self.assertEqual(
            len(result.data["items"]),
            MAX_ATTENTION_ITEMS,
        )

        self.assertEqual(result.meta.total_count, 100)

        self.assertEqual(result.meta.omitted_count, 80)

    def test_the_search_results_are_capped_per_group(self) -> None:
        result = normalize_tool_result(
            "planner.search.query",
            f.real_search_result(rows=100),
        )

        groups = result.data["groups"]

        self.assertEqual(len(groups), 3)

        self.assertEqual(
            len(groups[0]["results"]),
            MAX_SEARCH_RESULTS_PER_GROUP,
        )

        self.assertEqual(result.meta.total_count, 100)

        self.assertEqual(result.meta.omitted_count, 90)

    def test_the_search_groups_are_capped(self) -> None:
        raw = f.real_search_result(rows=1)

        groups = list(raw["groups"])

        for index in range(5):
            groups.append(
                {
                    "entityType": f"extra-{index}",
                    "label": "Extra",
                    "results": [],
                }
            )

        raw["groups"] = groups

        result = normalize_tool_result("planner.search.query", raw)

        self.assertEqual(
            len(result.data["groups"]),
            MAX_SEARCH_GROUPS,
        )

    def test_a_single_entity_tool_never_returns_two_entities(self) -> None:
        raw = f.real_task_get_result()

        result = normalize_tool_result("planner.tasks.get", raw)

        self.assertEqual(result.meta.returned_count, 1)


class ByteBudgetTests(unittest.TestCase):
    """The serialized model facing payload is bounded."""

    def test_a_huge_result_stays_inside_the_byte_budget(self) -> None:
        raw = f.real_tasks_list_result(rows=MAX_TASKS_LIST_ITEMS)

        for task in raw["tasks"]:
            task["title"] = "T" * 5000

            task["description"] = "D" * 5000

        result = normalize_tool_result("planner.tasks.list", raw)

        payload = result.to_payload()

        self.assertLessEqual(
            canonical_size(payload),
            MAX_TOOL_RESULT_BYTES,
        )

        self.assertTrue(result.meta.truncated)

    def test_the_reduced_payload_is_valid_json(self) -> None:
        raw = f.real_tasks_list_result(rows=MAX_TASKS_LIST_ITEMS)

        for task in raw["tasks"]:
            task["description"] = "D" * 5000

        result = normalize_tool_result("planner.tasks.list", raw)

        text = canonical_serialization(result.to_payload())

        decoded = json.loads(text)

        self.assertEqual(
            decoded["tool_id"],
            "planner.tasks.list",
        )

        self.assertIsInstance(decoded["data"], dict)

        self.assertIsInstance(decoded["meta"], dict)

    def test_the_serialized_payload_never_ends_inside_a_string(self) -> None:
        raw = f.real_tasks_list_result(rows=MAX_TASKS_LIST_ITEMS)

        for task in raw["tasks"]:
            task["title"] = "Ñ" * 5000

        result = normalize_tool_result("planner.tasks.list", raw)

        text = canonical_serialization(result.to_payload())

        self.assertTrue(text.endswith("}"))

        json.loads(text)

    def test_the_canonical_serialization_is_deterministic(self) -> None:
        raw = f.real_tasks_list_result(rows=3)

        first = canonical_serialization(
            normalize_tool_result(
                "planner.tasks.list",
                raw,
            ).to_payload()
        )

        second = canonical_serialization(
            normalize_tool_result(
                "planner.tasks.list",
                raw,
            ).to_payload()
        )

        self.assertEqual(first, second)


class MetadataTests(unittest.TestCase):
    """The truncation metadata is honest."""

    def test_a_complete_result_is_not_truncated(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(rows=1),
        )

        self.assertFalse(result.meta.truncated)

        self.assertIsNone(result.meta.truncation_reason)

        self.assertEqual(result.meta.returned_count, 1)

        self.assertEqual(result.meta.omitted_count, 0)

        self.assertIsNone(result.meta.total_count)

    def test_an_empty_result_is_represented_accurately(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            {"tasks": []},
        )

        self.assertEqual(result.data["tasks"], [])

        self.assertFalse(result.meta.truncated)

        self.assertEqual(result.meta.returned_count, 0)

        self.assertEqual(result.meta.omitted_count, 0)

        self.assertIsNone(result.meta.total_count)

        self.assertIsNone(result.meta.truncation_reason)

    def test_an_empty_attention_result_keeps_the_source_total(self) -> None:
        result = normalize_tool_result(
            "planner.attention.get",
            f.real_attention_result(rows=0, total=0),
        )

        self.assertEqual(result.data["items"], [])

        self.assertEqual(result.meta.total_count, 0)

        self.assertEqual(result.meta.returned_count, 0)

        self.assertFalse(result.meta.truncated)

    def test_a_result_without_a_total_keeps_it_null(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            f.real_tasks_list_result(rows=1),
        )

        self.assertIsNone(result.meta.total_count)

    def test_the_source_total_is_preserved(self) -> None:
        result = normalize_tool_result(
            "planner.attention.get",
            f.real_attention_result(rows=1, total=57),
        )

        self.assertEqual(result.meta.total_count, 57)

        self.assertEqual(result.meta.returned_count, 1)

        self.assertEqual(result.meta.omitted_count, 56)

        self.assertTrue(result.meta.truncated)

    def test_a_missing_item_list_is_an_empty_result(self) -> None:
        result = normalize_tool_result(
            "planner.tasks.list",
            {},
        )

        self.assertEqual(result.data["tasks"], [])

        self.assertEqual(result.meta.returned_count, 0)

        self.assertFalse(result.meta.truncated)

    def test_the_grounding_data_is_the_source_data(self) -> None:
        raw = f.real_tasks_list_result(rows=2)

        result = normalize_tool_result("planner.tasks.list", raw)

        self.assertEqual(
            [task["title"] for task in result.data["tasks"]],
            ["Hacer las compras", "Tarea numero 1"],
        )


if __name__ == "__main__":
    unittest.main()
