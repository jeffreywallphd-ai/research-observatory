from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "fixtures" / "scholarly-corpus"
sys.path.insert(0, str(REPO / "tools"))

from fixture_corpus_check import REQUIRED_FEATURES, corpus_errors  # noqa: E402


class FixtureCorpusCheckTests(unittest.TestCase):
    def copy_corpus(self, temporary: str) -> Path:
        destination = Path(temporary) / "corpus"
        shutil.copytree(CORPUS, destination)
        return destination

    def update_item_digest(self, corpus: Path, fixture_path: str) -> None:
        manifest_path = corpus / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = (corpus / fixture_path).read_bytes()
        item = next(item for item in manifest["items"] if item["path"] == fixture_path)
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        item["bytes"] = len(payload)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def test_canonical_corpus_is_licensed_deterministic_and_complete(self) -> None:
        self.assertEqual([], corpus_errors(CORPUS))
        manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
        features = {feature for item in manifest["items"] for feature in item["features"]}

        self.assertTrue(manifest["offline"])
        self.assertTrue(manifest["deterministic"])
        self.assertEqual("CC0-1.0", manifest["license"]["spdx"])
        self.assertFalse(manifest["provenance"]["containsThirdPartyScholarlyContent"])
        self.assertTrue(features >= REQUIRED_FEATURES)
        self.assertTrue(all(item["license"] == "CC0-1.0" for item in manifest["items"]))
        self.assertTrue(all(not item["provenance"]["containsThirdPartyContent"] for item in manifest["items"]))

    def test_content_tampering_is_detected_by_hash_and_byte_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            path = corpus / "metadata" / "records.ris"
            path.write_bytes(path.read_bytes() + b"tampered")

            errors = corpus_errors(corpus)

        self.assertTrue(any("SHA-256 mismatch" in error for error in errors))
        self.assertTrue(any("byte count mismatch" in error for error in errors))

    def test_schema_and_exact_inventory_reject_undocumented_or_unlicensed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            (corpus / "undocumented.txt").write_text("not in manifest", encoding="utf-8")
            manifest_path = corpus / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["items"][0]["license"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = corpus_errors(corpus)

        self.assertTrue(any("'license' is a required property" in error for error in errors))

        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            (corpus / "undocumented.txt").write_text("not in manifest", encoding="utf-8")

            errors = corpus_errors(corpus)

        self.assertIn("undocumented fixture file: undocumented.txt", errors)

    def test_rejection_fixture_must_reproduce_its_declared_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            path = corpus / "malformed" / "records.json"
            path.write_text('{"records": []}\n', encoding="utf-8")
            self.update_item_digest(corpus, "malformed/records.json")

            errors = corpus_errors(corpus)

        self.assertTrue(any("rejection fixture unexpectedly passes structural validation" in error for error in errors))

    def test_accepted_pdf_must_have_consistent_xref_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            path = corpus / "pdf" / "article.pdf"
            payload = path.read_bytes()
            path.write_bytes(payload.replace(b"0000000043 00000 n", b"0000000044 00000 n", 1))
            self.update_item_digest(corpus, "pdf/article.pdf")

            errors = corpus_errors(corpus)

        self.assertTrue(any("invalid-pdf-xref" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
