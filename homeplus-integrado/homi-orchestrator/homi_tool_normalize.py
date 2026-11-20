"""HOMI T09-F — tool result normalization (Node D).

This module turns ONE successful T07 READ result into the bounded,
safe, model facing ``ToolResultV1``.

Design rules
------------

* **Inert.** The module performs no HTTP call, no model call and no
  authentication. It never reads a credential and never opens a socket.
* **Positive projection.** Every tool has its own allow-list of the
  fields that may reach the model. The projection is built from the
  REAL T07 outputs of the eight canonical READ tools, not from a
  guess: the raw T07 rows of ``planner_tasks`` and ``planner_events``
  are ``select('*')`` rows and therefore carry the household id, the
  member foreign keys, the person foreign keys, the hydrated member
  objects, the origin columns, the responsibility columns and the
  optimistic-locking version.
* **Defense in depth.** A recursive strip of the internal/identity/
  auth keys runs after the projection. It must never have to remove
  anything: the projection already excludes them. The strip exists so
  that a future T07 column cannot leak by accident. It also removes
  every URL/transport CONTROL key, so a transport target can never
  reach the model.
* **URL content is data.** A URL inside an approved free text field
  (a task title, a task description, an event title, an event
  description, a location name) is inert user data. It is not a
  transport target, not an endpoint, not a tool argument and not an
  instruction to fetch anything. The module never fetches it, never
  follows it and never turns it into an execution. The guarantee is
  the POSITION of the URL (its key), never its spelling and never its
  domain, so an ordinary household link never aborts a valid READ.
* **Bounded.** Item counts, string lengths and the total serialized
  payload are bounded. The reduction is deterministic and always ends
  with a VALID JSON document: the module never slices serialized
  bytes.
* **Structured facts over narrative.** Where the source exposes the
  same fact both structurally and as pre-rendered free text, only the
  structured form reaches the model. A narrative whose scope differs
  from the structured facts of the same turn is a source of false
  claims, not a source of information.
* **Honest metadata.** ``truncated`` is true only when something was
  really removed or shortened. ``total_count`` is preserved only when
  the source exposes a total. An empty result is represented as an
  empty result, never as an invented one.

The module is the ONLY place where a raw T07 payload is turned into
something that may be sent to Node A.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The version of the internal model facing tool result shape.
TOOL_RESULT_VERSION = "1.0"

# The only status a normalized result can carry: the normalizer is
# only ever applied to a SUCCESSFUL tool execution.
TOOL_STATUS_SUCCESS = "SUCCESS"

from homi_tool_catalog import T24_READ_TOOL_IDS  # noqa: E402

# Exact output key names of the T24-I1 multidomain READ tools that are
# legitimate but collide with internal/auth key patterns. They are preserved
# only for the nine T24 READ tools.
T24_PRESERVE_KEYS: frozenset[str] = frozenset({"display_name", "role"})

# The hard model facing payload target, in serialized bytes.
MAX_TOOL_RESULT_BYTES = 16 * 1024


# ---------------------------------------------------------------------------
# Per tool item caps (T09-F section 4)
# ---------------------------------------------------------------------------

MAX_TASKS_LIST_ITEMS = 20

MAX_EVENTS_LIST_ITEMS = 20

MAX_CALENDAR_ITEMS = 30

MAX_ATTENTION_ITEMS = 20

MAX_SEARCH_RESULTS_PER_GROUP = 10

MAX_SEARCH_GROUPS = 3

# planner.summary.get is already bounded by the service
# (3 tasks, 3 events, 1 goal): no additional item cap is applied.


# ---------------------------------------------------------------------------
# String caps (T09-F section 4)
# ---------------------------------------------------------------------------

MAX_TITLE_CHARS = 200

MAX_DESCRIPTION_CHARS = 500

MAX_SUMMARY_CHARS = 300

MAX_FREE_TEXT_CHARS = 200

# The cap of every free-text field that has no explicit cap.
STRING_LIMITS: dict[str, int] = {
    "title": MAX_TITLE_CHARS,
    "description": MAX_DESCRIPTION_CHARS,
    "summary": MAX_SUMMARY_CHARS,
    "reason": MAX_SUMMARY_CHARS,
    "subtitle": MAX_FREE_TEXT_CHARS,
    "location_name": MAX_FREE_TEXT_CHARS,
    "label": MAX_FREE_TEXT_CHARS,
    "category": MAX_FREE_TEXT_CHARS,
    "unit": MAX_FREE_TEXT_CHARS,
    "recurrence": 64,
    "status": 64,
    "priority": 64,
    "severity": 64,
    "entityType": 64,
    "type": 64,
    "lifecycle": 64,
    "scope": 64,
    "visibility": 64,
    "progress_mode": 64,
    "target_type": 64,
    "context": 64,
    "projectionVersion": 64,
    "projection_version": 64,
}


# ---------------------------------------------------------------------------
# Per tool field allow-lists (the positive projection)
# ---------------------------------------------------------------------------

# The Planner task fields that may reach the model.
#
# EXCLUDED on purpose: household_id, assigned_to_member_id,
# created_by_member_id, created_by_person_id, completed_by_member_id,
# completed_by_person_id, verified_by_member_id, verified_by_person_id,
# trashed_by_member_id, cancelled_by_member_id, assigned_member,
# completed_member, verified_member, version, template_key, trashed_at,
# cancelled_at, cancelled_reason, cancelled_from_status, checklist,
# origin_*, goal_id, responsibility_*, plan_classification,
# estimated_duration_minutes.
TASK_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "description",
    "status",
    "priority",
    "category",
    "due_date",
    "due_time",
    "requires_verification",
    "created_at",
    "updated_at",
    "archived_at",
)

# The Planner event fields that may reach the model.
#
# EXCLUDED on purpose: household_id, created_by_member_id,
# created_by_person_id, version, trashed_at.
EVENT_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "description",
    "status",
    "starts_at",
    "ends_at",
    "all_day",
    "location_name",
    "recurrence",
    "created_at",
    "updated_at",
)

# The Planner calendar occurrence fields that may reach the model.
#
# EXCLUDED on purpose: occurrence_id, is_recurring_occurrence,
# is_override, parent_event_id, original_occurrence_start_at.
CALENDAR_ITEM_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "description",
    "status",
    "starts_at",
    "ends_at",
    "all_day",
    "location_name",
    "recurrence",
    "type",
)

# The Planner attention item fields that may reach the model.
#
# EXCLUDED on purpose: attentionId, dedupeKey.
ATTENTION_ITEM_FIELDS: tuple[str, ...] = (
    "entityType",
    "entityId",
    "title",
    "summary",
    "reason",
    "severity",
    "priorityScore",
    "unresolved",
    "createdAt",
    "updatedAt",
)

# The Planner search result fields that may reach the model.
#
# EXCLUDED on purpose: id (a composite "<type>:<uuid>" key),
# destination (an internal navigation descriptor).
SEARCH_RESULT_FIELDS: tuple[str, ...] = (
    "entityType",
    "entityId",
    "title",
    "subtitle",
    "updatedAt",
)

# The search metadata keys that may reach the model.
SEARCH_METADATA_FIELDS: tuple[str, ...] = (
    "status",
    "dueDate",
    "dueTime",
    "priority",
    "startsAt",
    "endsAt",
    "allDay",
    "locationName",
    "lifecycle",
    "scope",
    "targetDate",
    "archived",
)

# The Planner summary task fields that may reach the model.
SUMMARY_TASK_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "status",
    "priority",
    "category",
    "due_date",
    "due_time",
    "requires_verification",
)

# The Planner summary goal fields that may reach the model.
SUMMARY_GOAL_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "category",
    "visibility",
    "progress_mode",
    "target_type",
    "target_value",
    "current_value",
    "unit",
    "progress_percentage",
    "status",
    "starts_at",
    "ends_at",
)


# ---------------------------------------------------------------------------
# The internal / identity / auth keys that must never reach the model
# ---------------------------------------------------------------------------

# The URL / transport CONTROL keys.
#
# A URL in one of these positions is a TRANSPORT TARGET: it is an
# implementation detail of the HomePlus runtime. It is never data and
# it never reaches the model.
#
# A URL that lives inside an approved free text DATA field (a task
# title, a task description, an event title, an event description, a
# location name) is DATA: it is inert, it is never fetched, it never
# becomes a tool argument and it never becomes an execution. The
# distinction is the POSITION of the URL, never its spelling and never
# its domain.
#
# Normalized (lowercase, alphanumeric only) key names.
CONTROL_URL_KEYS: frozenset[str] = frozenset(
    {
        "url",
        "urls",
        "uri",
        "uris",
        "href",
        "link",
        "links",
        "endpoint",
        "endpoints",
        "host",
        "hosts",
        "hostname",
        "baseurl",
        "apibaseurl",
        "publicurl",
        "weburl",
        "permalink",
        "deeplink",
        "callbackurl",
        "redirecturl",
        "redirecturi",
        "requesturl",
        "downloadurl",
        "imageurl",
        "fileurl",
        "thumburl",
        "avatarurl",
        "signedurl",
        "presignedurl",
        "proxyurl",
        "webhook",
        "webhookurl",
        "toolurl",
        "homeplusurl",
        "homeplusbaseurl",
        "destination",
        "surfaceorigin",
    }
)


# Normalized (lowercase, alphanumeric only) key names.
FORBIDDEN_INTERNAL_KEYS: frozenset[str] = frozenset(
    {
        # identity and membership
        "actorid",
        "householdid",
        "householdids",
        "membershipid",
        "membershipids",
        "authuserid",
        "personid",
        "personids",
        "memberid",
        "memberids",
        "assignedtomemberid",
        "createdbymemberid",
        "completedbymemberid",
        "verifiedbymemberid",
        "trashedbymemberid",
        "cancelledbymemberid",
        "createdbypersonid",
        "completedbypersonid",
        "verifiedbypersonid",
        "assignedmember",
        "completedmember",
        "verifiedmember",
        "role",
        "roles",
        # credentials and transport
        "token",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "jwt",
        "authorization",
        "bearer",
        "password",
        "secret",
        "apikey",
        "cookie",
        "setcookie",
        "session",
        "url",
        "endpoint",
        "host",
        "signedurl",
        "presignedurl",
        "signature",
        "requestid",
        "sql",
        "querysql",
        # database implementation fields
        "version",
        "templatekey",
        "trashedat",
        "cancelledat",
        "cancelledreason",
        "cancelledfromstatus",
        "checklist",
        "originmodule",
        "originentitytype",
        "originentityid",
        "originreason",
        "goalid",
        "responsibilityid",
        "responsibilityoccurrencesequence",
        "planclassification",
        "estimateddurationminutes",
        "partialerrors",
        "dedupekey",
        "attentionid",
        "occurrenceid",
        "isoverride",
        "isrecurringoccurrence",
        "parenteventid",
        "originaloccurrencestartat",
        "surfaceorigin",
        "destination",
        "avatarurl",
        "displayname",
    }
) | CONTROL_URL_KEYS


def _normalized_key(key: str) -> str:
    """The normalized form of an object key."""

    return re.sub(
        r"[^a-z0-9]",
        "",
        key.lower(),
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolNormalizationError(RuntimeError):
    """Fail-closed error raised by the T09-F normalizer."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(f"{code}: {message}")

        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# The model facing shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolResultMeta:
    """The honest metadata of one normalized result."""

    truncated: bool = False
    returned_count: int | None = None
    total_count: int | None = None
    omitted_count: int | None = None
    truncation_reason: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "truncated": bool(self.truncated),
            "returned_count": self.returned_count,
            "total_count": self.total_count,
            "omitted_count": self.omitted_count,
            "truncation_reason": self.truncation_reason,
        }


@dataclass(frozen=True)
class ToolResultV1:
    """The internal model facing tool result, version 1.

    It carries factual data only: it is a projection of the result of
    ONE T07 invocation. It never carries a credential, an identity
    authority or a transport target. A URL that lives inside an
    approved free text field IS carried, as the inert data it is.
    """

    tool_id: str
    status: str
    data: dict[str, Any]
    meta: ToolResultMeta = ToolResultMeta()

    def to_payload(self) -> dict[str, Any]:
        """The exact model facing dictionary."""

        return {
            "tool_id": self.tool_id,
            "status": self.status,
            "data": self.data,
            "meta": self.meta.to_payload(),
        }


# ---------------------------------------------------------------------------
# Canonical serialization
# ---------------------------------------------------------------------------


def canonical_serialization(payload: Any) -> str:
    """The canonical JSON serialization of a normalized payload.

    UTF-8 JSON, sorted keys, no ASCII escaping, compact separators.
    The same payload always produces the same text.
    """

    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def canonical_size(payload: Any) -> int:
    """The serialized size, in bytes, of a normalized payload."""

    return len(
        canonical_serialization(payload).encode("utf-8")
    )


# The worst case metadata used while the byte budget is enforced. The
# real metadata is never larger than this one.
_WORST_CASE_META: dict[str, Any] = {
    "truncated": True,
    "returned_count": 999999,
    "total_count": 999999,
    "omitted_count": 999999,
    "truncation_reason": "byte_cap_reduction",
}


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _is_json_scalar(value: Any) -> bool:
    """Whether a value is a JSON scalar that can be forwarded."""

    if value is None or isinstance(value, (str, bool, int)):
        return True

    if isinstance(value, float):
        return (
            value == value
            and value not in (float("inf"), float("-inf"))
        )

    return False


def _cap_string(
    name: str | None,
    value: str,
    limits: Mapping[str, int] | None = None,
) -> tuple[str, bool]:
    """Cap one string. Returns (value, changed)."""

    table = STRING_LIMITS if limits is None else limits

    limit = (
        table.get(name, MAX_FREE_TEXT_CHARS)
        if name is not None
        else MAX_FREE_TEXT_CHARS
    )

    if len(value) <= limit:
        return value, False

    # The cut happens on a character boundary, so the JSON document
    # stays valid and the text stays readable.
    return value[:limit], True


def _recap(
    node: Any,
    limits: Mapping[str, int],
) -> bool:
    """Re-apply the string caps to an already projected structure.

    Returns whether any string was shortened.
    """

    changed = False

    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str):
                capped, was_changed = _cap_string(
                    key,
                    value,
                    limits,
                )

                node[key] = capped

                changed = changed or was_changed

            else:
                changed = _recap(value, limits) or changed

    elif isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, str):
                capped, was_changed = _cap_string(
                    None,
                    item,
                    limits,
                )

                node[index] = capped

                changed = changed or was_changed

            else:
                changed = _recap(item, limits) or changed

    return changed


def _project_fields(
    raw: Mapping[str, Any],
    fields: Sequence[str],
) -> tuple[dict[str, Any], bool]:
    """Copy the allowed fields of one raw object.

    Only JSON scalars are copied. A string is capped. Returns the
    projection and whether anything was shortened.
    """

    projected: dict[str, Any] = {}

    shortened = False

    for name in fields:
        if name not in raw:
            continue

        value = raw[name]

        if not _is_json_scalar(value):
            continue

        if isinstance(value, str):
            value, changed = _cap_string(name, value)

            shortened = shortened or changed

        projected[name] = value

    return projected, shortened


def strip_internal_keys(
    node: Any,
    preserve_keys: frozenset[str] | None = None,
) -> Any:
    """Recursively remove the internal, identity and auth keys.

    The positive projection already excludes them. This strip is the
    defense in depth of the last line: a new T07 column can never
    reach the model by accident.

    ``preserve_keys`` optionally lists exact key names that must never be
    removed even when they match a forbidden internal pattern. This is
    used by T24-I1 multidomain READ tools whose output fields (for example
    ``display_name`` or ``role``) legitimately collide with internal key
    patterns.
    """

    if isinstance(node, dict):
        cleaned: dict[str, Any] = {}

        for key, value in node.items():
            if not isinstance(key, str):
                continue

            if _normalized_key(key) in FORBIDDEN_INTERNAL_KEYS:
                if preserve_keys is not None and key in preserve_keys:
                    cleaned[key] = strip_internal_keys(value, preserve_keys)
                else:
                    continue

            cleaned[key] = strip_internal_keys(value, preserve_keys)

        return cleaned

    if isinstance(node, list):
        return [strip_internal_keys(item, preserve_keys) for item in node]

    return node


def forbidden_keys_in(node: Any) -> list[str]:
    """The internal, identity or auth keys reachable inside a node."""

    found: set[str] = set()

    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                continue

            if _normalized_key(key) in FORBIDDEN_INTERNAL_KEYS:
                found.add(key)

            found.update(forbidden_keys_in(value))

    elif isinstance(node, list):
        for item in node:
            found.update(forbidden_keys_in(item))

    return sorted(found)


def control_url_keys_in(node: Any) -> list[str]:
    """The URL / transport CONTROL keys reachable inside a node.

    These are the positions where a URL is a transport target instead
    of data. The recursive strip removes them and the safety gate
    rejects them. A URL that lives inside an approved free text field
    is NOT reachable here: it is a VALUE, not a key.
    """

    found: set[str] = set()

    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                continue

            if _normalized_key(key) in CONTROL_URL_KEYS:
                found.add(key)

            found.update(control_url_keys_in(value))

    elif isinstance(node, list):
        for item in node:
            found.update(control_url_keys_in(item))

    return sorted(found)


# ---------------------------------------------------------------------------
# The per tool projections
# ---------------------------------------------------------------------------


def _project_tasks(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project planner.tasks.list."""

    if not isinstance(raw, Mapping):
        return {"tasks": []}, False, 0

    rows = raw.get("tasks")

    if not isinstance(rows, list):
        rows = []

    projected: list[dict[str, Any]] = []

    shortened = False

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        item, changed = _project_fields(row, TASK_FIELDS)

        shortened = shortened or changed

        projected.append(item)

    return {"tasks": projected}, shortened, len(projected)


def _project_single_task(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project planner.tasks.get."""

    if not isinstance(raw, Mapping):
        return {"task": None}, False, 0

    task = raw.get("task")

    if not isinstance(task, Mapping):
        return {"task": None}, False, 0

    item, shortened = _project_fields(task, TASK_FIELDS)

    return {"task": item}, shortened, 1


def _project_events(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project planner.events.list."""

    if not isinstance(raw, Mapping):
        return {"events": []}, False, 0

    rows = raw.get("events")

    if not isinstance(rows, list):
        rows = []

    projected: list[dict[str, Any]] = []

    shortened = False

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        item, changed = _project_fields(row, EVENT_FIELDS)

        shortened = shortened or changed

        projected.append(item)

    return {"events": projected}, shortened, len(projected)


def _project_single_event(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project planner.events.get."""

    if not isinstance(raw, Mapping):
        return {"event": None}, False, 0

    event = raw.get("event")

    if not isinstance(event, Mapping):
        return {"event": None}, False, 0

    item, shortened = _project_fields(event, EVENT_FIELDS)

    return {"event": item}, shortened, 1


def _project_calendar(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project planner.calendar.get."""

    if not isinstance(raw, Mapping):
        return {
            "view": None,
            "date": None,
            "range": None,
            "items": [],
        }, False, 0

    data: dict[str, Any] = {}

    shortened = False

    for name in ("view", "date"):
        value = raw.get(name)

        if _is_json_scalar(value):
            if isinstance(value, str):
                value, changed = _cap_string(name, value)

                shortened = shortened or changed

            data[name] = value

    raw_range = raw.get("range")

    if isinstance(raw_range, Mapping):
        projected_range: dict[str, Any] = {}

        for name in ("from", "to"):
            value = raw_range.get(name)

            if _is_json_scalar(value):
                if isinstance(value, str):
                    value, changed = _cap_string(
                        name,
                        value,
                    )

                    shortened = shortened or changed

                projected_range[name] = value

        data["range"] = projected_range

    else:
        data["range"] = None

    rows = raw.get("items")

    if not isinstance(rows, list):
        rows = []

    projected: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        item, changed = _project_fields(
            row,
            CALENDAR_ITEM_FIELDS,
        )

        shortened = shortened or changed

        projected.append(item)

    data["items"] = projected

    return data, shortened, len(projected)


def _project_attention(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project planner.attention.get."""

    data: dict[str, Any] = {
        "projectionVersion": None,
        "context": None,
        "generatedAt": None,
        "limit": None,
        "total": None,
        "items": [],
    }

    if not isinstance(raw, Mapping):
        return data, False, 0

    shortened = False

    for name in (
        "projectionVersion",
        "context",
        "generatedAt",
    ):
        value = raw.get(name)

        if _is_json_scalar(value):
            if isinstance(value, str):
                value, changed = _cap_string(name, value)

                shortened = shortened or changed

            data[name] = value

    for name in ("limit", "total"):
        value = raw.get(name)

        if isinstance(value, int) and not isinstance(value, bool):
            data[name] = value

    rows = raw.get("items")

    if not isinstance(rows, list):
        rows = []

    projected: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        item, changed = _project_fields(
            row,
            ATTENTION_ITEM_FIELDS,
        )

        shortened = shortened or changed

        projected.append(item)

    data["items"] = projected

    return data, shortened, len(projected)


def _project_search_result(
    raw: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Project one search result."""

    item, shortened = _project_fields(
        raw,
        SEARCH_RESULT_FIELDS,
    )

    metadata = raw.get("metadata")

    if isinstance(metadata, Mapping):
        projected_meta: dict[str, Any] = {}

        for name in SEARCH_METADATA_FIELDS:
            if name not in metadata:
                continue

            value = metadata[name]

            if not _is_json_scalar(value):
                continue

            if isinstance(value, str):
                value, changed = _cap_string(name, value)

                shortened = shortened or changed

            projected_meta[name] = value

        item["metadata"] = projected_meta

    return item, shortened


def _project_search(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project the Planner search result shared by v1 and v2 tool ids."""

    data: dict[str, Any] = {
        "projectionVersion": None,
        "context": None,
        "query": None,
        "generatedAt": None,
        "limit": None,
        "total": None,
        "groups": [],
    }

    if not isinstance(raw, Mapping):
        return data, False, 0

    shortened = False

    for name in (
        "projectionVersion",
        "context",
        "query",
        "generatedAt",
    ):
        value = raw.get(name)

        if _is_json_scalar(value):
            if isinstance(value, str):
                value, changed = _cap_string(name, value)

                shortened = shortened or changed

            data[name] = value

    for name in ("limit", "total"):
        value = raw.get(name)

        if isinstance(value, int) and not isinstance(value, bool):
            data[name] = value

    raw_groups = raw.get("groups")

    if not isinstance(raw_groups, list):
        raw_groups = []

    groups: list[dict[str, Any]] = []

    returned = 0

    for group in raw_groups:
        if not isinstance(group, Mapping):
            continue

        results = group.get("results")

        if not isinstance(results, list):
            results = []

        projected_results: list[dict[str, Any]] = []

        for row in results:
            if not isinstance(row, Mapping):
                continue

            item, changed = _project_search_result(row)

            shortened = shortened or changed

            projected_results.append(item)

        projected_group: dict[str, Any] = {}

        for name in ("entityType", "label"):
            value = group.get(name)

            if _is_json_scalar(value):
                if isinstance(value, str):
                    value, changed = _cap_string(name, value)

                    shortened = shortened or changed

                projected_group[name] = value

        projected_group["results"] = projected_results

        groups.append(projected_group)

        returned += len(projected_results)

    data["groups"] = groups

    return data, shortened, returned


def _project_summary(raw: Any) -> tuple[dict[str, Any], bool, int]:
    """Project planner.summary.get.

    The model facing projection carries the STRUCTURED canonical
    facts only: the counts, the task array, the event array and the
    goal. The pre-rendered narrative of the source (``briefing_text``)
    is deliberately NOT projected.

    The reason is a proven scope divergence, not a style preference.
    The T07 summary service derives ``briefing_text`` from the tasks
    whose ``due_date`` is TODAY, while ``counts.tasks`` is the
    household wide count of the pending and awaiting-verification
    tasks. A household with one pending task and no due date therefore
    produces ``counts.tasks = 1`` together with
    ``"Hoy tienes 0 tareas y 0 eventos."``. Both readings are
    truthful, but they describe different populations and the free
    text one is the one a model reads first. The structured facts
    already carry everything the narrative carries (every task keeps
    its own ``due_date``), so the narrative only adds ambiguity.
    """

    data: dict[str, Any] = {
        "projection_version": None,
        "generated_at": None,
        "counts": None,
        "tasks": [],
        "events": [],
        "goal": None,
    }

    if not isinstance(raw, Mapping):
        return data, False, 0

    shortened = False

    for name in ("projection_version", "generated_at"):
        value = raw.get(name)

        if _is_json_scalar(value):
            if isinstance(value, str):
                value, changed = _cap_string(name, value)

                shortened = shortened or changed

            data[name] = value

    counts = raw.get("counts")

    if isinstance(counts, Mapping):
        projected_counts: dict[str, Any] = {}

        for name in ("tasks", "events", "goals"):
            value = counts.get(name)

            if isinstance(value, int) and not isinstance(value, bool):
                projected_counts[name] = value

        data["counts"] = projected_counts

    tasks = raw.get("tasks")

    if not isinstance(tasks, list):
        tasks = []

    projected_tasks: list[dict[str, Any]] = []

    for row in tasks:
        if not isinstance(row, Mapping):
            continue

        item, changed = _project_fields(
            row,
            SUMMARY_TASK_FIELDS,
        )

        shortened = shortened or changed

        projected_tasks.append(item)

    data["tasks"] = projected_tasks

    events = raw.get("events")

    if not isinstance(events, list):
        events = []

    projected_events: list[dict[str, Any]] = []

    for row in events:
        if not isinstance(row, Mapping):
            continue

        item, changed = _project_fields(row, EVENT_FIELDS)

        shortened = shortened or changed

        projected_events.append(item)

    data["events"] = projected_events

    goal = raw.get("goal")

    if isinstance(goal, Mapping):
        item, changed = _project_fields(
            goal,
            SUMMARY_GOAL_FIELDS,
        )

        shortened = shortened or changed

        data["goal"] = item

    return (
        data,
        shortened,
        len(projected_tasks) + len(projected_events),
    )


# ---------------------------------------------------------------------------
# The per tool dispatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolProjection:
    """The projection descriptor of one canonical tool."""

    tool_id: str
    max_items: int | None
    project: Any
    # The data keys that hold the item lists of the projection.
    item_lists: tuple[str, ...] = ()
    # The optional top level fields, lowest priority first.
    top_level_optional: tuple[str, ...] = ()
    # The optional item fields, lowest priority first.
    item_optional: tuple[str, ...] = ()


# The optional fields that are removed first when the payload does not
# fit into the byte budget. The order is the priority order: the first
# entry is the least useful for a natural answer.
TASK_OPTIONAL_FIELDS: tuple[str, ...] = (
    "description",
    "archived_at",
    "updated_at",
    "created_at",
    "requires_verification",
    "category",
    "due_time",
    "priority",
)

EVENT_OPTIONAL_FIELDS: tuple[str, ...] = (
    "description",
    "updated_at",
    "created_at",
    "recurrence",
    "location_name",
    "all_day",
)

ATTENTION_OPTIONAL_FIELDS: tuple[str, ...] = (
    "summary",
    "updatedAt",
    "createdAt",
    "unresolved",
    "priorityScore",
    "severity",
)

SEARCH_RESULT_OPTIONAL_FIELDS: tuple[str, ...] = (
    "subtitle",
    "updatedAt",
    "metadata",
)

SUMMARY_OPTIONAL_FIELDS: tuple[str, ...] = (
    "goal",
    "generated_at",
    "projection_version",
)


# ---------------------------------------------------------------------------
# T24-I1 projection helper functions
# ---------------------------------------------------------------------------


def _t24_truncate(value: Any, limit: int) -> Any:
    """Truncate a string to ``limit`` characters, pass others through."""

    if isinstance(value, str) and len(value) > limit:
        return value[:limit]
    return value


def _cap_item_fields(item: Mapping[str, Any], limits: Mapping[str, int]) -> tuple[dict[str, Any], bool]:
    """Apply string caps to an item's fields. Returns (item, changed)."""

    changed = False
    projected: dict[str, Any] = {}

    for key, value in item.items():
        limit = limits.get(key)
        if limit is not None and isinstance(value, str):
            capped = value[:limit]
            if capped != value:
                changed = True
            projected[key] = capped
        else:
            projected[key] = value

    return projected, changed


def _current_result_data(raw_result: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Accept the current gateway body and the historical nested envelope."""

    if not isinstance(raw_result, Mapping):
        return None
    nested = raw_result.get("data")
    return nested if isinstance(nested, Mapping) else raw_result


def _project_inventory_items(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "inventory.items.list result data is not an object",
        )

    items = data.get("items")

    if not isinstance(items, list):
        items = []

    shortened = False
    projected_items: list[dict[str, Any]] = []

    item_limits = {
        "name": MAX_TITLE_CHARS,
        "category_key": MAX_FREE_TEXT_CHARS,
    }

    for item in items:
        if not isinstance(item, Mapping):
            continue
        projected, changed = _cap_item_fields(item, item_limits)
        shortened = shortened or changed
        projected_items.append(projected)

    return {"items": projected_items}, shortened, len(projected_items)


def _project_inventory_alerts(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "inventory.alerts.get result data is not an object",
        )

    return {
        "low_stock": data.get("low_stock", 0),
        "out_of_stock": data.get("out_of_stock", 0),
        "pending_restock": data.get("pending_restock", 0),
    }, False, 1


def _project_inventory_restock_requests(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "inventory.restock_requests.list result data is not an object",
        )

    requests = data.get("requests")

    if not isinstance(requests, list):
        requests = []

    shortened = False
    projected: list[dict[str, Any]] = []

    item_limits = {
        "suggested_title": MAX_TITLE_CHARS,
    }

    for req in requests:
        if not isinstance(req, Mapping):
            continue
        projected_item, changed = _cap_item_fields(req, item_limits)
        shortened = shortened or changed
        projected.append(projected_item)

    return {"requests": projected}, shortened, len(projected)


def _project_family_household(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "family.household.get result data is not an object",
        )

    return {
        "name": _t24_truncate(data.get("name", ""), MAX_TITLE_CHARS),
        "current_member_role": _t24_truncate(data.get("current_member_role", ""), 40),
        "members_count": data.get("members_count", 0),
    }, False, 1


def _project_family_members(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "family.members.list result data is not an object",
        )

    members = data.get("members")

    if not isinstance(members, list):
        members = []

    shortened = False
    projected: list[dict[str, Any]] = []

    item_limits = {
        "display_name": MAX_TITLE_CHARS,
        "role": 40,
        "status": 32,
    }

    for member in members:
        if not isinstance(member, Mapping):
            continue
        projected_item, changed = _cap_item_fields(member, item_limits)
        shortened = shortened or changed
        projected.append(projected_item)

    return {"members": projected}, shortened, len(projected)


def _project_family_member(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "family.members.get result data is not an object",
        )

    return {
        "member_ref": data.get("member_ref", ""),
        "display_name": _t24_truncate(data.get("display_name", ""), MAX_TITLE_CHARS),
        "role": _t24_truncate(data.get("role", ""), 40),
        "status": _t24_truncate(data.get("status", ""), 32),
    }, False, 1


def _project_finance_movements(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "finance.movements.list result data is not an object",
        )

    movements = data.get("movements")

    if not isinstance(movements, list):
        movements = []

    shortened = False
    projected: list[dict[str, Any]] = []

    item_limits = {
        "category_label": MAX_FREE_TEXT_CHARS,
        "description": MAX_DESCRIPTION_CHARS,
    }

    for movement in movements:
        if not isinstance(movement, Mapping):
            continue
        projected_item, changed = _cap_item_fields(movement, item_limits)
        shortened = shortened or changed
        projected.append(projected_item)

    return {
        "movements": projected,
        "period": data.get("period", ""),
    }, shortened, len(projected)


def _project_finance_accounts(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    """Project the bounded, non-authoritative account view used by synthesis."""

    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "finance.accounts.list result data is not an object",
        )

    accounts = data.get("accounts")

    if not isinstance(accounts, list):
        accounts = []

    shortened = False
    projected: list[dict[str, Any]] = []

    for account in accounts:
        if not isinstance(account, Mapping):
            continue

        account_ref = account.get("account_ref", account.get("id", ""))
        name = account.get("name", "")
        capped_name = _t24_truncate(name, MAX_TITLE_CHARS)
        shortened = shortened or capped_name != name
        projected.append(
            {
                "account_ref": account_ref,
                "name": capped_name,
                "currency": account.get("currency", ""),
                "account_type": account.get(
                    "account_type",
                    account.get("accountType", ""),
                ),
                "balance_state": account.get(
                    "balance_state",
                    account.get("balanceState", ""),
                ),
                # Keep the canonical decimal text exact; never coerce money
                # through a binary float in the model-facing projection.
                "current_balance": account.get(
                    "current_balance",
                    account.get("currentBalance"),
                ),
                "status": account.get("status", ""),
            }
        )

    return {"accounts": projected}, shortened, len(projected)


def _project_finance_summary(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "finance.summary.get result data is not an object",
        )

    currencies = data.get("currencies")

    if not isinstance(currencies, list):
        currencies = []

    return {
        "period": data.get("period", ""),
        "context_type": data.get("context_type", ""),
        "currencies": currencies,
    }, False, 1


def _project_finance_transaction(raw_result: Mapping[str, Any]) -> tuple[dict[str, Any], bool, int]:
    data = _current_result_data(raw_result)

    if not isinstance(data, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "finance.transaction.get result data is not an object",
        )

    return {
        "transaction_ref": data.get("transaction_ref", ""),
        "type": data.get("type", ""),
        "amount": data.get("amount", 0),
        "currency": data.get("currency", ""),
        "date": data.get("date", ""),
        "category_label": _t24_truncate(data.get("category_label", ""), MAX_FREE_TEXT_CHARS),
        "description": _t24_truncate(data.get("description", ""), MAX_DESCRIPTION_CHARS),
    }, False, 1


# ---------------------------------------------------------------------------
# T24-I1 optional field priority lists (byte budget reduction)
# ---------------------------------------------------------------------------

INVENTORY_ITEM_OPTIONAL_FIELDS: tuple[str, ...] = (
    "category_key",
    "low_stock_threshold",
)

INVENTORY_REQUEST_OPTIONAL_FIELDS: tuple[str, ...] = (
    "suggested_title",
)

FAMILY_MEMBER_OPTIONAL_FIELDS: tuple[str, ...] = (
    "status",
)

FINANCE_MOVEMENT_OPTIONAL_FIELDS: tuple[str, ...] = (
    "category_label",
    "description",
)

FINANCE_ACCOUNT_OPTIONAL_FIELDS: tuple[str, ...] = (
    "status",
    "balance_state",
    "account_type",
)


TOOL_PROJECTIONS: dict[str, ToolProjection] = {
    "planner.tasks.list": ToolProjection(
        tool_id="planner.tasks.list",
        max_items=MAX_TASKS_LIST_ITEMS,
        project=_project_tasks,
        item_lists=("tasks",),
        item_optional=TASK_OPTIONAL_FIELDS,
    ),
    "planner.tasks.get": ToolProjection(
        tool_id="planner.tasks.get",
        max_items=1,
        project=_project_single_task,
        item_optional=TASK_OPTIONAL_FIELDS,
    ),
    "planner.events.list": ToolProjection(
        tool_id="planner.events.list",
        max_items=MAX_EVENTS_LIST_ITEMS,
        project=_project_events,
        item_lists=("events",),
        item_optional=EVENT_OPTIONAL_FIELDS,
    ),
    "planner.events.get": ToolProjection(
        tool_id="planner.events.get",
        max_items=1,
        project=_project_single_event,
        item_optional=EVENT_OPTIONAL_FIELDS,
    ),
    "planner.calendar.get": ToolProjection(
        tool_id="planner.calendar.get",
        max_items=MAX_CALENDAR_ITEMS,
        project=_project_calendar,
        item_lists=("items",),
        item_optional=EVENT_OPTIONAL_FIELDS,
    ),
    "planner.attention.get": ToolProjection(
        tool_id="planner.attention.get",
        max_items=MAX_ATTENTION_ITEMS,
        project=_project_attention,
        item_lists=("items",),
        item_optional=ATTENTION_OPTIONAL_FIELDS,
    ),
    "planner.search.query": ToolProjection(
        tool_id="planner.search.query",
        max_items=None,
        project=_project_search,
        item_optional=SEARCH_RESULT_OPTIONAL_FIELDS,
    ),
    "planner.tasks.search": ToolProjection(
        tool_id="planner.tasks.search",
        max_items=None,
        project=_project_search,
        item_optional=SEARCH_RESULT_OPTIONAL_FIELDS,
    ),
    "planner.summary.get": ToolProjection(
        tool_id="planner.summary.get",
        max_items=None,
        project=_project_summary,
        item_lists=("tasks", "events"),
        top_level_optional=SUMMARY_OPTIONAL_FIELDS,
        item_optional=TASK_OPTIONAL_FIELDS,
    ),
    # ── T24-I1 multidomain READ projections ──────────────────────────
    # The backend T24 handlers already return only the allowed output
    # fields. The projections here enforce item caps and string caps in
    # Node D as defense in depth, then hand the data straight through.
    "inventory.items.list": ToolProjection(
        tool_id="inventory.items.list",
        max_items=100,
        project=_project_inventory_items,
        item_lists=("items",),
        item_optional=INVENTORY_ITEM_OPTIONAL_FIELDS,
    ),
    "inventory.alerts.get": ToolProjection(
        tool_id="inventory.alerts.get",
        max_items=1,
        project=_project_inventory_alerts,
    ),
    "inventory.restock_requests.list": ToolProjection(
        tool_id="inventory.restock_requests.list",
        max_items=100,
        project=_project_inventory_restock_requests,
        item_lists=("requests",),
        item_optional=INVENTORY_REQUEST_OPTIONAL_FIELDS,
    ),
    "family.household.get": ToolProjection(
        tool_id="family.household.get",
        max_items=1,
        project=_project_family_household,
    ),
    "family.members.list": ToolProjection(
        tool_id="family.members.list",
        max_items=100,
        project=_project_family_members,
        item_lists=("members",),
        item_optional=FAMILY_MEMBER_OPTIONAL_FIELDS,
    ),
    "family.members.get": ToolProjection(
        tool_id="family.members.get",
        max_items=1,
        project=_project_family_member,
    ),
    "finance.movements.list": ToolProjection(
        tool_id="finance.movements.list",
        max_items=100,
        project=_project_finance_movements,
        item_lists=("movements",),
        item_optional=FINANCE_MOVEMENT_OPTIONAL_FIELDS,
    ),
    "finance.accounts.list": ToolProjection(
        tool_id="finance.accounts.list",
        max_items=100,
        project=_project_finance_accounts,
        item_lists=("accounts",),
        item_optional=FINANCE_ACCOUNT_OPTIONAL_FIELDS,
    ),
    "finance.summary.get": ToolProjection(
        tool_id="finance.summary.get",
        max_items=1,
        project=_project_finance_summary,
    ),
    "finance.transaction.get": ToolProjection(
        tool_id="finance.transaction.get",
        max_items=1,
        project=_project_finance_transaction,
    ),
}


# ---------------------------------------------------------------------------
# The byte budget reduction
# ---------------------------------------------------------------------------


def _search_result_lists(
    data: Mapping[str, Any],
) -> list[list[dict[str, Any]]]:
    """The mutable result lists of a search projection."""

    lists: list[list[dict[str, Any]]] = []

    groups = data.get("groups")

    if not isinstance(groups, list):
        return lists

    for group in groups:
        if not isinstance(group, Mapping):
            continue

        results = group.get("results")

        if isinstance(results, list):
            lists.append(results)

    return lists


def _item_lists(
    tool_id: str,
    data: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    """The mutable item lists of a projection."""

    if tool_id in ("planner.search.query", "planner.tasks.search"):
        return _search_result_lists(data)

    lists: list[list[dict[str, Any]]] = []

    for name in TOOL_PROJECTIONS[tool_id].item_lists:
        rows = data.get(name)

        if isinstance(rows, list):
            lists.append(rows)

    return lists


def _drop_item_fields(
    lists: Sequence[list[dict[str, Any]]],
    field: str,
) -> None:
    """Remove one optional field from every item of every list."""

    for rows in lists:
        for row in rows:
            if isinstance(row, dict):
                row.pop(field, None)


def _drop_one_item(
    tool_id: str,
    data: dict[str, Any],
) -> bool:
    """Remove the last item of the longest list. Returns whether it did."""

    lists = _item_lists(tool_id, data)

    target: list[dict[str, Any]] | None = None

    for rows in lists:
        if len(rows) > 0 and (
            target is None or len(rows) > len(target)
        ):
            target = rows

    if target is None:
        return False

    target.pop()

    return True


def _enforce_byte_budget(
    tool_id: str,
    data: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Reduce the projection until it fits into the byte budget.

    The reduction is deterministic and follows the T09-F order:

    1. the per tool item caps and the string caps are already applied;
    2. the lowest priority optional fields are removed;
    3. the item count is reduced further;
    4. the remaining strings are shortened.

    The result is always a valid structure: the serialized bytes are
    never sliced.
    """

    projection = TOOL_PROJECTIONS[tool_id]

    def size() -> int:
        return canonical_size(
            {
                "tool_id": tool_id,
                "status": TOOL_STATUS_SUCCESS,
                "data": data,
                "meta": _WORST_CASE_META,
            }
        )

    if size() <= MAX_TOOL_RESULT_BYTES:
        return data, None

    lists = _item_lists(tool_id, data)

    # 2. the lowest priority optional fields.
    for field in projection.top_level_optional:
        if field in data:
            data.pop(field, None)

            if size() <= MAX_TOOL_RESULT_BYTES:
                return data, "field_reduction"

    for field in projection.item_optional:
        _drop_item_fields(lists, field)

        if size() <= MAX_TOOL_RESULT_BYTES:
            return data, "field_reduction"

    # 3. the item count is reduced further.
    while size() > MAX_TOOL_RESULT_BYTES:
        if not _drop_one_item(tool_id, data):
            break

        if size() <= MAX_TOOL_RESULT_BYTES:
            return data, "byte_cap"

    # 4. the remaining strings are shortened.
    limits = dict(STRING_LIMITS)

    while size() > MAX_TOOL_RESULT_BYTES:
        reduced = False

        for name in list(limits):
            if limits[name] <= 32:
                continue

            limits[name] = max(
                32,
                limits[name] // 2,
            )

            reduced = True

        _recap(data, limits)

        if size() <= MAX_TOOL_RESULT_BYTES:
            return data, "byte_cap"

        if not reduced:
            break

    return data, "byte_cap"


# ---------------------------------------------------------------------------
# The public entry point
# ---------------------------------------------------------------------------


def _source_total(
    tool_id: str,
    raw: Any,
) -> int | None:
    """The total exposed by the source, when it exposes one."""

    if not isinstance(raw, Mapping):
        return None

    if tool_id in (
        "planner.attention.get",
        "planner.search.query",
        "planner.tasks.search",
    ):
        value = raw.get("total")

        if isinstance(value, int) and not isinstance(value, bool):
            return value

        return None

    if tool_id == "planner.summary.get":
        counts = raw.get("counts")

        if not isinstance(counts, Mapping):
            return None

        total = 0

        for name in ("tasks", "events", "goals"):
            value = counts.get(name)

            if not isinstance(value, int) or isinstance(value, bool):
                return None

            total += value

        return total

    return None


# T24-I1 list payload keys (the backend wraps results in an ok/data envelope).
_T24_LIST_KEYS: dict[str, str] = {
    "inventory.items.list": "items",
    "inventory.restock_requests.list": "requests",
    "family.members.list": "members",
    "finance.movements.list": "movements",
    "finance.accounts.list": "accounts",
}

_T24_SINGLE_TOOLS: tuple[str, ...] = (
    "inventory.alerts.get",
    "family.household.get",
    "family.members.get",
    "finance.summary.get",
    "finance.transaction.get",
)


def _source_item_count(
    tool_id: str,
    raw: Any,
) -> int:
    """The number of items the SOURCE returned, before the caps."""

    if not isinstance(raw, Mapping):
        return 0

    if tool_id in _T24_LIST_KEYS:
        data = _current_result_data(raw)

        if isinstance(data, Mapping):
            rows = data.get(_T24_LIST_KEYS[tool_id])

            if isinstance(rows, list):
                return len(rows)

        return 0

    if tool_id in _T24_SINGLE_TOOLS:
        data = _current_result_data(raw)

        return 1 if isinstance(data, Mapping) else 0

    if tool_id in (
        "planner.tasks.list",
        "planner.events.list",
        "planner.calendar.get",
        "planner.attention.get",
    ):
        rows = raw.get(
            {
                "planner.tasks.list": "tasks",
                "planner.events.list": "events",
                "planner.calendar.get": "items",
                "planner.attention.get": "items",
            }[tool_id]
        )

        return len(rows) if isinstance(rows, list) else 0

    if tool_id in ("planner.search.query", "planner.tasks.search"):
        groups = raw.get("groups")

        total = 0

        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, Mapping):
                    continue

                results = group.get("results")

                if isinstance(results, list):
                    total += len(results)

        return total

    if tool_id == "planner.summary.get":
        tasks = raw.get("tasks")
        events = raw.get("events")

        total = 0

        if isinstance(tasks, list):
            total += len(tasks)

        if isinstance(events, list):
            total += len(events)

        return total

    # The single entity tools.
    for name in ("task", "event"):
        entity = raw.get(name)

        if isinstance(entity, Mapping):
            return 1

    return 0


def _apply_item_caps(
    tool_id: str,
    data: dict[str, Any],
) -> None:
    """Apply the per tool item caps to a projection."""

    projection = TOOL_PROJECTIONS[tool_id]

    if projection.max_items is not None:
        for name in projection.item_lists:
            rows = data.get(name)

            if (
                isinstance(rows, list)
                and len(rows) > projection.max_items
            ):
                del rows[projection.max_items:]

    if tool_id in ("planner.search.query", "planner.tasks.search"):
        groups = data.get("groups")

        if isinstance(groups, list):
            del groups[MAX_SEARCH_GROUPS:]

            for group in groups:
                if not isinstance(group, Mapping):
                    continue

                results = group.get("results")

                if (
                    isinstance(results, list)
                    and len(results) > MAX_SEARCH_RESULTS_PER_GROUP
                ):
                    del results[MAX_SEARCH_RESULTS_PER_GROUP:]


def _count_returned(
    tool_id: str,
    data: Mapping[str, Any],
) -> int:
    """The number of items the normalized data carries."""

    if tool_id in _T24_LIST_KEYS:
        rows = data.get(_T24_LIST_KEYS[tool_id])

        return len(rows) if isinstance(rows, list) else 0

    if tool_id in _T24_SINGLE_TOOLS:
        return 1 if isinstance(data, Mapping) else 0

    if tool_id in ("planner.search.query", "planner.tasks.search"):
        groups = data.get("groups")

        total = 0

        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, Mapping):
                    continue

                results = group.get("results")

                if isinstance(results, list):
                    total += len(results)

        return total

    if tool_id == "planner.summary.get":
        total = 0

        for name in ("tasks", "events"):
            rows = data.get(name)

            if isinstance(rows, list):
                total += len(rows)

        return total

    for name in ("tasks", "events", "items"):
        rows = data.get(name)

        if isinstance(rows, list):
            return len(rows)

    for name in ("task", "event"):
        entity = data.get(name)

        if isinstance(entity, Mapping):
            return 1

    return 0


def normalize_tool_result(
    tool_id: str,
    raw_result: Any,
) -> ToolResultV1:
    """Normalize ONE successful T07 result into a ToolResultV1.

    The function never raises for a missing or an unusual field: it
    only raises when the raw result is not a JSON object at all, or
    when the tool id is not canonical. Both are fail-closed errors of
    the orchestration seam.
    """

    projection = TOOL_PROJECTIONS.get(tool_id)

    if projection is None:
        raise ToolNormalizationError(
            "TOOL_RESULT_UNSUPPORTED",
            f"unknown tool id {tool_id!r}",
        )

    if not isinstance(raw_result, Mapping):
        raise ToolNormalizationError(
            "TOOL_RESULT_MALFORMED",
            "the raw tool result is not a JSON object",
        )

    data, shortened, _ = projection.project(raw_result)

    _apply_item_caps(tool_id, data)

    # The defense in depth strip. T24-I1 multidomain READ tools legitimately
    # use output fields (display_name, role) that collide with internal key
    # patterns; those exact keys are preserved for T24 tools only.
    preserve = (
        frozenset(T24_PRESERVE_KEYS)
        if tool_id in T24_READ_TOOL_IDS
        else None
    )

    data = strip_internal_keys(data, preserve)

    # The byte budget.
    data, budget_reason = _enforce_byte_budget(tool_id, data)

    # The honest metadata.
    total_count = _source_total(tool_id, raw_result)

    source_count = _source_item_count(tool_id, raw_result)

    returned = _count_returned(tool_id, data)

    if total_count is not None:
        omitted = max(0, total_count - returned)

    else:
        omitted = max(0, source_count - returned)

    reason: str | None = None

    if budget_reason is not None:
        reason = budget_reason

    elif shortened:
        reason = "string_cap"

    elif omitted > 0:
        reason = "item_cap"

    result = ToolResultV1(
        tool_id=tool_id,
        status=TOOL_STATUS_SUCCESS,
        data=data,
        meta=ToolResultMeta(
            truncated=bool(
                shortened
                or budget_reason is not None
                or omitted > 0
            ),
            returned_count=returned,
            total_count=total_count,
            omitted_count=omitted,
            truncation_reason=reason,
        ),
    )

    # The final guarantee: the serialized model facing payload is
    # inside the byte budget. If it is not, one more item is dropped
    # and the metadata is recomputed.
    while canonical_size(result.to_payload()) > MAX_TOOL_RESULT_BYTES:
        if not _drop_one_item(tool_id, data):
            break

        returned = _count_returned(tool_id, data)

        if total_count is not None:
            omitted = max(0, total_count - returned)

        else:
            omitted = max(0, source_count - returned)

        result = ToolResultV1(
            tool_id=tool_id,
            status=TOOL_STATUS_SUCCESS,
            data=data,
            meta=ToolResultMeta(
                truncated=True,
                returned_count=returned,
                total_count=total_count,
                omitted_count=omitted,
                truncation_reason="byte_cap",
            ),
        )

    return result


# ---------------------------------------------------------------------------
# The safety gate
# ---------------------------------------------------------------------------


def assert_tool_result_is_safe(
    result: ToolResultV1,
    *,
    secret_values: Sequence[str] = (),
) -> None:
    """Fail closed when a normalized result is not safe to send.

    The gate proves three properties of the model facing result:

    * it carries no internal, identity or auth key;
    * it carries no URL in a CONTROL position: no transport target and
      no implementation/control field can reach the model. This is
      the STRUCTURAL guarantee that keeps the HomePlus runtime out of
      the model facing payload;
    * no known secret value appears in its serialization.

    A URL that lives inside an approved free text DATA field (a task
    title, a task description, an event title, an event description, a
    location name) is NOT a violation. It is inert user data: it is
    not a transport target, it is not an endpoint, it is not a tool
    argument and it is never fetched. Rejecting it would abort a
    perfectly valid READ of an ordinary household.
    """

    payload = result.to_payload()

    control_urls = control_url_keys_in(payload)

    if control_urls:
        raise ToolNormalizationError(
            "TOOL_RESULT_NOT_SAFE",
            "the normalized tool result carries a control URL key: "
            + ", ".join(control_urls),
        )

    violations = forbidden_keys_in(payload)

    if result.tool_id in T24_READ_TOOL_IDS:
        violations = [
            violation
            for violation in violations
            if violation not in T24_PRESERVE_KEYS
        ]

    if violations:
        raise ToolNormalizationError(
            "TOOL_RESULT_NOT_SAFE",
            "the normalized tool result carries forbidden keys: "
            + ", ".join(violations),
        )

    serialized = canonical_serialization(payload)

    for secret in secret_values:
        if secret and secret in serialized:
            raise ToolNormalizationError(
                "TOOL_RESULT_NOT_SAFE",
                "the normalized tool result carries secret material",
            )
