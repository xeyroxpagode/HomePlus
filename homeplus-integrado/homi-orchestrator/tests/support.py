from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable
from unittest import mock

ORCHESTRATOR_ROOT = Path(
    __file__
).resolve().parent.parent

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

import app as orch  # noqa: E402

from homi_contracts import (  # noqa: E402
    RequestContext,
    RequestEnvelope,
)

PROVIDER_ENDPOINT = "http://homi-a:8011/invoke"

CONTROL_PLANE_RESOLVE = (
    "http://127.0.0.1:8020/resolve/think"
)


def make_request(
    *,
    capability: str = "think",
    operation: str = "infer",
    text: str = (
        "Responde unicamente con la palabra: HOMI"
    ),
    suffix: str = "unit",
    payload: dict[str, Any] | None = None,
) -> RequestEnvelope:

    return RequestEnvelope(
        context=RequestContext(
            request_id=f"req_{suffix}_aaaaaaaa",
            trace_id=f"trc_{suffix}_aaaaaaaa",
            turn_id=f"turn_{suffix}_aaaaaaaa",
            conversation_id=f"conv_{suffix}_aaaaaaaa",
            actor_id="actor-unit-test",
            household_id="household-unit-test",
            timestamp="2026-10-20T16:00:00+00:00",
        ),
        capability=capability,
        operation=operation,
        payload=(
            payload
            if payload is not None
            else {"text": text}
        ),
    )


def correlation_of(
    request: RequestEnvelope,
) -> dict[str, str]:

    return {
        "request_id": request.context.request_id,
        "trace_id": request.context.trace_id,
        "turn_id": request.context.turn_id,
        "conversation_id": (
            request.context.conversation_id
        ),
    }


def success_envelope(
    request: RequestEnvelope,
    *,
    node_id: str = "homi-a",
    provider_id: str = "think-primary",
    capability: str = "think",
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:

    return {
        "contract_version": "1.0.0",
        "correlation": correlation_of(request),
        "node_id": node_id,
        "provider_id": provider_id,
        "capability": capability,
        "status": "SUCCESS",
        "timestamp": "2026-10-20T16:00:00+00:00",
        "result": (
            result
            if result is not None
            else {"answer": "HOMI"}
        ),
    }


def error_envelope(
    request: RequestEnvelope,
    *,
    code: str = "CAPABILITY_NOT_FOUND",
    message: str = "homi-a does not provide see",
    retryable: bool = False,
    node_id: str | None = "homi-a",
    provider_id: str | None = "think-primary",
) -> dict[str, Any]:

    return {
        "contract_version": "1.0.0",
        "correlation": correlation_of(request),
        "status": "ERROR",
        "timestamp": "2026-10-20T16:00:00+00:00",
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "node_id": node_id,
            "provider_id": provider_id,
            "details": {},
        },
    }


def resolution_document(
    *,
    capability: str = "think",
    node_id: str = "homi-a",
    provider_id: str = "think-primary",
    implementation: str = "real-v1",
    endpoint: str = PROVIDER_ENDPOINT,
    effective_state: str = "READY",
    extra_provider: dict[str, Any] | None = None,
) -> dict[str, Any]:

    provider: dict[str, Any] = {
        "provider_id": provider_id,
        "capability": capability,
        "node_id": node_id,
        "state": "READY",
        "implementation": implementation,
        "endpoint": endpoint,
        "node_reachable": True,
        "effective_state": effective_state,
    }

    if extra_provider:
        provider.update(extra_provider)

    return {
        "capability": capability,
        "selected_node": {
            "node_id": node_id,
            "role": "THINK",
            "base_url": "http://homi-a:8010",
            "node_state": "AVAILABLE",
            "node_ready": True,
            "capability_status": "READY",
            "provider": provider_id,
        },
        "provider": provider,
        "timestamp": "2026-10-20T16:00:00+00:00",
    }


class FakeResponse:
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


def json_response(
    document: Any,
    status_code: int = 200,
) -> FakeResponse:

    return FakeResponse(
        status_code=status_code,
        content=json.dumps(
            document
        ).encode("utf-8"),
    )


class FakeAsyncClient:
    def __init__(
        self,
        transport: "FakeTransport",
        timeout: Any,
    ) -> None:
        self.transport = transport
        self.timeout = timeout

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(
        self,
        *exc_info: Any,
    ) -> bool:
        return False

    async def get(
        self,
        url: str,
        **kwargs: Any,
    ) -> Any:
        return self.transport.handle(
            "GET",
            url,
            **kwargs,
        )

    async def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> Any:
        return self.transport.handle(
            "POST",
            url,
            **kwargs,
        )


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.client_timeouts: list[Any] = []
        self.get_handler: Callable[..., Any] | None = None
        self.post_handler: Callable[..., Any] | None = None

    def make_client(
        self,
        timeout: Any = None,
    ) -> FakeAsyncClient:
        self.client_timeouts.append(timeout)
        return FakeAsyncClient(self, timeout)

    def handle(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        self.calls.append((method, url))

        handler = (
            self.get_handler
            if method == "GET"
            else self.post_handler
        )

        if handler is None:
            raise AssertionError(
                f"unexpected {method} call to {url}"
            )

        return handler(method, url, **kwargs)


def patched(
    transport: FakeTransport,
):
    return mock.patch.object(
        orch.httpx,
        "AsyncClient",
        lambda **kwargs: transport.make_client(
            kwargs.get("timeout")
        ),
    )


def run_invoke(
    request: RequestEnvelope,
    transport: FakeTransport,
):
    with patched(transport):
        return asyncio.run(orch.invoke(request))


def default_transport(
    *,
    resolution: dict[str, Any] | None = None,
    provider_response: Any = None,
) -> FakeTransport:

    transport = FakeTransport()

    resolution = (
        resolution
        if resolution is not None
        else resolution_document()
    )

    transport.get_handler = (
        lambda method, url, **kwargs: json_response(
            resolution
        )
    )

    if provider_response is None:
        provider_response = json_response({})

    transport.post_handler = (
        lambda method, url, **kwargs: provider_response
    )

    return transport
