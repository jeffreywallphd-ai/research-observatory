"""Transport-sized projections over actual accepted, protected preview records."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError
from research_observatory_core.import_review import (
    RESPONSE_BYTES,
    ColumnSelection,
    GroupEdit,
    ImportReview,
    MappingEdit,
    RecordSelection,
    ReviewPageRequest,
    encoded_size,
)
from research_observatory_core.ports.import_previews import PreviewProblem

from tests.data import test_import_preview_drafts as fixture


class ImportReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ImportPreviewDraftTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.review = ImportReview(self.fixture.repository())
        self.actor = self.fixture.actor

    def accepted(self, raw=None):
        preview, records = self.fixture.accepted() if raw is None else self.fixture.accepted(raw)
        self.review.begin(preview, actor=self.actor())
        return preview, records

    def test_json_lists_are_explicit_transport_not_domain_relaxation(self):
        edit = MappingEdit.model_validate({"expectedRevision": 1, "columns": [{"index": 0, "target": "title"}]})
        self.assertEqual(0, edit.columns[0].index)
        for value in (True, "1", 1.5):
            with self.assertRaises(ValidationError):
                ReviewPageRequest.model_validate({"revision": value})
        with self.assertRaises(ValidationError):
            MappingEdit.model_validate({"expectedRevision": 1, "columns": [], "actor": "caller"})

    def test_page_uses_one_bounded_repository_read(self):
        preview, _ = self.accepted(b"title\n" + b"Synthetic\n" * 105)
        repository = self.review._repository
        with patch.object(repository, "draft_page", wraps=repository.draft_page) as read:
            page = self.review.page(preview, ReviewPageRequest(revision=1, limit=100))
        self.assertEqual(list(range(1, 101)), [row.ordinal for row in page.records])
        self.assertFalse(page.complete)
        read.assert_called_once_with(preview, revision=1, after=0, limit=100)

    def test_sparse_members_batch_and_cursor_follow_emitted_prefix(self):
        preview, _ = self.accepted(b"title\nOne\nTwo\nThree\nFour\n")
        repository = self.review._repository
        ordinals = (2, 4, 5)

        def members(_preview, **request):
            return tuple(n for n in ordinals if n > request["after"])[: request["limit"]]

        def page(after=0):
            return self.review.duplicate_members(
                preview, revision=1, reason="doi", group_key="a" * 64, after=after, limit=100
            )

        with patch.object(repository, "summary_members", side_effect=members):
            with patch.object(repository, "draft_selection", wraps=repository.draft_selection) as read:
                whole = page()
            self.assertEqual(list(ordinals), [row.ordinal for row in whole.records])
            read.assert_called_once_with(preview, revision=1, ordinals=ordinals)
            self.assertTrue(whole.complete)
            with patch(
                "research_observatory_core.import_draft_repository.StoredImportRecord.model_dump_json",
                return_value="x" * (8 * 1024 * 1024),
            ):
                first = page()
                second = page(first.next_after)
                last = page(second.next_after)
            self.assertEqual([2, 4, 5], [first.next_after, second.next_after, last.next_after])
            self.assertEqual([False, False, True], [first.complete, second.complete, last.complete])
            with patch("research_observatory_core.import_review.RESPONSE_BYTES", encoded_size(first)):
                bounded_page = page()
            self.assertEqual([2], [row.ordinal for row in bounded_page.records])
            self.assertEqual(2, bounded_page.next_after)
            self.assertFalse(bounded_page.complete)
            with (
                patch("research_observatory_core.import_review.RESPONSE_BYTES", 1),
                self.assertRaisesRegex(PreviewProblem, "response-limit"),
            ):
                page()

    def test_sparse_members_recheck_head_after_selected_read(self):
        preview, _ = self.accepted()
        repository = self.review._repository
        original = repository.draft_selection

        def changed(*args, **kwargs):
            rows = original(*args, **kwargs)
            self.fixture.change(preview, 1)
            return rows

        with (
            patch.object(repository, "summary_members", return_value=(2,)),
            patch.object(repository, "draft_selection", side_effect=changed),
            self.assertRaisesRegex(PreviewProblem, "revision-conflict"),
        ):
            self.review.duplicate_members(preview, revision=1, reason="doi", group_key="a" * 64, after=0, limit=100)

    def test_summary_page_detail_keep_original_and_correction_separate(self):
        preview, records = self.accepted()
        page = self.review.page(preview, ReviewPageRequest(revision=1, limit=2))
        self.assertEqual([1, 2], [item.ordinal for item in page.records])
        self.assertFalse(page.complete)
        request = GroupEdit.model_validate(
            {
                "expectedRevision": 1,
                "records": [{"ordinal": 2, "recordKey": records[1].record_key}],
                "corrections": [{"name": "title", "value": "Corrected"}],
            }
        )
        result = self.review.edit(preview, request, actor=self.actor())
        self.assertEqual(2, result.revision)
        raw = self.review.detail(preview, revision=2, ordinal=2, record_key=records[1].record_key, section="raw")
        effective = self.review.detail(
            preview, revision=2, ordinal=2, record_key=records[1].record_key, section="effective"
        )
        self.assertEqual("First", raw.fields[0].value)
        self.assertEqual("Corrected", effective.fields[0].value)
        self.assertEqual("correction", effective.fields[0].origin)
        self.assertIsNone(effective.fields[0].source_field_index)
        with self.assertRaisesRegex(PreviewProblem, "revision-conflict"):
            self.review.edit(preview, request, actor=self.actor())

    def test_duplicate_column_indices_and_mapping_high_water_after_undo(self):
        preview, records = self.accepted(b"name,name\nFirst,Second\n")
        mapped = self.review.map(
            preview,
            MappingEdit(expected_revision=1, columns=[ColumnSelection(index=1, target="title")]),
            actor=self.actor(),
        )
        self.assertEqual(2, mapped.mapping_revision)
        row = self.review.page(preview, ReviewPageRequest(revision=2, after=1)).records[0]
        assert row.title is not None
        self.assertEqual("Second", row.title.text)
        self.fixture.change(preview, 2, restore_revision=1)
        mapped = self.review.map(
            preview,
            MappingEdit(expected_revision=3, columns=[ColumnSelection(index=0, target="title")]),
            actor=self.actor(),
        )
        self.assertEqual(3, mapped.mapping_revision)
        title = self.review.page(preview, ReviewPageRequest(revision=4, after=1)).records[0].title
        assert title is not None
        self.assertEqual("First", title.text)
        self.assertEqual("name", records[0].fields[0].name)

    def test_group_exclusion_preserves_fields_and_substitution_is_atomic(self):
        preview, records = self.accepted()
        bad = GroupEdit(
            expected_revision=1,
            records=[
                RecordSelection(ordinal=2, record_key=records[1].record_key),
                RecordSelection(ordinal=3, record_key="f" * 64),
            ],
            included=False,
        )
        with self.assertRaisesRegex(PreviewProblem, "record-mismatch"):
            self.review.edit(preview, bad, actor=self.actor())
        self.assertEqual(1, self.review.summary(preview).revision)
        good = bad.model_copy(update={"records": bad.records[:1]})
        self.review.edit(preview, good, actor=self.actor())
        row = self.review.page(preview, ReviewPageRequest(revision=2, after=1)).records[0]
        self.assertFalse(row.included)
        assert row.title is not None
        self.assertEqual("First", row.title.text)

    def test_large_complete_fields_use_bounded_detail_pages_not_truncation(self):
        value = "x" * 64000
        raw = ("title,heading\n" + value + "," + value + "\n").encode()
        preview, records = self.accepted(raw)
        summary = self.review.page(preview, ReviewPageRequest(revision=1, after=1)).records[0]
        assert summary.title is not None
        self.assertTrue(summary.title.truncated)
        detail = self.review.detail(preview, revision=1, ordinal=2, record_key=records[1].record_key, section="raw")
        self.assertEqual(value, detail.fields[0].value)
        self.assertTrue(detail.complete)
        self.assertLessEqual(encoded_size(detail), RESPONSE_BYTES)

    def test_complete_report_pages_advance_scanned_ordinals_and_recheck_rights(self):
        preview, _records = self.accepted(b"title\n" + b"Synthetic\n" * 105)
        first = self.review.report(preview, ReviewPageRequest(revision=1, limit=100))
        last = self.review.report(preview, ReviewPageRequest(revision=1, after=first.next_after, limit=100))
        self.assertFalse(first.complete)
        self.assertTrue(last.complete)
        self.assertEqual(106, last.next_after)
        combined = first.csv + last.csv
        self.assertEqual(1, combined.count("ordinal,line_start"))
        self.assertIn("106,", combined)
        self.assertNotIn("Synthetic", combined)
        self.fixture.repository().cancel(preview, actor=self.actor())
        with self.assertRaises(PreviewProblem):
            self.review.report(preview, ReviewPageRequest(revision=1, after=100))

    def test_detail_substitution_and_invalid_cursors_are_denied(self):
        preview, _ = self.accepted()
        with self.assertRaisesRegex(PreviewProblem, "record-mismatch"):
            self.review.detail(preview, revision=1, ordinal=2, record_key="0" * 64, section="raw")
        with self.assertRaisesRegex(PreviewProblem, "cursor"):
            self.review.page(preview, ReviewPageRequest(revision=1, after=4))

    def test_detail_pages_split_below_bridge_limit_without_losing_fields(self):
        value = "x" * 64000
        raw = (",".join(f"column-{index}" for index in range(16)) + "\n" + ",".join([value] * 16) + "\n").encode()
        preview, records = self.accepted(raw)
        first = self.review.detail(
            preview, revision=1, ordinal=2, record_key=records[1].record_key, section="raw", limit=100
        )
        self.assertFalse(first.complete)
        last = self.review.detail(
            preview,
            revision=1,
            ordinal=2,
            record_key=records[1].record_key,
            section="raw",
            start=first.next_index,
            limit=100,
        )
        self.assertTrue(last.complete)
        self.assertEqual(list(range(16)), [field.index for field in first.fields + last.fields])
        self.assertTrue(all(field.value == value for field in first.fields + last.fields))
        self.assertLessEqual(encoded_size(first), RESPONSE_BYTES)
        self.assertLessEqual(encoded_size(last), RESPONSE_BYTES)

    def test_large_group_is_rejected_incrementally_without_partial_revision(self):
        preview, records = self.accepted(b"title\n" + b"Synthetic\n" * 100)
        edit = GroupEdit.model_validate(
            {
                "expectedRevision": 1,
                "records": [{"ordinal": row.ordinal, "recordKey": row.record_key} for row in records[1:]],
                "corrections": [{"name": "author", "value": "x" * 65000}, {"name": "author", "value": "y" * 65000}],
            }
        )
        with patch.object(self.review, "_record", wraps=self.review._record) as selected:
            with self.assertRaisesRegex(PreviewProblem, "draft-change-limit"):
                self.review.edit(preview, edit, actor=self.actor())
            self.assertLess(selected.call_count, 70)
        self.assertEqual(1, self.review.summary(preview).revision)


if __name__ == "__main__":
    unittest.main()
