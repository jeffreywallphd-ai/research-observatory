"""Synthetic data only: parser results are not scholarly evidence."""

from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.ingestion.reference_imports import (  # noqa: E402
    ImportLimits,
    ImportProblem,
    ImportSession,
    ImportSource,
)


class ShortReads(io.BytesIO):
    def __init__(self, payload: bytes, width: int = 7):
        super().__init__(payload)
        self.width = width

    def read(self, size: int | None = -1) -> bytes:
        if size is None or not 0 < size <= 8192:
            raise AssertionError("Only bounded reads are permitted")
        return super().read(min(size, self.width))


def session(payload: bytes, format_name: str, **kwargs):
    source = ImportSource("synthetic-library", hashlib.sha256(payload).hexdigest())
    return ImportSession(ShortReads(payload), source, format_name, **kwargs)


class ReferenceImportTests(unittest.TestCase):
    def test_existing_ris_and_bibtex_fixtures_preserve_raw_locations(self):
        for extension, format_name in (("ris", "ris"), ("bib", "bibtex")):
            payload = (REPO / f"tests/fixtures/scholarly-corpus/metadata/records.{extension}").read_bytes()
            run = session(payload, format_name)
            records = list(run.records())
            self.assertTrue(run.complete)
            self.assertEqual(2, len(records))
            self.assertTrue(all(record.status == "parsed" for record in records))
            for record in records:
                self.assertEqual(payload[record.byte_start : record.byte_end], record.raw_bytes)
                self.assertEqual(hashlib.sha256(record.raw_bytes).hexdigest(), record.raw_sha256)
                self.assertTrue(record.fields)
                self.assertIsNone(record.to_document()["mappingDecision"])

    def test_five_formats_isolate_balanced_malformed_records(self):
        samples = {
            "ris": b"TY  - JOUR\nTI  - First\nER  -\nTY  - JOUR\nbroken\nER  -\nTY  - JOUR\nTI  - Last\nER  -\n",
            "bibtex": b"@article{a,title={First}}\n@article{b,title=}\n@article{c,title={Last}}",
            "csl-json": b'[{"id":"a","type":"article","title":"First"},42,{"id":"c","type":"article","title":"Last"}]',
            "doi-list": b"10.99999/first\nnot a DOI\n10.99999/last\n",
            "csv": b"title,note\nFirst,ok\nbroken,too,many\nLast,ok\n",
        }
        for format_name, payload in samples.items():
            with self.subTest(format=format_name):
                run = session(payload, format_name)
                records = [item for item in run.records() if item.kind == "record"]
                self.assertEqual(["parsed", "malformed", "parsed"], [item.status for item in records])
                self.assertTrue(run.complete)
                self.assertEqual(1, run.error_count)

    def test_raw_duplicates_unknowns_and_normalized_candidates_are_distinct(self):
        payload = b'[{"id":"a","type":"article","title":" First ","title":"Second","x-extra":{"a":[1,2]},"DOI":"https://doi.org/10.99999/ABC(ONE)"}]'
        run = session(payload, "csl-json")
        (record,) = list(run.records())
        self.assertEqual(2, len([field for field in record.fields if field.name == "title"]))
        self.assertIn("x-extra", [field.name for field in record.fields])
        self.assertIn("duplicate-field", record.warnings)
        self.assertIn("10.99999/abc(one)", [item.value for item in record.candidates])
        self.assertIn(b'" First "', record.raw_bytes)
        self.assertTrue(all(item["confidence"] == {"kind": "unknown"} for item in record.to_document()["candidates"]))

    def test_csv_multiline_duplicate_headers_and_formulas_remain_data(self):
        payload = b'title,title,note\r\n"Synthetic\r\nmultiline",Other,"=SUM(1,2)"\r\n'
        run = session(payload, "csv")
        header, record = list(run.records())
        self.assertEqual("header", header.kind)
        self.assertIn("duplicate-field", header.warnings)
        self.assertEqual(["title", "title", "note"], [field.name for field in record.fields])
        self.assertEqual("=SUM(1,2)", record.fields[2].raw_value)
        self.assertIn("formula-like-cell", record.warnings)
        self.assertEqual((2, 3), (record.line_start, record.line_end))
        self.assertEqual(payload[record.byte_start : record.byte_end], record.raw_bytes)

    def test_bibtex_nested_values_concat_macros_and_commands_are_inert(self):
        payload = (
            rb'@string{prefix="Synthetic "}'
            + b"\n"
            + rb'@article{a,title=prefix # {A {nested} title},note={\write18{never execute}},x_unknown="a,b"}'
        )
        run = session(payload, "bibtex")
        with patch("subprocess.run", side_effect=AssertionError("No subprocess")):
            directive, record = list(run.records())
        self.assertEqual("directive", directive.kind)
        self.assertEqual("parsed", record.status)
        self.assertIn("Synthetic A {nested} title", [item.value for item in record.candidates])
        self.assertIn(rb"\write18", record.raw_bytes)
        self.assertIn("x_unknown", [field.name for field in record.fields])

    def test_keys_ignore_filename_and_chunking_but_bind_ordinal_and_bytes(self):
        payload = b"10.99999/Same\n10.99999/Same\n"
        source = ImportSource("one.txt", hashlib.sha256(payload).hexdigest())
        first = list(ImportSession(ShortReads(payload, 1), source, "doi-list").records())
        second = list(
            ImportSession(ShortReads(payload, 8192), replace(source, filename="two.txt"), "doi-list").records()
        )
        self.assertEqual([item.record_key for item in first], [item.record_key for item in second])
        self.assertNotEqual(first[0].record_key, first[1].record_key)
        changed = list(session(payload.lower(), "doi-list").records())
        self.assertNotEqual(first[0].record_key, changed[0].record_key)

    def test_utf8_bom_split_unicode_and_invalid_record_recovery(self):
        payload = (
            b"\xef\xbb\xbf"
            + "TY  - JOUR\r\nTI  - Synthétique\r\nER  -\r\n".encode()
            + b"TY  - JOUR\nTI  - \xff\nER  -\nTY  - JOUR\nER  -\n"
        )
        run = session(payload, "ris")
        records = list(run.records())
        self.assertEqual(["parsed", "malformed", "parsed"], [item.status for item in records])
        self.assertEqual(3, records[0].byte_start)
        self.assertIn("invalid-encoding", records[1].warnings)
        self.assertIn(b"\xff", records[1].raw_bytes)

    def test_oversized_record_is_bounded_and_following_record_survives(self):
        payload = b"10.99999/" + b"x" * 200 + b"\n10.99999/ok\n"
        run = session(payload, "doi-list", limits=ImportLimits(max_record_bytes=64))
        bad, good = list(run.records())
        self.assertEqual("malformed", bad.status)
        self.assertIsNone(bad.raw_bytes)
        self.assertEqual(hashlib.sha256(payload[: bad.byte_end]).hexdigest(), bad.raw_sha256)
        self.assertEqual("parsed", good.status)
        self.assertTrue(run.complete)

    def test_cancel_inside_large_field_and_restart_from_immutable_input(self):
        payload = b"@article{a,title={" + b"x" * 20000 + b"}}"
        stream = ShortReads(payload, 7)
        source = ImportSource("synthetic.bib", hashlib.sha256(payload).hexdigest())
        run = ImportSession(stream, source, "bibtex", cancelled=lambda: stream.tell() > 100)
        with self.assertRaisesRegex(ImportProblem, "cancelled"):
            list(run.records())
        self.assertFalse(run.complete)
        self.assertLess(stream.tell(), len(payload))
        replay = session(payload, "bibtex")
        self.assertEqual(1, len(list(replay.records())))
        self.assertTrue(replay.complete)

    def test_digest_mismatch_and_source_limit_never_report_completion(self):
        payload = b"10.99999/one\n"
        for source, limits, code in (
            (ImportSource("test", "0" * 64), ImportLimits(), "source-digest-mismatch"),
            (
                ImportSource("test", hashlib.sha256(payload).hexdigest()),
                ImportLimits(max_source_bytes=8),
                "source-limit",
            ),
        ):
            run = ImportSession(ShortReads(payload), source, "doi-list", limits=limits)
            with self.assertRaisesRegex(ImportProblem, code):
                list(run.records())
            self.assertFalse(run.complete)

    def test_unterminated_syntax_is_retained_not_false_success(self):
        for format_name, payload in (
            ("bibtex", b"@article{a,title={unfinished"),
            ("csv", b'title\n"unfinished'),
            ("csl-json", b'[{"title":"unfinished'),
        ):
            with self.subTest(format=format_name):
                run = session(payload, format_name)
                records = list(run.records())
                self.assertEqual("malformed", records[-1].status)
                self.assertGreater(run.error_count, 0)

    def test_path_names_denied_and_real_file_needs_no_seek(self):
        for name in ("../library.ris", "folder/library.ris", "folder\\library.ris"):
            with self.assertRaises(ValueError):
                ImportSource(name, "0" * 64)
        payload = b"10.99999/local\n"
        with tempfile.TemporaryFile() as source_file:
            source_file.write(payload)
            source_file.seek(0)
            run = ImportSession(source_file, ImportSource("local.txt", hashlib.sha256(payload).hexdigest()), "doi-list")
            self.assertEqual(1, len(list(run.records())))
            self.assertTrue(run.complete)

    def test_invalid_csv_header_cannot_promote_data_to_a_replacement_header(self):
        for payload in (b",title\na,b\nc,d\n", b"\xff,title\na,b\n"):
            run = session(payload, "csv")
            records = list(run.records())
            self.assertEqual("header", records[0].kind)
            self.assertTrue(all(record.status == "malformed" for record in records))
            self.assertTrue(all("csv-header-unavailable" in record.warnings for record in records[1:]))

    def test_field_and_depth_limits_leave_following_records_parseable(self):
        cases = (
            ("ris", b"TY  - JOUR\nTI  - A\nAU  - A\nAU  - B\nER  -\nTY  - JOUR\nER  -\n", ImportLimits(max_fields=3)),
            ("csl-json", b'[{"x":[[[[1]]]]},{"title":"ok"}]', ImportLimits(max_depth=3)),
            ("doi-list", b"10.99999/" + b"a" * 30 + b"\n10.99999/ok\n", ImportLimits(max_field_bytes=20)),
        )
        for format_name, payload, limits in cases:
            with self.subTest(format=format_name):
                run = session(payload, format_name, limits=limits)
                records = list(run.records())
                self.assertEqual(["malformed", "parsed"], [record.status for record in records])
                self.assertTrue(run.complete)

    def test_abandoned_iterator_record_count_timeout_and_io_failure_are_not_complete(self):
        run = session(b"10.99999/one\n10.99999/two\n", "doi-list")
        iterator = run.records()
        next(iterator)
        iterator.close()
        self.assertFalse(run.complete)
        with self.assertRaisesRegex(ImportProblem, "session-already-consumed"):
            list(run.records())
        limited = session(b"10.99999/one\n10.99999/two\n", "doi-list", limits=ImportLimits(max_records=1))
        with self.assertRaisesRegex(ImportProblem, "record-count-limit"):
            list(limited.records())
        self.assertFalse(limited.complete)
        ticks = iter((0.0, 999.0))
        expired = session(b"10.99999/one", "doi-list", clock=lambda: next(ticks))
        with self.assertRaisesRegex(ImportProblem, "timeout"):
            list(expired.records())
        self.assertFalse(expired.complete)
        broken = session(b"10.99999/one", "doi-list")
        with (
            patch.object(broken.stream, "read", side_effect=OSError("private input text must not escape")),
            self.assertRaises(ImportProblem) as failure,
        ):
            list(broken.records())
        self.assertEqual("source-unavailable", str(failure.exception))
        self.assertFalse(broken.complete)

    def test_explicit_legacy_encoding_and_unsupported_unicode_encoding(self):
        payload = b"TY  - JOUR\nTI  - Synth\xe9tique\nER  -\n"
        source = ImportSource("legacy.ris", hashlib.sha256(payload).hexdigest(), "cp1252")
        (record,) = list(ImportSession(ShortReads(payload, 1), source, "ris").records())
        self.assertEqual("parsed", record.status)
        self.assertEqual("Synthétique", record.candidates[0].value)
        run = session(b"\xff\xfeA\x00", "ris")
        with self.assertRaisesRegex(ImportProblem, "unsupported-encoding"):
            list(run.records())
        self.assertFalse(run.complete)

    def test_json_array_delimiters_and_trailing_content_are_not_silently_accepted(self):
        for payload in (b'[{"title":"A"},]', b"[,{}]", b'[{"title":"A",}]', b"[] unexpected"):
            with self.subTest(payload=payload):
                run = session(payload, "csl-json")
                list(run.records())
                self.assertGreater(run.error_count, 0)

    def test_cancellation_during_field_parsing_is_terminal_not_a_record_warning(self):
        run = session(b"10.99999/one\n", "doi-list")
        with (
            patch.object(run, "_candidate", side_effect=ImportProblem("cancelled")),
            self.assertRaisesRegex(ImportProblem, "cancelled"),
        ):
            list(run.records())
        self.assertFalse(run.complete)
        self.assertEqual("cancelled", run.failure_code)

    def test_ris_whitespace_separators_and_bibtex_empty_entries_remain_visible(self):
        payload = b"  \r\nTY  - JOUR\nER  -\n \t\nTY  - JOUR\nER  -\n"
        run = session(payload, "ris")
        self.assertEqual(2, len(list(run.records())))
        self.assertEqual(0, run.error_count)
        run = session(b"@misc{synthetic_empty}", "bibtex")
        (record,) = list(run.records())
        self.assertEqual("parsed", record.status)
        self.assertIn("empty-bibtex-entry", record.warnings)

    def test_macro_resource_failure_does_not_mutate_later_macro_resolution(self):
        payload = b'@string{p="valid"}\n@string{q="' + b"x" * 80 + b'"}\n@article{k,title=q}\n@article{a,title=p}'
        run = session(payload, "bibtex", limits=ImportLimits(max_field_bytes=40))
        records = list(run.records())
        self.assertEqual(["parsed", "malformed", "parsed", "parsed"], [item.status for item in records])
        self.assertIn("unresolved-bibtex-macro", records[2].warnings)
        self.assertEqual((), records[2].candidates)
        self.assertEqual("valid", records[3].candidates[0].value)

    def test_rejected_macro_name_does_not_consume_capacity(self):
        payload = b"@string{" + b"p" * 25 + b'="V"}\n@string{q="Good"}\n@article{a,title=q}'
        run = session(payload, "bibtex", limits=ImportLimits(max_field_bytes=20, max_macros=1))
        rejected, accepted, record = list(run.records())
        self.assertEqual("malformed", rejected.status)
        self.assertIn("field-limit", rejected.warnings)
        self.assertEqual("parsed", accepted.status)
        self.assertEqual("Good", record.candidates[0].value)
        self.assertTrue(run.complete)

    def test_unresolved_macro_redefinition_shadows_stale_value(self):
        payload = (
            b'@string{p="old"}\n@string{p=unknown}\n@string{q=p}\n'
            b'@article{a,title=p,author=q}\n@string{p="new"}\n@article{b,title=p}'
        )
        run = session(payload, "bibtex")
        records = list(run.records())
        self.assertTrue(all(item.status == "parsed" for item in records))
        for record in records[1:4]:
            self.assertIn("unresolved-bibtex-macro", record.warnings)
            self.assertEqual((), record.candidates)
        self.assertEqual("new", records[-1].candidates[0].value)
        self.assertTrue(run.complete)

    def test_macro_directive_is_atomic_and_local_unresolved_binding_wins(self):
        payload = (
            b'@string{p="old"}\n@string{p="new",'
            + b"x" * 25
            + b'="bad"}\n@article{a,title=p}\n@string{p=unknown,q=p}\n@article{b,title=q}'
        )
        run = session(payload, "bibtex", limits=ImportLimits(max_field_bytes=20))
        records = list(run.records())
        self.assertEqual("malformed", records[1].status)
        self.assertEqual("old", records[2].candidates[0].value)
        self.assertEqual((), records[4].candidates)
        self.assertIn("unresolved-bibtex-macro", records[4].warnings)

    def test_unresolved_macro_uses_capacity_without_recounting_previous_piece(self):
        payload = b'@string{p="123456789012345"}\n@string{p=p # unknown # missing}\n@string{q="new"}'
        run = session(payload, "bibtex", limits=ImportLimits(max_field_bytes=40, max_macros=1))
        old, unresolved, over_limit = list(run.records())
        self.assertEqual("parsed", old.status)
        self.assertEqual("parsed", unresolved.status)
        self.assertIn("unresolved-bibtex-macro", unresolved.warnings)
        self.assertEqual("malformed", over_limit.status)
        self.assertIn("macro-count-limit", over_limit.warnings)

    def test_field_warnings_identify_repeated_doi_macro_and_formula_inputs(self):
        samples = (
            ("ris", b"TY  - JOUR\nDO  - 10.99999/valid\nDO  - invalid\nER  -\n", "invalid-doi", 2),
            ("bibtex", b"@article{a,title=unknown,author={Valid}}", "unresolved-bibtex-macro", 2),
            ("csv", b"title,note\nValid,=SUM(A1)\n", "formula-like-cell", 1),
        )
        for format_name, payload, warning, expected_index in samples:
            with self.subTest(format=format_name):
                run = session(payload, format_name)
                records = list(run.records())
                record = next(item for item in records if item.kind == "record")
                self.assertEqual(
                    [expected_index], [index for index, item in enumerate(record.fields) if warning in item.warnings]
                )
                self.assertIn(warning, record.warnings)
                self.assertEqual(payload[record.byte_start : record.byte_end], record.raw_bytes)
                expected = ["duplicate-field", warning] if format_name == "ris" else [warning]
                self.assertEqual(expected, record.to_document()["fields"][expected_index]["warnings"])


if __name__ == "__main__":
    unittest.main()
