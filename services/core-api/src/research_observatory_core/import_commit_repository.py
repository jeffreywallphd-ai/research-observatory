"""Attempt-fenced import preparation in the existing protected project database.

Staging is provisional. Canonical publication is a separate atomic operation;
neither staged decisions nor their scientific hash imply accepted output.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from typing import Any

from .domain_contracts import new_uuid_v7
from .import_preview_repository import _actor
from .import_summary_repository import SqliteImportSummaryRepository
from .ingestion.commit_workflow import CommitJobInput, bind_commit_claim, commit_job_input
from .ingestion.import_commits import ImportIdentity, import_identity, source_assertion_key
from .ingestion.import_drafts import RecordDecision
from .ingestion.import_summaries import summarize_record
from .ingestion.preview_workflow import fingerprint
from .ports.import_previews import PreviewActor, PreviewDraft, PreviewProblem
from .ports.repositories import (
    AggregateKind,
    AggregateRevision,
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
    MaterialDependency,
)
from .ports.workflow_executor import WorkflowJobClaim, WorkflowOutputReference, WorkflowQueueProblem
from .repositories import (
    _UNIT_OF_WORKS,
    _projection_content_sha256,
    _revision_with_connection,
    _SqliteAggregateRepository,
)
from .storage import CanonicalConnection


def _publication_step_completed(_step: str) -> None:
    """Private failpoint for atomic publication rollback tests."""


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
        self,
        connection: CanonicalConnection,
        inputs: CommitJobInput,
        claim: WorkflowJobClaim,
        actor: PreviewActor,
        *,
        running: bool = True,
    ) -> PreviewDraft:
        if running:
            self._running(connection, claim, actor)
        else:
            if _actor(actor).actor_id != claim.worker_id:
                raise PreviewProblem("preview-worker-actor-mismatch")
            self._queue._verify_attempt_capability(connection, claim)
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
        self,
        connection: CanonicalConnection,
        inputs: CommitJobInput,
        claim: WorkflowJobClaim,
        actor: PreviewActor,
        *,
        running: bool = True,
    ) -> PreviewDraft:
        draft = self._commit_head(connection, inputs, claim, actor, running=running)
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

    @staticmethod
    def _output(revision: AggregateRevision) -> WorkflowOutputReference:
        return WorkflowOutputReference(
            artifact_id=revision.aggregate_id,
            revision_id=revision.revision_id,
            content_hash=_projection_content_sha256(revision),
            media_type="application/vnd.research-observatory.import-manifest+json",
            provenance_entity_id=revision.aggregate_id,
        )

    def _staged(self, connection: CanonicalConnection, attempt: str):
        return connection.execute(
            "SELECT ordinal, record_key, included, decision_json, warnings_json, raw_sha256, doi_key "
            "FROM import_commit_rows WHERE project_id=? AND attempt_id=? ORDER BY ordinal",
            (self._project, attempt),
        )

    def _comparison(
        self,
        connection: CanonicalConnection,
        inputs: CommitJobInput,
        row: Any,
        duplicates: frozenset[tuple[str, str]],
    ) -> tuple[str, str | None]:
        previous = inputs.previous_manifest_revision_id
        if previous is None or not row[2]:
            return "not-compared", None
        for column, value, label in (("raw_sha256", row[5], "unchanged"), ("doi_key", row[6], "updated")):
            if value is None:
                continue
            candidates = connection.execute(
                "SELECT s.source_record_revision_id, s.decision_json, d.rights_json FROM import_manifest_members s "
                "JOIN import_manifests m ON m.project_id=s.project_id AND m.revision_id=s.manifest_revision_id "
                "JOIN import_commit_preparations p ON p.project_id=m.project_id AND p.attempt_id=m.attempt_id "
                "JOIN import_draft_revisions d ON d.project_id=p.project_id AND d.preview_id=p.preview_id "
                "AND d.revision=p.draft_revision "
                f"WHERE s.project_id=? AND s.manifest_revision_id=? AND s.included=1 AND s.{column}=? LIMIT 2",
                (self._project, previous, value),
            ).fetchall()
            if len(candidates) > 1 or (candidates and (column, value) in duplicates):
                return "ambiguous", None
            if candidates:
                if label == "unchanged":
                    old = RecordDecision.model_validate_json(candidates[0][1])
                    current = RecordDecision.model_validate_json(row[3])
                    old_rights = fingerprint(
                        old.rights.model_dump(mode="json", by_alias=True)
                        if old.rights
                        else json.loads(candidates[0][2])
                    )
                    current_rights = (
                        fingerprint(current.rights.model_dump(mode="json", by_alias=True))
                        if current.rights
                        else inputs.preview.rights_hash
                    )
                    if old.fields != current.fields or old_rights != current_rights:
                        label = "updated"
                return label, str(candidates[0][0])
        return "added", None

    def _manifest_access(self, connection: CanonicalConnection, revision: str) -> None:
        binding = connection.execute(
            "SELECT p.preview_id, p.draft_revision FROM import_manifests m "
            "JOIN import_manifest_seals s ON s.project_id=m.project_id AND s.manifest_revision_id=m.revision_id "
            "JOIN import_commit_preparations p ON p.project_id=m.project_id AND p.attempt_id=m.attempt_id "
            "WHERE m.project_id=? AND m.revision_id=?",
            (self._project, revision),
        ).fetchone()
        if binding is None:
            raise PreviewProblem("preview-commit-manifest-authority-mismatch")
        preview, historical_revision = binding
        state = self._read(connection, preview)
        self._active(state)
        current = self._latest(connection, preview)
        draft = self._draft(connection, state, current)
        historical = self._draft(connection, state, historical_revision)
        if draft.attempt_id != historical.attempt_id:
            raise PreviewProblem("preview-commit-manifest-authority-mismatch")
        after = 0
        while True:
            rows = connection.execute(
                "SELECT ordinal, decision_json FROM import_manifest_members "
                "WHERE project_id=? AND manifest_revision_id=? AND ordinal>? ORDER BY ordinal LIMIT 100",
                (self._project, revision, after),
            ).fetchall()
            if not rows:
                break
            selected = self._page_decision_revisions(
                connection, preview, current, current, tuple(row[0] for row in rows)
            )
            for ordinal, decision_json in rows:
                old = RecordDecision.model_validate_json(decision_json)
                current_decision = self._decision_at(
                    connection, preview, selected.get(ordinal, (None, None))[0], ordinal
                )[0]
                for rights in (
                    old.rights or historical.authority.rights,
                    current_decision.rights if current_decision and current_decision.rights else draft.authority.rights,
                ):
                    if not rights.permits("store") or not rights.permits("inspect"):
                        raise PreviewProblem("preview-commit-manifest-rights-denied")
            after = rows[-1][0]

    def _members(
        self, connection: CanonicalConnection, inputs: CommitJobInput, claim: WorkflowJobClaim, manifest: str
    ) -> Iterator[tuple[Any, ...]]:
        # At most half the bounded source rows can form duplicate groups. Group
        # once per stream rather than scanning the current batch for each row.
        duplicates = (
            frozenset(
                (column, str(row[0]))
                for column in ("raw_sha256", "doi_key")
                for row in connection.execute(
                    f"SELECT {column} FROM import_commit_rows WHERE project_id=? AND attempt_id=? "
                    f"AND included=1 AND {column} IS NOT NULL GROUP BY {column} HAVING COUNT(*)>1",
                    (self._project, claim.attempt_id),
                )
            )
            if inputs.previous_manifest_revision_id
            else frozenset()
        )
        rows = self._staged(connection, claim.attempt_id)
        try:
            for row in rows:
                source = None
                if row[2]:
                    saved = connection.execute(
                        "SELECT revision_id FROM import_source_records WHERE project_id=? AND source_sha256=? "
                        "AND record_key=?",
                        (self._project, inputs.preview.source_sha256, row[1]),
                    ).fetchone()
                    if saved is None:
                        raise PreviewProblem("preview-commit-source-incomplete")
                    source = saved[0]
                comparison, previous = self._comparison(connection, inputs, row, duplicates)
                yield (
                    manifest,
                    self._project,
                    inputs.preview.preview_id,
                    inputs.parse_attempt_id,
                    row[0],
                    row[1],
                    source,
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    comparison,
                    previous,
                )
        finally:
            rows.close()

    @staticmethod
    def _append_canonical(
        aggregates: _SqliteAggregateRepository,
        *,
        kind: AggregateKind,
        label: str,
        actor: PreviewActor,
        parser: AggregateRevision,
        digest: str,
        key: str,
    ) -> AggregateRevision:
        return aggregates.append(
            AggregateRevisionDraft(
                revision_id=new_uuid_v7(),
                aggregate_id=new_uuid_v7(),
                aggregate_kind=kind,
                created_at=actor.occurred_at,
                modified_at=actor.occurred_at,
                display_label_observed=label,
                display_label_normalized=None,
                knowledge_status="observed",
                rights_status="unknown",
                dependency_coverage="complete",
                provenance_inputs=(parser,),
                material_dependencies=(
                    MaterialDependency(
                        dependency_id=new_uuid_v7(),
                        dependency_kind="source-revision",
                        relation_type="direct",
                        revision_id=parser.revision_id,
                        configuration_id=None,
                        configuration_version=None,
                        fingerprint=_projection_content_sha256(parser),
                        governing_policy_id="dependency.material.v1",
                        governing_policy_version="1.0.0",
                    ),
                    MaterialDependency(
                        dependency_id=new_uuid_v7(),
                        dependency_kind="parameter-set",
                        relation_type="direct",
                        revision_id=None,
                        configuration_id="import.commit",
                        configuration_version="1.0.0",
                        fingerprint="sha256:" + digest,
                        governing_policy_id="dependency.material.v1",
                        governing_policy_version="1.0.0",
                    ),
                ),
            ),
            AtomicRepositoryEvent(
                event_id=new_uuid_v7(),
                outbox_id=new_uuid_v7(),
                event_type=kind + ".created",
                occurred_at=actor.occurred_at,
                available_at=actor.occurred_at,
                trace_id=actor.trace_id,
                actor_type="worker",
                actor_id=actor.actor_id,
                idempotency_key=key,
            ),
            expected_revision=None,
        )

    def _verified_identity(
        self,
        inputs: CommitJobInput,
        claim: WorkflowJobClaim,
        actor: PreviewActor,
        now: Callable[[], str],
        poll: Callable[[], None] | None,
        *,
        running: bool = True,
    ) -> ImportIdentity:
        preview = inputs.preview.preview_id
        with self._transaction(preview) as connection:
            draft = self._prepared(
                connection, inputs, claim, actor.model_copy(update={"occurred_at": now()}), running=running
            )

        def decisions() -> Iterator[RecordDecision]:
            after = 0
            while after < inputs.record_count:
                if poll is not None:
                    poll()
                page = self.draft_page(preview, revision=inputs.draft_revision, after=after, limit=100)
                if not page:
                    raise PreviewProblem("preview-commit-incomplete")
                with self._transaction(preview) as connection:
                    self._prepared(
                        connection, inputs, claim, actor.model_copy(update={"occurred_at": now()}), running=running
                    )
                    staged = connection.execute(
                        "SELECT ordinal, record_key, included, decision_json, warnings_json, raw_sha256, doi_key "
                        "FROM import_commit_rows WHERE project_id=? AND attempt_id=? AND ordinal>? AND ordinal<=? "
                        "ORDER BY ordinal",
                        (self._project, claim.attempt_id, after, page[-1].record.ordinal),
                    ).fetchall()
                if len(staged) != len(page):
                    raise PreviewProblem("preview-commit-incomplete")
                for item, row in zip(page, staged, strict=True):
                    summary = summarize_record(item.record, item.decision, item.warnings, draft.authority.rights)
                    expected = (
                        item.record.ordinal,
                        item.record.record_key,
                        int(item.decision.included),
                        item.decision.model_dump_json(by_alias=True),
                        json.dumps(item.warnings, ensure_ascii=True, separators=(",", ":")),
                        item.record.raw_sha256,
                        summary.doi_key,
                    )
                    if tuple(row) != expected:
                        raise PreviewProblem("preview-commit-prepared-row-mismatch")
                    yield item.decision
                after = page[-1].record.ordinal

        try:
            return import_identity(draft.authority, decisions(), expected_record_count=draft.record_count)
        except ValueError:
            raise PreviewProblem("preview-commit-record-denied") from None

    def publish_commit(
        self,
        inputs: CommitJobInput,
        *,
        claim: WorkflowJobClaim,
        actor: PreviewActor,
        now: Callable[[], str],
        poll: Callable[[], None] | None = None,
    ) -> WorkflowOutputReference:
        inputs = self._bind_commit(inputs, claim)
        running = self._queue.get(claim.job_id).state != "succeeded"
        expected_identity = self._verified_identity(inputs, claim, actor, now, poll, running=running)
        with self._transaction(inputs.preview.preview_id, write=True) as connection:
            actor = actor.model_copy(update={"occurred_at": now()})
            completed = connection.execute(
                "SELECT output_manifest_json FROM workflow_committed_outputs WHERE project_id=? AND job_id=?",
                (self._project, claim.job_id),
            ).fetchone()
            if completed is not None:
                self._prepared(connection, inputs, claim, actor, running=False)
                outputs = json.loads(completed[0])["outputs"]
                if len(outputs) != 1:
                    raise PreviewProblem("preview-commit-output-authority-mismatch")
                manifest = connection.execute(
                    "SELECT m.identity_sha256 FROM import_manifests m "
                    "JOIN import_manifest_seals s ON s.project_id=m.project_id "
                    "AND s.manifest_revision_id=m.revision_id "
                    "WHERE m.project_id=? AND m.revision_id=?",
                    (self._project, outputs[0]["revisionId"]),
                ).fetchone()
                if manifest is None or manifest[0] != expected_identity.sha256:
                    raise PreviewProblem("preview-commit-manifest-authority-mismatch")
                self._manifest_access(connection, outputs[0]["revisionId"])
                saved = _revision_with_connection(connection, self._project, outputs[0]["revisionId"])
                output = self._output(saved)
                self._queue._complete_with_connection(connection, claim, now=actor.occurred_at, outputs=(output,))
                return output
            draft = self._prepared(connection, inputs, claim, actor)
            if inputs.previous_manifest_revision_id is not None:
                self._manifest_access(connection, inputs.previous_manifest_revision_id)
            cursor = self._staged(connection, claim.attempt_id)
            try:
                identity = import_identity(
                    draft.authority,
                    (RecordDecision.model_validate_json(row[3]) for row in cursor),
                    expected_record_count=draft.record_count,
                )
            finally:
                cursor.close()
            if identity != expected_identity:
                raise PreviewProblem("preview-commit-prepared-identity-mismatch")
            existing = connection.execute(
                "SELECT m.revision_id, o.output_manifest_json, o.output_record_sha256 "
                "FROM import_manifests m JOIN import_manifest_seals s "
                "ON s.project_id=m.project_id AND s.manifest_revision_id=m.revision_id "
                "JOIN workflow_committed_outputs o ON o.project_id=m.project_id AND o.attempt_id=m.attempt_id "
                "JOIN workflow_queue_jobs j ON j.project_id=o.project_id AND j.job_id=o.job_id AND j.state='succeeded' "
                "WHERE m.project_id=? AND m.identity_sha256=?",
                (self._project, identity.sha256),
            ).fetchone()
            token = _UNIT_OF_WORKS.register(connection, self._project)
            try:
                if existing is not None:
                    self._manifest_access(connection, existing[0])
                    manifest = _revision_with_connection(connection, self._project, existing[0])
                    if self._queue._output_manifest((self._output(manifest),)) != tuple(existing[1:]):
                        raise PreviewProblem("preview-commit-output-authority-mismatch")
                else:
                    aggregates = _SqliteAggregateRepository(token)
                    receipt = connection.execute(
                        "SELECT receipt_revision_id FROM import_parse_completions "
                        "WHERE project_id=? AND preview_id=? AND attempt_id=?",
                        (self._project, inputs.preview.preview_id, inputs.parse_attempt_id),
                    ).fetchone()
                    parser = _revision_with_connection(connection, self._project, receipt[0])
                    created = 0
                    rows = self._staged(connection, claim.attempt_id)
                    try:
                        for row in rows:
                            if not row[2]:
                                continue
                            self._running(connection, claim, actor.model_copy(update={"occurred_at": now()}))
                            prior = connection.execute(
                                "SELECT revision_id FROM import_source_records WHERE project_id=? "
                                "AND source_sha256=? AND record_key=?",
                                (self._project, inputs.preview.source_sha256, row[1]),
                            ).fetchone()
                            if prior is not None:
                                continue
                            source_digest = source_assertion_key(self._project, inputs.preview.source_sha256, row[1])
                            revision = self._append_canonical(
                                aggregates,
                                kind="record",
                                label="Imported source record",
                                actor=actor,
                                parser=parser,
                                digest=source_digest,
                                key="import-source:" + source_digest,
                            )
                            connection.execute(
                                "INSERT INTO import_source_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    self._project,
                                    inputs.preview.source_sha256,
                                    row[1],
                                    revision.aggregate_id,
                                    revision.revision_id,
                                    inputs.preview.preview_id,
                                    inputs.parse_attempt_id,
                                    row[0],
                                ),
                            )
                            created += 1
                            _publication_step_completed("source-record-created")
                    finally:
                        rows.close()
                    member_digest = hashlib.sha256()
                    # The common event cannot carry 100k inputs. Bind the complete
                    # ordered dedicated membership by digest, without truncation.
                    for member in self._members(connection, inputs, claim, "pending"):
                        member_digest.update(json.dumps(member[1:], separators=(",", ":"), ensure_ascii=True).encode())
                        member_digest.update(b"\n")
                    digest = member_digest.hexdigest()
                    manifest = self._append_canonical(
                        aggregates,
                        kind="workflow",
                        label="Local import manifest",
                        actor=actor,
                        parser=parser,
                        digest=digest,
                        key="import-manifest:" + identity.sha256,
                    )
                    connection.execute(
                        "INSERT INTO import_manifests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            self._project,
                            manifest.revision_id,
                            manifest.aggregate_id,
                            claim.attempt_id,
                            inputs.preview.preview_id,
                            inputs.parse_attempt_id,
                            inputs.preview.source_sha256,
                            identity.sha256,
                            identity.effective_draft_sha256,
                            identity.record_count,
                            identity.selected_count,
                            created,
                            identity.selected_count - created,
                            actor.occurred_at,
                        ),
                    )
                    _publication_step_completed("manifest-created")
                    for member in self._members(connection, inputs, claim, manifest.revision_id):
                        connection.execute(
                            "INSERT INTO import_manifest_members VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            member,
                        )
                        _publication_step_completed("manifest-member-created")
                    connection.execute(
                        "INSERT INTO import_manifest_seals VALUES (?, ?, ?, ?)",
                        (
                            manifest.revision_id,
                            self._project,
                            digest,
                            actor.occurred_at,
                        ),
                    )
                    _publication_step_completed("manifest-sealed")
                completed_at = now()
                self._running(connection, claim, actor.model_copy(update={"occurred_at": completed_at}))
                output = self._output(manifest)
                connection.execute(
                    "INSERT INTO workflow_attempt_artifacts VALUES "
                    "(?, ?, ?, ?, ?, 'output', 'retained-incomplete', ?, ?, ?, ?, ?)",
                    (
                        claim.attempt_id,
                        self._project,
                        claim.job_id,
                        output.artifact_id,
                        output.revision_id,
                        output.content_hash,
                        output.media_type,
                        output.provenance_entity_id,
                        completed_at,
                        completed_at,
                    ),
                )
                _publication_step_completed("output-staged")
                self._queue._complete_with_connection(connection, claim, now=completed_at, outputs=(output,))
                _publication_step_completed("output-completed")
                return output
            finally:
                _UNIT_OF_WORKS.unregister(token)
