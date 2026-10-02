"""Frozen Windows sidecar entry point.

This thin wrapper keeps PyInstaller's source root explicit while delegating all
runtime behavior to the normal Core API composition root.
"""

import json
import sys


def _check_worker_runtime() -> int:
    from workers.windows.runtime_inventory import RuntimeInventoryError, load_installed_worker_runtime

    try:
        load_installed_worker_runtime()
    except OSError, RuntimeInventoryError:
        print(json.dumps({"status": "worker-runtime-invalid"}))
        return 2
    print(json.dumps({"status": "worker-runtime-valid"}))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--check-worker-runtime"]:
        raise SystemExit(_check_worker_runtime())
    if sys.argv[1:] == ["--plugin-acl-guardian"]:
        from workers.windows.recovery_guardian import guardian_main

        raise SystemExit(guardian_main())
    from research_observatory_core.main import main

    raise SystemExit(main())
