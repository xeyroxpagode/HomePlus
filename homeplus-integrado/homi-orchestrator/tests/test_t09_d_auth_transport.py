"""HOMI T09-D — secure HomePlus authorization transport."""

from __future__ import annotations

import logging
import unittest

import t09_support
from support import patched
from t09_support import (
    SENTINEL_TOKEN,
    make_tool_request,
    run_invoke_with_tools,
    tool_transport,
)


class LogCapture(logging.Handler):

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record) -> None:
        self.messages.append(record.getMessage())


class AuthorizationTransportTests(unittest.TestCase):

    def setUp(self) -> None:
        self.capture = LogCapture()

        t09_support.loop.TOOL_LOGGER.addHandler(self.capture)

    def tearDown(self) -> None:
        t09_support.loop.TOOL_LOGGER.removeHandler(self.capture)

    def _run(
        self,
        decision,
        *,
        authorization=None,
        posts=None,
    ):
        transport = tool_transport(
            decision=decision,
            posts=posts,
        )

        result = run_invoke_with_tools(
            make_tool_request(suffix="t09dauth"),
            transport,
            authorization=authorization,
        )

        return result, transport

    def test_authorization_is_captured_outside_the_envelope(
        self,
    ) -> None:
        posts: list[dict] = []

        result, _ = self._run(
            {
                "decision": "direct_response",
                "answer": "Buenos Aires",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
            authorization=f"Bearer {SENTINEL_TOKEN}",
            posts=posts,
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            len(posts),
            1,
        )

        body = str(posts[0]["json"])

        self.assertNotIn("Authorization", body)
        self.assertNotIn("authorization", body)
        self.assertNotIn(SENTINEL_TOKEN, body)

    def test_sentinel_token_never_reaches_the_a_request(
        self,
    ) -> None:
        posts: list[dict] = []

        self._run(
            {
                "decision": "direct_response",
                "answer": "Buenos Aires",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
            authorization=f"Bearer {SENTINEL_TOKEN}",
            posts=posts,
        )

        payload = posts[0]["json"]["payload"]

        serialized = t09_support.serialized(payload)

        self.assertEqual(
            serialized.count(SENTINEL_TOKEN),
            0,
        )

        self.assertNotIn("token", serialized)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("bearer", serialized.lower())

    def test_sentinel_token_is_never_logged(self) -> None:
        self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
            },
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        for message in self.capture.messages:
            self.assertNotIn(SENTINEL_TOKEN, message)

    def test_sentinel_token_is_never_in_error_details(self) -> None:
        result, _ = self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
            },
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        serialized = t09_support.serialized(result)

        self.assertNotIn(SENTINEL_TOKEN, serialized)

        for message in self.capture.messages:
            self.assertNotIn(SENTINEL_TOKEN, message)

    def test_direct_response_works_without_a_token(self) -> None:
        result, _ = self._run(
            {
                "decision": "direct_response",
                "answer": "La capital de Argentina es Buenos Aires.",
                "question": None,
                "tool_id": None,
                "arguments": None,
            }
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            result.result.get("answer"),
            "La capital de Argentina es Buenos Aires.",
        )

        self.assertEqual(
            result.result.get("decision_kind"),
            "direct_response",
        )

    def test_clarify_works_without_a_token(self) -> None:
        result, _ = self._run(
            {
                "decision": "clarify",
                "answer": None,
                "question": "Que tareas quieres revisar?",
                "tool_id": None,
                "arguments": None,
            }
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        self.assertEqual(
            result.result.get("answer"),
            "Que tareas quieres revisar?",
        )

        self.assertEqual(
            result.result.get("decision_kind"),
            "clarify",
        )

    def test_tool_request_without_a_token_is_policy_denied(
        self,
    ) -> None:
        result, _ = self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
            }
        )

        self.assertEqual(
            getattr(result, "status", None),
            "ERROR",
        )

        self.assertEqual(
            result.error.code.value,
            "POLICY_DENIED",
        )

        self.assertFalse(result.error.retryable)

    def test_tool_request_without_a_token_never_reaches_t07(
        self,
    ) -> None:
        transport = tool_transport(
            decision={
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
            }
        )

        result = run_invoke_with_tools(
            make_tool_request(suffix="t09dnoauth"),
            transport,
        )

        self.assertEqual(
            result.error.code.value,
            "POLICY_DENIED",
        )

        self.assertEqual(
            len(transport.calls),
            2,
        )

        self.assertEqual(
            transport.calls[0][0],
            "GET",
        )

        self.assertEqual(
            transport.calls[1],
            ("POST", "http://homi-a:8011/invoke"),
        )

    def test_malformed_authorization_header_fails_closed(
        self,
    ) -> None:
        result, _ = self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
            },
            authorization="Basic dXNlcjpwYXNz",
        )

        self.assertEqual(
            result.error.code.value,
            "POLICY_DENIED",
        )

    def test_empty_authorization_header_fails_closed(self) -> None:
        result, _ = self._run(
            {
                "decision": "tool_request",
                "answer": None,
                "question": None,
                "tool_id": "planner.tasks.list",
                "arguments": {"limit": 5},
            },
            authorization="Bearer   ",
        )

        self.assertEqual(
            result.error.code.value,
            "POLICY_DENIED",
        )

    def test_caller_cannot_smuggle_a_credential_into_the_payload(
        self,
    ) -> None:
        posts: list[dict] = []

        request = make_tool_request(
            suffix="t09dsmuggle",
            payload={
                "text": "hola",
                "authorization": SENTINEL_TOKEN,
                "access_token": SENTINEL_TOKEN,
            },
        )

        transport = tool_transport(
            decision={
                "decision": "direct_response",
                "answer": "ok",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
            posts=posts,
        )

        result = run_invoke_with_tools(
            request,
            transport,
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            getattr(result, "status", None),
            "SUCCESS",
        )

        body = str(posts[0]["json"])

        self.assertNotIn(SENTINEL_TOKEN, body)

        self.assertNotIn(
            "access_token",
            posts[0]["json"]["payload"],
        )

        self.assertEqual(
            set(posts[0]["json"]["payload"].keys()),
            {
                "text",
                "mode",
                "phase",
                "tool_catalog",
                "catalog_digest",
                "decision_schema_version",
                "decision_schema_digest",
            },
        )

    def test_bearer_extraction_is_opaque(self) -> None:
        extract = t09_support.loop.extract_bearer_token

        self.assertEqual(
            extract(f"Bearer {SENTINEL_TOKEN}"),
            SENTINEL_TOKEN,
        )

        self.assertEqual(
            extract(f"bearer {SENTINEL_TOKEN}"),
            SENTINEL_TOKEN,
        )

        self.assertIsNone(extract(None))
        self.assertIsNone(extract(""))
        self.assertIsNone(extract("Bearer"))
        self.assertIsNone(extract("Basic abc"))
        self.assertIsNone(extract(SENTINEL_TOKEN))

    def test_the_asgi_stack_delivers_the_authorization_header(
        self,
    ) -> None:
        from fastapi.testclient import TestClient

        posts: list[dict] = []

        transport = tool_transport(
            decision={
                "decision": "direct_response",
                "answer": "ok",
                "question": None,
                "tool_id": None,
                "arguments": None,
            },
            posts=posts,
        )

        request = make_tool_request(suffix="t09dasgi")

        with patched(transport):
            with TestClient(t09_support.orch.app) as client:
                response = client.post(
                    "/invoke",
                    json=request.model_dump(mode="json"),
                    headers={
                        "Authorization": f"Bearer {SENTINEL_TOKEN}",
                    },
                )

        self.assertEqual(response.status_code, 200)

        body = response.json()

        self.assertEqual(
            body.get("status"),
            "SUCCESS",
        )

        self.assertEqual(
            len(posts),
            1,
        )

        self.assertNotIn(
            SENTINEL_TOKEN,
            str(posts[0]["json"]),
        )

        self.assertNotIn(
            "Authorization",
            str(posts[0]["json"]),
        )


if __name__ == "__main__":
    unittest.main()
