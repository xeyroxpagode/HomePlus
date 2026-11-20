"""HOMI T11-6 — internal write execution (Node D to T07).

Scope covered by this suite:

CONFIG (fail closed)
    env parsing, unconfigured/unusable seam, timeout bounds, the
    fallback base URL, secret free describe.

SEAM URL AND WIRE (the one HTTP call)
    canonical URL percent encoding; the exact headers (internal
    authority in its dedicated header, HomePlus credential in
    Authorization, nothing else); the exact body (proposal owned,
    caller cannot substitute arguments); ONE call, never retried;
    deterministic response interpretation for every status family.

EXECUTOR SEAM (REAL/DISABLED)
    the disabled production default; install_production_write_executor
    installs REAL only with a full configuration and never raises;
    reset restores DISABLED; the disabled executor never performs a
    call.

EXECUTION STATE MACHINE (proposal module)
    begin/complete transitions; no-confirmed rejected; stale id
    rejected; a second execution rejected; a tampered proposal
    rejected with the state untouched; result required for success;
    execution records are safe and bounded; cleanup clears them.

LOOP INTEGRATION (T11-5 preserved when DISABLED)
    a REAL executor executes EXACTLY ONE write for the current
    confirmed proposal, the answer never carries credentials and the
    public projection only carries the allow-listed task fields; a
    failed execution demotes the proposal deterministically; a
    DISABLED executor keeps the T11-5 state-only confirm behavior.
"""

from __future__ import annotations

import asyncio
import json
import threading
import unittest
from dataclasses import replace as dc_replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ORCHESTRATOR_ROOT = Path(
    __file__).resolve().parent.parent

import sys  # noqa: E402

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

sys.path.insert(
    0,
    str(ORCHESTRATOR_ROOT / "tests"),
)

import homi_tool_proposal as proposal  # noqa: E402
import homi_tool_write_execution as wexec  # noqa: E402
import t09f_support as f  # noqa: E402

import test_t11_5_proposal_action as t115  # noqa: E402


SECRET = "t11-6-internal-write-secret-unit"

BEARER = f.T09F_SENTINEL_TOKEN

FIXED_CREATED_AT = "2026-10-22T20:00:00+00:00"

P1_ARGUMENTS = {
    "title": "Comprar leche",
    "dueDate": "2026-10-23",
}

TASK_DTO = {
    "id": "task_11111111",
    "title": "Comprar leche",
    "status": "pending",
    "due_date": "2026-10-23",
    "due_time": "18:00",
    "assigned_to_member_id": None,
    "created_at": "2026-10-22T21:00:00+00:00",
    "version": 1,
    "internal_secret_field": "ROW(vacuum)",
}

CONVERSATION = "conv_t116unit_aaaa"


def build_proposal(arguments: dict | None = None):
    """A trusted proposal built through the canonical construction."""

    return proposal.build_action_proposal(
        "planner.tasks.create",
        dict(P1_ARGUMENTS if arguments is None else arguments),
        created_at=FIXED_CREATED_AT,
    )


def reset_state() -> None:
    proposal._PENDING_PROPOSALS.clear()
    proposal._PROPOSAL_REVISIONS.clear()
    proposal._TERMINAL_PROPOSALS.clear()
    proposal._EXECUTION_RECORDS.clear()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def expect_action_error(callable_, *args, **kwargs):

    try:
        callable_(*args, **kwargs)
        raise AssertionError("no error was raised")

    except proposal.ActionProposalError as error:
        return error.code


def register_confirmed(conversation_id=CONVERSATION):

    pending = build_proposal()

    proposal.register_pending_proposal(
        conversation_id,
        pending,
    )

    transitioned = proposal.apply_proposal_action(
        conversation_id,
        pending.proposal_id,
        "confirm",
    )

    return pending, transitioned


class FakeWriteExecutor:
    """A fake REAL write executor for the loop unit tests."""

    state = "REAL"

    def __init__(
        self,
        attempt=None,
        *,
        times=None,
    ) -> None:

        self.calls: list[dict] = []

        self.attempt = attempt

        self.times = times

    async def execute_write(
        self,
        execution_proposal,
        *,
        bearer_token,
        actor_id,
        household_id,
    ):
        self.calls.append({
            "proposal_id": execution_proposal.proposal_id,
            "tool_id": execution_proposal.tool_id,
            "arguments": dict(execution_proposal.arguments),
            "bearer_token": bearer_token,
            "actor_id": actor_id,
            "household_id": household_id,
        })

        if self.times is not None:
            self.times -= 1

            if self.times < 0:
                raise AssertionError("no more executions were expected")

        return self.attempt


def succeeded_attempt():

    return wexec.WriteExecutionAttemptResult(
        ok=True,
        tool_id="planner.tasks.create",
        result={"task": TASK_DTO},
    )


def failed_attempt(reason="EXECUTION_AUTHORITY_REJECTED"):

    return wexec.WriteExecutionAttemptResult(
        ok=False,
        tool_id="planner.tasks.create",
        reason_code=reason,
        error_message="rejected",
        retryable=False,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class WriteConfigTests(unittest.TestCase):
    """The env parsing of the write seam is fail closed."""

    def test_the_seam_is_unconfigured_by_default(self) -> None:

        config = wexec.load_write_execution_config({})

        self.assertFalse(config.configured)
        self.assertIsNone(config.base_url)
        self.assertIsNone(config.secret)
        self.assertEqual(config.timeout_s, 20.0)

    def test_a_full_configuration_is_resolved(self) -> None:

        config = wexec.load_write_execution_config({
            "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:3000/",
            "HOMI_INTERNAL_WRITE_SECRET": f"  {SECRET}  ",
            "HOMI_INTERNAL_WRITE_TIMEOUT_S": "30.5",
        })

        self.assertTrue(config.configured)
        self.assertEqual(config.base_url, "http://127.0.0.1:3000")
        self.assertEqual(config.secret, SECRET)
        self.assertEqual(config.timeout_s, 30.5)

    def test_a_missing_secret_leaves_the_seam_unconfigured(self) -> None:

        config = wexec.load_write_execution_config({
            "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:3000",
        })

        self.assertFalse(config.configured)
        self.assertEqual(config.base_url, "http://127.0.0.1:3000")

    def test_the_fallback_base_url_env_is_used(self) -> None:

        config = wexec.load_write_execution_config({
            "HOMI_TOOL_BASE_URL": "http://127.0.0.1:3000",
            "HOMI_INTERNAL_WRITE_SECRET": SECRET,
        })

        self.assertTrue(config.configured)
        self.assertEqual(config.base_url, "http://127.0.0.1:3000")

    def test_an_explicit_base_url_wins_over_the_fallback(self) -> None:

        config = wexec.load_write_execution_config({
            "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:4444",
            "HOMI_TOOL_BASE_URL": "http://127.0.0.1:3000",
            "HOMI_INTERNAL_WRITE_SECRET": SECRET,
        })

        self.assertEqual(config.base_url, "http://127.0.0.1:4444")

    def test_a_malformed_base_url_is_an_error(self) -> None:
        for bad in ("not-a-url", "ftp://127.0.0.1", "http://"):
            with self.assertRaises(wexec.WriteConfigError):
                wexec.load_write_execution_config({
                    "HOMI_INTERNAL_WRITE_BASE_URL": bad,
                })

    def test_a_malformed_timeout_is_an_error(self) -> None:
        for bad in ("abc", "0", "-1", "121"):
            with self.assertRaises(wexec.WriteConfigError):
                wexec.load_write_execution_config({
                    "HOMI_INTERNAL_WRITE_TIMEOUT_S": bad,
                })

    def test_the_timeout_upper_bound_is_allowed(self) -> None:

        config = wexec.load_write_execution_config({
            "HOMI_INTERNAL_WRITE_TIMEOUT_S": "120",
        })

        self.assertEqual(config.timeout_s, 120.0)

    def test_the_description_never_carries_the_secret(self) -> None:

        config = wexec.load_write_execution_config({
            "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:3000",
            "HOMI_INTERNAL_WRITE_SECRET": SECRET,
        })

        described = json.dumps(config.describe())

        self.assertNotIn(SECRET, described)

    def test_require_configured_fails_closed(self) -> None:

        with self.assertRaises(wexec.WriteConfigError):
            wexec.require_configured(
                wexec.load_write_execution_config({})
            )


# ---------------------------------------------------------------------------
# The seam wire
# ---------------------------------------------------------------------------


class WriteWireTests(unittest.TestCase):
    """The URL, the headers and the body of the ONE internal call."""

    def test_the_url_is_canonical_and_tool_scoped(self) -> None:

        self.assertEqual(
            wexec.internal_write_url("http://127.0.0.1:3000"),
            (
                "http://127.0.0.1:3000"
                "/api/homi/internal/tools/planner.tasks.create/execute"
            ),
        )

    def test_the_url_never_leaks_out_of_its_path_segment(self) -> None:

        self.assertEqual(
            wexec.internal_write_url(
                "http://127.0.0.1:3000",
                tool_id="bad/tool",
            ),
            (
                "http://127.0.0.1:3000"
                "/api/homi/internal/tools/bad%2Ftool/execute"
            ),
        )

    def test_the_headers_carry_exactly_two_authorities(self) -> None:

        headers = wexec.build_write_headers(
            secret=SECRET,
            bearer_token=BEARER,
        )

        self.assertEqual(
            headers,
            {
                "X-Homi-Internal-Write": SECRET,
                "Authorization": f"Bearer {BEARER}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def test_the_body_is_derived_from_the_confirmed_proposal(self) -> None:

        pending = build_proposal()

        body = wexec.build_write_body(
            pending,
            actor_id="actor-unit-test",
            household_id="household-unit-test",
        )

        self.assertEqual(
            body,
            {
                "proposal_id": pending.proposal_id,
                "tool_id": "planner.tasks.create",
                "actor_id": "actor-unit-test",
                "household_id": "household-unit-test",
                "args": dict(pending.arguments),
            },
        )

    def test_only_the_canonical_write_tool_is_trusted(self) -> None:

        pending = build_proposal()

        wexec.assert_write_execution_trusted(pending)

        # Restore is now an execution-capable tool (T12-6_RESTORE_DEFERRED
        # removed); a non-catalog write tool still fails closed.
        wexec.assert_write_execution_trusted(
            dc_replace(
                pending,
                tool_id="planner.tasks.restore",
            )
        )

        with self.assertRaises(wexec.WriteConfigError):
            wexec.assert_write_execution_trusted(
                dc_replace(
                    pending,
                    tool_id="planner.tasks.reopen",
                )
            )

    def test_one_call_is_performed_and_never_retried(self) -> None:

        calls: list[dict] = []

        class Handler(BaseHTTPRequestHandler):

            def do_POST(self):  # noqa: N802
                calls.append({
                    "path": self.path,
                    "headers": {
                        key.lower(): value
                        for key, value in self.headers.items()
                    },
                    "body": self.rfile.read(
                        int(self.headers.get("Content-Length") or 0)
                    ),
                })

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()

                self.wfile.write(
                    json.dumps({
                        "ok": True,
                        "tool_id": "planner.tasks.create",
                        "result": {"task": TASK_DTO},
                    }).encode("utf-8")
                )

            def log_message(self, *args):  # pragma: no cover
                pass

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            Handler,
        )

        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True,
        )
        thread.start()

        try:
            attempt = asyncio.run(
                wexec.attempt_write_execution(
                    build_proposal(),
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    secret=SECRET,
                    bearer_token=BEARER,
                    actor_id="actor-unit-test",
                    household_id="household-unit-test",
                    timeout_s=5.0,
                )
            )

        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertTrue(attempt.ok)
        self.assertIsNone(attempt.reason_code)
        self.assertEqual(len(calls), 1)

        called = calls[0]

        self.assertEqual(
            called["path"],
            "/api/homi/internal/tools/planner.tasks.create/execute",
        )
        self.assertEqual(
            called["headers"]["x-homi-internal-write"],
            SECRET,
        )
        self.assertEqual(
            called["headers"]["authorization"],
            f"Bearer {BEARER}",
        )

        body = json.loads(called["body"])

        self.assertEqual(body["tool_id"], "planner.tasks.create")
        self.assertEqual(body["args"], dict(P1_ARGUMENTS))

    def test_an_unreachable_seam_is_a_deterministic_failure(self) -> None:

        attempt = asyncio.run(
            wexec.attempt_write_execution(
                build_proposal(),
                base_url="http://127.0.0.1:1",
                secret=SECRET,
                bearer_token=BEARER,
                actor_id="actor-unit-test",
                household_id="household-unit-test",
                timeout_s=2.0,
            )
        )

        self.assertFalse(attempt.ok)
        self.assertIn(
            attempt.reason_code,
            {"EXECUTION_UNREACHABLE", "EXECUTION_TIMEOUT"},
        )
        self.assertTrue(attempt.retryable)


# ---------------------------------------------------------------------------
# The response interpretation
# ---------------------------------------------------------------------------


class WriteResponseTests(unittest.TestCase):
    """The deterministic interpretation of EVERY response family."""

    def interpret(self, status_code, body):
        return wexec.interpret_write_response(
            tool_id="planner.tasks.create",
            status_code=status_code,
            content=body,
        )

    def ok_envelope(self, tool_id="planner.tasks.create"):
        return json.dumps({
            "ok": True,
            "tool_id": tool_id,
            "result": {"task": TASK_DTO},
        }).encode("utf-8")

    def test_a_canonical_success_carries_the_service_result(self) -> None:

        attempt = self.interpret(200, self.ok_envelope())

        self.assertTrue(attempt.ok)
        self.assertEqual(attempt.result, {"task": TASK_DTO})

    def test_a_malformed_success_is_a_failure(self) -> None:
        for body in (
            b"{}",
            b'{"ok": true, "tool_id": "planner.tasks.create"}',
            b'{"ok": true, "tool_id": "planner.tasks.list", "result": {}}',
            b'{"ok": true, "tool_id": "planner.tasks.create", "result": "task"}',
        ):
            attempt = self.interpret(200, body)

            self.assertFalse(attempt.ok)
            self.assertEqual(
                attempt.reason_code,
                "EXECUTION_MALFORMED_SUCCESS",
            )
            self.assertFalse(attempt.retryable)

    def test_the_request_families_are_deterministic_failures(self) -> None:
        expected = {
            400: "EXECUTION_REQUEST_REJECTED",
            404: "EXECUTION_SEAM_ABSENT",
            422: "EXECUTION_REQUEST_REJECTED",
        }

        for status, reason in expected.items():
            attempt = self.interpret(status, b"{}")

            self.assertFalse(attempt.ok)
            self.assertEqual(attempt.reason_code, reason)
            self.assertFalse(attempt.retryable)

    def test_the_authority_families_keep_the_upstream_code(self) -> None:
        for status, canonical, fallback in (
            (401, None, "EXECUTION_AUTH_REJECTED"),
            (403, "HOMI_INTERNAL_WRITE_DENIED", None),
            (403, "planner_forbidden", None),
            (403, None, "EXECUTION_AUTHORITY_REJECTED"),
            (401, "token_invalid", None),
        ):
            body = (
                json.dumps({"error": {"code": canonical}}).encode()
                if canonical
                else b"{}"
            )

            attempt = self.interpret(status, body)

            self.assertFalse(attempt.ok)
            self.assertEqual(
                attempt.reason_code,
                canonical or fallback,
            )
            self.assertFalse(attempt.retryable)

    def test_an_unexpected_upstream_status_is_opaque(self) -> None:
        for status in (500, 503, 599):
            attempt = self.interpret(status, b"boom")

            self.assertFalse(attempt.ok)
            self.assertEqual(
                attempt.reason_code,
                "EXECUTION_UPSTREAM_ERROR",
            )

        self.assertTrue(self.interpret(503, b"").retryable)

    def test_an_unknown_status_family_is_canonical_and_opaque(self) -> None:

        body = json.dumps({
            "error": {"code": "idempotency_conflict"},
        }).encode()

        attempt = self.interpret(409, body)

        self.assertFalse(attempt.ok)
        self.assertEqual(
            attempt.reason_code,
            "EXECUTION_UPSTREAM_ERROR",
        )
        self.assertFalse(attempt.retryable)

    def test_a_non_json_success_body_is_a_malformed_success(self) -> None:

        attempt = self.interpret(200, b"<html>ok</html>")

        self.assertFalse(attempt.ok)
        self.assertEqual(
            attempt.reason_code,
            "EXECUTION_MALFORMED_SUCCESS",
        )


# ---------------------------------------------------------------------------
# The executor seam
# ---------------------------------------------------------------------------


class WriteExecutorSeamTests(unittest.TestCase):
    """The REAL/DISABLED executor seam of the confirm lifecycle."""

    def setUp(self) -> None:

        reset_state()

        self._original = wexec.get_write_executor()

    def tearDown(self) -> None:

        reset_state()

        wexec.reset_write_executor()

        if self._original is not None:
            wexec.set_write_executor(self._original)

    def test_the_production_default_executor_is_disabled(self) -> None:

        executor = wexec.get_write_executor()

        self.assertEqual(wexec.write_executor_state(), "DISABLED")
        self.assertIsInstance(
            executor,
            wexec.InternalWriteExecutorDisabled,
        )

    def test_the_disabled_executor_fails_closed(self) -> None:

        with self.assertRaises(wexec.WriteExecutorDisabledError):
            asyncio.run(
                wexec.get_write_executor().execute_write(
                    build_proposal(),
                    bearer_token=BEARER,
                    actor_id="actor-unit-test",
                    household_id="household-unit-test",
                )
            )

    def test_the_installation_fails_closed_without_a_secret(self) -> None:

        state = wexec.install_production_write_executor({
            "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:3000",
        })

        self.assertEqual(state, "DISABLED")

        state = wexec.install_production_write_executor({})

        self.assertEqual(state, "DISABLED")

    def test_the_installation_never_raises_on_malformed_config(self) -> None:

        state = wexec.install_production_write_executor({
            "HOMI_INTERNAL_WRITE_BASE_URL": "not-a-url",
            "HOMI_INTERNAL_WRITE_SECRET": SECRET,
        })

        self.assertEqual(state, "DISABLED")

    def test_the_installation_installs_a_real_executor(self) -> None:

        state = wexec.install_production_write_executor({
            "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:3000",
            "HOMI_INTERNAL_WRITE_SECRET": SECRET,
        })

        self.assertEqual(state, "REAL")

        executor = wexec.get_write_executor()

        self.assertEqual(executor.state, "REAL")

        described = json.dumps(executor.describe())

        self.assertNotIn(SECRET, described)

    def test_the_reset_restores_the_disabled_executor(self) -> None:

        wexec.install_production_write_executor({
            "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:3000",
            "HOMI_INTERNAL_WRITE_SECRET": SECRET,
        })

        wexec.reset_write_executor()

        self.assertEqual(wexec.write_executor_state(), "DISABLED")

    def test_a_real_executor_requires_a_credential(self) -> None:

        executor = wexec.InternalWriteExecutor(
            wexec.load_write_execution_config({
                "HOMI_INTERNAL_WRITE_BASE_URL": "http://127.0.0.1:3000",
                "HOMI_INTERNAL_WRITE_SECRET": SECRET,
            }),
        )

        attempt = asyncio.run(
            executor.execute_write(
                build_proposal(),
                bearer_token=None,
                actor_id="actor-unit-test",
                household_id="household-unit-test",
            )
        )

        self.assertFalse(attempt.ok)
        self.assertEqual(
            attempt.reason_code,
            "EXECUTION_CREDENTIAL_MISSING",
        )


# ---------------------------------------------------------------------------
# The execution state machine
# ---------------------------------------------------------------------------


class ExecutionStateMachineTests(unittest.TestCase):
    """CONFIRMED -> EXECUTING -> SUCCEEDED | FAILED, deterministically."""

    def setUp(self) -> None:

        reset_state()

    def tearDown(self) -> None:

        reset_state()

    def test_a_confirmed_proposal_can_begin_one_execution(self) -> None:

        pending, _ = register_confirmed()

        executing = proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        self.assertEqual(executing.status, "EXECUTING")
        self.assertEqual(
            executing.proposal_id,
            pending.proposal_id,
        )
        self.assertIsNone(proposal.get_pending_proposal(CONVERSATION))
        self.assertEqual(
            proposal.get_terminal_proposal(CONVERSATION).status,
            "EXECUTING",
        )

    def test_no_confirmed_proposal_cannot_begin_one_execution(self) -> None:

        self.assertEqual(
            expect_action_error(
                proposal.begin_proposal_execution,
                CONVERSATION,
                "prop_0aa9c5bb12b59bb8",
            ),
            "PROPOSAL_EXECUTION_NO_CONFIRMED",
        )

    def test_an_unknown_id_is_rejected_before_any_lookup(self) -> None:

        self.assertEqual(
            expect_action_error(
                proposal.begin_proposal_execution,
                CONVERSATION,
                "   ",
            ),
            "PROPOSAL_EXECUTION_UNKNOWN_ID",
        )

        self.assertEqual(
            expect_action_error(
                proposal.begin_proposal_execution,
                CONVERSATION,
                None,
            ),
            "PROPOSAL_EXECUTION_UNKNOWN_ID",
        )

    def test_a_stale_id_is_rejected_when_a_fresh_confirmed_exists(self) -> None:

        first, _ = register_confirmed()

        second = proposal.build_action_proposal(
            "planner.tasks.create",
            {"title": "Otra tarea"},
            created_at=FIXED_CREATED_AT,
        )

        proposal.register_pending_proposal(
            CONVERSATION,
            second,
        )

        proposal.apply_proposal_action(
            CONVERSATION,
            second.proposal_id,
            "confirm",
        )

        self.assertEqual(
            expect_action_error(
                proposal.begin_proposal_execution,
                CONVERSATION,
                first.proposal_id,
            ),
            "PROPOSAL_EXECUTION_STALE",
        )

    def test_one_proposal_cannot_execute_twice_after_terminal_success(self) -> None:

        pending, _ = register_confirmed()

        proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        proposal.complete_proposal_execution(
            CONVERSATION,
            succeeded=True,
            result={"task": TASK_DTO},
        )

        self.assertEqual(
            expect_action_error(
                proposal.begin_proposal_execution,
                CONVERSATION,
                pending.proposal_id,
            ),
            "PROPOSAL_EXECUTION_NOT_CONFIRMED",
        )

    def test_an_executing_proposal_reuses_its_execution_identity(self) -> None:

        pending, _ = register_confirmed()

        first = proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        second = proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        self.assertEqual(second.status, "EXECUTING")
        self.assertEqual(
            proposal.get_execution_id(CONVERSATION),
            proposal.get_execution_id(CONVERSATION),
        )

    def test_a_tampered_proposal_fails_the_gates_with_the_state_untouched(self) -> None:  # noqa: E501

        pending, _ = register_confirmed()

        tampered = dc_replace(
            proposal.get_terminal_proposal(CONVERSATION),
            confirmation="OPTIONAL",
        )

        proposal._TERMINAL_PROPOSALS[
            proposal._conv_key(CONVERSATION)
        ] = tampered

        self.assertEqual(
            expect_action_error(
                proposal.begin_proposal_execution,
                CONVERSATION,
                pending.proposal_id,
            ),
            "PROPOSAL_EXECUTION_GATES_FAILED",
        )

        self.assertEqual(
            proposal.get_terminal_proposal(CONVERSATION).status,
            "CONFIRMED",
        )

    def test_succeeding_promotes_the_proposal_and_stores_a_safe_record(self) -> None:

        pending, _ = register_confirmed()

        proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        terminal = proposal.complete_proposal_execution(
            CONVERSATION,
            succeeded=True,
            result={"task": TASK_DTO},
        )

        self.assertEqual(terminal.status, "SUCCEEDED")

        record = proposal.get_execution_record(CONVERSATION)

        self.assertEqual(record["proposal_id"], pending.proposal_id)
        self.assertEqual(record["tool_id"], "planner.tasks.create")
        self.assertEqual(record["status"], "SUCCEEDED")
        self.assertIsNone(record["reason"])

        self.assertEqual(
            set(record["result"]),
            proposal.EXECUTION_RESULT_SAFE_KEYS,
        )
        self.assertNotIn("internal_secret_field", record["result"])
        self.assertEqual(record["result"]["id"], TASK_DTO["id"])
        self.assertEqual(record["result"]["title"], TASK_DTO["title"])
        self.assertEqual(record["result"]["status"], "pending")

    def test_a_success_requires_an_authoritative_result(self) -> None:

        register_confirmed()

        proposal.begin_proposal_execution(
            CONVERSATION,
            proposal.get_terminal_proposal(
                CONVERSATION
            ).proposal_id,
        )

        self.assertEqual(
            expect_action_error(
                proposal.complete_proposal_execution,
                CONVERSATION,
                succeeded=True,
            ),
            "PROPOSAL_EXECUTION_RESULT_INVALID",
        )

    def test_failing_demotes_the_proposal_with_a_deterministic_reason(self) -> None:

        pending, _ = register_confirmed()

        proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        terminal = proposal.complete_proposal_execution(
            CONVERSATION,
            succeeded=False,
            reason="EXECUTION_AUTHORITY_REJECTED",
        )

        self.assertEqual(terminal.status, "FAILED")

        record = proposal.get_execution_record(CONVERSATION)

        self.assertEqual(record["status"], "FAILED")
        self.assertIsNone(record["result"])
        self.assertEqual(
            record["reason"],
            "EXECUTION_AUTHORITY_REJECTED",
        )

    def test_completing_without_an_executing_proposal_is_rejected(self) -> None:

        self.assertEqual(
            expect_action_error(
                proposal.complete_proposal_execution,
                CONVERSATION,
                succeeded=False,
                reason="EXECUTION_TIMEOUT",
            ),
            "PROPOSAL_EXECUTION_NOT_EXECUTING",
        )

        register_confirmed()

        self.assertEqual(
            expect_action_error(
                proposal.complete_proposal_execution,
                CONVERSATION,
                succeeded=False,
                reason="EXECUTION_TIMEOUT",
            ),
            "PROPOSAL_EXECUTION_NOT_EXECUTING",
        )

    def test_the_cleanup_clears_the_execution_records(self) -> None:

        pending, _ = register_confirmed()

        proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        proposal.complete_proposal_execution(
            CONVERSATION,
            succeeded=True,
            result={"task": TASK_DTO},
        )

        self.assertIsNotNone(
            proposal.get_execution_record(CONVERSATION)
        )

        proposal.clear_all_proposal_state(CONVERSATION)

        self.assertIsNone(
            proposal.get_execution_record(CONVERSATION)
        )

    def test_version_conflict_is_recorded_as_failed(self) -> None:
        """A version conflict from the write seam demotes the proposal to FAILED
        with the canonical version_conflict_v2 reason code."""
        pending, _ = register_confirmed()

        proposal.begin_proposal_execution(
            CONVERSATION,
            pending.proposal_id,
        )

        terminal = proposal.complete_proposal_execution(
            CONVERSATION,
            succeeded=False,
            reason="version_conflict_v2",
        )

        self.assertEqual(terminal.status, "FAILED")

        record = proposal.get_execution_record(CONVERSATION)

        self.assertEqual(record["status"], "FAILED")
        self.assertEqual(record["reason"], "version_conflict_v2")
        self.assertIsNone(record["result"])


# ---------------------------------------------------------------------------
# The loop integration
# ---------------------------------------------------------------------------


class LoopWriteExecutionTests(t115.LoopLifecycleTestBase):
    """The CONFIRM pivot only runs through the REAL write executor."""

    suffix = "t116loop"

    def setUp(self) -> None:

        super().setUp()

        self.executor.result = {"task": TASK_DTO}

        self.__original = wexec.get_write_executor()

        self.write_executor = FakeWriteExecutor(
            succeeded_attempt(),
        )

        wexec.set_write_executor(self.write_executor)

    def tearDown(self) -> None:

        wexec.reset_write_executor()

        if self.__original is not None:
            wexec.set_write_executor(self.__original)

        super().tearDown()

    def conversation_id(self) -> str:

        return f"conv_{self.suffix}_aaaaaaaa"

    def run_write_confirm(
        self,
        decision,
        **kwargs,
    ):
        kwargs.setdefault(
            "authorization",
            f"Bearer {BEARER}",
        )

        return self.run_turn(
            decision,
            **kwargs,
        )

    def test_a_confirmed_write_is_executed_exactly_once(self) -> None:

        body = self.create_pending()

        envelope = self.run_write_confirm(t115.NL_CONFIRM)

        self.assertEqual(envelope.status.value, "SUCCESS", envelope)

        result = envelope.result

        self.assertEqual(result["decision_kind"], "action_executed")
        self.assertEqual(
            result["answer"],
            "Creé la tarea en tu hogar.",
        )
        self.assertEqual(
            result["tool_id"],
            "planner.tasks.create",
        )
        self.assertEqual(result["proposal_action"], "confirmed")

        self.assertEqual(
            result["proposal"]["proposal"]["status"],
            "VERIFIED",
        )
        self.assertEqual(
            result["proposal"]["proposal"]["proposal_id"],
            body["proposal_id"],
        )

        execution = result["execution_result"]

        self.assertEqual(execution["id"], TASK_DTO["id"])
        self.assertEqual(execution["title"], TASK_DTO["title"])
        self.assertEqual(execution["status"], "pending")
        self.assertEqual(
            execution["due_date"],
            TASK_DTO["due_date"],
        )
        self.assertNotIn("internal_secret_field", execution)

        # Exactly ONE write, tied to the confirmed proposal.
        self.assertEqual(len(self.write_executor.calls), 1)

        call = self.write_executor.calls[0]

        self.assertEqual(call["proposal_id"], body["proposal_id"])
        self.assertEqual(call["tool_id"], "planner.tasks.create")
        self.assertEqual(
            call["arguments"],
            t115.P1_ARGUMENTS,
        )
        self.assertEqual(call["bearer_token"], BEARER)
        self.assertEqual(call["actor_id"], "actor-unit-test")
        self.assertEqual(call["household_id"], "household-unit-test")

        # The READ tool executor is engaged once for verification.
        self.assertEqual(
            len(self.executor.calls),
            1,
        )

        # The terminal registry is SUCCEEDED and the proposal is terminal.
        self.assertIsNone(self.pending())
        self.assertEqual(self.terminal().status, "VERIFIED")

    def test_the_credential_never_reaches_the_write_response(self) -> None:

        self.create_pending()

        envelope = self.run_write_confirm(t115.NL_CONFIRM)

        serialized = json.dumps(
            envelope.model_dump(mode="json"),
            default=str,
        )

        self.assertNotIn(BEARER, serialized)
        self.assertNotIn("internal_secret_field", serialized)

    def test_a_failed_execution_is_a_deterministic_error(self) -> None:

        self.create_pending()

        self.write_executor = FakeWriteExecutor(failed_attempt())

        wexec.set_write_executor(self.write_executor)

        envelope = self.run_write_confirm(t115.NL_CONFIRM)

        self.assertEqual(envelope.status.value, "ERROR")

        self.assertEqual(
            envelope.error.details["reason"],
            "EXECUTION_AUTHORITY_REJECTED",
        )

        self.assertEqual(len(self.write_executor.calls), 1)

        self.assertEqual(self.terminal().status, "FAILED")

        record = proposal.get_execution_record(self.conversation_id())

        self.assertEqual(
            record["reason"],
            "EXECUTION_AUTHORITY_REJECTED",
        )
        self.assertIsNone(record["result"])

    def test_a_failed_execution_is_never_retried_by_the_lifecycle(self) -> None:

        self.create_pending()

        self.write_executor = FakeWriteExecutor(failed_attempt())

        wexec.set_write_executor(self.write_executor)

        first = self.run_write_confirm(t115.NL_CONFIRM)

        self.assertEqual(first.status.value, "ERROR")

        second = self.run_write_confirm(
            t115.NL_CONFIRM_NO_PENDING,
        )

        self.assertEqual(second.status.value, "SUCCESS")
        self.assertEqual(
            second.result["answer"],
            "No hay una propuesta pendiente que confirmar.",
        )
        self.assertEqual(
            second.result["decision_kind"],
            "action_proposal",
        )
        self.assertEqual(
            len(self.write_executor.calls),
            1,
        )

    def test_a_timeout_failure_demotes_the_proposal(self) -> None:

        self.create_pending()

        self.write_executor = FakeWriteExecutor(
            failed_attempt("EXECUTION_TIMEOUT"),
        )

        wexec.set_write_executor(self.write_executor)

        envelope = self.run_write_confirm(t115.NL_CONFIRM)

        self.assertEqual(envelope.status.value, "ERROR")
        self.assertEqual(
            envelope.error.details["reason"],
            "EXECUTION_TIMEOUT",
        )
        self.assertEqual(self.terminal().status, "FAILED")

    def test_the_disabled_executor_keeps_the_t11_5_behavior(self) -> None:

        self.create_pending()

        wexec.set_write_executor(
            wexec.InternalWriteExecutorDisabled(),
        )

        envelope = self.run_write_confirm(t115.NL_CONFIRM)

        self.assertEqual(envelope.status.value, "SUCCESS")

        result = envelope.result

        self.assertEqual(result["decision_kind"], "action_proposal")
        self.assertEqual(
            result["answer"],
            "Confirmaste la propuesta.",
        )
        self.assertEqual(result["proposal_action"], "confirmed")
        self.assertEqual(
            result["proposal"]["proposal"]["status"],
            "CONFIRMED",
        )
        self.assertNotIn("execution_result", result)
        self.assertEqual(
            len(self.write_executor.calls),
            0,
        )

    def test_the_disabled_executor_never_performs_a_call(self) -> None:

        self.create_pending()

        disabled = wexec.InternalWriteExecutorDisabled()

        wexec.set_write_executor(disabled)

        envelope = self.run_write_confirm(t115.NL_CONFIRM)

        self.assertEqual(
            len(self.write_executor.calls),
            0,
        )

        with self.assertRaises(wexec.WriteExecutorDisabledError):
            asyncio.run(
                disabled.execute_write(
                    build_proposal(),
                    bearer_token=BEARER,
                    actor_id="actor-unit-test",
                    household_id="household-unit-test",
                )
            )


if __name__ == "__main__":  # pragma: no cover

    unittest.main()
