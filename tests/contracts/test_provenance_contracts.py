from __future__ import annotations

import copy
import json
import sys
import unittest
from hashlib import sha256
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
CORE_SRC = REPO / "services" / "core-api" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from research_observatory_core.provenance_contracts import (  # noqa: E402
    PROVENANCE_SCHEMA_SHA256,
    canonical_provenance_json,
    decode_provenance_event,
    is_known_provenance_event,
    provenance_event_errors,
    provenance_record_sha256,
)


class ProvenanceContractTests(unittest.TestCase):
    schema_path: Path
    fixture_path: Path

    @classmethod
    def setUpClass(cls) -> None:
        root = REPO / "packages" / "contracts" / "provenance"
        cls.schema_path = root / "provenance-event.schema.json"
        cls.fixture_path = root / "fixtures" / "valid-source-acquired-event.v1.json"

    def fixture(self) -> dict[str, object]:
        return json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def test_schema_and_generated_runtime_accept_minimized_prov_event(self) -> None:
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        event = self.fixture()
        self.assertEqual([], list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(event)))
        self.assertEqual((), provenance_event_errors(event))
        decoded = decode_provenance_event(event)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertTrue(is_known_provenance_event(decoded))
        before = canonical_provenance_json(decoded)
        event["actorid"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86dbb1"
        self.assertEqual(before, canonical_provenance_json(decoded))
        self.assertNotIn("@example", before)
        self.assertNotIn("C:\\", before)

    def test_semantics_fail_closed_without_copying_sensitive_content(self) -> None:
        actor = self.fixture()
        actor["actorid"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86dbb1"
        self.assertIn("actor-and-agent-match", provenance_event_errors(actor))
        overlap = self.fixture()
        data = overlap["data"]
        assert isinstance(data, dict)
        data["inputs"] = copy.deepcopy(data["outputs"])
        self.assertIn("input-output-sets-are-disjoint", provenance_event_errors(overlap))
        relations = self.fixture()
        relation_data = relations["data"]
        assert isinstance(relation_data, dict)
        relation_items = relation_data["relations"]
        assert isinstance(relation_items, list)
        relation_items.pop(0)
        self.assertIn("output-generation-relations-are-complete", provenance_event_errors(relations))
        raw = self.fixture()
        raw_data = raw["data"]
        assert isinstance(raw_data, dict)
        raw_data["rawDocument"] = "private research content"
        self.assertIsNone(decode_provenance_event(raw))
        subject = self.fixture()
        subject["subject"] = (
            "project/550e8400-e29b-41d4-a716-446655440000/source-observation/------------------------------------"
        )
        self.assertIsNone(decode_provenance_event(subject))

    def test_failed_source_acquisition_does_not_invent_an_output_entity(self) -> None:
        event = self.fixture()
        data = event["data"]
        assert isinstance(data, dict)
        activity = data["activity"]
        assert isinstance(activity, dict)
        activity["status"] = "failed"
        data["outputs"] = []
        relations = data["relations"]
        assert isinstance(relations, list)
        data["relations"] = [relation for relation in relations if relation["relationType"] == "wasAssociatedWith"]
        self.assertEqual((), provenance_event_errors(event))
        self.assertIsNotNone(decode_provenance_event(event))

    def test_future_event_is_storable_but_not_interpreted(self) -> None:
        event = self.fixture()
        event["type"] = "org.research-observatory.future.observed.v2"
        data = event["data"]
        assert isinstance(data, dict)
        activity = data["activity"]
        assert isinstance(activity, dict)
        activity["activityType"] = "future-observation"
        decoded = decode_provenance_event(event)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertFalse(is_known_provenance_event(decoded))

    def test_schema_hash_and_canonical_record_are_restart_stable(self) -> None:
        canonical_schema = self.schema_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        self.assertEqual(sha256(canonical_schema.encode("utf-8")).hexdigest(), PROVENANCE_SCHEMA_SHA256)
        event = self.fixture()
        canonical = canonical_provenance_json(event)
        self.assertEqual(canonical, canonical_provenance_json(json.loads(canonical)))
        self.assertEqual(f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}", provenance_record_sha256(event))


if __name__ == "__main__":
    unittest.main()
