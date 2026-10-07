"""Extended filesystem spelling for already authenticated local owned paths.

This changes no location or permission and does not change global Windows
settings. Callers validate ownership/root identity before destructive operations.
"""

import os
from pathlib import Path


def extended_path(path: Path) -> Path:
    if os.name != "nt" or str(path).startswith("\\\\?\\"):
        return path
    if not path.is_absolute() or path.drive.startswith("\\\\") or any(part in {".", ".."} for part in path.parts):
        raise ValueError("worker-local-path-invalid")
    return Path("\\\\?\\" + str(path))
