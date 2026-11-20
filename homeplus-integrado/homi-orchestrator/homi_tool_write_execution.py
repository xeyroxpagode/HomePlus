"""HOMI T11-6 — internal write execution seam (Node D -> T07).

T11-6 enables EXACTLY ONE real WRITE: ``planner.tasks.create`` — and
only from the CURRENT trusted CONFIRMED ActionProposal:

    CONFIRMED
        -> EXECUTING (state owned by ``homi_tool_proposal``)
        -> ONE internal server-to-server call to the T07 write seam
        -> SUCCEEDED (authoritative create result)
        |  FAILED (deterministic definite failure)

Hard boundaries of this stage
-----------------------------
* One execution attempt performs at most ONE HTTP call. The executor
  never retries: automatic retry, transport retry and dedup recovery
  beyond what the T07 idempotency key naturally provides belong to
  T11-7.
* The executor never reinterprets the user request, never asks Node A
  anything, never chooses another tool, never changes the proposal
  arguments and never executes a second tool.
* The execution request is derived EXCLUSIVELY from the CONFIRMED
  proposal: ``execute(proposal)`` only — the caller cannot submit
  replacement arguments at execution time.
* The internal WRITE authority travels in the dedicated
  ``X-Homi-Internal-Write`` header, sourced from the
  ``HOMI_INTERNAL_WRITE_SECRET`` environment variable. It is held by
  the D and T07 SERVER environments only: it is never exposed via
  ``EXPO_PUBLIC_*``, the frontend bundle, the proposal, the model
  context, the logs or the response envelope.
* The HomePlus bearer credential of the ORIGINAL request travels in
  ``Authorization`` for every write execution. Normal HomePlus user
  authorization remains authoritative; D confirmation never bypasses
  T07 permissions.
* Missing or malformed configuration fails closed: without a secret
  the disabled executor stays in place and every confirm behaves as
  the T11-5 state-only lifecycle.
* The T11-6 flow claims SUCCEEDED, never VERIFIED. Independent
  post-write verification belongs to T11-8.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import httpx

from homi_tool_compound_result_contract import (
    COMPOUND_OPERATION_ERROR_FIELDS,
    COMPOUND_OPERATION_RESULT_FIELDS,
    COMPOUND_OPERATION_RESULT_STATUSES,
    COMPOUND_RESULT_FIELDS,
    COMPOUND_RESULT_STATUSES,
    CompoundResultAuthorityError,
    validate_compound_execution_result,
)
from homi_tool_proposal import (
    PLANNER_TASKS_CREATE_TOOL_ID,
    PLANNER_TASKS_UPDATE_TOOL_ID,
    PLANNER_TASKS_COMPLETE_TOOL_ID,
    PLANNER_TASKS_TRASH_TOOL_ID,
    PLANNER_TASKS_RESTORE_TOOL_ID,
    PROPOSAL_TOOL_IDS,
    ActionProposalV1,
    is_compound_create_arguments,
    proposal_arguments_copy,
    proposal_execution_safe_result,
)


SECRET_ENV = "HOMI_INTERNAL_WRITE_SECRET"

BASE_URL_ENV = "HOMI_INTERNAL_WRITE_BASE_URL"

FALLBACK_BASE_URL_ENV = "HOMI_TOOL_BASE_URL"

TIMEOUT_ENV = "HOMI_INTERNAL_WRITE_TIMEOUT_S"

DEFAULT_WRITE_TIMEOUT_S = 20.0

MAX_WRITE_TIMEOUT_S = 120.0

ALLOWED_SCHEMES = ("http", "https")

INTERNAL_WRITE_HEADER = "X-Homi-Internal-Write"

WRITE_EXECUTE_PATH_PREFIX = "/api/homi/v1/internal/tools"

EXECUTE_PATH_SUFFIX = "/execute"

# Every WRITE tool of the frozen catalog is executable through this seam
# (Pass 2 V1 full scope). The seam still fails closed when the proposal is
# not CONFIRMED and when a tool is outside this allow-list.
WRITE_EXECUTION_TOOL_IDS: tuple[str, ...] = PROPOSAL_TOOL_IDS

# The exact top level fields of the write execution body. No other
# field is ever sent: the credential travels in the Authorization
# header, the internal authority travels in its dedicated header and
# never in the body.
EXECUTE_BODY_FIELDS: tuple[str, ...] = (
    "proposal_id",
    "tool_id",
    "actor_id",
    "household_id",
    "args",
)


class WriteConfigError(RuntimeError):
    """Fail-closed configuration error of the write execution seam."""


@dataclass(frozen=True)
class WriteExecutionConfig:
    """The resolved write execution configuration."""

    base_url: str | None
    secret: str | None
    timeout_s: float

    @property
    def configured(self) -> bool:
        """Whether the seam has a usable base URL AND secret."""

        return bool(self.base_url) and bool(self.secret)

    def describe(self) -> dict[str, Any]:
        """A secret-free description of the configuration."""

        return {
            "configured": self.configured,
            "base_url_present": self.base_url is not None,
            "secret_present": self.secret is not None,
            "timeout_s": self.timeout_s,
        }


def load_write_execution_config(
    environ: Mapping[str, str] | None = None,
) -> WriteExecutionConfig:
    """Parse the write execution configuration from the environment.

    An absent secret or base URL is NOT an error: it yields an
    unconfigured seam, which fails closed when it is used (the disabled
    executor stays in place). A malformed URL or timeout is an error.
    """

    env = os.environ if environ is None else environ

    raw_base_url = (
        env.get(BASE_URL_ENV)
        or env.get(FALLBACK_BASE_URL_ENV)
        or ""
    ).strip()

    base_url: str | None = None

    if raw_base_url:
        parsed = urlparse(raw_base_url)

        if (
            parsed.scheme.lower() not in ALLOWED_SCHEMES
            or not parsed.netloc
        ):
            raise WriteConfigError(
                f"{BASE_URL_ENV} must be an absolute http(s) URL"
            )

        base_url = raw_base_url.rstrip("/")

    secret = (env.get(SECRET_ENV) or "").strip() or None

    raw_timeout = (env.get(TIMEOUT_ENV) or "").strip()

    timeout_s = DEFAULT_WRITE_TIMEOUT_S

    if raw_timeout:
        try:
            timeout_s = float(raw_timeout)

        except (TypeError, ValueError) as error:
            raise WriteConfigError(
                f"{TIMEOUT_ENV} must be a positive number"
            ) from error

        if not 0 < timeout_s <= MAX_WRITE_TIMEOUT_S:
            raise WriteConfigError(
                f"{TIMEOUT_ENV} must be a positive number and at "
                f"most {MAX_WRITE_TIMEOUT_S}"
            )

    return WriteExecutionConfig(
        base_url=base_url,
        secret=secret,
        timeout_s=timeout_s,
    )


def require_configured(
    config: WriteExecutionConfig | None = None,
) -> WriteExecutionConfig:
    """Return a configured seam or fail closed."""

    resolved = (
        config
        if config is not None
        else load_write_execution_config()
    )

    if not resolved.configured:
        raise WriteConfigError(
            "the internal write execution seam is not configured"
        )

    return resolved


class WriteExecutorDisabledError(RuntimeError):
    """Raised by the disabled write executor."""


# ---------------------------------------------------------------------------
# The real internal write client
# ---------------------------------------------------------------------------


def internal_write_url(
    base_url: str,
    tool_id: str = PLANNER_TASKS_CREATE_TOOL_ID,
) -> str:
    """The canonical internal write execution URL of one tool.

    The tool id is percent encoded: it can never escape its path
    segment.
    """

    encoded = quote(str(tool_id), safe="")

    return (
        f"{base_url.rstrip('/')}"
        f"{WRITE_EXECUTE_PATH_PREFIX}/{encoded}"
        f"{EXECUTE_PATH_SUFFIX}"
    )


def build_write_headers(
    *,
    secret: str,
    bearer_token: str,
) -> dict[str, str]:
    """The exact headers of one write execution.

    The internal authority travels ONLY in its dedicated header and the
    HomePlus user credential ONLY in ``Authorization``.
    """

    return {
        INTERNAL_WRITE_HEADER: secret,
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def build_write_body(
    proposal: ActionProposalV1,
    *,
    actor_id: str,
    household_id: str,
) -> dict[str, Any]:
    """The exact body of one write execution.

    The arguments are taken from the CONFIRMED proposal snapshot. There
    is no parameter to replace them at execution time.
    """

    return {
        "proposal_id": proposal.proposal_id,
        "tool_id": proposal.tool_id,
        "actor_id": actor_id,
        "household_id": household_id,
        "args": proposal_arguments_copy(proposal.arguments),
    }


def assert_write_execution_trusted(
    proposal: ActionProposalV1,
) -> None:
    """Fail closed when the proposal is not a trusted write execution.

    The tool must be the ONE canonical write tool. The identity, the
    kind, the risk and the confirmation of the tool contract were
    already revalidated by the proposal lifecycle; this bound is the
    last fail-closed seal of the seam itself.
    """

    if proposal.tool_id not in WRITE_EXECUTION_TOOL_IDS:
        raise WriteConfigError(
            f"tool {proposal.tool_id!r} is not executable through the "
            "internal write seam"
        )


class InternalWriteClient:
    """The real server-to-server write client of Node D (T11-6).

    The client is a transport, not an authority:

    * the seam URL comes from the trusted configuration only;
    * the tool id comes from the CONFIRMED proposal only;
    * the internal WRITE authority travels in its dedicated header
      only, is received per call, and is never stored, logged or
      serialized;
    * the HomePlus bearer token travels as the request-local user
      credential, never stored, never logged;
    * one execution performs ONE call and never retries.
    """

    def __init__(
        self,
        config: WriteExecutionConfig,
    ) -> None:

        resolved = require_configured(config)

        self._base_url = str(resolved.base_url).rstrip("/")

        self._secret = resolved.secret

        self._timeout_s = float(resolved.timeout_s)

    @property
    def base_url(self) -> str:
        """The trusted T07 base URL."""

        return self._base_url

    @property
    def timeout_s(self) -> float:
        """The write call timeout, in seconds."""

        return self._timeout_s

    def build_url(
        self,
        tool_id: str,
    ) -> str:
        """Build the write URL of one tool."""

        return internal_write_url(self._base_url, tool_id)

    def build_headers(
        self,
        bearer_token: str,
    ) -> dict[str, str]:
        """Build the write headers."""

        return build_write_headers(
            secret=self._secret,
            bearer_token=bearer_token,
        )

    def build_body(
        self,
        proposal: ActionProposalV1,
        *,
        actor_id: str,
        household_id: str,
    ) -> dict[str, Any]:
        """Build the write body."""

        return build_write_body(
            proposal,
            actor_id=actor_id,
            household_id=household_id,
        )


def _read_json(
    content: bytes | None,
) -> Any:
    """Read a JSON body, or return None when it is not JSON."""

    if not content or not content.strip():
        return None

    try:
        return json.loads(content)

    except (ValueError, UnicodeDecodeError):
        return None


@dataclass(frozen=True)
class WriteExecutionAttemptResult:
    """The normalized outcome of ONE write execution attempt.

    ``ok`` mirrors the authoritative create response of T07. A failure
    carries a deterministic, credential free reason code, never a raw
    upstream body, stack or row.

    ``retryable`` is semantics only in T11-6: the executor NEVER
    retries; a retryable transport outcome still demotes the proposal
    to FAILED and every recovery protocol belongs to T11-7.
    """

    ok: bool
    tool_id: str
    result: dict[str, Any] | None = None
    reason_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    upstream_status: int | None = None


async def attempt_write_execution(
    proposal: ActionProposalV1,
    *,
    base_url: str,
    secret: str,
    bearer_token: str,
    actor_id: str,
    household_id: str,
    timeout_s: float,
) -> WriteExecutionAttemptResult:
    """Perform ONE internal write execution attempt.

    This is the ONLY place where the loop performs the network call.
    The call is never retried.
    """

    tool_id = proposal.tool_id

    url = internal_write_url(base_url, tool_id)

    headers = build_write_headers(
        secret=secret,
        bearer_token=bearer_token,
    )

    body = build_write_body(
        proposal,
        actor_id=actor_id,
        household_id=household_id,
    )

    try:
        async with httpx.AsyncClient(
            timeout=timeout_s
        ) as client:

            response = await client.post(
                url,
                json=body,
                headers=headers,
            )

    except httpx.TimeoutException:
        return WriteExecutionAttemptResult(
            ok=False,
            tool_id=tool_id,
            reason_code="EXECUTION_TIMEOUT",
            error_message=(
                "the internal write execution timed out"
            ),
            retryable=True,
        )

    except Exception:
        return WriteExecutionAttemptResult(
            ok=False,
            tool_id=tool_id,
            reason_code="EXECUTION_UNREACHABLE",
            error_message=(
                "the internal write execution is unreachable"
            ),
            retryable=True,
        )

    compound = is_compound_create_arguments(
        proposal.arguments
    )

    expected_operation_count = None

    if compound:
        operations = proposal.arguments.get("operations")

        if isinstance(operations, list):
            expected_operation_count = len(operations)

    return interpret_write_response(
        tool_id=tool_id,
        status_code=response.status_code,
        content=response.content,
        compound=compound,
        expected_operation_count=expected_operation_count,
    )


def interpret_write_response(
    *,
    tool_id: str,
    status_code: int,
    content: bytes | None,
    compound: bool = False,
    expected_operation_count: int | None = None,
) -> WriteExecutionAttemptResult:
    """Map one T07 write response onto a normalized outcome."""

    payload = _read_json(content)

    upstream_code = None

    if isinstance(payload, dict):
        error = payload.get("error")

        if isinstance(error, dict) and isinstance(
            error.get("code"), str
        ):
            upstream_code = error["code"]

    if status_code == 200:
        if not isinstance(payload, dict) or payload.get(
            "ok"
        ) is not True:
            return WriteExecutionAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="EXECUTION_MALFORMED_SUCCESS",
                error_message=(
                    "the internal write execution returned a "
                    "malformed success envelope"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        if payload.get("tool_id") != tool_id:
            return WriteExecutionAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="EXECUTION_MALFORMED_SUCCESS",
                error_message=(
                    "the internal write execution returned a "
                    "tool mismatch"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        result = payload.get("result")

        if not isinstance(result, dict):
            return WriteExecutionAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="EXECUTION_MALFORMED_SUCCESS",
                error_message=(
                    "the internal write execution returned a "
                    "malformed result"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        if compound:
            try:
                compound_violations = (
                    validate_compound_execution_result(
                        result,
                        expected_operation_count=(
                            expected_operation_count
                        ),
                    )
                )

            except CompoundResultAuthorityError:
                return WriteExecutionAttemptResult(
                    ok=False,
                    tool_id=tool_id,
                    reason_code=(
                        "COMPOUND_RESULT_AUTHORITY_ANCHOR_MISMATCH"
                    ),
                    error_message=(
                        "the local compound result authority failed "
                        "its integrity check"
                    ),
                    retryable=False,
                    upstream_status=status_code,
                )

            if compound_violations:
                return WriteExecutionAttemptResult(
                    ok=False,
                    tool_id=tool_id,
                    reason_code="EXECUTION_MALFORMED_SUCCESS",
                    error_message=(
                        "the internal write execution returned a "
                        "malformed compound result"
                    ),
                    retryable=False,
                    upstream_status=status_code,
                )

        elif (
            "operations" in result
            or result.get("status")
            in COMPOUND_RESULT_STATUSES
        ):
            return WriteExecutionAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="EXECUTION_MALFORMED_SUCCESS",
                error_message=(
                    "the internal write execution returned a "
                    "compound result for a simple create"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        return WriteExecutionAttemptResult(
            ok=True,
            tool_id=tool_id,
            result=result,
            upstream_status=status_code,
        )

    reason_by_status = {
        400: "EXECUTION_REQUEST_REJECTED",
        401: "EXECUTION_AUTH_REJECTED",
        403: "EXECUTION_AUTHORITY_REJECTED",
        404: "EXECUTION_SEAM_ABSENT",
        412: "EXECUTION_VERSION_CONFLICT",
        422: "EXECUTION_REQUEST_REJECTED",
    }

    if status_code in reason_by_status:
        return WriteExecutionAttemptResult(
            ok=False,
            tool_id=tool_id,
            reason_code=(
                upstream_code if upstream_code
                else reason_by_status[status_code]
            ),
            error_message=(
                "the internal write execution was rejected"
            ),
            retryable=False,
            upstream_status=status_code,
        )

    return WriteExecutionAttemptResult(
        ok=False,
        tool_id=tool_id,
        reason_code="EXECUTION_UPSTREAM_ERROR",
        error_message=(
            "the internal write execution reported an "
            "unexpected upstream status"
        ),
        retryable=status_code >= 500,
        upstream_status=status_code,
    )


# ---------------------------------------------------------------------------
# The executor seam (mirrors the loop's tool executor seam)
# ---------------------------------------------------------------------------


class InternalWriteExecutorProtocol:
    """The seam the T11-6 executor implements."""

    state = "UNKNOWN"

    async def execute_write(
        self,
        proposal: ActionProposalV1,
        *,
        bearer_token: str | None,
        actor_id: str,
        household_id: str,
    ) -> Any:
        ...


class InternalWriteExecutor:
    """The production internal write executor of Node D (T11-6)."""

    state = "REAL"

    def __init__(
        self,
        config: WriteExecutionConfig,
    ) -> None:

        resolved = require_configured(config)

        self._base_url: str = str(resolved.base_url).rstrip("/")

        self._secret: str = resolved.secret or ""

        self._timeout_s: float = float(resolved.timeout_s)

    @property
    def timeout_s(self) -> float:
        """The write call timeout, in seconds."""

        return self._timeout_s

    def describe(self) -> dict[str, Any]:
        """A secret-free description for the startup telemetry."""

        return {
            "state": self.state,
            "base_url_present": bool(
                self._base_url
            ),
            "secret_present": bool(
                self._secret
            ),
            "timeout_s": self._timeout_s,
        }

    async def execute_write(
        self,
        proposal: ActionProposalV1,
        *,
        bearer_token: str | None,
        actor_id: str,
        household_id: str,
    ) -> WriteExecutionAttemptResult:
        """Execute exactly ONE write for ONE CONFIRMED proposal.

        The bearer credential is REQUIRED: the T07 seam performs the
        normal user authorization with it. Without a credential the
        executor fails closed BEFORE any network call.
        """

        if not bearer_token:
            return WriteExecutionAttemptResult(
                ok=False,
                tool_id=proposal.tool_id,
                reason_code="EXECUTION_CREDENTIAL_MISSING",
                error_message=(
                    "a HomePlus authorization credential is "
                    "required to execute a write"
                ),
                retryable=False,
            )

        return await attempt_write_execution(
            proposal,
            base_url=self._base_url,
            secret=self._secret,
            bearer_token=bearer_token,
            actor_id=actor_id,
            household_id=household_id,
            timeout_s=self._timeout_s,
        )


class InternalWriteExecutorDisabled:
    """The production executor while the write seam is not configured.

    It performs no network call at all: the confirm lifecycle keeps
    its T11-5 state-only behavior. It fails closed.
    """

    state = "DISABLED"

    def describe(self) -> dict[str, Any]:
        """A secret-free description for the startup telemetry."""

        return {
            "state": self.state,
            "base_url_present": False,
            "secret_present": False,
        }

    async def execute_write(
        self,
        proposal: ActionProposalV1,
        *,
        bearer_token: str | None,
        actor_id: str,
        household_id: str,
    ) -> WriteExecutionAttemptResult:

        raise WriteExecutorDisabledError(
            "the internal write executor is disabled"
        )


_WRITE_EXECUTOR: Any = InternalWriteExecutorDisabled()


def get_write_executor() -> Any:
    """The active write executor (disabled by default)."""

    return _WRITE_EXECUTOR


def set_write_executor(
    executor: Any,
) -> None:
    """Install a write executor. Used by unit tests and T11-6."""

    global _WRITE_EXECUTOR

    _WRITE_EXECUTOR = executor


def reset_write_executor() -> None:
    """Restore the disabled production executor."""

    set_write_executor(InternalWriteExecutorDisabled())


def write_executor_state() -> str:
    """The state of the active write executor."""

    return str(
        getattr(
            get_write_executor(),
            "state",
            "UNKNOWN",
        )
    )


def install_production_write_executor(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Install the real write executor when the configuration allows it.

    The installation fails closed: without a configured secret or base
    URL the disabled executor stays in place and the production node
    keeps treating every confirm as the T11-5 state-only lifecycle.
    The function never raises and never performs a network call.
    """

    try:
        config = load_write_execution_config(environ)

        if not config.configured:
            return write_executor_state()

        set_write_executor(InternalWriteExecutor(config))

    except WriteConfigError:
        return write_executor_state()

    return write_executor_state()


# ---------------------------------------------------------------------------
# T12 — internal trashed-task preflight client (Node D -> T07)
#
# D performs a trusted, server-authoritative lookup of a trashed task
# before building a restore proposal. This is an internal-only call: it
# uses the same internal write authority header and the same authenticated
# bearer credential as the write seam, but it performs a READ (no Planner
# mutation). It is never exposed through the public tool executor.
# ---------------------------------------------------------------------------

INTERNAL_PREFLIGHT_GET_TRASHED_TASK_PATH = (
    "/tools/planner.tasks.get_trashed_task/execute"
)


@dataclass(frozen=True)
class PreflightAttemptResult:
    """The normalized outcome of ONE internal preflight attempt.

    ``ok`` mirrors the authoritative T07 preflight response. A failure
    carries a deterministic, credential free reason code.
    """

    ok: bool
    tool_id: str
    task: dict[str, Any] | None = None
    reason_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    upstream_status: int | None = None


def internal_preflight_url(
    base_url: str,
    tool_id: str = "planner.tasks.get_trashed_task",
) -> str:
    """The canonical internal preflight URL of one tool.

    The tool id is percent encoded: it can never escape its path segment.
    """

    encoded = quote(str(tool_id), safe="")

    return (
        f"{base_url.rstrip('/')}"
        f"{WRITE_EXECUTE_PATH_PREFIX}/{encoded}"
        f"{EXECUTE_PATH_SUFFIX}"
    )


async def attempt_internal_preflight(
    *,
    base_url: str,
    secret: str,
    bearer_token: str,
    actor_id: str,
    household_id: str,
    task_id: str,
    timeout_s: float,
) -> PreflightAttemptResult:
    """Perform ONE internal trashed-task preflight attempt.

    The call is never retried.
    """

    tool_id = "planner.tasks.get_trashed_task"

    url = internal_preflight_url(base_url, tool_id)

    headers = build_write_headers(
        secret=secret,
        bearer_token=bearer_token,
    )

    body = {
        "taskId": task_id,
    }

    try:
        async with httpx.AsyncClient(
            timeout=timeout_s
        ) as client:

            response = await client.post(
                url,
                json=body,
                headers=headers,
            )

    except httpx.TimeoutException:
        return PreflightAttemptResult(
            ok=False,
            tool_id=tool_id,
            reason_code="PREFLIGHT_TIMEOUT",
            error_message=(
                "the internal preflight timed out"
            ),
            retryable=True,
        )

    except Exception:
        return PreflightAttemptResult(
            ok=False,
            tool_id=tool_id,
            reason_code="PREFLIGHT_UNREACHABLE",
            error_message=(
                "the internal preflight is unreachable"
            ),
            retryable=True,
        )

    return interpret_internal_preflight_response(
        tool_id=tool_id,
        status_code=response.status_code,
        content=response.content,
    )


def interpret_internal_preflight_response(
    *,
    tool_id: str,
    status_code: int,
    content: bytes | None,
) -> PreflightAttemptResult:
    """Map one T07 preflight response onto a normalized outcome."""

    payload = _read_json(content)

    upstream_code = None

    if isinstance(payload, dict):
        error = payload.get("error")

        if isinstance(error, dict) and isinstance(
            error.get("code"), str
        ):
            upstream_code = error["code"]

    if status_code == 200:
        if not isinstance(payload, dict) or payload.get(
            "ok"
        ) is not True:
            return PreflightAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="PREFLIGHT_MALFORMED_SUCCESS",
                error_message=(
                    "the internal preflight returned a "
                    "malformed success envelope"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        if payload.get("tool_id") != tool_id:
            return PreflightAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="PREFLIGHT_MALFORMED_SUCCESS",
                error_message=(
                    "the internal preflight returned a "
                    "tool mismatch"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        result = payload.get("result")

        if not isinstance(result, dict):
            return PreflightAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="PREFLIGHT_MALFORMED_SUCCESS",
                error_message=(
                    "the internal preflight returned a "
                    "malformed result"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        task = result.get("task")

        if not isinstance(task, dict):
            return PreflightAttemptResult(
                ok=False,
                tool_id=tool_id,
                reason_code="PREFLIGHT_MALFORMED_SUCCESS",
                error_message=(
                    "the internal preflight returned a "
                    "malformed task"
                ),
                retryable=False,
                upstream_status=status_code,
            )

        return PreflightAttemptResult(
            ok=True,
            tool_id=tool_id,
            task=task,
            upstream_status=status_code,
        )

    reason_by_status = {
        400: "PREFLIGHT_REQUEST_REJECTED",
        401: "PREFLIGHT_AUTH_REJECTED",
        403: "PREFLIGHT_AUTHORITY_REJECTED",
        404: "PREFLIGHT_SEAM_ABSENT",
        422: "PREFLIGHT_REQUEST_REJECTED",
    }

    if status_code in reason_by_status:
        return PreflightAttemptResult(
            ok=False,
            tool_id=tool_id,
            reason_code=(
                upstream_code if upstream_code
                else reason_by_status[status_code]
            ),
            error_message=(
                "the internal preflight was rejected"
            ),
            retryable=False,
            upstream_status=status_code,
        )

    return PreflightAttemptResult(
        ok=False,
        tool_id=tool_id,
        reason_code="PREFLIGHT_UPSTREAM_ERROR",
        error_message=(
            "the internal preflight reported an "
            "unexpected upstream status"
        ),
        retryable=status_code >= 500,
        upstream_status=status_code,
    )


__all__ = [
    "EXECUTE_BODY_FIELDS",
    "INTERNAL_PREFLIGHT_GET_TRASHED_TASK_PATH",
    "InternalWriteExecutor",
    "InternalWriteExecutorDisabled",
    "PreflightAttemptResult",
    "WriteConfigError",
    "WriteExecutionConfig",
    "WriteExecutorDisabledError",
    "WriteExecutionAttemptResult",
    "assert_write_execution_trusted",
    "attempt_internal_preflight",
    "attempt_write_execution",
    "build_write_body",
    "build_write_headers",
    "get_write_executor",
    "validate_compound_execution_result",
    "install_production_write_executor",
    "internal_preflight_url",
    "internal_write_url",
    "interpret_internal_preflight_response",
    "interpret_write_response",
    "load_write_execution_config",
    "proposal_execution_safe_result",
    "require_configured",
    "reset_write_executor",
    "set_write_executor",
    "write_executor_state",
]
