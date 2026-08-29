from __future__ import annotations

import copy
import json
import sys
import unittest
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import cast

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

JsonRecord = dict[str, object]


class ProvenanceContractTests(unittest.TestCase):
    schema_path: Path
    fixture_path: Path

    @classmethod
    def setUpClass(cls) -> None:
        root = REPO / "packages" / "contracts" / "provenance"
        cls.schema_path = root / "provenance-event.schema.json"
        cls.fixture_path = root / "fixtures" / "valid-source-acquired-event.v1.json"

    def fixture(self) -> JsonRecord:
        return cast(JsonRecord, json.loads(self.fixture_path.read_text(encoding="utf-8")))

    @staticmethod
    def uuid(suffix: str) -> str:
        return f"018f47a2-4d6b-7f78-9f2e-7fb76c86{suffix}"

    @staticmethod
    def data_of(event: JsonRecord) -> JsonRecord:
        return cast(JsonRecord, event["data"])

    def activity_of(self, event: JsonRecord) -> JsonRecord:
        return cast(JsonRecord, self.data_of(event)["activity"])

    def relations_of(self, event: JsonRecord) -> list[JsonRecord]:
        return cast(list[JsonRecord], self.data_of(event)["relations"])

    @staticmethod
    def reference(entity: JsonRecord) -> JsonRecord:
        return {"entityId": entity["entityId"], "revisionId": entity["revisionId"]}

    @staticmethod
    def entity_subject(event: JsonRecord, entity: JsonRecord) -> str:
        return (
            f"project/{event['projectid']}/entity/{entity['entityKind']}/{entity['entityId']}"
            f"/revision/{entity['revisionId']}"
        )

    @staticmethod
    def relation(
        relation_id: str,
        relation_type: str,
        entity: JsonRecord | None,
        related_entity: JsonRecord | None,
        activity_id: str | None,
        agent_id: str | None,
        occurred_at: str = "2026-08-29T15:00:01.000Z",
    ) -> JsonRecord:
        return {
            "relationId": relation_id,
            "relationType": relation_type,
            "entity": entity,
            "relatedEntity": related_entity,
            "activityId": activity_id,
            "agentId": agent_id,
            "occurredAt": occurred_at,
        }

    def transform_event(self, status: str = "succeeded") -> JsonRecord:
        event = self.fixture()
        event["type"] = "org.research-observatory.document.parsed.v1"
        data = self.data_of(event)
        activity = self.activity_of(event)
        activity["activityType"] = "parsing"
        activity["status"] = status
        source = copy.deepcopy(cast(list[JsonRecord], data["outputs"])[0])
        document = copy.deepcopy(source)
        document["revisionId"] = self.uuid("dab3")
        document["entityKind"] = "document"
        document["contentHash"] = f"sha256:{'3' * 64}"
        data["inputs"] = [source]
        data["outputs"] = [document] if status == "succeeded" else []
        event["subject"] = self.entity_subject(event, document if status == "succeeded" else source)
        activity_id = cast(str, activity["activityId"])
        agent_id = cast(str, cast(JsonRecord, data["agent"])["agentId"])
        relations = [
            self.relation(self.uuid("daf4"), "used", self.reference(source), None, activity_id, None),
            self.relation(self.uuid("daf2"), "wasAssociatedWith", None, None, activity_id, agent_id),
        ]
        if status == "denied":
            relations.pop(0)
        if status == "succeeded":
            relations.extend(
                [
                    self.relation(
                        self.uuid("daf1"), "wasGeneratedBy", self.reference(document), None, activity_id, None
                    ),
                    self.relation(
                        self.uuid("daf5"),
                        "wasDerivedFrom",
                        self.reference(document),
                        self.reference(source),
                        activity_id,
                        None,
                    ),
                    self.relation(self.uuid("daf3"), "wasAttributedTo", self.reference(document), None, None, agent_id),
                ]
            )
        data["relations"] = relations
        return event

    def invalidation_event(self, status: str) -> JsonRecord:
        event = self.transform_event("failed" if status == "succeeded" else status)
        event["type"] = "org.research-observatory.entity.invalidated.v1"
        data = self.data_of(event)
        activity = self.activity_of(event)
        activity["activityType"] = "invalidation"
        activity["status"] = status
        input_ = cast(list[JsonRecord], data["inputs"])[0]
        event["subject"] = self.entity_subject(event, input_)
        if status == "succeeded":
            data["relations"] = [
                self.relation(
                    self.uuid("daf6"),
                    "wasInvalidatedBy",
                    self.reference(input_),
                    None,
                    cast(str, activity["activityId"]),
                    None,
                ),
                self.relation(
                    self.uuid("daf2"),
                    "wasAssociatedWith",
                    None,
                    None,
                    cast(str, activity["activityId"]),
                    cast(str, cast(JsonRecord, data["agent"])["agentId"]),
                ),
            ]
        return event

    def set_times(self, event: JsonRecord, started_at: str, ended_at: str) -> None:
        event["time"] = ended_at
        activity = self.activity_of(event)
        activity["startedAt"] = started_at
        activity["endedAt"] = ended_at
        for relation in self.relations_of(event):
            relation["occurredAt"] = ended_at

    def test_schema_and_generated_runtime_accept_minimized_exact_revision_event(self) -> None:
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
        event["actorid"] = self.uuid("dbb1")
        self.assertEqual(before, canonical_provenance_json(decoded))
        self.assertNotIn("@example", before)
        self.assertNotIn("C:\\", before)

    def test_sensitive_hostile_and_unbound_values_fail_closed(self) -> None:
        raw = self.fixture()
        self.data_of(raw)["rawDocument"] = "private research content"
        self.assertIsNone(decode_provenance_event(raw))
        actor = self.fixture()
        actor["actorid"] = self.uuid("dbb1")
        self.assertIn("actor-and-agent-match", provenance_event_errors(actor))
        unbound = self.fixture()
        unbound["subject"] = cast(str, unbound["subject"]).replace(self.uuid("dab2"), self.uuid("da99"))
        self.assertIn("subject-binds-exact-event-object", provenance_event_errors(unbound))
        wrong_kind = self.fixture()
        wrong_kind["subject"] = cast(str, wrong_kind["subject"]).replace(
            "entity/source-observation/", "entity/document/"
        )
        self.assertIn("subject-binds-exact-event-object", provenance_event_errors(wrong_kind))

    def test_success_failure_cancellation_and_denial_have_noncontradictory_shapes(self) -> None:
        for status in ("succeeded", "failed", "cancelled", "denied"):
            with self.subTest(operation="transform", status=status):
                self.assertEqual((), provenance_event_errors(self.transform_event(status)))
            with self.subTest(operation="invalidation", status=status):
                self.assertEqual((), provenance_event_errors(self.invalidation_event(status)))
        failed_acquisition = self.fixture()
        data = self.data_of(failed_acquisition)
        activity = self.activity_of(failed_acquisition)
        activity["status"] = "failed"
        data["outputs"] = []
        data["relations"] = [
            relation
            for relation in self.relations_of(failed_acquisition)
            if relation["relationType"] == "wasAssociatedWith"
        ]
        failed_acquisition["subject"] = (
            f"project/{failed_acquisition['projectid']}/activity/{activity['activityType']}/{activity['activityId']}"
        )
        self.assertEqual((), provenance_event_errors(failed_acquisition))

    def test_contradictory_outcomes_and_wrong_relation_roles_are_rejected(self) -> None:
        denied = self.invalidation_event("denied")
        denied_input = cast(list[JsonRecord], self.data_of(denied)["inputs"])[0]
        self.relations_of(denied).append(
            self.relation(
                self.uuid("daf7"),
                "wasInvalidatedBy",
                self.reference(denied_input),
                None,
                cast(str, self.activity_of(denied)["activityId"]),
                None,
            )
        )
        denied_errors = provenance_event_errors(denied)
        self.assertIn("relation-outcome-matches-activity-status", denied_errors)
        self.assertIn("known-event-relations-match-operation", denied_errors)

        def used_output(event: JsonRecord) -> None:
            used = next(item for item in self.relations_of(event) if item["relationType"] == "used")
            used["entity"] = self.reference(cast(list[JsonRecord], self.data_of(event)["outputs"])[0])

        def generated_input(event: JsonRecord) -> None:
            generated = next(item for item in self.relations_of(event) if item["relationType"] == "wasGeneratedBy")
            generated["entity"] = self.reference(cast(list[JsonRecord], self.data_of(event)["inputs"])[0])

        def attributed_input(event: JsonRecord) -> None:
            attributed = next(item for item in self.relations_of(event) if item["relationType"] == "wasAttributedTo")
            attributed["entity"] = self.reference(cast(list[JsonRecord], self.data_of(event)["inputs"])[0])

        def derived_reversed(event: JsonRecord) -> None:
            derived = next(item for item in self.relations_of(event) if item["relationType"] == "wasDerivedFrom")
            derived["entity"] = self.reference(cast(list[JsonRecord], self.data_of(event)["inputs"])[0])
            derived["relatedEntity"] = self.reference(cast(list[JsonRecord], self.data_of(event)["outputs"])[0])

        cases: tuple[Callable[[JsonRecord], None], ...] = (
            used_output,
            generated_input,
            attributed_input,
            derived_reversed,
        )
        for mutate in cases:
            event = self.transform_event()
            mutate(event)
            self.assertIn("relation-roles-match-event-objects", provenance_event_errors(event))

        acquired = self.fixture()
        output = cast(list[JsonRecord], self.data_of(acquired)["outputs"])[0]
        self.relations_of(acquired).append(
            self.relation(
                self.uuid("daf7"),
                "wasInvalidatedBy",
                self.reference(output),
                None,
                cast(str, self.activity_of(acquired)["activityId"]),
                None,
            )
        )
        acquired_errors = provenance_event_errors(acquired)
        self.assertIn("relation-roles-match-event-objects", acquired_errors)
        self.assertIn("known-event-relations-match-operation", acquired_errors)

    def test_relation_identity_fact_and_exact_revision_binding_are_unique(self) -> None:
        duplicate = self.transform_event()
        self.relations_of(duplicate).append(copy.deepcopy(self.relations_of(duplicate)[0]))
        self.assertIn("relation-identities-and-facts-are-unique", provenance_event_errors(duplicate))

        reused_id = self.transform_event()
        distinct = copy.deepcopy(self.relations_of(reused_id)[0])
        distinct["occurredAt"] = "2026-08-29T15:00:00.500Z"
        self.relations_of(reused_id).append(distinct)
        self.assertIn("relation-identities-and-facts-are-unique", provenance_event_errors(reused_id))

        wrong_revision = self.transform_event()
        used = next(item for item in self.relations_of(wrong_revision) if item["relationType"] == "used")
        cast(JsonRecord, used["entity"])["revisionId"] = self.uuid("da99")
        self.assertIn("relations-close-over-event-objects", provenance_event_errors(wrong_revision))

    def test_future_type_and_schema_compatible_utc_boundaries_match(self) -> None:
        future = self.fixture()
        future["type"] = "org.research-observatory.future.observed.v2"
        self.activity_of(future)["activityType"] = "future-observation"
        decoded = decode_provenance_event(future)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertFalse(is_known_provenance_event(decoded))

        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        year_zero = self.fixture()
        self.set_times(year_zero, "0000-01-01T00:00:00.000Z", "0000-01-01T00:00:01.000Z")
        self.assertIsNone(decode_provenance_event(year_zero))
        self.assertTrue(list(validator.iter_errors(year_zero)))
        with self.assertRaisesRegex(ValueError, "invalid provenance event"):
            canonical_provenance_json(year_zero)
        for started_at, ended_at in (
            ("0001-01-01T00:00:00.000Z", "0001-01-01T00:00:01.000Z"),
            ("9999-12-31T23:59:58.999Z", "9999-12-31T23:59:59.999Z"),
        ):
            with self.subTest(started_at=started_at):
                boundary = self.fixture()
                self.set_times(boundary, started_at, ended_at)
                self.assertEqual([], list(validator.iter_errors(boundary)))
                self.assertIsNotNone(decode_provenance_event(boundary))
                canonical = canonical_provenance_json(boundary)
                self.assertEqual(canonical, canonical_provenance_json(json.loads(canonical)))
                self.assertEqual(
                    f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}",
                    provenance_record_sha256(boundary),
                )

    def test_schema_hash_and_canonical_record_are_restart_stable(self) -> None:
        canonical_schema = self.schema_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        self.assertEqual(sha256(canonical_schema.encode("utf-8")).hexdigest(), PROVENANCE_SCHEMA_SHA256)
        event = self.fixture()
        canonical = canonical_provenance_json(event)
        self.assertEqual(canonical, canonical_provenance_json(json.loads(canonical)))
        self.assertEqual(f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}", provenance_record_sha256(event))


if __name__ == "__main__":
    unittest.main()
