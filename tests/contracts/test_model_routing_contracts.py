from __future__ import annotations

import asyncio
import copy
import json
import sys
import unittest
from collections.abc import Mapping, MutableMapping
from contextvars import Context
from pathlib import Path
from typing import Any, TypedDict, cast
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


class CapturedDecodeScope(TypedDict):
    task: decoder.ModelTaskSnapshot
    memo: decoder._TaskDecodeScope
    context: Context


class ModelRoutingContractTests(unittest.TestCase):
    def test_decoder_identity_scope_reuses_only_owned_snapshots_not_mutable_inputs(self):
        from types import MappingProxyType

        document = task()
        proxy = MappingProxyType(document)
        with decoder._model_task_decode_scope():
            first = decoder.decode_model_task(document)
            self.assertIsNotNone(first)
            assert first is not None
            self.assertIs(first, decoder.decode_model_task(first))
            second = decoder.decode_model_task(proxy)
            self.assertEqual(first, second)
            self.assertIsNot(first, second)
            self.assertIsNot(proxy, second)
            document["requirements"]["deadlineMs"] = 0
            self.assertIsNone(decoder.decode_model_task(document))
            self.assertIsNone(decoder.decode_model_task(proxy))
            requirements = first["requirements"]
            assert isinstance(requirements, Mapping)
            self.assertEqual(30_000, requirements["deadlineMs"])
            self.assertIs(first, decoder.decode_model_task(first))
        self.assertIsNot(first, decoder.decode_model_task(first))

    def test_decoder_identity_scope_is_two_entries_and_rejects_no_large_valid_tasks(self):
        with decoder._model_task_decode_scope():
            first = decoder.decode_model_task(task())
            second = decoder.decode_model_task(task())
            third = decoder.decode_model_task(task())
            self.assertEqual(first, second)
            self.assertIsNot(first, second)
            memo = decoder._MODEL_TASK_DECODE_SCOPE.get()
            assert memo is not None
            self.assertEqual(2, len(memo.snapshots))
            self.assertIs(first, decoder.decode_model_task(first))
            self.assertIs(second, decoder.decode_model_task(second))
            self.assertIsNot(third, decoder.decode_model_task(third))
        document = task()
        document["taskKind"] = "embedding"
        document["input"] = {"kind": "embedding", "items": [document["input"]["instruction"]] * 500}
        self.assertGreater(len(canonical_bytes(document)), 64_000)
        with decoder._model_task_decode_scope():
            large = decoder.decode_model_task(document)
            self.assertIsNotNone(large)
            memo = decoder._MODEL_TASK_DECODE_SCOPE.get()
            assert memo is not None
            self.assertEqual([], memo.snapshots)
            self.assertEqual(large, decoder.decode_model_task(large))
            self.assertIsNot(large, decoder.decode_model_task(large))

    def test_decoder_cacheability_matches_canonical_byte_boundary_including_escaping(self):
        from types import MappingProxyType

        for character in ("x", "é", "\ud800", '"', "\\"):
            # Ensure that byte sizing includes canonical ASCII escaping, keys,
            # container delimiters and separators, not merely Python len(text).
            value = MappingProxyType({"key": (character, None, True, 1, 1.5)})
            size = len(canonical_bytes(value))
            self.assertTrue(decoder._cacheable_task(value, maximum_bytes=size))
            self.assertFalse(decoder._cacheable_task(value, maximum_bytes=size - 1))
        boundary_value = MappingProxyType({"key": "x" * (64_000 - len(canonical_bytes({"key": ""})))})
        self.assertEqual(64_000, len(canonical_bytes(boundary_value)))
        self.assertTrue(decoder._cacheable_task(boundary_value))
        self.assertFalse(decoder._cacheable_task(MappingProxyType({"key": boundary_value["key"] + "x"})))

    def test_decoder_does_not_cache_scalar_or_key_subclasses_or_change_their_acceptance(self):
        class Text(str):
            pass

        class Number(int):
            pass

        for change in ("value", "number", "key"):
            document = task()
            if change == "value":
                document["taskId"] = Text(document["taskId"])
            elif change == "number":
                document["requirements"]["deadlineMs"] = Number(30_000)
            else:
                document = {Text(key): value for key, value in document.items()}
            without_scope = decoder.decode_model_task(document)
            self.assertIsNotNone(without_scope)
            with decoder._model_task_decode_scope(), self.subTest(change=change):
                snapshot = decoder.decode_model_task(document)
                self.assertEqual(without_scope, snapshot)
                self.assertIsNot(snapshot, decoder.decode_model_task(snapshot))
                memo = decoder._MODEL_TASK_DECODE_SCOPE.get()
                assert memo is not None
                self.assertEqual([], memo.snapshots)

    def test_decoder_identity_scope_nested_exception_and_inherited_exit_clear_references(self):
        from contextvars import copy_context

        with decoder._model_task_decode_scope():
            first = decoder.decode_model_task(task())
            outer = decoder._MODEL_TASK_DECODE_SCOPE.get()
            assert outer is not None
            with self.assertRaisesRegex(RuntimeError, "synthetic"), decoder._model_task_decode_scope():
                other = decoder.decode_model_task(first)
                inner = decoder._MODEL_TASK_DECODE_SCOPE.get()
                assert inner is not None
                inherited = copy_context()
                self.assertIsNot(first, other)
                raise RuntimeError("synthetic")
            assert inner is not None
            self.assertFalse(inner.active)
            self.assertEqual([], inner.snapshots)
            self.assertIsNot(other, inherited.run(decoder.decode_model_task, other))
            self.assertEqual([], inner.snapshots)
            self.assertIs(outer, decoder._MODEL_TASK_DECODE_SCOPE.get())
            self.assertIs(first, decoder.decode_model_task(first))
        self.assertFalse(outer.active)
        self.assertEqual([], outer.snapshots)

    def test_decoder_identity_scope_foreign_thread_cannot_hit_or_refill(self):
        from concurrent.futures import ThreadPoolExecutor
        from contextvars import copy_context

        with ThreadPoolExecutor(max_workers=1) as pool:
            with decoder._model_task_decode_scope():
                first = decoder.decode_model_task(task())
                memo = decoder._MODEL_TASK_DECODE_SCOPE.get()
                assert memo is not None
                inherited = copy_context()
                other = pool.submit(inherited.run, decoder.decode_model_task, first).result()
                self.assertEqual(first, other)
                self.assertIsNot(first, other)
                self.assertEqual([first], memo.snapshots)
            self.assertIsNot(other, pool.submit(inherited.run, decoder.decode_model_task, other).result())
            self.assertEqual([], memo.snapshots)

    def test_decoder_identity_scope_cancellation_clears_inherited_state(self):
        from contextvars import copy_context

        async def check():
            entered = asyncio.Event()
            captured: CapturedDecodeScope | None = None

            async def pending():
                nonlocal captured
                with decoder._model_task_decode_scope():
                    try:
                        snapshot = decoder.decode_model_task(task())
                        memo = decoder._MODEL_TASK_DECODE_SCOPE.get()
                        assert snapshot is not None and memo is not None
                        captured = {"task": snapshot, "memo": memo, "context": copy_context()}
                    finally:
                        entered.set()
                    await asyncio.Event().wait()

            work = asyncio.create_task(pending())
            try:
                await asyncio.wait_for(entered.wait(), 2)
                if work.done():
                    await work  # Surface initialization failure before cancellation.
                work.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await work
            finally:
                if not work.done():
                    work.cancel()
                await asyncio.gather(work, return_exceptions=True)
            assert captured is not None
            self.assertFalse(captured["memo"].active)
            self.assertEqual([], captured["memo"].snapshots)
            self.assertIsNot(captured["task"], captured["context"].run(decoder.decode_model_task, captured["task"]))
            self.assertEqual([], captured["memo"].snapshots)

        asyncio.run(check())

    def test_decoder_identity_scope_never_reuses_result_validation(self):
        result = json.loads(
            (REPO / "packages/contracts/model-gateway/fixtures/valid-generation-result.v1.json").read_text("utf-8")
        )
        with decoder._model_task_decode_scope():
            request = decoder.decode_model_task(task())
            first = decoder.decode_model_result(request, result)
            self.assertIsNotNone(first)
            self.assertIs(request, decoder.decode_model_task(request))
            result["requestHash"] = "sha256:" + "0" * 64
            self.assertIsNone(decoder.decode_model_result(request, result))
            self.assertIsNot(first, decoder.decode_model_result(request, first))

    def test_type_and_array_keyword_applicability_match_json_schema(self):
        schemas: tuple[dict[str, Any], ...] = (
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
        values: tuple[object, ...] = (
            None,
            True,
            -1,
            1.5,
            "a",
            "ab",
            {},
            {"x": 1},
            {"x": "a"},
            [],
            [1],
            [1, 1],
            [1, "x"],
        )
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
                requirements = first["requirements"]
                assert isinstance(requirements, Mapping)
                with self.assertRaises(TypeError):
                    # Deliberately attempt an invalid mutation of the immutable snapshot.
                    cast(MutableMapping[str, decoder.FrozenJsonValue], requirements)["dataClass"] = "public"
                with self.assertRaises(ValueError):
                    routing_contracts._canonical_task(text.replace('"schemaVersion":"1.0"', '"schemaVersion":"bad"'))
                inherited = copy_context()
                memo = routing_contracts._TASK_DECODE_MEMO.get()
                assert memo is not None
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
            memo = routing_contracts._TASK_DECODE_MEMO.get()
            assert memo is not None
            self.assertIsNone(memo.text)

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
                assert memo is not None
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
        run = repository.read(request["taskId"])
        assert run is not None
        original = run.model_dump(by_alias=True, mode="json")
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
            paths: list[tuple[str | int, ...]] = []

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
            replacements: tuple[object, ...] = (None, True, -1, {}, [], "unexpected")
            for path in paths:
                for replacement in replacements:
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
