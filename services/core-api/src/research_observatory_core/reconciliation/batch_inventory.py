"""Exhaust frozen accepted output pages before publishing any batch result."""

from collections.abc import Callable

from pydantic import ValidationError

from ..ports.reconciliation import ReconciliationSourceService
from ..ports.workflow_executor import WorkflowQueueRepository
from .batch import MAX_INVENTORY_JOBS, MAX_SCANNED_ROWS, InventorySnapshot
from .candidates import DEFAULT_CONFIG
from .contracts import ReconciliationProblem, SourceAddress
from .inventory import SourcePage


def collect_batch_sources(
    inventory: InventorySnapshot,
    *,
    root: str,
    queue: WorkflowQueueRepository,
    imports: ReconciliationSourceService,
    connectors: ReconciliationSourceService,
    checkpoint: Callable[[], None],
    page_size: int = 100,
) -> tuple[SourceAddress, ...]:
    """Owner services authorize content; this boundary proves stream completeness.

    Every queue page is authenticated against the same immutable snapshot. Empty
    owner pages still advance excluded ordinals; only a complete final page with
    the declared selected count can complete one accepted output. A later output
    cannot be substituted for the revision in that queue acceptance.
    """
    inventory = InventorySnapshot.model_validate(inventory)
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ReconciliationProblem("reconciliation-source-page-invalid")
    snapshot = inventory.queue_snapshot()
    bounds: dict[str, int] = {item.segment_key: item.sequence for item in inventory.boundaries}
    cursor = None
    seen_jobs: set[str] = set()
    sources: dict[str, SourceAddress] = {}
    scanned = 0
    while True:
        checkpoint()
        outputs = queue.accepted_page(snapshot, after=cursor, limit=page_size)
        if not outputs:
            return tuple(sources[key] for key in sorted(sources))
        if len(outputs) > page_size:
            raise ReconciliationProblem("reconciliation-inventory-page-invalid")
        for output in outputs:
            checkpoint()
            if (
                output.activity_type not in inventory.activity_types
                or len(output.outputs) != 1
                or output.job_id in seen_jobs
                or output.cursor.snapshot_sha256 != snapshot.fingerprint
                or (output.cursor.segment_key, output.cursor.sequence) != (output.segment_key, output.sequence)
                or not 0 < output.sequence <= bounds.get(output.segment_key, 0)
                or (
                    cursor is not None
                    and (output.segment_key, output.sequence) <= (cursor.segment_key, cursor.sequence)
                )
            ):
                raise ReconciliationProblem("reconciliation-inventory-page-invalid")
            seen_jobs.add(output.job_id)
            if len(seen_jobs) > MAX_INVENTORY_JOBS:
                raise ReconciliationProblem("reconciliation-inventory-job-limit")
            service = imports if output.activity_type == "local-import-commit" else connectors
            kind = "import-member" if output.activity_type == "local-import-commit" else "connector-record"
            through, selected = 0, 0
            counts: tuple[int, int] | None = None
            complete = False
            for raw in service.reconciliation_pages(root, output.job_id, limit=page_size, checkpoint=checkpoint):
                checkpoint()
                try:
                    page = SourcePage.model_validate(raw)
                except ValidationError:
                    raise ReconciliationProblem("reconciliation-inventory-source-invalid") from None
                if (
                    complete
                    or page.job_id != output.job_id
                    or page.output_revision_id != output.outputs[0].revision_id
                    or page.after != through
                    or (counts is not None and counts != (page.record_count, page.selected_count))
                    or any(address.kind != kind for address in page.addresses)
                ):
                    raise ReconciliationProblem("reconciliation-inventory-source-invalid")
                counts = page.record_count, page.selected_count
                selected += len(page.addresses)
                scanned += page.scanned_through - through
                through, complete = page.scanned_through, page.complete
                if scanned > MAX_SCANNED_ROWS:
                    raise ReconciliationProblem("reconciliation-inventory-row-limit")
                for address in page.addresses:
                    sources.setdefault(address.model_dump_json(by_alias=True), address)
                if len(sources) > DEFAULT_CONFIG.max_records:
                    raise ReconciliationProblem("duplicate-record-limit")
            if counts is None or not complete or selected != counts[1]:
                raise ReconciliationProblem("reconciliation-inventory-incomplete")
            cursor = output.cursor
