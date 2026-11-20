"""Shared helpers for the HOMI T09-E test suite (Node D).

This module is test-only. It adds a REAL local HTTP server that plays
the role of the HomePlus tool layer, so the T09-E client, the URL
construction, the header placement and the response validation are
exercised over a real socket instead of a mocked transport.

The real user JWT is NEVER used in an automated test. The only
credential that appears in this suite is a sentinel constant that exists
to prove that a credential never leaks.
"""

from __future__ import annotations

import contextlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest import mock

ORCHESTRATOR_ROOT = Path(
    __file__
).resolve().parent.parent

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

import httpx  # noqa: E402

import app as orch  # noqa: E402
import homi_tool_loop as loop  # noqa: E402

from homi_contracts import RequestContext, RequestEnvelope  # noqa: E402
from homi_tool_loop import (  # noqa: E402
    ToolExecutionContext,
    ToolInvocationPlan,
)


# The captured real client class. It is captured before any patch, so a
# test can still perform a REAL HTTP call while the Node A leg is
# faked.
REAL_ASYNC_CLIENT = httpx.AsyncClient


# A credential that must never reach Node A, never reach a log and
# never reach the public response.
T09E_SENTINEL_TOKEN = (
    "T09E_SENTINEL_CREDENTIAL_MUST_NEVER_LEAK"
)

# A second, distinct sentinel used by the log scan.
T09E_LOG_SENTINEL = (
    "T09E_LOG_SENTINEL_MUST_NEVER_BE_LOGGED"
)

TEST_ACTOR_ID = "actor-t09e-unit"

TEST_HOUSEHOLD_ID = "household-t09e-unit"

TEST_CATALOG_DIGEST = "0" * 64


# ---------------------------------------------------------------------------
# The fake HomePlus tool layer
# ---------------------------------------------------------------------------


class FakeT07Server:
    """A real, loopback only HTTP server that plays T07.

    Every request is recorded: method, path, headers and raw body. The
    response of each call is programmed by the test.
    """

    def __init__(
        self,
        responses: list[tuple[int, Any, float]] | None = None,
    ) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses: list[tuple[int, Any, float]] = list(
            responses or []
        )
        self._default: tuple[int, Any, float] = (
            200,
            {"ok": True, "tool_id": "x", "result": {}},
            0.0,
        )
        self._lock = threading.Lock()

        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                return

            def handle_error(
                self,
                request: Any,
                client_address: Any,
            ) -> None:
                # A client that gives up (the timeout test) must not
                # print a traceback.
                return

            def do_POST(self) -> None:
                length = int(
                    self.headers.get("Content-Length") or 0
                )

                raw = (
                    self.rfile.read(length)
                    if length
                    else b""
                )

                record = {
                    "method": "POST",
                    "path": self.path,
                    "headers": {
                        key.lower(): value
                        for key, value in self.headers.items()
                    },
                    "body": raw.decode("utf-8", "replace"),
                }

                with server._lock:
                    server.requests.append(record)

                    if server._responses:
                        response = server._responses.pop(0)
                    else:
                        response = server._default

                status, payload, delay = response

                if delay:
                    time.sleep(delay)

                data = (
                    payload
                    if isinstance(payload, bytes)
                    else json.dumps(payload).encode("utf-8")
                )

                self.send_response(status)
                self.send_header(
                    "Content-Type",
                    "application/json",
                )
                self.send_header(
                    "Content-Length",
                    str(len(data)),
                )
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            Handler,
        )

        self.port = int(
            self._server.server_address[1]
        )

        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(
                poll_interval=0.02
            ),
            daemon=True,
        )

    def start(self) -> "FakeT07Server":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def call_count(self) -> int:
        with self._lock:
            return len(self.requests)

    def last_request(self) -> dict[str, Any]:
        with self._lock:
            return self.requests[-1]

    def __enter__(self) -> "FakeT07Server":
        return self.start()

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()


def closed_port() -> int:
    """Return a loopback port that refuses every connection."""

    import socket

    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as probe:
        probe.bind(("127.0.0.1", 0))

        port = int(probe.getsockname()[1])

    return port


# ---------------------------------------------------------------------------
# Node A double
# ---------------------------------------------------------------------------


def a_decision_response(
    decision: dict[str, Any],
    *,
    node_id: str = "homi-a",
    provider_id: str = "think-primary",
) -> dict[str, Any]:
    """Build the Node A structured decision response."""

    return {
        "contract_version": "1.0.0",
        "correlation": {
            "request_id": "req_t09e_aaaaaaaa",
            "trace_id": "trc_t09e_aaaaaaaa",
            "turn_id": "turn_t09e_aaaaaaaa",
            "conversation_id": "conv_t09e_aaaaaaaa",
        },
        "node_id": node_id,
        "provider_id": provider_id,
        "capability": "think",
        "status": "SUCCESS",
        "timestamp": "2026-10-20T16:00:00+00:00",
        "result": {"decision": decision},
    }


# The default synthesized answer of the Node A double.
DEFAULT_SYNTHESIS_ANSWER = (
    "Tenes una tarea pendiente: Hacer las compras."
)


def a_synthesis_response(
    answer: str = DEFAULT_SYNTHESIS_ANSWER,
    *,
    node_id: str = "homi-a",
    provider_id: str = "think-primary",
) -> dict[str, Any]:
    """Build the Node A synthesis response."""

    return {
        "contract_version": "1.0.0",
        "correlation": {
            "request_id": "req_t09e_aaaaaaaa",
            "trace_id": "trc_t09e_aaaaaaaa",
            "turn_id": "turn_t09e_aaaaaaaa",
            "conversation_id": "conv_t09e_aaaaaaaa",
        },
        "node_id": node_id,
        "provider_id": provider_id,
        "capability": "think",
        "status": "SUCCESS",
        "timestamp": "2026-10-20T16:00:00+00:00",
        "result": {"answer": answer},
    }


class FakeResponse:
    """A minimal response double for the Node A leg."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self.content = content

    def json(self) -> Any:
        return json.loads(
            self.content.decode("utf-8")
        )


class RoutingAsyncClient:
    """An async client that fakes Node A and calls T07 for real.

    The Node A leg is answered by a double, so the test never depends
    on a live model. The T07 leg performs a REAL HTTP call against the
    fake HomePlus server, so the URL, the headers and the body of the
    invocation are proven over a real socket.
    """

    def __init__(
        self,
        *,
        a_handler: Callable[..., Any],
        timeout: Any = None,
        a_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self._a_handler = a_handler
        self._timeout = timeout
        self._real: Any = None
        self.a_calls: list[dict[str, Any]] = (
            a_calls if a_calls is not None else []
        )

    async def __aenter__(self) -> "RoutingAsyncClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        if self._real is not None:
            await self._real.aclose()

        return False

    def _real_client(self) -> Any:
        if self._real is None:
            self._real = REAL_ASYNC_CLIENT(
                timeout=self._timeout
            )

        return self._real

    async def get(
        self,
        url: str,
        **kwargs: Any,
    ) -> Any:
        return self._a_handler("GET", url, **kwargs)

    async def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> Any:
        if "/api/homi/v1/tools/" in url:
            return await self._real_client().post(
                url,
                **kwargs,
            )

        self.a_calls.append(
            {
                "url": url,
                "json": kwargs.get("json"),
                "headers": kwargs.get("headers"),
            }
        )

        return self._a_handler("POST", url, **kwargs)


def patched_routing_client(
    a_handler: Callable[..., Any],
    a_calls: list[dict[str, Any]] | None = None,
) -> Any:
    """Patch the httpx client so Node A is faked and T07 is real."""

    return mock.patch.object(
        orch.httpx,
        "AsyncClient",
        lambda **kwargs: RoutingAsyncClient(
            a_handler=a_handler,
            timeout=kwargs.get("timeout"),
            a_calls=a_calls,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_tool_request(
    *,
    text: str = "Quelles sont mes taches pendientes ?",
    suffix: str = "t09e",
) -> RequestEnvelope:
    """Build a T09 structured request."""

    return RequestEnvelope(
        context=RequestContext(
            request_id=f"req_{suffix}_aaaaaaaa",
            trace_id=f"trc_{suffix}_aaaaaaaa",
            turn_id=f"turn_{suffix}_aaaaaaaa",
            conversation_id=f"conv_{suffix}_aaaaaaaa",
            actor_id=TEST_ACTOR_ID,
            household_id=TEST_HOUSEHOLD_ID,
            timestamp="2026-10-20T16:00:00+00:00",
        ),
        capability="think",
        operation="infer_with_tools",
        payload={"text": text},
    )


def make_plan(
    *,
    tool_id: str = "planner.tasks.list",
    arguments: dict[str, Any] | None = None,
    tool_call_id: str = "tcall_t09e_0000000000000000000000000000",
) -> ToolInvocationPlan:
    """Build a validated invocation plan."""

    return ToolInvocationPlan(
        tool_call_id=tool_call_id,
        tool_id=tool_id,
        arguments=(
            dict(arguments)
            if arguments is not None
            else {}
        ),
        catalog_digest=TEST_CATALOG_DIGEST,
    )


def make_context(
    *,
    bearer_token: str | None = T09E_SENTINEL_TOKEN,
    actor_id: str = TEST_ACTOR_ID,
    household_id: str = TEST_HOUSEHOLD_ID,
) -> ToolExecutionContext:
    """Build a request local execution context."""

    return ToolExecutionContext(
        request_id="req_t09e_aaaaaaaa",
        trace_id="trc_t09e_aaaaaaaa",
        turn_id="turn_t09e_aaaaaaaa",
        conversation_id="conv_t09e_aaaaaaaa",
        actor_id=actor_id,
        household_id=household_id,
        bearer_token=bearer_token,
    )


@contextlib.contextmanager
def installed_executor(
    executor: Any,
) -> Iterator[Any]:
    """Install an executor for the duration of a test."""

    loop.set_tool_executor(executor)

    try:
        yield executor

    finally:
        loop.reset_tool_executor()


def tool_decision(
    tool_id: str = "planner.tasks.list",
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Node A decision of a tool request."""

    return {
        "decision": "tool_request",
        "answer": None,
        "question": None,
        "tool_id": tool_id,
        "arguments": (
            dict(arguments)
            if arguments is not None
            else {}
        ),
    }


def t07_success(
    tool_id: str = "planner.tasks.list",
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical HomePlus success envelope."""

    return {
        "tool_id": tool_id,
        "data": (
            dict(result)
            if result is not None
            else {"items": []}
        ),
        "meta": {},
    }


def t07_error(
    code: str,
    message: str = "denied",
) -> dict[str, Any]:
    """Build the canonical HomePlus error envelope."""

    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": "req-t07e-unit",
        },
    }
