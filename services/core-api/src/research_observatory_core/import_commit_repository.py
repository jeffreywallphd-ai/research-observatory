"""Attempt-fenced import preparation in the existing protected project database.

Staging is provisional. Canonical publication is a separate atomic operation;
neither staged decisions nor their scientific hash imply accepted output.
"""

from __future__ import annotations

import json

from .import_summary_repository import SqliteImportSummaryRepository
from .ingestion.commit_workflow import CommitJobInput, bind_commit_claim, commit_job_input
from .ingestion.import_commits import ImportIdentity, import_identity
from .ingestion.import_drafts import RecordDecision
from .ingestion.import_summaries import summarize_record
from .ports.import_previews import PreviewActor, PreviewDraft, PreviewProblem
from .ports.workflow_executor import WorkflowJobClaim, WorkflowQueueProblem
from .storage import CanonicalConnection


class SqliteImportCommitRepository(SqliteImportSummaryRepository):
    def _bind_commit(self, inputs: CommitJobInput, claim: WorkflowJobClaim) -> CommitJobInput:
        # Immutable snapshots are read before taking the writer reservation.
        try:
            authority = self._queue.authority(claim.job_id)
            continuation = json.loads(authority.snapshot_json).get("continuation")
            previous = None
            if continuation is not None:
                job = continuation["sourceJobId"]
                previous = self._queue.get(job), self._queue.authority(job)
            return bind_commit_claim(authority, claim, inputs, predecessor=previous)
        except WorkflowQueueProblem, ValueError, KeyError, TypeError:
            raise PreviewProblem("preview-commit-job-authority-invalid") from None

    def _commit_head(
        self, connection: CanonicalConnection, inputs: CommitJobInput, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> PreviewDraft:
        self._running(connection, claim, actor)
        state, draft = self._summary_head(connection, inputs.preview.preview_id, inputs.draft_revision)
        current = commit_job_input(
            state,
            draft,
            inputs.intent,
            inputs.preview.policy_hash,
            inputs.preview.resume_epoch,
            request_id=inputs.request_id,
            previous_manifest_revision_id=inputs.previous_manifest_revision_id,
        )
        if current != inputs:
            raise PreviewProblem("preview-commit-input-authority-mismatch")
        return draft

    def _prepared(
        self, connection: CanonicalConnection, inputs: CommitJobInput, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> PreviewDraft:
        draft = self._commit_head(connection, inputs, claim, actor)
        row = connection.execute(
            "SELECT job_id, preview_id, draft_revision, parse_attempt_id, previous_manifest_revision_id "
            "FROM import_commit_preparations WHERE project_id=? AND attempt_id=?",
            (self._project, claim.attempt_id),
        ).fetchone()
        expected = (
            claim.job_id,
            inputs.preview.preview_id,
            inputs.draft_revision,
            inputs.parse_attempt_id,
            inputs.previous_manifest_revision_id,
        )
        if row is None or tuple(row) != expected:
            raise PreviewProblem("preview-commit-preparation-mismatch")
        return draft

    def begin_commit(self, inputs: CommitJobInput, *, claim: WorkflowJobClaim, actor: PreviewActor) -> None:
        inputs = self._bind_commit(inputs, claim)
        with self._transaction(inputs.preview.preview_id, write=True) as connection:
            self._commit_head(connection, inputs, claim, actor)
            exists = connection.execute(
                "SELECT 1 FROM import_commit_preparations WHERE project_id=? AND attempt_id=?",
                (self._project, claim.attempt_id),
            ).fetchone()
            if exists:
                self._prepared(connection, inputs, claim, actor)
                return
            connection.execute(
                "INSERT INTO import_commit_preparations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._project,
                    claim.attempt_id,
                    claim.job_id,
                    inputs.preview.preview_id,
                    inputs.draft_revision,
                    inputs.parse_attempt_id,
                    inputs.previous_manifest_revision_id,
                    actor.occurred_at,
                ),
            )

    def append_commit_page(
        self, inputs: CommitJobInput, *, after: int, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> int:
        inputs = self._bind_commit(inputs, claim)
        preview = inputs.preview.preview_id
        with self._transaction(preview) as connection:
            draft = self._prepared(connection, inputs, claim, actor)
        page = self.draft_page(preview, revision=inputs.draft_revision, after=after, limit=100)
        try:
            rows = tuple(
                (row, summarize_record(row.record, row.decision, row.warnings, draft.authority.rights)) for row in page
            )
        except ValueError:
            raise PreviewProblem("preview-commit-record-denied") from None
        with self._transaction(preview, write=True) as connection:
            self._prepared(connection, inputs, claim, actor)
            maximum = connection.execute(
                "SELECT COALESCE(MAX(ordinal), 0) FROM import_commit_rows WHERE project_id=? AND attempt_id=?",
                (self._project, claim.attempt_id),
            ).fetchone()[0]
            if maximum != after:
                raise PreviewProblem("preview-commit-cursor-conflict")
            for row, summary in rows:
                connection.execute(
                    "INSERT INTO import_commit_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        claim.attempt_id,
                        self._project,
                        preview,
                        draft.attempt_id,
                        row.record.ordinal,
                        row.record.record_key,
                        int(row.decision.included),
                        row.decision.model_dump_json(by_alias=True),
                        json.dumps(row.warnings, ensure_ascii=True, separators=(",", ":")),
                        row.record.raw_sha256,
                        summary.doi_key,
                    ),
                )
        return after if not page else page[-1].record.ordinal

    def prepared_identity(
        self, inputs: CommitJobInput, *, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> ImportIdentity:
        inputs = self._bind_commit(inputs, claim)
        with self._transaction(inputs.preview.preview_id) as connection:
            draft = self._prepared(connection, inputs, claim, actor)
            rows = connection.execute(
                "SELECT decision_json FROM import_commit_rows WHERE project_id=? AND attempt_id=? ORDER BY ordinal",
                (self._project, claim.attempt_id),
            )
            try:
                return import_identity(
                    draft.authority,
                    (RecordDecision.model_validate_json(row[0]) for row in rows),
                    expected_record_count=draft.record_count,
                )
            finally:
                rows.close()
