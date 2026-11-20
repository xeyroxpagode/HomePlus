"""HOMI T12-3 — deterministic target resolver unit tests (Node D).

Pure-logic coverage of ``homi_tool_t12_targets`` (task matrix sections
4, 8, 9, 11, 12, 13, 14 and 16): the existing-task target contract,
the exact title resolution, the checklist intent validation and
read-modify-write transform, the dueTime merge rule, the clear-date
invariant, the complete preconditions and the restore preconditions.

No HTTP, no executor, no Node A: every trusted READ result is an
injected fixture.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ORCHESTRATOR_ROOT = Path(
    __file__).resolve().parent.parent

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

import homi_tool_t12_targets as targets  # noqa: E402


TASK_ID = (
    "dd93db9c-4ac6-4e64-a069-63ded69b25e4"
)

OTHER_ID = (
    "11111111-2222-3333-4444-555555555555"
)


def task_row(
    **overrides,
):
    row = {
        "id": TASK_ID,
        "title": "Comprar materiales",
        "description": None,
        "status": "pending",
        "due_date": "2026-10-30",
        "due_time": None,
        "checklist": [],
        "version": 3,
        "trashed_at": None,
        "requires_verification": False,
        "assigned_to_member_id": None,
    }

    row.update(overrides)

    return row


def expect_error(
    code: str,
    callable_,
    *args,
    **kwargs,
):
    try:
        callable_(*args, **kwargs)
    except targets.TaskTargetError as error:
        return error.code
    raise AssertionError(
        f"expected TaskTargetError {code}; nothing was raised"
    )


class TaskTargetContractTests(unittest.TestCase):
    """The additive v2 target contract (section 3)."""

    def test_valid_explicit_task_id(self) -> None:
        task_id, task_title = targets.validate_task_target(
            {
                "kind": "task",
                "task_id": TASK_ID,
                "task_title": None,
            },
        )

        self.assertEqual(task_id, TASK_ID)
        self.assertIsNone(task_title)

    def test_valid_explicit_task_title(self) -> None:
        task_id, task_title = targets.validate_task_target(
            {
                "kind": "task",
                "task_id": None,
                "task_title": "Comprar materiales",
            },
        )

        self.assertIsNone(task_id)
        self.assertEqual(task_title, "Comprar materiales")

    def test_both_id_and_title_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_AMBIGUOUS",
                targets.validate_task_target,
                {
                    "kind": "task",
                    "task_id": TASK_ID,
                    "task_title": "Comprar materiales",
                },
            ),
            "TASK_TARGET_AMBIGUOUS",
        )

    def test_neither_id_nor_title_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_EMPTY",
                targets.validate_task_target,
                {
                    "kind": "task",
                    "task_id": None,
                    "task_title": None,
                },
            ),
            "TASK_TARGET_EMPTY",
        )

    def test_uppercase_or_non_canonical_uuid_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_ID_INVALID",
                targets.validate_task_target,
                {
                    "kind": "task",
                    "task_id": TASK_ID.upper(),
                    "task_title": None,
                },
            ),
            "TASK_TARGET_ID_INVALID",
        )

    def test_non_task_kind_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_INVALID",
                targets.validate_task_target,
                {
                    "kind": "event",
                    "task_id": TASK_ID,
                    "task_title": None,
                },
            ),
            "TASK_TARGET_INVALID",
        )

    def test_unknown_target_field_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_INVALID",
                targets.validate_task_target,
                {
                    "kind": "task",
                    "task_id": TASK_ID,
                    "task_title": None,
                    "expectedVersion": 3,
                },
            ),
            "TASK_TARGET_INVALID",
        )

    def test_blank_title_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_TITLE_INVALID",
                targets.validate_task_target,
                {
                    "kind": "task",
                    "task_id": None,
                    "task_title": "   ",
                },
            ),
            "TASK_TARGET_TITLE_INVALID",
        )

    def test_non_object_target_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_INVALID",
                targets.validate_task_target,
                "Comprar materiales",
            ),
            "TASK_TARGET_INVALID",
        )


class TitleResolutionTests(unittest.TestCase):
    """The exact deterministic title resolution (section 4)."""

    def test_unique_exact_title_resolves(self) -> None:
        row = targets.resolve_task_by_title(
            "Comprar materiales",
            [
                task_row(),
                task_row(
                    id=OTHER_ID,
                    title="Otra cosa",
                ),
            ],
        )

        self.assertEqual(row["id"], TASK_ID)

    def test_case_and_outer_whitespace_are_harmless(self) -> None:
        row = targets.resolve_task_by_title(
            "  comprar MATERIALES  ",
            [task_row()],
        )

        self.assertEqual(row["id"], TASK_ID)

    def test_zero_matches_clarifies(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_NOT_FOUND",
                targets.resolve_task_by_title,
                "Comprar cartulina",
                [task_row()],
            ),
            "TASK_TARGET_NOT_FOUND",
        )

    def test_multiple_matches_clarify(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_AMBIGUOUS",
                targets.resolve_task_by_title,
                "Comprar materiales",
                [
                    task_row(),
                    task_row(id=OTHER_ID),
                ],
            ),
            "TASK_TARGET_AMBIGUOUS",
        )

    def test_partial_matches_never_resolve(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_NOT_FOUND",
                targets.resolve_task_by_title,
                "Comprar",
                [task_row()],
            ),
            "TASK_TARGET_NOT_FOUND",
        )

    def test_malformed_read_result_fails_closed(self) -> None:
        self.assertEqual(
            expect_error(
                "TASK_TARGET_READ_INVALID",
                targets.resolve_task_by_title,
                "Comprar materiales",
                {"tasks": []},
            ),
            "TASK_TARGET_READ_INVALID",
        )


class ChecklistPatchValidationTests(unittest.TestCase):
    """The checklist intent contract (sections 11-12)."""

    def test_add_requires_the_new_item_text(self) -> None:
        normalized = targets.validate_checklist_patch(
            {"op": "add", "item": "Comprar cartulina"},
        )

        self.assertEqual(normalized["op"], "add")
        self.assertEqual(
            normalized["item"],
            "Comprar cartulina",
        )

    def test_add_without_item_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "CHECKLIST_PATCH_INVALID",
                targets.validate_checklist_patch,
                {"op": "add"},
            ),
            "CHECKLIST_PATCH_INVALID",
        )

    def test_edit_requires_new_item_text(self) -> None:
        self.assertEqual(
            expect_error(
                "CHECKLIST_PATCH_INVALID",
                targets.validate_checklist_patch,
                {
                    "op": "edit",
                    "item": "Comprar cartulina",
                },
            ),
            "CHECKLIST_PATCH_INVALID",
        )

    def test_edit_with_item_and_new_text_is_valid(self) -> None:
        normalized = targets.validate_checklist_patch(
            {
                "op": "edit",
                "item": "Comprar cartulina",
                "newItemText": "Comprar cartulina gruesa",
            },
        )

        self.assertEqual(
            normalized["newItemText"],
            "Comprar cartulina gruesa",
        )

    def test_unknown_op_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "CHECKLIST_PATCH_INVALID",
                targets.validate_checklist_patch,
                {"op": "clear", "item": "x"},
            ),
            "CHECKLIST_PATCH_INVALID",
        )

    def test_item_and_index_are_mutually_exclusive(self) -> None:
        self.assertEqual(
            expect_error(
                "CHECKLIST_PATCH_INVALID",
                targets.validate_checklist_patch,
                {
                    "op": "complete",
                    "item": "x",
                    "index": 0,
                },
            ),
            "CHECKLIST_PATCH_INVALID",
        )

    def test_unknown_patch_field_is_rejected(self) -> None:
        self.assertEqual(
            expect_error(
                "CHECKLIST_PATCH_INVALID",
                targets.validate_checklist_patch,
                {
                    "op": "remove",
                    "item": "x",
                    "whole_array": [],
                },
            ),
            "CHECKLIST_PATCH_INVALID",
        )


class ChecklistTransformTests(unittest.TestCase):
    """The deterministic read-modify-write (sections 11-13)."""

    CHECKLIST = [
        {"text": "Comprar cartulina", "checked": False},
        {"text": "Cortar la cartulina", "checked": True},
        {"text": "Pegar la maqueta", "checked": False},
    ]

    def task(self) -> dict:
        return task_row(
            checklist=[
                dict(entry) for entry in self.CHECKLIST
            ],
        )

    def test_add_appends_unchecked_at_the_end(self) -> None:
        result = targets.transform_checklist(
            self.task(),
            {"op": "add", "item": "Comprar pegamento"},
        )

        self.assertEqual(
            result,
            self.CHECKLIST
            + [
                {
                    "text": "Comprar pegamento",
                    "checked": False,
                }
            ],
        )

    def test_edit_changes_only_the_intended_text(self) -> None:
        result = targets.transform_checklist(
            self.task(),
            {
                "op": "edit",
                "item": "Comprar cartulina",
                "newItemText": "Comprar cartulina gruesa",
            },
        )

        self.assertEqual(
            result[0],
            {
                "text": "Comprar cartulina gruesa",
                "checked": False,
            },
        )

        self.assertEqual(result[1], self.CHECKLIST[1])
        self.assertEqual(result[2], self.CHECKLIST[2])

    def test_complete_sets_checked_true(self) -> None:
        result = targets.transform_checklist(
            self.task(),
            {"op": "complete", "item": "Pegar la maqueta"},
        )

        self.assertTrue(result[2]["checked"])
        self.assertFalse(result[0]["checked"])
        self.assertTrue(result[1]["checked"])

    def test_reopen_sets_checked_false(self) -> None:
        result = targets.transform_checklist(
            self.task(),
            {"op": "reopen", "item": "Cortar la cartulina"},
        )

        self.assertFalse(result[1]["checked"])

    def test_remove_deletes_only_the_resolved_item(self) -> None:
        result = targets.transform_checklist(
            self.task(),
            {"op": "remove", "item": "Cortar la cartulina"},
        )

        self.assertEqual(
            result,
            [
                self.CHECKLIST[0],
                self.CHECKLIST[2],
            ],
        )

    def test_explicit_index_resolves_deterministically(self) -> None:
        result = targets.transform_checklist(
            self.task(),
            {"op": "complete", "index": 2},
        )

        self.assertTrue(result[2]["checked"])

    def test_out_of_bounds_index_clarifies(self) -> None:
        self.assertEqual(
            expect_error(
                "CHECKLIST_ITEM_NOT_FOUND",
                targets.transform_checklist,
                self.task(),
                {"op": "remove", "index": 9},
            ),
            "CHECKLIST_ITEM_NOT_FOUND",
        )

    def test_zero_text_matches_clarify(self) -> None:
        self.assertEqual(
            expect_error(
                "CHECKLIST_ITEM_NOT_FOUND",
                targets.transform_checklist,
                self.task(),
                {"op": "complete", "item": "Pintar la maqueta"},
            ),
            "CHECKLIST_ITEM_NOT_FOUND",
        )

    def test_duplicate_text_matches_clarify(self) -> None:
        task = task_row(
            checklist=[
                {"text": "Comprar cartulina", "checked": False},
                {"text": "comprar cartulina", "checked": True},
            ],
        )

        self.assertEqual(
            expect_error(
                "CHECKLIST_ITEM_AMBIGUOUS",
                targets.transform_checklist,
                task,
                {"op": "remove", "item": "Comprar Cartulina"},
            ),
            "CHECKLIST_ITEM_AMBIGUOUS",
        )

    def test_order_of_unrelated_items_is_preserved(self) -> None:
        result = targets.transform_checklist(
            self.task(),
            {"op": "add", "item": "Comprar pegamento"},
        )

        self.assertEqual(
            [entry["text"] for entry in result],
            [
                "Comprar cartulina",
                "Cortar la cartulina",
                "Pegar la maqueta",
                "Comprar pegamento",
            ],
        )

    def test_authoritative_row_is_never_mutated(self) -> None:
        task = self.task()

        before = [dict(e) for e in task["checklist"]]

        targets.transform_checklist(
            task,
            {"op": "remove", "item": "Pegar la maqueta"},
        )

        self.assertEqual(
            [dict(e) for e in task["checklist"]],
            before,
        )


class DueTimeMergeTests(unittest.TestCase):
    """The mandatory dueTime merge rule (section 8)."""

    def test_time_only_intent_merges_the_authoritative_date(
        self,
    ) -> None:
        merged = targets.merge_due_time_intent(
            {"dueTime": "18:00"},
            task_row(due_date="2026-10-30"),
        )

        self.assertEqual(
            merged,
            {
                "dueTime": "18:00",
                "dueDate": "2026-10-30",
            },
        )

    def test_time_only_intent_without_a_date_fails_closed(
        self,
    ) -> None:
        self.assertEqual(
            expect_error(
                "DUE_DATE_REQUIRED",
                targets.merge_due_time_intent,
                {"dueTime": "18:00"},
                task_row(due_date=None),
            ),
            "DUE_DATE_REQUIRED",
        )

    def test_explicit_null_due_date_is_never_silently_re_dated(
        self,
    ) -> None:
        merged = targets.merge_due_time_intent(
            {"dueDate": None, "dueTime": "18:00"},
            task_row(due_date="2026-10-30"),
        )

        self.assertEqual(
            merged,
            {"dueDate": None, "dueTime": "18:00"},
        )

    def test_date_and_time_intent_passes_through(self) -> None:
        merged = targets.merge_due_time_intent(
            {"dueDate": "2026-10-31", "dueTime": "09:30"},
            task_row(due_date="2026-10-30"),
        )

        self.assertEqual(
            merged,
            {"dueDate": "2026-10-31", "dueTime": "09:30"},
        )

    def test_input_patch_is_never_mutated(self) -> None:
        patch = {"dueTime": "18:00"}

        targets.merge_due_time_intent(
            patch,
            task_row(due_date="2026-10-30"),
        )

        self.assertEqual(patch, {"dueTime": "18:00"})


class ClearDateInvariantTests(unittest.TestCase):
    """The clear-date/clear-time normalization (section 9)."""

    def test_clearing_the_date_also_clears_the_time(self) -> None:
        merged = targets.apply_clear_date_invariant(
            {"dueDate": None},
            task_row(
                due_date="2026-10-30",
                due_time="18:00:00",
            ),
        )

        self.assertEqual(
            merged,
            {"dueDate": None, "dueTime": None},
        )

    def test_clearing_only_the_time_never_touches_the_date(
        self,
    ) -> None:
        merged = targets.apply_clear_date_invariant(
            {"dueTime": None},
            task_row(
                due_date="2026-10-30",
                due_time="18:00:00",
            ),
        )

        self.assertEqual(merged, {"dueTime": None})

    def test_absent_due_date_is_untouched(self) -> None:
        merged = targets.apply_clear_date_invariant(
            {"dueTime": "18:00"},
            task_row(due_date="2026-10-30"),
        )

        self.assertEqual(merged, {"dueTime": "18:00"})


class CompletePreconditionTests(unittest.TestCase):
    """The deterministic complete preconditions (section 14)."""

    def test_pending_task_without_evidence_passes(self) -> None:
        targets.complete_preconditions(
            task_row(status="pending"),
        )

    def test_completed_task_clarifies(self) -> None:
        self.assertEqual(
            expect_error(
                "COMPLETE_PRECONDITION_FAILED",
                targets.complete_preconditions,
                task_row(status="completed"),
            ),
            "COMPLETE_PRECONDITION_FAILED",
        )

    def test_awaiting_verification_task_clarifies(self) -> None:
        self.assertEqual(
            expect_error(
                "COMPLETE_PRECONDITION_FAILED",
                targets.complete_preconditions,
                task_row(status="awaiting_verification"),
            ),
            "COMPLETE_PRECONDITION_FAILED",
        )

    def test_cancelled_task_clarifies(self) -> None:
        self.assertEqual(
            expect_error(
                "COMPLETE_PRECONDITION_FAILED",
                targets.complete_preconditions,
                task_row(status="cancelled"),
            ),
            "COMPLETE_PRECONDITION_FAILED",
        )

    def test_evidence_required_task_clarifies(self) -> None:
        self.assertEqual(
            expect_error(
                "COMPLETE_PRECONDITION_FAILED",
                targets.complete_preconditions,
                task_row(requires_verification=True),
            ),
            "COMPLETE_PRECONDITION_FAILED",
        )


class RestorePreconditionTests(unittest.TestCase):
    """The deterministic restore preconditions (section 16)."""

    def test_trashed_task_passes(self) -> None:
        targets.restore_preconditions(
            task_row(
                trashed_at="2026-10-25T10:00:00+00:00",
            ),
        )

    def test_operational_task_clarifies(self) -> None:
        self.assertEqual(
            expect_error(
                "RESTORE_PRECONDITION_FAILED",
                targets.restore_preconditions,
                task_row(trashed_at=None),
            ),
            "RESTORE_PRECONDITION_FAILED",
        )


if __name__ == "__main__":
    unittest.main()
