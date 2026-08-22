from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import taskctl  # noqa: E402

TASK_ID = "CAP-02.S04.T03"
HEAD = "8ad2b7a6ed8349d84380dbc36a73d586238a109a"
MANIFEST_RELATIVE = "artifacts/evidence/task-recovery/CAP-02.S04.T03.json"


class ExactTaskRecoveryTests(unittest.TestCase):
    def load_context(self, *, base_sha: str = HEAD):
        data = yaml.safe_load((REPO / "planning/backlog.yaml").read_text(encoding="utf-8"))
        context = taskctl.index_backlog(data)
        data, _capabilities, _slices, _tasks, _gates = context
        amendment = taskctl.wave_amendment_map(data)["W1.A03"]
        amendment["lifecycle"]["status"] = "ADOPTED"
        amendment["completion"]["status"] = "APPROVED"
        amendment["campaign"]["status"] = "COMPLETE"
        amendment["campaign"]["lease"] = None
        hold = next(item for item in data["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0001")
        hold["status"] = "RELEASED"
        wave = taskctl.wave_map(data)["W1"]
        wave["campaign"].update(
            status="ACTIVE",
            scope="wave",
            owner="codex",
            branch="codex/w1-windows-local-runtime",
            worktree=REPO.as_posix(),
            base_sha=base_sha,
            profile="LOC",
            platform="windows-x64",
            lease={
                "claimed_by": "codex",
                "claimed_at": "2026-08-22T20:00:00+00:00",
                "expires_at": "2099-08-23T20:00:00+00:00",
            },
        )
        wave.setdefault("checkpoints", []).append(
            {
                "id": "W1.CP02",
                "kind": "security",
                "recorded_by": "codex",
                "recorded_at": "2026-08-22T20:00:00+00:00",
                "evidence": [
                    {
                        "type": "amendment-adoption-evidence",
                        "amendment_id": "W1.A03",
                        "path": "artifacts/evidence/W1.A03.adoption.json",
                        "sha256": "a" * 64,
                        "commit": HEAD,
                    }
                ],
                "notes": "Bound test checkpoint.",
            }
        )
        return context

    @staticmethod
    def args(
        task: str = TASK_ID,
        *,
        file: Path | None = None,
        base_sha: str = HEAD,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            file=str(file or (REPO / "planning/backlog.yaml")),
            task=task,
            agent="codex",
            branch="codex/w1-windows-local-runtime",
            base_sha=base_sha,
            worktree=str(REPO),
            profile="LOC",
            platform="windows-x64",
            from_file=MANIFEST_RELATIVE,
            lease_hours=8,
        )

    def persisted_args(self, path: Path, data: dict, *, base_sha: str) -> argparse.Namespace:
        document = taskctl.serializable_backlog(data)
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=120),
            encoding="utf-8",
        )
        args = self.args(file=path, base_sha=base_sha)
        args.source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        args.source_identity = taskctl.identity_snapshot(document)
        args.source_amendment_identity = taskctl.amendment_identity_snapshot(document)
        args.source_approved_waves = taskctl.approved_wave_snapshot(document)
        args.source_amendment_history = taskctl.amendment_history_snapshot(document)
        args.source_task_review_history = taskctl.task_review_history_snapshot(document)
        args.source_wave_checkpoint_history = taskctl.wave_checkpoint_history_snapshot(document)
        args.source_recovery_history = taskctl.recovery_history_snapshot(document)
        args.source_task_recovery_history = taskctl.task_recovery_history_snapshot(document)
        args.repo_root = REPO
        return args

    def invoke(self, context, **patches):
        data, capabilities, slices, tasks, gates = context
        manifest_payload = (REPO / MANIFEST_RELATIVE).read_bytes()
        real_git_blob = taskctl.git_blob

        def committed_blob(repo: Path, commit: str, path: str) -> bytes | None:
            if path == MANIFEST_RELATIVE:
                return manifest_payload
            return real_git_blob(repo, commit, path)

        paused_task = taskctl.historical_task(REPO, taskctl.EXACT_T03_RECOVERY["pause_record"], TASK_ID)
        self.assertIsNotNone(paused_task)
        defaults = {
            "git_execution_identity": (
                "codex",
                "codex/w1-windows-local-runtime",
                HEAD,
                REPO.as_posix(),
            ),
            "validate": [],
            "exact_recovery_manifest_errors": [],
            "run_exact_recovery_checks": [],
        }
        defaults.update(patches)
        with (
            patch.object(taskctl, "git_execution_identity", return_value=defaults["git_execution_identity"]),
            patch.object(taskctl, "discover_repository", return_value=REPO),
            patch.object(taskctl, "require_clean_repository"),
            patch.object(taskctl, "validate", return_value=defaults["validate"]),
            patch.object(
                taskctl,
                "historical_task",
                return_value=copy.deepcopy(paused_task),
            ),
            patch.object(taskctl, "git_blob", side_effect=committed_blob),
            patch.object(
                taskctl,
                "exact_recovery_manifest_errors",
                return_value=defaults["exact_recovery_manifest_errors"],
            ),
            patch.object(
                taskctl,
                "run_exact_recovery_checks",
                return_value=defaults["run_exact_recovery_checks"],
            ),
            patch.object(taskctl, "persist") as persist,
        ):
            taskctl.command_recover(self.args(), data, capabilities, slices, tasks, gates)
        return persist

    def test_manifest_matches_schema_and_exact_repository_lineage(self) -> None:
        schema = json.loads(
            (REPO / "planning/enabler-change-requests/task-recovery-manifest.schema.json").read_text(encoding="utf-8")
        )
        manifest = json.loads((REPO / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(manifest)
        data, _capabilities, _slices, tasks, _gates = taskctl.load(str(REPO / "planning/backlog.yaml"))
        self.assertEqual(
            [],
            taskctl.exact_recovery_manifest_errors(
                data,
                tasks[TASK_ID],
                manifest,
                REPO,
                require_current_candidate_bytes=True,
            ),
        )

    def test_parser_exposes_recovery_without_bypassing_the_active_hold(self) -> None:
        parsed = taskctl.build_parser().parse_args(
            [
                "recover",
                TASK_ID,
                "--agent",
                "codex",
                "--branch",
                "codex/w1-windows-local-runtime",
                "--base-sha",
                HEAD,
                "--worktree",
                str(REPO),
                "--from",
                MANIFEST_RELATIVE,
            ]
        )
        data, _capabilities, _slices, tasks, _gates = taskctl.load(str(REPO / "planning/backlog.yaml"))
        if not taskctl.active_recovery_holds(data):
            data = copy.deepcopy(data)
            hold = data["control_plane"]["recovery_holds"][-1]
            hold["status"] = "ACTIVE"
            hold["released_at"] = None
        with self.assertRaisesRegex(SystemExit, "Governance recovery hold"):
            taskctl.require_recovery_hold_permission(parsed, data, tasks, REPO)

    def test_lawful_transition_changes_only_recovery_execution_projection(self) -> None:
        context = self.load_context()
        task = context[3][TASK_ID]
        before = copy.deepcopy(task)
        persist = self.invoke(context)

        persist.assert_called_once()
        self.assertEqual("IN_PROGRESS", task["status"])
        self.assertEqual(HEAD, task["base_sha"])
        self.assertIsNone(task["blocker"])
        self.assertEqual("codex", task["lease"]["claimed_by"])
        self.assertEqual(taskctl.task_recovery_boundary(before), task["recovery_control"]["original_blocked_state"])
        self.assertEqual([], task["evidence"])
        self.assertIsNone(task["review"]["result"])
        self.assertIsNone(task["verification_state"])
        self.assertEqual(
            "59079efccc122a7d56a9f18efc20030851bf32a9",
            task["recovery_control"]["historical"]["candidate"],
        )
        self.assertEqual([], taskctl.backlog_schema_errors(taskctl.serializable_backlog(context[0])))
        self.assertEqual([], taskctl.task_recovery_projection_errors(context[0], task, REPO))

    def test_recovery_uses_real_atomic_persistence_for_one_task_only(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        context = self.load_context(base_sha=head)
        before = taskctl.serializable_backlog(context[0])
        before_tasks = taskctl.index_backlog(copy.deepcopy(before))[3]
        before_task = copy.deepcopy(before_tasks[TASK_ID])

        with tempfile.TemporaryDirectory() as temp:
            backlog_path = Path(temp) / "backlog.yaml"
            args = self.persisted_args(backlog_path, context[0], base_sha=head)
            real_save_atomic = taskctl.save_atomic
            with (
                patch.object(
                    taskctl,
                    "git_execution_identity",
                    return_value=("codex", "codex/w1-windows-local-runtime", head, REPO.as_posix()),
                ),
                patch.object(taskctl, "discover_repository", return_value=REPO),
                patch.object(taskctl, "require_clean_repository"),
                patch.object(taskctl, "validate", return_value=[]),
                patch.object(taskctl, "run_exact_recovery_checks", return_value=[]),
                patch.object(taskctl, "save_atomic", wraps=real_save_atomic) as save_atomic,
            ):
                taskctl.command_recover(args, *context)

            save_atomic.assert_called_once()
            after = yaml.safe_load(backlog_path.read_text(encoding="utf-8"))

        after_tasks = taskctl.index_backlog(copy.deepcopy(after))[3]
        changed_task_ids = sorted(task_id for task_id in before_tasks if before_tasks[task_id] != after_tasks[task_id])
        self.assertEqual([TASK_ID], changed_task_ids)
        after_task = after_tasks[TASK_ID]
        self.assertEqual("IN_PROGRESS", after_task["status"])
        self.assertEqual(before_task, after_task["recovery_control"]["original_blocked_state"])
        self.assertEqual(before_task["blocker"], after_task["recovery_control"]["original_blocked_state"]["blocker"])
        self.assertEqual(before_task["evidence"], after_task["evidence"])
        self.assertEqual(before_task["review"], after_task["review"])
        self.assertEqual(before["wave_amendments"], after["wave_amendments"])
        self.assertEqual(before["waves"], after["waves"])
        self.assertEqual(before["release_gates"], after["release_gates"])

    def test_real_atomic_persistence_rejects_a_competing_writer_without_overwrite(self) -> None:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        context = self.load_context(base_sha=head)
        with tempfile.TemporaryDirectory() as temp:
            backlog_path = Path(temp) / "backlog.yaml"
            args = self.persisted_args(backlog_path, context[0], base_sha=head)
            competing_bytes: bytes | None = None

            def competing_write(_repo: Path) -> list[str]:
                nonlocal competing_bytes
                competing_bytes = backlog_path.read_bytes() + b"\n# competing writer\n"
                backlog_path.write_bytes(competing_bytes)
                return []

            real_save_atomic = taskctl.save_atomic
            with (
                patch.object(
                    taskctl,
                    "git_execution_identity",
                    return_value=("codex", "codex/w1-windows-local-runtime", head, REPO.as_posix()),
                ),
                patch.object(taskctl, "discover_repository", return_value=REPO),
                patch.object(taskctl, "require_clean_repository"),
                patch.object(taskctl, "validate", return_value=[]),
                patch.object(taskctl, "run_exact_recovery_checks", side_effect=competing_write),
                patch.object(taskctl, "save_atomic", wraps=real_save_atomic) as save_atomic,
                self.assertRaisesRegex(SystemExit, "Backlog changed after taskctl loaded it"),
            ):
                taskctl.command_recover(args, *context)

            save_atomic.assert_called_once()
            self.assertIsNotNone(competing_bytes)
            self.assertEqual(competing_bytes, backlog_path.read_bytes())

    def test_authority_and_state_denials_are_atomic(self) -> None:
        cases = {
            "unadopted amendment": lambda context: taskctl.wave_amendment_map(context[0])["W1.A03"]["lifecycle"].update(
                status="ACTIVE"
            ),
            "unreleased hold": lambda context: next(
                item for item in context[0]["control_plane"]["recovery_holds"] if item["id"] == "HOLD-W1-GRR-0001"
            ).update(status="ACTIVE"),
            "paused Wave": lambda context: taskctl.wave_map(context[0])["W1"]["campaign"].update(status="PAUSED"),
            "wrong Wave scope": lambda context: taskctl.wave_map(context[0])["W1"]["campaign"].update(
                scope="amendment-hold"
            ),
            "duplicate recovery": lambda context: context[3][TASK_ID].update(recovery_control={}),
            "altered blocker": lambda context: context[3][TASK_ID]["blocker"].update(reason="rewritten"),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                context = self.load_context()
                mutate(context)
                task = context[3][TASK_ID]
                before = copy.deepcopy(task)
                with self.assertRaises(SystemExit):
                    self.invoke(context)
                self.assertEqual(before, task)

    def test_wrong_task_stale_dirty_predecessor_and_failed_check_are_atomic(self) -> None:
        context = self.load_context()
        before = copy.deepcopy(context[3][TASK_ID])
        with self.assertRaisesRegex(SystemExit, "authorized only"):
            taskctl.command_recover(self.args("CAP-02.S04.T02"), *context)
        self.assertEqual(before, context[3][TASK_ID])

        for label, target, error in (
            ("stale", "git_execution_identity", SystemExit("Base SHA must equal the current Git HEAD")),
            ("dirty", "require_clean_repository", SystemExit("Tracked worktree changes exist")),
        ):
            with self.subTest(label=label):
                context = self.load_context()
                task = context[3][TASK_ID]
                before = copy.deepcopy(task)
                with patch.object(taskctl, target, side_effect=error), self.assertRaises(SystemExit):
                    taskctl.command_recover(self.args(), *context)
                self.assertEqual(before, task)

        for label, invoke_kwargs in (
            ("manifest mismatch", {"exact_recovery_manifest_errors": ["hash mismatch"]}),
            ("failed recomputation", {"run_exact_recovery_checks": ["privacy check failed"]}),
        ):
            with self.subTest(label=label):
                context = self.load_context()
                task = context[3][TASK_ID]
                before = copy.deepcopy(task)
                with self.assertRaises(SystemExit):
                    self.invoke(context, **invoke_kwargs)
                self.assertEqual(before, task)

    def test_amendment_and_target_contract_rewrites_are_atomic_denials(self) -> None:
        context = self.load_context()
        amendment = taskctl.wave_amendment_map(context[0])["W1.A03"]
        amendment["tasks"][0]["title"] = "FORGED PREDECESSOR TITLE"
        before = copy.deepcopy(context[3][TASK_ID])
        with self.assertRaisesRegex(SystemExit, "immutable amendment task field title"):
            self.invoke(context)
        self.assertEqual(before, context[3][TASK_ID])

        context = self.load_context()
        task = context[3][TASK_ID]
        task["acceptance_criteria"][0] = "FORGED TARGET CRITERION"
        before = copy.deepcopy(task)
        with self.assertRaisesRegex(SystemExit, "immutable blocked/pause boundary"):
            self.invoke(context)
        self.assertEqual(before, task)

    def test_generic_validation_and_manifest_reject_static_contract_rewrites(self) -> None:
        context = self.load_context()
        amendment = taskctl.wave_amendment_map(context[0])["W1.A03"]
        amendment["tasks"][0]["title"] = "FORGED PREDECESSOR TITLE"
        errors = taskctl.validate(*context, repo=REPO)
        self.assertTrue(any("immutable amendment task field title" in error for error in errors), errors)

        data, _capabilities, _slices, tasks, _gates = taskctl.load(str(REPO / "planning/backlog.yaml"))
        task = tasks[TASK_ID]
        task["acceptance_criteria"][0] = "FORGED TARGET CRITERION"
        manifest = json.loads((REPO / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        errors = taskctl.exact_recovery_manifest_errors(
            data,
            task,
            manifest,
            REPO,
            require_current_candidate_bytes=True,
        )
        self.assertIn("current T03 immutable task contract differs from the exact pause record", errors)

    def test_manifest_tampering_is_rejected(self) -> None:
        data, _capabilities, _slices, tasks, _gates = taskctl.load(str(REPO / "planning/backlog.yaml"))
        canonical = json.loads((REPO / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        mutations = {
            "wrong task": lambda item: item.update(taskId="CAP-02.S04.T02"),
            "wrong authority": lambda item: item["authority"].update(amendmentId="W1.A02"),
            "wrong commit": lambda item: item["commits"].update(candidate="0" * 40),
            "wrong path set": lambda item: item["changedPaths"].pop(),
            "wrong evidence hash": lambda item: item["uiEvidence"].update(sha256="0" * 64),
            "wrong reference": lambda item: item["uiEvidence"].update(referenceId="forged"),
            "duplicate checks": lambda item: item["selectedChecks"].append(copy.deepcopy(item["selectedChecks"][0])),
            "unverified residual": lambda item: item["unverifiedItems"].append("not verified"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                manifest = copy.deepcopy(canonical)
                mutate(manifest)
                self.assertTrue(
                    taskctl.exact_recovery_manifest_errors(
                        data,
                        tasks[TASK_ID],
                        manifest,
                        REPO,
                        require_current_candidate_bytes=True,
                    )
                )

    def test_recovery_projection_history_cannot_be_rewritten(self) -> None:
        context = self.load_context()
        self.invoke(context)
        snapshot = taskctl.task_recovery_history_snapshot(context[0])
        context[3][TASK_ID]["recovery_control"]["historical"]["candidate"] = "0" * 40
        with self.assertRaisesRegex(SystemExit, "Append-only task recovery history changed"):
            taskctl.save_validated(
                str(REPO / "planning/backlog.yaml"),
                context[0],
                expected_task_recovery_history=snapshot,
            )


if __name__ == "__main__":
    unittest.main()
