from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import taskctl  # noqa: E402
import ui_change_gate as ui_gate  # noqa: E402
from ui_change_gate import (  # noqa: E402
    APPLICATION_INVENTORY_HARDENING_ENVELOPE,
    additive_preimplementation_quality_scope_errors,
    application_activation_errors,
    automatic_base,
    immutable_record,
    independent_identity,
    independent_review_hardening_errors,
    provenance_reference_handoff_errors,
    require_resumed_hold,
    restoration_classification_errors,
    restoration_segments,
    reviewed_historical_hardening_errors,
    validate,
)


class UiChangeGateTests(unittest.TestCase):
    def linked_fixture(
        self,
        temporary: str,
        review_gate: str = "human-and-agent-review",
        changed_paths: list[str] | None = None,
    ) -> tuple[Path, str, dict[str, Any], dict[str, Any]]:
        root, approval, package = self.prepare(temporary)
        origin = {
            "id": "CAP-01.S01.T01",
            "wave": "W1",
            "title": "Approved route",
            "objective": "Preserve the approved route",
            "dependencies": [],
            "acceptance_criteria": ["Approved route works"],
            "verification_commands": ["test View"],
            "deployment_profiles": ["LOC"],
            "platform_targets": ["windows-x64"],
            "status": "DONE",
            "owner": "prior-owner",
            "review_gate": review_gate,
            "review": {"reviewer": "prior-reviewer", "result": "approved"},
            "evidence": [{"path": "artifacts/evidence/origin.json"}],
        }
        data: dict[str, Any] = {
            "capabilities": [{"id": "CAP-01", "slices": [{"id": "CAP-01.S01", "tasks": [origin]}]}],
            "waves": [
                {
                    "id": "W1",
                    "approval": {"status": "APPROVED", "commit": approval},
                    "campaign": {"status": "PAUSED", "scope": "wave", "lease": None},
                    "completion": {"status": "IN_PROGRESS"},
                }
            ],
            "release_gates": [{"id": "G1", "after_wave": "W1", "status": "PENDING"}],
        }
        self.write_yaml(root / "planning/backlog.yaml", data)
        origin_commit = self.commit(root, "completed independently reviewed origin")
        spec = {
            "schemaVersion": "1.0",
            "kind": "authority-preserving-correction",
            "origin": {
                "taskId": origin["id"],
                "commit": origin_commit,
                "sha256": taskctl.canonical_json_sha256(origin),
            },
            "reproduction": "Approved route drifts",
            "changedPaths": changed_paths if changed_paths is not None else ["apps/desktop/src/View.tsx"],
            "impactAnalysis": "Restore the unchanged approved route and retain all review obligations",
        }
        spec_path = "artifacts/evidence/W1.C01.T01.spec.json"
        self.write_json(root / spec_path, spec)
        base = self.commit(root, "publish bounded correction spec")
        reference = {
            "path": spec_path,
            "commit": base,
            "sha256": taskctl.evidence_sha256((root / spec_path).read_bytes()),
        }
        indexed = taskctl.index_backlog(data)
        task = taskctl.build_corrective_task(
            data,
            indexed[3],
            origin,
            spec,
            reference,
            Namespace(
                agent="codex", branch="main", base_sha=base, profile="LOC", platform="windows-x64", lease_hours=8
            ),
        )
        data["waves"][0]["campaign"]["corrective_tasks"] = [task]
        contract = self.contract("defect-restoration", package, approval, task_id=task["id"])
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.commit(root, "claim linked correction without experience metadata")
        return root, base, data, contract

    def linked_candidate(self, root: Path, data: dict[str, Any], contract: dict[str, Any]) -> str:
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.write_json(root / str(contract["contractPath"]), contract)
        (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n", encoding="utf-8")
        return self.commit(root, "restore approved route with focused evidence")

    def test_linked_correction_authenticates_without_mutating_origin_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary)
            original = copy.deepcopy(data["capabilities"])
            head = self.linked_candidate(root, data, contract)
            result = validate(root, base, head)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(original, data["capabilities"])
            self.assertNotIn("experience_change", data["waves"][0]["campaign"]["corrective_tasks"][0])
            self.assertNotIn("review_gate", data["waves"][0]["campaign"]["corrective_tasks"][0])

    def test_linked_automatic_base_precedes_missing_contract_and_evidence_only_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary)
            self.assertEqual(base, automatic_base(root, "HEAD"))
            (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n", encoding="utf-8")
            self.commit(root, "UI implementation before missing evidence")
            self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "evidence only"})
            self.commit(root, "later evidence-only commit")
            self.assertEqual(base, automatic_base(root, "HEAD"))
            self.assertFalse(validate(root, automatic_base(root, "HEAD"))["ok"])
            self.linked_candidate(root, data, contract)
            self.assertTrue(validate(root, automatic_base(root, "HEAD"))["ok"])

    def test_linked_rejects_authority_and_live_claim_substitutions(self) -> None:
        for mutation in (
            "origin",
            "history",
            "authority",
            "spec-hash",
            "spec-content",
            "scope",
            "expired",
            "lease-owner",
            "owner",
            "branch",
            "worktree",
            "base",
            "experience",
            "review-gate",
            "ordinary-masquerade",
            "duplicate",
            "historical",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, data, contract = self.linked_fixture(temporary)
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                origin = data["capabilities"][0]["slices"][0]["tasks"][0]
                if mutation == "origin":
                    origin["objective"] = "Substituted purpose"
                elif mutation == "history":
                    task["correction"]["origin_history_sha256"] = "0" * 64
                elif mutation == "authority":
                    task["correction"]["authority_sha256"] = "0" * 64
                elif mutation == "spec-hash":
                    task["correction"]["spec"]["sha256"] = "0" * 64
                elif mutation == "spec-content":
                    task["correction"]["reproduction"] = "Substituted reproduction"
                elif mutation == "scope":
                    task["correction"]["changed_paths"] = ["apps/desktop/src/Other.tsx"]
                elif mutation == "expired":
                    task["lease"]["expires_at"] = "2000-01-01T00:00:00+00:00"
                elif mutation == "lease-owner":
                    task["lease"]["claimed_by"] = "other"
                elif mutation == "owner":
                    task["owner"] = "other"
                elif mutation == "branch":
                    task["branch"] = "codex/other"
                elif mutation == "worktree":
                    task["worktree"] = "other"
                elif mutation == "base":
                    task["base_sha"] = self.git(root, "rev-parse", "HEAD")
                elif mutation == "experience":
                    task["experience_change"] = {"kind": "defect-restoration"}
                elif mutation == "review-gate":
                    origin["review_gate"] = "agent-review"
                elif mutation == "ordinary-masquerade":
                    data["waves"][0]["campaign"]["corrective_tasks"] = []
                    data["capabilities"][0]["slices"][0]["tasks"].append(task)
                elif mutation == "duplicate":
                    data["waves"][0]["campaign"]["corrective_tasks"].append(copy.deepcopy(task))
                head = self.linked_candidate(root, data, contract)
                if mutation == "historical":
                    self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "later"})
                    self.commit(root, "later live head")
                self.assertFalse(validate(root, base, head)["ok"])

    def test_linked_rejects_ambiguous_and_invalid_automatic_bases(self) -> None:
        for mutation in ("duplicate", "missing", "abbreviated", "nonancestor", "expired"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, _base, data, _contract = self.linked_fixture(temporary)
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                if mutation == "duplicate":
                    data["waves"][0]["campaign"]["corrective_tasks"].append(copy.deepcopy(task))
                elif mutation == "expired":
                    task["lease"]["expires_at"] = "2000-01-01T00:00:00+00:00"
                else:
                    task["base_sha"] = {"missing": None, "abbreviated": "abc123", "nonancestor": "0" * 40}[mutation]
                self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
                self.commit(root, "invalid claim")
                with self.assertRaises(ValueError):
                    automatic_base(root, "HEAD")

    def test_linked_rejects_reverted_ui_reference_and_spec_touches(self) -> None:
        for path in (
            "apps/desktop/src/Extra.tsx",
            "design/ui-reference/assets/tokens.css",
            "artifacts/evidence/W1.C01.T01.spec.json",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                root, base, data, contract = self.linked_fixture(temporary)
                target = root / path
                original = target.read_bytes() if target.exists() else None
                target.write_text("unadmitted intermediate content\n", encoding="utf-8")
                self.commit(root, "unadmitted intermediate touch")
                if original is None:
                    target.unlink()
                else:
                    target.write_bytes(original)
                self.commit(root, "revert intermediate touch")
                head = self.linked_candidate(root, data, contract)
                self.assertFalse(validate(root, base, head)["ok"])

    def test_linked_schema_limits_correction_ids_to_v1_restoration(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        contract = self.contract("defect-restoration", "a" * 64, "b" * 40, task_id="W1.C03.T01")
        self.assertEqual([], list(validator.iter_errors(contract)))
        for mutation in ("kind", "version", "task-number", "id"):
            candidate = copy.deepcopy(contract)
            if mutation == "kind":
                candidate.update(
                    changeKind="approved-reference-implementation", implementationScope="not a restoration"
                )
            elif mutation == "version":
                candidate["schemaVersion"] = "1.1"
            else:
                candidate["taskId"] = "W1.C03.T02" if mutation == "task-number" else "W1.C3.T01"
                candidate["contractPath"] = f"artifacts/evidence/ui-change/{candidate['taskId']}.json"
            with self.subTest(mutation=mutation):
                self.assertTrue(list(validator.iter_errors(candidate)))

    def test_linked_explicit_short_base_cannot_hide_evidence_only_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary)
            candidate = self.linked_candidate(root, data, contract)
            self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "later evidence"})
            head = self.commit(root, "evidence-only head")
            self.assertTrue(validate(root, base, head)["ok"])
            result = validate(root, candidate, head)
            self.assertFalse(result["ok"], result)
            self.assertTrue(any("full claim base" in error for error in result["errors"]), result)

    def test_linked_no_ui_range_still_authenticates_claim(self) -> None:
        for mutation in ("none", "expired", "duplicate", "reverted-ui", "reference"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, data, _contract = self.linked_fixture(temporary)
                task = data["waves"][0]["campaign"]["corrective_tasks"][0]
                if mutation == "expired":
                    task["lease"]["expires_at"] = "2000-01-01T00:00:00+00:00"
                elif mutation == "duplicate":
                    data["waves"][0]["campaign"]["corrective_tasks"].append(copy.deepcopy(task))
                elif mutation == "reverted-ui":
                    target = root / "apps/desktop/src/View.tsx"
                    original = target.read_bytes()
                    target.write_text("unreviewed intermediate UI\n", encoding="utf-8")
                    self.commit(root, "intermediate UI")
                    target.write_bytes(original)
                elif mutation == "reference":
                    (root / "design/ui-reference/assets/tokens.css").write_text("unapproved tokens\n", encoding="utf-8")
                self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
                self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": mutation})
                head = self.commit(root, "no net UI implementation")
                result = validate(root, base, head)
                self.assertEqual(mutation == "none", result["ok"], result)

    def test_linked_rejects_rebinding_base_after_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _base, data, contract = self.linked_fixture(temporary)
            rebased = self.git(root, "rev-parse", "HEAD")
            task = data["waves"][0]["campaign"]["corrective_tasks"][0]
            task["base_sha"] = rebased
            task["correction"]["spec"]["commit"] = rebased
            head = self.linked_candidate(root, data, contract)
            result = validate(root, rebased, head)
            self.assertFalse(result["ok"])
            self.assertTrue(any("precede its admission" in error for error in result["errors"]), result)

    def test_linked_rejects_authenticated_origin_without_required_review_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, data, contract = self.linked_fixture(temporary, review_gate="agent-review")
            head = self.linked_candidate(root, data, contract)
            result = validate(root, base, head)
            self.assertFalse(result["ok"])
            self.assertTrue(any("inherited human-and-agent-review" in error for error in result["errors"]), result)

    def test_ordinary_no_ui_historical_range_still_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            self.write_json(root / "artifacts/evidence/ordinary.json", {"note": "non-UI evidence"})
            historical = self.commit(root, "ordinary evidence-only candidate")
            (root / "planning/backlog.yaml").unlink()
            head = self.commit(root, "minimal repository without a task ledger")
            self.assertTrue(validate(root, base, historical)["ok"])
            self.assertTrue(validate(root, historical, head)["ok"])

    def linked_hidden_scope_fixture(self, temporary: str, paths: list[str]) -> tuple[Path, str, str, str]:
        root, base, data, _contract = self.linked_fixture(temporary)
        (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'unreviewed';\n", encoding="utf-8")
        ui_commit = self.commit(root, "real UI change without its required contract")
        data["waves"][0]["campaign"]["corrective_tasks"][0]["correction"]["changed_paths"] = paths
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "substituted scope"})
        head = self.commit(root, "evidence-only head with substituted current scope")
        return root, base, ui_commit, head

    def test_linked_discovery_authenticates_before_scope_filtering(self) -> None:
        for paths in ([], ["tests/desktop/test_view.py"]):
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as temporary:
                root, _base, _ui_commit, _head = self.linked_hidden_scope_fixture(temporary, paths)
                with self.assertRaisesRegex(ValueError, "corrective spec content differs from admission"):
                    automatic_base(root, "HEAD")

    def test_linked_explicit_no_ui_authenticates_before_scope_filtering(self) -> None:
        for paths in ([], ["tests/desktop/test_view.py"]):
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as temporary:
                root, base, ui_commit, head = self.linked_hidden_scope_fixture(temporary, paths)
                self.assertFalse(validate(root, base, head)["ok"])
                result = validate(root, ui_commit, head)
                self.assertFalse(result["ok"], result)
                self.assertTrue(
                    any("corrective spec content differs from admission" in error for error in result["errors"]), result
                )

    def test_linked_public_cli_rejects_scope_disappearance(self) -> None:
        for paths in ([], ["tests/desktop/test_view.py"]):
            with tempfile.TemporaryDirectory() as temporary:
                root, _base, ui_commit, _head = self.linked_hidden_scope_fixture(temporary, paths)
                for explicit_base in ([], ["--base", ui_commit]):
                    with self.subTest(paths=paths, explicit_base=bool(explicit_base)):
                        completed = subprocess.run(
                            [
                                sys.executable,
                                "-B",
                                str(REPO / "tools/ui_change_gate.py"),
                                "--repo",
                                str(root),
                                *explicit_base,
                            ],
                            cwd=REPO,
                            capture_output=True,
                            text=True,
                            timeout=45,
                            check=False,
                        )
                        self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
                        result = json.loads(completed.stdout)
                        self.assertFalse(result["ok"], result)
                        self.assertTrue(
                            any(
                                "corrective spec content differs from admission" in error for error in result["errors"]
                            ),
                            result,
                        )

    def test_linked_genuinely_admitted_non_ui_correction_keeps_parent_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _data, _contract = self.linked_fixture(
                temporary, review_gate="agent-review", changed_paths=["tests/desktop/test_view.py"]
            )
            target = root / "tests/desktop/test_view.py"
            target.parent.mkdir(parents=True)
            target.write_text("# admitted non-UI correction fixture\n", encoding="utf-8")
            head = self.commit(root, "genuinely admitted non-UI correction")
            self.assertEqual("HEAD^", automatic_base(root, "HEAD"))
            self.assertTrue(validate(root, base, head)["ok"])
            self.assertTrue(validate(root, "HEAD^", head)["ok"])
            completed = subprocess.run(
                [sys.executable, "-B", str(REPO / "tools/ui_change_gate.py"), "--repo", str(root)],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["ok"])

    def linked_relocated_correction_fixture(self, temporary: str, shape: str = "both") -> tuple[Path, str, str, str]:
        root, base, data, contract = self.linked_fixture(temporary)
        ui_commit = self.linked_candidate(root, data, contract)
        task = data["waves"][0]["campaign"]["corrective_tasks"].pop()
        if shape == "id-only":
            task.pop("correction")
        elif shape == "binding-only":
            task["id"] = "CAP-01.S01.T99"
        data["capabilities"][0]["slices"][0]["tasks"].append(task)
        self.write_yaml(root / "planning/backlog.yaml", taskctl.serializable_backlog(data))
        self.write_json(root / "artifacts/evidence/W1.C01.T01.note.json", {"note": "relocated correction"})
        head = self.commit(root, "relocate correction into ordinary inventory after UI work")
        return root, base, ui_commit, head

    def test_linked_public_cli_rejects_relocated_correction_on_short_no_ui_range(self) -> None:
        for shape in ("both", "id-only", "binding-only"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as temporary:
                root, _base, ui_commit, _head = self.linked_relocated_correction_fixture(temporary, shape)
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(REPO / "tools/ui_change_gate.py"),
                        "--repo",
                        str(root),
                        "--base",
                        ui_commit,
                    ],
                    cwd=REPO,
                    capture_output=True,
                    text=True,
                    timeout=45,
                    check=False,
                )
                self.assertEqual(1, completed.returncode, completed.stdout + completed.stderr)
                result = json.loads(completed.stdout)
                self.assertFalse(result["ok"], result)
                self.assertTrue(
                    any("must be an admitted campaign corrective task" in error for error in result["errors"]), result
                )

    def test_linked_relocated_correction_is_denied_before_all_range_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, ui_commit, head = self.linked_relocated_correction_fixture(temporary)
            with self.assertRaisesRegex(ValueError, "must be an admitted campaign corrective task"):
                automatic_base(root, "HEAD")
            self.assertFalse(validate(root, base, head)["ok"])
            result = validate(root, ui_commit, head)
            self.assertFalse(result["ok"], result)
            self.assertTrue(
                any("must be an admitted campaign corrective task" in error for error in result["errors"]), result
            )

    def legacy_control_fixture(self, temporary: str, mutation: str = "") -> tuple[Path, str, str, str]:
        root, predecessor, _ = self.prepare(temporary)
        stem = "artifacts/evidence/fixture-control"
        contract_path, evidence_path, review_path = (
            stem + ".maintenance-01.md",
            stem + ".evidence-01.json",
            stem + ".review-01.json",
        )
        sources = [contract_path, "tools/ui_conformance.py"]
        if mutation == "product":
            sources.append("apps/desktop/src-tauri/src/lib.rs")
        elif mutation == "build-tool":
            sources.append("tools/core_sidecar_build.py")
        for path in sources:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Bounded synthetic control fixture\n", encoding="utf-8")
        candidate = self.commit(root, "legacy control candidate")
        bindings = [
            {
                "path": path,
                "blob": self.git(root, "rev-parse", candidate + ":" + path),
                "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest(),
            }
            for path in sorted(sources)
        ]
        evidence = {
            "schemaVersion": "1.0",
            "documentType": "bounded-governance-maintenance-evidence",
            "candidateCommit": candidate,
            "predecessorCommit": predecessor,
            "implementer": "agent:codex",
            "riskTier": 2,
            "contract": contract_path,
            "selectedChecksStatus": "PASS",
            "independentReviewStatus": "PENDING",
            "changedFiles": bindings,
        }
        if mutation == "missing-implementer":
            evidence.pop("implementer")
        elif mutation == "invalid-implementer":
            evidence["implementer"] = "not an agent"
        self.write_json(root / evidence_path, evidence)
        if mutation == "mixed-evidence":
            (root / "extra.txt").write_text("extra delivery\n", encoding="utf-8")
        delivery = self.commit(root, "legacy evidence delivery")
        review: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "bounded-governance-maintenance-independent-review",
            "reviewId": "fixture-control.review-01",
            "reviewedCommit": candidate,
            "predecessorCommit": predecessor,
            "reviewedAt": "2026-09-01T00:00:00Z",
            "reviewer": "agent:independent-reviewer",
            "independence": {"implementer": "agent:codex", "implementationAuthoredByReviewer": False},
            "disposition": "ACCEPTED",
            "findings": [],
            "evidence": {
                "path": evidence_path,
                "introductionCommit": delivery,
                "gitBlob": self.git(root, "rev-parse", delivery + ":" + evidence_path),
                "sha256": hashlib.sha256((root / evidence_path).read_bytes()).hexdigest(),
            },
            "reviewedArtifacts": [
                {"path": item["path"], "gitBlob": item["blob"], "sha256": item["sha256"]} for item in bindings
            ],
        }
        if mutation == "self-review":
            review["reviewer"] = "agent:co_dex"
        elif mutation == "missing-implementer":
            review["independence"].pop("implementer")
        elif mutation == "invalid-implementer":
            review["independence"]["implementer"] = "not an agent"
        elif mutation == "wrong-candidate":
            review["reviewedCommit"] = predecessor
        elif mutation == "wrong-predecessor":
            review["predecessorCommit"] = candidate
        elif mutation == "evidence-hash":
            review["evidence"]["sha256"] = "0" * 64
        elif mutation == "source-hash":
            review["reviewedArtifacts"][0]["sha256"] = "0" * 64
        elif mutation == "adverse":
            review["findings"] = [{"id": "OPEN"}]
        self.write_json(root / review_path, review)
        if mutation == "mixed-review":
            (root / "extra-review.txt").write_text("extra delivery\n", encoding="utf-8")
        self.commit(root, "legacy independent review")
        if mutation == "rewrite-revert":
            self.write_json(root / review_path, {**review, "findings": [{"id": "changed"}]})
            self.commit(root, "rewrite historical review")
            self.write_json(root / review_path, review)
            self.commit(root, "restore historical review bytes")
        (root / "claim-marker.txt").write_text("later correction start\n", encoding="utf-8")
        cutoff = self.commit(root, "correction task start")
        return root, candidate, cutoff, review_path

    def test_legacy_control_maintenance_authenticates_existing_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, candidate, cutoff, _ = self.legacy_control_fixture(temporary)
            self.assertEqual([], ui_gate.legacy_control_maintenance_errors(root, candidate, cutoff, cutoff))

    def test_legacy_control_maintenance_rejects_false_or_late_authority(self) -> None:
        for mutation in (
            "self-review",
            "wrong-candidate",
            "wrong-predecessor",
            "evidence-hash",
            "source-hash",
            "adverse",
            "product",
            "build-tool",
            "mixed-evidence",
            "mixed-review",
            "rewrite-revert",
            "late",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, candidate, cutoff, _ = self.legacy_control_fixture(temporary, mutation)
                boundary = candidate if mutation == "late" else cutoff
                self.assertTrue(ui_gate.legacy_control_maintenance_errors(root, candidate, cutoff, boundary))

    def test_legacy_control_maintenance_requires_valid_implementer_identity(self) -> None:
        for mutation in ("missing-implementer", "invalid-implementer"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, candidate, cutoff, _ = self.legacy_control_fixture(temporary, mutation)
                self.assertTrue(ui_gate.legacy_control_maintenance_errors(root, candidate, cutoff, cutoff))

    def test_inherited_control_admission_requires_exact_complete_linear_range(self) -> None:
        for mutation in ("", "extra-path", "hidden-extra-revert", "overlap", "outside", "merge", "later-revert"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, base, _ = self.prepare(temporary)
                policy = json.loads((root / "ui-change-policy.json").read_text())
                source = root / "tools/ui_conformance.py"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("CHECK = True\n", encoding="utf-8")
                (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'inherited';\n")
                if mutation in {"extra-path", "hidden-extra-revert"}:
                    (root / "extra.txt").write_text("not reviewed\n")
                candidate = self.commit(root, "reviewed correction control and UI")
                if mutation == "hidden-extra-revert":
                    self.git(root, "rm", "extra.txt")
                    candidate = self.commit(root, "remove undeclared intermediate path")
                paths = ["apps/desktop/src/View.tsx", "tools/ui_conformance.py"]
                ranges = [{"base": base, "candidate": candidate, "paths": paths}]
                if mutation == "overlap":
                    ranges *= 2
                elif mutation == "outside":
                    ranges = []
                if mutation == "merge":
                    self.git(root, "switch", "-c", "side")
                    (root / "side.txt").write_text("side\n")
                    self.commit(root, "side history")
                    self.git(root, "switch", "main")
                    self.git(root, "merge", "--no-ff", "side", "-m", "merge ambiguity")
                (root / "activation.txt").write_text("returned parent\n")
                activation = self.commit(root, "parent activation")
                if mutation == "later-revert":
                    source.write_text("CHECK = False\n")
                    self.commit(root, "unreviewed later control")
                    source.write_text("CHECK = True\n")
                    self.commit(root, "restore later control bytes")
                (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n")
                head = self.commit(root, "resumed UI")
                scope = {"correctionSubmissionRanges": ranges, "reactivationCommit": activation}
                errors = application_activation_errors(
                    root,
                    base,
                    head,
                    ["tools/ui_conformance.py"],
                    {"schemaVersion": "1.1", "changeKind": "defect-restoration", "amendmentAuthority": {}},
                    policy,
                    resumed_scope=scope,
                )
                self.assertEqual(bool(mutation), bool(errors), errors)

    def test_public_resumed_control_dispatch_authenticates_once_before_admission(self) -> None:
        for invalid_authority in (False, True):
            with self.subTest(invalid_authority=invalid_authority), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'restored';\n")
                (root / "tools").mkdir(exist_ok=True)
                (root / "tools/ui_conformance.py").write_text("CHECK = True\n")
                contract = self.contract("defect-restoration", package, base, task_id="W1.A08.T02")
                contract.update(
                    {
                        "schemaVersion": "1.1",
                        "amendmentAuthority": {
                            "correctionId": "W1.A09",
                            "adoptionCommit": "c" * 40,
                            "reactivationCommit": "d" * 40,
                            "inheritedCorrectionUiFiles": ["apps/desktop/src/View.tsx"],
                            "resumedUiFiles": ["apps/desktop/src/View.tsx"],
                            "classification": {
                                "path": "artifacts/evidence/W1.A08.T02.ui-classification-R01.json",
                                "sha256": "e" * 64,
                                "commit": "f" * 40,
                            },
                        },
                    }
                )
                self.install_contract(root, contract, base_sha=base)
                backlog_path = root / "planning/backlog.yaml"
                backlog = yaml.safe_load(backlog_path.read_text())
                task = backlog["wave_amendments"][0]["tasks"][0]
                task.update({"branch": "main", "lease": {"claimed_by": "codex"}})
                self.write_yaml(backlog_path, backlog)
                head = self.commit(root, "synthetic resumed public boundary")
                calls: list[str] = []
                scope = {"correctionSubmissionRanges": [], "reactivationCommit": "d" * 40}

                # Stub only authenticated authority/classification for this
                # public dispatch test; real Git range/review checks are separate.
                def authenticate(
                    *_args: object,
                    recorded: list[str] = calls,
                    invalid: bool = invalid_authority,
                    bound_scope: dict[str, Any] = scope,
                ) -> dict[str, Any]:
                    recorded.append("authenticate")
                    if invalid:
                        raise ValueError("unadopted or unreviewed correction")
                    return bound_scope

                def admit(
                    *_args: object,
                    recorded: list[str] = calls,
                    bound_scope: dict[str, Any] = scope,
                    **kwargs: object,
                ) -> list[str]:
                    recorded.append("admit")
                    self.assertIs(bound_scope, kwargs.get("resumed_scope"))
                    return []

                with (
                    patch("ui_change_gate.resumed_amendment_authority", side_effect=authenticate) as authority,
                    patch("ui_change_gate.application_activation_errors", side_effect=admit),
                    patch("ui_change_gate.restoration_classification_errors", return_value=[]),
                ):
                    result = validate(root, base, head)
                self.assertEqual(not invalid_authority, result["ok"], result["errors"])
                self.assertEqual(["authenticate"] if invalid_authority else ["authenticate", "admit"], calls)
                authority.assert_called_once()

    def test_resumed_hold_rejects_inconsistent_current_authority(self) -> None:
        parent: dict[str, Any] = {
            "id": "W1.A08",
            "lifecycle": {"status": "ACTIVE"},
            "campaign": {
                "status": "ACTIVE",
                "scope": "wave-amendment",
                "owner": "codex",
                "lease": {"claimed_by": "codex"},
            },
        }
        backlog: dict[str, Any] = {"control_plane": {"active_amendment": "W1.A08"}, "wave_amendments": [parent]}
        projections = [
            {
                "parentId": "W1.A08",
                "correctionId": "W1.A09",
                "phase": "returned",
                "holdOwner": "W1.A08",
                "parentFrozen": False,
            }
        ]
        require_resumed_hold(backlog, parent, "W1.A09", "codex", projections)
        mutations: tuple[tuple[tuple[str, ...], object], ...] = (
            (("lifecycle", "status"), "ADOPTED"),
            (("lifecycle", "status"), "PAUSED"),
            (("campaign", "status"), "REVIEW"),
            (("campaign", "scope"), "wave"),
            (("campaign", "owner"), "other"),
            (("campaign", "lease", "claimed_by"), "other"),
            (("campaign", "lease"), None),
        )
        for path, value in mutations:
            with self.subTest(path=path, value=value):
                mutated = copy.deepcopy(parent)
                node = mutated
                for part in path[:-1]:
                    node = node[part]
                node[path[-1]] = value
                with self.assertRaisesRegex(ValueError, "current lifecycle"):
                    require_resumed_hold(
                        {**backlog, "wave_amendments": [mutated]}, mutated, "W1.A09", "codex", projections
                    )
        for relation in (
            [],
            projections * 2,
            [{**projections[0], "holdOwner": None}],
            [{**projections[0], "parentFrozen": True}],
            [{**projections[0], "phase": "executing"}],
        ):
            with self.subTest(relation=relation), self.assertRaisesRegex(ValueError, "derived hold"):
                require_resumed_hold(backlog, parent, "W1.A09", "codex", relation)
        for document in (
            {**backlog, "control_plane": {"active_amendment": "W1.A09"}},
            {**backlog, "wave_amendments": [parent, {"id": "W1.A10", "campaign": {"status": "ACTIVE"}}]},
        ):
            with self.subTest(document=document), self.assertRaisesRegex(ValueError, "derived hold"):
                require_resumed_hold(document, parent, "W1.A09", "codex", projections)

    def test_classification_real_git_binding_and_stale_or_adverse_denials(self) -> None:
        # The capture reader has its own real PNG/producer suite. Stub only that
        # boundary here; this fixture tests actual Git records and classification,
        # not pixels, renderer behavior, or a complete product qualification.
        for finding in (None, {"blockingVisualAcceptance": True}, {"blockingVisualAcceptance": 0}, {}):
            with self.subTest(finding=finding), tempfile.TemporaryDirectory() as temporary:
                root, base, package = self.prepare(temporary)
                policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
                identity = "W1.A08.T02"
                source_path = "apps/desktop/src/View.tsx"
                (root / source_path).write_text("export const View = () => 'restored';\n", encoding="utf-8")
                candidate = self.commit(root, "restoration candidate")
                capture_path = f"artifacts/evidence/{identity}.captures-01/manifest.json"
                manifest = {
                    "schemaVersion": "1.0",
                    "documentType": "product-style-capture-bundle",
                    "producer": {
                        "producerCommit": candidate,
                        "referencePackageSha256": package,
                        "inputGitBlobs": {source_path: self.git(root, "rev-parse", f"{candidate}:{source_path}")},
                    },
                    "report": {"fixtureOnly": True},
                }
                self.write_json(root / capture_path, manifest)
                capture_commit = self.commit(root, "synthetic capture boundary")
                capture_sha = hashlib.sha256((root / capture_path).read_bytes()).hexdigest()
                visual_path = f"artifacts/evidence/{identity}.visual-review-01.json"
                self.write_json(
                    root / visual_path,
                    {
                        "documentType": "independent-product-visual-disposition",
                        "taskId": identity,
                        "reviewer": "agent:/root/fixture_review",
                        "disposition": "approved",
                        "findings": [] if finding is None else [finding],
                        "bindings": {
                            "producerCommit": candidate,
                            "manifest": capture_path,
                            "manifestSha256": capture_sha,
                            "captureDeliveryCommit": capture_commit,
                            "referencePackageSha256": package,
                        },
                    },
                )
                visual_commit = self.commit(root, "synthetic independent visual record")
                scope = {
                    "taskDefinitionSha256": "d" * 64,
                    "resumedUiFiles": [source_path],
                    "resumedUiCommits": [candidate],
                    "reactivationCommit": base,
                }
                classification_path = f"artifacts/evidence/{identity}.ui-classification-R01.json"
                self.write_json(
                    root / classification_path,
                    {
                        "schemaVersion": "1.0",
                        "documentType": "independent-ui-restoration-disposition",
                        "taskId": identity,
                        "baseCommit": base,
                        "candidateCommit": candidate,
                        "reviewer": "agent:/root/fixture_review",
                        "disposition": "approved",
                        "taskDefinitionSha256": scope["taskDefinitionSha256"],
                        "referencePackageSha256": package,
                        "resumedUiFiles": [source_path],
                        "resumedUiCommits": [candidate],
                        "approvedTaskAllowsRestoration": True,
                        "authorityPreserved": True,
                        "formalTaskApproval": False,
                        "normativeRationale": "Synthetic authority fixture, not an actual visual observation.",
                        "captures": {"path": capture_path, "sha256": capture_sha, "deliveryCommit": capture_commit},
                        "visualReview": {
                            "path": visual_path,
                            "commit": visual_commit,
                            "sha256": hashlib.sha256((root / visual_path).read_bytes()).hexdigest(),
                        },
                    },
                )
                head = self.commit(root, "synthetic independent classification")
                contract = {
                    "taskId": identity,
                    "implementationAgent": "agent:codex",
                    "reference": {"packageSha256": package},
                    "amendmentAuthority": {
                        "classification": {
                            "path": classification_path,
                            "commit": head,
                            "sha256": hashlib.sha256((root / classification_path).read_bytes()).hexdigest(),
                        }
                    },
                }
                with (
                    patch("product_style_check.read_capture_bundle", return_value=manifest) as capture_reader,
                    patch("desktop_app_check.qualification_capture_contract", return_value=[]),
                    patch("desktop_app_check.qualification_report_errors", return_value=[]),
                ):
                    errors = restoration_classification_errors(root, base, head, contract, scope, policy)
                    if finding is not None:
                        self.assertTrue(any("findings" in error for error in errors), errors)
                        capture_reader.assert_not_called()
                    else:
                        self.assertEqual([], errors)
                        capture_reader.assert_called_once()
                        original = (root / source_path).read_bytes()
                        (root / source_path).write_text("export const View = () => 'unreviewed';\n", encoding="utf-8")
                        self.commit(root, "unreviewed UI edit")
                        (root / source_path).write_bytes(original)
                        reverted = self.commit(root, "hide edit by restoring final bytes")
                        errors = restoration_classification_errors(root, base, reverted, contract, scope, policy)
                        self.assertTrue(any("stale" in error for error in errors), errors)

    def test_restoration_judgment_requires_booleans_not_numeric_lookalikes(self) -> None:
        base, candidate, introduction = "a" * 40, "b" * 40, "c" * 40
        identity = "W1.A08.T02"
        scope = {
            "taskDefinitionSha256": "d" * 64,
            "resumedUiFiles": ["apps/desktop/src/View.tsx"],
            "resumedUiCommits": [candidate],
            "reactivationCommit": base,
        }
        contract = {
            "taskId": identity,
            "implementationAgent": "agent:codex",
            "reference": {"packageSha256": "e" * 64},
            "amendmentAuthority": {
                "classification": {
                    "path": f"artifacts/evidence/{identity}.ui-classification-R01.json",
                    "sha256": "f" * 64,
                    "commit": introduction,
                }
            },
        }
        record = {
            "schemaVersion": "1.0",
            "documentType": "independent-ui-restoration-disposition",
            "taskId": identity,
            "baseCommit": base,
            "candidateCommit": candidate,
            "reviewer": "agent:/root/independent_review",
            "disposition": "approved",
            "taskDefinitionSha256": scope["taskDefinitionSha256"],
            "referencePackageSha256": "e" * 64,
            "resumedUiFiles": scope["resumedUiFiles"],
            "resumedUiCommits": [candidate],
            "approvedTaskAllowsRestoration": True,
            "authorityPreserved": True,
            "formalTaskApproval": False,
            "normativeRationale": "Restore approved geometry.",
        }
        for field, value in (
            ("approvedTaskAllowsRestoration", 1),
            ("authorityPreserved", 1),
            ("formalTaskApproval", 0),
        ):
            with (
                self.subTest(field=field),
                patch("ui_change_gate.immutable_record", return_value=({**record, field: value}, introduction)),
                patch("ui_change_gate.is_ancestor", return_value=True),
                patch("ui_change_gate.git") as git_read,
            ):
                errors = restoration_classification_errors(REPO, base, introduction, contract, scope, {})
                self.assertTrue(any("independent approved-task/source classification" in error for error in errors))
                git_read.assert_not_called()

    def test_immutable_authority_record_rejects_rewrite_even_when_reverted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _base, _package = self.prepare(temporary)
            path = "artifacts/evidence/fixture-review.json"
            record = {"disposition": "approved"}
            self.write_json(root / path, record)
            introduction = self.commit(root, "independent record")
            self.assertEqual((record, introduction), immutable_record(root, introduction, path))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                immutable_record(root, introduction, path, "0" * 64)
            self.write_json(root / path, {"disposition": "changes-requested"})
            self.commit(root, "rewrite record")
            self.write_json(root / path, record)
            reverted = self.commit(root, "restore bytes but not history")
            with self.assertRaisesRegex(ValueError, "immutable introduction"):
                immutable_record(root, reverted, path)

    def test_resumed_amendment_schema_is_opt_in_and_cannot_authorize_ordinary_tasks(self) -> None:
        schema = json.loads((REPO / "design/ui-change.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        contract = self.contract("defect-restoration", "a" * 64, "b" * 40, task_id="W1.A08.T02")
        contract.update(
            {
                "schemaVersion": "1.1",
                "amendmentAuthority": {
                    "correctionId": "W1.A09",
                    "adoptionCommit": "c" * 40,
                    "reactivationCommit": "d" * 40,
                    "inheritedCorrectionUiFiles": ["apps/desktop/src/View.tsx"],
                    "resumedUiFiles": ["apps/desktop/src/View.tsx"],
                    "classification": {
                        "path": "artifacts/evidence/W1.A08.T02.ui-classification-R01.json",
                        "sha256": "e" * 64,
                        "commit": "f" * 40,
                    },
                },
            }
        )
        self.assertEqual([], list(validator.iter_errors(contract)))
        invalid_fields: tuple[dict[str, Any], ...] = (
            {"schemaVersion": "1.0"},
            {"taskId": "CAP-01.S01.T01"},
            {"changeKind": "approved-reference-implementation"},
            {"amendmentAuthority": {}},
            {"review_gate": "human-and-agent-review"},
        )
        for fields in invalid_fields:
            with self.subTest(fields=fields):
                self.assertTrue(list(validator.iter_errors({**contract, **fields})))
        self.assertTrue(independent_identity("agent:/root/independent_review", "codex"))
        for reviewer in ("codex", "agent:codex", "agent:co_dex", "human:owner", "agent:../../codex"):
            self.assertFalse(independent_identity(reviewer, "codex"))

    def test_resumed_amendment_selects_original_base_without_a_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, _package = self.prepare(temporary)
            self.write_yaml(
                root / "planning/backlog.yaml",
                {
                    "capabilities": [],
                    "wave_amendments": [
                        {
                            "id": "W1.A08",
                            "tasks": [
                                {
                                    "id": "W1.A08.T02",
                                    "amendment_id": "W1.A08",
                                    "status": "IN_PROGRESS",
                                    "base_sha": base,
                                }
                            ],
                        },
                        {"id": "W1.A09", "correction": {"id": "W1.A08"}, "lifecycle": {"status": "ADOPTED"}},
                    ],
                },
            )
            self.commit(root, "explicit resumed task")
            (root / "only-evidence.txt").write_text("no product edit\n", encoding="utf-8")
            head = self.commit(root, "later evidence")
            self.assertEqual(base, automatic_base(root, head))

    def test_restoration_segments_authenticate_each_real_git_commit(self) -> None:
        policy = {
            "implementationRoots": ["apps/desktop/src"],
            "implementationExtensions": [".css"],
            "ignoredImplementationSuffixes": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Gate Test")
            self.git(root, "config", "user.email", "ui-gate@example.invalid")
            self.git(root, "config", "core.autocrlf", "false")
            source = root / "apps/desktop/src/app.css"
            source.parent.mkdir(parents=True)
            source.write_text("a { color: black; }\n", encoding="utf-8")
            base = self.commit(root, "original claim")
            source.write_text("a { color: blue; }\n", encoding="utf-8")
            inherited = self.commit(root, "approved correction candidate")
            (root / "activation.txt").write_text("explicit activation\n", encoding="utf-8")
            activation = self.commit(root, "reactivation")
            source.write_text("a { color: blue; margin: 0; }\n", encoding="utf-8")
            head = self.commit(root, "resumed restoration")
            path = "apps/desktop/src/app.css"
            ranges = [{"base": base, "candidate": inherited, "paths": [path]}]
            expected = {
                "inheritedCorrectionUiFiles": [path],
                "resumedUiFiles": [path],
                "inheritedUiCommits": [inherited],
                "resumedUiCommits": [head],
            }
            self.assertEqual(expected, restoration_segments(root, base, head, activation, ranges, policy))
            for label, invalid in (("gap", []), ("overlap", ranges * 2), ("omission", [{**ranges[0], "paths": []}])):
                with self.subTest(label=label), self.assertRaises(ValueError):
                    restoration_segments(root, base, head, activation, invalid, policy)
            hidden = source.with_name("hidden.css")
            hidden.write_text(".hidden { color: red; }\n", encoding="utf-8")
            self.commit(root, "unattributed add")
            hidden.unlink()
            reverted = self.commit(root, "hide addition in net diff")
            with self.assertRaisesRegex(ValueError, "net inventory"):
                restoration_segments(root, base, reverted, activation, ranges, policy)
            self.git(root, "switch", "-c", "side", head)
            (root / "side.txt").write_text("side\n", encoding="utf-8")
            self.commit(root, "side history")
            self.git(root, "switch", "main")
            self.git(root, "merge", "--no-ff", "side", "-m", "ambiguous history")
            merged = self.git(root, "rev-parse", "HEAD").strip()
            with self.assertRaisesRegex(ValueError, "linear"):
                restoration_segments(root, base, merged, activation, ranges, policy)

    def test_current_w1_amendment_ui_range_accepts_reviewed_historical_maintenance(self) -> None:
        result = validate(
            REPO,
            "bd8d752a0fcec1f40b1a8abe59b793c783946e4e",
            "6c5757659ecbca11f1469e1ab3dfec330fe0d74f",
        )

        self.assertTrue(result["ok"], result["errors"])

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

    def inventory_fixture(self, temporary: str) -> tuple[Path, str, dict[str, Any], dict[str, Any]]:
        root, _, _ = self.prepare(temporary)
        scope: dict[str, Any] = {
            "schemaVersion": "1.0",
            "documentType": "python-quality-scope",
            "governedRoots": ["services", "tests", "tools"],
            "pythonFiles": ["services/existing.py", "tests/existing.py"],
        }
        for path in [*scope["pythonFiles"], "tools/already_present.py"]:
            source = root / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("EXISTING = True\n", encoding="utf-8")
        self.write_json(root / "quality-scope.json", scope)
        base = self.commit(root, "inventory baseline")
        (root / "apps/desktop/src/View.tsx").write_text("export const View = () => 'UI';\n", encoding="utf-8")
        self.commit(root, "earlier UI implementation")
        policy = json.loads((root / "ui-change-policy.json").read_text(encoding="utf-8"))
        return root, base, scope, policy

    def test_late_additive_python_inventory_does_not_change_ui_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, scope, policy = self.inventory_fixture(temporary)
            for path in ["tools/new_check.py", "services/new.py", "tests/new.py"]:
                (root / path).write_text("NEW = True\n", encoding="utf-8")
                scope["pythonFiles"].append(path)
            self.write_json(root / "quality-scope.json", scope)
            head = self.commit(root, "add new non-UI Python inventory after UI")
            self.assertEqual([], additive_preimplementation_quality_scope_errors(root, head, policy))
            self.assertEqual(
                [],
                application_activation_errors(
                    root,
                    base,
                    head,
                    ["quality-scope.json"],
                    {"changeKind": "approved-reference-implementation"},
                    policy,
                ),
            )

    def test_late_inventory_rejects_control_or_nonadditive_or_noncanonical_changes(self) -> None:
        cases = (
            "metadata",
            "roots",
            "removal",
            "reorder",
            "duplicate",
            "missing-source",
            "existing-source",
            "gate-source",
            "ui-source",
            "mixed-gate",
            "mixed-ui",
            "non-python",
            "outside-root",
            "dot-segment",
            "double-slash",
            "symlink",
            "merge",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root, _, scope, policy = self.inventory_fixture(temporary)
                source_path = {
                    "existing-source": "tools/already_present.py",
                    "gate-source": "tools/ui_change_gate.py",
                    "ui-source": "apps/desktop/src/extra.py",
                    "non-python": "tools/new.txt",
                    "outside-root": "other/new.py",
                    "dot-segment": "tools/../tools/new.py",
                    "double-slash": "tools//new.py",
                }.get(case, "tools/new_check.py")
                scope["pythonFiles"].append(source_path)
                if case != "missing-source":
                    source = root / source_path
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text("NEW = True\n", encoding="utf-8")
                if case == "metadata":
                    scope["extra"] = True
                elif case == "roots":
                    scope["governedRoots"].append("other")
                elif case == "removal":
                    scope["pythonFiles"].pop(0)
                elif case == "reorder":
                    scope["pythonFiles"][:2] = reversed(scope["pythonFiles"][:2])
                elif case == "duplicate":
                    scope["pythonFiles"].append(source_path)
                elif case == "mixed-gate":
                    (root / "tools/ui_change_gate.py").write_text("GATE = True\n", encoding="utf-8")
                elif case == "mixed-ui":
                    (root / "apps/desktop/src/View.tsx").write_text(
                        "export const View = () => 'more';\n", encoding="utf-8"
                    )
                self.write_json(root / "quality-scope.json", scope)
                if case == "symlink":
                    self.git(root, "add", "--all")
                    oid = self.git(root, "hash-object", "-w", source_path)
                    self.git(root, "update-index", "--add", "--cacheinfo", "120000", oid, source_path)
                    self.git(root, "commit", "-m", "redirected inventory source")
                    head = self.git(root, "rev-parse", "HEAD")
                elif case == "merge":
                    self.git(root, "switch", "-c", "side")
                    self.commit(root, "side inventory")
                    self.git(root, "switch", "main")
                    self.git(root, "merge", "--no-ff", "side", "-m", "merge inventory")
                    head = self.git(root, "rev-parse", "HEAD")
                else:
                    head = self.commit(root, "invalid inventory " + case)
                self.assertTrue(additive_preimplementation_quality_scope_errors(root, head, policy))

    def test_late_inventory_add_revert_cannot_hide_invalid_intermediate_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, scope, policy = self.inventory_fixture(temporary)
            original = copy.deepcopy(scope)
            scope["governedRoots"].append("ungoverned")
            self.write_json(root / "quality-scope.json", scope)
            self.commit(root, "invalid intermediate roots")
            self.write_json(root / "quality-scope.json", original)
            head = self.commit(root, "restore inventory net bytes")
            self.assertTrue(
                application_activation_errors(
                    root,
                    base,
                    head,
                    ["quality-scope.json"],
                    {"changeKind": "approved-reference-implementation"},
                    policy,
                )
            )

    def test_public_validation_rejects_inventory_control_change_even_after_exact_revert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, base, scope, _ = self.inventory_fixture(temporary)
            approval = self.git(root, "rev-parse", base + "^")
            contract = self.contract("approved-reference-implementation", self.reference_package(root), approval)
            self.install_contract(root, contract, base_sha=base)
            valid = self.commit(root, "valid public UI contract")
            result = validate(root, base, valid)
            self.assertTrue(result["ok"], result["errors"])
            original = copy.deepcopy(scope)
            scope["governedRoots"].append("ungoverned")
            self.write_json(root / "quality-scope.json", scope)
            self.commit(root, "invalid intermediate public control change")
            self.write_json(root / "quality-scope.json", original)
            head = self.commit(root, "restore public control net bytes")
            result = validate(root, base, head)
            self.assertFalse(result["ok"], result["errors"])
            self.assertTrue(any("gate" in error for error in result["errors"]), result)

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

    def install_provenance_reference_handoff(self, root: Path) -> tuple[str, str]:
        marker = root / "planning" / "review-marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("adverse review\n", encoding="utf-8", newline="\n")
        prior_review = self.commit(root, "record adverse review marker")

        approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
        manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
        approval = yaml.safe_load(approval_path.read_text(encoding="utf-8"))
        proposal_authority = {
            "wave_id": "W1",
            "slice_id": "CAP-03.S05",
            "approved_wave_commit": "1" * 40,
            "slice_plan": "planning/slice-plans/CAP-03/CAP-03.S05-fixture.md",
        }
        approval.update(
            {
                "status": "proposed",
                "approval_kind": "pending-human",
                "approved_by": None,
                "approved_at": None,
                "authority": proposal_authority,
            }
        )
        self.write_yaml(approval_path, approval)
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "proposed"
        self.write_yaml(manifest_path, manifest)
        self.reference_package(root)
        proposal = self.commit(root, "propose corrected reference provenance")

        approval.update(
            {
                "status": "approved",
                "approval_kind": "human",
                "approved_by": "human:repository-owner",
                "approved_at": "2026-09-03T12:00:00+00:00",
                "authority": {**proposal_authority, "proposal_commit": proposal},
            }
        )
        self.write_yaml(approval_path, approval)
        manifest["status"] = "approved"
        self.write_yaml(manifest_path, manifest)
        self.reference_package(root)
        self.commit(root, "approve corrected reference provenance")

        schema_path = root / "design" / "ui-change.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["$comment"] = "remediated after corrected reference provenance"
        self.write_json(schema_path, schema)
        remediation = self.commit(root, "remediate reviewed control")
        return prior_review, remediation

    def test_provenance_reference_handoff_accepts_exact_human_approval_between_review_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, _ = self.prepare(temporary)
            prior_review, remediation = self.install_provenance_reference_handoff(root)

            errors = provenance_reference_handoff_errors(root, prior_review, remediation)

        self.assertEqual([], errors)

    def test_provenance_reference_handoff_rejects_non_governance_intervening_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, _ = self.prepare(temporary)
            marker = root / "planning" / "review-marker.txt"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("adverse review\n", encoding="utf-8", newline="\n")
            prior_review = self.commit(root, "record adverse review marker")
            token = root / "design" / "ui-reference" / "assets" / "tokens.css"
            token.write_text(":root { --surface: red; }\n", encoding="utf-8", newline="\n")
            self.commit(root, "mutate governed product reference")
            schema_path = root / "design" / "ui-change.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["$comment"] = "attempt remediation after unrelated mutation"
            self.write_json(schema_path, schema)
            remediation = self.commit(root, "attempt reviewed control remediation")

            errors = provenance_reference_handoff_errors(root, prior_review, remediation)

        self.assertTrue(any("unauthorized intervening commit" in error for error in errors), errors)

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
