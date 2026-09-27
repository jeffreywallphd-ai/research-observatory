"""Portable, source-bound scholarly manifestations and human version decisions."""

import hashlib
import json
import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, computed_field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from .decisions import ReviewSource, WorkState

VersionKind = Literal[
    "preprint",
    "accepted-manuscript",
    "version-of-record",
    "erratum",
    "correction",
    "expression-of-concern",
    "retraction",
    "not-reported",
]
RelationKind = Literal["is-version-of", "supersedes", "erratum-for", "corrects", "expresses-concern", "retracts"]
WARNING_RELATIONS = frozenset({"erratum-for", "corrects", "expresses-concern", "retracts"})


def version_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class VersionDate(DraftValue):
    precision: Literal["unknown", "not-reported", "year", "month", "day"]
    value: Annotated[str, Field(min_length=4, max_length=10)] | None

    @model_validator(mode="after")
    def exact_precision(self) -> Self:
        if self.precision in {"unknown", "not-reported"}:
            if self.value is not None:
                raise ValueError("version-date-invalid")
            return self
        pattern = {"year": r"[0-9]{4}", "month": r"[0-9]{4}-[0-9]{2}", "day": r"[0-9]{4}-[0-9]{2}-[0-9]{2}"}[
            self.precision
        ]
        if self.value is None or re.fullmatch(pattern, self.value) is None:
            raise ValueError("version-date-invalid")
        date.fromisoformat(self.value + {"year": "-01-01", "month": "-01", "day": ""}[self.precision])
        return self


class VersionReference(DraftValue):
    version_id: Identity
    revision_id: Identity

    @model_validator(mode="after")
    def distinct_identity(self) -> Self:
        if self.version_id == self.revision_id:
            raise ValueError("version-identity-invalid")
        return self


class VersionEvidence(DraftValue):
    assertion_revision_id: Identity
    category: Literal["field", "identifier"]
    selector: Annotated[str, Field(min_length=1, max_length=128)]
    value_sha256: Digest


class VersionDefinition(DraftValue):
    kind: VersionKind
    assertion_revision_ids: Annotated[tuple[Identity, ...], Field(strict=False, min_length=1, max_length=256)]
    date: VersionDate

    @model_validator(mode="after")
    def ordered_sources(self) -> Self:
        if self.assertion_revision_ids != tuple(sorted(set(self.assertion_revision_ids))):
            raise ValueError("version-sources-invalid")
        return self


class UpdateRelationDraft(DraftValue):
    kind: RelationKind
    source: VersionReference
    target: VersionReference
    evidence: Annotated[tuple[VersionEvidence, ...], Field(strict=False, min_length=1, max_length=32)]
    date: VersionDate
    knowledge_status: Literal["adjudicated", "disputed"]

    @model_validator(mode="after")
    def directed_evidenced_relation(self) -> Self:
        if len({self.source.version_id, self.source.revision_id, self.target.version_id, self.target.revision_id}) != 4:
            raise ValueError("version-relation-endpoints-invalid")
        keys = [(item.assertion_revision_id, item.category, item.selector) for item in self.evidence]
        if len(keys) != len(set(keys)):
            raise ValueError("version-relation-evidence-invalid")
        return self


class WorkVersion(VersionReference):
    previous_revision_id: Identity | None
    definition: VersionDefinition
    decision_revision_id: Identity
    status_sha256: Digest

    @model_validator(mode="after")
    def retained_predecessor(self) -> Self:
        if self.previous_revision_id in {
            self.version_id,
            self.revision_id,
            self.decision_revision_id,
        } or self.decision_revision_id in {self.version_id, self.revision_id}:
            raise ValueError("version-predecessor-invalid")
        return self


class VersionRelation(DraftValue):
    relation_id: Identity
    revision_id: Identity
    decision_revision_id: Identity
    assertion: UpdateRelationDraft

    @model_validator(mode="after")
    def separate_relation_identity(self) -> Self:
        own = {self.relation_id, self.revision_id, self.decision_revision_id}
        endpoints = {
            self.assertion.source.version_id,
            self.assertion.source.revision_id,
            self.assertion.target.version_id,
            self.assertion.target.revision_id,
        }
        if len(own) != 3 or own & endpoints:
            raise ValueError("version-relation-identity-invalid")
        return self


class VersionPreference(DraftValue):
    decision_id: Identity
    revision_id: Identity
    previous_revision_id: Identity | None
    work_id: Identity
    work_revision_id: Identity
    command_decision_revision_id: Identity
    selected: VersionReference
    membership_sha256: Digest
    status_sha256: Digest

    @model_validator(mode="after")
    def separate_preference_identity(self) -> Self:
        identities = (
            self.decision_id,
            self.revision_id,
            self.work_id,
            self.work_revision_id,
            self.command_decision_revision_id,
            self.selected.version_id,
            self.selected.revision_id,
        )
        if len(set(identities)) != len(identities) or self.previous_revision_id in set(identities):
            raise ValueError("version-preference-identity-invalid")
        return self


class VersionPlacement(DraftValue):
    version_id: Identity
    work_ids: Annotated[tuple[Identity, ...], Field(strict=False, min_length=1, max_length=256)]
    state: Literal["assigned", "requires-review"]

    @model_validator(mode="after")
    def coherent_placement(self) -> Self:
        if (
            self.work_ids != tuple(sorted(set(self.work_ids)))
            or (len(self.work_ids) == 1) != (self.state == "assigned")
            or self.version_id in self.work_ids
        ):
            raise ValueError("version-placement-invalid")
        return self


class PreferenceState(DraftValue):
    work_id: Identity
    state: Literal["not-reported", "current", "requires-review"]
    preference_revision_id: Identity | None
    selected: VersionReference | None

    @model_validator(mode="after")
    def explicit_standing(self) -> Self:
        if (self.state == "not-reported") != (self.preference_revision_id is None and self.selected is None):
            raise ValueError("version-preference-state-invalid")
        if self.state != "not-reported" and (self.preference_revision_id is None or self.selected is None):
            raise ValueError("version-preference-state-invalid")
        return self


class VersionContext(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    works: Annotated[tuple[WorkState, ...], Field(strict=False, min_length=1, max_length=8)]
    versions: Annotated[tuple[WorkVersion, ...], Field(strict=False, max_length=256)]
    placements: Annotated[tuple[VersionPlacement, ...], Field(strict=False, max_length=256)]
    relations: Annotated[tuple[VersionRelation, ...], Field(strict=False, max_length=512)]
    preferences: Annotated[tuple[VersionPreference, ...], Field(strict=False, max_length=64)]
    preference_states: Annotated[tuple[PreferenceState, ...], Field(strict=False, min_length=1, max_length=8)]
    sources: Annotated[tuple[ReviewSource, ...], Field(strict=False, max_length=512)] = Field(repr=False)

    @model_validator(mode="after")
    def unique_context(self) -> Self:
        for identities in (
            tuple(item.work_id for item in self.works),
            tuple(item.version_id for item in self.versions),
            tuple(item.version_id for item in self.placements),
            tuple(item.revision_id for item in self.relations),
            tuple(item.revision_id for item in self.preferences),
            tuple(item.assertion_revision_id for item in self.sources),
        ):
            if len(identities) != len(set(identities)):
                raise ValueError("version-context-duplicate")
        if {item.version_id for item in self.versions} != {item.version_id for item in self.placements}:
            raise ValueError("version-context-placement-mismatch")
        if len(self.preference_states) != len(self.works) or {item.work_id for item in self.preference_states} != {
            item.work_id for item in self.works
        }:
            raise ValueError("version-context-preference-mismatch")
        sources = {item.assertion_revision_id for item in self.sources}
        if any(not set(item.definition.assertion_revision_ids) <= sources for item in self.versions):
            raise ValueError("version-context-sources-incomplete")
        if any(source.assertion.project_id != self.project_id for source in self.sources):
            raise ValueError("version-context-project-mismatch")
        version_ids = {item.version_id for item in self.versions}
        if any(item.disposition != "active" for item in self.works) or any(
            not {item.assertion.source.version_id, item.assertion.target.version_id} <= version_ids
            or not {evidence.assertion_revision_id for evidence in item.assertion.evidence} <= sources
            for item in self.relations
        ):
            raise ValueError("version-context-relations-invalid")
        expected = preference_standing(self.works, self.versions, self.placements, self.relations, self.preferences)
        if self.preference_states != expected:
            raise ValueError("version-context-preference-mismatch")
        return self

    @property
    def fingerprint(self) -> str:
        return version_digest(self.model_dump(mode="json", by_alias=True, exclude_computed_fields=True))

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def context_sha256(self) -> str:
        return self.fingerprint


def status_fingerprint(
    versions: tuple[WorkVersion, ...],
    placements: tuple[VersionPlacement, ...],
    relations: tuple[VersionRelation, ...],
    work_id: str,
) -> str:
    identities = {item.version_id for item in placements if work_id in item.work_ids}
    return version_digest(
        [
            [item.model_dump(mode="json", by_alias=True) for item in versions if item.version_id in identities],
            [item.model_dump(mode="json", by_alias=True) for item in placements if item.version_id in identities],
            [
                item.model_dump(mode="json", by_alias=True)
                for item in relations
                if item.assertion.source.version_id in identities or item.assertion.target.version_id in identities
            ],
        ]
    )


def preference_standing(
    works: tuple[WorkState, ...],
    versions: tuple[WorkVersion, ...],
    placements: tuple[VersionPlacement, ...],
    relations: tuple[VersionRelation, ...],
    preferences: tuple[VersionPreference, ...],
) -> tuple[PreferenceState, ...]:
    result = []
    current = {item.version_id: item.revision_id for item in versions}
    for work in works:
        placed = {item.version_id for item in placements if work.work_id in item.work_ids}
        own = [item for item in preferences if item.work_id == work.work_id]
        inherited = [item for item in preferences if item.selected.version_id in placed]
        candidates = own or inherited
        if not candidates:
            result.append(
                PreferenceState(work_id=work.work_id, state="not-reported", preference_revision_id=None, selected=None)
            )
            continue
        preference = candidates[-1]
        exact_placement = any(
            item.version_id == preference.selected.version_id and item.work_ids == (work.work_id,)
            for item in placements
        )
        valid = (
            bool(own)
            and exact_placement
            and work.previous_revision_id == preference.work_revision_id
            and work.decision_revision_id == preference.command_decision_revision_id
            and current.get(preference.selected.version_id) == preference.selected.revision_id
            and preference.membership_sha256 == version_digest(list(work.assertion_revision_ids))
            and preference.status_sha256 == status_fingerprint(versions, placements, relations, work.work_id)
        )
        result.append(
            PreferenceState(
                work_id=work.work_id,
                state="current" if valid else "requires-review",
                preference_revision_id=preference.revision_id,
                selected=preference.selected,
            )
        )
    return tuple(result)


class VersionPlan(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    action: Literal["register", "revise", "relate", "prefer"]
    work_ids: Annotated[tuple[Identity, ...], Field(strict=False, min_length=1, max_length=8)]
    context_sha256: Digest
    rationale: Annotated[str, Field(min_length=1, max_length=4000)] = Field(repr=False)
    definition: VersionDefinition | None = None
    version: VersionReference | None = None
    relation: UpdateRelationDraft | None = None
    previous_preference_revision_id: Identity | None = None

    @model_validator(mode="after")
    def complete_action(self) -> Self:
        if self.work_ids != tuple(sorted(set(self.work_ids))):
            raise ValueError("version-work-scope-invalid")
        shape = (self.definition is not None, self.version is not None, self.relation is not None)
        if (
            shape
            != {
                "register": (True, False, False),
                "revise": (True, True, False),
                "relate": (False, False, True),
                "prefer": (False, True, False),
            }[self.action]
        ):
            raise ValueError("version-action-invalid")
        if self.action == "prefer":
            if len(self.work_ids) != 1:
                raise ValueError("version-preference-scope-invalid")
        elif self.previous_preference_revision_id is not None:
            raise ValueError("version-action-invalid")
        return self

    @property
    def fingerprint(self) -> str:
        return version_digest(self.model_dump(mode="json", by_alias=True))


class VersionPreview(DraftValue):
    command_id: Identity
    plan_sha256: Digest
    context_sha256: Digest
    preview_sha256: Digest
    affected_count: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]


class VersionCommand(DraftValue):
    command_id: Identity
    plan: VersionPlan
    expected_preview_sha256: Digest


class VersionOutcome(DraftValue):
    command_id: Identity
    decision_id: Identity
    decision_revision_id: Identity
    plan_sha256: Digest
    version_revisions: Annotated[tuple[VersionReference, ...], Field(strict=False, max_length=256)]
    relation_revision_id: Identity | None
    preference_revision_id: Identity | None
    work_states: Annotated[tuple[WorkState, ...], Field(strict=False, max_length=8)]
    dependency_run_ids: Annotated[tuple[Identity, ...], Field(strict=False, max_length=264)]

    @model_validator(mode="after")
    def coherent_publication(self) -> Self:
        own = (self.command_id, self.decision_id, self.decision_revision_id)
        revisions = [item.revision_id for item in self.version_revisions] + [
            item.revision_id for item in self.work_states
        ]
        revisions += [item for item in (self.relation_revision_id, self.preference_revision_id) if item is not None]
        if len(set(own)) != len(own) or len(set(revisions)) != len(revisions) or set(own) & set(revisions):
            raise ValueError("version-outcome-identity-invalid")
        for ids in (
            tuple(item.version_id for item in self.version_revisions),
            tuple(item.work_id for item in self.work_states),
            self.dependency_run_ids,
        ):
            if len(set(ids)) != len(ids):
                raise ValueError("version-outcome-identity-invalid")
        if not self.work_states or any(
            item.disposition != "active" or item.decision_revision_id != self.decision_revision_id
            for item in self.work_states
        ):
            raise ValueError("version-outcome-work-invalid")
        return self


class VersionWorkPage(DraftValue):
    project_id: ProjectIdentity
    after: Identity | None
    next_after: Identity | None
    items: Annotated[tuple[WorkState, ...], Field(strict=False, max_length=32)]

    @model_validator(mode="after")
    def ordered_current_works(self) -> Self:
        ids = tuple(item.work_id for item in self.items)
        if ids != tuple(sorted(set(ids))) or any(item.disposition != "active" for item in self.items):
            raise ValueError("version-work-page-invalid")
        if self.after is not None and (
            any(identity <= self.after for identity in ids)
            or (self.next_after is not None and self.next_after <= self.after)
        ):
            raise ValueError("version-work-page-invalid")
        if self.next_after is not None and any(identity > self.next_after for identity in ids):
            raise ValueError("version-work-page-invalid")
        return self
