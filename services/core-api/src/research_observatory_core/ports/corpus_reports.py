"""Protected immutable corpus report snapshot and exact bounded drill port."""

from __future__ import annotations

from typing import Protocol

from ..corpus_report_model import CorpusReportDrillPage, CorpusReportFilter, CorpusReportSnapshot
from .corpus import CorpusActor


class CorpusReportRepository(Protocol):
    def create(
        self,
        *,
        command_id: str,
        command_sha256: str,
        actor: CorpusActor,
    ) -> CorpusReportSnapshot: ...

    def summary(self, snapshot_id: str, *, actor: CorpusActor) -> CorpusReportSnapshot:
        """Inspect a sealed snapshot only under current protected authority."""
        ...

    def page(
        self,
        snapshot_id: str,
        *,
        filter: CorpusReportFilter,
        after: str | None,
        limit: int,
        actor: CorpusActor,
    ) -> CorpusReportDrillPage:
        """Return a stable item-ID ordered page bound to snapshot and filter."""
        ...


__all__ = ["CorpusReportRepository"]
