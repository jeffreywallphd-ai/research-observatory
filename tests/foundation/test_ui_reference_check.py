from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "design" / "ui-reference"
sys.path.insert(0, str(REPO / "tools"))

from ui_reference_check import canonical_payload, validate, write_hashes  # noqa: E402


class UiReferenceCheckTests(unittest.TestCase):
    def reference_copy(self, temporary: str) -> Path:
        target = Path(temporary) / "design" / "ui-reference"
        shutil.copytree(
            REFERENCE,
            target,
            ignore=shutil.ignore_patterns("previews", "__pycache__"),
        )
        return target

    def write_json(self, path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    def canonical_hash(self, path: Path) -> str:
        payload = canonical_payload(path.name, path.read_bytes())
        return hashlib.sha256(payload).hexdigest()

    def test_approved_reference_report_is_complete_and_deterministic(self) -> None:
        first = validate(REFERENCE)
        second = validate(REFERENCE)

        self.assertEqual(first, second)
        self.assertTrue(first["ok"], first["errors"])
        self.assertEqual("RO-UI-ACADEMIC-MINIMAL-1.3", first["reference_id"])
        self.assertEqual(32, first["product_pages"])
        self.assertEqual(34, first["html_documents"])
        self.assertEqual(14, first["workflow_profiles"])
        self.assertEqual(20, first["capability_records"])
        self.assertEqual(54, first["governed_files"])
        self.assertEqual(54, len(first["governed_hashes"]))
        self.assertTrue(first["generator_reproducible"])
        self.assertRegex(first["reference_package_sha256"], r"^[0-9a-f]{64}$")

    def test_missing_modified_and_unapproved_governance_fail(self) -> None:
        mutations = {
            "missing": (
                lambda root: (root / "assets" / "app.js").unlink(),
                "governed inventory mismatch",
            ),
            "modified": (
                lambda root: (root / "STYLE_GUIDE.md").write_text("changed\n", encoding="utf-8"),
                "governed file hash mismatch: STYLE_GUIDE.md",
            ),
            "unapproved": (self.mark_unapproved, "reference is not approved"),
        }
        for label, (mutate, expected) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = self.reference_copy(temporary)
                mutate(root)
                result = validate(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any(expected in error for error in result["errors"]), result["errors"])

    def mark_unapproved(self, root: Path) -> None:
        path = root / "APPROVAL.yaml"
        approval = yaml.safe_load(path.read_text(encoding="utf-8"))
        approval["status"] = "proposed"
        path.write_text(yaml.safe_dump(approval, sort_keys=False), encoding="utf-8", newline="\n")

    def test_workflow_contract_link_and_hosted_route_boundaries_fail(self) -> None:
        mutations = {
            "broken-workflow": (self.break_workflow, "step is not a governed product page"),
            "missing-contract": (self.remove_page_contract, "page contracts must exactly match product pages"),
            "escaping-link": (self.add_escaping_link, "package-escaping local reference"),
            "network-link": (self.add_network_link, "network-dependent"),
            "hosted-route": (self.add_hosted_route, "unexpected hosted administration route"),
        }
        for label, (mutate, expected) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = self.reference_copy(temporary)
                mutate(root)
                result = validate(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any(expected in error for error in result["errors"]), result["errors"])

    def break_workflow(self, root: Path) -> None:
        path = root / "WORKFLOW_CATALOG.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["workflows"]["rapid-orientation"]["steps"][0] = "missing.html"
        self.write_json(path, value)

    def remove_page_contract(self, root: Path) -> None:
        path = root / "CAPABILITY_COVERAGE.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["page_contracts"].pop("index.html")
        self.write_json(path, value)

    def add_escaping_link(self, root: Path) -> None:
        path = root / "index.html"
        text = path.read_text(encoding="utf-8").replace('href="assets/tokens.css"', 'href="../outside.css"', 1)
        path.write_text(text, encoding="utf-8", newline="\n")

    def add_network_link(self, root: Path) -> None:
        path = root / "index.html"
        text = path.read_text(encoding="utf-8").replace(
            'href="assets/tokens.css"', 'href="https://example.invalid/tokens.css"', 1
        )
        path.write_text(text, encoding="utf-8", newline="\n")

    def add_hosted_route(self, root: Path) -> None:
        path = root / "SITE_MANIFEST.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["pages"][0]["file"] = "university-admin.html"
        self.write_json(path, value)

    def test_generator_drift_and_approved_hash_rewrite_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.reference_copy(temporary)
            generator = root / "scripts" / "build_mockups.py"
            generator.write_text(
                generator.read_text(encoding="utf-8").replace("Project Home", "Changed Project Home", 1),
                encoding="utf-8",
                newline="\n",
            )
            manifest_path = root / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["file_hashes"]["scripts/build_mockups.py"] = self.canonical_hash(generator)
            manifest_path.write_text(
                yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
            )

            result = validate(root)
            with self.assertRaisesRegex(ValueError, "approved UI reference"):
                write_hashes(root)

        self.assertFalse(result["ok"])
        self.assertTrue(any("generator is not reproducible" in error for error in result["errors"]), result["errors"])

    def test_reference_change_during_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.reference_copy(temporary)
            real_run = subprocess.run

            def mutate_then_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
                (root / "STYLE_GUIDE.md").write_text("changed during validation\n", encoding="utf-8")
                return real_run(*args, **kwargs)

            with mock.patch("ui_reference_check.subprocess.run", side_effect=mutate_then_run):
                result = validate(root)

        self.assertFalse(result["ok"])
        self.assertTrue(
            any("UI-reference file changed during validation: STYLE_GUIDE.md" in error for error in result["errors"]),
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
