"""Exact human review plans, complete partitions, and append-only Work state."""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, computed_field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity
from .candidates import ALGORITHM, DEFAULT_CONFIG, FEATURE_VERSION
from .contracts import SourceAssertion

type Members = Annotated[tuple[Identity, ...], Field(strict=False, max_length=256)]
type GroupName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,31}$")]


def _fingerprint(value: DraftValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value.model_dump(mode="json", by_alias=True, exclude_computed_fields=True),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


class WorkState(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    work_id: Identity
    revision_id: Identity
    previous_revision_id: Identity | None
    disposition: Literal["active", "alias"]
    alias_target: Identity | None
    assertion_revision_ids: Members
    decision_revision_id: Identity | None

    @model_validator(mode="after")
    def complete_state(self) -> Self:
        if self.assertion_revision_ids != tuple(sorted(set(self.assertion_revision_ids))):
            raise ValueError("review-membership-invalid")
        if self.previous_revision_id == self.revision_id or self.work_id == self.revision_id:
            raise ValueError("review-predecessor-invalid")
        if self.disposition == "active":
            if not self.assertion_revision_ids or self.alias_target is not None:
                raise ValueError("review-active-state-invalid")
        elif (
            self.assertion_revision_ids
            or self.alias_target is None
            or self.alias_target == self.work_id
            or self.previous_revision_id is None
            or self.decision_revision_id is None
        ):
            raise ValueError("review-alias-state-invalid")
        return self

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


class SourcePartition(DraftValue):
    group: GroupName
    existing_work_id: Identity | None
    assertion_revision_ids: Annotated[tuple[Identity, ...], Field(strict=False, min_length=1, max_length=256)]

    @model_validator(mode="after")
    def unique_members(self) -> Self:
        if self.assertion_revision_ids != tuple(sorted(set(self.assertion_revision_ids))):
            raise ValueError("review-partition-invalid")
        return self


class AliasPlan(DraftValue):
    work_id: Identity
    revision_id: Identity
    target_group: GroupName


class ReviewPlan(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    action: Literal["merge", "split", "assign"]
    works: Annotated[tuple[WorkState, ...], Field(strict=False, max_length=32)]
    unassigned_assertion_revision_ids: Members
    partitions: Annotated[tuple[SourcePartition, ...], Field(strict=False, min_length=1, max_length=32)]
    aliases: Annotated[tuple[AliasPlan, ...], Field(strict=False, max_length=256)]
    conflict_disposition: Literal["retain-all"]
    evidence_sha256: Digest
    rationale: Annotated[str, Field(min_length=1, max_length=2048)] = Field(repr=False)

    @model_validator(mode="after")
    def complete_partition(self) -> Self:
        work_ids = {item.work_id for item in self.works}
        if len(work_ids) != len(self.works) or any(item.disposition != "active" for item in self.works):
            raise ValueError("review-inputs-invalid")
        if self.unassigned_assertion_revision_ids != tuple(sorted(set(self.unassigned_assertion_revision_ids))):
            raise ValueError("review-unassigned-invalid")
        source_ids = [member for work in self.works for member in work.assertion_revision_ids]
        source_ids.extend(self.unassigned_assertion_revision_ids)
        if not source_ids or len(source_ids) != len(set(source_ids)) or len(source_ids) > 512:
            raise ValueError("review-inputs-invalid")
        outputs = [member for group in self.partitions for member in group.assertion_revision_ids]
        if len(outputs) != len(set(outputs)) or set(outputs) != set(source_ids):
            raise ValueError("review-partition-incomplete")
        groups = {item.group: item for item in self.partitions}
        survivors = [item.existing_work_id for item in self.partitions if item.existing_work_id is not None]
        if (
            len(groups) != len(self.partitions)
            or len(survivors) != len(set(survivors))
            or not set(survivors) <= work_ids
        ):
            raise ValueError("review-survivor-invalid")
        aliases = {item.work_id: item for item in self.aliases}
        if (
            len(aliases) != len(self.aliases)
            or set(aliases) & set(survivors)
            or not work_ids - set(survivors) <= set(aliases)
        ):
            raise ValueError("review-alias-plan-incomplete")
        for item in self.aliases:
            if item.target_group not in groups or item.work_id == groups[item.target_group].existing_work_id:
                raise ValueError("review-alias-plan-invalid")
            source = next((work for work in self.works if work.work_id == item.work_id), None)
            if source is not None and item.revision_id != source.revision_id:
                raise ValueError("review-alias-predecessor-invalid")
        if self.action == "merge":
            if len(self.works) + len(self.unassigned_assertion_revision_ids) < 2 or len(self.partitions) != 1:
                raise ValueError("review-merge-invalid")
        elif self.action == "split":
            if len(self.works) != 1 or self.unassigned_assertion_revision_ids or len(self.partitions) < 2:
                raise ValueError("review-split-invalid")
        elif len(self.works) > 1 or not self.unassigned_assertion_revision_ids or len(self.partitions) != 1:
            raise ValueError("review-assignment-invalid")
        return self

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


class ReviewCommand(DraftValue):
    command_id: Identity
    plan: ReviewPlan
    expected_preview_sha256: Digest


class ReviewOutcome(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    decision_id: Identity
    decision_revision_id: Identity
    command_id: Identity
    plan_sha256: Digest
    work_states: Annotated[tuple[WorkState, ...], Field(min_length=1, max_length=288)]
    dependency_run_ids: Annotated[tuple[Identity, ...], Field(max_length=288)]


class ReviewSource(DraftValue):
    assertion_revision_id: Identity
    assertion: SourceAssertion = Field(repr=False)


class ReviewContext(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    algorithm: str = ALGORITHM
    feature_version: str = FEATURE_VERSION
    configuration_sha256: Digest = DEFAULT_CONFIG.fingerprint
    works: Annotated[tuple[WorkState, ...], Field(max_length=32)]
    unassigned_assertion_revision_ids: Members
    inbound_aliases: Annotated[tuple[WorkState, ...], Field(max_length=256)]
    sources: Annotated[tuple[ReviewSource, ...], Field(min_length=1, max_length=512)] = Field(repr=False)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def evidence_sha256(self) -> str:
        return self.fingerprint


class ReviewPreview(DraftValue):
    command_id: Identity
    plan_sha256: Digest
    evidence_sha256: Digest
    preview_sha256: Digest
    affected_output_revision_ids: Annotated[tuple[Identity, ...], Field(max_length=20000)]
    unknown_impact_revision_ids: Annotated[tuple[Identity, ...], Field(max_length=20000)]
