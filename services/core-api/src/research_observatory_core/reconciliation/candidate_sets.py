"""Immutable candidate evidence; scores authorize human inspection, never merging."""

import hashlib
import json
from bisect import bisect_left
from dataclasses import asdict
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from .candidates import DEFAULT_CONFIG, FIELD_NAMES, CandidatePair
from .contracts import CanonicalWorkReference
from .identifiers import NORMALIZER_VERSION

type Score = Annotated[int, Field(strict=True, ge=0, le=10000)]
type CandidateFlag = Literal["competing-source-fields", "year-disagreement", "conflicting-identifiers"]


def content_digest(value: DraftValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value.model_dump(mode="json", by_alias=True, exclude_computed_fields=True),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


class CandidateFeature(DraftValue):
    name: Literal["title", "authors", "year", "venue", "pages", "abstract", "identifiers"]
    state: Literal["available", "not-reported", "disputed"]
    score: Score | None
    weight: Annotated[int, Field(strict=True, ge=1, le=10000)]
    conflict: bool

    @model_validator(mode="after")
    def consistent_state(self) -> Self:
        if (
            (self.state == "available" and self.score is None)
            or (self.state == "not-reported" and (self.score is not None or self.conflict))
            or (self.state == "disputed" and not self.conflict)
        ):
            raise ValueError("duplicate-feature-state-invalid")
        if self.name != "identifiers" and self.conflict != (
            self.state == "disputed" or (self.score is not None and self.score < 10000)
        ):
            raise ValueError("duplicate-feature-conflict-invalid")
        return self


class CandidateExplanation(DraftValue):
    left: Identity
    right: Identity
    left_revision: Identity
    right_revision: Identity
    left_fingerprint: Digest
    right_fingerprint: Digest
    score: Score
    features: Annotated[tuple[CandidateFeature, ...], Field(min_length=7, max_length=7)]
    flags: Annotated[tuple[CandidateFlag, ...], Field(max_length=3)]
    configuration_fingerprint: Digest
    algorithm: Literal["scholarly-duplicate-ranking/1.0.0"]
    feature_version: Literal["scholarly-duplicate-features/1.0.0"]
    identifier_normalizer: str
    disposition: Literal["human-review-required"]

    @model_validator(mode="after")
    def exact_explanation(self) -> Self:
        if (
            self.left >= self.right
            or self.configuration_fingerprint != DEFAULT_CONFIG.fingerprint
            or self.identifier_normalizer != NORMALIZER_VERSION
            or tuple(item.name for item in self.features) != (*FIELD_NAMES, "identifiers")
            or tuple(item.weight for item in self.features) != (7000, 1500, 800, 400, 200, 100, 2000)
        ):
            raise ValueError("duplicate-explanation-authority-invalid")
        denominator = sum(item.weight for item in self.features if item.score is not None)
        score = (
            sum(item.score * item.weight for item in self.features if item.score is not None) // denominator
            if denominator
            else 0
        )
        flags = set()
        if any(item.state == "disputed" for item in self.features[:-1]):
            flags.add("competing-source-fields")
        if self.features[2].score == 0:
            flags.add("year-disagreement")
        if self.features[-1].conflict:
            flags.add("conflicting-identifiers")
        if self.score != score or self.flags != tuple(sorted(flags)):
            raise ValueError("duplicate-explanation-score-invalid")
        return self

    @classmethod
    def from_kernel(cls, value: CandidatePair) -> Self:
        return cls.model_validate(asdict(value))


class CandidateMember(DraftValue):
    assertion_revision_id: Identity
    source_revision_id: Identity
    input_sha256: Digest
    canonical_work: CanonicalWorkReference | None


class CandidateSetContent(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    project_id: ProjectIdentity
    request_id: Identity
    request_sha256: Digest
    inventory_sha256: Digest
    members: Annotated[tuple[CandidateMember, ...], Field(max_length=10000)]
    compared_pairs: Annotated[int, Field(strict=True, ge=0, le=250000)]
    pair_sha256: Annotated[tuple[Digest, ...], Field(max_length=20000)]
    algorithm: Literal["scholarly-duplicate-ranking/1.0.0"] = "scholarly-duplicate-ranking/1.0.0"
    feature_version: Literal["scholarly-duplicate-features/1.0.0"] = "scholarly-duplicate-features/1.0.0"
    configuration_sha256: Digest = DEFAULT_CONFIG.fingerprint
    identifier_normalizer: str = NORMALIZER_VERSION

    @model_validator(mode="after")
    def exact_membership(self) -> Self:
        if (
            tuple(item.assertion_revision_id for item in self.members)
            != tuple(sorted({item.assertion_revision_id for item in self.members}))
            or len(self.pair_sha256) != len(set(self.pair_sha256))
            or not len(self.pair_sha256) <= self.compared_pairs <= len(self.members) * (len(self.members) - 1) // 2
            or self.configuration_sha256 != DEFAULT_CONFIG.fingerprint
            or self.identifier_normalizer != NORMALIZER_VERSION
        ):
            raise ValueError("duplicate-set-membership-invalid")
        heads: dict[str, str] = {}
        for member in self.members:
            work = member.canonical_work
            if work is not None and heads.setdefault(work.work_id, work.revision_id) != work.revision_id:
                raise ValueError("duplicate-set-work-head-invalid")
        return self

    def validate_pair(self, ordinal: int, pair: CandidateExplanation) -> None:
        pair = CandidateExplanation.model_validate(pair)
        if type(ordinal) is not int or not 0 <= ordinal < len(self.pair_sha256):
            raise ValueError("duplicate-set-pair-ordinal-invalid")
        for key, revision, digest in (
            (pair.left, pair.left_revision, pair.left_fingerprint),
            (pair.right, pair.right_revision, pair.right_fingerprint),
        ):
            index = bisect_left(self.members, key, key=lambda item: item.assertion_revision_id)
            member = (
                self.members[index]
                if index < len(self.members) and self.members[index].assertion_revision_id == key
                else None
            )
            if member is None or (member.source_revision_id, member.input_sha256) != (revision, digest):
                raise ValueError("duplicate-set-pair-member-invalid")
        if content_digest(pair) != self.pair_sha256[ordinal]:
            raise ValueError("duplicate-set-pair-digest-invalid")
