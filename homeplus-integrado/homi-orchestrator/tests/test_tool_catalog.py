from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ORCHESTRATOR_ROOT = (
    Path(__file__).resolve().parent.parent
)

if str(ORCHESTRATOR_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ORCHESTRATOR_ROOT),
    )

import homi_tool_catalog as cat  # noqa: E402


T07_WORKTREE = Path(
    os.getenv(
        "HOMI_T07_WORKTREE",
        r"C:\Users\thega\Desktop\HomePlus-worktrees\homi-t07",
    )
)

# The deterministic T07 exporter. It executes the canonical T07 registry from
# the frozen worktree and prints the canonical catalogue document on stdout.
# The parity test re-runs it and compares the result byte for byte with the
# stored artefact.
T07_EXPORT_SCRIPT = r"""
'use strict';

const path = require('path');
const { execFileSync } = require('child_process');

const SOURCE_REPOSITORY = 'https://github.com/xeyroxpagode/Family-Hub-Own.git';
const SOURCE_BRANCH = 'homi/t07-tool-layer';
const SOURCE_COMMIT = '126044232d11bc995b7540264d40d6dafb242e8c';
const SCHEMA_VERSION = '1.0';

const worktree = process.argv[2];

if (!worktree) {
  process.stderr.write('usage: node export_planner_read_tools.js <t07-worktree-root>\n');
  process.exit(2);
}

function git(args) {
  return execFileSync('git', args, {
    cwd: worktree,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

const head = git(['rev-parse', 'HEAD']);
const branch = git(['rev-parse', '--abbrev-ref', 'HEAD']);

if (head !== SOURCE_COMMIT) {
  process.stderr.write(`T07 HEAD mismatch: ${head} != ${SOURCE_COMMIT}\n`);
  process.exit(3);
}

if (branch !== SOURCE_BRANCH) {
  process.stderr.write(`T07 branch mismatch: ${branch} != ${SOURCE_BRANCH}\n`);
  process.exit(4);
}

const homiDir = path.join(worktree, 'backend', 'src', 'homi');

const { createDefaultHomiToolRegistry } = require(
  path.join(homiDir, 'defaultRegistry.js')
);

const { HOMI_TOOL_CONTRACT_VERSION } = require(
  path.join(homiDir, 'toolContract.js')
);

function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }

  if (value !== null && typeof value === 'object') {
    const sorted = {};

    for (const key of Object.keys(value).sort()) {
      sorted[key] = canonicalize(value[key]);
    }

    return sorted;
  }

  return value;
}

const registry = createDefaultHomiToolRegistry();
const listed = registry.list();

const tools = listed.map((tool) => {
  const entry = {
    contract_version: tool.contractVersion,
    tool_id: tool.id,
    description: tool.description,
    kind: tool.kind,
    riskFlags: tool.riskFlags.slice(),
    confirmation: tool.confirmation,
    inputSchema: tool.inputSchema,
  };

  if (tool.outputSchema !== undefined && tool.outputSchema !== null) {
    entry.outputSchema = tool.outputSchema;
  }

  return canonicalize(entry);
});

const document = canonicalize({
  schema_version: SCHEMA_VERSION,
  source_repository: SOURCE_REPOSITORY,
  source_branch: SOURCE_BRANCH,
  source_commit: SOURCE_COMMIT,
  tool_contract_version: HOMI_TOOL_CONTRACT_VERSION,
  tools,
});

process.stdout.write(`${JSON.stringify(document, null, 2)}\n`);
"""


def load_catalogue() -> cat.ToolCatalog:
    return cat.load_catalog()


def catalogue_document() -> dict[str, Any]:
    return json.loads(
        cat.CATALOG_PATH.read_text(
            encoding="utf-8",
        )
    )


class CatalogArtefactTests(unittest.TestCase):
    """The stored catalogue artefact is the canonical 8-tool READ set."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalogue()
        cls.document = catalogue_document()

    def test_catalogue_exposes_exactly_eight_tools(self) -> None:
        self.assertEqual(
            len(self.catalog.tools),
            8,
        )

    def test_catalogue_exposes_the_exact_canonical_ids(self) -> None:
        self.assertEqual(
            list(self.catalog.tool_ids),
            [
                "planner.attention.get",
                "planner.calendar.get",
                "planner.events.get",
                "planner.events.list",
                "planner.search.query",
                "planner.summary.get",
                "planner.tasks.get",
                "planner.tasks.list",
            ],
        )

    def test_catalogue_ids_match_the_allow_list_constant(self) -> None:
        self.assertEqual(
            list(self.catalog.tool_ids),
            list(cat.CANONICAL_TOOL_IDS),
        )

    def test_catalogue_is_sorted_lexicographically(self) -> None:
        tool_ids = list(self.catalog.tool_ids)

        self.assertEqual(
            tool_ids,
            sorted(tool_ids),
        )

    def test_catalogue_is_byte_deterministic_on_reload(self) -> None:
        again = load_catalogue()

        self.assertEqual(
            again.sha256,
            self.catalog.sha256,
        )

        self.assertEqual(
            json.dumps(
                again.document,
                sort_keys=True,
            ),
            json.dumps(
                self.catalog.document,
                sort_keys=True,
            ),
        )

    def test_every_tool_is_read_kind(self) -> None:
        for tool in self.catalog.tools:
            self.assertEqual(
                tool["kind"],
                "READ",
            )

    def test_catalogue_has_no_write_tool(self) -> None:
        write_tools = [
            tool["tool_id"]
            for tool in self.catalog.tools
            if tool["kind"] != "READ"
        ]

        self.assertEqual(
            write_tools,
            [],
        )

    def test_every_tool_carries_the_read_only_risk_flag(self) -> None:
        for tool in self.catalog.tools:
            self.assertIn(
                "READ_ONLY",
                tool["riskFlags"],
            )

    def test_every_tool_confirmation_is_never(self) -> None:
        for tool in self.catalog.tools:
            self.assertEqual(
                tool["confirmation"],
                "NEVER",
            )

    def test_every_input_schema_is_a_closed_object(self) -> None:
        for tool in self.catalog.tools:
            input_schema = tool["inputSchema"]

            self.assertEqual(
                input_schema["type"],
                "object",
            )

            self.assertIs(
                input_schema["additionalProperties"],
                False,
            )

    def test_no_input_schema_exposes_identity_or_auth_fields(self) -> None:
        for tool in self.catalog.tools:
            forbidden = cat.forbidden_keys_in(
                tool["inputSchema"]
            )

            self.assertEqual(
                forbidden,
                [],
                f"{tool['tool_id']} exposes {forbidden}",
            )

    def test_catalogue_identifies_the_frozen_t07_authority(self) -> None:
        self.assertEqual(
            self.catalog.source_commit,
            "126044232d11bc995b7540264d40d6dafb242e8c",
        )

        self.assertEqual(
            self.catalog.source_branch,
            "homi/t07-tool-layer",
        )

        self.assertEqual(
            self.catalog.schema_version,
            "1.0",
        )

        self.assertEqual(
            self.catalog.tool_contract_version,
            "1.0.0",
        )

    def test_catalogue_carries_no_volatile_export_metadata(self) -> None:
        forbidden_top_level = {
            "generated_at",
            "generatedAt",
            "timestamp",
            "exported_at",
            "path",
            "worktree",
            "random_id",
        }

        self.assertEqual(
            forbidden_top_level
            & set(self.document.keys()),
            set(),
        )

        serialized = json.dumps(self.document)

        self.assertNotIn(
            "C:\\Users",
            serialized,
        )

        self.assertNotIn(
            "C:/Users",
            serialized,
        )

    def test_catalogue_descriptions_come_from_t07(self) -> None:
        for tool in self.catalog.tools:
            self.assertTrue(
                tool["description"].strip(),
            )

            self.assertLessEqual(
                len(tool["description"]),
                500,
            )


class CatalogHashTests(unittest.TestCase):
    """The catalogue is bound to an in-code trust anchor."""

    def test_artefact_digest_matches_the_trust_anchor(self) -> None:
        digest = hashlib.sha256(
            cat.CATALOG_PATH.read_bytes()
        ).hexdigest()

        self.assertEqual(
            digest.upper(),
            cat.PLANNER_READ_TOOLS_SHA256.upper(),
        )

    def test_loaded_catalogue_reports_the_trust_anchor_digest(self) -> None:
        self.assertEqual(
            load_catalogue().digest.upper(),
            cat.PLANNER_READ_TOOLS_SHA256.upper(),
        )

    def test_adjacent_digest_file_is_informational_only(self) -> None:
        adjacent = cat.read_adjacent_digest_file()

        self.assertIsNotNone(adjacent)

        self.assertEqual(
            str(adjacent).upper(),
            cat.PLANNER_READ_TOOLS_SHA256.upper(),
        )

    def test_wrong_digest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "planner-read-tools.v1.json"

            target.write_bytes(
                cat.CATALOG_PATH.read_bytes()
                + b"\n"
            )

            with self.assertRaises(
                cat.ToolCatalogError
            ) as caught:
                cat.load_catalog(target)

            self.assertEqual(
                caught.exception.code,
                "CATALOG_DIGEST_MISMATCH",
            )

    def test_corrupted_catalogue_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "planner-read-tools.v1.json"

            target.write_bytes(
                b"{ this is not json"
            )

            with self.assertRaises(
                cat.ToolCatalogError
            ):
                cat.load_catalog(target)

    def test_corrupted_catalogue_fails_closed_on_json_parse(self) -> None:
        with self.assertRaises(
            cat.ToolCatalogError
        ) as caught:
            cat.loads_catalog_document(
                "{ this is not json"
            )

        self.assertEqual(
            caught.exception.code,
            "CATALOG_INVALID_JSON",
        )

    def test_catalogue_and_adjacent_digest_changed_together_fails_closed(
        self,
    ) -> None:
        document = catalogue_document()

        document["tools"][0]["description"] = (
            "Tampered description."
        )

        tampered = json.dumps(
            document,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "planner-read-tools.v1.json"

            target.write_bytes(tampered)

            digest = hashlib.sha256(tampered).hexdigest()

            (Path(folder) / "planner-read-tools.v1.sha256.txt").write_text(
                f"{digest}  planner-read-tools.v1.json\n",
                encoding="utf-8",
            )

            with self.assertRaises(
                cat.ToolCatalogError
            ) as caught:
                cat.load_catalog(target)

            self.assertEqual(
                caught.exception.code,
                "CATALOG_DIGEST_MISMATCH",
            )

    def test_missing_catalogue_fails_closed(self) -> None:
        with self.assertRaises(
            cat.ToolCatalogError
        ) as caught:
            cat.load_catalog(
                Path("C:/nonexistent/planner-read-tools.v1.json")
            )

        self.assertEqual(
            caught.exception.code,
            "CATALOG_NOT_FOUND",
        )


class CatalogDriftTests(unittest.TestCase):
    """Catalogue drift fails closed instead of being repaired."""

    def _mutated(
        self,
        mutate: Any,
    ) -> dict[str, Any]:
        document = catalogue_document()

        mutate(document)

        return document

    def test_added_ninth_tool_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            extra = json.loads(
                json.dumps(document["tools"][0])
            )

            extra["tool_id"] = "planner.calendar.list"

            document["tools"].append(extra)

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ) as caught:
            cat.parse_catalog_document(document)

        self.assertEqual(
            caught.exception.code,
            "CATALOG_TOOL_ID_SET_MISMATCH",
        )

    def test_removed_tool_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"].pop()

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ) as caught:
            cat.parse_catalog_document(document)

        self.assertEqual(
            caught.exception.code,
            "CATALOG_TOOL_ID_SET_MISMATCH",
        )

    def test_renamed_tool_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"][0]["tool_id"] = "planner.calendar"

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ):
            cat.parse_catalog_document(document)

    def test_write_tool_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"][0]["kind"] = "WRITE"

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ) as caught:
            cat.parse_catalog_document(document)

        self.assertEqual(
            caught.exception.code,
            "CATALOG_TOOL_INVARIANT_VIOLATION",
        )

    def test_missing_read_only_flag_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"][0]["riskFlags"] = []

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ):
            cat.parse_catalog_document(document)

    def test_required_confirmation_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"][0]["confirmation"] = "REQUIRED"

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ):
            cat.parse_catalog_document(document)

    def test_open_input_schema_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"][0]["inputSchema"][
                "additionalProperties"
            ] = True

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ):
            cat.parse_catalog_document(document)

    def test_identity_field_in_input_schema_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"][0]["inputSchema"]["properties"][
                "actor_id"
            ] = {"type": "string"}

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ) as caught:
            cat.parse_catalog_document(document)

        self.assertEqual(
            caught.exception.code,
            "CATALOG_FORBIDDEN_ARGUMENT_KEY",
        )

    def test_foreign_source_commit_fails_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["source_commit"] = "0" * 40

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ):
            cat.parse_catalog_document(document)

    def test_unsorted_tools_fail_closed(self) -> None:
        def mutate(document: dict[str, Any]) -> None:
            document["tools"].reverse()

        document = self._mutated(mutate)

        with self.assertRaises(
            cat.ToolCatalogError
        ):
            cat.parse_catalog_document(document)


class ModelProjectionTests(unittest.TestCase):
    """The model-facing projection is minimal and leak free."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.projection = load_catalogue().model_projection()

    def test_projection_exposes_exactly_eight_tools(self) -> None:
        self.assertEqual(
            len(self.projection),
            8,
        )

    def test_projection_exposes_exactly_three_keys_per_tool(self) -> None:
        for entry in self.projection:
            self.assertEqual(
                sorted(entry.keys()),
                [
                    "description",
                    "input_schema",
                    "tool_id",
                ],
            )

    def test_projection_exposes_no_output_schema(self) -> None:
        serialized = json.dumps(self.projection)

        self.assertNotIn(
            "outputSchema",
            serialized,
        )

        self.assertNotIn(
            "output_schema",
            serialized,
        )

    def test_projection_exposes_no_kind_or_risk_metadata(self) -> None:
        serialized = json.dumps(self.projection)

        for leaked in (
            '"kind"',
            "riskFlags",
            "risk_flags",
            "confirmation",
            "READ_ONLY",
        ):
            self.assertNotIn(
                leaked,
                serialized,
            )

    def test_projection_exposes_no_auth_or_identity_field(self) -> None:
        for entry in self.projection:
            forbidden = cat.forbidden_keys_in(entry)

            self.assertEqual(
                forbidden,
                [],
                f"{entry['tool_id']} exposes {forbidden}",
            )

    def test_projection_exposes_no_homeplus_url(self) -> None:
        serialized = json.dumps(self.projection)

        for leaked in (
            "http://",
            "https://",
            "supabase",
            "planner_tasks",
            "planner_events",
            "table",
        ):
            self.assertNotIn(
                leaked,
                serialized,
            )

    def test_projection_keeps_the_canonical_tool_ids(self) -> None:
        self.assertEqual(
            [entry["tool_id"] for entry in self.projection],
            list(cat.CANONICAL_TOOL_IDS),
        )

    def test_projection_descriptions_match_the_catalogue(self) -> None:
        catalogue = load_catalogue()

        for entry in self.projection:
            definition = catalogue.require(
                entry["tool_id"]
            )

            self.assertEqual(
                entry["description"],
                definition["description"],
            )

            self.assertEqual(
                entry["input_schema"],
                definition["inputSchema"],
            )

    def test_projection_is_deterministic(self) -> None:
        self.assertEqual(
            json.dumps(
                load_catalogue().model_projection(),
                sort_keys=True,
            ),
            json.dumps(
                self.projection,
                sort_keys=True,
            ),
        )


class T07ParityTests(unittest.TestCase):
    """The stored catalogue is byte identical to the T07 source."""

    def setUp(self) -> None:
        if shutil.which("node") is None:
            self.skipTest(
                "node is not available on this host"
            )

        if not (T07_WORKTREE / "backend" / "src" / "homi").is_dir():
            self.skipTest(
                f"T07 worktree is not available: {T07_WORKTREE}"
            )

    def _derive_from_t07(self) -> bytes:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "export.js"

            script.write_text(
                T07_EXPORT_SCRIPT,
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "node",
                    str(script),
                    str(T07_WORKTREE),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            if completed.returncode != 0:
                raise AssertionError(
                    "the T07 export failed: "
                    + completed.stderr.decode(
                        "utf-8",
                        errors="replace",
                    )
                )

            return completed.stdout

    def test_t07_worktree_is_present_and_read_only_for_us(self) -> None:
        # Pass 2: homi-t07 sigue presente, pero es de solo lectura para D.
        self.assertTrue(T07_WORKTREE.is_dir())
        self.assertTrue((T07_WORKTREE / "backend" / "src" / "homi").is_dir())

    def test_v2_catalogue_digest_matches_the_trust_anchor(self) -> None:
        data = cat.CATALOG_V2_PATH.read_bytes()
        digest = hashlib.sha256(data).hexdigest()

        self.assertEqual(
            digest.upper(),
            cat.HOMI_TOOLS_V2_SHA256.upper(),
        )

    def test_v2_catalogue_is_accepted_by_the_loader(self) -> None:
        tools = cat.load_catalog_v2()

        self.assertEqual(
            len(tools.tools),
            len(cat.V2_TARGET_TOOL_IDS),
        )
        self.assertEqual(
            [t["tool_id"] for t in tools.tools],
            list(cat.V2_TARGET_TOOL_IDS),
        )

    def test_v2_catalogue_is_not_byte_identical_to_the_t07_source_by_design(
        self,
    ) -> None:
        # Pass 2: el catálogo de D expone los 307 tools definitivos.
        # Nuevamente NOT equal: es un artefacto nuevo, anchor actualizado.
        self.assertNotEqual(
            cat.CATALOG_V2_PATH.read_bytes(),
            cat.CATALOG_PATH.read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
