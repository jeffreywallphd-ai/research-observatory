from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from taskctl import load, validate  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
