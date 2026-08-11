"""Frozen Windows sidecar entry point.

This thin wrapper keeps PyInstaller's source root explicit while delegating all
runtime behavior to the normal Core API composition root.
"""

from research_observatory_core.main import main

if __name__ == "__main__":
    raise SystemExit(main())
