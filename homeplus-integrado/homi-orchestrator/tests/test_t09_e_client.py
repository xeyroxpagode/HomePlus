"""HOMI T09-E — the real HomePlus tool client of Node D.

The client is exercised against a REAL loopback HTTP server that plays
the HomePlus tool layer. The real user JWT is never used here: the only
credential is a sentinel constant that exists to prove that no
credential ever leaks.
"""

from __future__ import annotations

import asyncio
import json
import unittest

import t09e_support
from t09e_support import (
    T09E_SENTINEL_TOKEN,
    FakeT07Server,
    closed_port,
    t07_error,
    t07_success,
)

from homi_contracts import ErrorCode
from homi_tool_client import (
    DEFAULT_TOOL_TIMEOUT_S,
    HomePlusToolClient,
    ToolClientConfig,
    ToolClientConfigError,
    load_tool_client_config,
    require_configured,
)


def client_for(
    base_url: str,
    timeout_s: float = DEFAULT_TOOL_TIMEOUT_S,
) -> HomePlusToolClient:
    return HomePlusToolClient(
        ToolClientConfig(
            base_url=base_url,
            timeout_s=timeout_s,
        )
    )


def invoke(
    client: HomePlusToolClient,
    *,
    tool_id: str = "planner.tasks.list",
    arguments: dict | None = None,
    bearer_token: str = T09E_SENTINEL_TOKEN,
):
    return asyncio.run(
        client.invoke(
            tool_id=tool_id,
            arguments=(
                dict(arguments)
                if arguments is not None
                else {}
            ),
            actor_id=t09e_support.TEST_ACTOR_ID,
            household_id=t09e_support.TEST_HOUSEHOLD_ID,
            bearer_token=bearer_token,
        )
    )


class ClientConfigurationTests(unittest.TestCase):
    """The T09-D configuration contract is preserved verbatim."""

    def test_an_unconfigured_client_fails_closed(self) -> None:
        config = load_tool_client_config({})

        self.assertFalse(config.configured)

        with self.assertRaises(ToolClientConfigError):
            require_configured(config)

        with self.assertRaises(ToolClientConfigError):
            HomePlusToolClient(config)

    def test_the_default_timeout_is_unchanged(self) -> None:
        self.assertEqual(
            DEFAULT_TOOL_TIMEOUT_S,
            20.0,
        )

        self.assertEqual(
            load_tool_client_config({}).timeout_s,
            20.0,
        )

    def test_the_timeout_is_read_from_the_environment(self) -> None:
        config = load_tool_client_config(
            {
                "HOMI_TOOL_BASE_URL": "http://127.0.0.1:3001",
                "HOMI_TOOL_TIMEOUT_S": "7.5",
            }
        )

        self.assertEqual(config.timeout_s, 7.5)
        self.assertEqual(
            config.base_url,
            "http://127.0.0.1:3001",
        )

    def test_a_malformed_configuration_fails_closed(self) -> None:
        with self.assertRaises(ToolClientConfigError):
            load_tool_client_config(
                {"HOMI_TOOL_BASE_URL": "not-a-url"}
            )

        with self.assertRaises(ToolClientConfigError):
            load_tool_client_config(
                {
                    "HOMI_TOOL_BASE_URL": "http://127.0.0.1:3001",
                    "HOMI_TOOL_TIMEOUT_S": "-3",
                }
            )


class UrlAndHeaderTests(unittest.TestCase):
    """The invocation URL and the header placement are exact."""

    def test_the_url_is_the_canonical_invocation_path(self) -> None:
        client = client_for("http://127.0.0.1:3001")

        self.assertEqual(
            client.build_url("planner.tasks.list"),
            "http://127.0.0.1:3001"
            "/api/homi/v1/tools/planner.tasks.list/invoke",
        )

    def test_the_tool_id_is_percent_encoded(self) -> None:
        client = client_for("http://127.0.0.1:3001")

        url = client.build_url("planner.tasks.list/../evil")

        self.assertEqual(
            url,
            "http://127.0.0.1:3001"
            "/api/homi/v1/tools/"
            "planner.tasks.list%2F..%2Fevil/invoke",
        )

        self.assertNotIn("/../", url)

    def test_the_trailing_slash_of_the_base_url_is_removed(self) -> None:
        client = client_for("http://127.0.0.1:3001/")

        self.assertEqual(
            client.build_url("planner.tasks.list"),
            "http://127.0.0.1:3001"
            "/api/homi/v1/tools/planner.tasks.list/invoke",
        )

    def test_the_bearer_travels_in_the_authorization_header(
        self,
    ) -> None:
        client = client_for("http://127.0.0.1:3001")

        headers = client.build_headers(T09E_SENTINEL_TOKEN)

        self.assertEqual(
            headers.get("Authorization"),
            f"Bearer {T09E_SENTINEL_TOKEN}",
        )

    def test_the_body_carries_no_credential(self) -> None:
        client = client_for("http://127.0.0.1:3001")

        body = client.build_body(
            actor_id="actor-1",
            household_id="household-1",
            arguments={"limit": 5},
        )

        self.assertEqual(
            set(body),
            {"actor_id", "household_id", "args"},
        )

        self.assertNotIn(
            T09E_SENTINEL_TOKEN,
            json.dumps(body),
        )

        self.assertNotIn("authorization", json.dumps(body).lower())
        self.assertNotIn("bearer", json.dumps(body).lower())


class RealInvocationTests(unittest.TestCase):
    """The invocation over a real socket is exact."""

    def test_a_successful_invocation_is_accepted(self) -> None:
        with FakeT07Server(
            responses=[
                (
                    200,
                    t07_success(
                        "planner.tasks.list",
                        {"items": [{"id": "task-1"}]},
                    ),
                    0.0,
                )
            ]
        ) as server:

            client = client_for(server.base_url)

            result = invoke(
                client,
                arguments={"limit": 5},
            )

            self.assertTrue(result.ok)
            self.assertEqual(
                result.result,
                {"items": [{"id": "task-1"}]},
            )
            self.assertEqual(
                result.error_code,
                None,
            )

            request = server.last_request()

            self.assertEqual(
                request["method"],
                "POST",
            )

            self.assertEqual(
                request["path"],
                "/api/homi/v1/tools/planner.tasks.list/invoke",
            )

            self.assertEqual(
                request["headers"].get("authorization"),
                f"Bearer {T09E_SENTINEL_TOKEN}",
            )

            body = json.loads(request["body"])

            self.assertEqual(
                body,
                {
                    "actor_id": t09e_support.TEST_ACTOR_ID,
                    "household_id": (
                        t09e_support.TEST_HOUSEHOLD_ID
                    ),
                    "args": {"limit": 5},
                },
            )

    def test_the_body_never_carries_the_credential(self) -> None:
        with FakeT07Server(
            responses=[
                (200, t07_success(), 0.0)
            ]
        ) as server:

            client = client_for(server.base_url)

            invoke(client)

            request = server.last_request()

            self.assertNotIn(
                T09E_SENTINEL_TOKEN,
                request["body"],
            )

    def test_the_url_of_the_real_call_is_the_canonical_one(
        self,
    ) -> None:
        with FakeT07Server(
            responses=[
                (200, t07_success(), 0.0)
            ]
        ) as server:

            client = client_for(server.base_url)

            invoke(client, tool_id="planner.search.query")

            self.assertEqual(
                server.last_request()["path"],
                "/api/homi/v1/tools/planner.search.query/invoke",
            )


class SuccessEnvelopeValidationTests(unittest.TestCase):
    """Only the canonical success envelope is accepted."""

    def _call(
        self,
        payload: object,
    ):
        with FakeT07Server(
            responses=[(200, payload, 0.0)]
        ) as server:

            client = client_for(server.base_url)

            return invoke(client), server

    def test_a_tool_id_mismatch_is_rejected(self) -> None:
        result, _ = self._call(
            t07_success("planner.events.list")
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )
        self.assertFalse(result.retryable)

    def test_a_missing_result_is_rejected(self) -> None:
        result, _ = self._call(
            {
                "ok": True,
                "tool_id": "planner.tasks.list",
            }
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )

    def test_a_non_object_result_is_rejected(self) -> None:
        result, _ = self._call(
            {
                "ok": True,
                "tool_id": "planner.tasks.list",
                "result": ["not", "an", "object"],
            }
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )

    def test_a_false_ok_flag_is_rejected(self) -> None:
        result, _ = self._call(
            {
                "ok": False,
                "tool_id": "planner.tasks.list",
                "result": {},
            }
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )

    def test_a_non_object_body_is_rejected(self) -> None:
        result, _ = self._call([1, 2, 3])

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )

    def test_a_malformed_body_is_rejected(self) -> None:
        result, _ = self._call(
            b"<html>not json</html>"
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )
        self.assertFalse(result.retryable)

    def test_an_empty_body_is_rejected(self) -> None:
        result, _ = self._call(b"")

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )


class ErrorMappingTests(unittest.TestCase):
    """Every HomePlus failure maps deterministically."""

    def _call(
        self,
        status: int,
        payload: object,
    ):
        with FakeT07Server(
            responses=[(status, payload, 0.0)]
        ) as server:

            client = client_for(server.base_url)

            return invoke(client), server

    def test_401_is_a_non_retryable_policy_denial(self) -> None:
        result, server = self._call(
            401,
            t07_error("token_invalid"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.POLICY_DENIED,
        )
        self.assertFalse(result.retryable)
        self.assertEqual(result.upstream_status, 401)
        self.assertEqual(server.call_count, 1)

    def test_403_is_a_non_retryable_policy_denial(self) -> None:
        result, server = self._call(
            403,
            t07_error("HOMI_CONTEXT_MISMATCH"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.POLICY_DENIED,
        )
        self.assertFalse(result.retryable)
        self.assertEqual(server.call_count, 1)

    def test_400_is_a_non_retryable_invalid_request(self) -> None:
        result, server = self._call(
            400,
            t07_error("HOMI_TOOL_ARGUMENT_INVALID"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.INVALID_REQUEST,
        )
        self.assertFalse(result.retryable)
        self.assertEqual(server.call_count, 1)

    def test_404_of_an_entity_is_non_retryable(self) -> None:
        result, server = self._call(
            404,
            t07_error("task_not_found"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.VALIDATION_ERROR,
        )
        self.assertFalse(result.retryable)
        self.assertEqual(server.call_count, 1)

    def test_404_of_an_unknown_tool_is_an_invalid_request(self) -> None:
        result, _ = self._call(
            404,
            t07_error("HOMI_TOOL_NOT_FOUND"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.INVALID_REQUEST,
        )

    def test_500_is_a_provider_error(self) -> None:
        result, server = self._call(
            500,
            t07_error("HOMI_TOOL_EXECUTION_FAILED"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )
        self.assertTrue(result.retryable)
        self.assertEqual(server.call_count, 1)

    def test_503_is_a_provider_error(self) -> None:
        result, _ = self._call(
            503,
            t07_error("internal_error"),
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )

    def test_an_unexpected_status_is_a_provider_error(self) -> None:
        result, _ = self._call(
            302,
            {},
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_ERROR,
        )
        self.assertFalse(result.retryable)

    def test_no_error_message_leaks_the_upstream_body(
        self,
    ) -> None:
        secret = "SUPABASE-INTERNAL-DETAIL"

        result, _ = self._call(
            500,
            {
                "error": {
                    "code": "internal_error",
                    "message": secret,
                    "details": {"row": secret},
                }
            },
        )

        self.assertFalse(result.ok)
        self.assertNotIn(secret, result.error_message)
        self.assertNotIn(secret, json.dumps(
            {
                "message": result.error_message,
                "code": str(result.error_code),
            }
        ))

    def test_an_unsafe_upstream_code_is_not_echoed(self) -> None:
        result, _ = self._call(
            500,
            {
                "error": {
                    "code": "boom with spaces and a very long code " * 4,
                    "message": "x",
                }
            },
        )

        self.assertIsNone(result.upstream_code)


class TransportFailureTests(unittest.TestCase):
    """A transport failure is reported, never retried."""

    def test_a_timeout_is_a_retryable_provider_timeout(self) -> None:
        with FakeT07Server(
            responses=[(200, t07_success(), 2.0)]
        ) as server:

            client = client_for(server.base_url, timeout_s=0.2)

            result = invoke(client)

            self.assertFalse(result.ok)
            self.assertEqual(
                result.error_code,
                ErrorCode.PROVIDER_TIMEOUT,
            )
            self.assertTrue(result.retryable)
            self.assertEqual(server.call_count, 1)

    def test_a_refused_connection_is_a_retryable_unavailable(
        self,
    ) -> None:
        client = client_for(
            f"http://127.0.0.1:{closed_port()}",
            timeout_s=5.0,
        )

        result = invoke(client)

        self.assertFalse(result.ok)
        self.assertEqual(
            result.error_code,
            ErrorCode.PROVIDER_UNAVAILABLE,
        )
        self.assertTrue(result.retryable)

    def test_a_failed_call_is_never_retried(self) -> None:
        with FakeT07Server(
            responses=[
                (500, t07_error("internal_error"), 0.0)
            ]
        ) as server:

            client = client_for(server.base_url)

            result = invoke(client)

            self.assertFalse(result.ok)
            self.assertEqual(server.call_count, 1)


if __name__ == "__main__":
    unittest.main()
