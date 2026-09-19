"""Protected, attempt-fenced mechanical summaries of a complete current draft.

The adapter computes rows from the real draft rather than accepting caller facts.
No summary is readable until its precise workflow output is committed. A changed
head, including an action-rights change, invalidates every old summary read.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from .import_draft_repository import SqliteImportDraftRepository
from .ingestion.import_summaries import (
    COVERAGE_FIELDS,
    SUMMARY_ACTIVITY,
    SUMMARY_ALGORITHM,
    SummaryCounts,
    SummaryCoverage,
    SummaryResult,
    SummaryRow,
    summarize_record,
    summary_receipt_fingerprint,
    summary_rows_sha256,
)
from .ports.import_previews import (
    PreviewActor,
    PreviewDraft,
    PreviewProblem,
    PreviewState,
    PreviewSummary,
    SummaryGroup,
)
from .ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference
from .storage import CanonicalConnection

_ROWS = "preview_id=:preview AND project_id=:project AND summary_attempt_id=:attempt"
_GROUPS = f"""
    SELECT 'raw' reason, raw_key group_key, COUNT(*) member_count, MIN(ordinal) first_ordinal
      FROM import_summary_rows WHERE {_ROWS} AND raw_key IS NOT NULL GROUP BY raw_key HAVING COUNT(*)>1
    UNION ALL
    SELECT 'doi', doi_key, COUNT(*), MIN(ordinal)
      FROM import_summary_rows WHERE {_ROWS} AND doi_key IS NOT NULL GROUP BY doi_key HAVING COUNT(*)>1
"""


class SqliteImportSummaryRepository(SqliteImportDraftRepository):
    def _summary_head(
        self, connection: CanonicalConnection, preview: str, revision: int
    ) -> tuple[PreviewState, PreviewDraft]:
        state = self._read(connection, preview)
        self._active(state)
        if type(revision) is not int or revision != self._latest(connection, preview):
            raise PreviewProblem("preview-draft-revision-conflict")
        draft = self._draft(connection, state, revision)
        if draft.attempt_id != self._accepted_attempt(connection, preview):
            raise PreviewProblem("preview-draft-attempt-mismatch")
        return state, draft

    def _summary_worker(self, connection: CanonicalConnection, claim: WorkflowJobClaim, actor: PreviewActor) -> None:
        self._running(connection, claim, actor)
        row = connection.execute(
            "SELECT activity_type FROM workflow_queue_jobs WHERE project_id=? AND job_id=?",
            (self._project, claim.job_id),
        ).fetchone()
        if claim.activity_type != SUMMARY_ACTIVITY or row is None or row[0] != SUMMARY_ACTIVITY:
            raise PreviewProblem("preview-summary-activity-mismatch")

    def _summary_attempt(
        self, connection: CanonicalConnection, preview: str, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> tuple[PreviewState, PreviewDraft]:
        self._summary_worker(connection, claim, actor)
        row = self._query(
            connection,
            f"SELECT draft_revision, parse_attempt_id FROM import_summary_attempts WHERE {_ROWS} "
            "AND job_id=:job AND algorithm_version=:algorithm",
            preview,
            attempt=claim.attempt_id,
            job=claim.job_id,
            algorithm=SUMMARY_ALGORITHM,
        ).fetchone()
        if row is None:
            raise PreviewProblem("preview-summary-attempt-mismatch")
        state, draft = self._summary_head(connection, preview, row[0])
        if draft.attempt_id != row[1]:
            raise PreviewProblem("preview-summary-attempt-mismatch")
        return state, draft

    def begin_summary(self, preview_id: str, *, revision: int, claim: WorkflowJobClaim, actor: PreviewActor) -> None:
        with self._transaction(preview_id, write=True) as connection:
            self._summary_worker(connection, claim, actor)
            _, draft = self._summary_head(connection, preview_id, revision)
            prior = self._query(
                connection,
                f"SELECT job_id, draft_revision, parse_attempt_id FROM import_summary_attempts WHERE {_ROWS}",
                preview_id,
                attempt=claim.attempt_id,
            ).fetchone()
            if prior is not None:
                if tuple(prior) != (claim.job_id, revision, draft.attempt_id):
                    raise PreviewProblem("preview-summary-attempt-mismatch")
                return
            self._query(
                connection,
                "INSERT INTO import_summary_attempts VALUES "
                "(:preview, :project, :attempt, :job, :parse, :revision, :algorithm, :started)",
                preview_id,
                attempt=claim.attempt_id,
                job=claim.job_id,
                parse=draft.attempt_id,
                revision=revision,
                algorithm=SUMMARY_ALGORITHM,
                started=actor.occurred_at,
            )

    def append_summary_page(
        self, preview_id: str, *, revision: int, after: int, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> tuple[SummaryRow, ...]:
        with self._transaction(preview_id) as connection:
            _, draft = self._summary_attempt(connection, preview_id, claim, actor)
            if draft.revision != revision:
                raise PreviewProblem("preview-draft-revision-conflict")
        # The existing page bounds raw+decision memory to 16 MiB. Projection runs
        # outside the writer reservation; immutable revision equality is checked
        # again inside the insertion transaction, so no intervening edit is lost.
        page = self.draft_page(preview_id, revision=revision, after=after, limit=100)
        try:
            rows = tuple(
                summarize_record(row.record, row.decision, row.warnings, draft.authority.rights) for row in page
            )
        except ValueError:
            raise PreviewProblem("preview-summary-record-denied") from None
        with self._transaction(preview_id, write=True) as connection:
            _, current = self._summary_attempt(connection, preview_id, claim, actor)
            if current.revision != revision:
                raise PreviewProblem("preview-draft-revision-conflict")
            maximum = self._query(
                connection,
                f"SELECT COALESCE(MAX(ordinal), 0) FROM import_summary_rows WHERE {_ROWS}",
                preview_id,
                attempt=claim.attempt_id,
            ).fetchone()[0]
            if maximum != after:
                raise PreviewProblem("preview-summary-cursor-conflict")
            for row in rows:
                self._query(
                    connection,
                    """INSERT INTO import_summary_rows VALUES
                    (:preview, :project, :attempt, :parse, :ordinal, :key, :kind, :status,
                     :included, :warnings, :coverage, :raw, :doi)""",
                    preview_id,
                    attempt=claim.attempt_id,
                    parse=draft.attempt_id,
                    ordinal=row.ordinal,
                    key=row.record_key,
                    kind=row.record_kind,
                    status=row.parse_status,
                    included=int(row.included),
                    warnings=row.warning_count,
                    coverage=row.coverage_mask,
                    raw=row.raw_key,
                    doi=row.doi_key,
                )
        return rows

    def _summary_result(
        self, connection: CanonicalConnection, preview: str, attempt: str, draft: PreviewDraft
    ) -> SummaryResult:
        conditions = [
            "record_kind='record'",
            "record_kind!='record'",
            "parse_status='malformed'",
            "included=1",
            "record_kind='record' AND included=0",
            "warning_count>0",
        ]
        aggregates = ", ".join(f"COALESCE(SUM(CASE WHEN {condition} THEN 1 ELSE 0 END), 0)" for condition in conditions)
        coverage = ", ".join(
            f"COALESCE(SUM(CASE WHEN (coverage_mask & {1 << index})!=0 THEN 1 ELSE 0 END), 0)" for index in range(5)
        )
        counts = self._query(
            connection,
            f"SELECT COUNT(*), {aggregates}, COALESCE(SUM(warning_count),0), {coverage} "
            f"FROM import_summary_rows WHERE {_ROWS}",
            preview,
            attempt=attempt,
        ).fetchone()
        if counts[0] != draft.record_count:
            raise PreviewProblem("preview-summary-incomplete")
        groups = dict(
            self._query(
                connection,
                f"WITH groups AS ({_GROUPS}) SELECT reason, COUNT(*) FROM groups GROUP BY reason",
                preview,
                attempt=attempt,
            ).fetchall()
        )
        candidates = self._query(
            connection,
            f"""WITH groups AS ({_GROUPS}), members AS (
                SELECT r.ordinal FROM groups g CROSS JOIN import_summary_rows r
                 WHERE r.preview_id=:preview AND r.project_id=:project AND r.summary_attempt_id=:attempt
                   AND g.reason='raw' AND r.raw_key=g.group_key
                UNION
                SELECT r.ordinal FROM groups g CROSS JOIN import_summary_rows r
                 WHERE r.preview_id=:preview AND r.project_id=:project AND r.summary_attempt_id=:attempt
                   AND g.reason='doi' AND r.doi_key=g.group_key
            ) SELECT COUNT(*) FROM members""",
            preview,
            attempt=attempt,
        ).fetchone()[0]
        rows = self._query(
            connection,
            "SELECT ordinal, record_key, record_kind, parse_status, included, warning_count, "
            "coverage_mask, raw_key, doi_key "
            f"FROM import_summary_rows WHERE {_ROWS} ORDER BY ordinal",
            preview,
            attempt=attempt,
        )
        digest = summary_rows_sha256(
            SummaryRow(
                ordinal=row[0],
                record_key=row[1],
                record_kind=row[2],
                parse_status=row[3],
                included=bool(row[4]),
                warning_count=row[5],
                coverage_mask=row[6],
                raw_key=row[7],
                doi_key=row[8],
            )
            for row in rows
        )
        return SummaryResult(
            counts=SummaryCounts(
                source_rows=counts[0],
                record_rows=counts[1],
                context_rows=counts[2],
                malformed_rows=counts[3],
                included_records=counts[4],
                excluded_records=counts[5],
                warning_rows=counts[6],
                warning_count=counts[7],
                coverage=SummaryCoverage.model_validate(dict(zip(COVERAGE_FIELDS, counts[8:], strict=True))),
                raw_duplicate_groups=groups.get("raw", 0),
                doi_duplicate_groups=groups.get("doi", 0),
                candidate_records=candidates,
            ),
            rows_sha256=digest,
        )

    def summary_result(self, preview_id: str, *, claim: WorkflowJobClaim, actor: PreviewActor) -> SummaryResult:
        with self._transaction(preview_id) as connection:
            _, draft = self._summary_attempt(connection, preview_id, claim, actor)
            return self._summary_result(connection, preview_id, claim.attempt_id, draft)

    def _summary_receipt(
        self,
        connection: CanonicalConnection,
        state: PreviewState,
        draft: PreviewDraft,
        job: str,
        attempt: str,
        receipt: str,
        result: SummaryResult,
    ) -> WorkflowOutputReference:
        binding = summary_receipt_fingerprint(
            project_id=self._project,
            preview_id=state.preview_id,
            job_id=job,
            summary_attempt_id=attempt,
            parse_attempt_id=draft.attempt_id,
            draft_revision=draft.revision,
            source_sha256=str(state.source_sha256),
            manifest_sha256=str(state.manifest_sha256),
            result=result,
        )
        row = self._query(
            connection,
            """
            SELECT r.aggregate_id, e.content_hash FROM aggregate_revisions r
              JOIN provenance_ledger_entities e ON e.project_id=r.project_id AND e.revision_id=r.revision_id
              JOIN material_dependency_outputs m ON m.project_id=r.project_id AND m.output_revision_id=r.revision_id
             WHERE r.project_id=:project AND r.revision_id=:receipt AND :preview IS NOT NULL
               AND r.aggregate_kind='workflow'
               AND r.knowledge_status='observed' AND e.direction='output' AND m.coverage='complete'
               AND EXISTS (SELECT 1 FROM material_dependencies d
                 WHERE d.project_id=r.project_id AND d.output_revision_id=r.revision_id
                   AND d.dependency_kind='parameter-set' AND d.configuration_id='import.draft-summary'
                   AND d.configuration_version='1.0.0' AND d.fingerprint=:binding)
        """,
            state.preview_id,
            receipt=receipt,
            binding=binding,
        ).fetchone()
        if row is None:
            raise PreviewProblem("preview-summary-receipt-authority-mismatch")
        return WorkflowOutputReference(
            artifact_id=row[0],
            revision_id=receipt,
            content_hash=row[1],
            media_type="application/json",
            provenance_entity_id=row[0],
        )

    def finish_summary(
        self,
        preview_id: str,
        *,
        claim: WorkflowJobClaim,
        result: SummaryResult,
        receipt_revision_id: str,
        actor: PreviewActor,
    ) -> WorkflowOutputReference:
        result = SummaryResult.model_validate(result)
        with self._transaction(preview_id, write=True) as connection:
            state, draft = self._summary_attempt(connection, preview_id, claim, actor)
            actual = self._summary_result(connection, preview_id, claim.attempt_id, draft)
            if actual != result:
                raise PreviewProblem("preview-summary-result-mismatch")
            output = self._summary_receipt(
                connection, state, draft, claim.job_id, claim.attempt_id, receipt_revision_id, result
            )
            self._query(
                connection,
                "INSERT INTO import_summary_groups SELECT :preview, :project, :attempt, "
                f"reason, group_key, member_count, first_ordinal FROM ({_GROUPS})",
                preview_id,
                attempt=claim.attempt_id,
            )
            self._query(
                connection,
                "INSERT INTO import_summary_completions VALUES "
                "(:preview, :project, :attempt, :receipt, :count, :digest, :result, :completed)",
                preview_id,
                attempt=claim.attempt_id,
                receipt=receipt_revision_id,
                count=draft.record_count,
                digest=result.sha256,
                result=result.model_dump_json(by_alias=True),
                completed=actor.occurred_at,
            )
            return output

    def _summary(self, connection: CanonicalConnection, preview: str, revision: int) -> PreviewSummary | None:
        state, draft = self._summary_head(connection, preview, revision)
        row = self._query(
            connection,
            """
            SELECT a.summary_attempt_id, a.job_id, c.receipt_revision_id, c.result_sha256,
                   c.summary_json, o.output_manifest_json
              FROM import_summary_attempts a
              JOIN import_summary_completions c USING (preview_id, project_id, summary_attempt_id)
              JOIN workflow_queue_jobs j ON j.project_id=a.project_id AND j.job_id=a.job_id
                AND j.current_attempt_id=a.summary_attempt_id
              JOIN workflow_job_attempts t ON t.project_id=a.project_id AND t.job_id=a.job_id
                AND t.attempt_id=a.summary_attempt_id
              JOIN workflow_committed_outputs o ON o.project_id=a.project_id AND o.job_id=a.job_id
                AND o.attempt_id=a.summary_attempt_id
             WHERE a.preview_id=:preview AND a.project_id=:project AND a.draft_revision=:revision
               AND a.parse_attempt_id=:parse AND a.algorithm_version=:algorithm
               AND j.state='succeeded' AND t.state='succeeded' AND j.cancellation_requested_at IS NULL
               AND j.activity_type=:activity ORDER BY a.rowid DESC LIMIT 1
        """,
            preview,
            revision=revision,
            parse=draft.attempt_id,
            algorithm=SUMMARY_ALGORITHM,
            activity=SUMMARY_ACTIVITY,
        ).fetchone()
        if row is None:
            return None
        result = SummaryResult.model_validate_json(row[4])
        if result.sha256 != row[3] or result.counts.source_rows != draft.record_count:
            raise PreviewProblem("preview-summary-result-mismatch")
        output = self._summary_receipt(connection, state, draft, row[1], row[0], row[2], result)
        expected = {
            "artifactId": output.artifact_id,
            "revisionId": output.revision_id,
            "contentHash": output.content_hash,
            "mediaType": output.media_type,
            "provenanceEntityId": output.provenance_entity_id,
        }
        if expected not in json.loads(row[5])["outputs"]:
            raise PreviewProblem("preview-summary-output-mismatch")
        return PreviewSummary(
            project_id=self._project,
            preview_id=preview,
            draft_revision=revision,
            parse_attempt_id=draft.attempt_id,
            summary_attempt_id=row[0],
            job_id=row[1],
            receipt_revision_id=row[2],
            result=result,
        )

    def summary(self, preview_id: str, *, revision: int) -> PreviewSummary | None:
        with self._transaction(preview_id) as connection:
            return self._summary(connection, preview_id, revision)

    @staticmethod
    def _group_page(reason: str, key: str | None, limit: int) -> None:
        if (
            reason not in {"raw", "doi"}
            or type(limit) is not int
            or not 1 <= limit <= 100
            or (key is not None and re.fullmatch(r"[0-9a-f]{64}", key) is None)
        ):
            raise PreviewProblem("preview-summary-page-limit")

    def summary_groups(
        self, preview_id: str, *, revision: int, reason: Literal["raw", "doi"], after: str | None, limit: int
    ) -> tuple[SummaryGroup, ...]:
        self._group_page(reason, after, limit)
        with self._transaction(preview_id) as connection:
            summary = self._summary(connection, preview_id, revision)
            if summary is None:
                raise PreviewProblem("preview-summary-not-accepted")
            rows = self._query(
                connection,
                f"SELECT group_key, member_count, first_ordinal FROM import_summary_groups WHERE {_ROWS} "
                "AND reason=:reason AND group_key>:after ORDER BY group_key LIMIT :limit",
                preview_id,
                attempt=summary.summary_attempt_id,
                reason=reason,
                after=after or "",
                limit=limit,
            )
            return tuple(
                SummaryGroup(reason=reason, group_key=row[0], member_count=row[1], first_ordinal=row[2]) for row in rows
            )

    def summary_members(
        self, preview_id: str, *, revision: int, reason: Literal["raw", "doi"], group_key: str, after: int, limit: int
    ) -> tuple[int, ...]:
        self._group_page(reason, group_key, limit)
        if type(after) is not int or not 0 <= after <= 200000:
            raise PreviewProblem("preview-summary-page-limit")
        with self._transaction(preview_id) as connection:
            summary = self._summary(connection, preview_id, revision)
            if summary is None:
                raise PreviewProblem("preview-summary-not-accepted")
            group = self._query(
                connection,
                f"SELECT 1 FROM import_summary_groups WHERE {_ROWS} AND reason=:reason AND group_key=:key",
                preview_id,
                attempt=summary.summary_attempt_id,
                reason=reason,
                key=group_key,
            ).fetchone()
            if group is None:
                raise PreviewProblem("preview-summary-group-not-found")
            rows = self._query(
                connection,
                f"SELECT ordinal FROM import_summary_rows WHERE {_ROWS} AND {reason}_key=:key "
                "AND ordinal>:after ORDER BY ordinal LIMIT :limit",
                preview_id,
                attempt=summary.summary_attempt_id,
                key=group_key,
                after=after,
                limit=limit,
            )
            return tuple(row[0] for row in rows)
