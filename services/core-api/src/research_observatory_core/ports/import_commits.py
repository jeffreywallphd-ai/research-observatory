"""Portable commit execution boundary; no storage handles or paths."""

from collections.abc import Callable
from typing import Protocol

from ..ingestion.commit_workflow import CommitJobInput
from .import_previews import PreviewActor
from .workflow_executor import WorkflowJobClaim, WorkflowOutputReference


class ImportCommitRepository(Protocol):
    def begin_commit(self, inputs: CommitJobInput, *, claim: WorkflowJobClaim, actor: PreviewActor) -> None: ...

    def append_commit_page(
        self, inputs: CommitJobInput, *, after: int, claim: WorkflowJobClaim, actor: PreviewActor
    ) -> int: ...

    def publish_commit(
        self,
        inputs: CommitJobInput,
        *,
        claim: WorkflowJobClaim,
        actor: PreviewActor,
        now: Callable[[], str],
        poll: Callable[[], None] | None = None,
    ) -> WorkflowOutputReference: ...
