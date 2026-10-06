"""Independent regression probes for durable attachment identity and migration rollback."""

# ruff: noqa: E402

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.app import create_app
from research_observatory_core.authentication import capability_token_digest
from research_observatory_core.corpus_service import CorpusService
from research_observatory_core.document_attachment_repository import AttachmentProblem, LocalDocumentAttachmentService
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.import_preview_service import ImportPreviewService
from research_observatory_core.main import DocumentAttachmentRuntime
from research_observatory_core.migrations import runner
from research_observatory_core.migrations.versions import v0023_attachment_operations
from research_observatory_core.ports.import_previews import PreviewProblem
from research_observatory_core.storage import DATABASE_SCHEMA_VERSION, open_canonical_database

from tests.documents import test_local_attachment as attachment_fixtures  # type: ignore[import-not-found]


class AttachmentLifecycleRegressionTests(unittest.TestCase):
    def test_every_v23_interruption_preserves_populated_v22_and_retries(self) -> None:
        self.assertTrue(v0023_attachment_operations.MATERIAL_MIGRATION_STEPS)
        for interrupted_step in v0023_attachment_operations.MATERIAL_MIGRATION_STEPS:
            with self.subTest(step=interrupted_step):
                fixture = attachment_fixtures.AttachmentOperationMigrationTests(methodName="runTest")
                fixture.setUp()
                try:
                    fixture._assert_literal_predecessor()
                    before_rows = fixture._source_rows()
                    ciphertext_sha256 = {
                        item["relativePath"]: item["sha256"] for item in fixture.manifest["ciphertext"]
                    }

                    def interrupt(step: str, expected_step: str = interrupted_step) -> None:
                        if step == expected_step:
                            raise RuntimeError("synthetic v23 migration interruption")

                    with (
                        patch.object(
                            v0023_attachment_operations, "_migration_step_completed", side_effect=interrupt
                        ) as hook,
                        self.assertRaisesRegex(runner.MigrationProblem, "migration-execution-failed") as failed,
                    ):
                        runner.migrate_database(fixture.database, expected_project_id=fixture.manifest["projectId"])
                    hook.assert_any_call(interrupted_step)
                    self.assertIsInstance(failed.exception.__cause__, RuntimeError)

                    fixture._assert_literal_predecessor()
                    self.assertEqual(before_rows, fixture._source_rows())
                    self.assertEqual(
                        ciphertext_sha256,
                        {
                            path: hashlib.sha256((fixture.project / path).read_bytes()).hexdigest()
                            for path in ciphertext_sha256
                        },
                    )
                    result = runner.migrate_database(
                        fixture.database, expected_project_id=fixture.manifest["projectId"]
                    )
                    self.assertEqual("migrated", result.status)
                    assert result.backup_relative_path is not None
                    with closing(sqlite3.connect(fixture.project / result.backup_relative_path)) as backup:
                        self.assertEqual(22, backup.execute("PRAGMA user_version").fetchone()[0])
                    with closing(
                        open_canonical_database(fixture.database, expected_project_id=fixture.manifest["projectId"])
                    ) as current:
                        self.assertEqual(DATABASE_SCHEMA_VERSION, current.execute("PRAGMA user_version").fetchone()[0])
                        self.assertEqual(
                            0, current.execute("SELECT COUNT(*) FROM document_attachment_operations").fetchone()[0]
                        )
                        self.assertEqual([], current.execute("PRAGMA foreign_key_check").fetchall())
                    self.assertEqual(before_rows, fixture._source_rows())
                    self.assertEqual(
                        ciphertext_sha256,
                        {
                            path: hashlib.sha256((fixture.project / path).read_bytes()).hexdigest()
                            for path in ciphertext_sha256
                        },
                    )
                finally:
                    fixture.doCleanups()

    def test_known_operation_denies_alternate_actor_and_project(self) -> None:
        first = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        first.setUp()
        self.addCleanup(first.doCleanups)
        second = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        second.setUp()
        self.addCleanup(second.doCleanups)
        self.assertNotEqual(first.corpus.project, second.corpus.project)

        operation_id, session_id, command_id = new_uuid_v7(), "d" * 32, new_uuid_v7()
        candidate = first.stage_operation(operation_id, session_id)
        selection = (
            candidate.source_assertion_revision_id,
            candidate.work_id,
            candidate.work_revision_id,
            candidate.version_id,
            candidate.version_revision_id,
        )
        query = dict(
            source_assertion_revision_id=selection[0],
            work_id=selection[1],
            work_revision_id=selection[2],
            version_id=selection[3],
            version_revision_id=selection[4],
            operation_id=operation_id,
            command_id=command_id,
            session_id=session_id,
        )
        alternate_actor = replace(first.corpus.actor, actor_id=new_uuid_v7(), trace_id="a" * 32)
        self.assertEqual("unavailable", first.service.status(**query, actor=alternate_actor).state)
        self.assertEqual("unavailable", second.service.status(**query, actor=second.corpus.actor).state)
        for service, actor in ((first.service, alternate_actor), (second.service, second.corpus.actor)):
            with self.assertRaisesRegex(AttachmentProblem, "attachment-operation-unavailable"):
                service.commit(
                    candidate.candidate_id,
                    confirmation_sha256=candidate.candidate_sha256,
                    command_id=command_id,
                    actor=actor,
                    operation_id=operation_id,
                    session_id=session_id,
                    match_confirmed=True,
                    permitted_use="project-only",
                    exact_selection=selection,
                )
        self.assertEqual("unresolved", first.service.status(**query, actor=first.corpus.actor).state)
        for fixture in (first, second):
            with closing(
                open_canonical_database(fixture.corpus.database, expected_project_id=fixture.corpus.project)
            ) as db:
                self.assertEqual(0, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])

    def test_operation_denial_precedes_candidate_lookup_for_commit_and_cancel(self) -> None:
        first = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        first.setUp()
        self.addCleanup(first.doCleanups)
        second = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        second.setUp()
        self.addCleanup(second.doCleanups)
        operation, session = new_uuid_v7(), "d" * 32
        candidate = first.stage_operation(operation, session)
        selection = (
            candidate.source_assertion_revision_id,
            candidate.work_id,
            candidate.work_revision_id,
            candidate.version_id,
            candidate.version_revision_id,
        )
        alternate = replace(first.corpus.actor, actor_id=new_uuid_v7(), trace_id="a" * 32)
        for service, actor in ((first.service, alternate), (second.service, second.corpus.actor)):
            with patch.object(
                service, "_candidate", side_effect=AssertionError("unauthorized candidate lookup")
            ) as lookup:
                with self.assertRaisesRegex(AttachmentProblem, "attachment-operation-unavailable"):
                    service.commit(
                        candidate.candidate_id,
                        confirmation_sha256=candidate.candidate_sha256,
                        command_id=new_uuid_v7(),
                        actor=actor,
                        operation_id=operation,
                        session_id=session,
                        match_confirmed=True,
                        permitted_use="project-only",
                        exact_selection=selection,
                    )
                with self.assertRaisesRegex(AttachmentProblem, "attachment-operation-unavailable"):
                    service.cancel(candidate.candidate_id, actor=actor, operation_id=operation, session_id=session)
                lookup.assert_not_called()

    def test_http_session_rotation_preserves_commit_and_closes_unresolved_candidate(self) -> None:
        fixture = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        session = "d" * 32
        actor = fixture.corpus.actor

        class Imports:
            def native_context(self, root: str, project_id: str) -> str:
                if (root, project_id) != (str(fixture.project_root), fixture.corpus.project):
                    raise PreviewProblem("preview-project-session-changed")
                return session

            def in_native_session(self, root: str, project_id: str, session_id: str, action):
                if self.native_context(root, project_id) != session_id:
                    raise PreviewProblem("preview-project-session-changed")
                return action()

        class Corpus:
            def _with_authority(self, root: str, _trace_id: str, action):
                if root != str(fixture.project_root):
                    raise AttachmentProblem("attachment-authority-changed")
                return action(None, actor, actor.intent_revision_id, fixture.project_root, fixture.corpus.project)

        runtime = DocumentAttachmentRuntime(
            cast(ImportPreviewService, Imports()),
            cast(CorpusService, Corpus()),
            lambda _path, _identity: fixture.store,
        )
        app = create_app(
            attachments=runtime,
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        client = self.enterContext(
            TestClient(
                app,
                base_url="http://127.0.0.1:49152",
                headers={"Authorization": "Bearer " + "a" * 64},
                client=("127.0.0.1", 50000),
            )
        )
        data = b"Synthetic plain text full text\n"
        base = {
            "root": str(fixture.project_root),
            "projectId": fixture.corpus.project,
            "sessionId": session,
            "sourceAssertionRevisionId": fixture._assertion_id(),
            "workId": fixture.corpus.work_id,
            "workRevisionId": fixture.work_revision_id,
            "versionId": fixture.version.version_id,
            "versionRevisionId": fixture.version.revision_id,
        }

        def stage(operation_id: str) -> dict[str, object]:
            header = {
                **base,
                "operationId": operation_id,
                "sourceName": "paper.txt",
                "declaredMediaType": "text/plain",
                "byteLength": len(data),
            }
            encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
            frame = len(encoded).to_bytes(4, "big") + encoded + data
            response = client.post(
                "/native/document-attachments/stage",
                content=frame,
                headers={"Content-Type": "application/octet-stream"},
            )
            self.assertEqual(200, response.status_code, response.text)
            return response.json()

        with patch(
            "research_observatory_core.main.LocalDocumentAttachmentService",
            side_effect=lambda database, project_id, store: LocalDocumentAttachmentService(
                database, project_id, store, inspector=fixture.service._inspector
            ),
        ):
            committed_operation = new_uuid_v7()
            first = stage(committed_operation)
            command_id = new_uuid_v7()
            commit = client.post(
                "/native/document-attachments/commit",
                json={
                    **base,
                    "candidateId": first["candidateId"],
                    "operationId": committed_operation,
                    "confirmationSha256": first["candidateSha256"],
                    "commandId": command_id,
                    "matchConfirmed": True,
                    "permittedUse": "project-only",
                },
            )
            self.assertEqual(200, commit.status_code, commit.text)
            unresolved_operation = new_uuid_v7()
            second = stage(unresolved_operation)
            unresolved_command = new_uuid_v7()

            session = "e" * 32
            committed_status = client.post(
                "/native/document-attachments/status",
                json={**base, "sessionId": session, "operationId": committed_operation, "commandId": command_id},
            )
            self.assertEqual(200, committed_status.status_code, committed_status.text)
            self.assertEqual("committed", committed_status.json()["state"])
            self.assertEqual(commit.json()["attachmentId"], committed_status.json()["attachmentId"])

            stale_status = client.post(
                "/native/document-attachments/status",
                json={
                    **base,
                    "sessionId": session,
                    "operationId": unresolved_operation,
                    "commandId": unresolved_command,
                },
            )
            self.assertEqual(200, stale_status.status_code, stale_status.text)
            self.assertEqual("stale-session", stale_status.json()["state"])
            self.assertIsNone(stale_status.json()["attachmentId"])
            self.assertEqual(
                403,
                client.post(
                    "/native/document-attachments/status",
                    json={**base, "operationId": unresolved_operation, "commandId": unresolved_command},
                ).status_code,
            )
            denied_commit = client.post(
                "/native/document-attachments/commit",
                json={
                    **base,
                    "sessionId": session,
                    "candidateId": second["candidateId"],
                    "operationId": unresolved_operation,
                    "confirmationSha256": second["candidateSha256"],
                    "commandId": unresolved_command,
                    "matchConfirmed": True,
                    "permittedUse": "project-only",
                },
            )
            self.assertEqual(409, denied_commit.status_code, denied_commit.text)
            with closing(
                open_canonical_database(fixture.corpus.database, expected_project_id=fixture.corpus.project)
            ) as db:
                self.assertEqual(1, db.execute("SELECT COUNT(*) FROM document_attachment_assertions").fetchone()[0])
