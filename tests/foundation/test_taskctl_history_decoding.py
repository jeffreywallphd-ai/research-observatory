"""Immutable historical facts, fresh decisions and bounded invocation lifetime."""

from __future__ import annotations

import copy
import datetime as dt
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from contextvars import copy_context
from pathlib import Path
from threading import Thread
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import taskctl  # noqa: E402


class HistoricalDecodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="history-decode-", dir=ROOT / "artifacts/tmp")
        self.repo = Path(self.temporary.name).resolve(strict=True)
        self.repo.relative_to((ROOT / "artifacts/tmp").resolve(strict=True))
        self.git("init", "--quiet")
        (self.repo / "planning").mkdir()
        self.backlog = self.repo / "planning/backlog.yaml"
        self.payload = b"waves:\n- id: W3\n  approval:\n    status: APPROVED\n    choices: [original]\n"
        self.commit = self.commit_bytes(self.payload)
        self.empty: dict[str, Any] = {
            "capabilities": [],
            "gates": [],
            "waves": [],
            "wave_amendments": [],
            "recovery_holds": [],
        }

    def tearDown(self):
        # Verify the exact owned cleanup target before recursive TemporaryDirectory cleanup.
        self.repo.resolve(strict=True).relative_to((ROOT / "artifacts/tmp").resolve(strict=True))
        self.temporary.cleanup()

    def git(self, *args):
        return (
            subprocess.check_output(["git", "--no-optional-locks", "-c", "core.autocrlf=false", *args], cwd=self.repo)
            .decode()
            .strip()
        )

    def commit_bytes(self, payload):
        self.backlog.write_bytes(payload)
        self.git("add", "planning/backlog.yaml")
        self.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "historical fixture",
        )
        return self.git("rev-parse", "HEAD")

    def invoke(self, callback):
        # Exercise the actual CLI scope without invoking unrelated whole-repository controls.
        with (
            patch.object(sys, "argv", ["taskctl", "--file", str(self.backlog), "status"]),
            patch.object(taskctl, "load", side_effect=lambda _path: taskctl.index_backlog(copy.deepcopy(self.empty))),
            patch.object(taskctl, "command_status", side_effect=lambda *_args: callback()),
            redirect_stdout(io.StringIO()),
        ):
            taskctl.main()

    def read_document(self, repo: Path, commit: str) -> dict[str, Any]:
        document = taskctl.historical_backlog_document(repo, commit)
        assert document is not None, "The positive historical fixture must decode"
        return document

    def read_pair(self):
        approval = taskctl.historical_wave_approval(self.repo, self.commit, "W3")
        assert approval is not None
        document = self.read_document(self.repo, self.commit)
        self.assertEqual(approval, document["waves"][0]["approval"])
        return approval, document

    def test_one_cli_decodes_same_immutable_facts_once_and_isolates_callers(self):
        real = taskctl.yaml.safe_load

        def work():
            approval, document = self.read_pair()
            approval["choices"].append("caller-only")
            document["waves"][0]["approval"]["status"] = "caller-only"
            later, _ = self.read_pair()
            self.assertEqual(later, {"status": "APPROVED", "choices": ["original"]})

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 1, "One immutable snapshot is repeatedly decoded within one CLI")

    def test_separate_clis_and_unscoped_calls_do_not_share_decoded_facts(self):
        real = taskctl.yaml.safe_load
        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(self.read_pair)
            self.invoke(self.read_pair)
            self.read_pair()
        self.assertEqual(parse.call_count, 4)

    def test_exception_discards_scope_and_next_cli_redecodes(self):
        real = taskctl.yaml.safe_load

        def failing():
            self.read_pair()
            raise RuntimeError("deliberate command failure")

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            with self.assertRaisesRegex(RuntimeError, "deliberate command failure"):
                self.invoke(failing)
            self.invoke(self.read_pair)
        self.assertEqual(parse.call_count, 2)

    def test_same_scope_still_executes_each_current_validation_and_denial(self):
        real = taskctl.yaml.safe_load
        calls = []
        data = copy.deepcopy(self.empty)

        def authority(current, _repo):
            self.read_pair()
            calls.append(current.get("deliberateDenial", False))
            return ["fresh current authority denial"] if current.get("deliberateDenial") else []

        def work():
            with patch.object(taskctl, "wave_authority_errors", side_effect=authority):
                first = taskctl.validate(data, {}, {}, {}, {})
                data["deliberateDenial"] = True
                second = taskctl.validate(data, {}, {}, {}, {})
            self.assertNotIn("fresh current authority denial", first)
            self.assertIn("fresh current authority denial", second)

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(calls, [False, True], "Validators must run again against current input")
        self.assertEqual(parse.call_count, 1, "Only decoded immutable facts may be shared")

    def test_aliases_and_cycles_are_preserved_but_not_shared_between_callers(self):
        self.commit = self.commit_bytes(self.payload + b"left: &shared [one]\nright: *shared\ncycle: &cycle [*cycle]\n")
        real = taskctl.yaml.safe_load

        def work():
            first = self.read_document(self.repo, self.commit)
            self.assertIs(first["left"], first["right"])
            self.assertIs(first["cycle"], first["cycle"][0])
            first["left"].append("caller-only")
            second = self.read_document(self.repo, self.commit)
            self.assertEqual(second["left"], ["one"])
            self.assertIs(second["left"], second["right"])
            self.assertIs(second["cycle"], second["cycle"][0])
            self.assertIsNot(first["left"], second["left"])

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 1)

    def test_nonimmutable_aliases_retain_fresh_decode_behavior(self):
        real = taskctl.yaml.safe_load

        def work():
            first = self.read_document(self.repo, "HEAD")
            second = self.read_document(self.repo, "HEAD")
            self.assertEqual(first, second)
            self.assertIsNot(first, second)

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 2)

    def test_malformed_and_nonmapping_history_keep_existing_failure_behavior(self):
        for payload in (b"waves: [", b"[]", b"null", b"\xff"):
            with self.subTest(payload=payload):
                commit = self.commit_bytes(payload)

                def work(commit=commit, payload=payload):
                    self.assertIsNone(taskctl.historical_backlog_document(self.repo, commit))
                    self.assertIsNone(taskctl.historical_backlog_document(self.repo, commit))
                    if payload in (b"[]", b"null"):
                        with self.assertRaises(AttributeError):
                            taskctl.historical_wave_approval(self.repo, commit, "W3")
                    else:
                        self.assertIsNone(taskctl.historical_wave_approval(self.repo, commit, "W3"))

                self.invoke(work)

    def test_copied_context_cannot_extend_completed_invocation_lifetime(self):
        saved = []
        real = taskctl.yaml.safe_load

        def work():
            self.read_pair()
            saved.append(copy_context())

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
            self.assertEqual(parse.call_count, 1)
            saved[0].run(self.read_pair)
        self.assertEqual(parse.call_count, 3, "Copied context must not retain a completed invocation's facts")

    def test_copied_context_on_another_thread_does_not_share_fact_state(self):
        real = taskctl.yaml.safe_load
        failures = []

        def work():
            self.read_pair()
            context = copy_context()

            def target():
                try:
                    context.run(self.read_pair)
                except BaseException as exc:
                    failures.append(exc)

            thread = Thread(target=target)
            thread.start()
            thread.join()
            self.read_pair()

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(failures, [])
        self.assertEqual(parse.call_count, 3)

    def test_entry_eviction_reparses_without_changing_returned_facts(self):
        old = self.commit
        newer = self.commit_bytes(self.payload.replace(b"APPROVED", b"CHANGES_REQUESTED"))
        real = taskctl.yaml.safe_load

        def work():
            for commit, status in ((old, "APPROVED"), (newer, "CHANGES_REQUESTED"), (old, "APPROVED")):
                document = self.read_document(self.repo, commit)
                self.assertEqual(document["waves"][0]["approval"]["status"], status)

        with (
            patch.object(taskctl, "_HISTORY_FACT_ENTRIES", 1),
            patch.object(taskctl.yaml, "safe_load", wraps=real) as parse,
        ):
            self.invoke(work)
        self.assertEqual(parse.call_count, 3)

    def test_retained_graph_and_raw_bounds_bypass_instead_of_rejecting_valid_history(self):
        expanded = self.payload + b"integers: [" + b",".join(str(number).encode() for number in range(200)) + b"]\n"
        self.assertLess(len(expanded), 2000)
        self.commit = self.commit_bytes(expanded)
        real = taskctl.yaml.safe_load
        for bound, limit in (("_HISTORY_FACT_BYTES", 2000), ("_HISTORY_FACT_RAW_BYTES", 1)):
            with self.subTest(bound=bound):

                def work():
                    first = self.read_document(self.repo, self.commit)
                    second = self.read_document(self.repo, self.commit)
                    self.assertEqual(first, second)
                    self.assertEqual(first["integers"], list(range(200)))

                with patch.object(taskctl, bound, limit), patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
                    self.invoke(work)
                self.assertEqual(parse.call_count, 2)

    def test_payload_digest_is_part_of_fact_identity_even_for_same_commit(self):
        alternative = self.payload.replace(b"APPROVED", b"CHANGES_REQUESTED")
        real = taskctl.yaml.safe_load

        def work():
            with patch.object(taskctl, "git_blob", side_effect=[self.payload, alternative, self.payload]):
                first = self.read_document(self.repo, self.commit)
                second = self.read_document(self.repo, self.commit)
                third = self.read_document(self.repo, self.commit)
            self.assertEqual(first["waves"][0]["approval"]["status"], "APPROVED")
            self.assertEqual(second["waves"][0]["approval"]["status"], "CHANGES_REQUESTED")
            self.assertEqual(third, first)

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 2)

    def test_missing_result_is_not_added_to_decoded_fact_cache(self):
        real = taskctl.yaml.safe_load

        def work():
            with patch.object(taskctl, "git_blob", side_effect=[None, self.payload]):
                self.assertIsNone(taskctl.historical_backlog_document(self.repo, self.commit))
                self.assertEqual(self.read_document(self.repo, self.commit)["waves"][0]["id"], "W3")

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 1)

    def test_distinct_repository_identity_does_not_share_decoded_template(self):
        other = self.repo / "other"
        self.git("clone", "--quiet", "--no-hardlinks", str(self.repo), str(other))
        real = taskctl.yaml.safe_load

        def work():
            first = self.read_document(self.repo, self.commit)
            second = self.read_document(other, self.commit)
            self.assertEqual(first, second)

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 2)

    def test_actual_current_control_policy_denial_is_recomputed(self):
        data = copy.deepcopy(self.empty)

        def work():
            self.read_pair()
            first = taskctl.validate(data, {}, {}, {}, {})
            data["control_plane"] = {"revision": 999, "minimum_tool_revision": 999}
            second = taskctl.validate(data, {}, {}, {}, {})
            self.assertNotIn("control plane revision is missing or unsupported", first)
            self.assertIn("control plane revision is missing or unsupported", second)
            self.read_pair()

        real = taskctl.yaml.safe_load
        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 1)

    def test_raw_bound_includes_exact_limit_and_bypasses_only_above(self):
        real = taskctl.yaml.safe_load
        for limit, expected in ((len(self.payload) - 1, 2), (len(self.payload), 1), (len(self.payload) + 1, 1)):
            with self.subTest(limit=limit):
                with (
                    patch.object(taskctl, "_HISTORY_FACT_RAW_BYTES", limit),
                    patch.object(taskctl.yaml, "safe_load", wraps=real) as parse,
                ):
                    self.invoke(self.read_pair)
                self.assertEqual(parse.call_count, expected)

    def test_deepcopy_recursion_fallback_returns_fresh_accepted_data(self):
        real = taskctl.yaml.safe_load
        real_copy = taskctl.copy.deepcopy
        for warm in (False, True):
            with self.subTest(warm=warm):

                def work(warm=warm):
                    if warm:
                        taskctl.historical_backlog_document(self.repo, self.commit)
                    with patch.object(taskctl.copy, "deepcopy", side_effect=RecursionError("deliberate copy limit")):
                        first = self.read_document(self.repo, self.commit)
                    first["waves"][0]["approval"]["status"] = "caller-only"
                    second = self.read_document(self.repo, self.commit)
                    self.assertEqual(second["waves"][0]["approval"]["status"], "APPROVED")
                    self.assertEqual(real_copy(second), second)

                with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
                    self.invoke(work)
                self.assertEqual(parse.call_count, 2)

    def test_retained_byte_eviction_and_entry_recency_preserve_facts(self):
        expanded = (
            self.payload + b"items: [" + b",".join(f"item{number:06d}".encode() for number in range(128)) + b"]\n"
        )
        first = self.commit_bytes(expanded)
        second = self.commit_bytes(expanded.replace(b"APPROVED", b"CHANGES_REQUESTED"))
        third = self.commit_bytes(expanded.replace(b"APPROVED", b"PENDING"))
        real = taskctl.yaml.safe_load

        def read(commit, expected):
            document = self.read_document(self.repo, commit)
            self.assertEqual(document["waves"][0]["approval"]["status"], expected)

        def byte_work():
            read(first, "APPROVED")
            read(first, "APPROVED")
            read(second, "CHANGES_REQUESTED")
            read(first, "APPROVED")

        with (
            patch.object(taskctl, "_HISTORY_FACT_BYTES", 16384),
            patch.object(taskctl.yaml, "safe_load", wraps=real) as parse,
        ):
            self.invoke(byte_work)
        self.assertEqual(parse.call_count, 3, "One in-budget template fits; combined retained graphs must evict")

        def recency_work():
            read(first, "APPROVED")
            read(second, "CHANGES_REQUESTED")
            read(first, "APPROVED")
            read(third, "PENDING")
            read(first, "APPROVED")
            read(second, "CHANGES_REQUESTED")

        with (
            patch.object(taskctl, "_HISTORY_FACT_ENTRIES", 2),
            patch.object(taskctl.yaml, "safe_load", wraps=real) as parse,
        ):
            self.invoke(recency_work)
        self.assertEqual(parse.call_count, 4)

    def test_non_utc_yaml_timestamp_bypasses_cache_and_preserves_values(self):
        self.commit = self.commit_bytes(self.payload + b"observed_at: 2026-10-17T12:30:45+05:45\n")
        real = taskctl.yaml.safe_load

        def work():
            first = self.read_document(self.repo, self.commit)
            second = self.read_document(self.repo, self.commit)
            self.assertEqual(first["observed_at"].utcoffset(), dt.timedelta(hours=5, minutes=45))
            self.assertEqual(first, second)
            first["waves"][0]["approval"]["choices"].append("caller-only")
            self.assertEqual(second["waves"][0]["approval"]["choices"], ["original"])

        with patch.object(taskctl.yaml, "safe_load", wraps=real) as parse:
            self.invoke(work)
        self.assertEqual(parse.call_count, 2, "Referenced timezone objects require uncached fallback")


if __name__ == "__main__":
    unittest.main(verbosity=2)
