from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from ui_change_gate import automatic_base, validate  # noqa: E402


class UiChangeGateTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")

    def write_yaml(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8", newline="\n")

    def commit(self, root: Path, message: str) -> str:
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def reference_package(self, root: Path) -> str:
        manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        hashes = {
            relative: hashlib.sha256((root / "design" / "ui-reference" / relative).read_bytes()).hexdigest()
            for relative in manifest["governed_files"]
        }
        manifest["file_hashes"] = hashes
        self.write_yaml(manifest_path, manifest)
        return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def prepare(self, temporary: str) -> tuple[Path, str, str]:
        root = Path(temporary) / "repo"
        root.mkdir()
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.name", "UI Gate Test")
        self.git(root, "config", "user.email", "ui-gate@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        (root / "design").mkdir()
        shutil.copy2(REPO / "design" / "ui-change.schema.json", root / "design" / "ui-change.schema.json")
        shutil.copy2(REPO / "ui-change-policy.json", root / "ui-change-policy.json")
        approval = {
            "reference_id": "REF-1",
            "version": "1",
            "status": "approved",
            "approved_by": "Project-owner direction",
            "approved_at": "2026-08-08",
            "supersedes": "REF-0",
        }
        self.write_yaml(root / "design" / "ui-reference" / "APPROVAL.yaml", approval)
        tokens = root / "design" / "ui-reference" / "assets" / "tokens.css"
        tokens.parent.mkdir(parents=True)
        tokens.write_text(":root { --surface: white; }\n", encoding="utf-8", newline="\n")
        self.write_yaml(
            root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml",
            {
                "reference_id": "REF-1",
                "version": "1",
                "status": "approved",
                "governed_files": ["APPROVAL.yaml", "assets/tokens.css"],
                "file_hashes": {},
            },
        )
        package = self.reference_package(root)
        view = root / "apps" / "desktop" / "src" / "View.tsx"
        view.parent.mkdir(parents=True)
        view.write_text("export const View = () => null;\n", encoding="utf-8", newline="\n")
        self.write_yaml(root / "planning" / "backlog.yaml", {"capabilities": []})
        base = self.commit(root, "baseline")
        return root, base, package

    def contract(
        self,
        kind: str,
        package: str,
        approval_commit: str,
        approved_by: str = "Project-owner direction",
        previous: str = "REF-0",
        reference_id: str = "REF-1",
        version: str = "1",
        implementation_agent: str = "agent:codex",
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schemaVersion": "1.0",
            "documentType": "ui-change-evidence",
            "taskId": "CAP-01.S01.T01",
            "changeKind": kind,
            "contractPath": "artifacts/evidence/ui-change/CAP-01.S01.T01.json",
            "implementationAgent": implementation_agent,
            "changedFiles": ["apps/desktop/src/View.tsx"],
            "reference": {
                "referenceId": reference_id,
                "version": version,
                "packageSha256": package,
                "approvalCommit": approval_commit,
                "approvedBy": approved_by,
                "previousReferenceId": previous,
            },
            "focusedEvidence": [{"command": "test View", "result": "passed", "scope": "approved route behavior"}],
        }
        if kind == "defect-restoration":
            value["restoration"] = {"defect": "route drift", "expectedBehavior": "approved route"}
        else:
            value["implementationScope"] = "approved shell route"
        return value

    def install_contract(
        self,
        root: Path,
        contract: dict[str, object],
        review_gate: str = "agent-review",
        base_sha: str | None = None,
    ) -> None:
        path = root / "artifacts" / "evidence" / "ui-change" / "CAP-01.S01.T01.json"
        self.write_json(path, contract)
        reference = contract["reference"]
        assert isinstance(reference, dict)
        experience = {
            "kind": contract["changeKind"],
            "contract_path": contract["contractPath"],
            "reference_id": reference["referenceId"],
            "reference_version": reference["version"],
            "reference_package_sha256": reference["packageSha256"],
            "reference_approval_commit": reference["approvalCommit"],
            "previous_reference_id": reference["previousReferenceId"],
            "implementation_agent": contract["implementationAgent"],
        }
        backlog = {
            "capabilities": [
                {
                    "slices": [
                        {
                            "tasks": [
                                {
                                    "id": "CAP-01.S01.T01",
                                    "owner": str(contract["implementationAgent"]).split(":", 1)[1],
                                    "status": "IN_PROGRESS",
                                    "review_gate": review_gate,
                                    "base_sha": base_sha,
                                    "experience_change": experience,
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        self.write_yaml(root / "planning" / "backlog.yaml", backlog)

    def test_approved_reference_implementation_and_defect_restoration_pass(self) -> None:
        for kind in ("approved-reference-implementation", "defect-restoration"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                    f"export const View = () => '{kind}';\n", encoding="utf-8", newline="\n"
                )
                contract = self.contract(kind, package, base)
                self.install_contract(root, contract)
                head = self.commit(root, kind)

                result = validate(root, base, head)

            self.assertTrue(result["ok"], result["errors"])

    def test_ui_change_requires_exact_contract_task_and_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'changed';\n", encoding="utf-8", newline="\n"
            )
            head = self.commit(root, "uncontracted UI")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("exactly one changed UI evidence contract" in error for error in result["errors"]))

    def test_ui_implementation_cannot_weaken_gate_controls_in_same_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'changed';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract)
            policy_path = root / "ui-change-policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["implementationRoots"] = list(reversed(policy["implementationRoots"]))
            self.write_json(policy_path, policy)
            head = self.commit(root, "weaken gate with UI")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("cannot change its own" in error for error in result["errors"]))

    def test_intentional_change_requires_new_human_approval_before_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            approval_commit = self.commit(root, "human approved reference")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'new design';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
            head = self.commit(root, "implement approved reference")

            result = validate(root, base, head)
            inferred_base = automatic_base(root, head)

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(base, inferred_base)

    def test_intentional_change_rejects_same_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'intentional';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract("intentional-design-change", package, base)
            self.install_contract(root, contract, review_gate="human-and-agent-review")
            head = self.commit(root, "intentional without new reference")
            same_reference = validate(root, base, head)

        self.assertFalse(same_reference["ok"])
        self.assertTrue(any("newer approved reference" in error for error in same_reference["errors"]))

    def test_intentional_change_rejects_self_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            approval_commit = self.commit(root, "self approval record")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'self approved';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
                implementation_agent="agent:owner",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review")
            head = self.commit(root, "implement self-approved design")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("cannot approve its own" in error for error in result["errors"]))

    def test_intentional_change_rejects_approval_and_implementation_in_same_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'same commit';\n", encoding="utf-8", newline="\n"
            )
            approval_commit = self.commit(root, "approve and implement together")
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review")
            head = self.commit(root, "record UI lineage")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("strictly precede" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
