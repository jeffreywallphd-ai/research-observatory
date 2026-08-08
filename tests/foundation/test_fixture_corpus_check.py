from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
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

        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            nested = corpus / "nested"
            nested.mkdir()
            (nested / "manifest.json").write_text("{}", encoding="utf-8")
            (nested / "manifest.schema.json").write_text("{}", encoding="utf-8")

            errors = corpus_errors(corpus)

        self.assertIn("undocumented fixture file: nested/manifest.json", errors)
        self.assertIn("undocumented fixture file: nested/manifest.schema.json", errors)

    def test_rejection_fixture_must_reproduce_its_declared_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            path = corpus / "malformed" / "records.json"
            path.write_text('{"records": []}\n', encoding="utf-8")
            self.update_item_digest(corpus, "malformed/records.json")

            errors = corpus_errors(corpus)

        self.assertTrue(any("rejection fixture unexpectedly passes structural validation" in error for error in errors))

    def test_media_types_and_pdf_xref_metadata_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            manifest_path = corpus / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            pdf_item = next(item for item in manifest["items"] if item["path"] == "pdf/article.pdf")
            pdf_item["mediaType"] = "text/plain"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = corpus_errors(corpus)

        self.assertTrue(any("mediaType" in error and "does not match path type" in error for error in errors))
        self.assertTrue(any("feature 'pdf' is incompatible" in error for error in errors))

        mutations = (
            (b"xref\n0 6\n", b"xref\n0 5\n"),
            (b"0000000043 00000 n", b"0000000043 00000 f"),
            (b"0000000043 00000 n", b"0000000043 00001 n"),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as temporary:
                corpus = self.copy_corpus(temporary)
                path = corpus / "pdf" / "article.pdf"
                payload = path.read_bytes()
                self.assertIn(original, payload)
                path.write_bytes(payload.replace(original, replacement, 1))
                self.update_item_digest(corpus, "pdf/article.pdf")

                errors = corpus_errors(corpus)

            self.assertTrue(any("invalid-pdf-xref" in error for error in errors))

    def test_declared_text_features_are_substantiated_by_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            path = corpus / "fulltext" / "article.txt"
            path.write_text("x\n", encoding="utf-8")
            self.update_item_digest(corpus, "fulltext/article.txt")

            errors = corpus_errors(corpus)

        self.assertTrue(any("plain-full-text lacks" in error for error in errors))
        self.assertTrue(any("table is declared" in error for error in errors))
        self.assertTrue(any("citations are declared" in error for error in errors))
        self.assertTrue(any("bibliography is declared" in error for error in errors))

    def test_normal_semantic_features_require_an_accepted_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = self.copy_corpus(temporary)
            article_path = corpus / "fulltext" / "article.xml"
            article = article_path.read_text(encoding="utf-8")
            article_path.write_text(
                article.replace("<body>", "<data>").replace("</body>", "</data>"),
                encoding="utf-8",
            )
            self.update_item_digest(corpus, "fulltext/article.xml")
            manifest_path = corpus / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            accepted = next(item for item in manifest["items"] if item["path"] == "fulltext/article.xml")
            rejected = next(item for item in manifest["items"] if item["path"] == "malformed/article.xml")
            accepted["features"].remove("structured-full-text")
            rejected["features"].append("structured-full-text")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = corpus_errors(corpus)

        self.assertTrue(any("feature 'structured-full-text' requires outcome 'accept'" in error for error in errors))

    def test_manifest_and_schema_redirects_are_rejected(self) -> None:
        for control_name in ("manifest.json", "manifest.schema.json"):
            with self.subTest(control_name=control_name), tempfile.TemporaryDirectory() as temporary:
                corpus = self.copy_corpus(temporary)
                control = corpus / control_name
                control.unlink()
                outside = Path(temporary) / "outside"
                outside.mkdir()
                redirected = False
                try:
                    if os.name == "nt":
                        created = subprocess.run(
                            ["cmd", "/c", "mklink", "/J", str(control), str(outside)],
                            capture_output=True,
                            check=False,
                        )
                        if created.returncode != 0:
                            self.skipTest("directory junctions are unavailable")
                    else:
                        target = outside / control_name
                        target.write_text("{}", encoding="utf-8")
                        control.symlink_to(target)
                    redirected = True

                    errors = corpus_errors(corpus)
                finally:
                    if redirected and control.exists():
                        control.unlink() if control.is_symlink() else control.rmdir()

            self.assertTrue(any("fixture control file" in error for error in errors))
            self.assertTrue(any("does not resolve inside the corpus" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
