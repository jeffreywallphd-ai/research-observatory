"""Encrypted plugin-job input and fenced publication port."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..connectors.plugin_dispatch import PluginStagedOutput
from ..connectors.plugin_manifest import PluginInvocationPlan
from ..connectors.plugin_workflow import PluginJobInput
from .workflow_executor import WorkflowJobClaim, WorkflowOutputReference


class PluginJobRepositoryProblem(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PluginPublishedPageView(Protocol):
    """The predecessor fields used by Core without coupling the port to storage."""

    @property
    def plan(self) -> PluginInvocationPlan: ...

    @property
    def continuation(self) -> str: ...

    @property
    def next_cursor(self) -> str | None: ...


class PluginJobStore(Protocol):
    def save_input(self, inputs: PluginJobInput, *, actor_id: str, now: str) -> None: ...

    def input(self, invocation_id: str) -> PluginJobInput: ...

    def result(self, inputs: PluginJobInput) -> PluginPublishedPageView | None: ...

    def publish(
        self,
        inputs: PluginJobInput,
        plan: PluginInvocationPlan,
        staged: PluginStagedOutput,
        claim: WorkflowJobClaim,
        *,
        actor_id: str,
        now: Callable[[], str],
        recheck_current: Callable[[], None],
        interrupted: Callable[[], bool],
    ) -> WorkflowOutputReference: ...
