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

    def update_governed_hash(self, root: Path, relative: str) -> None:
        manifest_path = root / "REFERENCE_MANIFEST.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["file_hashes"][relative] = self.canonical_hash(root / relative)
        manifest_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
        )

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
            "network-css": (self.add_network_css, "network-dependent CSS reference"),
            "network-api": (self.add_network_api, "browser network API is prohibited"),
            "network-worker": (self.add_network_worker, "browser network API is prohibited"),
            "network-svg": (self.add_network_svg, "network-dependent image href"),
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
        self.update_governed_hash(root, "index.html")

    def add_network_css(self, root: Path) -> None:
        path = root / "assets" / "app.css"
        path.write_text(
            path.read_text(encoding="utf-8") + '\n@import url("https://example.invalid/remote.css");\n',
            encoding="utf-8",
            newline="\n",
        )
        self.update_governed_hash(root, "assets/app.css")

    def add_network_api(self, root: Path) -> None:
        path = root / "assets" / "app.js"
        path.write_text(
            path.read_text(encoding="utf-8") + '\nfetch("https://example.invalid/data.json");\n',
            encoding="utf-8",
            newline="\n",
        )
        self.update_governed_hash(root, "assets/app.js")

    def add_network_worker(self, root: Path) -> None:
        path = root / "assets" / "app.js"
        path.write_text(
            path.read_text(encoding="utf-8") + '\nnew Worker("https://example.invalid/worker.js");\n',
            encoding="utf-8",
            newline="\n",
        )
        self.update_governed_hash(root, "assets/app.js")

    def add_network_svg(self, root: Path) -> None:
        generator = root / "scripts" / "build_mockups.py"
        text = generator.read_text(encoding="utf-8")
        marker = '    print(f"Generated {len(pages)} HTML files in {ROOT}")'
        injected = "\n".join(
            [
                '    index_path = ROOT / "index.html"',
                "    index_path.write_text(",
                '        index_path.read_text(encoding="utf-8").replace(',
                '            "</body>",',
                "            '<svg><image href=\"https://example.invalid/image.svg\"></image></svg></body>',",
                "        ),",
                '        encoding="utf-8",',
                '        newline="\\n",',
                "    )",
                marker,
            ]
        )
        generator.write_text(text.replace(marker, injected), encoding="utf-8", newline="\n")
        subprocess.run([sys.executable, str(generator)], cwd=root, check=True, capture_output=True)
        manifest_path = root / "REFERENCE_MANIFEST.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["file_hashes"] = {
            relative: self.canonical_hash(root / relative) for relative in manifest["governed_files"]
        }
        manifest_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
        )

    def add_hosted_route(self, root: Path) -> None:
        old_route = "project-settings.html"
        new_route = "university-administrator-console.html"
        manifest_path = root / "REFERENCE_MANIFEST.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        for relative in manifest["governed_files"]:
            path = root / relative
            if path.suffix.lower() not in {".css", ".html", ".js", ".json", ".md", ".py", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8")
            if old_route in text:
                path.write_text(text.replace(old_route, new_route), encoding="utf-8", newline="\n")
        (root / old_route).replace(root / new_route)
        manifest["governed_files"] = [new_route if item == old_route else item for item in manifest["governed_files"]]
        manifest["file_hashes"] = {
            relative: self.canonical_hash(root / relative) for relative in manifest["governed_files"]
        }
        manifest_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
        )

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

    def test_no_op_generator_cannot_reuse_preexisting_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.reference_copy(temporary)
            generator = root / "scripts" / "build_mockups.py"
            generator.write_text('print("no output generated")\n', encoding="utf-8", newline="\n")
            self.update_governed_hash(root, "scripts/build_mockups.py")
            result = validate(root)

        self.assertFalse(result["ok"])
        self.assertFalse(result["generator_reproducible"])
        self.assertTrue(any("generator inventory differs" in error for error in result["errors"]), result["errors"])

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
