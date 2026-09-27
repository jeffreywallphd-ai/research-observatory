"""Versioned project-local feature snapshots; source authority stays with the resolver."""

from collections import defaultdict
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..ingestion.import_drafts import Digest, DraftValue, Identity
from .candidates import (
    ALGORITHM,
    DEFAULT_CONFIG,
    FEATURE_VERSION,
    FIELD_NAMES,
    CandidateRecord,
    PreparedRecord,
    PreparedValue,
    candidate_record_fingerprint,
    prepare_record,
)
from .contracts import ReconciliationProblem, SourceAssertion
from .identifiers import NORMALIZER_VERSION


def candidate_record(assertion_revision_id: str, source: SourceAssertion) -> CandidateRecord:
    """Keep competing assertions; normalize source field names, never their values."""
    fields: dict[str, list[str]] = defaultdict(list)
    names = {"author": "authors", "container": "venue"}
    for item in source.fields:
        name = names.get(item.name, item.name)
        if name in FIELD_NAMES:
            fields[name].append(item.observed)
    # An import's individual author cells form one author list, not competing
    # alternative lists. Connector candidate.authors already contains that list.
    if any(item.name == "author" for item in source.fields):
        fields["authors"] = ["; ".join(fields["authors"])]
    return CandidateRecord(
        assertion_revision_id,
        source.source_revision_id,
        tuple((name, tuple(values)) for name, values in sorted(fields.items())),
        source.identifiers,
    )


class CachedValue(DraftValue):
    text: Annotated[str, Field(max_length=65536)] = Field(repr=False)
    tokens: Annotated[tuple[str, ...], Field(max_length=4096)] = Field(repr=False)

    @model_validator(mode="after")
    def exact_tokens(self) -> Self:
        if self.tokens != tuple(sorted(set(self.text.split()))):
            raise ValueError("duplicate-feature-cache-tokens-invalid")
        return self


class CachedField(DraftValue):
    name: Literal["title", "authors", "year", "venue", "pages", "abstract"]
    values: Annotated[tuple[CachedValue, ...], Field(max_length=256)] = Field(repr=False)


class FeatureSnapshot(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    algorithm: str = ALGORITHM
    feature_version: str = FEATURE_VERSION
    identifier_normalizer: str = NORMALIZER_VERSION
    configuration_sha256: Digest = DEFAULT_CONFIG.fingerprint
    assertion_revision_id: Identity
    source_revision_id: Identity
    source_sha256: Digest
    input_sha256: Digest
    fields: Annotated[tuple[CachedField, ...], Field(max_length=6)] = Field(repr=False)
    identifiers: Annotated[tuple[tuple[str, str], ...], Field(max_length=128)] = Field(repr=False)

    @model_validator(mode="after")
    def bounded_canonical_features(self) -> Self:
        if (
            (self.algorithm, self.feature_version, self.identifier_normalizer, self.configuration_sha256)
            != (ALGORITHM, FEATURE_VERSION, NORMALIZER_VERSION, DEFAULT_CONFIG.fingerprint)
            or tuple(field.name for field in self.fields) != tuple(sorted({field.name for field in self.fields}))
            or any(
                tuple(value.text for value in field.values) != tuple(sorted({value.text for value in field.values}))
                for field in self.fields
            )
            or self.identifiers != tuple(sorted(set(self.identifiers)))
            or any(not 1 <= len(part) <= 65536 for item in self.identifiers for part in item)
            or len(self.model_dump_json(by_alias=True).encode()) > 2 * 1024 * 1024
        ):
            raise ValueError("duplicate-feature-cache-invalid")
        return self

    @classmethod
    def create(cls, revision_id: str, source: SourceAssertion) -> Self:
        prepared = prepare_record(candidate_record(revision_id, source))
        return cls(
            assertion_revision_id=revision_id,
            source_revision_id=source.source_revision_id,
            source_sha256=source.source_sha256,
            input_sha256=prepared.fingerprint,
            fields=tuple(
                CachedField.model_validate(
                    {
                        "name": name,
                        "values": tuple(
                            CachedValue(text=value.text, tokens=tuple(sorted(value.tokens))) for value in values
                        ),
                    }
                )
                for name, values in prepared.fields
            ),
            identifiers=tuple(sorted(prepared.identifiers)),
        )

    def restore(self, revision_id: str, source: SourceAssertion) -> PreparedRecord:
        if (self.assertion_revision_id, self.source_revision_id, self.source_sha256) != (
            revision_id,
            source.source_revision_id,
            source.source_sha256,
        ) or self.input_sha256 != candidate_record_fingerprint(candidate_record(revision_id, source)):
            raise ReconciliationProblem("duplicate-feature-cache-mismatch")
        return PreparedRecord(
            revision_id,
            source.source_revision_id,
            self.input_sha256,
            tuple(
                (field.name, tuple(PreparedValue(value.text, frozenset(value.tokens)) for value in field.values))
                for field in self.fields
            ),
            frozenset(self.identifiers),
        )
