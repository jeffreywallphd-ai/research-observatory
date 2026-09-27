"""Portable generated schemas and strict caller/source authority separation."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportRights
from research_observatory_core.reconciliation.contracts import (
    ReconciliationInspection,
    ReconciliationResult,
    SourceAddress,
    SourceAssertion,
)
from research_observatory_core.reconciliation.exact import IdentifierAssertion
from research_observatory_core.reconciliation.identifiers import normalize_identifier
from research_observatory_core.reconciliation_api import ReconciliationRequest

REPO = Path(__file__).resolve().parents[2]


class ReconciliationContractTests(unittest.TestCase):
    def test_generated_schemas_consume_actual_portable_values(self):
        address = SourceAddress(
            kind="connector-record", context_id=new_uuid_v7(), revision_id=new_uuid_v7(), ordinal=0, record_key=None
        )
        source = SourceAssertion(
            project_id=new_uuid_v7(),
            address=address,
            source_revision_id=address.revision_id,
            provider="crossref",
            identifiers=(IdentifierAssertion(scheme="doi", observed="10.1234/SYNTHETIC"),),
            fields=(),
            rights=ImportRights(),
            source_sha256="a" * 64,
        )
        result = ReconciliationResult(
            project_id=source.project_id,
            assertion_revision_id=new_uuid_v7(),
            source=address,
            work_id=new_uuid_v7(),
            work_revision_id=new_uuid_v7(),
            disposition="new-work",
            candidates=(),
            flags=(),
            knowledge_status="inferred",
            matching_reason="no-exact-match",
        )
        inspection = ReconciliationInspection(result=result, assertion=source)
        for filename, value in (
            ("normalized-identifier", normalize_identifier("doi", "10.1234/SYNTHETIC")),
            ("source-assertion", source),
            ("reconciliation-result", result),
            ("reconciliation-inspection", inspection),
        ):
            with self.subTest(contract=filename):
                schema = json.loads(
                    (REPO / f"packages/contracts/scholarly-records/{filename}.schema.json").read_text(encoding="utf-8")
                )
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                document = value.model_dump(mode="json", by_alias=True)
                validator.validate(document)
                self.assertFalse(validator.is_valid(document | {"callerTrusted": True}))
        self.assertIn("normalizedIdentifiers", inspection.model_dump(mode="json", by_alias=True))

    def test_client_cannot_supply_grants_or_replace_source_authority(self):
        address = {
            "kind": "connector-record",
            "contextId": new_uuid_v7(),
            "revisionId": new_uuid_v7(),
            "ordinal": 0,
            "recordKey": None,
        }
        document = {"root": "synthetic-project", "commandId": new_uuid_v7(), "source": address}
        ReconciliationRequest.model_validate_json(json.dumps(document))
        for candidate in (
            document | {"rights": {"inspect": "permitted"}},
            document | {"source": address | {"projectId": new_uuid_v7()}},
            document | {"source": address | {"ordinal": True}},
            document | {"source": address | {"recordKey": "a" * 64}},
            document | {"source": address | {"kind": "import-member"}},
            document | {"source": address | {"ordinal": 1000}},
        ):
            with self.subTest(candidate=candidate), self.assertRaises(ValidationError):
                ReconciliationRequest.model_validate_json(json.dumps(candidate))
