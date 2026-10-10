"""Read-only adapter to current canonical scholarly identity and authority.

The trusted caller holds the project/rights lifecycle fence. An unavailable or
denied source fails the whole snapshot: omission cannot prove uniqueness.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

from .document_references import (
    MAX_REFERENCE_SECONDS,
    MAX_REFERENCES,
    ReferenceEntry,
    ReferenceProblem,
    ReferenceWorkSnapshot,
)
from .ports.reconciliation import ReconciliationSourceResolver
from .reconciliation.candidates import DEFAULT_CONFIG, CandidateRecord
from .reconciliation.contracts import CanonicalWorkReference
from .reconciliation.exact import (
    IdentifierAssertion,
    MatchAssessment,
    MatchDisposition,
    SourceOrigin,
    assess_match,
    exact_keys,
    select_field,
)
from .reconciliation.feature_cache import candidate_record
from .reconciliation.identifiers import NORMALIZER_VERSION
from .reconciliation_repository import SqliteReconciliationRepository, _digest
from .repositories import _projection_content_sha256


@dataclass(frozen=True, slots=True)
class ReferenceCatalogSnapshot:
    works: tuple[ReferenceWorkSnapshot, ...]
    assessments: tuple[MatchAssessment, ...]
    input_revision_ids: tuple[str, ...]
    sha256: str


class ReferenceMatchingRepository:
    def __init__(self, database, project_id, *, admit=lambda _size: None):
        self.reconciliation = SqliteReconciliationRepository(database, project_id)
        self.project = project_id
        self.admit = admit

    def snapshot(
        self,
        connection,
        aggregates,
        entries: tuple[ReferenceEntry, ...],
        *,
        resolve: ReconciliationSourceResolver,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> ReferenceCatalogSnapshot:
        deadline = time.monotonic() + MAX_REFERENCE_SECONDS

        def checkpoint():
            if cancelled():
                raise ReferenceProblem("reference-operation-cancelled")
            if time.monotonic() > deadline:
                raise ReferenceProblem("reference-operation-limit")

        checkpoint()
        if len(entries) > MAX_REFERENCES:
            raise ReferenceProblem("reference-operation-limit")
        repo = self.reconciliation
        # Include legacy Work identities as well: an unsealed legacy head is an
        # explicit failure, never an invisible exclusion from exact matching.
        ids = connection.execute(
            "SELECT work_id FROM reconciliation_work_states WHERE project_id=? "
            "UNION SELECT work_id FROM reconciliation_work_revisions WHERE project_id=? "
            "ORDER BY work_id LIMIT 10001",
            (self.project, self.project),
        ).fetchall()
        if len(ids) > DEFAULT_CONFIG.max_records:
            raise ReferenceProblem("reference-operation-limit")
        admitted = set()

        def resolved(address):
            source = resolve(address)
            key = _digest(address.model_dump(mode="json"))
            if key not in admitted:
                self.admit(len(source.model_dump_json(by_alias=True).encode()))
                admitted.add(key)
            return source

        prepared, collect = repo._source_snapshot(resolved, checkpoint=checkpoint)
        works, states = [], []
        material: set[str] = set()
        inspected: set[str] = set()
        for (work_id,) in ids:
            checkpoint()
            state = repo._state(connection, work_id)
            states.append(state.model_dump(mode="json", by_alias=True))
            material.add(state.revision_id)
            if state.decision_revision_id:
                material.add(state.decision_revision_id)
            if state.disposition != "active":
                continue
            sources = repo._work_sources(connection, work_id, collect)
            observations: dict[str, list[tuple[str, str, SourceOrigin]]] = {}
            identifiers: list[IdentifierAssertion] = []
            for source in sources:
                checkpoint()
                inspected.add(source.result.assertion_revision_id)
                identifiers.extend(source.assertion.identifiers)
                record = candidate_record(source.result.assertion_revision_id, source.assertion)
                for name, values in record.fields:
                    source_fields = [
                        field
                        for field in source.assertion.fields
                        if {"author": "authors", "container": "venue"}.get(field.name, field.name) == name
                    ]
                    for value in values:
                        origins = {field.origin for field in source_fields if field.observed == value}
                        if name == "authors" and any(field.name == "author" for field in source_fields):
                            origins = {field.origin for field in source_fields}
                        origin: SourceOrigin = "correction" if origins == {"correction"} else "observed"
                        observations.setdefault(name, []).append((source.result.assertion_revision_id, value, origin))
            fields = []
            for name, observations_for_field in sorted(observations.items()):
                selection = select_field(tuple(observations_for_field))
                selected = (
                    (selection.selected,)
                    if selection.selected is not None
                    else tuple(sorted({v[1] for v in observations_for_field}))
                )
                fields.append((name, selected))
            works.append(
                ReferenceWorkSnapshot(
                    CanonicalWorkReference(work_id=work_id, revision_id=state.revision_id),
                    CandidateRecord(work_id, state.revision_id, tuple(fields), tuple(identifiers)),
                )
            )
        assessments = []
        keys = {work.target.work_id: exact_keys(work.record.identifiers) for work in works}
        for entry in entries:
            checkpoint()
            incoming = tuple(i.assertion for i in entry.identifiers)
            indexed = repo._identifier_assessment(connection, incoming, collect, inspected=inspected)
            incoming_keys = exact_keys(incoming)
            overlapping = {
                work.target.work_id: work.record.identifiers
                for work in works
                if incoming_keys & keys[work.target.work_id]
            }
            complete = assess_match(incoming, overlapping)
            candidates = tuple(sorted(set(indexed.candidates) | set(complete.candidates)))
            flags = tuple(sorted(set(indexed.flags) | set(complete.flags)))
            # Both the complete current catalog and the index must establish the
            # same unique target. The index can add uncertainty, never hide it.
            target = complete.target if complete.target == indexed.target and not flags else None
            disposition: MatchDisposition = (
                "exact-linked" if target else "review-required" if candidates or flags else "new-work"
            )
            assessments.append(
                MatchAssessment(
                    disposition,
                    target,
                    candidates,
                    flags,
                    tuple(sorted(set(indexed.matching_keys) | set(complete.matching_keys))),
                )
            )
        assessment_tuple = tuple(assessments)
        for revision in sorted(inspected):
            checkpoint()
            stored = repo._authorized_load(connection, revision, collect)
            material.update((revision, stored.assertion.source_revision_id, stored.assertion.address.revision_id))
            assignment = repo._assignment(connection, revision)
            if assignment is not None:
                material.add(assignment.revision_id)
                if assignment.decision_revision_id:
                    material.add(assignment.decision_revision_id)
        ordered = tuple(sorted(material))
        repo._require_fresh_inputs(aggregates, ordered, checkpoint=checkpoint)
        fingerprint = _digest(
            {
                "projectId": self.project,
                "normalizer": NORMALIZER_VERSION,
                "ranking": DEFAULT_CONFIG.fingerprint,
                "workStates": states,
                "works": [
                    (
                        w.target.model_dump(mode="json"),
                        w.record.fields,
                        [i.model_dump(mode="json", by_alias=True) for i in w.record.identifiers],
                    )
                    for w in works
                ],
                "assessments": [asdict(a) for a in assessment_tuple],
                "sources": sorted(
                    (key, value.model_dump(mode="json", by_alias=True)) for key, value in prepared.items()
                ),
                "inputs": [
                    (revision, _projection_content_sha256(aggregates.get_revision(revision))) for revision in ordered
                ],
            }
        )
        checkpoint()
        return ReferenceCatalogSnapshot(tuple(works), assessment_tuple, ordered, fingerprint)
