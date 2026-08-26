from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import taskctl  # noqa: E402
from taskctl import backlog_schema_errors, load, validate  # noqa: E402

LoadedBacklog = tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]


class BacklogSchemaTests(unittest.TestCase):
    canonical: dict[str, Any]
    schema: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = yaml.safe_load((REPO / "planning" / "backlog.yaml").read_text(encoding="utf-8"))
        cls.schema = REPO / "planning" / "backlog.schema.json"

    def load_copy(self, data: dict[str, Any]) -> LoadedBacklog:
        with tempfile.TemporaryDirectory() as temporary:
            backlog = Path(temporary) / "backlog.yaml"
            backlog.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            return load(str(backlog), schema_path=self.schema)

    def test_canonical_backlog_passes_schema_and_semantic_validation(self) -> None:
        data, capabilities, slices, tasks, gates = load(
            str(REPO / "planning" / "backlog.yaml"), schema_path=self.schema
        )

        self.assertEqual([], validate(data, capabilities, slices, tasks, gates))

    def test_wave_resume_record_schema_is_exact_and_backward_compatible(self) -> None:
        data = copy.deepcopy(self.canonical)
        wave = next(item for item in data["waves"] if item["id"] == "W1")
        wave["campaign"]["resume_records"] = [
            {
                "id": "W1.R01",
                "wave_id": "W1",
                "control_revision": 6,
                "prior_status": "PAUSED",
                "pre_resume_commit": "a" * 40,
                "prior_campaign_sha256": "b" * 64,
                "branch": "codex/w1-windows-local-runtime",
                "worktree": "C:/workspace/research-observatory",
                "profile": "LOC",
                "platform": "windows-x64",
                "actor": "codex",
                "resumed_at": "2026-08-24T00:00:00+00:00",
            }
        ]
        self.assertEqual([], backlog_schema_errors(data, schema_path=self.schema))

        del wave["campaign"]["resume_records"][0]["actor"]
        errors = backlog_schema_errors(data, schema_path=self.schema)
        self.assertTrue(any("resume_records" in error and "actor" in error for error in errors))

        data = copy.deepcopy(self.canonical)
        self.assertEqual([], backlog_schema_errors(data, schema_path=self.schema))

    def test_bootstrap_scope_addendum_is_exactly_one_generated_path(self) -> None:
        schema = json.loads(
            (REPO / "planning/wave-amendment-approvals/bootstrap-scope-addendum.schema.json").read_text(
                encoding="utf-8"
            )
        )
        record = json.loads(
            (REPO / "planning/wave-amendment-approvals/W1.A02.B00.addendum-01.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual([], list(validator.iter_errors(record)))
        record["authorizedAdditionalPaths"].append("product/runtime.py")
        self.assertTrue(list(validator.iter_errors(record)))

    def test_duplicate_task_id_has_precise_diagnostic(self) -> None:
        data = copy.deepcopy(self.canonical)
        tasks = data["capabilities"][0]["slices"][0]["tasks"]
        duplicate_id = tasks[0]["id"]
        tasks.append(copy.deepcopy(tasks[0]))

        with self.assertRaisesRegex(SystemExit, f"Duplicate task ID: {duplicate_id}"):
            self.load_copy(data)

    def test_invalid_status_reports_schema_path_and_value(self) -> None:
        data = copy.deepcopy(self.canonical)
        data["capabilities"][0]["slices"][0]["tasks"][0]["status"] = "CLAIMED"

        with self.assertRaisesRegex(
            SystemExit,
            r"\$\.capabilities\[0\]\.slices\[0\]\.tasks\[0\]\.status: 'CLAIMED' is not one of",
        ):
            self.load_copy(data)

    def test_missing_dependency_names_task_and_target(self) -> None:
        data = copy.deepcopy(self.canonical)
        task = data["capabilities"][0]["slices"][0]["tasks"][0]
        task["dependencies"] = ["CAP-99.S99.T99"]

        loaded = self.load_copy(data)
        errors = validate(*loaded)

        self.assertIn(f"{task['id']}: missing dependency CAP-99.S99.T99", errors)

    def test_missing_slice_dependency_names_slice_and_target(self) -> None:
        data = copy.deepcopy(self.canonical)
        slice_ = data["capabilities"][0]["slices"][0]
        slice_["depends_on"] = ["CAP-99.S99.T99"]

        loaded = self.load_copy(data)
        errors = validate(*loaded)

        self.assertIn(f"{slice_['id']}: missing dependency CAP-99.S99.T99", errors)

    def test_dependency_cycle_prints_the_cycle_path(self) -> None:
        data = copy.deepcopy(self.canonical)
        first, second = data["capabilities"][0]["slices"][0]["tasks"][:2]
        first["dependencies"] = [second["id"]]
        second["dependencies"] = [first["id"]]

        loaded = self.load_copy(data)
        errors = validate(*loaded)

        self.assertIn(
            f"Dependency cycle detected: {first['id']} -> {second['id']} -> {first['id']}",
            errors,
        )

    def test_malformed_timestamp_fails_schema_format_check(self) -> None:
        data = copy.deepcopy(self.canonical)
        data["capabilities"][0]["campaign"]["updated_at"] = "not-a-timestamp"

        with self.assertRaisesRegex(SystemExit, r"campaign\.updated_at: 'not-a-timestamp' is not a 'date-time'"):
            self.load_copy(data)

    def test_every_wave_requires_one_exit_gate_and_activation_links_back(self) -> None:
        data = copy.deepcopy(self.canonical)
        removed = data["release_gates"][-1]
        removed["after_wave"] = "W10"
        loaded = self.load_copy(data)
        errors = validate(*loaded)
        self.assertIn("W11: expected exactly one wave-exit gate, found 0", errors)

        data = copy.deepcopy(self.canonical)
        data["waves"][1]["activation_gate"] = "G1"
        loaded = self.load_copy(data)
        errors = validate(*loaded)
        self.assertIn("W1: activation gate G1 does not unlock the wave", errors)

    def test_experience_change_requires_exact_machine_lineage_fields(self) -> None:
        data = copy.deepcopy(self.canonical)
        task = data["capabilities"][0]["slices"][0]["tasks"][0]
        task["experience_change"] = {
            "kind": "defect-restoration",
            "contract_path": f"artifacts/evidence/ui-change/{task['id']}.json",
            "reference_id": "RO-UI-ACADEMIC-MINIMAL-1.3",
            "reference_version": "1.3",
            "reference_package_sha256": "0" * 64,
            "reference_approval_commit": "0" * 40,
            "previous_reference_id": "RO-UI-ACADEMIC-MINIMAL-1.2",
            "implementation_agent": "codex",
        }

        with self.assertRaisesRegex(SystemExit, r"experience_change\.implementation_agent"):
            self.load_copy(data)

        task["experience_change"]["implementation_agent"] = "agent:codex."
        with self.assertRaisesRegex(SystemExit, r"experience_change\.implementation_agent"):
            self.load_copy(data)

    def test_slice_id_must_remain_in_capability_namespace(self) -> None:
        data = copy.deepcopy(self.canonical)
        capability = data["capabilities"][0]
        slice_ = capability["slices"][0]
        slice_["id"] = "CAP-99.S99"
        for task in slice_["tasks"]:
            task["slice_id"] = slice_["id"]

        loaded = self.load_copy(data)
        errors = validate(*loaded)

        self.assertIn("CAP-99.S99: outside capability namespace CAP-00", errors)

    def test_task_id_must_remain_in_slice_namespace(self) -> None:
        data = copy.deepcopy(self.canonical)
        slice_ = data["capabilities"][0]["slices"][0]
        task = slice_["tasks"][0]
        task["id"] = "CAP-98.S98.T98"

        loaded = self.load_copy(data)
        errors = validate(*loaded)

        self.assertIn(f"CAP-98.S98.T98: outside slice namespace {slice_['id']}", errors)

    def test_done_task_requires_reviewer_and_review_timestamp(self) -> None:
        data = copy.deepcopy(self.canonical)
        task = next(
            task
            for capability in data["capabilities"]
            for slice_ in capability["slices"]
            for task in slice_["tasks"]
            if task["status"] == "DONE"
        )
        task["review"]["reviewer"] = None
        task["review"]["reviewed_at"] = None

        loaded = self.load_copy(data)
        errors = validate(*loaded)

        self.assertIn(f"{task['id']}: DONE without evidence and complete approved review", errors)

    def test_control_plane_requires_the_supported_minimum_tool_revision(self) -> None:
        data = copy.deepcopy(self.canonical)
        data["control_plane"] = {
            "revision": 2,
            "minimum_tool_revision": 1,
            "active_amendment": None,
        }

        with self.assertRaisesRegex(SystemExit, r"control_plane\.minimum_tool_revision: 1 is less than"):
            self.load_copy(data)

    def test_gcr_generation_is_exact_and_revision_six_reader_fails_closed(self) -> None:
        data = copy.deepcopy(self.canonical)
        data["control_plane"]["revision"] = 7
        data["control_plane"]["minimum_tool_revision"] = 7
        next(hold for hold in data["control_plane"]["recovery_holds"] if hold["id"] == "HOLD-W1-GRR-0002")[
            "supplements"
        ] = []
        data["control_plane"]["control_generations"] = [
            {
                "id": "GCR-0001",
                "bootstrap_id": "GCR-0001.B00",
                "hold_id": "HOLD-W1-GRR-0002",
                "predecessor_revision": 6,
                "successor_revision": 7,
                "approval_reference": {
                    "path": "planning/governance-control-recovery/GCR-0001.approval.json",
                    "sha256": "a" * 64,
                    "introduction_commit": "b" * 40,
                },
                "review_reference": {
                    "path": "planning/governance-control-recovery/GCR-0001.B00.review-R01.json",
                    "sha256": "c" * 64,
                    "reviewed_state_commit": "d" * 40,
                    "approved_state_commit": "e" * 40,
                },
                "adopted_by": "codex",
                "adopted_at": "2026-08-24T02:00:00+00:00",
            }
        ]
        self.assertEqual([], backlog_schema_errors(data, schema_path=self.schema))
        self.assertEqual([], taskctl.governance_control_generation_errors(data, None))
        with patch.object(taskctl, "CONTROL_TOOL_REVISION", 6):
            errors = taskctl.wave_authority_errors(data, None)
        self.assertTrue(
            {
                "control plane revision is missing or unsupported",
                "this taskctl revision is too old for the active control plane",
            }
            & set(errors)
        )

    def test_gcr_adoption_transaction_artifacts_fail_closed_before_generation(self) -> None:
        data = copy.deepcopy(self.canonical)
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for relative in taskctl.GCR_ADOPTION_TRANSACTION_PATHS:
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("prepared\n", encoding="utf-8")
                errors = taskctl.governance_control_generation_errors(data, repo)
                self.assertTrue(any("requires explicit gcrctl recovery" in error for error in errors), errors)
                path.unlink()

    def test_amendment_hold_is_a_current_schema_marker_that_legacy_tools_reject(self) -> None:
        data = copy.deepcopy(self.canonical)
        wave = next(item for item in data["waves"] if item["id"] == "W1")
        self.assertEqual("PAUSED", wave["campaign"]["status"])
        wave["campaign"]["scope"] = "amendment-hold"

        self.assertEqual([], backlog_schema_errors(data, schema_path=self.schema))

        legacy_schema = json.loads(self.schema.read_text(encoding="utf-8"))
        legacy_schema["properties"]["waves"]["items"]["properties"]["campaign"]["properties"]["scope"] = {
            "const": "wave"
        }
        with tempfile.TemporaryDirectory() as temporary:
            legacy_path = Path(temporary) / "legacy-backlog.schema.json"
            legacy_path.write_text(json.dumps(legacy_schema), encoding="utf-8")
            errors = backlog_schema_errors(data, schema_path=legacy_path)

        self.assertTrue(
            any("$.waves[1].campaign.scope" in error and "'wave' was expected" in error for error in errors),
            errors,
        )

    def test_exact_pre_b00_schema_rejects_an_active_amendment_ledger(self) -> None:
        data = copy.deepcopy(self.canonical)
        wave = next(item for item in data["waves"] if item["id"] == "W1")
        wave["campaign"]["scope"] = "amendment-hold"
        amendment = next(item for item in data["wave_amendments"] if item["id"] == "W1.A02")
        amendment["lifecycle"]["status"] = "ACTIVE"
        amendment["lifecycle"]["history"].append(
            {
                "id": "E02",
                "status": "ACTIVE",
                "actor": "agent:test",
                "at": "2026-08-21T00:00:00+00:00",
                "rationale": "Exercise the old-tool denial marker.",
            }
        )
        amendment["campaign"] = {
            "status": "ACTIVE",
            "scope": "wave-amendment",
            "owner": "agent:test",
            "branch": "codex/test",
            "worktree": str(REPO),
            "base_sha": "a" * 40,
            "profile": "LOC",
            "platform": "windows-x64",
            "started_at": "2026-08-21T00:00:00+00:00",
            "updated_at": "2026-08-21T00:00:00+00:00",
            "pause_reason": None,
            "lease": {
                "claimed_by": "agent:test",
                "claimed_at": "2026-08-21T00:00:00+00:00",
                "expires_at": "2026-08-21T08:00:00+00:00",
            },
        }
        data["control_plane"]["active_amendment"] = "W1.A02"
        historical = subprocess.run(
            [
                "git",
                "show",
                "6e9c440102a5c463bb35d81f4dbdc3453d9ce029:planning/backlog.schema.json",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        with tempfile.TemporaryDirectory() as temporary:
            historical_schema = Path(temporary) / "pre-b00-backlog.schema.json"
            historical_schema.write_text(historical, encoding="utf-8")
            errors = backlog_schema_errors(data, schema_path=historical_schema)

        self.assertIn("$.waves[1].campaign.scope: 'wave' was expected", errors)

    def test_t01_review_control_schema_is_optional_shared_and_strict(self) -> None:
        schema = json.loads(self.schema.read_text(encoding="utf-8"))
        ordinary_task_schema = schema["properties"]["capabilities"]["items"]["properties"]["slices"]["items"][
            "properties"
        ]["tasks"]["items"]
        self.assertEqual("#/$defs/taskReviewControl", ordinary_task_schema["properties"]["review_control"]["$ref"])
        self.assertEqual(
            "#/$defs/taskReviewControl",
            schema["$defs"]["enablerTask"]["properties"]["review_control"]["$ref"],
        )

        legacy = copy.deepcopy(self.canonical)
        for capability in legacy["capabilities"]:
            for slice_ in capability["slices"]:
                for task in slice_["tasks"]:
                    task.pop("review_control", None)
        for amendment in legacy.get("wave_amendments", []):
            for task in amendment.get("tasks", []):
                task.pop("review_control", None)
        self.assertEqual([], backlog_schema_errors(legacy, schema_path=self.schema))

        packet = {
            "id": "R01",
            "submitted_by": "agent:implementer",
            "submitted_at": "2026-08-21T01:00:00+00:00",
            "candidate_commit": "b" * 40,
            "base_commit": "a" * 40,
            "branch": "codex/test",
            "evidence_reference": {
                "type": "criterion-manifest",
                "path": "artifacts/evidence/CAP-00.S01.T01.json",
                "sha256": "1" * 64,
                "commit": "b" * 40,
                "recorded_at": "2026-08-21T01:00:00+00:00",
            },
            "acceptance_criteria_sha256": "2" * 64,
            "changed_paths": ["tools/taskctl.py"],
            "selected_checks": ["python -m unittest focused"],
            "deferred_checks": ["complete Wave-exit profile"],
            "selection_rationale": "The task changes the review-control boundary.",
            "selection_sha256": "3" * 64,
            "prior_attempt_id": None,
            "open_finding_ids": [],
            "root_cause_analysis": None,
            "packet_sha256": "4" * 64,
        }
        finding = {
            "id": "F01",
            "severity": "high",
            "blocking": True,
            "criterion_index": 1,
            "title": "Review control gap",
            "reproduction": "Run the deterministic fixture.",
            "required_remediation": "Correct the review-control invariant.",
        }
        control: dict[str, Any] = {
            "version": 1,
            "attempts": [
                {
                    "submission": packet,
                    "review": {
                        "reviewer": "agent:reviewer",
                        "result": "changes-requested",
                        "reviewed_at": "2026-08-21T02:00:00+00:00",
                        "notes": "One consolidated finding ledger.",
                    },
                    "ledger": {
                        "path": "artifacts/evidence/CAP-00.S01.T01.review-R01.json",
                        "sha256": "5" * 64,
                    },
                    "findings": [finding],
                    "closures": [],
                }
            ],
            "current_submission": None,
        }
        validator = Draft202012Validator(
            {"$ref": "#/$defs/taskReviewControl", "$defs": schema["$defs"]},
            format_checker=FormatChecker(),
        )
        self.assertEqual([], list(validator.iter_errors(control)))
        historical_empty_ids = copy.deepcopy(control)
        historical_empty_ids["attempts"][0]["submission"]["selected_command_ids"] = []
        self.assertEqual([], list(validator.iter_errors(historical_empty_ids)))

        prospective = copy.deepcopy(control)
        prospective["attempts"][0]["submission"]["selected_command_ids"] = ["foundation:unit"]
        prospective["attempts"][0]["telemetry"] = {
            "task_id": "CAP-00.S01.T01",
            "amendment_id": None,
            "attempt_id": "R01",
            "submitted_at": "2026-08-21T01:00:00+00:00",
            "reviewed_at": "2026-08-21T02:00:00+00:00",
            "duration_seconds": 3600,
            "outcome": "changes-requested",
            "finding_counts": {
                "critical": 0,
                "high": 1,
                "medium": 0,
                "low": 0,
                "blocking": 1,
                "total": 1,
            },
            "command_ids": ["foundation:unit"],
            "remediation": {
                "prior_attempt_id": None,
                "replayed_finding_ids": [],
                "closed_finding_ids": [],
            },
        }
        self.assertEqual([], list(validator.iter_errors(prospective)))

        invalid = copy.deepcopy(prospective)
        invalid["attempts"][0]["telemetry"]["reviewer"] = "must-not-be-collected"
        self.assertTrue(list(validator.iter_errors(invalid)))
        invalid = copy.deepcopy(prospective)
        invalid["attempts"][0]["telemetry"]["duration_seconds"] = -1
        self.assertTrue(list(validator.iter_errors(invalid)))
        invalid = copy.deepcopy(prospective)
        invalid["attempts"][0]["telemetry"]["command_ids"] = ["C:/private/research.txt"]
        self.assertTrue(list(validator.iter_errors(invalid)))
        invalid = copy.deepcopy(prospective)
        invalid["attempts"][0]["telemetry"]["finding_counts"]["body"] = "forbidden"
        self.assertTrue(list(validator.iter_errors(invalid)))

        invalid = copy.deepcopy(control)
        invalid["attempts"][0]["findings"][0]["severity"] = "urgent"
        self.assertTrue(list(validator.iter_errors(invalid)))
        invalid = copy.deepcopy(control)
        invalid["attempts"][0]["closures"] = [
            {"finding_id": "F01", "disposition": "fixed", "evidence": "evidence.json", "rewrite": True}
        ]
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_amendment_exit_review_control_is_optional_append_only_shaped_and_strict(self) -> None:
        schema = json.loads(self.schema.read_text(encoding="utf-8"))
        completion_schema = schema["$defs"]["waveAmendment"]["properties"]["completion"]
        self.assertEqual(
            "#/$defs/amendmentExitReviewControl",
            completion_schema["properties"]["exit_review_control"]["$ref"],
        )

        legacy = copy.deepcopy(self.canonical)
        for amendment in legacy.get("wave_amendments", []):
            amendment["completion"].pop("exit_review_control", None)
        self.assertEqual([], backlog_schema_errors(legacy, schema_path=self.schema))

        packet = {
            "id": "R01",
            "submitted_by": "agent:implementer",
            "submitted_at": "2026-08-21T03:00:00+00:00",
            "candidate_commit": "b" * 40,
            "declared_candidate_commit": "a" * 40,
            "branch": "codex/amendment-exit",
            "evidence_reference": {
                "type": "amendment-exit-evidence",
                "amendment_id": "W1.A02",
                "path": "artifacts/evidence/W1.A02.exit.json",
                "sha256": "1" * 64,
                "commit": "a" * 40,
            },
            "acceptance_criteria_sha256": "2" * 64,
            "selected_checks": ["python tools/taskctl.py validate"],
            "selected_checks_sha256": "3" * 64,
            "prior_attempt_id": None,
            "open_finding_ids": [],
            "packet_sha256": "4" * 64,
        }
        finding = {
            "id": "W1.A02-EXIT-R01-F01",
            "severity": "high",
            "blocking": True,
            "criterion_index": 1,
            "title": "Exit evidence is not immutable",
            "reproduction": "Substitute the exit evidence after review.",
            "required_remediation": "Bind the exact evidence and candidate.",
        }
        control: dict[str, Any] = {
            "version": 1,
            "attempts": [
                {
                    "submission": packet,
                    "review": {
                        "reviewer": "agent:reviewer",
                        "result": "changes-requested",
                        "reviewed_at": "2026-08-21T04:00:00+00:00",
                        "reviewed_state_commit": "b" * 40,
                        "notes": "One blocking exit finding.",
                    },
                    "ledger": {
                        "path": "artifacts/evidence/W1.A02.exit-review-R01.json",
                        "sha256": "5" * 64,
                    },
                    "findings": [finding],
                    "closures": [],
                }
            ],
            "current_submission": None,
        }
        validator = Draft202012Validator(
            {"$ref": "#/$defs/amendmentExitReviewControl", "$defs": schema["$defs"]},
            format_checker=FormatChecker(),
        )
        self.assertEqual([], list(validator.iter_errors(control)))

        for path, value in (
            (("attempts", 0, "submission", "candidate_commit"), "not-a-commit"),
            (("attempts", 0, "submission", "selected_checks"), []),
            (("attempts", 0, "review", "reviewed_state_commit"), None),
            (("attempts", 0, "findings", 0, "severity"), "urgent"),
        ):
            with self.subTest(path=path):
                invalid = copy.deepcopy(control)
                cursor: Any = invalid
                for key in path[:-1]:
                    cursor = cursor[key]
                cursor[path[-1]] = value
                self.assertTrue(list(validator.iter_errors(invalid)))

        invalid = copy.deepcopy(control)
        invalid["attempts"][0]["review"]["implementation_commit"] = "b" * 40
        self.assertTrue(list(validator.iter_errors(invalid)))

        checkpoint_validator = Draft202012Validator(
            {"$ref": "#/$defs/checkpointEvidenceReferences", "$defs": schema["$defs"]},
            format_checker=FormatChecker(),
        )
        self.assertEqual([], list(checkpoint_validator.iter_errors(["legacy-checkpoint.json"])))
        bound_checkpoint = [
            {
                "type": "amendment-adoption-evidence",
                "amendment_id": "W1.A02",
                "path": "artifacts/evidence/W1.A02.adoption.json",
                "sha256": "6" * 64,
                "commit": "c" * 40,
            }
        ]
        self.assertEqual([], list(checkpoint_validator.iter_errors(bound_checkpoint)))
        bound_checkpoint[0]["raw_review_notes"] = "must remain outside the checkpoint reference"
        self.assertTrue(list(checkpoint_validator.iter_errors(bound_checkpoint)))

    def test_materialized_amendment_task_requires_a_packet_bound_hash(self) -> None:
        data = copy.deepcopy(self.canonical)
        data["control_plane"] = {
            "revision": 2,
            "minimum_tool_revision": 2,
            "active_amendment": None,
        }
        data["wave_amendments"] = [
            {
                "id": "W1.A02",
                "change_request_id": "ECR-0001",
                "target_wave": "W1",
                "kind": "gate-integrity-safety-defect",
                "approval_reference": {
                    "path": "planning/wave-amendment-approvals/W1.A02.json",
                    "sha256": "a" * 64,
                    "introduction_commit": "a" * 40,
                },
                "lifecycle": {
                    "status": "MATERIALIZED",
                    "history": [
                        {
                            "id": "E01",
                            "status": "MATERIALIZED",
                            "actor": "agent:bootstrap",
                            "at": "2026-08-20T00:00:00+00:00",
                            "rationale": "Approved inventory materialized.",
                        }
                    ],
                },
                "bootstrap": {
                    "id": "W1.A02.B00",
                    "status": "APPROVED",
                    "implementer": "agent:bootstrap",
                    "implementation_commit": "b" * 40,
                    "evidence": [],
                    "review": {
                        "reviewer": "agent:reviewer",
                        "result": "approved",
                        "reviewed_at": "2026-08-20T00:00:00+00:00",
                        "notes": None,
                    },
                },
                "campaign": None,
                "tasks": [
                    {
                        "id": "W1.A02.T01",
                        "amendment_id": "W1.A02",
                        "title": "First approved enabler task",
                        "objective": "Exercise packet binding.",
                        "dependencies": ["W1.A02.B00"],
                        "acceptance_criteria": ["The task remains bound to its packet."],
                        "verification_commands": ["python -m unittest"],
                        # packet_task_sha256 is intentionally absent.
                        "status": "NOT_STARTED",
                        "owner": None,
                        "branch": None,
                        "base_sha": None,
                        "worktree": None,
                        "lease": None,
                        "started_at": None,
                        "updated_at": None,
                        "completed_at": None,
                        "blocker": None,
                        "implementation_notes": "",
                        "evidence": [],
                        "verification_state": None,
                        "review": {"reviewer": None, "result": None, "reviewed_at": None, "notes": None},
                    }
                ],
                "completion": {
                    "status": "PENDING",
                    "reviewer": None,
                    "reviewed_at": None,
                    "evidence": [],
                    "notes": None,
                },
            }
        ]

        with self.assertRaisesRegex(
            SystemExit,
            r"wave_amendments\[0\]\.tasks\[0\]: 'packet_task_sha256' is a required property",
        ):
            self.load_copy(data)

    def test_revision_nine_schema_requires_the_exact_second_gcr_generation(self) -> None:
        data = copy.deepcopy(self.canonical)
        data["control_plane"]["revision"] = 9
        data["control_plane"]["minimum_tool_revision"] = 9
        data["control_plane"]["control_generations"] = data["control_plane"]["control_generations"][:2]
        hold = next(item for item in data["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0002")
        hold["supplements"] = hold["supplements"][:1]
        self.assertEqual(9, data["control_plane"]["revision"])
        self.assertEqual(
            ["GCR-0001", "GCR-0002"], [item["id"] for item in data["control_plane"]["control_generations"]]
        )
        self.assertEqual([], backlog_schema_errors(data, schema_path=self.schema))
        self.assertEqual([], taskctl.governance_control_generation_errors(data, None))
        self.assertEqual([], taskctl.recovery_hold_errors(data, None))

        revision_ten = copy.deepcopy(data)
        revision_ten["control_plane"]["revision"] = 10
        revision_ten["control_plane"]["minimum_tool_revision"] = 10
        revision_ten["control_plane"]["control_generations"].append(
            {
                "id": "GCR-0003",
                "bootstrap_id": "GCR-0003.B00",
                "hold_id": "HOLD-W1-GRR-0002",
                "predecessor_revision": 9,
                "successor_revision": 10,
                "supported_control_ceiling": 11,
                "approval_reference": {
                    "path": "planning/governance-control-recovery/GCR-0003.approval.json",
                    "sha256": "a" * 64,
                    "introduction_commit": "b" * 40,
                },
                "review_reference": {
                    "path": "planning/governance-control-recovery/GCR-0003.B00.review-R01.json",
                    "sha256": "c" * 64,
                    "reviewed_state_commit": "d" * 40,
                    "approved_state_commit": "e" * 40,
                },
                "adopted_by": "codex",
                "adopted_at": "2026-08-25T00:00:00+00:00",
            }
        )
        self.assertEqual([], backlog_schema_errors(revision_ten, schema_path=self.schema))
        self.assertEqual([], taskctl.governance_control_generation_errors(revision_ten, None))
        self.assertEqual([], taskctl.recovery_hold_errors(revision_ten, None))

        revision_eleven = copy.deepcopy(revision_ten)
        revision_eleven["control_plane"]["revision"] = 11
        revision_eleven["control_plane"]["minimum_tool_revision"] = 11
        hold = next(
            item for item in revision_eleven["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0002"
        )
        supplement = copy.deepcopy(hold["supplements"][0])
        supplement["id"] = "GRR-0002.S02"
        supplement["predecessor_control_revision"] = 10
        supplement["successor_control_revision"] = 11
        supplement["packet_reference"]["path"] = "planning/governance-recovery-requests/GRR-0002.S02.packet.json"
        supplement["approval_reference"]["path"] = "planning/governance-recovery-approvals/GRR-0002.S02.json"
        supplement["bootstrap"]["id"] = "GRR-0002.B02"
        hold["supplements"].append(supplement)
        self.assertEqual([], backlog_schema_errors(revision_eleven, schema_path=self.schema))
        self.assertEqual([], taskctl.governance_control_generation_errors(revision_eleven, None))
        self.assertEqual([], taskctl.recovery_hold_errors(revision_eleven, None))

        crossed = copy.deepcopy(revision_ten)
        crossed["control_plane"]["control_generations"][2]["predecessor_revision"] = 8
        self.assertTrue(backlog_schema_errors(crossed, schema_path=self.schema))
        missing = copy.deepcopy(revision_ten)
        missing["control_plane"]["control_generations"].pop()
        self.assertTrue(taskctl.governance_control_generation_errors(missing, None))

    def test_revision_twelve_headroom_requires_exact_neutral_gcr7_and_s03(self) -> None:
        data = copy.deepcopy(self.canonical)
        generation = {
            "id": "GCR-0007",
            "bootstrap_id": "GCR-0007.B00",
            "hold_id": "HOLD-W1-GRR-0002",
            "predecessor_revision": 11,
            "successor_revision": 11,
            "supported_control_ceiling": 12,
            "generation_neutral": True,
            "approval_reference": {
                "path": "planning/governance-control-recovery/GCR-0007.approval.json",
                "sha256": "a" * 64,
                "introduction_commit": "b" * 40,
            },
            "review_reference": {
                "path": "planning/governance-control-recovery/GCR-0007.B00.review-R01.json",
                "sha256": "c" * 64,
                "reviewed_state_commit": "d" * 40,
                "approved_state_commit": "e" * 40,
            },
            "adopted_by": "codex",
            "adopted_at": "2026-08-26T00:00:00+00:00",
        }
        data["control_plane"]["control_generations"].append(generation)
        self.assertEqual([], backlog_schema_errors(data, schema_path=self.schema))
        self.assertEqual([], taskctl.governance_control_generation_errors(data, None))
        self.assertEqual([], taskctl.recovery_hold_errors(data, None))

        old_schema = json.loads(
            subprocess.check_output(
                ["git", "show", "8babc35d0d82607a7301bc30189167dd4c0622c9:planning/backlog.schema.json"],
                cwd=REPO,
                text=True,
            )
        )
        self.assertTrue(list(Draft202012Validator(old_schema).iter_errors(data)))

        substituted = copy.deepcopy(data)
        substituted["control_plane"]["control_generations"][-1]["id"] = "GCR-0006"
        self.assertTrue(backlog_schema_errors(substituted, schema_path=self.schema))
        self.assertTrue(taskctl.governance_control_generation_errors(substituted, None))

        revision_twelve = copy.deepcopy(data)
        revision_twelve["control_plane"]["revision"] = 12
        revision_twelve["control_plane"]["minimum_tool_revision"] = 12
        self.assertIn(
            "control revision differs from the latest explicit generation transition",
            taskctl.governance_control_generation_errors(revision_twelve, None),
        )
        hold = next(
            item for item in revision_twelve["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0002"
        )
        supplement = copy.deepcopy(hold["supplements"][-1])
        supplement["id"] = "GRR-0002.S03"
        supplement["predecessor_control_revision"] = 11
        supplement["successor_control_revision"] = 12
        supplement["packet_reference"]["path"] = "planning/governance-recovery-requests/GRR-0002.S03.packet.json"
        supplement["approval_reference"]["path"] = "planning/governance-recovery-approvals/GRR-0002.S03.json"
        supplement["bootstrap"]["id"] = "GRR-0002.B03"
        hold["supplements"].append(supplement)
        self.assertEqual([], backlog_schema_errors(revision_twelve, schema_path=self.schema))
        self.assertEqual([], taskctl.governance_control_generation_errors(revision_twelve, None))
        self.assertEqual([], taskctl.recovery_hold_errors(revision_twelve, None))

    def test_neutral_gcr7_does_not_change_the_w1_a04_postappend_denial(self) -> None:
        before = copy.deepcopy(self.canonical)
        before.setdefault("wave_amendments", []).append({"id": "W1.A04"})
        before_hold = next(
            item for item in before["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0002"
        )
        before_s02 = next(item for item in before_hold["supplements"] if item["id"] == "GRR-0002.S02")
        before_errors, _packet = taskctl.recovery_supplement_authority_errors(
            before,
            REPO,
            before_hold,
            before_s02,
        )

        after = copy.deepcopy(before)
        after["control_plane"]["control_generations"].append(
            {
                "id": "GCR-0007",
                "bootstrap_id": "GCR-0007.B00",
                "hold_id": "HOLD-W1-GRR-0002",
                "predecessor_revision": 11,
                "successor_revision": 11,
                "supported_control_ceiling": 12,
                "generation_neutral": True,
                "approval_reference": {
                    "path": "planning/governance-control-recovery/GCR-0007.approval.json",
                    "sha256": "a" * 64,
                    "introduction_commit": "b" * 40,
                },
                "review_reference": {
                    "path": "planning/governance-control-recovery/GCR-0007.B00.review-R01.json",
                    "sha256": "c" * 64,
                    "reviewed_state_commit": "d" * 40,
                    "approved_state_commit": "e" * 40,
                },
                "adopted_by": "codex",
                "adopted_at": "2026-08-26T00:00:00+00:00",
            }
        )
        after_hold = next(item for item in after["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0002")
        after_s02 = next(item for item in after_hold["supplements"] if item["id"] == "GRR-0002.S02")
        after_errors, _packet = taskctl.recovery_supplement_authority_errors(
            after,
            REPO,
            after_hold,
            after_s02,
        )

        expected = ["GRR-0002.S02: pre-append target amendment was fabricated in backlog state"]
        self.assertEqual(expected, before_errors)
        self.assertEqual(before_errors, after_errors)


if __name__ == "__main__":
    unittest.main()
