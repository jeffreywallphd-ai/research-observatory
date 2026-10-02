"""A source checkout never silently activates the installed LPAC adapter."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.plugin_runtime import (  # noqa: E402
    InstalledPluginRuntime,
    InstalledPluginRuntimeProblem,
)


class InstalledPluginRuntimeTests(unittest.TestCase):
    def test_source_process_fails_closed_even_if_worker_module_is_importable(self):
        runtime = InstalledPluginRuntime()
        with patch.object(sys, "frozen", False, create=True):
            self.assertFalse(runtime.available())
            with self.assertRaises(InstalledPluginRuntimeProblem):
                runtime.load()
            with self.assertRaises(InstalledPluginRuntimeProblem):
                runtime.run(object(), object(), {})


if __name__ == "__main__":
    unittest.main()
