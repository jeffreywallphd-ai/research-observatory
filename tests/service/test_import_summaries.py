"""Fixed-draft summary facts are neither scholarly identity nor corpus changes."""

from __future__ import annotations

import unittest
from dataclasses import replace

from research_observatory_core.ingestion.import_drafts import (
    ImportPermission,
    ImportRights,
    MappedField,
    propose_fields,
    review_record,
)
from research_observatory_core.ingestion.import_summaries import summarize_record

from tests.service.test_import_drafts import parse, profile

ALLOWED = ImportRights(
    store=ImportPermission(value="permitted", basis="researcher-confirmed"),
    inspect=ImportPermission(value="permitted", basis="researcher-confirmed"),
)


class ImportSummaryTests(unittest.TestCase):
    def facts(self, record, *, included=True, fields=None, rights=None):
        proposal = propose_fields(record, profile())
        decision = review_record(
            record, included=included, fields=proposal.fields if fields is None else fields, rights=rights
        )
        return summarize_record(record, decision, proposal.warnings, ALLOWED)

    def test_raw_and_normalized_doi_candidates_are_distinct_from_record_identity(self):
        records = parse(
            b"title,doi,author,year,container\nSame,https://doi.org/10.99999/ABC,A,2026,Journal\nSame,https://doi.org/10.99999/ABC,A,2026,Journal\nDifferent,doi:10.99999/abc,,,\n"
        )
        a, b, c = (self.facts(record) for record in records[1:])
        self.assertNotEqual(a.record_key, b.record_key)
        self.assertEqual(a.raw_key, b.raw_key)
        self.assertNotEqual(a.raw_key, c.raw_key)
        self.assertEqual(a.doi_key, c.doi_key)
        self.assertEqual(31, a.coverage_mask)
        self.assertEqual(3, c.coverage_mask)
        self.assertNotIn("Same", a.model_dump_json())

    def test_context_malformed_and_excluded_rows_supply_no_candidate_or_coverage(self):
        header, record = parse(b"title,doi\nSynthetic,10.99999/a\n")
        malformed = parse(b"invalid\n", "doi-list")[0]
        for source in (header, record, malformed):
            with self.subTest(kind=source.kind, status=source.status):
                result = self.facts(source, included=False)
                self.assertEqual(0, result.coverage_mask)
                self.assertIsNone(result.raw_key)
                self.assertIsNone(result.doi_key)
                self.assertEqual(source.kind, result.record_kind)
                self.assertEqual(source.status, result.parse_status)

    def test_corrections_normalize_for_candidates_without_mutating_accepted_values(self):
        record = parse(b"title\nSynthetic\n")[1]
        fields = (
            MappedField(name="doi", value="HTTPS://DOI.ORG/10.99999/AbC", source_field_index=None, origin="correction"),
        )
        result = self.facts(record, fields=fields)
        other = self.facts(parse(b"10.99999/abc\n", "doi-list")[0])
        self.assertEqual(other.doi_key, result.doi_key)
        self.assertEqual(2, result.coverage_mask)
        self.assertEqual("HTTPS://DOI.ORG/10.99999/AbC", fields[0].value)

    def test_missing_permissions_and_substituted_decision_fail_closed(self):
        record = parse(b"title\nSynthetic\n")[1]
        decision = review_record(record, included=True, fields=())
        for rights in (
            ImportRights(),
            ALLOWED.model_copy(update={"inspect": ImportPermission()}),
            ALLOWED.model_copy(update={"store": ImportPermission()}),
        ):
            with self.assertRaisesRegex(ValueError, "summary-rights-denied"):
                summarize_record(record, decision, (), rights)
            with self.assertRaisesRegex(ValueError, "summary-rights-denied"):
                summarize_record(record, decision.model_copy(update={"rights": rights}), (), ALLOWED)
        with self.assertRaisesRegex(ValueError, "summary-record-mismatch"):
            summarize_record(replace(record, ordinal=record.ordinal + 1), decision, (), ALLOWED)
