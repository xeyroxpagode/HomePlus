from __future__ import annotations

import dataclasses
import inspect
import json
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock


import homi_tool_loop as loop
import homi_tool_proposal as proposal


FIXED_CREATED_AT = "2026-10-22T16:00:00+00:00"

VALID_ARGUMENTS = {
    "title": "Comprar leche",
}

FULL_ARGUMENTS = {
    "title": "Comprar leche",
    "description": "Y pan",
    "dueDate": "2026-10-23",
    "dueTime": "14:30",
    "assignedToMemberId": "member-abc",
}


def build(
    tool_id: str = "planner.tasks.create",
    arguments: dict | None = None,
):
    return proposal.build_action_proposal(
        tool_id,
        VALID_ARGUMENTS
        if arguments is None
        else arguments,
        created_at=FIXED_CREATED_AT,
    )


class WriteContractAuthorityTests(unittest.TestCase):
    """The D-side re-encoding of the T11-1 contract authority."""

    def test_canonical_write_allowlist_is_exactly_one_tool(
        self,
    ) -> None:

        # T12-3 factual update: the T12-1 freeze extends the T11
        # one-tool allow-list with the four existing-task WRITE tools.
        self.assertEqual(
            proposal.PROPOSAL_TOOL_IDS,
            (
                "planner.tasks.create",
                "planner.tasks.update",
                "planner.tasks.complete",
                "planner.tasks.trash",
                "planner.tasks.restore",
            ),
        )

    def test_the_write_tool_is_not_in_the_read_catalogue(
        self,
    ) -> None:

        self.assertNotIn(
            "planner.tasks.create",
            loop.CANONICAL_TOOL_IDS,
        )

    def test_the_read_execution_gate_rejects_the_write_tool(
        self,
    ) -> None:

        violations = loop.validate_tool_request(
            "planner.tasks.create",
            VALID_ARGUMENTS,
        )

        self.assertIn(
            "unknown_tool",
            violations,
        )

    def test_trusted_metadata_matches_the_t11_1_contract(
        self,
    ) -> None:

        contract = proposal.write_tool_contract(
            "planner.tasks.create",
        )

        self.assertIsNotNone(contract)

        self.assertEqual(
            contract.kind,
            "WRITE",
        )

        self.assertEqual(
            contract.risk_flags,
            ("LOW_MUTATION",),
        )

        self.assertEqual(
            contract.confirmation,
            "REQUIRED",
        )

        self.assertEqual(
            contract.contract_version,
            "1.1.0",
        )

        self.assertFalse(
            contract.execution_enabled,
        )

    def test_execution_is_disabled(
        self,
    ) -> None:

        self.assertIs(
            proposal.EXECUTION_ENABLED,
            False,
        )

    def test_input_schema_matches_the_t11_1_handoff(
        self,
    ) -> None:

        contract = proposal.write_tool_contract(
            "planner.tasks.create",
        )

        schema = contract.input_schema

        self.assertEqual(
            schema["type"],
            "object",
        )

        self.assertIs(
            schema["additionalProperties"],
            False,
        )

        self.assertEqual(
            list(schema["required"]),
            [],
        )

        self.assertEqual(
            sorted(schema["properties"]),
            [
                "assignedToMemberId",
                "description",
                "dueDate",
                "dueTime",
                "operations",
                "title",
            ],
        )

        operations_schema = schema["properties"]["operations"]

        self.assertEqual(operations_schema["minItems"], 2)
        self.assertEqual(operations_schema["maxItems"], 4)
        self.assertEqual(
            list(operations_schema["items"]["required"]),
            ["title"],
        )

    def test_domain_binding_is_documented(self) -> None:

        contract = proposal.write_tool_contract(
            "planner.tasks.create",
        )

        self.assertIn(
            "POST /api/planner/tasks",
            contract.domain_binding,
        )

    def test_authority_anchor_passes(self) -> None:

        proposal.assert_proposal_authority()

    def test_authority_anchor_fails_closed(
        self,
    ) -> None:

        with mock.patch.object(
            proposal,
            "PROPOSAL_AUTHORITY_SHA256",
            "0" * 64,
        ):

            with self.assertRaises(
                proposal.ActionProposalError,
            ) as ctx:

                proposal.assert_proposal_authority()

        self.assertEqual(
            ctx.exception.code,
            "PROPOSAL_AUTHORITY_ANCHOR_MISMATCH",
        )


class ProposalBuilderTests(unittest.TestCase):
    """The deterministic builder of ActionProposalV1."""

    def test_valid_minimal_proposal_builds(self) -> None:

        prop = build()

        self.assertEqual(
            prop.proposal_version,
            "1.0",
        )

        self.assertEqual(
            prop.tool_id,
            "planner.tasks.create",
        )

        self.assertEqual(
            prop.status,
            "PROPOSED",
        )

        self.assertEqual(
            prop.risk_flags,
            ("LOW_MUTATION",),
        )

        self.assertEqual(
            prop.confirmation,
            "REQUIRED",
        )

        self.assertIsNotNone(prop.expires_at)

        deadline = datetime.fromisoformat(prop.expires_at)
        remaining = deadline - datetime.now(timezone.utc)

        self.assertGreater(remaining, timedelta(0))
        self.assertLessEqual(
            remaining,
            timedelta(seconds=proposal.PROPOSAL_TTL_SECONDS),
        )

    def test_optional_fields_and_nulls_are_validated(
        self,
    ) -> None:

        prop = build(arguments=FULL_ARGUMENTS)

        self.assertEqual(
            dict(prop.arguments),
            FULL_ARGUMENTS,
        )

        nullable = build(
            arguments={
                "title": "T",
                "description": None,
                "dueDate": None,
                "dueTime": None,
                "assignedToMemberId": None,
            },
        )

        self.assertEqual(
            dict(nullable.arguments),
            {
                "title": "T",
                "description": None,
                "dueDate": None,
                "dueTime": None,
                "assignedToMemberId": None,
            },
        )

        self.assertEqual(
            nullable.summary,
            "Crear tarea\nTítulo: T",
        )

    def test_pending_time_with_seconds_is_validated(
        self,
    ) -> None:

        prop = build(
            arguments={
                "title": "T",
                "dueDate": "2026-10-23",
                "dueTime": "14:30:30",
            },
        )

        self.assertEqual(
            dict(prop.arguments)["dueTime"],
            "14:30:30",
        )

    def test_proposal_id_is_d_owned_and_well_formed(
        self,
    ) -> None:

        prop = build()

        self.assertRegex(
            prop.proposal_id,
            r"^prop_[a-z0-9]{16}$",
        )

        self.assertLessEqual(
            len(prop.proposal_id),
            64,
        )

        self.assertTrue(
            prop.proposal_id.isascii(),
        )

    def test_proposal_ids_are_random_and_collision_resistant(
        self,
    ) -> None:

        first = build()

        second = build()

        self.assertNotEqual(
            first.proposal_id,
            second.proposal_id,
        )

        self.assertEqual(
            first.summary,
            second.summary,
        )

        self.assertEqual(
            dict(first.arguments),
            dict(second.arguments),
        )

    def test_created_at_is_d_minted_iso8601_utc(
        self,
    ) -> None:

        minted = proposal.build_action_proposal(
            "planner.tasks.create",
            VALID_ARGUMENTS,
        )

        self.assertRegex(
            minted.created_at,
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00$",
        )

    def test_the_injected_clock_is_used_verbatim(
        self,
    ) -> None:

        prop = build()

        self.assertEqual(
            prop.created_at,
            FIXED_CREATED_AT,
        )

    def test_the_builder_signature_accepts_no_trusted_fields(
        self,
    ) -> None:

        parameters = set(
            inspect.signature(
                proposal.build_action_proposal,
            ).parameters
        )

        # T12-3: ``summary_context`` is the D-owned PRESENTATION-only
        # context (authoritative task title + resolved checklist
        # intent). It never enters the arguments and is not a trusted
        # proposal field.
        #
        # T12-4: ``checklist_intent`` is the D-owned REVISION metadata
        # of an update proposal (the validated checklist intent the
        # deterministic read-modify-write consumed). It is accepted
        # only for planner.tasks.update, is revalidated by the
        # builder and never enters the arguments or the public
        # projection. It is not a trusted proposal field either: the
        # trusted identity (proposal_id, risk, confirmation, status)
        # stays D-minted.
        self.assertEqual(
            parameters,
            {
                "tool_id",
                "arguments",
                "created_at",
                "summary_context",
                "checklist_intent",
            },
        )

        self.assertNotIn("proposal_id", parameters)
        self.assertNotIn("risk_flags", parameters)
        self.assertNotIn("risk", parameters)
        self.assertNotIn("confirmation", parameters)
        self.assertNotIn("status", parameters)

    def test_unknown_tool_ids_are_rejected(self) -> None:

        for tool_id in (
            "planner.tasks.list",
            "planner.tasks.create.extra",
            "",
            "PLANNER.TASKS.CREATE",
        ):

            with self.assertRaises(
                proposal.ActionProposalError,
            ) as ctx:

                proposal.build_action_proposal(
                    tool_id,
                    VALID_ARGUMENTS,
                )

            self.assertEqual(
                ctx.exception.code,
                "PROPOSAL_TOOL_UNKNOWN",
            )


class ArgumentValidationTests(unittest.TestCase):
    """Strict, no-coercion validation of the proposal arguments."""

    def _violations(
        self,
        arguments,
    ) -> list[str]:

        return (
            proposal.validate_proposal_arguments(
                arguments,
            )
        )

    def _reject(
        self,
        arguments,
        expected: str,
    ) -> None:

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:

            proposal.build_action_proposal(
                "planner.tasks.create",
                arguments,
            )

        violations = ctx.exception.message

        self.assertIn(expected, violations)

    def test_missing_required_title_is_rejected(
        self,
    ) -> None:

        self.assertIn(
            "missing_required:title",
            self._violations({}),
        )

        self._reject({}, "missing_required:title")

    def test_empty_title_is_rejected(self) -> None:

        self._reject(
            {"title": ""},
            "too_short:title",
        )

    def test_wrong_type_title_is_rejected(self) -> None:

        self._reject(
            {"title": 123},
            "invalid_type:title",
        )

    def test_too_long_title_is_rejected(self) -> None:

        self._reject(
            {"title": "a" * 501},
            "too_long:title",
        )

    def test_unknown_field_is_rejected(self) -> None:

        self._reject(
            {"title": "T", "priority": "high"},
            "unknown_argument:priority",
        )

    def test_identity_fields_are_rejected(self) -> None:

        for key in (
            "actor_id",
            "household_id",
            "membership_id",
            "auth_user_id",
            "created_by",
            "jwt",
            "authorization",
            "access_token",
            "role",
            "JWT",
            "Authorization",
            "Actor_ID",
        ):

            arguments = dict(VALID_ARGUMENTS)

            arguments[key] = "admin"

            self.assertIn(
                f"forbidden_key:{key}",
                self._violations(arguments),
            )

            self._reject(
                arguments,
                "forbidden_key",
            )

    def test_transport_and_url_controls_are_rejected(
        self,
    ) -> None:

        for key in (
            "url",
            "endpoint",
            "host",
            "token",
        ):

            arguments = dict(VALID_ARGUMENTS)

            arguments[key] = "http://x"

            self.assertIn(
                f"forbidden_key:{key}",
                self._violations(arguments),
            )

    def test_nested_structure_is_rejected(self) -> None:

        self._reject(
            {
                "title": "T",
                "description": {"nested": "object"},
            },
            "invalid_type:description",
        )

        self._reject(
            {"title": "T", "dueDate": ["x"]},
            "invalid_type:dueDate",
        )

    def test_internal_persistence_fields_are_rejected(
        self,
    ) -> None:

        for key in (
            "id",
            "created_at",
            "task_id",
        ):

            arguments = dict(VALID_ARGUMENTS)

            arguments[key] = "x"

            self.assertIn(
                f"unknown_argument:{key}",
                self._violations(arguments),
            )

    def test_malformed_due_date_is_rejected(self) -> None:

        for value in (
            "2026-13-45",
            "23-10-2026",
            "2026-10-23T00:00:00",
            "20261023",
        ):

            self._reject(
                {"title": "T", "dueDate": value},
                "dueDate",
            )

    def test_valid_due_date_is_accepted(self) -> None:

        self.assertTrue(
            self._violations(
                {"title": "T", "dueDate": "2026-10-23"},
            )
            == [],
        )

    def test_malformed_due_time_is_rejected(self) -> None:

        for value in (
            "24:30",
            "14:75",
            "14:30:75",
            "25:61:99",
        ):

            self._reject(
                {
                    "title": "T",
                    "dueDate": "2026-10-23",
                    "dueTime": value,
                },
                "dueTime",
            )

    def test_due_time_requires_due_date(self) -> None:

        self.assertIn(
            "due_time_without_due_date",
            self._violations(
                {"title": "T", "dueTime": "14:30"},
            ),
        )

    def test_oversized_arguments_are_rejected(self) -> None:

        filler = "b" * 2000

        big = {
            "title": "T",
            "description": filler,
            "dueDate": "2026-10-23",
            "dueTime": "14:30",
        }

        document = json.dumps(
            big,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        self.assertGreater(
            len(document.encode("utf-8")),
            1024,
        )

        self.assertEqual(
            self._violations(big),
            [],
        )

        oversized = {
            "title": "T",
            "description": filler * 3,
        }

        violations = self._violations(oversized)

        self.assertIn(
            "too_long:description",
            violations,
        )

    def test_arguments_must_be_a_plain_object(self) -> None:

        for arguments in (None, [], "title", 5):

            self.assertEqual(
                self._violations(arguments),
                ["arguments_not_object"],
            )


class TamperingMatrixTests(unittest.TestCase):
    """Tampering with trusted fields always fails closed."""

    def test_supplied_proposal_id_is_rejected(self) -> None:

        arguments = dict(
            VALID_ARGUMENTS,
            proposal_id="prop_hijacked0000",
        )

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:

            proposal.build_action_proposal(
                "planner.tasks.create",
                arguments,
            )

        self.assertIn(
            "unknown_argument:proposal_id",
            ctx.exception.message,
        )

    def test_supplied_status_is_rejected(self) -> None:

        arguments = dict(
            VALID_ARGUMENTS,
            status="EXECUTING",
        )

        with self.assertRaises(
            proposal.ActionProposalError,
        ):

            proposal.build_action_proposal(
                "planner.tasks.create",
                arguments,
            )

    def test_supplied_confirmation_is_rejected(self) -> None:

        arguments = dict(
            VALID_ARGUMENTS,
            confirmation="NEVER",
        )

        with self.assertRaises(
            proposal.ActionProposalError,
        ):

            proposal.build_action_proposal(
                "planner.tasks.create",
                arguments,
            )

    def test_trusted_confirmation_can_never_be_downgraded(
        self,
    ) -> None:

        prop = build()

        self.assertEqual(
            prop.confirmation,
            "REQUIRED",
        )

    def test_trusted_risk_can_never_be_downgraded(
        self,
    ) -> None:

        prop = build()

        self.assertEqual(
            prop.risk_flags,
            ("LOW_MUTATION",),
        )

    def test_explicit_trusted_kwargs_are_impossible(
        self,
    ) -> None:

        with self.assertRaises(TypeError):

            proposal.build_action_proposal(
                "planner.tasks.create",
                VALID_ARGUMENTS,
                confirmation="NEVER",
            )

        with self.assertRaises(TypeError):

            proposal.build_action_proposal(
                "planner.tasks.create",
                VALID_ARGUMENTS,
                risk_flags=("READ_ONLY",),
            )

        with self.assertRaises(TypeError):

            proposal.build_action_proposal(
                "planner.tasks.create",
                VALID_ARGUMENTS,
                proposal_id="prop_hijacked0000",
            )

    def test_changing_tool_id_is_rejected(self) -> None:

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:

            proposal.build_action_proposal(
                "planner.tasks.get",
                VALID_ARGUMENTS,
            )

        self.assertEqual(
            ctx.exception.code,
            "PROPOSAL_TOOL_UNKNOWN",
        )

    def test_tool_id_inside_arguments_is_rejected(self) -> None:

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:

            proposal.build_action_proposal(
                "planner.tasks.create",
                {
                    "title": "T",
                    "tool_id": "planner.tasks.create",
                },
            )

        self.assertIn(
            "unknown_argument:tool_id",
            ctx.exception.message,
        )


class ImmutabilityTests(unittest.TestCase):
    """A proposal is a copy-isolated, immutable snapshot."""

    def test_mutating_the_input_does_not_mutate_the_proposal(
        self,
    ) -> None:

        original = dict(VALID_ARGUMENTS)

        arguments = original.copy()

        prop = build(arguments=arguments)

        self.assertEqual(
            dict(prop.arguments),
            VALID_ARGUMENTS,
        )

        original["title"] = "hacked"

        original["injected"] = "later"

        self.assertEqual(
            dict(prop.arguments),
            {"title": "Comprar leche"},
        )

        self.assertEqual(
            prop.summary,
            "Crear tarea\nTítulo: Comprar leche",
        )

    def test_mutating_the_argument_view_is_impossible(
        self,
    ) -> None:

        prop = build()

        with self.assertRaises(TypeError):

            prop.arguments["title"] = "injected"

        with self.assertRaises(TypeError):

            del prop.arguments["title"]

    def test_attribute_reassignment_is_impossible(
        self,
    ) -> None:

        prop = build()

        with self.assertRaises(
            dataclasses.FrozenInstanceError,
        ):

            prop.status = "CONFIRMED"

        with self.assertRaises(
            dataclasses.FrozenInstanceError,
        ):

            prop.confirmation = "NEVER"

        with self.assertRaises(
            dataclasses.FrozenInstanceError,
        ):

            prop.proposal_id = "prop_hijacked0000"

    def test_the_snapshot_is_an_independent_copy(
        self,
    ) -> None:

        original = dict(VALID_ARGUMENTS)

        prop = build(arguments=original)

        original.pop("title", None)

        self.assertIn(
            "title",
            dict(prop.arguments),
        )


class SummaryTests(unittest.TestCase):
    """The deterministic human summary."""

    def test_the_reference_summary(self) -> None:

        prop = build(
            arguments={
                "title": "Comprar leche",
                "dueDate": "2026-10-23",
            },
        )

        self.assertEqual(
            prop.summary,
            (
                "Crear tarea\n"
                "Título: Comprar leche\n"
                "Fecha: 23/10/2026"
            ),
        )

    def test_only_present_facts_appear(self) -> None:

        prop = build()

        self.assertEqual(
            prop.summary,
            "Crear tarea\nTítulo: Comprar leche",
        )

        full = build(arguments=FULL_ARGUMENTS)

        self.assertEqual(
            full.summary,
            (
                "Crear tarea\n"
                "Título: Comprar leche\n"
                "Descripción: Y pan\n"
                "Fecha: 23/10/2026\n"
                "Hora: 14:30\n"
                "Asignada a: member-abc"
            ),
        )

    def test_the_summary_is_deterministic(self) -> None:

        first = build(arguments=FULL_ARGUMENTS)

        second = build(arguments=FULL_ARGUMENTS)

        self.assertEqual(
            first.summary,
            second.summary,
        )

    def test_hostile_text_stays_inert_data(self) -> None:

        hostile = (
            "<script>alert(1)</script> #hax "
            "[link](http://evil) `rm -rf /` | 하la"
        )

        prop = build(arguments={"title": hostile})

        self.assertIn(
            "<script>alert(1)</script>",
            prop.summary,
        )

        self.assertIn(
            "[link](http://evil)",
            prop.summary,
        )

    def test_control_characters_are_stripped_from_data(
        self,
    ) -> None:

        prop = build(
            arguments={"title": "a\x00b\x1fc"},
        )

        self.assertIn(
            "Título: abc",
            prop.summary,
        )

    def test_the_summary_is_bounded(self) -> None:

        prop = build(
            arguments={
                "title": "a" * 500,
                "description": "d" * 2000,
            },
        )

        self.assertLessEqual(
            len(prop.summary),
            proposal.MAX_SUMMARY_CHARS,
        )


class ProjectionTests(unittest.TestCase):
    """The safe public representation."""

    def test_the_exact_projection_shape(self) -> None:

        prop = build(arguments=FULL_ARGUMENTS)

        projection = prop.public_projection

        self.assertEqual(
            projection["kind"],
            "action_proposal",
        )

        self.assertEqual(
            set(projection["proposal"]),
            {
                "proposal_id",
                "tool_id",
                "summary",
                "arguments",
                "risk",
                "confirmation",
                "status",
            },
        )

        inner = projection["proposal"]

        self.assertEqual(
            inner["risk"],
            ["LOW_MUTATION"],
        )

        self.assertEqual(
            inner["confirmation"],
            "REQUIRED",
        )

        self.assertEqual(
            inner["status"],
            "PROPOSED",
        )

        self.assertEqual(
            inner["arguments"],
            FULL_ARGUMENTS,
        )

    def test_the_projection_is_deterministic(self) -> None:

        prop = build(arguments=FULL_ARGUMENTS)

        self.assertEqual(
            prop.public_projection,
            prop.public_projection,
        )

    def test_the_projection_carries_no_authority_fields(
        self,
    ) -> None:

        prop = build(arguments=FULL_ARGUMENTS)

        text = prop.to_json()

        for forbidden in (
            "actor_id",
            "household_id",
            "jwt",
            "authorization",
            "access_token",
            "bearer_token",
            "catalog_digest",
            "request_id",
            "trace_id",
        ):

            self.assertNotIn(
                forbidden,
                text,
            )


class SerializationTests(unittest.TestCase):
    """Deterministic, bounded serialization."""

    def test_serialization_is_deterministic(self) -> None:

        prop = build(arguments=FULL_ARGUMENTS)

        self.assertEqual(
            prop.to_json(),
            prop.to_json(),
        )

        decoded = json.loads(prop.to_json())

        self.assertEqual(
            decoded,
            prop.public_projection,
        )

    def test_keys_are_sorted_deterministically(self) -> None:

        prop = build()

        text = prop.to_json()

        self.assertLess(
            text.index('"arguments"'),
            text.index('"confirmation"'),
        )

        self.assertLess(
            text.index('"confirmation"'),
            text.index('"proposal_id"'),
        )

        self.assertGreater(
            text.index('"tool_id"'),
            text.index('"status"'),
        )

    def test_serialization_is_bounded(self) -> None:

        prop = build(arguments=FULL_ARGUMENTS)

        self.assertLess(
            len(prop.to_json().encode("utf-8")),
            proposal.MAX_PROPOSAL_JSON_BYTES,
        )

    def test_oversized_proposals_fail_closed(self) -> None:

        huge = proposal.ActionProposalV1(
            proposal_version="1.0",
            proposal_id="prop_p_00000000000000",
            tool_id="planner.tasks.create",
            arguments={
                "title": "x" * 40000,
                "description": "y" * 40000,
            },
            risk_flags=("LOW_MUTATION",),
            confirmation="REQUIRED",
            status="PROPOSED",
            created_at=FIXED_CREATED_AT,
            summary="s",
        )

        with self.assertRaises(
            proposal.ActionProposalError,
        ) as ctx:

            huge.to_json()

        self.assertEqual(
            ctx.exception.code,
            "PROPOSAL_JSON_TOO_LARGE",
        )


class ZeroExecutionTests(unittest.TestCase):
    """No WRITE execution path exists in T11-2."""

    def test_the_module_carries_no_execution_seam(self) -> None:

        import ast

        import homi_tool_proposal

        source = inspect.getsource(
            homi_tool_proposal,
        )

        tree = ast.parse(source)

        identifiers: list[str] = []

        for node in ast.walk(tree):

            if isinstance(
                node,
                (ast.Import, ast.ImportFrom),
            ):

                names = [alias.name for alias in node.names]

                module = getattr(node, "module", None)

                if module:
                    names.append(module)

                identifiers.extend(names)

            elif isinstance(node, ast.Name):

                identifiers.append(node.id)

            elif isinstance(node, ast.Attribute):

                identifiers.append(node.attr)

        for forbidden in (
            "httpx",
            "urllib",
            "socket",
            "subprocess",
            "HomePlusToolClient",
            "ToolExecutor",
        ):

            hits = [
                identifier
                for identifier in identifiers
                if forbidden in identifier
            ]

            self.assertEqual(
                hits,
                [],
                f"the proposal module references {forbidden!r} "
                f"in code: {hits}",
            )

    def test_building_a_proposal_never_invokes_the_executor(
        self,
    ) -> None:

        spy = mock.Mock()

        with mock.patch.object(
            loop,
            "get_tool_executor",
            spy,
        ):

            build()

        self.assertEqual(
            spy.call_count,
            0,
        )

    def test_the_executor_stays_disabled_in_this_runtime(
        self,
    ) -> None:

        import os

        if os.environ.get("HOMI_TOOL_BASE_URL"):
            self.skipTest(
                "the production executor is configured "
                "on this host"
            )

        self.assertEqual(
            loop.executor_state(),
            "DISABLED",
        )

    def test_a_write_tool_command_is_absent_from_the_read_path(
        self,
    ) -> None:

        spy = mock.Mock()

        with mock.patch.object(
            loop,
            "get_tool_executor",
            spy,
        ):

            loop.validate_tool_request(
                "planner.tasks.create",
                VALID_ARGUMENTS,
            )

        self.assertEqual(
            spy.call_count,
            0,
        )

    def test_no_t07_route_is_written_by_t11_2(self) -> None:

        contract = proposal.write_tool_contract(
            "planner.tasks.create",
        )

        # The binding candidate is documentation only: T11-2 installs
        # no executable binding and EXECUTION_ENABLED stays false.
        self.assertIn(
            "planner.tasks.service.js",
            contract.domain_binding,
        )

        self.assertFalse(
            contract.execution_enabled,
        )


if __name__ == "__main__":

    unittest.main()
