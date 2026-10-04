"""Run only the two approved desktop bundles with the installed pinned tools."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "tools"))
from desktop_app_check import tool_environment  # noqa: E402

app = (repo / "apps/desktop").resolve(strict=True)
for name in ("dist", "product-dist"):
    target = app / name
    if target.is_symlink() or target.is_junction() or target.resolve(strict=False) != target:
        raise ValueError(f"refusing redirected generated output: {name}")
    if target.parent != app or not target.resolve(strict=False).is_relative_to(app):
        raise ValueError(f"output escaped the intended desktop directory: {name}")
environment, corepack, _ = tool_environment(repo)
candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
print(
    json.dumps({"producerCommit": candidate, "outputs": ["apps/desktop/dist", "apps/desktop/product-dist"]}), flush=True
)
for command in (
    [str(corepack.parent / "node.exe"), "--version"],
    [str(corepack), "pnpm", "--dir", "apps/desktop", "run", "build"],
):
    result = subprocess.run(command, cwd=repo, env=environment, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip() != candidate:
    raise ValueError("HEAD changed during pinned build")
