"""HOMI T09-D/T09-E — HomePlus tool client (Node D).

T09-D defined the configuration surface of the HomePlus tool layer.
T09-E turns that surface into a REAL client:

* the T09-D configuration contract is preserved verbatim (the same
  environment variables, the same defaults, the same fail-closed rules);
* the client performs exactly ONE HTTP call per tool invocation, over
  the already installed ``httpx`` stack: no new dependency;
* the client NEVER retries: a failed call is reported, never repeated;
* the client holds no credential: the bearer token is received per call,
  used for that call only and never stored, logged or serialized;
* the client hardcodes no HomePlus host: the base URL comes from the
  environment only, and an absent base URL fails closed;
* it does not touch ``providers.json`` nor ``nodes.json``;
* it does not change the frozen timeouts (THINK 180 s, A->llama 120 s,
  other remote providers 10 s). The tool timeout is an independent
  setting.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import httpx

from homi_contracts import ErrorCode


BASE_URL_ENV = "HOMI_TOOL_BASE_URL"

TIMEOUT_ENV = "HOMI_TOOL_TIMEOUT_S"

# Recommended tool timeout for T09-E. It never replaces the frozen
# provider timeouts.
DEFAULT_TOOL_TIMEOUT_S = 20.0

MAX_TOOL_TIMEOUT_S = 120.0

ALLOWED_SCHEMES = ("http", "https")

# The canonical HomePlus Homi tool invocation path. The tool id is
# appended, percent encoded, by the client.
TOOL_INVOKE_PATH_PREFIX = "/api/homi/v1/tools"

TOOL_INVOKE_PATH_SUFFIX = "/invoke"

# The exact top level fields of a HomePlus tool invocation body. No
# other field is ever sent: the credential travels in the Authorization
# header, never in the body.
INVOKE_BODY_FIELDS: tuple[str, ...] = (
    "actor_id",
    "household_id",
    "args",
)

# Only a strict, credential free upstream code is ever echoed. Anything
# else (a message, a stack, a row) is dropped.
SAFE_UPSTREAM_CODE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class ToolClientConfigError(RuntimeError):
    """Fail-closed error raised by the tool client configuration."""


@dataclass(frozen=True)
class ToolClientConfig:
    """The resolved tool client configuration."""

    base_url: str | None
    timeout_s: float

    @property
    def configured(self) -> bool:
        """Whether the tool client has a usable base URL."""

        return bool(self.base_url)

    def describe(self) -> dict[str, object]:
        """A secret-free description of the configuration."""

        return {
            "configured": self.configured,
            "base_url_present": self.base_url is not None,
            "timeout_s": self.timeout_s,
        }


def load_tool_client_config(
    environ: Mapping[str, str] | None = None,
) -> ToolClientConfig:
    """Parse the tool client configuration from the environment.

    An absent ``HOMI_TOOL_BASE_URL`` is not an error: it yields an
    unconfigured client, which fails closed when it is used. A malformed
    base URL or a malformed timeout is an error and also fails closed.
    """

    env = os.environ if environ is None else environ

    raw_base_url = (env.get(BASE_URL_ENV) or "").strip()

    base_url: str | None = None

    if raw_base_url:
        parsed = urlparse(raw_base_url)

        if (
            parsed.scheme.lower() not in ALLOWED_SCHEMES
            or not parsed.netloc
        ):
            raise ToolClientConfigError(
                f"{BASE_URL_ENV} must be an absolute http(s) URL"
            )

        base_url = raw_base_url.rstrip("/")

    raw_timeout = (env.get(TIMEOUT_ENV) or "").strip()

    timeout_s = DEFAULT_TOOL_TIMEOUT_S

    if raw_timeout:
        try:
            timeout_s = float(raw_timeout)

        except (TypeError, ValueError) as error:
            raise ToolClientConfigError(
                f"{TIMEOUT_ENV} must be a positive number"
            ) from error

        if not math.isfinite(timeout_s):
            raise ToolClientConfigError(
                f"{TIMEOUT_ENV} must be a finite number"
            )

        if timeout_s <= 0:
            raise ToolClientConfigError(
                f"{TIMEOUT_ENV} must be a positive number"
            )

        if timeout_s > MAX_TOOL_TIMEOUT_S:
            raise ToolClientConfigError(
                f"{TIMEOUT_ENV} exceeds the maximum allowed value"
            )

    return ToolClientConfig(
        base_url=base_url,
        timeout_s=timeout_s,
    )


def require_configured(
    config: ToolClientConfig | None = None,
) -> ToolClientConfig:
    """Return a configured client or fail closed."""

    resolved = (
        config
        if config is not None
        else load_tool_client_config()
    )

    if not resolved.configured:
        raise ToolClientConfigError(
            f"{BASE_URL_ENV} is not configured"
        )

    return resolved


# ---------------------------------------------------------------------------
# T09-E — the real HomePlus tool client
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCallResult:
    """The normalized outcome of ONE HomePlus tool invocation.

    The raw HomePlus payload never appears here when the call failed:
    a failure carries a deterministic, credential free message and a
    normalized error code, never an upstream body, a stack or a row.
    """

    ok: bool
    tool_id: str
    result: dict[str, Any] | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None
    retryable: bool = False
    upstream_status: int | None = None
    upstream_code: str | None = None


def _safe_upstream_code(
    payload: Any,
) -> str | None:
    """Read the upstream error code, when it is safe to echo.

    The canonical HomePlus error envelope is
    ``{"error": {"code": ..., "message": ..., "request_id": ...}}``.
    Only ``code`` is ever read, and only when it matches a strict
    credential free pattern. The message, the request id and the
    details are never read.
    """

    if not isinstance(payload, dict):
        return None

    error = payload.get("error")

    if not isinstance(error, dict):
        return None

    code = error.get("code")

    if not isinstance(code, str):
        return None

    if SAFE_UPSTREAM_CODE.match(code) is None:
        return None

    return code


def _read_json(
    content: bytes,
) -> Any:
    """Read a JSON body, or return None when it is not JSON."""

    if not content or not content.strip():
        return None

    try:
        return json.loads(content)

    except (ValueError, UnicodeDecodeError):
        return None


class HomePlusToolClient:
    """The real, private HomePlus tool client of Node D.

    The client is a transport, not an authority:

    * the base URL comes from the trusted configuration only;
    * the tool id comes from the validated invocation plan only;
    * the bearer token comes from the request local execution context
      only, travels in the ``Authorization`` header only and is never
      stored, logged or serialized;
    * the actor and the household are transported as assertions. T07
      remains the identity authority and rejects a mismatch.
    """

    def __init__(
        self,
        config: ToolClientConfig,
    ) -> None:
        """Build a client. An unconfigured client fails closed."""

        resolved = require_configured(config)

        base_url = str(resolved.base_url).rstrip("/")

        if not base_url:
            raise ToolClientConfigError(
                f"{BASE_URL_ENV} is not configured"
            )

        self._base_url = base_url

        self._timeout_s = float(resolved.timeout_s)

    @property
    def base_url(self) -> str:
        """The trusted HomePlus base URL."""

        return self._base_url

    @property
    def timeout_s(self) -> float:
        """The tool call timeout, in seconds."""

        return self._timeout_s

    def build_url(
        self,
        tool_id: str,
    ) -> str:
        """Build the canonical invocation URL of one tool.

        The tool id is percent encoded: it can never escape its path
        segment.
        """

        encoded = quote(
            str(tool_id),
            safe="",
        )

        return (
            f"{self._base_url}"
            f"{TOOL_INVOKE_PATH_PREFIX}/{encoded}"
            f"{TOOL_INVOKE_PATH_SUFFIX}"
        )

    def build_headers(
        self,
        bearer_token: str,
    ) -> dict[str, str]:
        """Build the invocation headers.

        The credential is placed in the ``Authorization`` header and
        nowhere else.
        """

        return {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def build_body(
        self,
        *,
        actor_id: str,
        household_id: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build the exact invocation body of the HomePlus tool layer."""

        return {
            "actor_id": actor_id,
            "household_id": household_id,
            "args": dict(arguments),
        }

    async def invoke(
        self,
        *,
        tool_id: str,
        arguments: Mapping[str, Any],
        actor_id: str,
        household_id: str,
        bearer_token: str,
    ) -> ToolCallResult:
        """Invoke ONE HomePlus tool.

        The call is never retried. A transport failure, a rejected
        credential, a rejected context, an invalid request and a
        malformed success envelope are all reported deterministically.
        """

        url = self.build_url(tool_id)

        headers = self.build_headers(bearer_token)

        body = self.build_body(
            actor_id=actor_id,
            household_id=household_id,
            arguments=arguments,
        )

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s
            ) as client:

                response = await client.post(
                    url,
                    json=body,
                    headers=headers,
                )

        except httpx.TimeoutException:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.PROVIDER_TIMEOUT,
                error_message=(
                    "the HomePlus tool call timed out"
                ),
                retryable=True,
            )

        except httpx.TransportError:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.PROVIDER_UNAVAILABLE,
                error_message=(
                    "the HomePlus tool layer is unreachable"
                ),
                retryable=True,
            )

        except Exception:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.PROVIDER_ERROR,
                error_message=(
                    "the HomePlus tool call failed"
                ),
                retryable=False,
            )

        return self._interpret(
            tool_id=tool_id,
            status_code=response.status_code,
            content=response.content,
        )

    def _interpret(
        self,
        *,
        tool_id: str,
        status_code: int,
        content: bytes,
    ) -> ToolCallResult:
        """Map one HomePlus response onto a normalized outcome."""

        payload = _read_json(content)

        upstream_code = _safe_upstream_code(payload)

        if status_code == 401:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.POLICY_DENIED,
                error_message=(
                    "the HomePlus tool layer rejected the "
                    "authorization credential"
                ),
                retryable=False,
                upstream_status=status_code,
                upstream_code=upstream_code,
            )

        if status_code == 403:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.POLICY_DENIED,
                error_message=(
                    "the HomePlus tool layer rejected the "
                    "identity context"
                ),
                retryable=False,
                upstream_status=status_code,
                upstream_code=upstream_code,
            )

        if status_code == 400:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.INVALID_REQUEST,
                error_message=(
                    "the HomePlus tool layer rejected the request"
                ),
                retryable=False,
                upstream_status=status_code,
                upstream_code=upstream_code,
            )

        if status_code == 404:
            if upstream_code == "HOMI_TOOL_NOT_FOUND":
                error_code = ErrorCode.INVALID_REQUEST
                message = (
                    "the requested tool does not exist in the "
                    "HomePlus tool layer"
                )
            else:
                error_code = ErrorCode.VALIDATION_ERROR
                message = (
                    "the requested entity was not found in the "
                    "HomePlus tool layer"
                )

            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=error_code,
                error_message=message,
                retryable=False,
                upstream_status=status_code,
                upstream_code=upstream_code,
            )

        if status_code >= 500:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.PROVIDER_ERROR,
                error_message=(
                    "the HomePlus tool layer reported an internal "
                    "error"
                ),
                retryable=True,
                upstream_status=status_code,
                upstream_code=upstream_code,
            )

        if status_code != 200:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.PROVIDER_ERROR,
                error_message=(
                    "the HomePlus tool layer returned an unexpected "
                    "status"
                ),
                retryable=False,
                upstream_status=status_code,
                upstream_code=upstream_code,
            )

        return self._interpret_success(
            tool_id=tool_id,
            payload=payload,
        )

    def _interpret_success(
        self,
        *,
        tool_id: str,
        payload: Any,
    ) -> ToolCallResult:
        """Validate the canonical HomePlus success envelope.

        The integrated gateway returns ``tool_id``, canonical service
        ``data`` and execution ``meta``. The requested id must match and
        both payload sections must be objects. Anything else is a malformed
        success and is reported as a non retryable provider error.
        """

        def malformed() -> ToolCallResult:
            return ToolCallResult(
                ok=False,
                tool_id=tool_id,
                error_code=ErrorCode.PROVIDER_ERROR,
                error_message=(
                    "the HomePlus tool layer returned a malformed "
                    "success envelope"
                ),
                retryable=False,
                upstream_status=200,
            )

        if not isinstance(payload, dict):
            return malformed()

        if payload.get("tool_id") != tool_id:
            return malformed()

        result = payload.get("data")
        meta = payload.get("meta")

        if not isinstance(result, dict) or not isinstance(meta, dict):
            return malformed()

        return ToolCallResult(
            ok=True,
            tool_id=tool_id,
            result=result,
            upstream_status=200,
        )
