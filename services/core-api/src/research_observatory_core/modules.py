"""Explicit module and capability registration for the modular monolith."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    module_id: str
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.module_id):
            raise ValueError("module id must be a canonical dotted identifier")
        if not self.capabilities:
            raise ValueError("module must declare at least one capability")
        if tuple(sorted(set(self.capabilities))) != self.capabilities:
            raise ValueError("module capabilities must be unique and sorted")
        if any(not _IDENTIFIER.fullmatch(capability) for capability in self.capabilities):
            raise ValueError("capabilities must be canonical dotted identifiers")


class ModuleRegistry:
    def __init__(self, definitions: tuple[ModuleDefinition, ...]) -> None:
        if not definitions:
            raise ValueError("module registry cannot be empty")
        module_ids = tuple(definition.module_id for definition in definitions)
        if len(set(module_ids)) != len(module_ids):
            raise ValueError("duplicate module id")
        if tuple(sorted(module_ids)) != module_ids:
            raise ValueError("modules must be registered in canonical order")
        capabilities = tuple(capability for definition in definitions for capability in definition.capabilities)
        if len(set(capabilities)) != len(capabilities):
            raise ValueError("capability ownership must be unique")
        self._definitions = definitions
        self._capabilities = tuple(sorted(capabilities))

    @property
    def definitions(self) -> tuple[ModuleDefinition, ...]:
        return self._definitions

    @property
    def capabilities(self) -> tuple[str, ...]:
        return self._capabilities


def default_module_registry() -> ModuleRegistry:
    return ModuleRegistry(
        (
            ModuleDefinition(
                module_id="intent",
                capabilities=(
                    "intent.acceptance",
                    "intent.drafts",
                    "intent.impact-preview",
                    "intent.policy-evaluation",
                    "intent.read",
                ),
            ),
            ModuleDefinition(
                module_id="operations",
                capabilities=("operations.cancel", "operations.events", "operations.read"),
            ),
            ModuleDefinition(
                module_id="privacy",
                capabilities=("privacy.cache-cleanup", "privacy.policy"),
            ),
            ModuleDefinition(module_id="projects", capabilities=("projects.lifecycle",)),
            ModuleDefinition(module_id="runtime", capabilities=("runtime.contract", "runtime.status")),
        )
    )
