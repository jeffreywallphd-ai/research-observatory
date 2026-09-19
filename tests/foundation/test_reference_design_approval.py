"""Synthetic Git-bound pre-Wave reference approval; no project/history fixture."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ui_conformance import approval_record_errors, reference_package_at


class ReferenceDesignApprovalTests(unittest.TestCase):
    reference_id = "RO-UI-ACADEMIC-MINIMAL-1.7"

    def fixture(self, directory: str, record_change=None, *, bad_publication: bool = False) -> tuple[Path, dict, str]:
        root = Path(directory)

        def git(*args: str) -> str:
            return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode().strip()

        git("init", "--quiet")
        git("config", "user.name", "Reference Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "core.autocrlf", "false")
        git("config", "commit.gpgsign", "false")
        self.git = git
        self.write(root, ".gitattributes", "* text eol=lf\n")
        self.write(root, "design/ui-reference/APPROVAL.yaml", "reference_id: RO-UI-ACADEMIC-MINIMAL-1.6\n")
        self.commit("Prior reference")
        proposal = {
            "reference_id": self.reference_id,
            "version": "1.7",
            "status": "proposed",
            "approval_kind": "human",
            "approved_by": None,
            "approved_at": None,
            "approval_basis": None,
            "supersedes": "RO-UI-ACADEMIC-MINIMAL-1.6",
            "scope": {"normative": ["Synthetic fixture"], "illustrative": ["No product content"]},
            "implementation_rule": "Design approval is not execution authority.",
        }
        source = "planning/reference-proposal"
        source_files = {"APPROVAL.yaml": yaml.safe_dump(proposal, sort_keys=False), "page.html": "<p>Synthetic</p>\n"}
        hashes = {name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in source_files.items()}
        manifest = {
            "reference_id": self.reference_id,
            "version": "1.7",
            "status": "proposed",
            "approval_file": "APPROVAL.yaml",
            "canonical_token_file": "page.html",
            "style_guides": [],
            "workflow_catalog": [],
            "page_contracts": "page.html",
            "page_inventory": "page.html",
            "site_manifest": "page.html",
            "generator": "page.html",
            "validator": "page.html",
            "governed_files": sorted(source_files),
            "file_hashes": hashes,
        }
        for name, raw in source_files.items():
            self.write(root, f"{source}/{name}", raw)
        self.write(root, f"{source}/REFERENCE_MANIFEST.yaml", yaml.safe_dump(manifest, sort_keys=False))
        proposal_commit = self.commit("Exact proposal")
        record = {
            "schemaVersion": "1.0",
            "kind": "ui-reference-design-approval",
            "referenceId": self.reference_id,
            "approvedBy": "human:fixture",
            "approvedAt": "2026-09-19T16:19:10Z",
            "scope": "reference-publication-and-plan-binding-only",
            "proposal": {
                "commit": proposal_commit,
                "path": source,
                "packageSha256": hashlib.sha256(
                    json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            },
            "basis": "Synthetic approval for this test only.",
        }
        record_path = f"planning/reference-approvals/{self.reference_id}.json"
        if record_change:
            record_change(record)
        record_raw = json.dumps(record, indent=2) + "\n"
        self.write(root, record_path, record_raw)
        introduction = self.commit("Record human design decision")
        approval = {
            **proposal,
            "status": "approved",
            "approved_by": record["approvedBy"],
            "approved_at": record["approvedAt"],
            "approval_basis": record["basis"],
            "authority": {
                "design_approval_record": record_path,
                "design_approval_record_sha256": hashlib.sha256(record_raw.encode()).hexdigest(),
                "design_approval_record_introduction_commit": introduction,
            },
        }
        source_files["APPROVAL.yaml"] = yaml.safe_dump(approval, sort_keys=False)
        if bad_publication:
            source_files["page.html"] = "<p>Unreviewed original publication</p>\n"
        for name, raw in source_files.items():
            self.write(root, f"design/ui-reference/{name}", raw)
        manifest["status"] = "approved"
        manifest["file_hashes"] = {name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in source_files.items()}
        self.write(root, "design/ui-reference/REFERENCE_MANIFEST.yaml", yaml.safe_dump(manifest, sort_keys=False))
        return root, approval, self.commit("Publish exact reference")

    @staticmethod
    def write(root: Path, name: str, raw: str) -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8", newline="\n")

    def commit(self, message: str) -> str:
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def test_exact_pre_wave_design_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, approval, commit = self.fixture(directory)
            self.assertEqual([], approval_record_errors(approval, "fixture", self.reference_id))
            _, package, errors = reference_package_at(root, commit, self.reference_id)
            self.assertEqual([], errors, errors)
            self.assertRegex(package or "", r"^[0-9a-f]{64}$")

    def test_rejects_forged_authority_and_nonmetadata_changes(self) -> None:
        for mutation in (
            "record-hash",
            "record-introduction",
            "record-body",
            "proposal-hash",
            "source-path",
            "actor",
            "supersedes",
            "scope",
            "page",
            "inventory",
            "extra-file",
            "reuse",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root, approval, _ = self.fixture(directory)
                if mutation == "record-hash":
                    approval["authority"]["design_approval_record_sha256"] = "0" * 64
                elif mutation == "record-introduction":
                    approval["authority"]["design_approval_record_introduction_commit"] = "0" * 40
                elif mutation in {"record-body", "proposal-hash", "source-path"}:
                    path = approval["authority"]["design_approval_record"]
                    record = json.loads((root / path).read_text())
                    if mutation == "record-body":
                        record["scope"] = "execute-wave"
                    elif mutation == "proposal-hash":
                        record["proposal"]["packageSha256"] = "0" * 64
                    else:
                        record["proposal"]["path"] = "planning/../../artifacts/evidence"
                    self.write(root, path, json.dumps(record))
                elif mutation == "actor":
                    approval["approved_by"] = "human:someone-else"
                elif mutation == "supersedes":
                    approval["supersedes"] = "RO-UI-OTHER-1.0"
                elif mutation == "scope":
                    approval["scope"]["normative"].append("Unreviewed behavior")
                elif mutation == "page":
                    self.write(root, "design/ui-reference/page.html", "<p>Changed</p>\n")
                elif mutation == "inventory":
                    path = root / "design/ui-reference/REFERENCE_MANIFEST.yaml"
                    manifest = yaml.safe_load(path.read_text())
                    manifest["governed_files"].append("unapproved.html")
                    self.write(root, "design/ui-reference/REFERENCE_MANIFEST.yaml", yaml.safe_dump(manifest))
                elif mutation == "extra-file":
                    self.write(root, "design/ui-reference/unlisted.html", "<p>Unreviewed</p>\n")
                else:
                    approval["approval_basis"] += " Reused."
                self.write(root, "design/ui-reference/APPROVAL.yaml", yaml.safe_dump(approval, sort_keys=False))
                commit = self.commit("Synthetic invalid publication")
                self.assertTrue(reference_package_at(root, commit, self.reference_id)[2])

    def test_legacy_schema_stays_strict_and_live_authority_drift_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, approval, commit = self.fixture(directory)
            legacy = copy.deepcopy(approval)
            legacy.pop("authority")
            legacy.pop("approval_kind")
            self.assertTrue(approval_record_errors(legacy, "fixture", self.reference_id))
            self.write(root, approval["authority"]["design_approval_record"], "{}\n")
            self.assertTrue(reference_package_at(root, commit, self.reference_id)[2])

    def test_bound_record_cannot_authorize_wrong_package_scope_or_ancestry(self) -> None:
        mutations = (
            lambda record: record["proposal"].update(packageSha256="0" * 64),
            lambda record: record["proposal"].update(path="planning/../../artifacts/evidence"),
            lambda record: record.update(scope="execute-wave"),
            lambda record: record.update(approvedBy="agent:fixture"),
            lambda record: record["proposal"].update(
                commit=self.git("commit-tree", self.git("rev-parse", "HEAD^{tree}"), "-m", "Unrelated proposal")
            ),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)), tempfile.TemporaryDirectory() as directory:
                root, _, commit = self.fixture(directory, mutation)
                self.assertTrue(reference_package_at(root, commit, self.reference_id)[2])

    def test_multiparent_publication_is_rejected(self) -> None:
        from reference_design_approval import design_authority_bound_approval_errors

        with tempfile.TemporaryDirectory() as directory:
            root, approval, commit = self.fixture(directory)
            merged = self.git(
                "commit-tree",
                self.git("rev-parse", "HEAD^{tree}"),
                "-p",
                commit,
                "-p",
                commit + "^",
                "-m",
                "Invalid merge publication",
            )
            self.assertTrue(
                design_authority_bound_approval_errors(root, approval, merged, "design/ui-reference/APPROVAL.yaml")
            )

    def test_later_repair_cannot_launder_invalid_original_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _, original = self.fixture(directory, bad_publication=True)
            self.assertTrue(reference_package_at(root, original, self.reference_id)[2])
            self.write(root, "design/ui-reference/page.html", "<p>Synthetic</p>\n")
            path = "design/ui-reference/REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load((root / path).read_text())
            manifest["file_hashes"]["page.html"] = hashlib.sha256(b"<p>Synthetic</p>\n").hexdigest()
            self.write(root, path, yaml.safe_dump(manifest, sort_keys=False))
            repaired = self.commit("Repair content without a new approval")
            self.assertTrue(reference_package_at(root, repaired, self.reference_id)[2])

    def test_sibling_consumption_is_denied_but_ordinary_merge_is_allowed(self) -> None:
        for sibling_publication in (False, True):
            with self.subTest(sibling_publication=sibling_publication), tempfile.TemporaryDirectory() as directory:
                root, _, publication = self.fixture(directory)
                record_commit = self.git("rev-parse", publication + "^")
                side_tree = self.git("rev-parse", (publication if sibling_publication else record_commit) + "^{tree}")
                sibling = self.git("commit-tree", side_tree, "-p", record_commit, "-m", "Synthetic sibling")
                merged = self.git(
                    "commit-tree",
                    self.git("rev-parse", publication + "^{tree}"),
                    "-p",
                    publication,
                    "-p",
                    sibling,
                    "-m",
                    "Merge branches",
                )
                errors = reference_package_at(root, merged, self.reference_id)[2]
                self.assertEqual(sibling_publication, bool(errors), errors)


if __name__ == "__main__":
    unittest.main()
