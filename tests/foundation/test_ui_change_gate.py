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

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from ui_change_gate import (  # noqa: E402
    APPLICATION_INVENTORY_HARDENING_ENVELOPE,
    additive_preimplementation_quality_scope_errors,
    automatic_base,
    independent_review_hardening_errors,
    reviewed_historical_hardening_errors,
    validate,
)


class UiChangeGateTests(unittest.TestCase):
    def test_cumulative_additive_pre_ui_inventory_then_ui_implementation_passes(self) -> None:
        result = validate(
            REPO,
            "bfb8797398707bece9e0662c0d995fabaced9979",
            "59079efccc122a7d56a9f18efc20030851bf32a9",
        )

        self.assertTrue(result["ok"], result["errors"])

    def test_pre_ui_quality_inventory_is_only_additive_same_commit_non_ui_python(self) -> None:
        policy = {
            "implementationRoots": ["apps/desktop/src"],
            "implementationExtensions": [".css", ".tsx"],
            "ignoredImplementationSuffixes": [".test.tsx"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Gate Test")
            self.git(root, "config", "user.email", "ui-gate@example.invalid")
            self.git(root, "config", "core.autocrlf", "false")
            self.write_json(
                root / "quality-scope.json",
                {
                    "schemaVersion": "1.0",
                    "documentType": "python-quality-scope",
                    "governedRoots": ["services", "tests", "tools"],
                    "pythonFiles": ["services/core/existing.py"],
                },
            )
            existing = root / "services/core/existing.py"
            existing.parent.mkdir(parents=True)
            existing.write_text("EXISTING = True\n", encoding="utf-8")
            self.commit(root, "baseline quality scope")

            source = root / "services/core/projects.py"
            test = root / "tests/service/test_projects.py"
            source.write_text("PROJECTS = True\n", encoding="utf-8")
            test.parent.mkdir(parents=True)
            test.write_text("def test_projects(): pass\n", encoding="utf-8")
            scope = json.loads((root / "quality-scope.json").read_text(encoding="utf-8"))
            scope["pythonFiles"].extend(["services/core/projects.py", "tests/service/test_projects.py"])
            self.write_json(root / "quality-scope.json", scope)
            additive = self.commit(root, "add service quality inventory before UI")
            self.assertEqual([], additive_preimplementation_quality_scope_errors(root, additive, policy))

            scope["pythonFiles"].remove("services/core/existing.py")
            self.write_json(root / "quality-scope.json", scope)
            removal = self.commit(root, "remove existing inventory")
            self.assertTrue(additive_preimplementation_quality_scope_errors(root, removal, policy))

            gate = root / "tools/ui_change_gate.py"
            gate.parent.mkdir(parents=True)
            gate.write_text("GATE = True\n", encoding="utf-8")
            scope["pythonFiles"].append("tools/ui_change_gate.py")
            self.write_json(root / "quality-scope.json", scope)
            gate_addition = self.commit(root, "attempt gate inventory addition")
            self.assertTrue(additive_preimplementation_quality_scope_errors(root, gate_addition, policy))

    def test_historical_quality_scope_hardening_requires_exact_immutable_approval(self) -> None:
        hardening = "1cd9deebe94fa2b667ad6b0030bd07ec45d1c6bb"
        approval = "43bcdec4eba110f994a540f0a1e625a6d44aff4b"
        paths = {"quality-scope.json"}
        self.assertEqual(
            [],
            reviewed_historical_hardening_errors(REPO, hardening, approval, "CAP-01.S04.T03", paths),
        )
        for label, commit, head, task_id, changed in (
            ("commit", "0" * 40, approval, "CAP-01.S04.T03", paths),
            ("head", hardening, hardening, "CAP-01.S04.T03", paths),
            ("task", hardening, approval, "CAP-01.S04.T02", paths),
            ("scope", hardening, approval, "CAP-01.S04.T03", paths | {"tools/ui_change_gate.py"}),
        ):
            with self.subTest(label=label):
                self.assertTrue(reviewed_historical_hardening_errors(REPO, commit, head, task_id, changed))

    def test_application_inventory_hardening_uses_the_exact_reviewed_envelope(self) -> None:
        self.assertEqual(
            {
                "tests/desktop/test_ui_conformance.py",
                "tests/foundation/test_ui_change_gate.py",
                "tools/ui_change_gate.py",
                "tools/ui_conformance.py",
            },
            APPLICATION_INVENTORY_HARDENING_ENVELOPE,
        )

    def test_post_implementation_hardening_requires_independent_changes_requested_record(self) -> None:
        paths = {
            "tests/desktop/test_desktop_app_check.py",
            "tools/ui_change_gate.py",
            "tools/ui_conformance.py",
            "tests/desktop/test_ui_conformance.py",
            "tests/foundation/test_ui_change_gate.py",
            "tools/desktop_app_check.py",
        }
        review = {
            "reviewer": "agent:descartes",
            "result": "changes-requested",
            "reviewed_at": "2026-08-09T08:02:53+00:00",
        }
        backlog: dict[str, Any] = {
            "capabilities": [
                {
                    "slices": [
                        {
                            "tasks": [
                                {
                                    "id": "CAP-01.S01.T01",
                                    "status": "IN_PROGRESS",
                                    "owner": "codex",
                                    "updated_at": "2026-08-09T08:02:53+00:00",
                                    "review": review,
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        previous_backlog = json.loads(json.dumps(backlog))
        previous_task = previous_backlog["capabilities"][0]["slices"][0]["tasks"][0]
        previous_task["status"] = "REVIEW"
        previous_task["review"]["reviewed_at"] = None

        self.assertEqual([], independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))
        review["reviewer"] = "agent:codex"
        self.assertTrue(independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))
        review["reviewer"] = "agent:co-dex"
        self.assertTrue(independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))
        review["reviewer"] = "agent:descartes"
        self.assertTrue(
            independent_review_hardening_errors(
                backlog, previous_backlog, "CAP-01.S01.T01", paths | {"verification-profiles.json"}
            )
        )
        self.assertTrue(
            independent_review_hardening_errors(
                backlog, previous_backlog, "CAP-01.S01.T01", paths | {"tools/taskctl.py"}
            )
        )
        self.assertTrue(
            independent_review_hardening_errors(
                backlog, previous_backlog, "CAP-01.S01.T01", paths | {"apps/desktop/src/App.tsx"}
            )
        )
        previous_task["review"]["reviewed_at"] = review["reviewed_at"]
        self.assertTrue(independent_review_hardening_errors(backlog, previous_backlog, "CAP-01.S01.T01", paths))

    def test_later_ui_task_accepts_only_exact_independently_reviewed_hardening_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            view = root / "apps" / "desktop" / "src" / "View.tsx"
            view.write_text("export const View = () => 'implemented';\n", encoding="utf-8", newline="\n")
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            backlog_path = root / "planning" / "backlog.yaml"
            backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            task = backlog["capabilities"][0]["slices"][0]["tasks"][0]
            task.update(
                {
                    "status": "REVIEW",
                    "updated_at": "2026-08-09T08:00:00+00:00",
                    "review": {"reviewer": None, "result": None, "reviewed_at": None},
                }
            )
            self.write_yaml(backlog_path, backlog)
            self.commit(root, "implement UI")

            task.update(
                {
                    "status": "IN_PROGRESS",
                    "updated_at": "2026-08-09T08:02:53+00:00",
                    "review": {
                        "reviewer": "agent:descartes",
                        "result": "changes-requested",
                        "reviewed_at": "2026-08-09T08:02:53+00:00",
                    },
                }
            )
            self.write_yaml(backlog_path, backlog)
            (root / "docs" / "planning-implementation-plan.md").parent.mkdir(parents=True)
            (root / "docs" / "planning-implementation-plan.md").write_text("reviewed\n", encoding="utf-8")
            (root / "planning" / "status-summary.md").write_text("reviewed\n", encoding="utf-8")
            self.commit(root, "record independent review")

            for relative in (
                "tests/desktop/test_desktop_app_check.py",
                "tests/desktop/test_ui_conformance.py",
                "tests/foundation/test_ui_change_gate.py",
                "tools/desktop_app_check.py",
                "tools/ui_change_gate.py",
                "tools/ui_conformance.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("hardened\n", encoding="utf-8", newline="\n")
            head = self.commit(root, "harden reviewed UI boundary")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

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
        task_id: str = "CAP-01.S01.T01",
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schemaVersion": "1.0",
            "documentType": "ui-change-evidence",
            "taskId": task_id,
            "changeKind": kind,
            "contractPath": f"artifacts/evidence/ui-change/{task_id}.json",
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
        if base_sha is None:
            base_sha = self.git(root, "rev-parse", "HEAD")
        task_id = str(contract["taskId"])
        path = root / "artifacts" / "evidence" / "ui-change" / f"{task_id}.json"
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
        task = {
            "id": task_id,
            "owner": str(contract["implementationAgent"]).split(":", 1)[1],
            "status": "IN_PROGRESS",
            "review_gate": review_gate,
            "base_sha": base_sha,
            "experience_change": experience,
        }
        backlog = (
            {"capabilities": [], "wave_amendments": [{"id": "W1.A05", "tasks": [task]}]}
            if task_id.startswith("W")
            else {"capabilities": [{"slices": [{"tasks": [task]}]}], "wave_amendments": []}
        )
        self.write_yaml(root / "planning" / "backlog.yaml", backlog)

    def install_reviewed_maintenance(
        self,
        root: Path,
        predecessor: str,
        *,
        reviewer: str = "agent:independent-reviewer",
        implementation_agent: str = "codex",
        mixed_product_path: str | None = None,
    ) -> str:
        maintenance_id = "GOV-MAINT-0001"
        record_path = f"planning/governance-migrations/{maintenance_id}.json"
        review_path = f"planning/governance-migrations/{maintenance_id}.review-R01.json"
        schema_path = root / "design" / "ui-change.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["$comment"] = "reviewed generic pre-implementation maintenance"
        self.write_json(schema_path, schema)
        changed_paths = ["design/ui-change.schema.json", record_path]
        if mixed_product_path is not None:
            view = root / mixed_product_path
            view.parent.mkdir(parents=True, exist_ok=True)
            view.write_text(
                "export const View = () => { throw new Error('laundered'); };\n", encoding="utf-8", newline="\n"
            )
            changed_paths.append(mixed_product_path)
        changed_paths = sorted(changed_paths)
        record: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance",
            "maintenanceId": maintenance_id,
            "title": "Fixture pre-implementation gate maintenance",
            "status": "candidate",
            "riskTier": 2,
            "humanApprovalRequired": False,
            "implementationAgent": implementation_agent,
            "predecessor": {"commit": predecessor},
            "trigger": {"diagnosis": "fixture control grammar gap"},
            "authority": "Preserve the approved reference and task authority.",
            "intendedDelta": {"changedPaths": changed_paths},
            "verification": {"results": [{"check": "fixture", "result": "passed"}]},
            "rollback": "Return to the frozen predecessor.",
            "reviewAttempts": [],
            "review": None,
        }
        self.write_json(root / record_path, record)
        candidate = self.commit(root, "candidate gate maintenance")
        reviewed_at = "2026-08-30T20:00:00+00:00"
        review_record = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance-review",
            "maintenanceId": maintenance_id,
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": reviewer,
            "reviewedAt": reviewed_at,
            "disposition": "APPROVED",
            "authorityPreserved": True,
            "candidateChangedPaths": changed_paths,
            "findings": [],
        }
        self.write_json(root / review_path, review_record)
        review_sha = hashlib.sha256((root / review_path).read_bytes()).hexdigest()
        review = {
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": reviewer,
            "reviewedAt": reviewed_at,
            "disposition": "APPROVED",
            "findings": [],
            "path": review_path,
            "sha256": review_sha,
        }
        record.update(status="adopted", reviewAttempts=[review], review=review)
        self.write_json(root / record_path, record)
        self.commit(root, "record independent maintenance review")
        return candidate

    def install_remediated_maintenance(self, root: Path, predecessor: str) -> None:
        maintenance_id = "GOV-MAINT-0001"
        record_path = f"planning/governance-migrations/{maintenance_id}.json"
        schema_path = root / "design" / "ui-change.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["$comment"] = "candidate generic pre-implementation maintenance"
        self.write_json(schema_path, schema)
        changed_paths = sorted(["design/ui-change.schema.json", record_path])
        record: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance",
            "maintenanceId": maintenance_id,
            "title": "Fixture remediated gate maintenance",
            "status": "candidate",
            "riskTier": 2,
            "humanApprovalRequired": False,
            "implementationAgent": "agent:codex",
            "predecessor": {"commit": predecessor},
            "trigger": {"diagnosis": "fixture control grammar gap"},
            "authority": "Preserve the approved reference and task authority.",
            "intendedDelta": {"changedPaths": changed_paths},
            "verification": {"results": [{"check": "fixture", "result": "passed"}]},
            "rollback": "Return to the frozen predecessor.",
            "reviewAttempts": [],
            "review": None,
        }
        self.write_json(root / record_path, record)
        candidate = self.commit(root, "candidate gate maintenance")

        first_review_path = f"planning/governance-migrations/{maintenance_id}.review-R01.json"
        first_finding = {
            "id": f"{maintenance_id}-R01-F01",
            "severity": "HIGH",
            "blocking": True,
            "title": "Fixture defect",
            "reproduction": "The candidate permits a forbidden identity.",
            "requiredResolution": "Normalize both identities symmetrically.",
        }
        first_review = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance-review",
            "maintenanceId": maintenance_id,
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": "agent:independent-reviewer",
            "reviewedAt": "2026-08-30T20:00:00+00:00",
            "disposition": "CHANGES_REQUESTED",
            "authorityPreserved": False,
            "candidateChangedPaths": changed_paths,
            "findings": [first_finding],
        }
        self.write_json(root / first_review_path, first_review)
        first_attempt = {
            "reviewId": f"{maintenance_id}.R01",
            "reviewedCommit": candidate,
            "reviewer": "agent:independent-reviewer",
            "reviewedAt": "2026-08-30T20:00:00+00:00",
            "disposition": "CHANGES_REQUESTED",
            "findings": [f"{maintenance_id}-R01-F01"],
            "path": first_review_path,
            "sha256": hashlib.sha256((root / first_review_path).read_bytes()).hexdigest(),
        }
        record.update(status="changes-requested", reviewAttempts=[first_attempt])
        self.write_json(root / record_path, record)
        self.commit(root, "record adverse maintenance review")

        schema["$comment"] = "remediated generic pre-implementation maintenance"
        self.write_json(schema_path, schema)
        record["remediation"] = {
            "resolvedFindingIds": [f"{maintenance_id}-R01-F01"],
            "rootCause": "The candidate normalized only one identity form.",
            "resolution": "Both identity forms now use one canonicalizer.",
            "recurrenceControl": "The real-Git fixture replays the adverse identity.",
        }
        self.write_json(root / record_path, record)
        remediation = self.commit(root, "remediate gate maintenance")

        second_review_path = f"planning/governance-migrations/{maintenance_id}.review-R02.json"
        remediation_paths = sorted(["design/ui-change.schema.json", record_path])
        second_review = {
            "schemaVersion": "1.0",
            "documentType": "governance-control-maintenance-review",
            "maintenanceId": maintenance_id,
            "reviewId": f"{maintenance_id}.R02",
            "reviewedCommit": remediation,
            "reviewer": "agent:second-independent-reviewer",
            "reviewedAt": "2026-08-30T20:05:00+00:00",
            "disposition": "APPROVED",
            "authorityPreserved": True,
            "candidateChangedPaths": remediation_paths,
            "findings": [],
        }
        self.write_json(root / second_review_path, second_review)
        second_attempt = {
            "reviewId": f"{maintenance_id}.R02",
            "reviewedCommit": remediation,
            "reviewer": "agent:second-independent-reviewer",
            "reviewedAt": "2026-08-30T20:05:00+00:00",
            "disposition": "APPROVED",
            "findings": [],
            "path": second_review_path,
            "sha256": hashlib.sha256((root / second_review_path).read_bytes()).hexdigest(),
        }
        record.update(status="adopted", reviewAttempts=[first_attempt, second_attempt], review=second_attempt)
        self.write_json(root / record_path, record)
        self.commit(root, "adopt remediated maintenance")

    def test_approved_reference_implementation_and_defect_restoration_pass(self) -> None:
        for kind in ("approved-reference-implementation", "defect-restoration"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                    f"export const View = () => '{kind}';\n", encoding="utf-8", newline="\n"
                )
                contract = self.contract(kind, package, base)
                review_gate = "human-and-agent-review" if kind == "defect-restoration" else "agent-review"
                self.install_contract(root, contract, review_gate=review_gate, base_sha=base)
                head = self.commit(root, kind)

                result = validate(root, base, head)

            self.assertTrue(result["ok"], result["errors"])

    def test_amendment_task_identity_uses_the_same_ui_lineage_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved amendment UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract(
                "approved-reference-implementation",
                package,
                base,
                task_id="W1.A05.T04",
            )
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "implement approved amendment UI")

            result = validate(root, base, head)
            inferred_base = automatic_base(root, head)

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(base, inferred_base)

    def test_amendment_task_identity_rejects_out_of_range_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'unapproved task namespace';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract(
                "approved-reference-implementation",
                package,
                base,
                task_id="W12.A05.T04",
            )
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt out-of-range amendment UI")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("taskId" in error or "contractPath" in error for error in result["errors"]))

    def test_independently_reviewed_preimplementation_maintenance_can_precede_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_reviewed_maintenance(root, base)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after reviewed maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "implement UI after reviewed maintenance")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

    def test_independently_reviewed_maintenance_can_repair_the_gate_after_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI before reviewed maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

    def test_postimplementation_maintenance_still_rejects_self_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI before self-reviewed maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented, reviewer="agent:codex")
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("independent" in error for error in result["errors"]))

    def test_postimplementation_maintenance_rejects_mixed_product_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented, mixed_product_path="apps/desktop/src/View.tsx")
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and "View.tsx" in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_build_script_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "apps/desktop/scripts/assemble-application.mjs"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_non_ui_runtime_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "services/runtime/src/session.ts"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_root_launcher_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "dev.cmd"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_product_build_tool_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            path = "tools/core_sidecar_build.py"
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_postimplementation_maintenance_rejects_unrelated_maintenance_record_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            path = "planning/governance-migrations/GOV-MAINT-9999.json"
            self.write_json(
                root / path,
                {
                    "schemaVersion": "1.0",
                    "documentType": "governance-control-maintenance",
                    "maintenanceId": "GOV-MAINT-9999",
                    "status": "adopted",
                },
            )
            self.commit(root, "record unrelated adopted maintenance")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'approved UI';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            implemented = self.commit(root, "implement approved UI")
            self.install_reviewed_maintenance(root, implemented, mixed_product_path=path)
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("control-only" in error and path in error for error in result["errors"]), result)

    def test_remediated_preimplementation_maintenance_preserves_adverse_review_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_remediated_maintenance(root, base)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after remediated maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "implement UI after remediated maintenance")

            result = validate(root, base, head)

        self.assertTrue(result["ok"], result["errors"])

    def test_remediated_preimplementation_maintenance_rejects_post_approval_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_remediated_maintenance(root, base)
            record_path = root / "planning" / "governance-migrations" / "GOV-MAINT-0001.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["remediation"]["resolution"] = "Substituted after approval."
            self.write_json(record_path, record)
            self.commit(root, "substitute approved remediation")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after substituted maintenance';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt UI after substituted maintenance")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("changed after its final review" in error for error in result["errors"]))

    def test_preimplementation_maintenance_rejects_self_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_reviewed_maintenance(root, base, reviewer="agent:codex")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after self review';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt UI after self-reviewed maintenance")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("independent" in error for error in result["errors"]))

    def test_preimplementation_maintenance_rejects_namespaced_implementer_self_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            self.install_reviewed_maintenance(
                root,
                base,
                reviewer="agent:codex",
                implementation_agent="agent:codex",
            )
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'UI after namespaced self review';\n",
                encoding="utf-8",
                newline="\n",
            )
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            head = self.commit(root, "attempt UI after namespaced self-reviewed maintenance")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("independent" in error for error in result["errors"]))

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
        for control_path in ("ui-change-policy.json", "architecture-protected-paths.json", "tools/ci_check.py"):
            with self.subTest(control_path=control_path), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                target = root / control_path
                target.parent.mkdir(parents=True, exist_ok=True)
                if control_path != "ui-change-policy.json":
                    target.write_text("governed control\n", encoding="utf-8", newline="\n")
                    base = self.commit(root, f"install {control_path}")
                (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                    "export const View = () => 'changed';\n", encoding="utf-8", newline="\n"
                )
                contract = self.contract("approved-reference-implementation", package, base)
                self.install_contract(root, contract)
                if control_path == "ui-change-policy.json":
                    policy = json.loads(target.read_text(encoding="utf-8"))
                    policy["implementationRoots"] = list(reversed(policy["implementationRoots"]))
                    self.write_json(target, policy)
                else:
                    target.write_text("weakened control\n", encoding="utf-8", newline="\n")
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
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
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
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
            head = self.commit(root, "record UI lineage")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("strictly precede" in error for error in result["errors"]))

    def test_governed_ui_path_must_be_a_regular_git_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            view = root / "apps" / "desktop" / "src" / "View.tsx"
            view.write_text("design/ui-reference/index.html\n", encoding="utf-8", newline="\n")
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            self.git(root, "add", "--all")
            object_id = self.git(root, "hash-object", "-w", "apps/desktop/src/View.tsx")
            self.git(root, "update-index", "--add", "--cacheinfo", "120000", object_id, "apps/desktop/src/View.tsx")
            self.git(root, "commit", "-m", "redirect UI implementation")
            head = self.git(root, "rev-parse", "HEAD")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("regular Git blob" in error for error in result["errors"]))

    def test_automatic_base_rejects_ambiguous_active_experience_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            contract = self.contract("approved-reference-implementation", package, base)
            self.install_contract(root, contract, base_sha=base)
            backlog_path = root / "planning" / "backlog.yaml"
            backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
            first = backlog["capabilities"][0]["slices"][0]["tasks"][0]
            second = dict(first)
            second["id"] = "CAP-01.S01.T02"
            backlog["capabilities"][0]["slices"][0]["tasks"].append(second)
            self.write_yaml(backlog_path, backlog)
            head = self.commit(root, "ambiguous UI tasks")

            with self.assertRaisesRegex(ValueError, "ambiguous active UI experience tasks"):
                automatic_base(root, head)

    def test_contract_task_must_be_active_and_bound_to_validated_base(self) -> None:
        for field, value, expected in (
            ("base_sha", None, "base_sha must exactly equal"),
            ("status", "DONE", "must be active"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                view = root / "apps" / "desktop" / "src" / "View.tsx"
                view.write_text("export const View = () => 'changed';\n", encoding="utf-8", newline="\n")
                contract = self.contract("approved-reference-implementation", package, base)
                self.install_contract(root, contract, base_sha=base)
                backlog_path = root / "planning" / "backlog.yaml"
                backlog = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))
                backlog["capabilities"][0]["slices"][0]["tasks"][0][field] = value
                self.write_yaml(backlog_path, backlog)
                head = self.commit(root, f"unbound task {field}")

                result = validate(root, base, head)

            self.assertFalse(result["ok"])
            self.assertTrue(any(expected in error for error in result["errors"]))

    def test_self_approval_rejects_trailing_separator_lookalike(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _ = self.prepare(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
            approval.update(
                {
                    "reference_id": "REF-2",
                    "version": "2",
                    "approval_kind": "human",
                    "approved_by": "human:owner.",
                    "supersedes": "REF-1",
                }
            )
            self.write_yaml(approval_path, approval)
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"reference_id": "REF-2", "version": "2"})
            self.write_yaml(manifest_path, manifest)
            package = self.reference_package(root)
            approval_commit = self.commit(root, "lookalike approval")
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'lookalike';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract(
                "intentional-design-change",
                package,
                approval_commit,
                approved_by="human:owner.",
                previous="REF-1",
                reference_id="REF-2",
                version="2",
                implementation_agent="agent:owner",
            )
            self.install_contract(root, contract, review_gate="human-and-agent-review", base_sha=base)
            head = self.commit(root, "implement lookalike-approved design")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("does not match" in error or "explicit human" in error for error in result["errors"]))

    def test_defect_restoration_requires_human_classification_until_conformance_gate_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, package = self.prepare(temporary)
            (root / "apps" / "desktop" / "src" / "View.tsx").write_text(
                "export const View = () => 'arbitrary new behavior';\n", encoding="utf-8", newline="\n"
            )
            contract = self.contract("defect-restoration", package, base)
            self.install_contract(root, contract, review_gate="agent-review", base_sha=base)
            head = self.commit(root, "self-asserted restoration")

            result = validate(root, base, head)

        self.assertFalse(result["ok"])
        self.assertTrue(any("requires human-and-agent-review" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
