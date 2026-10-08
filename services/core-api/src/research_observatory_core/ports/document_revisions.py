"""Core parse activity port; no database, path, key or original-byte authority."""

from collections.abc import Callable
from typing import Any, Protocol

from ..document_parse_workflow import DocumentParseInput
from ..document_revisions import RetainedParseResultReceipt
from ..parsing.requests import ParseRequest, ParseResult, ParseSuccess
from ..workflow_executor import WorkflowActivityContext, WorkflowAtomicCompletion
from .corpus import CorpusActor
from .workflow_executor import WorkflowJobClaim


class DocumentParsePipeline(Protocol):
    def stage(self, request: ParseRequest, *, actor: CorpusActor, cancelled: Callable[[], bool]) -> ParseResult: ...


class DocumentRevisionWorkerRepository(Protocol):
    actor: Callable[[], CorpusActor]

    def claim_input(self, claim: WorkflowJobClaim) -> DocumentParseInput: ...

    def parser_pipeline(
        self, context: WorkflowActivityContext, request: ParseRequest, runtime: Any
    ) -> DocumentParsePipeline: ...

    def retain(
        self, claim: WorkflowJobClaim, request: ParseRequest, result: ParseSuccess, *, stopped: Callable[[], bool]
    ) -> tuple[RetainedParseResultReceipt, WorkflowAtomicCompletion]: ...
