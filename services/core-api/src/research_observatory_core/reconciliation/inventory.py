"""Owner-authenticated, bounded source pages for durable reconciliation."""

from typing import Annotated, Self

from pydantic import Field, computed_field, model_validator

from ..ingestion.import_drafts import DraftValue, Identity
from .contracts import ReconciliationProblem, SourceAddress


def page_bounds(after: int, limit: int, total: int) -> None:
    if type(after) is not int or type(limit) is not int or not 0 <= after <= total or not 1 <= limit <= 100:
        raise ReconciliationProblem("reconciliation-source-page-invalid")


class SourcePage(DraftValue):
    job_id: Identity
    output_revision_id: Identity
    record_count: Annotated[int, Field(strict=True, ge=0, le=200000)]
    selected_count: Annotated[int, Field(strict=True, ge=0, le=200000)]
    after: Annotated[int, Field(strict=True, ge=0, le=200000)]
    scanned_through: Annotated[int, Field(strict=True, ge=0, le=200000)]
    addresses: Annotated[tuple[SourceAddress, ...], Field(max_length=100)]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def complete(self) -> bool:
        return self.scanned_through == self.record_count

    @model_validator(mode="after")
    def coherent_page(self) -> Self:
        if (
            not self.after <= self.scanned_through <= self.record_count
            or self.scanned_through - self.after > 100
            or (self.after < self.record_count and self.scanned_through == self.after)
            or self.selected_count > self.record_count
            or len(self.addresses) > min(self.selected_count, self.scanned_through - self.after)
            or len({item.ordinal for item in self.addresses}) != len(self.addresses)
            or any(item.revision_id != self.output_revision_id for item in self.addresses)
            or any(
                not self.after < item.ordinal + (item.kind == "connector-record") <= self.scanned_through
                for item in self.addresses
            )
        ):
            raise ValueError("reconciliation-source-page-invalid")
        return self
