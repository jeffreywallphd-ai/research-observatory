from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleProblem, ProjectLifecycleService  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    APPLICATION_ID,
    database_integrity_report,
    open_canonical_database,
)

TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
TRACE = "a" * 32


class ProjectLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-project-lifecycle-")
        self.parent = Path(self.temporary.name).resolve(strict=True)
        self.service = ProjectLifecycleService()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create(self, name: str = "study-one"):
        return self.service.create(
            parent_directory=str(self.parent),
            directory_name=name,
            display_name="Study One",
            template_id="theory-synthesis",
            trace_id=TRACE,
        )

    @staticmethod
    def package_bytes(root: Path) -> dict[str, bytes]:
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def test_create_publishes_exact_relocatable_package_and_schema_valid_records(self) -> None:
        projection = self.create()
        root = Path(projection.root)
        self.assertTrue(root.is_dir())
        self.assertEqual(
            sorted(path.name for path in root.iterdir()),
            [
                ".locks",
                ".tmp",
                "cache",
                "config",
                "exports",
                "indexes",
                "logs",
                "models",
                "objects",
                "project.ro.json",
                "state",
            ],
        )
        profile = json.loads((root / "config" / "project-profile.json").read_text(encoding="utf-8"))
        event = json.loads((root / "logs" / "project-lifecycle.jsonl").read_text(encoding="utf-8").splitlines()[0])
        contract = REPO / "packages" / "contracts" / "project"
        for value, schema_name in (
            (profile, "project-profile.schema.json"),
            (event, "project-lifecycle-event.schema.json"),
        ):
            schema = json.loads((contract / schema_name).read_text(encoding="utf-8"))
            self.assertEqual([], list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)))
        self.assertNotIn("root", profile)
        self.assertNotIn(str(root), json.dumps(event))
        self.assertNotIn("Study One", json.dumps(event))
        self.assertFalse(any(path.name.startswith(".study-one.ro-staging-") for path in self.parent.iterdir()))

        database = root / "state" / "project.sqlite3"
        connection = open_canonical_database(database, expected_project_id=projection.project_id)
        try:
            report = database_integrity_report(connection, expected_project_id=projection.project_id)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual("sqlite-wal-v1", report.profile_id)
        finally:
            connection.close()

    def test_open_rejects_mismatched_database_before_lock_or_audit_mutation(self) -> None:
        project = self.create()
        root = Path(project.root)
        database = root / "state" / "project.sqlite3"
        before_manifest = (root / "project.ro.json").read_bytes()
        before_audit = (root / "logs" / "project-lifecycle.jsonl").read_bytes()
        raw = sqlite3.connect(database, autocommit=True)
        raw.execute(f"PRAGMA application_id={APPLICATION_ID + 1}")
        raw.close()

        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-DAMAGED"):
            self.service.open(root=project.root, trace_id=TRACE)
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-DAMAGED"):
            self.service.archive(root=project.root, trace_id=TRACE)
        self.assertFalse((root / ".locks" / "session.lock").exists())
        self.assertEqual(before_manifest, (root / "project.ro.json").read_bytes())
        self.assertEqual(before_audit, (root / "logs" / "project-lifecycle.jsonl").read_bytes())

    def test_open_is_exclusive_close_is_owned_and_restart_can_reopen(self) -> None:
        project = self.create()
        opened = self.service.open(root=project.root, trace_id=TRACE)
        self.assertTrue(opened.open)
        self.assertEqual("read-write", opened.access_mode)
        self.assertEqual("compatible", opened.compatibility_state)
        lock_path = Path(project.root) / ".locks" / "session.lock"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        schema = json.loads(
            (REPO / "packages" / "contracts" / "project" / "project-lock.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual([], list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(lock)))
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-ALREADY-OPEN"):
            self.service.open(root=project.root, trace_id=TRACE)
        competing = ProjectLifecycleService()
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-ALREADY-OPEN"):
            competing.open(root=project.root, trace_id=TRACE)
        closed = self.service.close(root=project.root, trace_id=TRACE)
        self.assertFalse(closed.open)
        self.assertFalse(lock_path.exists())
        reopened = competing.open(root=project.root, trace_id=TRACE)
        self.assertTrue(reopened.open)
        competing.close(root=project.root, trace_id=TRACE)

    def test_archive_restores_and_delete_requires_exact_confirmation_without_shared_cache_effect(self) -> None:
        project = self.create()
        archived = self.service.archive(root=project.root, trace_id=TRACE)
        self.assertEqual(archived.lifecycle_state, "archived")
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-NOT-ACTIVE"):
            self.service.open(root=project.root, trace_id=TRACE)
        restored = self.service.restore(root=project.root, trace_id=TRACE)
        self.assertEqual(restored.lifecycle_state, "active")
        self.assertEqual(restored.revision, 2)

        shared_cache = self.parent / "shared-model-cache"
        shared_cache.mkdir()
        sentinel = shared_cache / "model.bin"
        sentinel.write_bytes(b"shared-model")
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-DELETE-CONFIRMATION-INVALID"):
            self.service.delete(root=project.root, confirmation="delete:wrong", trace_id=TRACE)
        self.assertTrue(Path(project.root).is_dir())
        trashed = self.service.delete(root=project.root, confirmation=project.delete_confirmation, trace_id=TRACE)
        self.assertEqual(trashed.lifecycle_state, "trash")
        self.assertFalse(Path(project.root).exists())
        self.assertTrue(Path(trashed.root).is_dir())
        self.assertEqual(sentinel.read_bytes(), b"shared-model")

    def test_invalid_paths_and_existing_targets_fail_without_publishing_staging_content(self) -> None:
        (self.parent / "already-there").mkdir()
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-ALREADY-EXISTS"):
            self.create("already-there")
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"):
            self.service.create(
                parent_directory=str(self.parent),
                directory_name="../escape",
                display_name="Escape",
                template_id="theory-synthesis",
                trace_id=TRACE,
            )
        self.assertFalse(any(path.name.startswith(".already-there.ro-staging-") for path in self.parent.iterdir()))

    def test_open_rejects_redirectable_layout_and_malformed_manifest_contracts(self) -> None:
        project = self.create()
        root = Path(project.root)
        (root / "unexpected-root-entry").write_text("untrusted", encoding="utf-8")
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"):
            self.service.open(root=project.root, trace_id=TRACE)
        (root / "unexpected-root-entry").unlink()

        manifest_path = root / "project.ro.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["databaseProfile"] = "unapproved-database"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-DAMAGED"):
            self.service.open(root=project.root, trace_id=TRACE)

    def test_newer_and_older_projects_open_read_only_without_mutating_package_bytes(self) -> None:
        for name, fixture_name, compatibility, recovery_action in (
            (
                "newer-project",
                "newer-unsupported-project-manifest.v2.json",
                "newer-unsupported",
                "backup-then-use-compatible-application",
            ),
            (
                "older-project",
                "migration-required-project-manifest.v0.json",
                "migration-required",
                "backup-then-migrate",
            ),
        ):
            project = self.create(name)
            root = Path(project.root)
            manifest_path = root / "project.ro.json"
            fixture = REPO / "packages" / "contracts" / "project" / "fixtures" / fixture_name
            manifest_path.write_bytes(fixture.read_bytes())
            before = self.package_bytes(root)

            opened = self.service.open(root=project.root, trace_id=TRACE)
            self.assertTrue(opened.open)
            self.assertEqual("read-only", opened.access_mode)
            self.assertEqual(compatibility, opened.compatibility_state)
            self.assertTrue(opened.backup_required_before_repair)
            self.assertEqual(recovery_action, opened.recovery_action)
            self.assertEqual(before, self.package_bytes(root))
            self.assertFalse((root / ".locks" / "session.lock").exists())
            with self.assertRaisesRegex(
                ProjectLifecycleProblem,
                "RO-CORE-PROJECT-NEWER-UNSUPPORTED|RO-CORE-PROJECT-MIGRATION-REQUIRED",
            ):
                self.service.archive(root=project.root, trace_id=TRACE)
            self.assertEqual(before, self.package_bytes(root))

            closed = self.service.close(root=project.root, trace_id=TRACE)
            self.assertFalse(closed.open)
            self.assertEqual("closed", closed.access_mode)
            self.assertEqual(before, self.package_bytes(root))

            restarted = ProjectLifecycleService()
            reopened = restarted.open(root=project.root, trace_id=TRACE)
            self.assertEqual("read-only", reopened.access_mode)
            restarted.shutdown()
            self.assertEqual(before, self.package_bytes(root))

    def test_application_compatibility_range_can_force_read_only_without_format_mutation(self) -> None:
        project = self.create("future-application")
        root = Path(project.root)
        manifest_path = root / "project.ro.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["applicationCompatibility"] = {"minimum": "0.2.0", "maximumExclusive": "1.0.0"}
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        before = self.package_bytes(root)
        opened = self.service.open(root=project.root, trace_id=TRACE)
        self.assertEqual("newer-unsupported", opened.compatibility_state)
        self.assertEqual("read-only", opened.access_mode)
        self.assertEqual(before, self.package_bytes(root))

    def test_damaged_and_incomplete_projects_fail_without_mutation_and_name_backup_first_recovery(self) -> None:
        damaged = self.create("damaged-project")
        damaged_root = Path(damaged.root)
        manifest_path = damaged_root / "project.ro.json"
        manifest_path.write_text("{not-json\n", encoding="utf-8", newline="\n")
        damaged_before = self.package_bytes(damaged_root)
        with self.assertRaises(ProjectLifecycleProblem) as damaged_failure:
            self.service.open(root=damaged.root, trace_id=TRACE)
        self.assertEqual("RO-CORE-PROJECT-DAMAGED", damaged_failure.exception.code)
        self.assertIn("First make and verify a complete backup", damaged_failure.exception.remediation)
        self.assertEqual(damaged_before, self.package_bytes(damaged_root))
        self.assertFalse((damaged_root / ".locks" / "session.lock").exists())

        incomplete = self.create("incomplete-project")
        incomplete_root = Path(incomplete.root)
        (incomplete_root / "config" / "project-profile.json").unlink()
        incomplete_before = self.package_bytes(incomplete_root)
        with self.assertRaises(ProjectLifecycleProblem) as incomplete_failure:
            self.service.open(root=incomplete.root, trace_id=TRACE)
        self.assertEqual("RO-CORE-PROJECT-INCOMPLETE", incomplete_failure.exception.code)
        self.assertIn("First make and verify a complete backup", incomplete_failure.exception.remediation)
        self.assertEqual(incomplete_before, self.package_bytes(incomplete_root))
        self.assertFalse((incomplete_root / ".locks" / "session.lock").exists())

        linked = self.create("linked-manifest")
        linked_root = Path(linked.root)
        manifest_path = linked_root / "project.ro.json"
        outside_manifest = self.parent / "outside-project-manifest.json"
        outside_manifest.write_bytes(manifest_path.read_bytes())
        manifest_path.unlink()
        os.link(outside_manifest, manifest_path)
        outside_before = outside_manifest.read_bytes()
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-DAMAGED"):
            self.service.open(root=linked.root, trace_id=TRACE)
        self.assertEqual(outside_before, outside_manifest.read_bytes())
        self.assertFalse((linked_root / ".locks" / "session.lock").exists())

    def test_failed_delete_restores_exact_prior_archived_manifest(self) -> None:
        project = self.create()
        archived = self.service.archive(root=project.root, trace_id=TRACE)
        manifest_path = Path(project.root) / "project.ro.json"
        before = manifest_path.read_bytes()
        with patch("research_observatory_core.projects._held_directory_renamer") as held_renamer:
            held_renamer.return_value.__enter__.return_value.side_effect = OSError("simulated move failure")
            with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-DELETE-FAILED"):
                self.service.delete(
                    root=project.root,
                    confirmation=archived.delete_confirmation,
                    trace_id=TRACE,
                )
        self.assertEqual(before, manifest_path.read_bytes())
        self.assertEqual("archived", json.loads(before)["lifecycleState"])

    def test_audit_hardlink_and_failure_leave_project_state_unchanged(self) -> None:
        project = self.create("audit-boundary")
        root = Path(project.root)
        audit = root / "logs" / "project-lifecycle.jsonl"
        outside = self.parent / "outside-audit-target.txt"
        outside.write_text("outside\n", encoding="utf-8", newline="\n")
        audit.unlink()
        os.link(outside, audit)
        manifest_before = (root / "project.ro.json").read_bytes()
        outside_before = outside.read_bytes()
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-AUDIT-FAILED"):
            self.service.archive(root=project.root, trace_id=TRACE)
        self.assertEqual(outside_before, outside.read_bytes())
        self.assertEqual(manifest_before, (root / "project.ro.json").read_bytes())

        audit.unlink()
        audit.write_text("", encoding="utf-8", newline="\n")
        with (
            patch.object(
                self.service,
                "_audit",
                side_effect=ProjectLifecycleProblem(
                    status=500,
                    code="RO-CORE-PROJECT-AUDIT-FAILED",
                    title="audit failed",
                    detail="audit failed",
                    remediation="retry",
                ),
            ),
            self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-AUDIT-FAILED"),
        ):
            self.service.delete(root=project.root, confirmation=project.delete_confirmation, trace_id=TRACE)
        self.assertEqual(manifest_before, (root / "project.ro.json").read_bytes())

    def test_failed_open_audit_removes_lock_and_internal_open_state(self) -> None:
        project = self.create("open-audit-boundary")
        failure = ProjectLifecycleProblem(
            status=500,
            code="RO-CORE-PROJECT-AUDIT-FAILED",
            title="audit failed",
            detail="audit failed",
            remediation="retry",
        )
        with (
            patch.object(self.service, "_audit", side_effect=failure),
            self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-AUDIT-FAILED"),
        ):
            self.service.open(root=project.root, trace_id=TRACE)
        self.assertFalse((Path(project.root) / ".locks" / "session.lock").exists())
        self.assertNotIn(Path(project.root), self.service._opened)

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_open_holds_project_identity_and_rejects_device_and_install_roots(self) -> None:
        first = self.create("identity-first")
        second = self.create("identity-second")
        first_root = Path(first.root)
        second_root = Path(second.root)
        holding = self.parent / "identity-holding"
        original_validate = ProjectLifecycleService._validate_layout

        def swap_after_validation(path: Path) -> None:
            original_validate(path)
            os.rename(first_root, holding)
            os.rename(second_root, first_root)
            os.rename(holding, second_root)

        with (
            patch.object(ProjectLifecycleService, "_validate_layout", side_effect=swap_after_validation),
            self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"),
        ):
            self.service.open(root=first.root, trace_id=TRACE)
        self.assertEqual(first.project_id, json.loads((first_root / "project.ro.json").read_text())["projectId"])
        self.assertEqual(second.project_id, json.loads((second_root / "project.ro.json").read_text())["projectId"])

        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"):
            self.service.create(
                parent_directory=f"\\\\?\\{self.parent}",
                directory_name="device-path",
                display_name="Device path",
                template_id="theory-synthesis",
                trace_id=TRACE,
            )
        program_files = os.environ.get("PROGRAMFILES")
        if program_files and Path(program_files).is_dir():
            with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"):
                self.service.create(
                    parent_directory=program_files,
                    directory_name="install-root",
                    display_name="Install root",
                    template_id="theory-synthesis",
                    trace_id=TRACE,
                )

    def test_authenticated_api_exposes_functional_lifecycle_and_secret_safe_conflicts(self) -> None:
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            projects=self.service,
        )
        with TestClient(
            app,
            base_url=f"http://{AUTHORITY}",
            headers={"Authorization": f"Bearer {TOKEN}", "X-Trace-Id": TRACE},
            client=("127.0.0.1", 50000),
        ) as client:
            created = client.post(
                "/projects",
                json={
                    "parentDirectory": str(self.parent),
                    "directoryName": "api-study",
                    "displayName": "API Study",
                    "templateId": "theory-synthesis",
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            projection = created.json()
            opened = client.post("/projects/open", json={"root": projection["root"]})
            self.assertEqual(opened.status_code, 200)
            duplicate = client.post("/projects/open", json={"root": projection["root"]})
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(duplicate.headers["content-type"], "application/problem+json")
            self.assertEqual(duplicate.json()["code"], "RO-CORE-PROJECT-ALREADY-OPEN")
            self.assertEqual(duplicate.json()["traceId"], TRACE)
            self.assertNotIn(projection["root"], duplicate.text)
            closed = client.post("/projects/close", json={"root": projection["root"]})
            self.assertFalse(closed.json()["open"])
            archived = client.post("/projects/archive", json={"root": projection["root"]})
            self.assertEqual(archived.json()["lifecycleState"], "archived")
            restored = client.post("/projects/restore", json={"root": projection["root"]})
            self.assertEqual(restored.json()["lifecycleState"], "active")
            denied = client.post(
                "/projects/delete",
                json={"root": projection["root"], "confirmation": "delete:not-this-project"},
            )
            self.assertEqual(denied.status_code, 422)
            deleted = client.post(
                "/projects/delete",
                json={"root": projection["root"], "confirmation": projection["deleteConfirmation"]},
            )
            self.assertEqual(deleted.json()["lifecycleState"], "trash")

    def test_clean_core_shutdown_releases_only_its_owned_project_lock(self) -> None:
        project = self.create("shutdown-study")
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            projects=self.service,
        )
        with TestClient(
            app,
            base_url=f"http://{AUTHORITY}",
            headers={"Authorization": f"Bearer {TOKEN}", "X-Trace-Id": TRACE},
            client=("127.0.0.1", 50000),
        ) as client:
            self.assertEqual(client.post("/projects/open", json={"root": project.root}).status_code, 200)
            self.assertTrue((Path(project.root) / ".locks" / "session.lock").is_file())
        self.assertFalse((Path(project.root) / ".locks" / "session.lock").exists())


if __name__ == "__main__":
    unittest.main()
