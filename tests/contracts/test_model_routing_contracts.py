from __future__ import annotations

import asyncio
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

# ruff: noqa: E402
from research_observatory_core import model_gateway_contracts as decoder
from research_observatory_core import model_routing_contracts as routing_contracts
from research_observatory_core.model_registry_contracts import ModelManifest, ModelRegistryCatalog, canonical_bytes
from research_observatory_core.model_routing import ModelGateway
from research_observatory_core.model_routing_contracts import (
    CancellationToken,
    RoutingPolicy,
    RoutingRun,
    input_references,
)

from tests.ai.test_model_registry import FixtureInventory, FixturePolicy, manifest_document, task
from tests.ai.test_model_routing import FixtureAdapter
from tests.model_routing_fixtures import MemoryRoutingRepository


class ModelRoutingContractTests(unittest.TestCase):
    def test_type_and_array_keyword_applicability_match_json_schema(self):
        schemas = (
            {"type": "string", "minLength": 2},
            {"type": "number", "minimum": 0},
            {"type": ["string", "null"], "minLength": 2},
            {"type": ["object", "null"], "properties": {"x": {"type": "string"}}},
            {"type": ["array", "null"], "minItems": 1, "items": {"type": "integer"}},
            {"minItems": 2},
            {"maxItems": 1},
            {"uniqueItems": True},
            {"items": {"type": "integer"}},
            {"type": "array"},
            {},
        )
        values = (None, True, -1, 1.5, "a", "ab", {}, {"x": 1}, {"x": "a"}, [], [1], [1, 1], [1, "x"])
        for schema in schemas:
            validator = Draft202012Validator(schema)
            for value in values:
                with self.subTest(schema=schema, value=value):
                    self.assertEqual(validator.is_valid(value), not decoder._validation_errors(value, schema, "$"))

    def test_task_decode_memo_is_exact_bounded_immutable_and_cleared_at_scope_exit(self):
        from contextvars import copy_context

        document = task()
        text = canonical_bytes(document).decode()
        with patch.object(routing_contracts, "decode_model_task", wraps=decoder.decode_model_task) as decode:
            with routing_contracts.routing_contract_scope():
                first = routing_contracts._canonical_task(text)
                self.assertIs(first, routing_contracts._canonical_task(text))
                self.assertEqual(1, decode.call_count)
                with self.assertRaises(TypeError):
                    first["requirements"]["dataClass"] = "public"
                with self.assertRaises(ValueError):
                    routing_contracts._canonical_task(text.replace('"schemaVersion":"1.0"', '"schemaVersion":"bad"'))
                inherited = copy_context()
                memo = routing_contracts._TASK_DECODE_MEMO.get()
            self.assertFalse(memo.active)
            self.assertIsNone(memo.text)
            self.assertIsNone(memo.snapshot)
            before = decode.call_count
            inherited.run(routing_contracts._canonical_task, text)
            inherited.run(routing_contracts._canonical_task, text)
            self.assertEqual(before + 2, decode.call_count)
            self.assertIsNone(memo.snapshot)
        document["taskKind"] = "embedding"
        document["input"] = {"kind": "embedding", "items": [document["input"]["instruction"]] * 500}
        large = canonical_bytes(document).decode()
        self.assertGreater(len(large), 64_000)
        with routing_contracts.routing_contract_scope():
            self.assertIsNotNone(routing_contracts._canonical_task(large))
            self.assertIsNone(routing_contracts._TASK_DECODE_MEMO.get().text)

    def test_thread_inherited_decode_context_neither_hits_nor_refills_parent_memo(self):
        from concurrent.futures import ThreadPoolExecutor
        from contextvars import copy_context

        text = canonical_bytes(task()).decode()
        with (
            patch.object(routing_contracts, "decode_model_task", wraps=decoder.decode_model_task) as decode,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            with routing_contracts.routing_contract_scope():
                first = routing_contracts._canonical_task(text)
                inherited = copy_context()
                memo = routing_contracts._TASK_DECODE_MEMO.get()
                other = pool.submit(inherited.run, routing_contracts._canonical_task, text).result()
                self.assertEqual(first, other)
                self.assertIsNot(first, other)
                self.assertEqual(2, decode.call_count)
                self.assertIs(first, memo.snapshot)
            pool.submit(inherited.run, routing_contracts._canonical_task, text).result()
            self.assertEqual(3, decode.call_count)
            self.assertIsNone(memo.snapshot)

    def test_discriminated_task_inputs_match_schema_for_every_kind_and_malformed_tag(self):
        document = task()
        reference = document["input"]["instruction"]
        schema_ref = {"schemaId": "fixture-output", "schemaVersion": "1.0.0", "schemaHash": "sha256:" + "a" * 64}
        inputs = (
            {"kind": "embedding", "items": [reference]},
            {"kind": "reranking", "query": reference, "candidates": [reference], "topK": 1},
            {"kind": "classification", "items": [reference], "labels": ["include", "exclude"]},
            {"kind": "nli", "premise": reference, "hypothesis": reference},
            {"kind": "structured-extraction", "sources": [reference], "outputSchema": schema_ref},
            document["input"],
            {"kind": "moderation", "items": [reference], "policyId": "fixture-policy", "policyVersion": "1.0.0"},
            {
                "kind": "tool-call",
                "toolId": "fixture-tool",
                "toolVersion": "1.0.0",
                "arguments": reference,
                "inputSchema": schema_ref,
            },
        )
        validator = Draft202012Validator(decoder._MODEL_TASK_SCHEMA)
        for task_input in inputs:
            candidate = document | {"taskKind": task_input["kind"], "input": task_input}
            with self.subTest(kind=task_input["kind"]):
                self.assertTrue(validator.is_valid(candidate))
                self.assertIsNotNone(decoder.decode_model_task(candidate))
            for tag in (None, True, {}, [], "unknown", *[item["kind"] for item in inputs]):
                malformed = candidate | {"input": task_input | {"kind": tag}}
                self.assertEqual(
                    validator.is_valid(malformed),
                    not decoder._validation_errors(malformed, decoder._MODEL_TASK_SCHEMA, "$"),
                )
            missing = candidate | {"input": {key: value for key, value in task_input.items() if key != "kind"}}
            self.assertIsNone(decoder.decode_model_task(missing))

    def test_portable_policy_matches_core_and_never_accepts_authorization_flags(self):
        schema = RoutingPolicy.model_json_schema(by_alias=True)
        Draft202012Validator.check_schema(schema)
        committed = json.loads(
            (REPO / "packages/contracts/model-gateway/routing-policy.schema.json").read_text("utf-8")
        )
        self.assertEqual(schema, committed)
        policy = RoutingPolicy(project_id="fixture-project", revision=1).model_dump(by_alias=True, mode="json")
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(policy)))
        for delta in ({"allowed": True}, {"maximumAttempts": 9}, {"revision": True}, {"maximumCostMicrounits": -1}):
            with self.subTest(delta=delta):
                self.assertTrue(list(validator.iter_errors(policy | delta)))
                with self.assertRaises(ValidationError):
                    RoutingPolicy.model_validate(policy | delta)

    def test_audit_history_rejects_tampered_authority_cost_route_and_terminal_claims(self):
        manifest = ModelManifest.model_validate(manifest_document())
        repository = MemoryRoutingRepository("fixture-project")
        gateway = ModelGateway(
            catalog=ModelRegistryCatalog(project_id="fixture-project", revision=1, manifests=(manifest,)),
            inventory=FixtureInventory((manifest,)),
            authority=FixturePolicy(),
            adapters=(FixtureAdapter(manifest),),
            repository=repository,
            clock_ms=lambda: 1500,
        )
        request = task()
        asyncio.run(
            gateway.execute(
                request,
                input_references(request),
                RoutingPolicy(project_id="fixture-project", revision=1),
                CancellationToken(),
            )
        )
        original = repository.read(request["taskId"]).model_dump(by_alias=True, mode="json")
        changes = (
            (0, {"attemptNumber": 1}),
            (1, {"manifest": manifest.model_dump(by_alias=True, mode="json")}),
            (2, {"manifestHash": "sha256:" + "0" * 64}),
            (2, {"policyRevision": "forged-policy"}),
            (2, {"reservedCostMicrounits": 1}),
            (2, {"effectiveCostLimitMicrounits": 1}),
            (2, {"effectiveCostLimitMicrounits": None}),
            (1, {"effectiveCostLimitMicrounits": 0}),
            (2, {"attemptNumber": 2}),
            (3, {"kind": "interrupted"}),
        )
        for index, delta in changes:
            candidate = copy.deepcopy(original)
            candidate["events"][index].update(delta)
            with self.subTest(index=index, delta=delta), self.assertRaises(ValidationError):
                RoutingRun.model_validate(candidate)

    def test_short_circuit_decoder_matches_json_schema_on_structural_mutations(self):
        root = REPO / "packages/contracts/model-gateway"
        schema = json.loads((root / "model-task.schema.json").read_text("utf-8"))
        validator = Draft202012Validator(schema)
        comparisons = 0
        for name in ("valid-generation-task.v1.json", "valid-generation-result.v1.json"):
            original = json.loads((root / "fixtures" / name).read_text("utf-8"))
            paths = []

            def visit(value, path=(), *, found=paths):
                if isinstance(value, dict):
                    for key, child in value.items():
                        found.append((*path, key))
                        visit(child, (*path, key), found=found)
                elif isinstance(value, list):
                    for key, child in enumerate(value):
                        found.append((*path, key))
                        visit(child, (*path, key), found=found)

            visit(original)
            for path in paths:
                for replacement in (None, True, -1, {}, [], "unexpected"):
                    document = copy.deepcopy(original)
                    parent = document
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = replacement
                    with self.subTest(name=name, path=path, replacement=replacement):
                        self.assertEqual(
                            validator.is_valid(document), not decoder._validation_errors(document, schema, "$")
                        )
                    comparisons += 1
        self.assertGreater(comparisons, 500)
