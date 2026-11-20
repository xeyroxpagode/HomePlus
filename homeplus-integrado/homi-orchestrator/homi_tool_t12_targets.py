"""HOMI T12-3 — deterministic existing-task target resolution (Node D).

This module owns the MINIMAL deterministic resolution required to make
the four existing-task T12 WRITE tools proposeable:

    planner.tasks.update
    planner.tasks.complete
    planner.tasks.trash
    planner.tasks.restore

Hard boundaries (T12-3 sections 4, 8, 9, 10, 11, 12 and 13)
-----------------------------------------------------------
* EXACT resolution only. No fuzzy matching, no semantic similarity,
  no pronoun resolution, no conversation-memory inference and no
  guessing between multiple candidates.
* Allowed task targets:
  - an explicit canonical taskId (UUID, T12-2 pattern), or
  - an explicit task title that resolves to EXACTLY ONE canonical
    task of the trusted READ result.
* Zero matches -> clarify. Multiple matches -> clarify. Never
  arbitrarily select one.
* The only normalization is the harmless case/outer-whitespace fold
  already justified by the task-title resolver. Nothing else.
* Checklist identity is exact item text (same harmless normalization)
  or an explicit in-bounds index. Zero or multiple candidates clarify.
* The checklist transformation is a deterministic read-modify-write
  over the AUTHORITATIVE checklist of the trusted ``planner.tasks.get``
  result. The model NEVER supplies the full authoritative array.
* ``dueTime`` requires ``dueDate`` (Product Truth invariant). A
  time-only intent is merged with the authoritative existing due date;
  when no authoritative date exists the merge fails closed to a
  clarify instead of inventing a date.
* Clearing ``dueDate`` clears ``dueTime`` too when the authoritative
  task has a time (Product Truth invariant: a time without a date is
  invalid). Clearing ``dueTime`` alone never touches the date.

This module is inert: no HTTP, no HomePlus authentication, no tool
execution, no model call, no persistence. The trusted READ results are
injected by the loop (``homi_tool_loop``).
"""

from __future__ import annotations

import re
from typing import Any, Mapping


class TaskTargetError(ValueError):
    """Fail-closed error of the T12-3 deterministic target layer."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:

        super().__init__(
            f"{code}: {message}"
        )

        self.code = code
        self.message = message


# The canonical T12-2 UUID pattern (HomePlus plannerWriteTools.js,
# UUID_ONLY_PATTERN). Lowercase canonical form only: the model can not
# smuggle a non-canonical identifier through the target contract.
TASK_TARGET_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)

TASK_TARGET_KIND = "task"

TASK_TARGET_FIELDS = frozenset(
    {
        "kind",
        "task_id",
        "task_title",
    }
)

MAX_TASK_TITLE_TARGET_CHARS = 500

# The checklist intent operations of the T12-3 read-modify-write
# (T12-1 freeze section D + T12-3 sections 11-13).
CHECKLIST_OPS: tuple[str, ...] = (
    "add",
    "edit",
    "complete",
    "reopen",
    "remove",
)

CHECKLIST_PATCH_FIELDS = frozenset(
    {
        "op",
        "item",
        "newItemText",
        "index",
    }
)

MAX_CHECKLIST_ITEMS = 200

MAX_CHECKLIST_ITEM_CHARS = 500


def normalize_title(
    value: str,
) -> str:
    """The harmless normalization of the task-title resolver.

    Outer whitespace + case fold. Nothing else: no accent folding, no
    plural folding, no phonetics, no fuzzy distance.
    """

    return value.strip().casefold()


def validate_task_target(
    target: Any,
) -> tuple[str | None, str | None]:
    """Validate the additive v2 task-target contract.

    The accepted shape is exactly::

        {"kind": "task", "task_id": <uuid>|null, "task_title": <str>|null}

    Exactly one of ``task_id`` / ``task_title`` must be present. A
    ``task_id`` must match the canonical T12-2 UUID pattern; a
    ``task_title`` must be a non-empty bounded string. Anything else
    fails closed with a deterministic code.
    """

    if not isinstance(target, dict):
        raise TaskTargetError(
            "TASK_TARGET_INVALID",
            "target must be a JSON object",
        )

    unknown = sorted(
        key
        for key in target
        if key not in TASK_TARGET_FIELDS
    )

    if unknown:
        raise TaskTargetError(
            "TASK_TARGET_INVALID",
            "unknown target field(s): " + ", ".join(unknown),
        )

    if target.get("kind") != TASK_TARGET_KIND:
        raise TaskTargetError(
            "TASK_TARGET_INVALID",
            "target.kind must be 'task'",
        )

    task_id = target.get("task_id")
    task_title = target.get("task_title")

    if task_id is not None and task_title is not None:
        raise TaskTargetError(
            "TASK_TARGET_AMBIGUOUS",
            "exactly one of task_id or task_title must be given",
        )

    if task_id is None and task_title is None:
        raise TaskTargetError(
            "TASK_TARGET_EMPTY",
            "task_id or task_title is required",
        )

    if task_id is not None:
        if not isinstance(task_id, str) or (
            TASK_TARGET_UUID_PATTERN.match(task_id) is None
        ):
            raise TaskTargetError(
                "TASK_TARGET_ID_INVALID",
                "task_id must be a canonical lowercase UUID",
            )

    if task_title is not None:
        if not isinstance(task_title, str):
            raise TaskTargetError(
                "TASK_TARGET_TITLE_INVALID",
                "task_title must be a string",
            )

        if not task_title.strip():
            raise TaskTargetError(
                "TASK_TARGET_TITLE_INVALID",
                "task_title must be non-empty",
            )

        if len(task_title) > MAX_TASK_TITLE_TARGET_CHARS:
            raise TaskTargetError(
                "TASK_TARGET_TITLE_INVALID",
                "task_title is too long",
            )

    return task_id, task_title


def resolve_task_by_title(
    title: str,
    tasks: Any,
) -> Mapping[str, Any]:
    """Resolve one explicit title against the trusted task rows.

    Deterministic exact resolution over the authoritative
    ``planner.tasks.list`` result: the normalized title must match
    EXACTLY ONE visible task. Zero matches and multiple matches both
    fail closed to clarify. The task row is returned as-is (the
    trusted READ result is the authority; this function copies
    nothing and mutates nothing).
    """

    if not isinstance(tasks, list):
        raise TaskTargetError(
            "TASK_TARGET_READ_INVALID",
            "the trusted task list is malformed",
        )

    wanted = normalize_title(title)

    matches: list[Mapping[str, Any]] = []

    for row in tasks:
        if not isinstance(row, Mapping):
            continue

        row_title = row.get("title")

        if not isinstance(row_title, str):
            continue

        if normalize_title(row_title) == wanted:
            matches.append(row)

    if not matches:
        raise TaskTargetError(
            "TASK_TARGET_NOT_FOUND",
            "no visible task matches that exact title",
        )

    if len(matches) > 1:
        raise TaskTargetError(
            "TASK_TARGET_AMBIGUOUS",
            "multiple visible tasks match that exact title",
        )

    return matches[0]


def validate_checklist_patch(
    patch: Any,
) -> dict[str, Any]:
    """Validate the additive v2 checklist intent descriptor.

    The model expresses the checklist INTENT only; it never supplies
    the authoritative array. The accepted shape is::

        {"op": "add"|"edit"|"complete"|"reopen"|"remove",
         "item": <str>|null,          # exact item text (add: the new
                                      # item text; edit: the OLD text)
         "newItemText": <str>|null,   # edit only: the replacement text
         "index": <int>|null}         # explicit in-bounds index

    Exactly one of ``item`` / ``index`` identifies the target item
    (``add`` requires ``item`` = the new item text). ``newItemText``
    is valid only for ``edit``.
    """

    if not isinstance(patch, dict):
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "checklist_patch must be a JSON object",
        )

    unknown = sorted(
        key
        for key in patch
        if key not in CHECKLIST_PATCH_FIELDS
    )

    if unknown:
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "unknown checklist_patch field(s): "
            + ", ".join(unknown),
        )

    op = patch.get("op")

    if op not in CHECKLIST_OPS:
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "checklist_patch.op must be one of "
            + ", ".join(CHECKLIST_OPS),
        )

    item = patch.get("item")
    newItemText = patch.get("newItemText")
    index = patch.get("index")

    if item is not None and not isinstance(item, str):
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "checklist_patch.item must be a string",
        )

    if item is not None and len(item) > MAX_CHECKLIST_ITEM_CHARS:
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "checklist_patch.item is too long",
        )

    if newItemText is not None and not isinstance(
        newItemText,
        str,
    ):
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "checklist_patch.newItemText must be a string",
        )

    if index is not None and (
        not isinstance(index, int)
        or isinstance(index, bool)
        or index < 0
    ):
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "checklist_patch.index must be a non-negative integer",
        )

    if op == "add":
        if item is None or not item.strip():
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                "op add requires the new item text",
            )

        if index is not None or newItemText is not None:
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                "op add accepts only the new item text",
            )

    elif op == "edit":
        if newItemText is None or not newItemText.strip():
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                "op edit requires newItemText",
            )

        if len(newItemText) > MAX_CHECKLIST_ITEM_CHARS:
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                "checklist_patch.newItemText is too long",
            )

        if item is not None and not item.strip():
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                "op edit item text must be non-empty",
            )

        if item is None and index is None:
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                "op edit requires item or index",
            )

    else:
        if newItemText is not None:
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                f"op {op} does not accept newItemText",
            )

        if item is None and index is None:
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                f"op {op} requires item or index",
            )

        if item is not None and not item.strip():
            raise TaskTargetError(
                "CHECKLIST_PATCH_INVALID",
                f"op {op} item text must be non-empty",
            )

    if item is not None and index is not None:
        raise TaskTargetError(
            "CHECKLIST_PATCH_INVALID",
            "item and index are mutually exclusive",
        )

    return {
        "op": op,
        "item": item,
        "newItemText": newItemText,
        "index": index,
    }


def _authoritative_checklist(
    task: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """The canonical checklist array of the authoritative task row.

    Product Truth stores ``checklist`` as a JSONB array of
    ``{text, checked}``; null/absent is the empty list. The row is
    deep-copied so the trusted READ result is never mutated.
    """

    raw = task.get("checklist")

    if raw is None:
        return []

    if not isinstance(raw, list):
        raise TaskTargetError(
            "CHECKLIST_AUTHORITY_INVALID",
            "the authoritative checklist is malformed",
        )

    items: list[dict[str, Any]] = []

    for entry in raw:
        if not isinstance(entry, Mapping):
            raise TaskTargetError(
                "CHECKLIST_AUTHORITY_INVALID",
                "an authoritative checklist item is malformed",
            )

        text = entry.get("text")
        checked = entry.get("checked")

        if not isinstance(text, str) or not isinstance(
            checked,
            bool,
        ):
            raise TaskTargetError(
                "CHECKLIST_AUTHORITY_INVALID",
                "an authoritative checklist item is malformed",
            )

        items.append(
            {
                "text": text,
                "checked": checked,
            }
        )

    return items


def _resolve_checklist_index(
    items: list[dict[str, Any]],
    patch: Mapping[str, Any],
) -> int:
    """Deterministically resolve the intended checklist item index.

    Exact item text (harmless normalization only) must yield exactly
    one candidate; an explicit index must be in bounds. Zero matches,
    multiple matches and out-of-bounds indexes all fail closed to a
    clarify. Never the wrong item.
    """

    index = patch.get("index")

    if index is not None:
        if index >= len(items):
            raise TaskTargetError(
                "CHECKLIST_ITEM_NOT_FOUND",
                "the checklist index is out of bounds",
            )

        return int(index)

    item = patch.get("item")

    if patch.get("op") == "add":
        # For add, ``item`` is the new item text, not a lookup key.
        return -1

    wanted = normalize_title(item)

    candidates = [
        position
        for position, entry in enumerate(items)
        if normalize_title(entry["text"]) == wanted
    ]

    if not candidates:
        raise TaskTargetError(
            "CHECKLIST_ITEM_NOT_FOUND",
            "no checklist item matches that exact text",
        )

    if len(candidates) > 1:
        raise TaskTargetError(
            "CHECKLIST_ITEM_AMBIGUOUS",
            "multiple checklist items match that exact text",
        )

    return candidates[0]


def transform_checklist(
    task: Mapping[str, Any],
    patch: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """The deterministic checklist read-modify-write transform.

    ``task`` is the AUTHORITATIVE ``planner.tasks.get`` result; the
    returned value is the COMPLETE new checklist array for the
    ``planner.tasks.update`` proposal (whole-array replacement, T12-2
    contract). All unrelated entries and their order are preserved.

    ADD     -> append ``{text, checked: false}`` (Product Truth
               ordering semantics: array order).
    EDIT    -> change only the resolved item's text.
    COMPLETE-> set ``checked: true`` on the resolved item.
    REOPEN  -> set ``checked: false`` on the resolved item.
    REMOVE  -> remove only the resolved item.
    """

    normalized = validate_checklist_patch(patch)

    items = _authoritative_checklist(task)

    op = normalized["op"]

    if len(items) >= MAX_CHECKLIST_ITEMS and op == "add":
        raise TaskTargetError(
            "CHECKLIST_TOO_LARGE",
            "the checklist already holds the maximum number of items",
        )

    position = _resolve_checklist_index(
        items,
        normalized,
    )

    if op == "add":
        result = [
            dict(entry) for entry in items
        ]

        result.append(
            {
                "text": str(normalized["item"]),
                "checked": False,
            }
        )

        return result

    if op == "edit":
        result = [
            dict(entry) for entry in items
        ]

        result[position]["text"] = str(
            normalized["newItemText"]
        )

        return result

    if op == "complete":
        result = [
            dict(entry) for entry in items
        ]

        result[position]["checked"] = True

        return result

    if op == "reopen":
        result = [
            dict(entry) for entry in items
        ]

        result[position]["checked"] = False

        return result

    # remove
    return [
        dict(entry)
        for position_, entry in enumerate(items)
        if position_ != position
    ]


def merge_due_time_intent(
    patch: dict[str, Any],
    authoritative: Mapping[str, Any],
) -> dict[str, Any]:
    """The mandatory dueTime merge rule (T12-3 section 8).

    A time-only intent ("Poné 'X' a las 18") must keep the
    authoritative existing due date:

    * the patch carries ``dueTime`` WITHOUT any ``dueDate`` key and the
      authoritative ``due_date`` exists -> the canonical patch carries
      ``dueDate = <authoritative due_date>`` plus the requested
      ``dueTime``; the user-intended delta remains only the time;
    * the same time-only intent with NO authoritative ``due_date`` ->
      fail closed: no date is invented and the caller must clarify the
      date;
    * a patch that EXPLICITLY carries ``dueDate`` (value or null) is
      never silently re-dated here: an explicit ``dueDate = null`` with
      a non-null ``dueTime`` is a contradictory intent and stays for
      the strict final validation to reject (due_time_without_due_date).

    The patch is copied; the input is never mutated.
    """

    merged = dict(patch)

    if (
        "dueTime" in merged
        and merged.get("dueTime") is not None
        and "dueDate" not in merged
    ):
        current_date = authoritative.get("due_date")

        if not isinstance(current_date, str) or not current_date:
            raise TaskTargetError(
                "DUE_DATE_REQUIRED",
                "the task has no due date; a date is required to set "
                "a time",
            )

        merged["dueDate"] = current_date

    return merged


def apply_clear_date_invariant(
    patch: dict[str, Any],
    authoritative: Mapping[str, Any],
) -> dict[str, Any]:
    """The clear-date normalization (T12-3 section 9).

    Clearing ``dueDate`` (``dueDate = null``) while the authoritative
    task has a due time would leave an invalid date/time combination
    (Product Truth: ``due_time`` requires ``due_date``). The minimal
    deterministic canonical normalization therefore also clears
    ``dueTime``. The date-less result never carries a time.
    """

    merged = dict(patch)

    if merged.get("dueDate") is None and "dueDate" in merged:
        merged["dueTime"] = None

    return merged


def complete_preconditions(
    authoritative: Mapping[str, Any],
) -> None:
    """The deterministic complete preconditions (T12-3 section 14).

    Product Truth rejects (or makes no sense of) a completion proposal
    for states that can be deterministically detected from the
    authoritative READ:

    * ``status == completed`` / ``awaiting_verification`` /
      ``verified``: the task is already done -> clarify;
    * ``status == cancelled``: a cancelled task is not completable ->
      clarify;
    * ``requires_verification``: completion requires the evidence
      workflow (409 ``evidence_submission_required``), which is out
      of T12 -> clarify.

    Only a ``pending`` task may receive a complete proposal. The
    task-level reopen of a completed task does NOT exist in the T12
    catalog (Product Truth: NOT_SUPPORTED).
    """

    status = authoritative.get("status")

    if status != "pending":
        raise TaskTargetError(
            "COMPLETE_PRECONDITION_FAILED",
            f"the task status is {status!r}, not 'pending'",
        )

    if authoritative.get("requires_verification") is True:
        raise TaskTargetError(
            "COMPLETE_PRECONDITION_FAILED",
            "the task requires the evidence workflow before "
            "completion",
        )


def restore_preconditions(
    authoritative: Mapping[str, Any],
) -> None:
    """The deterministic restore preconditions (T12-3 section 16).

    ``planner.tasks.restore`` is strictly the trash/restore lifecycle:
    the authoritative task must actually be trashed. A visible,
    operational task is NOT in the trash -> clarify. (An invisible
    task can not be resolved through the frozen READ surface at all;
    the caller clarifies before reaching here.)
    """

    trashed_at = authoritative.get("trashed_at")

    if not isinstance(trashed_at, str) or not trashed_at:
        raise TaskTargetError(
            "RESTORE_PRECONDITION_FAILED",
            "the task is not in the trash",
        )


__all__ = [
    "CHECKLIST_OPS",
    "CHECKLIST_PATCH_FIELDS",
    "MAX_CHECKLIST_ITEM_CHARS",
    "MAX_CHECKLIST_ITEMS",
    "MAX_TASK_TITLE_TARGET_CHARS",
    "TASK_TARGET_FIELDS",
    "TASK_TARGET_KIND",
    "TASK_TARGET_UUID_PATTERN",
    "TaskTargetError",
    "apply_clear_date_invariant",
    "complete_preconditions",
    "merge_due_time_intent",
    "normalize_title",
    "resolve_task_by_title",
    "restore_preconditions",
    "transform_checklist",
    "validate_checklist_patch",
    "validate_task_target",
]
