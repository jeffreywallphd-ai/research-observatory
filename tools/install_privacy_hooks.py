"""Prepare pinned local privacy hooks; Git configuration activation is separate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
import uuid
from pathlib import Path

CONFIG = b'title = "Prospective credential checks"\n[extend]\nuseDefault = true\n'
LAUNCHER = """import hashlib, json, runpy, sys
from pathlib import Path
base = Path(__file__).resolve().parent
pins = PINS
for relative, expected in pins.items():
    path = base / relative
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit("Privacy hook inputs changed; reviewed reinstall required.")
if Path(SCANNER).is_symlink() or hashlib.sha256(Path(SCANNER).read_bytes()).hexdigest() != SCANNER_HASH:
    raise SystemExit("Redirected scanner rejected.")
mode = sys.argv[1]
extra = ["--remote-url", sys.argv[2]] if mode == "push" else []
if mode == "message":
    extra = ["--message", sys.argv[2]]
sys.argv = [str(base / "guard.py"), mode, "--repo", REPO,
            "--policy", str(base / "policy.json"), "--scanner", SCANNER,
            "--config", str(base / "gitleaks.toml"), *extra]
runpy.run_path(str(base / "guard.py"), run_name="__main__")
"""


def prepare(repo: Path, scanner: Path) -> Path:
    repo, scanner = repo.resolve(), scanner.resolve()
    policy_raw = (repo / ".privacy-baseline.json").read_bytes()
    policy = json.loads(policy_raw)
    if hashlib.sha256(scanner.read_bytes()).hexdigest() != policy["scannerSha256"]:
        raise ValueError("Pinned scanner is required")
    runtime = Path(sys.executable).resolve()
    if not runtime.is_file():
        raise ValueError("Install the repository Python environment first")
    target = repo / ".local" / ("push-guard-" + uuid.uuid4().hex)
    if target.parent.is_symlink() or target.parent.resolve() != target.parent:
        raise ValueError("Redirected local state rejected")
    target.mkdir(parents=False, exist_ok=False)
    outputs = {
        "guard.py": (repo / "tools/prospective_privacy.py").read_bytes(),
        "policy.json": policy_raw,
        "gitleaks.toml": CONFIG,
    }
    pins = {path: hashlib.sha256(raw).hexdigest() for path, raw in outputs.items()}
    source = LAUNCHER.replace("PINS", repr(pins)).replace("SCANNER_HASH", repr(policy["scannerSha256"]))
    source = source.replace("SCANNER", repr(str(scanner)))
    source = source.replace("REPO", repr(str(repo)))
    outputs["launcher.py"] = source.encode()
    python_arg = shlex.quote(runtime.as_posix())
    launcher_arg = shlex.quote((target / "launcher.py").as_posix())
    for name, mode, extra in (
        ("pre-commit", "staged", ""),
        ("commit-msg", "message", ' "$1"'),
        ("pre-push", "push", ' "$2"'),
    ):
        outputs[name] = f"#!/bin/sh\nexec {python_arg} -I -S {launcher_arg} {mode}{extra}\n".encode()
    for name, raw in outputs.items():
        with (target / name).open("xb") as stream:
            stream.write(raw)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--scanner", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.repo, args.scanner)
        print(json.dumps({"status": "PREPARED_NOT_ACTIVE", "hooksPath": str(result)}))
        return 0
    except ValueError, OSError, KeyError:
        print("Hook preparation failed. No Git configuration changed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
