"""Immutable, sparse researcher revisions over accepted import observations.

Undo appends a revision pointing to its restored history, not a deletion or a
copy of the complete batch. Reads use that history, including after another edit.
This adapter does not create canonical SourceRecords or authorize import commits.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator

from .domain_contracts import new_uuid_v7
from .import_preview_repository import _actor, _SqliteImportPreviewRepository
from .ingestion.import_drafts import (
    DraftAuthority,
    ImportOptions,
    ImportRights,
    MappingProfile,
    RecordDecision,
    RightsAction,
    effective_draft_sha256,
    propose_fields,
    review_record,
    spreadsheet_cell,
)
from .ingestion.preview_records import StoredImportRecord
from .ingestion.reference_imports import ImportRecord, ImportSource
from .ports.import_previews import (
    PreviewDraft,
    PreviewDraftChange,
    PreviewDraftRecord,
    PreviewProblem,
    PreviewState,
)
from .storage import CanonicalConnection

_HISTORY = """
    WITH RECURSIVE history(revision) AS (
        SELECT :revision
        UNION ALL
        SELECT COALESCE(d.undo_revision, d.predecessor_revision)
          FROM import_draft_revisions d JOIN history h ON d.revision=h.revision
         WHERE d.preview_id=:preview AND d.project_id=:project
           AND COALESCE(d.undo_revision, d.predecessor_revision) IS NOT NULL
    )
"""
_RIGHTS_ACTIONS: tuple[RightsAction, ...] = (
    "store",
    "inspect",
    "index",
    "derive",
    "model-use",
    "quote",
    "export",
    "share",
)


class SqliteImportDraftRepository(_SqliteImportPreviewRepository):
    def _latest(self, connection: CanonicalConnection, preview: str) -> int:
        return int(
            self._query(
                connection,
                """
            SELECT COALESCE(MAX(revision), 0) FROM import_draft_revisions
             WHERE preview_id=:preview AND project_id=:project
        """,
                preview,
            ).fetchone()[0]
        )

    def _draft(self, connection: CanonicalConnection, state: PreviewState, revision: int) -> PreviewDraft:
        if type(revision) is not int or revision < 1:
            raise PreviewProblem("preview-draft-revision-invalid")
        row = self._query(
            connection,
            """
            SELECT d.predecessor_revision, d.undo_revision, d.attempt_id,
                   d.mapping_json, d.rights_json, d.options_json, c.record_count
              FROM import_draft_revisions d JOIN import_parse_completions c
                ON c.preview_id=d.preview_id AND c.project_id=d.project_id AND c.attempt_id=d.attempt_id
             WHERE d.preview_id=:preview AND d.project_id=:project AND d.revision=:revision
        """,
            state.preview_id,
            revision=revision,
        ).fetchone()
        if row is None or state.source_sha256 is None:
            raise PreviewProblem("preview-draft-not-found")
        return PreviewDraft(
            revision=revision,
            predecessor_revision=row[0],
            restore_revision=row[1],
            attempt_id=row[2],
            record_count=row[6],
            authority=DraftAuthority(
                project_id=self._project,
                preview_id=state.preview_id,
                source_sha256=state.source_sha256,
                mapping=MappingProfile.model_validate_json(row[3]),
                rights=ImportRights.model_validate_json(row[4]),
                options=ImportOptions.model_validate_json(row[5]),
            ),
        )

    def draft(self, preview_id: str, *, revision: int | None = None) -> PreviewDraft:
        with self._transaction(preview_id) as connection:
            state = self._read(connection, preview_id)
            self._active(state)
            attempt = self._accepted_attempt(connection, preview_id)
            draft = self._draft(
                connection, state, self._latest(connection, preview_id) if revision is None else revision
            )
            if draft.attempt_id != attempt:
                raise PreviewProblem("preview-draft-attempt-mismatch")
            return draft

    def _mapping(self, connection: CanonicalConnection, preview: str, mapping: MappingProfile) -> None:
        # A project mapping identity/revision always denotes the same immutable bytes,
        # even after undo or reuse in another preview. New revisions use the high-water mark.
        rows = self._query(
            connection,
            """
            SELECT mapping_json FROM import_draft_revisions
             WHERE project_id=:project AND :preview IS NOT NULL
               AND json_extract(mapping_json, '$.profileId')=:profile
        """,
            preview,
            profile=mapping.profile_id,
        )
        maximum = 0
        exists = False
        for row in rows:
            previous = MappingProfile.model_validate_json(row[0])
            maximum = max(maximum, previous.revision)
            if previous.revision == mapping.revision:
                if previous != mapping:
                    raise PreviewProblem("preview-mapping-revision-conflict")
                exists = True
        if not exists and mapping.revision != maximum + 1:
            raise PreviewProblem("preview-mapping-revision-conflict")

    def _decision(self, connection: CanonicalConnection, preview: str, revision: int, ordinal: int):
        row = self._query(
            connection,
            _HISTORY
            + """
            SELECT d.decision_json, r.mapping_json
              FROM import_record_decisions d JOIN import_draft_revisions r
                ON r.preview_id=d.preview_id AND r.project_id=d.project_id AND r.revision=d.revision
             WHERE d.preview_id=:preview AND d.project_id=:project AND d.ordinal=:ordinal
               AND d.revision IN (SELECT revision FROM history) ORDER BY d.revision DESC LIMIT 1
        """,
            preview,
            revision=revision,
            ordinal=ordinal,
        ).fetchone()
        if row is None:
            return None, None
        return RecordDecision.model_validate_json(row[0]), MappingProfile.model_validate_json(row[1])

    @staticmethod
    def _project_row(record: ImportRecord, draft: PreviewDraft, previous, previous_mapping) -> PreviewDraftRecord:
        proposal = propose_fields(record, draft.authority.mapping)
        fields = proposal.fields
        included = record.kind == "record" and record.status == "parsed" and not proposal.conflicts
        rights = None
        if previous is not None:
            if previous.record_key != record.record_key or previous.ordinal != record.ordinal:
                raise PreviewProblem("preview-draft-record-mismatch")
            included, rights = previous.included, previous.rights
            if previous_mapping == draft.authority.mapping:
                fields = previous.fields
            else:
                # Re-map source suggestions, retain explicit researcher corrections,
                # selection and rights. Source observations are never rewritten.
                corrections = tuple(field for field in previous.fields if field.origin == "correction")
                corrected_names = {field.name for field in corrections}
                fields = tuple(field for field in fields if field.name not in corrected_names) + corrections
        warnings = set(proposal.warnings)
        values: dict[str, set[str]] = {}
        for field in fields:
            values.setdefault(field.name, set()).add(field.value)
        conflicts = {name for name, candidates in values.items() if name != "author" and len(candidates) > 1}
        if conflicts:
            included = False
            warnings.add("mapping-conflict")
        decision = review_record(record, included=included, fields=fields, rights=rights)
        if not included and record.kind == "record":
            warnings.add("excluded")
        return PreviewDraftRecord(record, decision, tuple(sorted(warnings)))

    def _record(self, connection: CanonicalConnection, state: PreviewState, attempt: str, ordinal: int) -> ImportRecord:
        row = self._query(
            connection,
            """
            SELECT record_key, record_json FROM import_parse_records
             WHERE preview_id=:preview AND project_id=:project AND attempt_id=:attempt AND ordinal=:ordinal
        """,
            state.preview_id,
            attempt=attempt,
            ordinal=ordinal,
        ).fetchone()
        if row is None or state.source_sha256 is None:
            raise PreviewProblem("preview-draft-record-mismatch")
        record = StoredImportRecord.model_validate_json(row[1]).restore(
            ImportSource(state.source_name, state.source_sha256, state.encoding),
            state.format_name,
        )
        if record.record_key != row[0]:
            raise PreviewProblem("preview-draft-record-mismatch")
        return record

    def _restore_rights(
        self,
        connection: CanonicalConnection,
        preview_id: str,
        current: PreviewDraft,
        restored: PreviewDraft,
    ) -> None:
        def does_not_broaden(before: ImportRights, after: ImportRights) -> None:
            if any(after.permits(action) and not before.permits(action) for action in _RIGHTS_ACTIONS):
                raise PreviewProblem("preview-rights-restore-denied")

        does_not_broaden(current.authority.rights, restored.authority.rights)
        # Include records outside the visible page and every historical branch.
        # Stream only changed ordinals; untouched records use the checked defaults.
        rows = self._query(
            connection,
            """
            SELECT DISTINCT ordinal FROM import_record_decisions
             WHERE preview_id=:preview AND project_id=:project ORDER BY ordinal
        """,
            preview_id,
        )
        try:
            for row in rows:
                before, _ = self._decision(connection, preview_id, current.revision, row[0])
                after, _ = self._decision(connection, preview_id, restored.revision, row[0])
                does_not_broaden(
                    before.rights if before and before.rights else current.authority.rights,
                    after.rights if after and after.rights else restored.authority.rights,
                )
        finally:
            rows.close()

    def revise_draft(self, preview_id: str, change: PreviewDraftChange) -> PreviewDraft:
        change = PreviewDraftChange.model_validate(change)
        actor = _actor(change.actor)
        if len(change.model_dump_json(by_alias=True).encode("utf-8")) > 8 * 1024 * 1024:
            raise PreviewProblem("preview-draft-change-limit")
        with self._transaction(preview_id, write=True) as connection:
            state = self._read(connection, preview_id)
            self._active(state)
            attempt = self._accepted_attempt(connection, preview_id)
            latest = self._latest(connection, preview_id)
            if latest != change.expected_revision:
                raise PreviewProblem("preview-draft-revision-conflict")
            previous = self._draft(connection, state, latest) if latest else None
            restored = self._draft(connection, state, change.restore_revision) if change.restore_revision else None
            if restored and previous:
                self._restore_rights(connection, preview_id, previous, restored)
            base = restored or previous
            mapping = change.mapping or (
                base.authority.mapping
                if base
                else MappingProfile(
                    profile_id=new_uuid_v7(),
                    revision=1,
                    predecessor_revision=None,
                    mode="automatic",
                    bindings=(),
                )
            )
            if previous and mapping.profile_id != previous.authority.mapping.profile_id:
                raise PreviewProblem("preview-mapping-revision-conflict")
            if mapping.mode == "columns" and state.format_name != "csv":
                raise PreviewProblem("preview-column-mapping-requires-csv")
            self._mapping(connection, preview_id, mapping)
            rights = change.rights or (base.authority.rights if base else state.rights)
            options = change.options or (base.authority.options if base else ImportOptions())
            revision = latest + 1
            self._query(
                connection,
                """
                INSERT INTO import_draft_revisions VALUES
                (:preview, :project, :revision, :previous, :attempt, :mapping, :rights, :options,
                 :restore, :actor, :trace, :created)
            """,
                preview_id,
                revision=revision,
                previous=latest or None,
                attempt=attempt,
                mapping=mapping.model_dump_json(by_alias=True),
                rights=rights.model_dump_json(by_alias=True),
                options=options.model_dump_json(by_alias=True),
                restore=change.restore_revision,
                actor=actor.actor_id,
                trace=actor.trace_id,
                created=actor.occurred_at,
            )
            for decision in change.decisions:
                record = self._record(connection, state, attempt, decision.ordinal)
                if record.record_key != decision.record_key:
                    raise PreviewProblem("preview-draft-record-mismatch")
                validated = review_record(
                    record,
                    included=decision.included,
                    fields=decision.fields,
                    rights=decision.rights,
                )
                proposed = propose_fields(record, mapping).fields
                if any(field.origin != "correction" and field not in proposed for field in validated.fields):
                    raise PreviewProblem("preview-draft-mapping-mismatch")
                # Changing a decision is not a bypass around current per-record rights.
                if previous:
                    prior, _ = self._decision(connection, preview_id, latest, record.ordinal)
                    if prior and prior.rights and not prior.rights.permits("inspect"):
                        raise PreviewProblem("preview-record-rights-denied")
                self._query(
                    connection,
                    """
                    INSERT INTO import_record_decisions VALUES
                    (:preview, :project, :revision, :attempt, :ordinal, :key, :decision)
                """,
                    preview_id,
                    revision=revision,
                    attempt=attempt,
                    ordinal=record.ordinal,
                    key=record.record_key,
                    decision=validated.model_dump_json(by_alias=True),
                )
            self._event(connection, preview_id, "draft-revised", actor)
            return self._draft(connection, self._read(connection, preview_id), revision)

    def draft_page(
        self,
        preview_id: str,
        *,
        revision: int,
        after: int,
        limit: int,
    ) -> tuple[PreviewDraftRecord, ...]:
        if type(after) is not int or not 0 <= after <= 200000 or type(limit) is not int or not 1 <= limit <= 100:
            raise PreviewProblem("preview-page-limit")
        with self._transaction(preview_id) as connection:
            state = self._read(connection, preview_id)
            self._active(state)
            attempt = self._accepted_attempt(connection, preview_id)
            draft = self._draft(connection, state, revision)
            current = self._latest(connection, preview_id)
            if draft.attempt_id != attempt:
                raise PreviewProblem("preview-draft-attempt-mismatch")
            result: list[PreviewDraftRecord] = []
            size = 0
            for ordinal in range(after + 1, min(draft.record_count, after + limit) + 1):
                previous, mapping = self._decision(connection, preview_id, revision, ordinal)
                current_decision, _ = self._decision(connection, preview_id, current, ordinal)
                for decision in (previous, current_decision):
                    if decision and decision.rights and not decision.rights.permits("inspect"):
                        raise PreviewProblem("preview-record-rights-denied")
                record = self._record(connection, state, attempt, ordinal)
                row = self._project_row(record, draft, previous, mapping)
                size += len(StoredImportRecord.from_record(record).model_dump_json().encode("utf-8"))
                size += len(row.decision.model_dump_json().encode("utf-8"))
                if size > 16 * 1024 * 1024:
                    if not result:
                        raise PreviewProblem("preview-draft-record-limit")
                    break
                result.append(row)
            return tuple(result)

    def _record_access(self, connection: CanonicalConnection, preview_id: str, ordinal: int) -> None:
        revision = self._latest(connection, preview_id)
        if revision:
            decision, _ = self._decision(connection, preview_id, revision, ordinal)
            if decision and decision.rights and not decision.rights.permits("inspect"):
                raise PreviewProblem("preview-record-rights-denied")

    def _rows(self, preview_id: str, revision: int) -> Iterator[PreviewDraftRecord]:
        count = self.draft(preview_id, revision=revision).record_count
        after = 0
        while after < count:
            page = self.draft_page(preview_id, revision=revision, after=after, limit=100)
            if not page:
                raise PreviewProblem("preview-draft-incomplete")
            yield from page
            after = page[-1].record.ordinal

    def draft_digest(self, preview_id: str, *, revision: int) -> str:
        draft = self.draft(preview_id, revision=revision)
        return effective_draft_sha256(draft.authority, (row.decision for row in self._rows(preview_id, revision)))

    def diagnostic_report(self, preview_id: str, *, revision: int) -> Iterator[str]:
        count = self.draft(preview_id, revision=revision).record_count
        yield "ordinal,line_start,line_end,status,diagnostic\r\n"
        after = 0
        while after < count:
            page = self.draft_page(preview_id, revision=revision, after=after, limit=100)
            if not page:
                raise PreviewProblem("preview-draft-incomplete")
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            for row in page:
                for warning in row.warnings or ("none",):
                    writer.writerow(
                        (
                            row.record.ordinal,
                            row.record.line_start,
                            row.record.line_end,
                            row.record.status,
                            spreadsheet_cell(warning),
                        )
                    )
            after = page[-1].record.ordinal
            yield output.getvalue()
