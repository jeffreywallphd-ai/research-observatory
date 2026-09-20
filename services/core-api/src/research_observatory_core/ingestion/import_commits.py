"""Bounded scientific import identities; never UUID minting or authorization.

The repository must supply every accepted row and recheck membership, current
rights, project and worker authority at commit. These pure hashes do not certify
any of those facts and do not mutate canonical or preview state.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from typing import Annotated, Self

from pydantic import Field, model_validator

from .import_drafts import (
    Digest,
    DraftAuthority,
    DraftValue,
    ProjectIdentity,
    RecordDecision,
    effective_draft_sha256,
)


class ImportIdentity(DraftValue):
    sha256: Digest
    effective_draft_sha256: Digest
    record_count: Annotated[int, Field(ge=0, le=200000)]
    selected_count: Annotated[int, Field(ge=0, le=200000)]

    @model_validator(mode="after")
    def coherent_counts(self) -> Self:
        if self.selected_count > self.record_count:
            raise ValueError("import-selection-count-mismatch")
        return self


class _SourceAssertion(DraftValue):
    project_id: ProjectIdentity
    source_sha256: Digest
    record_key: Digest


def source_assertion_key(project_id: str, source_sha256: str, record_key: str) -> str:
    """Project-local lookup key; stored Core UUIDv7 identity remains authoritative."""
    value = _SourceAssertion(project_id=project_id, source_sha256=source_sha256, record_key=record_key)
    return hashlib.sha256(
        json.dumps(
            ["local-source-assertion/1", value.project_id, value.source_sha256, value.record_key],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()


def import_identity(
    authority: DraftAuthority, decisions: Iterable[RecordDecision], *, expected_record_count: int
) -> ImportIdentity:
    """Hash one complete ordered stream without retaining the selection in memory.

    Serialization: [version, project, source, parser, [profile, revision],
    [ordered selected record keys], effective-draft digest]. Request/preview IDs
    are not scientific identity. Empty input is a valid identity, not proof of a
    completed parse or permission to commit an empty manifest.
    """
    authority = DraftAuthority.model_validate(authority)
    if type(expected_record_count) is not int or not 0 <= expected_record_count <= 200000:
        raise ValueError("import-record-count-limit")
    header = [
        "import-identity/1",
        authority.project_id,
        authority.source_sha256,
        authority.parser_version,
        [authority.mapping.profile_id, authority.mapping.revision],
    ]
    digest = hashlib.sha256(json.dumps(header, ensure_ascii=True, separators=(",", ":")).encode("ascii")[:-1])
    digest.update(b",[")
    count = selected = 0

    def ordered() -> Iterator[RecordDecision]:
        nonlocal count, selected
        for item in decisions:
            item = RecordDecision.model_validate(item)
            count += 1
            if count > expected_record_count or item.ordinal != count:
                raise ValueError("import-record-coverage-mismatch")
            if item.included:
                if selected:
                    digest.update(b",")
                digest.update(json.dumps(item.record_key).encode("ascii"))
                selected += 1
            yield item
        if count != expected_record_count:
            raise ValueError("import-record-coverage-mismatch")

    draft_digest = effective_draft_sha256(authority, ordered())
    digest.update(b"],")
    digest.update(json.dumps(draft_digest).encode("ascii"))
    digest.update(b"]")
    return ImportIdentity(
        sha256=digest.hexdigest(), effective_draft_sha256=draft_digest, record_count=count, selected_count=selected
    )
