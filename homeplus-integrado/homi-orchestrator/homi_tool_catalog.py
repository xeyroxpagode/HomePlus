"""HOMI T09-B — canonical Planner READ tool catalogue loader (Node D).

This module is deliberately inert:

* it performs no HTTP call;
* it performs no HomePlus authentication;
* it executes no tool;
* it makes no model call;
* it imports nothing from the HomePlus backend or from ``homi_contracts``.

It only reads one frozen local artefact, verifies that artefact against an
in-code trust anchor and exposes deterministic read-only APIs over it.

Trust model
-----------
The runtime trust anchor is the module constant
``PLANNER_READ_TOOLS_SHA256``. It is *not* the adjacent ``.sha256.txt`` file:
that file is informational only, so a catalogue that is modified together
with its adjacent digest file still fails closed at runtime.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ORCHESTRATOR_ROOT = (
    Path(__file__).resolve().parent
)

# Pass 2 (V1 full scope): el catálogo de D expone los 307 tools del catálogo
# definitivo (114 READ + 193 WRITE). Las tuplas estáticas están generadas
# desde homi-tools.v2.json por `_gen_target_ids.py`.
from homi_target_catalog import (  # noqa: E402
    V2_TARGET_TOOL_IDS,
    V2_TARGET_READ_IDS,
    V2_TARGET_WRITE_IDS,
)

CATALOG_DIR = ORCHESTRATOR_ROOT / "catalog"

CATALOG_FILENAME = "planner-read-tools.v1.json"

CATALOG_SHA256_FILENAME = (
    "planner-read-tools.v1.sha256.txt"
)

CATALOG_PATH = CATALOG_DIR / CATALOG_FILENAME

CATALOG_SHA256_PATH = (
    CATALOG_DIR / CATALOG_SHA256_FILENAME
)

# T09-B internal trust anchor. Any change to the catalogue artefact requires
# an explicit, reviewed change of this constant.
PLANNER_READ_TOOLS_SHA256 = (
    "5DBB18A2B95E0A3F57A1746C6B0D7271A1617EE8BC4489C665988D6A26722151"
)

# The frozen T07 authority the catalogue was derived from.
EXPECTED_SOURCE_COMMIT = (
    "126044232d11bc995b7540264d40d6dafb242e8c"
)

EXPECTED_SOURCE_BRANCH = "homi/t07-tool-layer"

EXPECTED_SCHEMA_VERSION = "1.0"

EXPECTED_TOOL_CONTRACT_VERSION = "1.0.0"

EXPECTED_TOOL_COUNT = 8

EXPECTED_TOOL_KIND = "READ"

EXPECTED_RISK_FLAG = "READ_ONLY"

EXPECTED_CONFIRMATION = "NEVER"

# The fixed 8-ID allow-list. Order is lexicographic by tool_id.
CANONICAL_TOOL_IDS: tuple[str, ...] = (
    "planner.attention.get",
    "planner.calendar.get",
    "planner.events.get",
    "planner.events.list",
    "planner.search.query",
    "planner.summary.get",
    "planner.tasks.get",
    "planner.tasks.list",
)

# Identity / authorization / transport fields that must never appear in a
# tool argument surface. The effective identity is supplied by the
# authoritative context boundary, never by the model.
FORBIDDEN_IDENTITY_KEYS: frozenset[str] = frozenset(
    {
        "actor_id",
        "household_id",
        "membership_id",
        "membershipId",
        "auth_user_id",
        "authUserId",
        "role",
        "token",
        "access_token",
        "authorization",
        "bearer",
        "password",
        "secret",
        "api_key",
        "url",
        "endpoint",
        "host",
        "sql",
        "query_sql",
    }
)

CATALOG_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "schema_version",
    "source_repository",
    "source_branch",
    "source_commit",
    "tool_contract_version",
    "tools",
)

TOOL_REQUIRED_FIELDS: tuple[str, ...] = (
    "contract_version",
    "tool_id",
    "description",
    "kind",
    "riskFlags",
    "confirmation",
    "inputSchema",
)


class ToolCatalogError(RuntimeError):
    """Fail-closed error raised by the T09-B catalogue layer."""

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


def _normalized_key(
    key: str,
) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        key.lower(),
    )


FORBIDDEN_IDENTITY_KEYS_NORMALIZED = frozenset(
    _normalized_key(key)
    for key in FORBIDDEN_IDENTITY_KEYS
)


def is_forbidden_identity_key(
    key: str,
) -> bool:
    """Whether a key is an identity/auth/transport field."""

    if key in FORBIDDEN_IDENTITY_KEYS:
        return True

    return (
        _normalized_key(key)
        in FORBIDDEN_IDENTITY_KEYS_NORMALIZED
    )


def _iter_schema_keys(
    node: Any,
) -> list[str]:
    """Collect every object key reachable inside a schema fragment."""

    found: list[str] = []

    if isinstance(node, dict):
        for key, value in node.items():
            found.append(key)
            found.extend(
                _iter_schema_keys(value)
            )

    elif isinstance(node, list):
        for value in node:
            found.extend(
                _iter_schema_keys(value)
            )

    return found


def sha256_bytes(
    data: bytes,
) -> str:
    """Hex SHA256 digest of a byte string."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(
    path: Path,
) -> str:
    """Hex SHA256 digest of a file, read in binary mode."""

    try:
        data = path.read_bytes()
    except OSError as error:
        raise ToolCatalogError(
            "CATALOG_NOT_FOUND",
            f"cannot read catalogue file {path}: {error}",
        ) from error

    return sha256_bytes(data)


def read_adjacent_digest_file(
    path: Path | None = None,
) -> str | None:
    """Read the informational adjacent digest file.

    This helper is *not* part of the trust model. It exists for operator
    diagnostics only. The loader never calls it and never uses it to
    accept a catalogue.
    """

    target = (
        path
        if path is not None
        else CATALOG_SHA256_PATH
    )

    if not target.is_file():
        return None

    try:
        text = target.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        return stripped.split()[0].lower()

    return None


def _validate_tool(
    tool: Any,
    tool_contract_version: str,
) -> None:
    if not isinstance(tool, dict):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "every catalogue entry must be an object",
        )

    for field in TOOL_REQUIRED_FIELDS:
        if field not in tool:
            raise ToolCatalogError(
                "CATALOG_DOCUMENT_INVALID",
                f"tool entry is missing required field {field!r}",
            )

    if tool["contract_version"] != tool_contract_version:
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "tool contract_version does not match the catalogue",
        )

    if tool["kind"] != EXPECTED_TOOL_KIND:
        raise ToolCatalogError(
            "CATALOG_TOOL_INVARIANT_VIOLATION",
            f"tool {tool['tool_id']!r} must be kind {EXPECTED_TOOL_KIND!r}, "
            f"got {tool['kind']!r}",
        )

    risk_flags = tool["riskFlags"]

    if (
        not isinstance(risk_flags, list)
        or EXPECTED_RISK_FLAG not in risk_flags
    ):
        raise ToolCatalogError(
            "CATALOG_TOOL_INVARIANT_VIOLATION",
            f"tool {tool['tool_id']!r} must carry risk flag "
            f"{EXPECTED_RISK_FLAG!r}",
        )

    if tool["confirmation"] != EXPECTED_CONFIRMATION:
        raise ToolCatalogError(
            "CATALOG_TOOL_INVARIANT_VIOLATION",
            f"tool {tool['tool_id']!r} must use confirmation "
            f"{EXPECTED_CONFIRMATION!r}",
        )

    description = tool["description"]

    if (
        not isinstance(description, str)
        or not description.strip()
    ):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            f"tool {tool['tool_id']!r} must carry a non-empty description",
        )

    input_schema = tool["inputSchema"]

    if not isinstance(input_schema, dict):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            f"tool {tool['tool_id']!r} inputSchema must be an object",
        )

    if input_schema.get("type") != "object":
        raise ToolCatalogError(
            "CATALOG_TOOL_INVARIANT_VIOLATION",
            f"tool {tool['tool_id']!r} inputSchema.type must be 'object'",
        )

    if input_schema.get("additionalProperties") is not False:
        raise ToolCatalogError(
            "CATALOG_TOOL_INVARIANT_VIOLATION",
            f"tool {tool['tool_id']!r} inputSchema.additionalProperties "
            "must be false",
        )

    properties = input_schema.get("properties")

    if not isinstance(properties, dict):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            f"tool {tool['tool_id']!r} inputSchema.properties must be "
            "an object",
        )

    required = input_schema.get("required")

    if not isinstance(required, list):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            f"tool {tool['tool_id']!r} inputSchema.required must be a list",
        )

    for name in required:
        if name not in properties:
            raise ToolCatalogError(
                "CATALOG_DOCUMENT_INVALID",
                f"tool {tool['tool_id']!r} required argument {name!r} "
                "is not declared in properties",
            )

    for key in _iter_schema_keys(input_schema):
        if is_forbidden_identity_key(key):
            raise ToolCatalogError(
                "CATALOG_FORBIDDEN_ARGUMENT_KEY",
                f"tool {tool['tool_id']!r} inputSchema exposes forbidden "
                f"identity/auth/transport key {key!r}",
            )


def parse_catalog_document(
    document: Any,
) -> tuple[Mapping[str, Any], ...]:
    """Validate a parsed catalogue document and return its tools.

    The document is accepted only when it matches the frozen T07 authority:
    the fixed 8-ID allow-list, the expected schema/contract versions and the
    READ / READ_ONLY / NEVER invariants.
    """

    if not isinstance(document, dict):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "the catalogue document must be an object",
        )

    for field in CATALOG_TOP_LEVEL_FIELDS:
        if field not in document:
            raise ToolCatalogError(
                "CATALOG_DOCUMENT_INVALID",
                f"the catalogue document is missing {field!r}",
            )

    if document["schema_version"] != EXPECTED_SCHEMA_VERSION:
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "unsupported catalogue schema_version "
            f"{document['schema_version']!r}",
        )

    if document["source_commit"] != EXPECTED_SOURCE_COMMIT:
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "the catalogue was not derived from the frozen T07 commit "
            f"{EXPECTED_SOURCE_COMMIT!r}",
        )

    tool_contract_version = document["tool_contract_version"]

    if tool_contract_version != EXPECTED_TOOL_CONTRACT_VERSION:
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "unsupported tool contract version "
            f"{tool_contract_version!r}",
        )

    tools = document["tools"]

    if not isinstance(tools, list):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "'tools' must be a list",
        )

    if len(tools) != EXPECTED_TOOL_COUNT:
        raise ToolCatalogError(
            "CATALOG_TOOL_ID_SET_MISMATCH",
            f"the catalogue must expose exactly {EXPECTED_TOOL_COUNT} tools, "
            f"got {len(tools)}",
        )

    for tool in tools:
        _validate_tool(tool, tool_contract_version)

    tool_ids = [tool["tool_id"] for tool in tools]

    if tool_ids != list(CANONICAL_TOOL_IDS):
        raise ToolCatalogError(
            "CATALOG_TOOL_ID_SET_MISMATCH",
            "the catalogue tool ids do not match the canonical allow-list",
        )

    if tool_ids != sorted(tool_ids):
        raise ToolCatalogError(
            "CATALOG_DOCUMENT_INVALID",
            "the catalogue tools are not sorted lexicographically by tool_id",
        )

    return tuple(copy.deepcopy(tools))


def loads_catalog_document(
    text: str,
) -> tuple[Mapping[str, Any], ...]:
    """Parse and validate a catalogue document from raw JSON text."""

    try:
        document = json.loads(text)
    except (ValueError, TypeError) as error:
        raise ToolCatalogError(
            "CATALOG_INVALID_JSON",
            f"the catalogue is not valid JSON: {error}",
        ) from error

    return parse_catalog_document(document)


@dataclass(frozen=True)
class ToolCatalog:
    """Immutable view over the verified canonical catalogue."""

    path: Path
    sha256: str
    document: Mapping[str, Any]
    tools: tuple[Mapping[str, Any], ...]

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return tuple(
            tool["tool_id"] for tool in self.tools
        )

    @property
    def source_commit(self) -> str:
        return str(self.document["source_commit"])

    @property
    def source_branch(self) -> str:
        return str(self.document["source_branch"])

    @property
    def source_repository(self) -> str:
        return str(self.document["source_repository"])

    @property
    def tool_contract_version(self) -> str:
        return str(
            self.document["tool_contract_version"]
        )

    @property
    def schema_version(self) -> str:
        return str(self.document["schema_version"])

    @property
    def digest(self) -> str:
        """The catalogue SHA256 digest (equals the trust anchor)."""

        return self.sha256

    def get(
        self,
        tool_id: str,
    ) -> Mapping[str, Any] | None:
        """Return the canonical definition or None when unknown."""

        for tool in self.tools:
            if tool["tool_id"] == tool_id:
                return tool

        return None

    def require(
        self,
        tool_id: str,
    ) -> Mapping[str, Any]:
        """Return the canonical definition or fail closed."""

        found = self.get(tool_id)

        if found is None:
            raise ToolCatalogError(
                "CATALOG_UNKNOWN_TOOL",
                f"unknown tool id {tool_id!r}",
            )

        return found

    def list_tools(self) -> list[Mapping[str, Any]]:
        """Every canonical definition, lexicographic by tool_id."""

        return [dict(tool) for tool in self.tools]

    def input_schema(
        self,
        tool_id: str,
    ) -> Mapping[str, Any]:
        """The input schema of a canonical tool."""

        return self.require(tool_id)["inputSchema"]

    def model_projection(self) -> list[dict[str, Any]]:
        """The minimal model-facing catalogue projection.

        Exactly three keys are exposed per tool: ``tool_id``,
        ``description`` and ``input_schema``. Kind, risk flags,
        confirmation, output schema, HomePlus URLs, database details and
        every identity/authentication field stay inside Node D.
        """

        projection: list[dict[str, Any]] = []

        for tool in self.tools:
            projection.append(
                {
                    "tool_id": tool["tool_id"],
                    "description": tool["description"],
                    "input_schema": copy.deepcopy(
                        tool["inputSchema"]
                    ),
                }
            )

        return projection


def load_catalog(
    path: Path | None = None,
) -> ToolCatalog:
    """Load, verify and validate the canonical catalogue.

    The byte digest of the artefact is compared against the in-code trust
    anchor ``PLANNER_READ_TOOLS_SHA256``. Any mismatch, any malformed
    document and any invariant violation fails closed.
    """

    target = (
        path
        if path is not None
        else CATALOG_PATH
    )

    if not target.is_file():
        raise ToolCatalogError(
            "CATALOG_NOT_FOUND",
            f"catalogue artefact not found: {target}",
        )

    data = target.read_bytes()

    digest = sha256_bytes(data)

    if digest.lower() != PLANNER_READ_TOOLS_SHA256.lower():
        raise ToolCatalogError(
            "CATALOG_DIGEST_MISMATCH",
            "the catalogue digest does not match the T09-B trust anchor "
            f"(expected {PLANNER_READ_TOOLS_SHA256}, got {digest})",
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ToolCatalogError(
            "CATALOG_INVALID_JSON",
            f"the catalogue is not valid UTF-8: {error}",
        ) from error

    tools = loads_catalog_document(text)

    document = json.loads(text)

    return ToolCatalog(
        path=target,
        sha256=digest,
        document=document,
        tools=tools,
    )


def catalog() -> ToolCatalog:
    """Return the verified catalogue.

    The artefact is re-read and re-verified on every call: the loader never
    caches, so a corrupted or replaced catalogue always fails closed on the
    next read instead of being masked by a stale in-memory copy.
    """

    return load_catalog()


def model_projection() -> list[dict[str, Any]]:
    """The model-facing projection of the verified catalogue."""

    return catalog().model_projection()


def tool_ids() -> tuple[str, ...]:
    """The canonical 8 tool ids, lexicographic."""

    return catalog().tool_ids


def is_known_tool(
    tool_id: str,
) -> bool:
    """Whether a tool id belongs to the canonical allow-list."""

    return tool_id in CANONICAL_TOOL_IDS


def forbidden_keys_in(
    node: Any,
) -> list[str]:
    """Forbidden identity/auth/transport keys reachable inside a node."""

    return sorted(
        {
            key
            for key in _iter_schema_keys(node)
            if is_forbidden_identity_key(key)
        }
    )


def forbidden_keys_in_arguments(
    arguments: Any,
) -> list[str]:
    """Forbidden identity/auth/transport keys inside an argument object."""

    return forbidden_keys_in(arguments)


# ---------------------------------------------------------------------------
# HOMI T24-I1 — additive v2 catalogue (nine multidomain READ tools)
# ---------------------------------------------------------------------------

CATALOG_V2_FILENAME = "homi-tools.v2.json"

CATALOG_V2_SHA256_FILENAME = "homi-tools.v2.sha256.txt"

CATALOG_V2_PATH = CATALOG_DIR / CATALOG_V2_FILENAME

CATALOG_V2_SHA256_PATH = CATALOG_DIR / CATALOG_V2_SHA256_FILENAME

# Pass 2 (V1 full scope): el catálogo de D expone los 307 tools del catálogo
# definitivo (114 READ + 193 WRITE). Las tuplas estáticas están generadas
# desde homi-tools.v2.json por `_gen_target_ids.py`.
from homi_target_catalog import (  # noqa: E402
    V2_TARGET_TOOL_IDS,
    V2_TARGET_READ_IDS,
    V2_TARGET_WRITE_IDS,
)

# Compat: el nombre legacy apunta ahora al catálogo definitivo. Los códigos
# externos usan `T24_READ_TOOL_IDS` como allow-list; para Pass 2 es el set
# de 307 tools objetivo.
T24_READ_TOOL_IDS: tuple[str, ...] = V2_TARGET_TOOL_IDS

# T24-I1 internal trust anchor for the v2 catalogue artefact. Any change to
# the v2 catalogue requires an explicit, reviewed change of this constant.
HOMI_TOOLS_V2_SHA256 = (
    "C2320B40D21241858EC8225A95E63731248C980ADA44DCF6BEF1F8AF458230ED"
)

EXPECTED_SCHEMA_VERSION_V2 = "2.0.0"

EXPECTED_TOOL_CONTRACT_VERSION_V2 = "2.0.0"

# Invariante del catálogo definitivo: todos los tools objetivo están presentes
# en `homi-tools.v2.json`; WRITE => kind 'WRITE' + confirmation 'REQUIRED'
# + risk flag mutacional; READ => kind 'READ' + confirmation 'NEVER'.
V2_KINDS: tuple[str, ...] = ("READ", "WRITE")
V2_CONFIRMATIONS: tuple[str, ...] = ("NEVER", "REQUIRED")
V2_WRITE_RISK_FLAGS: tuple[str, ...] = ("LOW_MUTATION", "MODERATE_MUTATION", "REVERSIBLE_MUTATION", "DESTRUCTIVE")

# T24 gate legado: ahora default-True porque el catálogo de D es el del
# catálogo definitivo. Mantener constante para pruebas legacy.
T24_READ_ENABLED = True

# Effective allow-list: todos los tools del catálogo definitivo.
def effective_tool_ids() -> tuple[str, ...]:
    """The effective tool id allow-list for this Node D instance.

    Pass 2: exposes the 307 tools of the frozen catalog (114 READ + 193
    WRITE). No se permite ninguna sublista por estado de proveedor: los
    proveedores (THINK/STT/SEE) son runtime, no parte del catálogo.
    """

    return tuple(sorted(V2_TARGET_TOOL_IDS))


def is_t24_read_tool(
    tool_id: str,
) -> bool:
    """Whether a tool id is one of the target tools (legacy name)."""

    return tool_id in V2_TARGET_READ_IDS


def is_t24_read_enabled() -> bool:
    """Whether the catalog gate is open (always True in Pass 2)."""

    return bool(T24_READ_ENABLED)


def is_known_tool_v2(
    tool_id: str,
) -> bool:
    """Whether a tool id belongs to the effective allow-list (v2)."""

    return tool_id in effective_tool_ids()


def parse_catalog_document_v2(
    document: Any,
) -> tuple[Mapping[str, Any], ...]:
    """Validate a parsed v2 catalogue document and return its tools.

    The v2 document must contain exactly the frozen target tools
    (`V2_TARGET_TOOL_IDS`), with the definitivo invariants for READ
    (kind READ + NEVER + READ_ONLY risk) and WRITE (kind WRITE +
    REQUIRED + mutation risk flags).
    """

    if not isinstance(document, dict):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            "the v2 catalogue document must be an object",
        )

    for field in CATALOG_TOP_LEVEL_FIELDS:
        if field not in document:
            raise ToolCatalogError(
                "CATALOG_V2_DOCUMENT_INVALID",
                f"the v2 catalogue document is missing {field!r}",
            )

    if document["schema_version"] != EXPECTED_SCHEMA_VERSION_V2:
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            "unsupported v2 catalogue schema_version "
            f"{document['schema_version']!r}",
        )

    tool_contract_version = document["tool_contract_version"]

    if tool_contract_version != EXPECTED_TOOL_CONTRACT_VERSION_V2:
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            "unsupported v2 tool contract version "
            f"{tool_contract_version!r}",
        )

    tools = document["tools"]

    if not isinstance(tools, list):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            "'tools' must be a list",
        )

    if len(tools) != len(V2_TARGET_TOOL_IDS):
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_COUNT_MISMATCH",
            f"the v2 catalogue must expose exactly "
            f"{len(V2_TARGET_TOOL_IDS)} tools, got {len(tools)}",
        )

    for tool in tools:
        _validate_tool_v2(tool, tool_contract_version)

    tool_ids = [tool["tool_id"] for tool in tools]

    if tool_ids != sorted(tool_ids):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            "the v2 catalogue tools are not sorted lexicographically by "
            "tool_id",
        )

    expected_ids = list(V2_TARGET_TOOL_IDS)

    if tool_ids != expected_ids:
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_ID_SET_MISMATCH",
            "the v2 catalogue tool ids do not match the frozen target set",
        )

    return tuple(copy.deepcopy(tools))


def _validate_tool_v2(
    tool: Any,
    tool_contract_version: str,
) -> None:
    if not isinstance(tool, dict):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            "every v2 catalogue entry must be an object",
        )

    for field in TOOL_REQUIRED_FIELDS:
        if field not in tool:
            raise ToolCatalogError(
                "CATALOG_V2_DOCUMENT_INVALID",
                f"v2 tool entry is missing required field {field!r}",
            )

    if tool["contract_version"] != tool_contract_version:
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            "v2 tool contract_version does not match the catalogue",
        )

    kind = tool["kind"]

    if kind not in V2_KINDS:
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_INVARIANT_VIOLATION",
            f"v2 tool {tool['tool_id']!r} must have kind in {V2_KINDS}, got {kind!r}",
        )

    risk_flags = tool["riskFlags"]

    if not isinstance(risk_flags, list) or len(risk_flags) == 0:
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_INVARIANT_VIOLATION",
            f"v2 tool {tool['tool_id']!r} must carry risk flags",
        )

    if kind == "READ" and (
        not any(f in risk_flags for f in ("READ_ONLY",))
        or any(f in V2_WRITE_RISK_FLAGS for f in risk_flags)
    ):
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_INVARIANT_VIOLATION",
            f"v2 tool {tool['tool_id']!r} READ must carry READ_ONLY only",
        )

    if kind == "WRITE" and (
        "READ_ONLY" in risk_flags
        or not any(f in V2_WRITE_RISK_FLAGS for f in risk_flags)
    ):
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_INVARIANT_VIOLATION",
            f"v2 tool {tool['tool_id']!r} WRITE must carry mutation risk flags",
        )

    expected_confirmation = "NEVER" if kind == "READ" else "REQUIRED"

    if tool["confirmation"] != expected_confirmation:
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_INVARIANT_VIOLATION",
            f"v2 tool {tool['tool_id']!r} must use confirmation "
            f"{expected_confirmation!r}, got {tool['confirmation']!r}",
        )

    description = tool["description"]

    if (
        not isinstance(description, str)
        or not description.strip()
    ):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            f"v2 tool {tool['tool_id']!r} must carry a non-empty description",
        )

    input_schema = tool["inputSchema"]

    if not isinstance(input_schema, dict):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            f"v2 tool {tool['tool_id']!r} inputSchema must be an object",
        )

    if input_schema.get("type") != "object":
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_INVARIANT_VIOLATION",
            f"v2 tool {tool['tool_id']!r} inputSchema.type must be 'object'",
        )

    if input_schema.get("additionalProperties") is not False:
        raise ToolCatalogError(
            "CATALOG_V2_TOOL_INVARIANT_VIOLATION",
            f"v2 tool {tool['tool_id']!r} inputSchema.additionalProperties "
            "must be false",
        )

    properties = input_schema.get("properties")

    if not isinstance(properties, dict):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            f"v2 tool {tool['tool_id']!r} inputSchema.properties must be "
            "an object",
        )

    required = input_schema.get("required")

    if not isinstance(required, list):
        raise ToolCatalogError(
            "CATALOG_V2_DOCUMENT_INVALID",
            f"v2 tool {tool['tool_id']!r} inputSchema.required must be a list",
        )

    for name in required:
        if name not in properties:
            raise ToolCatalogError(
                "CATALOG_V2_DOCUMENT_INVALID",
                f"v2 tool {tool['tool_id']!r} required argument {name!r} "
                "is not declared in properties",
            )

    for key in _iter_schema_keys(input_schema):
        if is_forbidden_identity_key(key):
            raise ToolCatalogError(
                "CATALOG_V2_FORBIDDEN_ARGUMENT_KEY",
                f"v2 tool {tool['tool_id']!r} inputSchema exposes forbidden "
                f"identity/auth/transport key {key!r}",
            )


def sha256_file_v2(
    path: Path,
) -> str:
    """Hex SHA256 digest of the v2 catalogue file."""

    return sha256_file(path)


def load_catalog_v2(
    path: Path | None = None,
) -> ToolCatalog:
    """Load, verify and validate the v2 catalogue artefact.

    The byte digest is compared against the in-code trust anchor
    ``HOMI_TOOLS_V2_SHA256``. Any mismatch, any malformed document and any
    invariant violation fails closed.
    """

    target = (
        path
        if path is not None
        else CATALOG_V2_PATH
    )

    if not target.is_file():
        raise ToolCatalogError(
            "CATALOG_V2_NOT_FOUND",
            f"v2 catalogue artefact not found: {target}",
        )

    data = target.read_bytes()

    digest = sha256_bytes(data)

    if digest.lower() != HOMI_TOOLS_V2_SHA256.lower():
        raise ToolCatalogError(
            "CATALOG_V2_DIGEST_MISMATCH",
            "the v2 catalogue digest does not match the T24-I1 trust anchor "
            f"(expected {HOMI_TOOLS_V2_SHA256}, got {digest})",
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ToolCatalogError(
            "CATALOG_V2_INVALID_JSON",
            f"the v2 catalogue is not valid UTF-8: {error}",
        ) from error

    tools = parse_catalog_document_v2(json.loads(text))

    document = json.loads(text)

    return ToolCatalog(
        path=target,
        sha256=digest,
        document=document,
        tools=tools,
    )


def catalog_v2() -> ToolCatalog:
    """Return the verified v2 catalogue.

    The artefact is re-read and re-verified on every call: the loader never
    caches, so a corrupted or replaced catalogue always fails closed on the
    next read instead of being masked by a stale in-memory copy.
    """

    return load_catalog_v2()


def model_projection_v2() -> list[dict[str, Any]]:
    """The model-facing projection of the verified v2 catalogue."""

    return catalog_v2().model_projection()


def load_effective_catalog(
) -> tuple[Mapping[str, Any], ...]:
    """Return the effective combined catalogue (v1 + v2 when enabled).

    The v1 Planner READ tools are always included. The nine T24 READ tools
    are included only when the T24 gate is enabled. The combined list is
    sorted lexicographically by tool_id and contains no duplicate ids.
    """

    v1_tools = list(catalog().tools)
    effective_tools = list(v1_tools)

    if T24_READ_ENABLED:
        v2_tools = list(catalog_v2().tools)
        v1_ids = {tool["tool_id"] for tool in v1_tools}

        for tool in v2_tools:
            if tool["tool_id"] not in v1_ids:
                effective_tools.append(tool)
                v1_ids.add(tool["tool_id"])

    effective_tools.sort(key=lambda tool: str(tool["tool_id"]))

    return tuple(effective_tools)
