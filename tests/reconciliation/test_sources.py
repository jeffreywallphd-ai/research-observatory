"""Reconcile actual parser observations without inheriting lossy candidate casing."""

import hashlib
import io
import unittest

from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import (
    ImportRights,
    MappedField,
    MappingProfile,
    RecordDecision,
    propose_fields,
)
from research_observatory_core.ingestion.reference_imports import ImportSession, ImportSource
from research_observatory_core.ports.import_commits import ImportManifestMember
from research_observatory_core.reconciliation.contracts import SourceAddress
from research_observatory_core.reconciliation.exact import exact_keys
from research_observatory_core.reconciliation.sources import import_assertion


class SourceProjectionTests(unittest.TestCase):
    def test_import_formats_preserve_original_doi_case_and_source_bytes(self):
        cases = (
            ("doi-list", "10.1234/ÁBC\n"),
            ("ris", "TY  - JOUR\nDO  - 10.1234/ÁBC\nER  - \n"),
            ("bibtex", "@article{synthetic,doi={10.1234/ÁBC},title={Synthetic}}"),
            ("csl-json", '[{"type":"article-journal","DOI":"10.1234/ÁBC","title":"Synthetic"}]'),
            ("csv", "title,doi\nSynthetic,10.1234/ÁBC\n"),
        )
        for format_name, text in cases:
            with self.subTest(format_name=format_name):
                raw = text.encode()
                records = tuple(
                    ImportSession(
                        io.BytesIO(raw), ImportSource("synthetic.txt", hashlib.sha256(raw).hexdigest()), format_name
                    ).records()
                )
                record = next(item for item in records if item.kind == "record")
                fields = propose_fields(
                    record,
                    MappingProfile(
                        profile_id=new_uuid_v7(), revision=1, predecessor_revision=None, mode="automatic", bindings=()
                    ),
                ).fields
                member = ImportManifestMember(
                    ordinal=record.ordinal,
                    record_key=record.record_key,
                    source_record_revision_id=new_uuid_v7(),
                    decision=RecordDecision(
                        record_key=record.record_key, ordinal=record.ordinal, included=True, fields=fields
                    ),
                    warnings=(),
                    comparison="not-compared",
                    previous_record_revision_id=None,
                )
                address = SourceAddress(
                    kind="import-member",
                    context_id=new_uuid_v7(),
                    revision_id=new_uuid_v7(),
                    ordinal=record.ordinal,
                    record_key=record.record_key,
                )
                projected = import_assertion(
                    project_id=new_uuid_v7(), address=address, record=record, member=member, rights=ImportRights()
                )
                doi = next(item for item in projected.identifiers if item.scheme == "doi")
                self.assertEqual("10.1234/Ábc", doi.normalized.canonical)
                self.assertIn("Á", doi.observed)
                self.assertEqual(record.raw_sha256, projected.source_sha256)
                corrected = member.model_copy(
                    update={
                        "decision": member.decision.model_copy(
                            update={
                                "fields": (
                                    *(item for item in fields if item.name != "doi"),
                                    MappedField(
                                        name="doi",
                                        value="10.1234/accepted-correction",
                                        source_field_index=None,
                                        origin="correction",
                                    ),
                                )
                            }
                        )
                    }
                )
                revised = import_assertion(
                    project_id=projected.project_id,
                    address=address,
                    record=record,
                    member=corrected,
                    rights=ImportRights(),
                )
                raw_doi = next(
                    item for item in revised.identifiers if item.scheme == "doi" and item.origin == "observed"
                )
                self.assertEqual(doi.observed, raw_doi.observed)
                self.assertFalse(raw_doi.active_for_matching)
                self.assertEqual(frozenset({("doi", "10.1234/accepted-correction")}), exact_keys(revised.identifiers))
