from __future__ import annotations

import argparse
import base64
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import gcr3ctl  # noqa: E402
import gcr4ctl  # noqa: E402
import recoveryctl  # noqa: E402
import taskctl  # noqa: E402


class Gcr3ctlTests(unittest.TestCase):
    def git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

    def write_json(self, repo: Path, relative: str, document: dict) -> Path:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(document, indent=2) + "\n").encode())
        return path

    def run_python(self, repo: Path, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, *arguments],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def create_exact_gcr4_bridge(self, temporary: str) -> tuple[Path, str, str, str, str]:
        repo = Path(temporary) / "gcr4-bridge"
        bundle = Path(temporary) / "gcr4-source.bundle"
        bundled = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPO.as_posix()}",
                "-C",
                str(REPO),
                "bundle",
                "create",
                str(bundle),
                gcr4ctl.BRANCH,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, bundled.returncode, bundled.stdout + bundled.stderr)
        cloned = subprocess.run(
            ["git", "clone", "-b", gcr4ctl.BRANCH, str(bundle), str(repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, cloned.returncode, cloned.stdout + cloned.stderr)
        self.git(repo, "config", "user.email", "gcr4-bridge@example.test")
        self.git(repo, "config", "user.name", "GCR4 Bridge Fixture")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-B", gcr4ctl.BRANCH, gcr4ctl.APPROVAL_COMMIT)
        self.assertEqual(
            "",
            self.git(
                repo,
                "diff",
                "--name-only",
                f"{gcr4ctl.GCR3_REVIEWED_STATE_COMMIT}..{gcr4ctl.APPROVAL_COMMIT}",
                "--",
                gcr4ctl.GCR3_STATE_PATH,
                gcr4ctl.BACKLOG_PATH,
            ),
        )
        frozen = subprocess.run(
            ["git", "show", f"{gcr4ctl.GCR3_REVIEWED_STATE_COMMIT}:{gcr4ctl.GCR3_STATE_PATH}"],
            cwd=repo,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(gcr4ctl.GCR3_STATE_SHA256, gcr4ctl.sha256(frozen))
        self.assertEqual(frozen, (repo / gcr4ctl.GCR3_STATE_PATH).read_bytes())

        implementation_paths = [
            gcr4ctl.GCR3_SUCCESSOR_SCHEMA_PATH,
            "quality-scope.json",
            "tests/foundation/test_gcr3ctl.py",
            "tests/foundation/test_gcr4ctl.py",
            "tools/gcr3ctl.py",
            "tools/gcr4ctl.py",
        ]
        for relative in implementation_paths:
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        self.git(repo, "add", "--", *implementation_paths)
        self.git(repo, "commit", "-m", "fixture: implement exact GCR-0004 B00")
        candidate = self.git(repo, "rev-parse", "HEAD")
        self.assertNotEqual(gcr4ctl.APPROVAL_COMMIT, candidate)

        for relative in (gcr4ctl.TRIGGER_PATH, gcr4ctl.GCR3_LEDGER_PATH):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        self.assertEqual(gcr4ctl.TRIGGER_SHA256, gcr4ctl.sha256((repo / gcr4ctl.TRIGGER_PATH).read_bytes()))
        self.assertEqual(
            gcr4ctl.GCR3_LEDGER_SHA256,
            gcr4ctl.sha256((repo / gcr4ctl.GCR3_LEDGER_PATH).read_bytes()),
        )

        packet = json.loads((repo / gcr4ctl.PACKET_PATH).read_bytes())
        changed = gcr4ctl.changed_paths(repo, gcr4ctl.APPROVAL_COMMIT, candidate)
        evidence_relative = gcr4ctl.evidence_path("R01")
        self.write_json(
            repo,
            evidence_relative,
            {
                "schemaVersion": "4.0-control-recovery-evidence",
                "documentType": "governance-control-recovery-bootstrap-evidence",
                "controlRecoveryId": gcr4ctl.GCR_ID,
                "bootstrapUnit": gcr4ctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "commit": candidate,
                "baseCommit": gcr4ctl.APPROVAL_COMMIT,
                "branch": gcr4ctl.BRANCH,
                "triggerWitness": gcr4ctl.trigger_witness(),
                "adverseLedger": gcr4ctl.adverse_ledger_reference(),
                "changedFiles": changed,
                "checks": [
                    {
                        "id": "exact-real-git-bridge",
                        "command": "fixture exact real-Git GCR-0004 bridge lifecycle",
                        "exitCode": 0,
                        "result": "passed",
                    }
                ],
                "acceptanceCriteria": [
                    {
                        "index": index,
                        "statement": statement,
                        "evidence": ["Exercised by the disposable exact-authority lifecycle."],
                    }
                    for index, statement in enumerate(packet["acceptanceCriteria"], start=1)
                ],
                "findingClosures": [],
                "unverifiedItems": [],
                "verificationSelection": {
                    "riskAnalysis": "Exact authority, review projection, durable bridge, and successor-reader risk.",
                    "selectedChecks": ["exact-real-git-bridge"],
                    "deferredChecks": ["Full repository qualification remains at the Wave boundary."],
                },
            },
        )
        self.run_python(
            repo,
            "tools/gcr4ctl.py",
            "--repo",
            ".",
            "submit",
            gcr4ctl.GCR_ID,
            "--agent",
            gcr4ctl.ACTOR,
            "--approval-commit",
            gcr4ctl.APPROVAL_COMMIT,
            "--implementation-commit",
            candidate,
            "--evidence",
            evidence_relative,
        )
        self.git(repo, "add", "--", evidence_relative, gcr4ctl.STATE_PATH)
        self.git(repo, "commit", "-m", "fixture: freeze exact GCR-0004 R01")
        reviewed_state = self.git(repo, "rev-parse", "HEAD")
        frozen_state = json.loads((repo / gcr4ctl.STATE_PATH).read_bytes())
        submission = frozen_state["currentSubmission"]
        review_relative = gcr4ctl.review_path("R01")
        self.write_json(
            repo,
            review_relative,
            {
                "schemaVersion": "4.0-control-recovery-review",
                "documentType": "governance-control-recovery-bootstrap-review",
                "controlRecoveryId": gcr4ctl.GCR_ID,
                "bootstrapUnit": gcr4ctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "candidateCommit": candidate,
                "reviewedStateCommit": reviewed_state,
                "reviewer": "independent-gcr4-bridge-fixture-reviewer",
                "result": "approved",
                "evidence": submission["evidence"],
                "findings": [],
                "closures": [],
                "notes": "Independent disposable exact-authority approval.",
            },
        )
        self.run_python(
            repo,
            "tools/gcr4ctl.py",
            "--repo",
            ".",
            "review",
            gcr4ctl.GCR_ID,
            "--reviewer",
            "independent-gcr4-bridge-fixture-reviewer",
            "--from",
            review_relative,
        )
        self.git(repo, "add", "--", review_relative, gcr4ctl.STATE_PATH)
        self.git(repo, "commit", "-m", "fixture: independently approve exact GCR-0004 R01")
        approved_state = self.git(repo, "rev-parse", "HEAD")
        approved_document = json.loads((repo / gcr4ctl.STATE_PATH).read_bytes())
        self.assertEqual("APPROVED", approved_document["status"])

        application_relative = gcr4ctl.APPLICATION_EVIDENCE_PATH
        self.write_json(
            repo,
            application_relative,
            {
                "schemaVersion": "4.0-control-recovery-application-evidence",
                "documentType": "governance-control-recovery-review-transition-evidence",
                "controlRecoveryId": gcr4ctl.GCR_ID,
                "bootstrapUnit": gcr4ctl.BOOTSTRAP_ID,
                "approvedStateCommit": approved_state,
                "reviewedStateCommit": gcr4ctl.GCR3_REVIEWED_STATE_COMMIT,
                "triggerWitness": gcr4ctl.trigger_witness(),
                "adverseLedger": {
                    "path": gcr4ctl.GCR3_LEDGER_PATH,
                    "sha256": gcr4ctl.GCR3_LEDGER_SHA256,
                    "bytePreserved": True,
                },
                "predecessorStateSha256": gcr4ctl.GCR3_STATE_SHA256,
                "successorStatus": "CHANGES_REQUESTED",
                "controlRevision": 9,
                "expectedChangedFiles": [gcr4ctl.GCR3_LEDGER_PATH, gcr4ctl.GCR3_STATE_PATH],
                "checks": [
                    {
                        "id": "application-preflight",
                        "command": "fixture exact GCR-0004 application preflight",
                        "exitCode": 0,
                        "result": "passed",
                    }
                ],
                "unverifiedItems": [],
            },
        )
        self.git(repo, "add", "--", application_relative)
        self.git(repo, "commit", "-m", "fixture: bind exact GCR-0004 application evidence")
        application_commit = self.git(repo, "rev-parse", "HEAD")
        applied = self.run_python(
            repo,
            "tools/gcr4ctl.py",
            "--repo",
            ".",
            "apply",
            gcr4ctl.GCR_ID,
            "--agent",
            gcr4ctl.ACTOR,
            "--approved-state-commit",
            approved_state,
            "--evidence",
            application_relative,
        )
        self.assertIn("Prepared exact GCR-0003 R01 CHANGES_REQUESTED projection", applied.stdout)
        recovered = self.run_python(
            repo,
            "tools/gcr4ctl.py",
            "--repo",
            ".",
            "recover",
            gcr4ctl.GCR_ID,
            "--agent",
            gcr4ctl.ACTOR,
        )
        self.assertIn("ABSENT", recovered.stdout)
        self.git(repo, "add", "--", gcr4ctl.GCR3_LEDGER_PATH, gcr4ctl.GCR3_STATE_PATH)
        self.git(repo, "commit", "-m", "fixture: finalize exact GCR-0004 bridge pair")
        finalization = self.git(repo, "rev-parse", "HEAD")
        self.assertEqual(application_commit, self.git(repo, "rev-parse", f"{finalization}^"))
        self.assertEqual(
            [f"A\t{gcr4ctl.GCR3_LEDGER_PATH}", f"M\t{gcr4ctl.GCR3_STATE_PATH}"],
            self.git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", finalization).splitlines(),
        )
        self.run_python(repo, "tools/gcr4ctl.py", "--repo", ".", "validate", gcr4ctl.GCR_ID)
        self.run_python(repo, "tools/gcr3ctl.py", "--repo", ".", "validate", gcr3ctl.GCR_ID)
        return repo, reviewed_state, approved_state, application_commit, finalization

    def test_runtime_schema_selection_is_exactly_versioned(self) -> None:
        with patch.object(gcr3ctl, "validate_schema") as validate:
            gcr3ctl.validate_runtime(
                REPO,
                {"schemaVersion": "3.1-control-recovery-state"},
                "successor",
            )
            validate.assert_called_once_with(
                REPO,
                {"schemaVersion": "3.1-control-recovery-state"},
                gcr3ctl.SUCCESSOR_RUNTIME_SCHEMA_PATH,
                "successor",
            )
        with patch.object(gcr3ctl, "validate_schema") as validate:
            gcr3ctl.validate_runtime(
                REPO,
                {"schemaVersion": "3.0-control-recovery-state"},
                "frozen",
            )
            validate.assert_called_once_with(
                REPO,
                {"schemaVersion": "3.0-control-recovery-state"},
                gcr3ctl.RUNTIME_SCHEMA_PATH,
                "frozen",
            )

    def test_bridge_only_lineage_path_cannot_change_after_finalization(self) -> None:
        finalization = "1" * 40
        candidate = "2" * 40
        bridge_only = "tools/gcr4ctl.py"
        with (
            patch.object(gcr3ctl, "validate_gcr4_bridge", return_value=finalization),
            patch.object(gcr3ctl, "changed_paths", return_value=[bridge_only]),
            patch.object(taskctl, "git_is_ancestor", return_value=True),
            patch.object(taskctl, "git_blob", side_effect=[b"changed", b"frozen"]),
            self.assertRaisesRegex(SystemExit, "bridge-only path changed"),
        ):
            gcr3ctl.exact_gcr4_lineage_paths(
                REPO,
                {"schemaVersion": "3.1-control-recovery-state"},
                candidate=candidate,
                original_patterns=["tools/gcr3ctl.py"],
            )
        with (
            patch.object(gcr3ctl, "validate_gcr4_bridge", return_value=finalization),
            patch.object(gcr3ctl, "changed_paths", return_value=[bridge_only]),
            patch.object(taskctl, "git_is_ancestor", return_value=True),
            patch.object(taskctl, "git_blob", side_effect=[b"frozen", b"frozen"]),
        ):
            self.assertEqual(
                {bridge_only},
                gcr3ctl.exact_gcr4_lineage_paths(
                    REPO,
                    {"schemaVersion": "3.1-control-recovery-state"},
                    candidate=candidate,
                    original_patterns=["tools/gcr3ctl.py"],
                ),
            )

    def test_r02_changed_files_exclude_only_authenticated_bridge_lineage(self) -> None:
        candidate = "2" * 40
        base = "3" * 40
        packet = {
            "acceptanceCriteria": ["criterion"],
            "bootstrapUnit": {"authorizedPaths": ["tools/gcr3ctl.py"]},
        }
        document = {
            "controlRecoveryId": gcr3ctl.GCR_ID,
            "bootstrapUnit": gcr3ctl.BOOTSTRAP_ID,
            "attemptId": "R02",
            "commit": candidate,
            "baseCommit": base,
            "branch": gcr3ctl.BRANCH,
            "triggerWitness": gcr3ctl.trigger_witness(),
            "changedFiles": ["tools/gcr3ctl.py"],
            "acceptanceCriteria": [{"index": 1, "statement": "criterion", "evidence": ["proved"]}],
            "findingClosures": [],
            "unverifiedItems": [],
            "checks": [{"id": "focused", "exitCode": 0, "result": "passed"}],
            "verificationSelection": {"selectedChecks": ["focused"]},
        }
        with (
            patch.object(gcr3ctl, "validate_runtime"),
            patch.object(
                gcr3ctl,
                "changed_paths",
                return_value=["tools/gcr3ctl.py", "tools/gcr4ctl.py"],
            ),
            patch.object(
                gcr3ctl,
                "exact_gcr4_lineage_paths",
                return_value={"tools/gcr4ctl.py"},
            ),
        ):
            gcr3ctl.validate_evidence_document(
                REPO,
                packet,
                gcr3ctl.evidence_path("R02"),
                document,
                candidate,
                base,
                "R02",
                {},
                bridge_state={"schemaVersion": "3.1-control-recovery-state"},
            )
            document["changedFiles"] = ["tools/gcr3ctl.py", "tools/gcr4ctl.py"]
            with self.assertRaisesRegex(SystemExit, "evidence identity, scope"):
                gcr3ctl.validate_evidence_document(
                    REPO,
                    packet,
                    gcr3ctl.evidence_path("R02"),
                    document,
                    candidate,
                    base,
                    "R02",
                    {},
                    bridge_state={"schemaVersion": "3.1-control-recovery-state"},
                )

    def test_real_git_gcr4_bridge_to_strict_descendant_gcr3_r02_and_authority_denials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (
                bridge_repo,
                _gcr4_reviewed_state,
                gcr4_approved_state,
                _application_commit,
                bridge_finalization,
            ) = self.create_exact_gcr4_bridge(temporary)
            self.assertTrue(
                taskctl.git_is_ancestor(
                    bridge_repo,
                    gcr4ctl.GCR3_REVIEWED_STATE_COMMIT,
                    bridge_finalization,
                )
            )

            r02_repo = Path(temporary) / "gcr3-r02"
            cloned = subprocess.run(
                [
                    "git",
                    "clone",
                    "--no-local",
                    "-b",
                    gcr3ctl.BRANCH,
                    str(bridge_repo),
                    str(r02_repo),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, cloned.returncode, cloned.stdout + cloned.stderr)
            self.git(r02_repo, "config", "user.email", "gcr3-r02@example.test")
            self.git(r02_repo, "config", "user.name", "GCR3 R02 Fixture")
            trigger = r02_repo / gcr3ctl.TRIGGER_PATH
            trigger.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / gcr3ctl.TRIGGER_PATH, trigger)
            remediation_path = r02_repo / "tests/foundation/test_gcr3ctl.py"
            remediation_path.write_bytes(
                remediation_path.read_bytes() + b"\n# fixture strict-descendant GCR-0003 R02 remediation\n"
            )
            self.git(r02_repo, "add", "--", "tests/foundation/test_gcr3ctl.py")
            self.git(r02_repo, "commit", "-m", "fixture: strict-descendant GCR-0003 R02 remediation")
            r02_candidate = self.git(r02_repo, "rev-parse", "HEAD")
            r01_candidate = "a0988d8d9cfde8cde5cc9cf148f9b37ae8e13873"
            self.assertNotEqual(r01_candidate, r02_candidate)
            self.assertTrue(taskctl.git_is_ancestor(r02_repo, r01_candidate, r02_candidate))

            gcr3_packet = json.loads((r02_repo / gcr3ctl.PACKET_PATH).read_bytes())
            patterns = [str(item) for item in (gcr3_packet.get("bootstrapUnit") or {}).get("authorizedPaths", [])]
            actual = gcr3ctl.changed_paths(r02_repo, gcr3ctl.APPROVAL_COMMIT, r02_candidate)
            bridge_paths = set(gcr3ctl.changed_paths(r02_repo, gcr3ctl.APPROVAL_COMMIT, bridge_finalization))
            bridge_only = {relative for relative in bridge_paths if not gcr3ctl.path_authorized(relative, patterns)}
            effective_actual = [relative for relative in actual if relative not in bridge_only]
            bridged_state = json.loads((r02_repo / gcr3ctl.STATE_PATH).read_bytes())
            open_findings = gcr3ctl.open_findings(bridged_state)
            r02_evidence = gcr3ctl.evidence_path("R02")
            self.write_json(
                r02_repo,
                r02_evidence,
                {
                    "schemaVersion": "3.0-control-recovery-evidence",
                    "documentType": "governance-control-recovery-bootstrap-evidence",
                    "controlRecoveryId": gcr3ctl.GCR_ID,
                    "bootstrapUnit": gcr3ctl.BOOTSTRAP_ID,
                    "attemptId": "R02",
                    "commit": r02_candidate,
                    "baseCommit": gcr3ctl.APPROVAL_COMMIT,
                    "branch": gcr3ctl.BRANCH,
                    "triggerWitness": gcr3ctl.trigger_witness(),
                    "changedFiles": effective_actual,
                    "checks": [
                        {
                            "id": "real-git-gcr4-lineage",
                            "command": "fixture real-Git GCR-0004 lineage and GCR-0003 R02 eligibility",
                            "exitCode": 0,
                            "result": "passed",
                        }
                    ],
                    "acceptanceCriteria": [
                        {
                            "index": index,
                            "statement": statement,
                            "evidence": ["Exercised through the exact finalized GCR-0004 bridge."],
                        }
                        for index, statement in enumerate(gcr3_packet["acceptanceCriteria"], start=1)
                    ],
                    "findingClosures": [
                        {
                            "findingId": finding_id,
                            "disposition": "fixed",
                            "evidence": "The strict-descendant fixture candidate closes the exact R01 finding.",
                        }
                        for finding_id in sorted(open_findings)
                    ],
                    "unverifiedItems": [],
                    "verificationSelection": {
                        "riskAnalysis": (
                            "Exact successor schema, bridge authority, history, lineage, and remediation scope."
                        ),
                        "selectedChecks": ["real-git-gcr4-lineage"],
                        "deferredChecks": ["Full repository qualification remains at the Wave boundary."],
                    },
                },
            )
            self.run_python(
                r02_repo,
                "tools/gcr3ctl.py",
                "--repo",
                ".",
                "resubmit",
                gcr3ctl.GCR_ID,
                "--agent",
                gcr3ctl.ACTOR,
                "--implementation-commit",
                r02_candidate,
                "--evidence",
                r02_evidence,
            )
            submitted = json.loads((r02_repo / gcr3ctl.STATE_PATH).read_bytes())
            self.assertEqual("REVIEW", submitted["status"])
            self.assertEqual("R02", submitted["currentSubmission"]["attemptId"])
            self.assertEqual(r02_candidate, submitted["currentSubmission"]["candidateCommit"])
            self.assertEqual(bridged_state["attempts"], submitted["attempts"])

            watched = [
                gcr3ctl.BACKLOG_PATH,
                gcr3ctl.STATE_PATH,
                gcr3ctl.TRIGGER_PATH,
                gcr4ctl.GCR3_LEDGER_PATH,
                gcr4ctl.PACKET_PATH,
                "planning/governance-control-recovery/GCR-0004.review-R01.json",
                gcr4ctl.APPROVAL_PATH,
                gcr4ctl.STATE_PATH,
                gcr4ctl.APPLICATION_EVIDENCE_PATH,
                gcr4ctl.GCR3_SUCCESSOR_SCHEMA_PATH,
                "tools/gcr4ctl.py",
            ]

            def snapshot(repo: Path) -> tuple[str, str, dict[str, bytes | None]]:
                return (
                    self.git(repo, "rev-parse", "HEAD"),
                    self.git(repo, "status", "--short"),
                    {
                        relative: ((repo / relative).read_bytes() if (repo / relative).is_file() else None)
                        for relative in watched
                    },
                )

            scenarios = (
                "missing-packet",
                "substituted-packet-review",
                "substituted-approval",
                "forked-b00",
                "adverse-b00",
                "stale-application-evidence",
                "substituted-application-evidence",
                "post-finalization-mutated-ledger",
            )
            for scenario in scenarios:
                with self.subTest(scenario=scenario):
                    variant = Path(temporary) / f"denial-{scenario}"
                    cloned = subprocess.run(
                        [
                            "git",
                            "clone",
                            "--no-local",
                            "-b",
                            gcr3ctl.BRANCH,
                            str(bridge_repo),
                            str(variant),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(0, cloned.returncode, cloned.stdout + cloned.stderr)
                    self.git(variant, "config", "user.email", "gcr4-denial@example.test")
                    self.git(variant, "config", "user.name", "GCR4 Denial Fixture")
                    variant_trigger = variant / gcr3ctl.TRIGGER_PATH
                    variant_trigger.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(REPO / gcr3ctl.TRIGGER_PATH, variant_trigger)

                    if scenario == "missing-packet":
                        self.git(variant, "rm", "--", gcr4ctl.PACKET_PATH)
                    elif scenario == "substituted-packet-review":
                        packet_review = variant / "planning/governance-control-recovery/GCR-0004.review-R01.json"
                        packet_review.write_bytes(packet_review.read_bytes() + b" ")
                        self.git(variant, "add", "--", packet_review.relative_to(variant).as_posix())
                    elif scenario == "substituted-approval":
                        approval = variant / gcr4ctl.APPROVAL_PATH
                        approval.write_bytes(approval.read_bytes() + b" ")
                        self.git(variant, "add", "--", gcr4ctl.APPROVAL_PATH)
                    elif scenario in {"forked-b00", "adverse-b00"}:
                        side_branch = f"fixture-{scenario}"
                        self.git(variant, "checkout", "-b", side_branch, gcr4_approved_state)
                        if scenario == "adverse-b00":
                            adverse_state = json.loads((variant / gcr4ctl.STATE_PATH).read_bytes())
                            adverse_state["status"] = "CHANGES_REQUESTED"
                            adverse_state["attempts"][-1]["review"]["result"] = "changes-requested"
                            self.write_json(variant, gcr4ctl.STATE_PATH, adverse_state)
                            self.git(variant, "add", "--", gcr4ctl.STATE_PATH)
                            self.git(variant, "commit", "-m", "fixture: adverse forked GCR-0004 state")
                        else:
                            self.git(variant, "commit", "--allow-empty", "-m", "fixture: fork GCR-0004 state")
                        side_commit = self.git(variant, "rev-parse", "HEAD")
                        self.git(variant, "checkout", gcr3ctl.BRANCH)
                        bridge_state = json.loads((variant / gcr3ctl.STATE_PATH).read_bytes())
                        bridge_state["reviewTransitionRecovery"]["approvedGcr4StateCommit"] = side_commit
                        self.write_json(variant, gcr3ctl.STATE_PATH, bridge_state)
                        self.git(variant, "add", "--", gcr3ctl.STATE_PATH)
                    elif scenario == "stale-application-evidence":
                        bridge_state = json.loads((variant / gcr3ctl.STATE_PATH).read_bytes())
                        bridge_state["reviewTransitionRecovery"]["applicationEvidence"]["commit"] = gcr4_approved_state
                        self.write_json(variant, gcr3ctl.STATE_PATH, bridge_state)
                        self.git(variant, "add", "--", gcr3ctl.STATE_PATH)
                    elif scenario == "substituted-application-evidence":
                        application = variant / gcr4ctl.APPLICATION_EVIDENCE_PATH
                        application.write_bytes(application.read_bytes() + b" ")
                        self.git(variant, "add", "--", gcr4ctl.APPLICATION_EVIDENCE_PATH)
                    else:
                        ledger = json.loads((variant / gcr4ctl.GCR3_LEDGER_PATH).read_bytes())
                        ledger["notes"] = "Post-finalization substitution is not authority."
                        self.write_json(variant, gcr4ctl.GCR3_LEDGER_PATH, ledger)
                        self.git(variant, "add", "--", gcr4ctl.GCR3_LEDGER_PATH)

                    self.git(variant, "commit", "-m", f"fixture: {scenario} bridge authority")
                    before = snapshot(variant)
                    denied = self.run_python(
                        variant,
                        "tools/gcr3ctl.py",
                        "--repo",
                        ".",
                        "validate",
                        gcr3ctl.GCR_ID,
                        expected=1,
                    )
                    self.assertTrue((denied.stdout + denied.stderr).strip())
                    self.assertEqual(before, snapshot(variant))

    def fixture(self, temporary: str) -> tuple[Path, str, str, dict]:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr3@example.test")
        self.git(repo, "config", "user.name", "GCR3 Test")
        self.git(repo, "config", "core.autocrlf", "false")
        self.git(repo, "checkout", "-b", gcr3ctl.BRANCH)
        shutil.copy2(REPO / ".gitignore", repo / ".gitignore")
        for relative in (gcr3ctl.RUNTIME_SCHEMA_PATH, gcr3ctl.TRANSACTION_SCHEMA_PATH):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        self.write_json(repo, gcr3ctl.APPROVAL_PATH, {"fixture": True})
        backlog = {
            "control_plane": {
                "revision": 9,
                "minimum_tool_revision": 9,
                "active_amendment": None,
                "recovery_holds": [{"id": "HOLD-W1-GRR-0002", "status": "ACTIVE"}],
                "control_generations": [],
            }
        }
        (repo / gcr3ctl.BACKLOG_PATH).write_text(yaml.safe_dump(backlog, sort_keys=False), encoding="utf-8")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "approval base")
        base = self.git(repo, "rev-parse", "HEAD")
        controller = repo / "tools/gcr3ctl.py"
        controller.parent.mkdir(parents=True, exist_ok=True)
        controller.write_text("# bounded GCR-0003 implementation\n", encoding="utf-8")
        self.git(repo, "add", "tools/gcr3ctl.py")
        self.git(repo, "commit", "-m", "implementation candidate")
        candidate = self.git(repo, "rev-parse", "HEAD")
        trigger = repo / gcr3ctl.TRIGGER_PATH
        trigger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcr3ctl.TRIGGER_PATH, trigger)
        packet = {
            "activationBoundary": {"controlRevision": 9},
            "acceptanceCriteria": ["criterion"],
            "bootstrapUnit": {"authorizedPaths": ["tools/gcr3ctl.py"]},
        }
        return repo, base, candidate, packet

    def evidence(self, repo: Path, base: str, candidate: str, packet: dict) -> str:
        relative = gcr3ctl.evidence_path("R01")
        self.write_json(
            repo,
            relative,
            {
                "schemaVersion": "3.0-control-recovery-evidence",
                "documentType": "governance-control-recovery-bootstrap-evidence",
                "controlRecoveryId": gcr3ctl.GCR_ID,
                "bootstrapUnit": gcr3ctl.BOOTSTRAP_ID,
                "attemptId": "R01",
                "commit": candidate,
                "baseCommit": base,
                "branch": gcr3ctl.BRANCH,
                "triggerWitness": gcr3ctl.trigger_witness(),
                "changedFiles": ["tools/gcr3ctl.py"],
                "checks": [{"id": "focused", "command": "focused", "exitCode": 0, "result": "passed"}],
                "acceptanceCriteria": [
                    {"index": 1, "statement": packet["acceptanceCriteria"][0], "evidence": ["proved"]}
                ],
                "findingClosures": [],
                "unverifiedItems": [],
                "verificationSelection": {
                    "riskAnalysis": "Exact controller state and transaction risk.",
                    "selectedChecks": ["focused"],
                    "deferredChecks": ["Wave qualification"],
                },
            },
        )
        return relative

    def submitted_fixture(self, temporary: str) -> tuple[Path, dict, str, str, str]:
        repo, base, candidate, packet = self.fixture(temporary)
        evidence = self.evidence(repo, base, candidate, packet)
        args = argparse.Namespace(
            repo=repo,
            agent=gcr3ctl.ACTOR,
            approval_commit=base,
            implementation_commit=candidate,
            evidence=evidence,
        )
        with patch.object(gcr3ctl, "load_authority", return_value=({}, packet, base)):
            gcr3ctl.freeze_submission(args, remediation=False)
        return repo, packet, base, candidate, evidence

    def recovery_fixture(
        self,
        temporary: str,
        *,
        coherent_substitution: bool = False,
        ledger_state_mismatch: str | None = None,
    ) -> tuple[Path, bytes, bytes, bytes, bytes, dict, dict, tuple[dict, dict, str]]:
        repo = Path(temporary)
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "gcr3@example.test")
        self.git(repo, "config", "user.name", "GCR3 Test")
        self.git(repo, "config", "core.autocrlf", "true")
        self.git(repo, "checkout", "-b", gcr3ctl.BRANCH)
        for relative in (
            ".gitignore",
            ".gitattributes",
            gcr3ctl.RUNTIME_SCHEMA_PATH,
            gcr3ctl.TRANSACTION_SCHEMA_PATH,
            gcr3ctl.BACKLOG_PATH,
        ):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, destination)
        approval_path = repo / gcr3ctl.APPROVAL_PATH
        approval_path.parent.mkdir(parents=True, exist_ok=True)
        approval_path.write_bytes(b'{"fixture": true}\n')
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "approval base")
        approval_base = self.git(repo, "rev-parse", "HEAD")
        candidate_path = repo / "tools/gcr3ctl.py"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_bytes(b"# synthetic candidate\n")
        self.git(repo, "add", "tools/gcr3ctl.py")
        self.git(repo, "commit", "-m", "synthetic candidate")
        candidate = self.git(repo, "rev-parse", "HEAD")
        # Preserve the release-authoritative worktree bytes while Git retains
        # the normalized LF blob. Git considers this CRLF worktree clean.
        shutil.copy2(REPO / gcr3ctl.BACKLOG_PATH, repo / gcr3ctl.BACKLOG_PATH)
        self.assertEqual("", self.git(repo, "status", "--short"))
        state_path = repo / gcr3ctl.STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        attempt_id = "R01"
        evidence_relative = gcr3ctl.evidence_path(attempt_id)
        packet = {
            "acceptanceCriteria": ["Synthetic recovery fixture criterion."],
            "bootstrapUnit": {"authorizedPaths": ["tools/gcr3ctl.py"]},
        }
        evidence_document = {
            "schemaVersion": "3.0-control-recovery-evidence",
            "documentType": "governance-control-recovery-bootstrap-evidence",
            "controlRecoveryId": gcr3ctl.GCR_ID,
            "bootstrapUnit": gcr3ctl.BOOTSTRAP_ID,
            "attemptId": attempt_id,
            "commit": candidate,
            "baseCommit": approval_base,
            "branch": gcr3ctl.BRANCH,
            "triggerWitness": gcr3ctl.trigger_witness(),
            "changedFiles": ["tools/gcr3ctl.py"],
            "checks": [{"id": "fixture", "command": "fixture", "exitCode": 0, "result": "passed"}],
            "acceptanceCriteria": [
                {
                    "index": 1,
                    "statement": "Synthetic recovery fixture criterion.",
                    "evidence": ["Exercised by the synthetic recovery fixture."],
                }
            ],
            "findingClosures": [],
            "unverifiedItems": [],
            "verificationSelection": {
                "riskAnalysis": "Synthetic recovery fixture scope.",
                "selectedChecks": ["fixture"],
                "deferredChecks": [],
            },
        }
        if ledger_state_mismatch == "candidate-evidence-scope":
            evidence_document["changedFiles"] = ["tools/unapproved.py"]
        evidence_payload = (json.dumps(evidence_document, indent=2) + "\n").encode()
        evidence_path = repo / evidence_relative
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(evidence_payload)
        submission: dict[str, Any] = {
            "attemptId": attempt_id,
            "submittedBy": gcr3ctl.ACTOR,
            "candidateCommit": candidate,
            "baseCommit": approval_base,
            "branch": gcr3ctl.BRANCH,
            "evidence": {
                "path": evidence_relative,
                "sha256": gcr3ctl.sha256(evidence_payload),
                "commit": candidate,
            },
            "submittedAt": "2026-08-25T00:00:00+00:00",
            "priorAttemptId": None,
            "openFindingIds": [],
            "rootCauseAnalysis": None,
        }
        state: dict[str, Any] = {
            "schemaVersion": "3.0-control-recovery-state",
            "documentType": "governance-control-recovery-bootstrap-state",
            "controlRecoveryId": gcr3ctl.GCR_ID,
            "bootstrapUnit": gcr3ctl.BOOTSTRAP_ID,
            "status": "REVIEW",
            "approval": {
                "path": gcr3ctl.APPROVAL_PATH,
                "sha256": gcr3ctl.sha256(approval_path.read_bytes()),
                "commit": approval_base,
            },
            "triggerWitness": gcr3ctl.trigger_witness(),
            "attempts": [],
            "currentSubmission": submission,
            "adoption": None,
        }
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        self.git(repo, "add", evidence_relative, gcr3ctl.STATE_PATH)
        self.git(repo, "commit", "-m", "freeze synthetic R01 submission")
        reviewed_state = self.git(repo, "rev-parse", "HEAD")
        authority: tuple[dict, dict, str] = ({}, packet, approval_base)
        gcr3ctl.validate_history(repo, state, authority[1])
        closures: list[dict[str, str]] = []
        ledger_relative = gcr3ctl.review_path(attempt_id)
        ledger = {
            "schemaVersion": "3.0-control-recovery-review",
            "documentType": "governance-control-recovery-bootstrap-review",
            "controlRecoveryId": gcr3ctl.GCR_ID,
            "bootstrapUnit": gcr3ctl.BOOTSTRAP_ID,
            "attemptId": attempt_id,
            "candidateCommit": candidate,
            "reviewedStateCommit": reviewed_state,
            "reviewer": "independent-test-reviewer",
            "result": "approved",
            "evidence": submission["evidence"],
            "findings": [],
            "closures": closures,
            "notes": "Synthetic canonical approval for recovery tests.",
        }
        fixture_finding = {
            "id": "GCR-0003.B00-R01-F99",
            "severity": "high",
            "blocking": True,
            "criterionIndex": 8,
            "title": "Synthetic mismatched finding",
            "reproduction": "Synthetic mismatch",
            "requiredRemediation": "Reconcile the immutable ledger and state.",
        }
        if ledger_state_mismatch == "adverse-ledger-approved-state":
            ledger["result"] = "changes-requested"
            ledger["findings"] = [fixture_finding]
        elif ledger_state_mismatch == "evidence":
            ledger["evidence"] = {**submission["evidence"], "commit": "f" * 40}
        elif ledger_state_mismatch == "reviewer":
            ledger["reviewer"] = "alternate-independent-test-reviewer"
        elif ledger_state_mismatch == "candidate":
            ledger["candidateCommit"] = "f" * 40
        ledger_payload = (json.dumps(ledger, indent=2) + "\n").encode()
        ledger_path = repo / ledger_relative
        ledger_path.write_bytes(ledger_payload)
        attempt: dict[str, Any] = {
            "submission": submission,
            "review": {
                "reviewer": "independent-test-reviewer",
                "result": "approved",
                "reviewedAt": "2026-08-25T00:00:00+00:00",
                "reviewedStateCommit": reviewed_state,
                "notes": "Synthetic canonical approval for recovery tests.",
            },
            "ledger": {
                "path": ledger_relative,
                "sha256": gcr3ctl.sha256(ledger_payload),
                "commit": reviewed_state,
            },
            "findings": [],
            "closures": closures,
        }
        if ledger_state_mismatch == "approved-ledger-adverse-state":
            attempt["review"]["result"] = "changes-requested"
        elif ledger_state_mismatch == "findings":
            attempt["findings"] = [fixture_finding]
        elif ledger_state_mismatch == "closures":
            attempt["closures"] = [
                {"findingId": "synthetic-closed-item", "disposition": "fixed", "evidence": "mismatch"}
            ]
        state["attempts"].append(attempt)
        state["status"] = "APPROVED"
        state["currentSubmission"] = None
        state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
        self.git(repo, "add", ledger_relative, gcr3ctl.STATE_PATH)
        self.git(repo, "commit", "-m", "approve synthetic R01")
        approved_state = self.git(repo, "rev-parse", "HEAD")
        if coherent_substitution:
            state["approval"]["sha256"] = "f" * 64
            state_path.write_bytes((json.dumps(state, indent=2) + "\n").encode())
            self.git(repo, "add", gcr3ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "substitute approved authority")
            approved_state = self.git(repo, "rev-parse", "HEAD")
        evidence = {
            "schemaVersion": "3.0-control-recovery-adoption-evidence",
            "documentType": "governance-control-recovery-adoption-evidence",
            "controlRecoveryId": gcr3ctl.GCR_ID,
            "bootstrapUnit": gcr3ctl.BOOTSTRAP_ID,
            "reviewedStateCommit": approved_state,
            "triggerWitness": gcr3ctl.trigger_witness(),
            "predecessorRevision": 9,
            "successorRevision": 10,
            "supportedControlCeiling": 11,
            "expectedChangedFiles": [gcr3ctl.BACKLOG_PATH, gcr3ctl.STATE_PATH],
            "checks": [{"id": "recovery", "command": "recovery", "exitCode": 0, "result": "passed"}],
            "unverifiedItems": [],
        }
        adoption_evidence_path = repo / gcr3ctl.ADOPTION_EVIDENCE_PATH
        adoption_evidence_path.parent.mkdir(parents=True, exist_ok=True)
        adoption_evidence_path.write_bytes((json.dumps(evidence, indent=2) + "\n").encode())
        self.git(repo, "add", gcr3ctl.ADOPTION_EVIDENCE_PATH)
        self.git(repo, "commit", "-m", "adoption evidence")
        evidence_commit = self.git(repo, "rev-parse", "HEAD")
        trigger = repo / gcr3ctl.TRIGGER_PATH
        trigger.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / gcr3ctl.TRIGGER_PATH, trigger)
        predecessor_backlog = (repo / gcr3ctl.BACKLOG_PATH).read_bytes()
        predecessor_state = state_path.read_bytes()
        self.assertEqual(gcr3ctl.BACKLOG_SHA256, gcr3ctl.sha256(predecessor_backlog))
        self.assertEqual(
            gcr3ctl.sha256(predecessor_backlog),
            gcr3ctl.sha256(taskctl.git_blob(repo, approved_state, gcr3ctl.BACKLOG_PATH) or b""),
        )
        successor_backlog_document = yaml.safe_load(predecessor_backlog)
        control = successor_backlog_document["control_plane"]
        control["revision"] = 10
        control["minimum_tool_revision"] = 10
        control["control_generations"].append(
            {
                "id": gcr3ctl.GCR_ID,
                "bootstrap_id": gcr3ctl.BOOTSTRAP_ID,
                "hold_id": "HOLD-W1-GRR-0002",
                "predecessor_revision": 9,
                "successor_revision": 10,
                "supported_control_ceiling": 11,
                "approval_reference": {
                    "path": gcr3ctl.APPROVAL_PATH,
                    "sha256": gcr3ctl.sha256((repo / gcr3ctl.APPROVAL_PATH).read_bytes()),
                    "introduction_commit": state["approval"]["commit"],
                },
                "review_reference": {
                    "path": ledger_relative,
                    "sha256": gcr3ctl.sha256(ledger_payload),
                    "reviewed_state_commit": reviewed_state,
                    "approved_state_commit": approved_state,
                },
                "adopted_by": gcr3ctl.ACTOR,
                "adopted_at": "2026-08-25T00:00:00+00:00",
            }
        )
        successor_backlog = yaml.safe_dump(successor_backlog_document, sort_keys=False).encode()
        successor_state_document = copy.deepcopy(state)
        successor_state_document["status"] = "ADOPTION_FINALIZATION"
        successor_state_document["adoption"] = {
            "adoptedBy": gcr3ctl.ACTOR,
            "adoptedAt": "2026-08-25T00:00:00+00:00",
            "predecessorRevision": 9,
            "successorRevision": 10,
            "supportedControlCeiling": 11,
            "reviewedStateCommit": approved_state,
            "evidence": {
                "path": gcr3ctl.ADOPTION_EVIDENCE_PATH,
                "sha256": gcr3ctl.sha256(adoption_evidence_path.read_bytes()),
                "commit": evidence_commit,
            },
        }
        successor_state = (json.dumps(successor_state_document, indent=2) + "\n").encode()
        transaction = gcr3ctl.transaction_document(
            predecessor_backlog=predecessor_backlog,
            predecessor_state=predecessor_state,
            successor_backlog=successor_backlog,
            successor_state=successor_state,
            reviewed_state=approved_state,
            evidence_commit=evidence_commit,
        )
        anchor = gcr3ctl.recovery_anchor_document(
            transaction=transaction,
            predecessor_backlog=predecessor_backlog,
            predecessor_state=predecessor_state,
        )
        if not coherent_substitution and ledger_state_mismatch is None:
            gcr3ctl.validate_recovery_anchor(repo, anchor, authority)
        gcr3ctl.validate_successor_pair(repo, successor_backlog, successor_state)
        return (
            repo,
            predecessor_backlog,
            predecessor_state,
            successor_backlog,
            successor_state,
            transaction,
            anchor,
            authority,
        )

    def test_repository_authority_is_valid_at_revision_nine(self) -> None:
        approval, packet, base = gcr3ctl.load_authority(REPO)
        self.assertEqual("APPROVED", approval["status"])
        self.assertEqual(gcr3ctl.GCR_ID, packet["controlRecoveryId"])
        self.assertEqual("d6ec319a6d9d3ccbc5fc195e91d8ee6be594ef3c", base)
        _payload, backlog = gcr3ctl.current_boundary(REPO, packet, revision=9)
        self.assertEqual(9, backlog["control_plane"]["revision"])

    def test_root_cause_analysis_is_not_required_before_a_third_submission(self) -> None:
        self.assertIsNone(gcr3ctl.required_root_cause(0))
        self.assertIsNone(gcr3ctl.required_root_cause(1))
        self.assertEqual("current root cause", gcr3ctl.required_root_cause(2, "current root cause"))
        with self.assertRaisesRegex(SystemExit, "require a normalized root-cause analysis"):
            gcr3ctl.required_root_cause(2)

    def test_v3_schemas_remain_immutable_and_v4_is_exactly_ten_to_eleven(self) -> None:
        packet_schema = json.loads(
            (REPO / "planning/governance-recovery-requests/governance-recovery-supplement.v4.schema.json").read_text(
                encoding="utf-8"
            )
        )
        approval_schema = json.loads(
            (
                REPO / "planning/governance-recovery-requests/governance-recovery-supplement-approval.v4.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(packet_schema)
        Draft202012Validator.check_schema(approval_schema)
        transition = packet_schema["properties"]["controlTransition"]["properties"]
        self.assertEqual(10, transition["predecessorRevision"]["const"])
        self.assertEqual(11, transition["successorRevision"]["const"])
        self.assertEqual("GRR-0002.S02", packet_schema["properties"]["supplementId"]["const"])
        self.assertEqual("GRR-0002.B02", approval_schema["properties"]["supplementalBootstrapUnit"]["const"])
        self.assertEqual(
            "943c650120b32d3a2837e96c769f48c9c9afa4435ecb2fe1275c17d7f1cd1e7d",
            gcr3ctl.sha256(
                (
                    REPO / "planning/governance-recovery-requests/governance-recovery-supplement.v3.schema.json"
                ).read_bytes()
            ),
        )
        self.assertEqual(
            "9d3eaf942b6798a6dafc9d8fdbcc502c4068dc9d1b547b0be2e76b5b3b98052d",
            gcr3ctl.sha256(
                (
                    REPO
                    / "planning/governance-recovery-requests/governance-recovery-supplement-approval.v3.schema.json"
                ).read_bytes()
            ),
        )

    def test_submit_freezes_exact_real_git_candidate_and_witness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _packet, _base, candidate, evidence = self.submitted_fixture(temporary)
            state = json.loads((repo / gcr3ctl.STATE_PATH).read_text(encoding="utf-8"))
            self.assertEqual("REVIEW", state["status"])
            self.assertEqual(candidate, state["currentSubmission"]["candidateCommit"])
            self.assertEqual(gcr3ctl.trigger_witness(), state["triggerWitness"])
            before = (repo / gcr3ctl.STATE_PATH).read_bytes()
            extra = repo / "unrelated.tmp"
            extra.write_text("denied\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "untracked-path boundary"):
                gcr3ctl.require_workspace(repo, extra_untracked={evidence, gcr3ctl.STATE_PATH})
            self.assertEqual(before, (repo / gcr3ctl.STATE_PATH).read_bytes())

    def test_transaction_schema_rejects_crossed_canonical_bindings(self) -> None:
        predecessor_backlog = yaml.safe_dump({"control_plane": {"revision": 9}}).encode()
        predecessor_state = json.dumps({"status": "APPROVED"}).encode()
        successor_backlog = yaml.safe_dump({"control_plane": {"revision": 10}}).encode()
        successor_state = json.dumps({"status": "ADOPTION_FINALIZATION"}).encode()
        transaction = gcr3ctl.transaction_document(
            predecessor_backlog=predecessor_backlog,
            predecessor_state=predecessor_state,
            successor_backlog=successor_backlog,
            successor_state=successor_state,
            reviewed_state="1" * 40,
            evidence_commit="2" * 40,
        )
        gcr3ctl.validate_transaction(REPO, transaction)
        crossed = copy.deepcopy(transaction)
        crossed["predecessor"]["backlog"]["path"] = gcr3ctl.STATE_PATH
        with self.assertRaisesRegex(SystemExit, "schema validation failed"):
            gcr3ctl.validate_transaction(REPO, crossed)
        redirected = copy.deepcopy(transaction)
        redirected["paths"]["state"] = "planning/other.json"
        with self.assertRaisesRegex(SystemExit, "schema validation failed"):
            gcr3ctl.validate_transaction(REPO, redirected)

    def test_unpublished_transaction_restores_exact_predecessor_and_cleans_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (
                repo,
                predecessor_backlog,
                predecessor_state,
                _successor_backlog,
                _successor_state,
                _transaction,
                anchor,
                authority,
            ) = self.recovery_fixture(temporary)
            artifacts = gcr3ctl.transaction_artifacts(repo)
            with gcr3ctl.transaction_lock(repo, anchor=anchor, authority=authority):
                pass
            gcr3ctl.write_new_durable(artifacts[gcr3ctl.BACKLOG_NEXT_PATH], b"substituted\n")
            (repo / gcr3ctl.BACKLOG_PATH).write_bytes(b"partial\n")
            self.assertEqual("RESTORED_PREDECESSOR", gcr3ctl.recover_transaction(repo, authority))
            self.assertEqual(predecessor_backlog, (repo / gcr3ctl.BACKLOG_PATH).read_bytes())
            self.assertEqual(predecessor_state, (repo / gcr3ctl.STATE_PATH).read_bytes())
            self.assertEqual([], gcr3ctl.present_transaction_artifacts(repo))
            self.assertEqual("ABSENT", gcr3ctl.recover_transaction(repo, authority))

    def test_invalid_manifest_restores_but_stale_head_and_substituted_anchor_fail_closed(self) -> None:
        for scenario in ("invalid-manifest", "stale-head", "substituted-anchor"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                (
                    repo,
                    predecessor_backlog,
                    predecessor_state,
                    _successor_backlog,
                    _successor_state,
                    _transaction,
                    anchor,
                    authority,
                ) = self.recovery_fixture(temporary)
                artifacts = gcr3ctl.transaction_artifacts(repo)
                with gcr3ctl.transaction_lock(repo, anchor=anchor, authority=authority):
                    pass
                if scenario == "invalid-manifest":
                    gcr3ctl.write_new_durable(artifacts[gcr3ctl.TRANSACTION_PATH], b"not-json\n")
                elif scenario == "stale-head":
                    unrelated = repo / "unrelated.txt"
                    unrelated.write_text("new head\n", encoding="utf-8")
                    self.git(repo, "add", "unrelated.txt")
                    self.git(repo, "commit", "-m", "unrelated head")
                else:
                    changed = copy.deepcopy(anchor)
                    changed_state = json.dumps({"status": "APPROVED"}).encode()
                    changed["predecessorPayloads"]["stateBase64"] = base64.b64encode(changed_state).decode("ascii")
                    changed["predecessor"]["state"] = gcr3ctl.binding(
                        gcr3ctl.STATE_PATH, changed_state, json.loads(changed_state)
                    )
                    artifacts[gcr3ctl.LOCK_PATH].write_bytes((json.dumps(changed, indent=2) + "\n").encode())
                (repo / gcr3ctl.BACKLOG_PATH).write_bytes(b"partial backlog\n")
                (repo / gcr3ctl.STATE_PATH).write_bytes(b"partial state\n")
                before = {
                    path: (repo / path).read_bytes()
                    for path in (gcr3ctl.BACKLOG_PATH, gcr3ctl.STATE_PATH, gcr3ctl.LOCK_PATH)
                }
                if scenario == "invalid-manifest":
                    self.assertEqual("RESTORED_PREDECESSOR", gcr3ctl.recover_transaction(repo, authority))
                    self.assertEqual(predecessor_backlog, (repo / gcr3ctl.BACKLOG_PATH).read_bytes())
                    self.assertEqual(predecessor_state, (repo / gcr3ctl.STATE_PATH).read_bytes())
                    self.assertEqual([], gcr3ctl.present_transaction_artifacts(repo))
                else:
                    with self.assertRaisesRegex(SystemExit, "recovery anchor"):
                        gcr3ctl.recover_transaction(repo, authority)
                    after = {
                        path: (repo / path).read_bytes()
                        for path in (gcr3ctl.BACKLOG_PATH, gcr3ctl.STATE_PATH, gcr3ctl.LOCK_PATH)
                    }
                    self.assertEqual(before, after)

    def test_coherent_substituted_approved_parent_fails_closed_without_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            (
                repo,
                _predecessor_backlog,
                _predecessor_state,
                successor_backlog,
                successor_state,
                transaction,
                anchor,
                authority,
            ) = self.recovery_fixture(temporary, coherent_substitution=True)
            artifacts = gcr3ctl.transaction_artifacts(repo)
            gcr3ctl.write_new_durable(artifacts[gcr3ctl.LOCK_PATH], (json.dumps(anchor, indent=2) + "\n").encode())
            gcr3ctl.write_new_durable(artifacts[gcr3ctl.BACKLOG_NEXT_PATH], successor_backlog)
            gcr3ctl.write_new_durable(artifacts[gcr3ctl.STATE_NEXT_PATH], successor_state)
            gcr3ctl.write_new_durable(
                artifacts[gcr3ctl.TRANSACTION_PATH], (json.dumps(transaction, indent=2) + "\n").encode()
            )
            (repo / gcr3ctl.BACKLOG_PATH).write_bytes(b"partial backlog\n")
            (repo / gcr3ctl.STATE_PATH).write_bytes(b"partial state\n")
            protected = [
                gcr3ctl.BACKLOG_PATH,
                gcr3ctl.STATE_PATH,
                gcr3ctl.LOCK_PATH,
                gcr3ctl.TRANSACTION_PATH,
                gcr3ctl.BACKLOG_NEXT_PATH,
                gcr3ctl.STATE_NEXT_PATH,
            ]
            before = {path: (repo / path).read_bytes() for path in protected}
            with self.assertRaisesRegex(SystemExit, "approval reference is not canonical"):
                gcr3ctl.recover_transaction(repo, authority)
            after = {path: (repo / path).read_bytes() for path in protected}
            self.assertEqual(before, after)

    def test_ledger_state_semantic_mismatches_fail_closed_without_cleanup(self) -> None:
        scenarios = (
            "adverse-ledger-approved-state",
            "approved-ledger-adverse-state",
            "findings",
            "closures",
            "evidence",
            "reviewer",
            "candidate",
            "candidate-evidence-scope",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                (
                    repo,
                    _predecessor_backlog,
                    _predecessor_state,
                    successor_backlog,
                    successor_state,
                    transaction,
                    anchor,
                    authority,
                ) = self.recovery_fixture(temporary, ledger_state_mismatch=scenario)
                artifacts = gcr3ctl.transaction_artifacts(repo)
                gcr3ctl.write_new_durable(artifacts[gcr3ctl.LOCK_PATH], (json.dumps(anchor, indent=2) + "\n").encode())
                gcr3ctl.write_new_durable(artifacts[gcr3ctl.BACKLOG_NEXT_PATH], successor_backlog)
                gcr3ctl.write_new_durable(artifacts[gcr3ctl.STATE_NEXT_PATH], successor_state)
                gcr3ctl.write_new_durable(
                    artifacts[gcr3ctl.TRANSACTION_PATH], (json.dumps(transaction, indent=2) + "\n").encode()
                )
                (repo / gcr3ctl.BACKLOG_PATH).write_bytes(b"partial backlog\n")
                (repo / gcr3ctl.STATE_PATH).write_bytes(b"partial state\n")
                protected = [
                    gcr3ctl.BACKLOG_PATH,
                    gcr3ctl.STATE_PATH,
                    gcr3ctl.LOCK_PATH,
                    gcr3ctl.TRANSACTION_PATH,
                    gcr3ctl.BACKLOG_NEXT_PATH,
                    gcr3ctl.STATE_NEXT_PATH,
                ]
                before = {path: (repo / path).read_bytes() for path in protected}
                with self.assertRaises(SystemExit):
                    gcr3ctl.recover_transaction(repo, authority)
                after = {path: (repo / path).read_bytes() for path in protected}
                self.assertEqual(before, after)

    def test_taskctl_revision_nine_reader_fails_closed_on_revision_ten(self) -> None:
        backlog = yaml.safe_load((REPO / gcr3ctl.BACKLOG_PATH).read_text(encoding="utf-8"))
        backlog["control_plane"]["revision"] = 10
        backlog["control_plane"]["minimum_tool_revision"] = 10
        with patch.object(taskctl, "CONTROL_TOOL_REVISION", 9):
            errors = taskctl.wave_authority_errors(backlog, None)
        self.assertTrue(
            any(
                message in errors
                for message in (
                    "this taskctl revision is too old for the active control plane",
                    "control plane revision is missing or unsupported",
                )
            ),
            errors,
        )

    def test_child_process_crashes_recover_to_one_exact_pair(self) -> None:
        boundaries = [
            "lock-durable",
            "backlog-next-durable",
            "state-next-durable",
            "transaction-published",
            "backlog-published",
            "state-published",
            "successor-directories-durable",
            "cleanup-GCR-0003.B00.adoption-transaction.json",
            "cleanup-GCR-0003.B00.adoption.lock",
        ]
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temporary:
                (
                    repo,
                    predecessor_backlog,
                    predecessor_state,
                    successor_backlog,
                    successor_state,
                    transaction,
                    anchor,
                    authority,
                ) = self.recovery_fixture(temporary)
                (repo / ".git/gcr3-transaction.json").write_bytes((json.dumps(transaction, indent=2) + "\n").encode())
                (repo / ".git/gcr3-anchor.json").write_bytes((json.dumps(anchor, indent=2) + "\n").encode())
                (repo / ".git/gcr3-authority-base").write_text(authority[2], encoding="ascii")
                (repo / ".git/gcr3-authority-packet.json").write_bytes(
                    (json.dumps(authority[1], indent=2) + "\n").encode()
                )
                (repo / ".git/gcr3-successor-backlog").write_bytes(successor_backlog)
                (repo / ".git/gcr3-successor-state").write_bytes(successor_state)
                child = "\n".join(
                    [
                        "import json, os, pathlib, sys, yaml",
                        f"sys.path.insert(0, {json.dumps(str(REPO / 'tools'))})",
                        "import gcr3ctl, taskctl",
                        "repo = pathlib.Path(sys.argv[1])",
                        "boundary = sys.argv[2]",
                        "new_backlog = (repo / '.git/gcr3-successor-backlog').read_bytes()",
                        "new_state = (repo / '.git/gcr3-successor-state').read_bytes()",
                        "transaction = json.loads((repo / '.git/gcr3-transaction.json').read_bytes())",
                        "anchor = json.loads((repo / '.git/gcr3-anchor.json').read_bytes())",
                        (
                            "authority = ({}, json.loads((repo / '.git/gcr3-authority-packet.json').read_bytes()), "
                            "(repo / '.git/gcr3-authority-base').read_text(encoding='ascii'))"
                        ),
                        "def crash(label):",
                        "  if label == boundary: os._exit(77)",
                        "gcr3ctl.adoption_fault_boundary = crash",
                        "artifacts = gcr3ctl.transaction_artifacts(repo)",
                        (
                            "with taskctl.exclusive_backlog_lock(repo / gcr3ctl.BACKLOG_PATH), "
                            "gcr3ctl.transaction_lock(repo, anchor=anchor, authority=authority):"
                        ),
                        "  gcr3ctl.write_new_durable(artifacts[gcr3ctl.BACKLOG_NEXT_PATH], new_backlog)",
                        "  crash('backlog-next-durable')",
                        "  gcr3ctl.write_new_durable(artifacts[gcr3ctl.STATE_NEXT_PATH], new_state)",
                        "  crash('state-next-durable')",
                        (
                            "  gcr3ctl.write_new_durable(artifacts[gcr3ctl.TRANSACTION_PATH], "
                            "(json.dumps(transaction, indent=2) + '\\n').encode())"
                        ),
                        "  crash('transaction-published')",
                        "  gcr3ctl.complete_transaction(repo, transaction)",
                    ]
                )
                result = subprocess.run(
                    [sys.executable, "-c", child, str(repo), boundary],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(77, result.returncode, result.stdout + result.stderr)
                if gcr3ctl.present_transaction_artifacts(repo):
                    outcome = gcr3ctl.recover_transaction(repo, authority)
                    self.assertIn(outcome, {"RESTORED_PREDECESSOR", "COMPLETED_SUCCESSOR"})
                live = (
                    (repo / gcr3ctl.BACKLOG_PATH).read_bytes(),
                    (repo / gcr3ctl.STATE_PATH).read_bytes(),
                )
                self.assertIn(
                    live,
                    {
                        (predecessor_backlog, predecessor_state),
                        (successor_backlog, successor_state),
                    },
                )
                self.assertEqual([], gcr3ctl.present_transaction_artifacts(repo))
                self.assertEqual("ABSENT", gcr3ctl.recover_transaction(repo, authority))

    def test_real_git_revision_nine_to_gcr3_then_separately_approved_v4_s02(self) -> None:
        implementation_paths = [
            "planning/backlog.schema.json",
            "planning/governance-recovery-requests/governance-recovery-supplement.v4.schema.json",
            "planning/governance-recovery-requests/governance-recovery-supplement-approval.v4.schema.json",
            "quality-scope.json",
            "tests/foundation/test_gcr3ctl.py",
            "tests/foundation/test_recoveryctl.py",
            "tests/foundation/test_taskctl_schema.py",
            "tools/gcr3ctl.py",
            "tools/recoveryctl.py",
            "tools/taskctl.py",
        ]

        def run(repo: Path, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [sys.executable, *arguments],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
            return result

        def assert_historic_retry_denied(repo: Path, candidate: str) -> None:
            before = (repo / gcr3ctl.BACKLOG_PATH).read_bytes()
            result = run(
                repo,
                "tools/taskctl.py",
                "--file",
                gcr3ctl.BACKLOG_PATH,
                "amendment",
                "bootstrap-resubmit",
                "W1.A04",
                "--agent",
                "codex",
                "--implementation-commit",
                candidate,
                "--evidence",
                gcr3ctl.TRIGGER_PATH,
                expected=1,
            )
            diagnostic = result.stdout + result.stderr
            self.assertTrue("W1.A04" in diagnostic or "HOLD-W1-GRR-0002" in diagnostic, diagnostic)
            self.assertEqual(before, (repo / gcr3ctl.BACKLOG_PATH).read_bytes())

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            bundle = Path(temporary) / "source.bundle"
            bundled = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={REPO.as_posix()}",
                    "-C",
                    str(REPO),
                    "bundle",
                    "create",
                    str(bundle),
                    gcr3ctl.BRANCH,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, bundled.returncode, bundled.stdout + bundled.stderr)
            clone = subprocess.run(
                ["git", "clone", "-b", gcr3ctl.BRANCH, str(bundle), str(repo)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, clone.returncode, clone.stdout + clone.stderr)
            self.git(repo, "config", "user.email", "gcr3-e2e@example.test")
            self.git(repo, "config", "user.name", "GCR3 E2E Fixture")
            self.git(repo, "config", "core.autocrlf", "false")
            self.assertEqual(gcr3ctl.BRANCH, self.git(repo, "branch", "--show-current"))
            self.git(repo, "checkout", "-B", gcr3ctl.BRANCH, gcr3ctl.APPROVAL_COMMIT)
            for relative in implementation_paths:
                destination = repo / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / relative, destination)
            self.git(repo, "add", "--", *implementation_paths)
            self.git(repo, "commit", "-m", "fixture: implement exact GCR-0003 B00")
            candidate = self.git(repo, "rev-parse", "HEAD")
            trigger = repo / gcr3ctl.TRIGGER_PATH
            trigger.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / gcr3ctl.TRIGGER_PATH, trigger)
            self.assertEqual(gcr3ctl.BACKLOG_SHA256, gcr3ctl.sha256((repo / gcr3ctl.BACKLOG_PATH).read_bytes()))
            assert_historic_retry_denied(repo, "214ac1aac53b4396ee29f7a935ddcac2a34618b6")

            packet = json.loads((repo / gcr3ctl.PACKET_PATH).read_bytes())
            changed = sorted(
                self.git(
                    repo,
                    "diff",
                    "--name-only",
                    f"{gcr3ctl.APPROVAL_COMMIT}..{candidate}",
                    "--",
                ).splitlines()
            )
            evidence_relative = gcr3ctl.evidence_path("R01")
            self.write_json(
                repo,
                evidence_relative,
                {
                    "schemaVersion": "3.0-control-recovery-evidence",
                    "documentType": "governance-control-recovery-bootstrap-evidence",
                    "controlRecoveryId": "GCR-0003",
                    "bootstrapUnit": "GCR-0003.B00",
                    "attemptId": "R01",
                    "commit": candidate,
                    "baseCommit": gcr3ctl.APPROVAL_COMMIT,
                    "branch": gcr3ctl.BRANCH,
                    "triggerWitness": gcr3ctl.trigger_witness(),
                    "changedFiles": changed,
                    "checks": [
                        {
                            "id": "real-git-lifecycle",
                            "command": "fixture real-Git lifecycle",
                            "exitCode": 0,
                            "result": "passed",
                        }
                    ],
                    "acceptanceCriteria": [
                        {"index": index, "statement": statement, "evidence": ["Exercised by this fixture."]}
                        for index, statement in enumerate(packet["acceptanceCriteria"], start=1)
                    ],
                    "findingClosures": [],
                    "unverifiedItems": [],
                    "verificationSelection": {
                        "riskAnalysis": "Exact authority, durable adoption, and post-adoption S02 sequencing.",
                        "selectedChecks": ["real-git-lifecycle"],
                        "deferredChecks": ["Full repository qualification remains at the Wave boundary."],
                    },
                },
            )
            run(
                repo,
                "tools/gcr3ctl.py",
                "--repo",
                ".",
                "submit",
                "GCR-0003",
                "--agent",
                "codex",
                "--approval-commit",
                gcr3ctl.APPROVAL_COMMIT,
                "--implementation-commit",
                candidate,
                "--evidence",
                evidence_relative,
            )
            self.git(repo, "add", "--", evidence_relative, gcr3ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "fixture: freeze GCR-0003 R01")
            reviewed_state = self.git(repo, "rev-parse", "HEAD")
            state = json.loads((repo / gcr3ctl.STATE_PATH).read_bytes())
            submission = state["currentSubmission"]
            review_relative = gcr3ctl.review_path("R01")
            self.write_json(
                repo,
                review_relative,
                {
                    "schemaVersion": "3.0-control-recovery-review",
                    "documentType": "governance-control-recovery-bootstrap-review",
                    "controlRecoveryId": "GCR-0003",
                    "bootstrapUnit": "GCR-0003.B00",
                    "attemptId": "R01",
                    "candidateCommit": candidate,
                    "reviewedStateCommit": reviewed_state,
                    "reviewer": "independent-gcr3-e2e-reviewer",
                    "result": "approved",
                    "evidence": submission["evidence"],
                    "findings": [],
                    "closures": [],
                    "notes": "Exact disposable-repository control/security review.",
                },
            )
            run(
                repo,
                "tools/gcr3ctl.py",
                "--repo",
                ".",
                "review",
                "GCR-0003",
                "--reviewer",
                "independent-gcr3-e2e-reviewer",
                "--from",
                review_relative,
            )
            self.git(repo, "add", "--", review_relative, gcr3ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "fixture: approve GCR-0003 R01")
            approved_state = self.git(repo, "rev-parse", "HEAD")
            adoption_evidence = {
                "schemaVersion": "3.0-control-recovery-adoption-evidence",
                "documentType": "governance-control-recovery-adoption-evidence",
                "controlRecoveryId": "GCR-0003",
                "bootstrapUnit": "GCR-0003.B00",
                "reviewedStateCommit": approved_state,
                "triggerWitness": gcr3ctl.trigger_witness(),
                "predecessorRevision": 9,
                "successorRevision": 10,
                "supportedControlCeiling": 11,
                "expectedChangedFiles": [gcr3ctl.BACKLOG_PATH, gcr3ctl.STATE_PATH],
                "checks": [
                    {
                        "id": "adoption-preflight",
                        "command": "fixture adoption preflight",
                        "exitCode": 0,
                        "result": "passed",
                    }
                ],
                "unverifiedItems": [],
            }
            self.write_json(repo, gcr3ctl.ADOPTION_EVIDENCE_PATH, adoption_evidence)
            self.git(repo, "add", "--", gcr3ctl.ADOPTION_EVIDENCE_PATH)
            self.git(repo, "commit", "-m", "fixture: bind GCR-0003 adoption evidence")
            adoption_evidence_commit = self.git(repo, "rev-parse", "HEAD")
            run(
                repo,
                "tools/gcr3ctl.py",
                "--repo",
                ".",
                "adopt",
                "GCR-0003",
                "--agent",
                "codex",
                "--approved-state-commit",
                approved_state,
                "--evidence",
                gcr3ctl.ADOPTION_EVIDENCE_PATH,
            )
            self.git(repo, "add", "--", gcr3ctl.BACKLOG_PATH, gcr3ctl.STATE_PATH)
            self.git(repo, "commit", "-m", "fixture: adopt GCR-0003 revision 10")
            adoption_commit = self.git(repo, "rev-parse", "HEAD")
            run(repo, "tools/gcr3ctl.py", "--repo", ".", "validate", "GCR-0003", "--require-approved")
            revision_ten = yaml.safe_load((repo / gcr3ctl.BACKLOG_PATH).read_bytes())
            self.assertEqual(10, revision_ten["control_plane"]["revision"])
            with patch.object(taskctl, "CONTROL_TOOL_REVISION", 9):
                self.assertTrue(taskctl.wave_authority_errors(revision_ten, None))

            base_approval, base_packet, base_approval_payload, base_packet_payload = (
                recoveryctl.load_recovery_authority(repo, "GRR-0002")
            )
            hold = recoveryctl.recovery_hold(revision_ten, "GRR-0002")
            base_attempt = hold["bootstrap"]["attempts"][-1]
            base_ledger = base_attempt["ledger"]
            base_ledger_document = json.loads((repo / base_ledger["path"]).read_bytes())
            target_approval_path = "planning/wave-amendment-approvals/W1.A04.json"
            target_approval_payload = (repo / target_approval_path).read_bytes()
            target_approval = json.loads(target_approval_payload)
            target_intro = taskctl.approval_introduction_commit(repo, target_approval_path)
            self.assertIsNotNone(target_intro)
            witness_payload = trigger.read_bytes()
            witness = json.loads(witness_payload)
            state_payload = (repo / gcr3ctl.STATE_PATH).read_bytes()
            adopted_state = json.loads(state_payload)
            generation = revision_ten["control_plane"]["control_generations"][-1]
            proposal_relative = "planning/governance-recovery-requests/GRR-0002.S02.md"
            review_page_relative = "planning/governance-recovery-requests/GRR-0002.S02-review.html"
            (repo / proposal_relative).write_bytes(b"# Fixture GRR-0002.S02\n")
            (repo / review_page_relative).write_bytes(b"<!doctype html><title>Fixture S02 review</title>\n")
            schema_relative = "planning/governance-recovery-requests/governance-recovery-supplement.v4.schema.json"
            backlog_payload = (repo / gcr3ctl.BACKLOG_PATH).read_bytes()
            packet_relative = "planning/governance-recovery-requests/GRR-0002.S02.packet.json"
            s02_packet = {
                "$schema": "./governance-recovery-supplement.v4.schema.json",
                "schemaVersion": "4.0-recovery-supplement-proposal",
                "documentType": "governance-recovery-supplement-packet",
                "recoveryRequestId": "GRR-0002",
                "supplementId": "GRR-0002.S02",
                "title": "Fixture exact post-GCR-0003 S02 lane",
                "targetWave": "W1",
                "status": "pending-human-approval",
                "executionState": "non-executable",
                "classification": "approved-bootstrap-latent-control-defect",
                "controlTransition": {
                    "predecessorRevision": 10,
                    "successorRevision": 11,
                    "generationNeutral": True,
                    "olderReadersFailClosed": True,
                },
                "baseRecoveryAuthority": {
                    "packet": {
                        "path": "planning/governance-recovery-requests/GRR-0002.packet.json",
                        "sha256": recoveryctl.sha256(base_packet_payload),
                        "commit": base_approval["packet"]["commit"],
                    },
                    "approval": {
                        "path": "planning/governance-recovery-approvals/GRR-0002.json",
                        "sha256": recoveryctl.sha256(base_approval_payload),
                        "introductionCommit": taskctl.approval_introduction_commit(
                            repo, "planning/governance-recovery-approvals/GRR-0002.json"
                        ),
                    },
                    "holdId": base_packet["controlHold"]["id"],
                    "bootstrapUnit": base_packet["bootstrapUnit"]["id"],
                    "latestApprovedReview": {
                        "attemptId": base_attempt["id"],
                        "path": base_ledger["path"],
                        "sha256": base_ledger["sha256"],
                        "candidateCommit": base_attempt["implementation_commit"],
                        "reviewedStateCommit": base_ledger_document["reviewedStateCommit"],
                    },
                },
                "installedControlRecovery": {
                    "controlRecoveryId": "GCR-0003",
                    "bootstrapUnit": "GCR-0003.B00",
                    "adoptionCommit": adoption_commit,
                    "approval": {
                        "path": generation["approval_reference"]["path"],
                        "sha256": generation["approval_reference"]["sha256"],
                        "commit": generation["approval_reference"]["introduction_commit"],
                    },
                    "latestApprovedReview": {
                        "path": generation["review_reference"]["path"],
                        "sha256": generation["review_reference"]["sha256"],
                        "commit": generation["review_reference"]["approved_state_commit"],
                    },
                    "adoptedState": {
                        "path": gcr3ctl.STATE_PATH,
                        "sha256": recoveryctl.sha256(state_payload),
                        "commit": adoption_commit,
                    },
                    "adoptionEvidence": adopted_state["adoption"]["evidence"],
                    "controlTransition": {
                        "predecessorRevision": 9,
                        "successorRevision": 10,
                        "supportedControlCeiling": 11,
                    },
                },
                "targetAmendmentAuthority": {
                    "changeRequestPacket": {
                        "id": target_approval["changeRequestId"],
                        "path": target_approval["packet"]["path"],
                        "sha256": target_approval["packet"]["sha256"],
                        "commit": target_approval["packet"]["commit"],
                    },
                    "amendmentApproval": {
                        "id": "W1.A04",
                        "path": target_approval_path,
                        "sha256": recoveryctl.sha256(target_approval_payload),
                        "introductionCommit": target_intro,
                    },
                    "bootstrap": {
                        "id": "W1.A04.B00",
                        "candidateCommit": witness["commit"],
                        "evidence": {
                            "path": gcr3ctl.TRIGGER_PATH,
                            "sha256": recoveryctl.sha256(witness_payload),
                            "commit": witness["commit"],
                        },
                    },
                    "backlogPresence": False,
                },
                "triggerEvidence": {
                    "discoveryCommit": adoption_commit,
                    "backlogSha256": recoveryctl.sha256(backlog_payload),
                    "command": "fixture supplement-start GRR-0002.S02",
                    "diagnostic": "Exact post-GCR-0003 revision-10 activation boundary.",
                    "atomicNoMutation": True,
                },
                "activationBoundary": {
                    "controlRevision": 10,
                    "holdStatus": "ACTIVE",
                    "waveStatus": "PAUSED",
                    "waveScope": "wave",
                    "amendmentId": "W1.A04",
                    "amendmentBacklogStatus": "ABSENT",
                    "blockedTaskId": "CAP-02.S04.T03",
                    "blockedTaskStatus": "BLOCKED",
                },
                "supplementalBootstrap": {
                    "id": "GRR-0002.B02",
                    "kind": "append-only-approved-bootstrap-remediation",
                    "exceptionReason": "Exercise only the separately approved exact S02/B02 transition.",
                    "authorizedPaths": ["planning/backlog.yaml"],
                    "requiredOutcomes": ["Install only sequential GRR-0002.S02/B02 at revision 11."],
                    "prohibitedOutcomes": ["No W1.A04 retry, Wave resume, hold release, or task execution."],
                },
                "acceptanceCriteria": ["The exact independently approved v4 S02 raises revision 10 to 11."],
                "verificationObligations": ["Run the unmocked real-Git supplement-start boundary."],
                "rollback": ["Any failed check leaves the revision-10 backlog byte-identical."],
                "alternatives": [
                    {
                        "id": "A",
                        "title": "Install exact v4 S02",
                        "disposition": "recommended",
                        "consequence": "Advances only the supplemental bootstrap lane.",
                    },
                    {
                        "id": "B",
                        "title": "Keep recovery paused",
                        "disposition": "safe",
                        "consequence": "Leaves all ordinary execution denied.",
                    },
                ],
                "files": [
                    {"path": schema_relative, "sha256": recoveryctl.sha256((repo / schema_relative).read_bytes())},
                    {"path": proposal_relative, "sha256": recoveryctl.sha256((repo / proposal_relative).read_bytes())},
                    {
                        "path": review_page_relative,
                        "sha256": recoveryctl.sha256((repo / review_page_relative).read_bytes()),
                    },
                ],
                "requiredApprovalStatement": "Approve only fixture GRR-0002.S02/B02 at its exact packet commit.",
            }
            self.write_json(repo, packet_relative, s02_packet)
            self.assertEqual(
                [],
                recoveryctl.schema_errors(s02_packet, repo / schema_relative),
            )
            self.git(repo, "add", "--", proposal_relative, review_page_relative, packet_relative)
            self.git(repo, "commit", "-m", "fixture: freeze independently reviewed v4 S02 packet")
            packet_commit = self.git(repo, "rev-parse", "HEAD")
            packet_payload = (repo / packet_relative).read_bytes()
            approval_relative = "planning/governance-recovery-approvals/GRR-0002.S02.json"
            s02_approval = {
                "$schema": "../governance-recovery-requests/governance-recovery-supplement-approval.v4.schema.json",
                "schemaVersion": "4.0",
                "documentType": "governance-recovery-supplement-approval",
                "recoveryRequestId": "GRR-0002",
                "supplementId": "GRR-0002.S02",
                "targetWave": "W1",
                "status": "APPROVED",
                "approvedBy": "fixture-repository-owner",
                "approvedAt": "2026-08-25T03:00:00Z",
                "decision": "Approve only the exact fixture S02/B02 packet.",
                "packet": {
                    "commit": packet_commit,
                    "path": packet_relative,
                    "sha256": recoveryctl.sha256(packet_payload),
                    "proposalPath": proposal_relative,
                    "proposalSha256": recoveryctl.sha256((repo / proposal_relative).read_bytes()),
                    "schemaPath": schema_relative,
                    "schemaSha256": recoveryctl.sha256((repo / schema_relative).read_bytes()),
                    "reviewPath": review_page_relative,
                    "reviewSha256": recoveryctl.sha256((repo / review_page_relative).read_bytes()),
                },
                "supplementalBootstrapUnit": "GRR-0002.B02",
                "independentPacketReview": {
                    "reviewer": "independent-fixture-s02-reviewer",
                    "attemptId": "R01",
                    "candidateCommit": packet_commit,
                    "packetSha256": recoveryctl.sha256(packet_payload),
                    "result": "APPROVED",
                    "openFindingIds": [],
                    "closedFindingIds": [],
                    "priorAdverseLedger": None,
                },
                "executionAuthority": {
                    "supplementalBootstrapOnly": True,
                    "postBootstrapExecution": False,
                    "amendmentMaterialization": False,
                    "ordinaryWaveResume": False,
                    "taskExecution": False,
                    "releaseGateApproval": False,
                },
            }
            self.write_json(repo, approval_relative, s02_approval)
            self.git(repo, "add", "--", approval_relative)
            self.git(repo, "commit", "-m", "fixture: separately approve exact v4 S02 packet")
            run(
                repo,
                "tools/recoveryctl.py",
                "--repo",
                ".",
                "supplement-start",
                "GRR-0002.S02",
                "--agent",
                "codex",
            )
            revision_eleven = yaml.safe_load((repo / gcr3ctl.BACKLOG_PATH).read_bytes())
            self.assertEqual(11, revision_eleven["control_plane"]["revision"])
            with patch.object(taskctl, "CONTROL_TOOL_REVISION", 10):
                self.assertTrue(taskctl.wave_authority_errors(revision_eleven, None))
            self.git(repo, "add", "--", gcr3ctl.BACKLOG_PATH)
            self.git(repo, "commit", "-m", "fixture: start exact v4 S02 at revision 11")
            run(repo, "tools/gcr3ctl.py", "--repo", ".", "validate", "GCR-0003", "--require-approved")
            assert_historic_retry_denied(repo, "214ac1aac53b4396ee29f7a935ddcac2a34618b6")
            final_data = yaml.safe_load((repo / gcr3ctl.BACKLOG_PATH).read_bytes())
            final_tasks = taskctl.index_backlog(final_data)[3]
            self.assertNotIn("W1.A04", taskctl.wave_amendment_map(final_data))
            self.assertEqual("PAUSED", taskctl.wave_map(final_data)["W1"]["campaign"]["status"])
            self.assertEqual("BLOCKED", final_tasks["CAP-02.S04.T03"]["status"])
            self.assertEqual("PENDING", taskctl.index_backlog(final_data)[4]["G1"]["status"])
            self.assertEqual(gcr3ctl.TRIGGER_SHA256, gcr3ctl.sha256(trigger.read_bytes()))
            self.assertEqual(
                [gcr3ctl.TRIGGER_PATH],
                self.git(repo, "ls-files", "--others", "--exclude-standard").splitlines(),
            )
            self.assertEqual(adoption_evidence_commit, adopted_state["adoption"]["evidence"]["commit"])


if __name__ == "__main__":
    unittest.main()
