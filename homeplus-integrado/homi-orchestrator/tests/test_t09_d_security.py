"""HOMI T09-D — security properties of the Node D seam."""

from __future__ import annotations

import hashlib
import logging
import unittest
from pathlib import Path

import t09_support
from t09_support import (
    SENTINEL_TOKEN,
    FakeExecutor,
    installed_executor,
    make_tool_request,
    run_invoke_with_tools,
    tool_transport,
)


HOMI_ROOT = Path(r"C:\Homi")

T08_FREEZE_DIR = (
    HOMI_ROOT / "baseline" / "t08-think-final-v1"
)

NODE_D_MANIFEST = (
    T08_FREEZE_DIR / "NODE_D_MANIFEST_SHA256.txt"
)

# app.py is the single file that T09-D is allowed to change: it receives
# the T09 dispatch and the Authorization header seam.
T09_D_ALLOWED_CHANGES = frozenset(
    {
        str(HOMI_ROOT / "orchestrator" / "app.py"),
    }
)


class LogCapture(logging.Handler):

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record) -> None:
        self.messages.append(record.getMessage())


def decision(
    kind: str,
    *,
    answer=None,
    question=None,
    tool_id=None,
    arguments=None,
) -> dict:
    return {
        "decision": kind,
        "answer": answer,
        "question": question,
        "tool_id": tool_id,
        "arguments": arguments,
    }


class SecurityTests(unittest.TestCase):

    def setUp(self) -> None:
        self.capture = LogCapture()

        t09_support.loop.TOOL_LOGGER.addHandler(self.capture)

    def tearDown(self) -> None:
        t09_support.loop.TOOL_LOGGER.removeHandler(self.capture)

    def test_no_credential_reaches_the_request_the_logs_or_the_errors(
        self,
    ) -> None:
        cases = [
            decision(
                "direct_response",
                answer="ok",
            ),
            decision(
                "clarify",
                question="que?",
            ),
            decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            ),
        ]

        for payload in cases:
            with self.subTest(decision=payload["decision"]):
                posts: list[dict] = []

                transport = tool_transport(
                    decision=payload,
                    posts=posts,
                )

                executor = FakeExecutor()

                with installed_executor(executor):
                    result = run_invoke_with_tools(
                        make_tool_request(suffix="t09dsec"),
                        transport,
                        authorization=(
                            f"Bearer {SENTINEL_TOKEN}"
                        ),
                    )

                serialized_request = t09_support.serialized(
                    posts[0]["json"]
                )

                serialized_result = t09_support.serialized(result)

                self.assertNotIn(
                    SENTINEL_TOKEN,
                    serialized_request,
                )

                self.assertNotIn(
                    SENTINEL_TOKEN,
                    serialized_result,
                )

                for message in self.capture.messages:
                    self.assertNotIn(SENTINEL_TOKEN, message)

    def test_the_a_payload_carries_no_identity_or_transport_field(
        self,
    ) -> None:
        posts: list[dict] = []

        transport = tool_transport(
            decision=decision(
                "direct_response",
                answer="ok",
            ),
            posts=posts,
        )

        run_invoke_with_tools(
            make_tool_request(suffix="t09dident"),
            transport,
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        payload = posts[0]["json"]["payload"]

        serialized = t09_support.serialized(payload)

        for forbidden in [
            "actor_id",
            "household_id",
            "membership_id",
            "role",
            "authorization",
            "access_token",
            "bearer",
            "homeplus",
            "http://",
            "https://",
        ]:
            self.assertNotIn(
                forbidden,
                serialized,
                forbidden,
            )

    def test_the_model_cannot_supply_a_homeplus_url(self) -> None:
        result = run_invoke_with_tools(
            make_tool_request(suffix="t09durl"),
            tool_transport(
                decision=decision(
                    "tool_request",
                    tool_id="planner.tasks.list",
                    arguments={
                        "url": "http://homeplus.invalid/api",
                    },
                )
            ),
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertEqual(
            result.error.code.value,
            "PROVIDER_ERROR",
        )

        self.assertNotIn(
            "homeplus.invalid",
            t09_support.serialized(result),
        )

    def test_the_sanitization_gate_rejects_a_poisoned_payload(
        self,
    ) -> None:
        from homi_contracts import RequestEnvelope

        from t09_support import make_request

        loop = t09_support.loop

        poisoned = RequestEnvelope(
            context=make_request(
                suffix="t09dpoison"
            ).context,
            capability="think",
            operation="infer",
            payload={
                "text": "hola",
                "actor_id": "attacker",
            },
        )

        with self.assertRaises(loop.ToolLoopError):
            loop.assert_a_request_is_sanitized(poisoned)

        leaky = RequestEnvelope(
            context=make_request(
                suffix="t09dpoison2"
            ).context,
            capability="think",
            operation="infer",
            payload={
                "text": SENTINEL_TOKEN,
            },
        )

        with self.assertRaises(loop.ToolLoopError):
            loop.assert_a_request_is_sanitized(
                leaky,
                secret_values=(SENTINEL_TOKEN,),
            )

    def test_the_sanitization_gate_accepts_the_real_internal_request(
        self,
    ) -> None:
        loop = t09_support.loop

        internal = loop.build_internal_request(
            make_tool_request(suffix="t09dgate"),
            "hola",
        )

        loop.assert_a_request_is_sanitized(
            internal,
            secret_values=(SENTINEL_TOKEN,),
        )

    def test_the_telemetry_record_has_only_the_allowed_keys(self) -> None:
        transport = tool_transport(
            decision=decision(
                "tool_request",
                tool_id="planner.tasks.list",
                arguments={"limit": 5},
            )
        )

        run_invoke_with_tools(
            make_tool_request(suffix="t09dtele"),
            transport,
            authorization=f"Bearer {SENTINEL_TOKEN}",
        )

        self.assertTrue(self.capture.messages)

        import json

        for message in self.capture.messages:
            record = json.loads(message)

            self.assertEqual(
                set(record.keys()),
                set(t09_support.loop.TOOL_TELEMETRY_FIELDS),
            )

            self.assertNotIn("payload", record)
            self.assertNotIn("arguments", record)
            self.assertNotIn("answer", record)
            self.assertNotIn("tool_result", record)
            self.assertNotIn("actor_id", record)
            self.assertNotIn("household_id", record)

    def test_the_telemetry_never_carries_the_user_text(self) -> None:
        transport = tool_transport(
            decision=decision(
                "direct_response",
                answer="ok",
            )
        )

        run_invoke_with_tools(
            make_tool_request(
                suffix="t09dtxt",
                text="TEXTO PRIVADO DEL USUARIO",
            ),
            transport,
        )

        for message in self.capture.messages:
            self.assertNotIn(
                "TEXTO PRIVADO DEL USUARIO",
                message,
            )


class T08FreezeIntegrityTests(unittest.TestCase):

    def _manifest_entries(self):
        entries = []

        for line in NODE_D_MANIFEST.read_text(
            encoding="utf-8"
        ).splitlines():
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split()

            if len(parts) < 2:
                continue

            digest = parts[0]

            if len(digest) != 64:
                continue

            if any(
                char not in "0123456789abcdefABCDEF"
                for char in digest
            ):
                continue

            path = parts[1]

            entries.append((digest, path))

        return entries

    def test_the_frozen_node_d_files_are_unchanged(self) -> None:
        changed = []

        for digest, path in self._manifest_entries():
            target = Path(path)

            if not target.is_file():
                changed.append((path, "missing"))
                continue

            actual = hashlib.sha256(
                target.read_bytes()
            ).hexdigest().upper()

            if actual != digest.upper():
                changed.append((path, "modified"))

        self.assertEqual(
            [
                path
                for path, _ in changed
                if path not in T09_D_ALLOWED_CHANGES
            ],
            [],
        )

    def test_the_t08_baseline_artefacts_are_unchanged(self) -> None:
        digest_line = (
            T08_FREEZE_DIR
            / "T08_FREEZE_V1.sha256.txt"
        ).read_text(encoding="utf-8").strip()

        expected, name = digest_line.split()

        target = T08_FREEZE_DIR / name

        actual = hashlib.sha256(
            target.read_bytes()
        ).hexdigest().upper()

        self.assertEqual(
            actual,
            expected.upper(),
        )

    def test_the_frozen_contracts_are_unchanged(self) -> None:
        entries = self._manifest_entries()

        contracts = [
            (digest, path)
            for digest, path in entries
            if str(HOMI_ROOT / "contracts") in path
        ]

        self.assertTrue(contracts)

        for digest, path in contracts:
            target = Path(path)

            actual = hashlib.sha256(
                target.read_bytes()
            ).hexdigest().upper()

            self.assertEqual(
                actual,
                digest.upper(),
                path,
            )


if __name__ == "__main__":
    unittest.main()
