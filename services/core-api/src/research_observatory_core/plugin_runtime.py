"""Release-installed, application-pinned Windows connector worker adapter.

No path or verification key is accepted from a plugin, project or renderer. A
source checkout stays closed even when a test worker happens to be present.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from .connectors.plugin_manifest import VerifiedPluginPackage


class InstalledPluginRuntimeProblem(ValueError):
    def __init__(self) -> None:
        super().__init__("plugin-runtime-unavailable")


class InstalledPluginRuntime:
    def load(self) -> object:
        if os.name != "nt" or getattr(sys, "frozen", False) is not True:
            raise InstalledPluginRuntimeProblem()
        try:
            from workers.windows.runtime_inventory import load_installed_worker_runtime

            return load_installed_worker_runtime()
        except Exception:
            raise InstalledPluginRuntimeProblem() from None

    def available(self) -> bool:
        try:
            self.load()
            return True
        except InstalledPluginRuntimeProblem:
            return False

    def run(self, runtime: object, package: object, package_files: dict[str, bytes], **kwargs: Any) -> object:
        if os.name != "nt" or getattr(sys, "frozen", False) is not True:
            raise InstalledPluginRuntimeProblem()
        try:
            from workers.windows.connector_launcher import run_connector
            from workers.windows.runtime_inventory import SignedWorkerRuntime

            if not isinstance(runtime, SignedWorkerRuntime) or not isinstance(package, VerifiedPluginPackage):
                raise ValueError
            return run_connector(runtime, package, package_files, **kwargs)
        except Exception:
            # Worker diagnostics are local evidence, never a renderer response.
            raise InstalledPluginRuntimeProblem() from None
