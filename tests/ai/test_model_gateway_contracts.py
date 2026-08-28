from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO / "packages" / "contracts" / "model-gateway"
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core.model_gateway_contracts import (  # noqa: E402
    MODEL_TASK_SCHEMA_SHA256,
    assess_model_task,
    decode_model_result,
    decode_model_task,
    model_result_errors,
    model_task_errors,
)


def fixture(name: str) -> object:
    return json.loads((CONTRACT_ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class ModelGatewayContractTests(unittest.TestCase):
    def test_draft_schema_and_generated_python_accept_complete_task_and_result(self) -> None:
        schema = json.loads((CONTRACT_ROOT / "model-task.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        task = fixture("valid-generation-task.v1.json")
        result = fixture("valid-generation-result.v1.json")
        self.assertEqual([], list(validator.iter_errors(task)))
        self.assertEqual([], list(validator.iter_errors(result)))
        self.assertIsNotNone(decode_model_task(task))
        self.assertEqual((), model_result_errors(task, result))
        self.assertIsNotNone(decode_model_result(task, result))

        impossible = cast(dict[str, Any], fixture("valid-generation-task.v1.json"))
        impossible["taskKind"] = "reranking"
        impossible["input"] = {
            "kind": "reranking",
            "query": self._reference("query"),
            "candidates": [self._reference("candidate")],
            "topK": 2,
        }
        self.assertIn("reranking-top-k-within-candidate-count", model_task_errors(impossible))

    def test_decoder_owns_and_freezes_task_and_result_snapshots(self) -> None:
        task = cast(dict[str, Any], fixture("valid-generation-task.v1.json"))
        result = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
        decoded_task = decode_model_task(task)
        decoded_result = decode_model_result(task, result)
        assert decoded_task is not None and decoded_result is not None
        task["requirements"]["deadlineMs"] = 1
        result["latency"]["totalMs"] = 999
        self.assertEqual(30000, cast(Any, decoded_task)["requirements"]["deadlineMs"])
        self.assertEqual(20, cast(Any, decoded_result)["latency"]["totalMs"])
        with self.assertRaises(TypeError):
            cast(Any, decoded_task)["taskKind"] = "embedding"
        with self.assertRaises(TypeError):
            cast(Any, decoded_result)["route"]["modelId"] = "substituted"

    def test_unsupported_features_return_stable_content_free_failure(self) -> None:
        task = fixture("valid-generation-task.v1.json")
        assessment = assess_model_task(task, ())
        self.assertEqual(False, assessment["supported"])
        self.assertEqual("model-task-feature-unsupported", assessment["diagnosticCode"])
        self.assertEqual(("structured-output",), assessment["unsupportedFeatures"])
        self.assertNotIn("aggregateId", json.dumps(assessment, default=dict))

        result = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
        result.update(
            {
                "status": "unsupported",
                "route": {
                    "selection": "none",
                    "providerId": None,
                    "providerVersion": None,
                    "modelId": None,
                    "modelVersion": None,
                    "runtimeId": None,
                    "runtimeVersion": None,
                    "configurationHash": None,
                    "evaluationId": None,
                    "evaluationVersion": None,
                    "reasonCode": "required-feature-unsupported",
                },
                "policyDecision": {
                    "decisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a6",
                    "policyVersion": "1.0.0",
                    "outcome": "denied",
                    "reasonCodes": ["required-feature-unsupported"],
                },
                "usage": {
                    "reporting": "not-reported",
                    "inputTokens": None,
                    "outputTokens": None,
                    "totalTokens": None,
                },
                "validation": {
                    "outcome": "not-run",
                    "validatorVersion": "1.0.0",
                    "outputHash": None,
                    "errorCodes": [],
                },
                "confidence": {"kind": "not-applicable"},
                "citationStatus": "not-supplied",
                "citations": [],
                "output": None,
                "diagnostics": [
                    {
                        "code": "model-task-feature-unsupported",
                        "retryable": False,
                        "partialOutputDisposition": "none",
                    }
                ],
            }
        )
        self.assertEqual((), model_result_errors(task, result))

    def test_contract_fails_closed_on_content_injection_and_material_result_mismatches(self) -> None:
        raw = cast(dict[str, Any], fixture("valid-generation-task.v1.json"))
        raw["input"]["prompt"] = "private research text"
        self.assertIsNone(decode_model_task(raw))
        self.assertTrue(model_task_errors(raw))

        task = fixture("valid-generation-task.v1.json")
        result = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
        result["requestHash"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        result["usage"]["totalTokens"] = 137
        result["citations"][0]["sourceContentHash"] = (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        result["route"]["modelVersion"] = "substituted"
        self.assertEqual(
            {
                "result-request-hash-matches-task",
                "reported-token-total-equals-input-plus-output",
                "supplied-citations-close-over-task-input-references",
                "pinned-execution-route-matches-result-route",
            },
            set(model_result_errors(task, result)),
        )
        self.assertIsNone(decode_model_result(task, result))

        hostile = json.loads(
            json.dumps(fixture("valid-generation-task.v1.json")).replace(
                "{", '{"__proto__":{"credential":"secret"},', 1
            )
        )
        self.assertIsNone(decode_model_task(hostile))

    def test_result_semantics_enforce_budget_deadline_artifact_validation_and_citation_closure(self) -> None:
        task = cast(dict[str, Any], fixture("valid-generation-task.v1.json"))
        boundary = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
        boundary["usage"] = {
            "reporting": "reported",
            "inputTokens": 4096,
            "outputTokens": 512,
            "totalTokens": 4608,
        }
        boundary["latency"] = {"queueMs": 0, "executionMs": 30000, "totalMs": 30000}
        self.assertEqual((), model_result_errors(task, boundary))

        invalid = copy.deepcopy(boundary)
        invalid["usage"] = {
            "reporting": "reported",
            "inputTokens": 4097,
            "outputTokens": 513,
            "totalTokens": 4610,
        }
        invalid["latency"] = {"queueMs": 1, "executionMs": 30000, "totalMs": 30001}
        invalid["validation"]["outputHash"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        invalid["citations"][0]["sourceContentHash"] = (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        optional_task = copy.deepcopy(task)
        optional_task["requirements"]["citationRequirement"] = "optional"
        self.assertTrue(
            {
                "reported-usage-within-task-bounds",
                "successful-result-within-task-deadline",
                "accepted-artifact-validation-hash-matches-output",
                "supplied-citations-close-over-task-input-references",
            }.issubset(model_result_errors(optional_task, invalid))
        )

        rejected = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
        rejected.update(
            {
                "status": "failed",
                "output": None,
                "citationStatus": "not-supplied",
                "citations": [],
                "validation": {
                    "outcome": "rejected",
                    "validatorVersion": "1.0.0",
                    "outputHash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
                    "errorCodes": ["output-schema-invalid"],
                },
            }
        )
        self.assertEqual((), model_result_errors(task, rejected))
        rejected["validation"]["errorCodes"] = []
        self.assertIn("rejected-validation-has-output-hash-and-errors", model_result_errors(task, rejected))
        rejected["validation"] = {
            "outcome": "accepted",
            "validatorVersion": "1.0.0",
            "outputHash": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
            "errorCodes": [],
        }
        self.assertIn("accepted-validation-requires-successful-output", model_result_errors(task, rejected))
        optional_without_citations = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
        optional_without_citations["citations"] = []
        optional_without_citations["citationStatus"] = "not-applicable"
        self.assertIn(
            "citation-status-matches-task-requirement",
            model_result_errors(optional_task, optional_without_citations),
        )

    def test_indexed_outputs_close_over_task_inputs_labels_and_cardinality(self) -> None:
        cases: tuple[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], str], ...] = (
            (
                "reranking",
                {
                    "kind": "reranking",
                    "query": self._reference("query"),
                    "candidates": [self._reference("candidate")],
                    "topK": 1,
                },
                {"kind": "reranking", "items": [{"inputIndex": 0, "label": "relevance", "score": 0.9}]},
                {"kind": "reranking", "items": [{"inputIndex": 1, "label": "relevance", "score": 0.9}]},
                "reranking-output-closes-over-candidates",
            ),
            (
                "classification",
                {
                    "kind": "classification",
                    "items": [self._reference("source")],
                    "labels": ["include", "exclude"],
                },
                {"kind": "classification", "items": [{"inputIndex": 0, "label": "include", "score": 0.9}]},
                {"kind": "classification", "items": [{"inputIndex": 0, "label": "unknown", "score": 0.9}]},
                "classification-output-closes-over-items-and-labels",
            ),
            (
                "nli",
                {
                    "kind": "nli",
                    "premise": self._reference("premise"),
                    "hypothesis": self._reference("hypothesis"),
                },
                {
                    "kind": "nli",
                    "label": "entailment",
                    "scores": [{"inputIndex": 0, "label": "entailment", "score": 0.9}],
                },
                {
                    "kind": "nli",
                    "label": "entailment",
                    "scores": [{"inputIndex": 1, "label": "entailment", "score": 0.9}],
                },
                "nli-output-closes-over-task",
            ),
            (
                "moderation",
                {
                    "kind": "moderation",
                    "items": [self._reference("source")],
                    "policyId": "research-content",
                    "policyVersion": "1.0.0",
                },
                {"kind": "moderation", "items": [{"inputIndex": 0, "label": "allowed", "score": 0.9}]},
                {"kind": "moderation", "items": [{"inputIndex": 1, "label": "allowed", "score": 0.9}]},
                "moderation-output-closes-over-items",
            ),
        )
        for kind, task_input, valid_output, invalid_output, code in cases:
            with self.subTest(kind=kind):
                task = cast(dict[str, Any], fixture("valid-generation-task.v1.json"))
                task["taskKind"] = kind
                task["input"] = task_input
                task["requirements"]["citationRequirement"] = "optional"
                result = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
                result["taskKind"] = kind
                result["output"] = valid_output
                result["citationStatus"] = "not-supplied"
                result["citations"] = []
                self.assertEqual((), model_result_errors(task, result))
                result["output"] = invalid_output
                self.assertIn(code, model_result_errors(task, result))

        mismatched_task = cast(dict[str, Any], fixture("valid-generation-task.v1.json"))
        mismatched_task["taskKind"] = "nli"
        mismatched_task["input"] = {
            "kind": "nli",
            "premise": self._reference("premise"),
            "hypothesis": self._reference("hypothesis"),
        }
        mismatched_task["requirements"]["citationRequirement"] = "optional"
        mismatched_result = cast(dict[str, Any], fixture("valid-generation-result.v1.json"))
        mismatched_result["taskKind"] = "nli"
        mismatched_result["output"] = {
            "kind": "classification",
            "items": [{"inputIndex": 0, "label": "include", "score": 0.9}],
        }
        mismatched_result["citations"] = []
        mismatched_result["citationStatus"] = "not-supplied"
        self.assertIn(
            "successful-result-output-kind-matches-task-kind",
            model_result_errors(mismatched_task, mismatched_result),
        )

    @staticmethod
    def _reference(role: str) -> dict[str, str]:
        return {
            "aggregateId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d9b1",
            "revisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d9b2",
            "contentHash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "role": role,
        }

    def test_schema_hash_is_canonical_across_checkout_newlines(self) -> None:
        schema_text = (CONTRACT_ROOT / "model-task.schema.json").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(hashlib.sha256(schema_text.encode()).hexdigest(), MODEL_TASK_SCHEMA_SHA256)
        clone = copy.deepcopy(fixture("valid-generation-task.v1.json"))
        self.assertIsNotNone(decode_model_task(clone))


if __name__ == "__main__":
    unittest.main()
