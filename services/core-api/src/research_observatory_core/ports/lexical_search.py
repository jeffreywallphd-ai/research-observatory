"""Renderer-independent search commands and existing-worker activity ports.

Request protocols describe validated values; they do not grant authority. Core
resolves Native/session/actor/rights at the concrete adapter on every command.
"""

from collections.abc import Callable
from typing import Protocol

from ..search.delivery_values import SearchExplanation, SearchJob, SearchPage
from ..search.run_values import SearchFilters, SearchRequestInput
from .workflow_executor import WorkflowJobClaim


class SearchProject(Protocol):
    @property
    def root(self) -> str: ...

    @property
    def project_id(self) -> str: ...


class SearchCommand(SearchProject, Protocol):
    @property
    def command_id(self) -> str: ...

    @property
    def query(self) -> str: ...

    @property
    def filters(self) -> SearchFilters: ...


class SearchJobAddress(SearchProject, Protocol):
    @property
    def job_id(self) -> str: ...


class SearchPageAddress(SearchJobAddress, Protocol):
    @property
    def after(self) -> str | None: ...

    @property
    def limit(self) -> int: ...


class SearchExplanationAddress(SearchJobAddress, Protocol):
    @property
    def item_id(self) -> str: ...


class SearchRegistration(SearchProject, Protocol):
    @property
    def session_id(self) -> str: ...

    def stopped(self) -> bool: ...


class LexicalSearchPort(Protocol):
    def submit(self, command: SearchCommand, *, trace_id: str) -> SearchJob: ...

    def status(self, command: SearchJobAddress, *, trace_id: str) -> SearchJob: ...

    def page(self, command: SearchPageAddress, *, trace_id: str) -> SearchPage: ...

    def explain(self, command: SearchExplanationAddress, *, trace_id: str) -> SearchExplanation: ...

    def cancel(self, command: SearchJobAddress, *, trace_id: str) -> SearchJob: ...

    def run_activity(
        self,
        registration: SearchRegistration,
        context: object,
        claim: WorkflowJobClaim,
        *,
        admission: object,
        trace_id: str,
    ) -> object: ...


class SearchActivityRepository(Protocol):
    def claim_input(self, claim: WorkflowJobClaim) -> SearchRequestInput: ...

    def prepare(self, *, cancelled: Callable[[], bool]) -> None: ...

    def run_query(
        self,
        claim: WorkflowJobClaim,
        inputs: SearchRequestInput,
        *,
        before_publish: Callable[[], None],
        cancelled: Callable[[], bool],
    ) -> object: ...
