"""Compact mechanical facts for one reviewed draft, never canonical identity.

Values and candidate keys stay in the protected project. Matching bytes/DOIs are
review candidates only; this module does not merge, exclude, commit or export.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from .import_drafts import Digest, DraftValue, ImportRights, RecordDecision, review_record
from .reference_imports import ImportRecord, normalize_import_field

SUMMARY_ALGORITHM = "draft-summary/1"
SUMMARY_ACTIVITY = "local-import-draft-summary"
COVERAGE_FIELDS = ("title", "doi", "year", "author", "container")
type Count = Annotated[int, Field(ge=0, le=200000)]


class SummaryRow(DraftValue):
    ordinal: Annotated[int, Field(ge=1, le=200000)]
    record_key: Digest
    record_kind: Literal["record", "header", "directive"]
    parse_status: Literal["parsed", "malformed"]
    included: bool
    warning_count: Annotated[int, Field(ge=0, le=64)]
    coverage_mask: Annotated[int, Field(ge=0, le=31)]
    raw_key: Digest | None
    doi_key: Digest | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.included and (self.record_kind != "record" or self.parse_status != "parsed"):
            raise ValueError("summary-record-not-importable")
        if self.included != (self.raw_key is not None):
            raise ValueError("summary-raw-key-mismatch")
        if not self.included and (self.coverage_mask or self.doi_key is not None):
            raise ValueError("summary-excluded-coverage")
        if bool(self.coverage_mask & 2) != (self.doi_key is not None):
            raise ValueError("summary-doi-key-mismatch")
        return self


class SummaryCoverage(DraftValue):
    title: Count
    doi: Count
    year: Count
    author: Count
    container: Count


class SummaryCounts(DraftValue):
    source_rows: Count
    record_rows: Count
    context_rows: Count
    malformed_rows: Count
    included_records: Count
    excluded_records: Count
    warning_rows: Count
    warning_count: Annotated[int, Field(ge=0, le=12800000)]
    coverage: SummaryCoverage
    raw_duplicate_groups: Count
    doi_duplicate_groups: Count
    candidate_records: Count

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.record_rows + self.context_rows != self.source_rows:
            raise ValueError("summary-source-count-mismatch")
        if self.included_records + self.excluded_records != self.record_rows:
            raise ValueError("summary-selection-count-mismatch")
        if self.malformed_rows > self.source_rows - self.included_records or self.warning_rows > self.source_rows:
            raise ValueError("summary-status-count-mismatch")
        if not self.warning_rows <= self.warning_count <= 64 * self.warning_rows:
            raise ValueError("summary-warning-count-mismatch")
        if any(value > self.included_records for value in self.coverage.model_dump().values()):
            raise ValueError("summary-coverage-count-mismatch")
        if self.candidate_records > self.included_records or self.candidate_records == 1:
            raise ValueError("summary-candidate-count-mismatch")
        groups = self.raw_duplicate_groups + self.doi_duplicate_groups
        if (
            bool(groups) != bool(self.candidate_records)
            or max(self.raw_duplicate_groups, self.doi_duplicate_groups) * 2 > self.candidate_records
        ):
            raise ValueError("summary-group-count-mismatch")
        return self


class SummaryResult(DraftValue):
    counts: SummaryCounts
    rows_sha256: Digest

    @property
    def sha256(self) -> str:
        payload = [SUMMARY_ALGORITHM, self.model_dump(mode="json", by_alias=True)]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def summary_rows_sha256(rows: Iterable[SummaryRow]) -> str:
    digest = hashlib.sha256(b'["draft-summary-rows/1",[')
    for index, row in enumerate(rows):
        if row.ordinal != index + 1:
            raise ValueError("summary-row-order-mismatch")
        if index:
            digest.update(b",")
        digest.update(row.model_dump_json(by_alias=True).encode("ascii"))
    digest.update(b"]]")
    return digest.hexdigest()


def summary_receipt_fingerprint(
    *,
    project_id: str,
    preview_id: str,
    job_id: str,
    summary_attempt_id: str,
    parse_attempt_id: str,
    draft_revision: int,
    source_sha256: str,
    manifest_sha256: str,
    result: SummaryResult,
) -> str:
    binding = [
        SUMMARY_ALGORITHM,
        project_id,
        preview_id,
        job_id,
        summary_attempt_id,
        parse_attempt_id,
        draft_revision,
        source_sha256,
        manifest_sha256,
        result.sha256,
    ]
    return "sha256:" + hashlib.sha256(json.dumps(binding, separators=(",", ":")).encode("ascii")).hexdigest()


def summarize_record(
    record: ImportRecord, decision: RecordDecision, warnings: tuple[str, ...], defaults: ImportRights
) -> SummaryRow:
    defaults = ImportRights.model_validate(defaults)
    decision = RecordDecision.model_validate(decision)
    effective_rights = decision.rights or defaults
    if any(not rights.permits(action) for rights in (defaults, effective_rights) for action in ("store", "inspect")):
        raise ValueError("summary-rights-denied")
    if decision.ordinal != record.ordinal or decision.record_key != record.record_key:
        raise ValueError("summary-record-mismatch")
    review_record(record, included=decision.included, fields=decision.fields, rights=decision.rights)
    coverage = 0
    doi_key = None
    if decision.included:
        for index, name in enumerate(COVERAGE_FIELDS):
            values = {
                candidate.value
                for field in decision.fields
                if field.name == name
                if (candidate := normalize_import_field(name, field.value, 0, set())) is not None
            }
            if values and (name == "author" or len(values) == 1):
                coverage |= 1 << index
                if name == "doi":
                    doi_key = hashlib.sha256(next(iter(values)).encode("utf-8")).hexdigest()
    return SummaryRow(
        ordinal=record.ordinal,
        record_key=record.record_key,
        record_kind=cast(Literal["record", "header", "directive"], record.kind),
        parse_status=cast(Literal["parsed", "malformed"], record.status),
        included=decision.included,
        warning_count=len(set(warnings)),
        coverage_mask=coverage,
        raw_key=record.raw_sha256 if decision.included else None,
        doi_key=doi_key,
    )
