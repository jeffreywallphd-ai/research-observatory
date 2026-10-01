"""Build a disposable, independently packaged Windows LPAC probe image."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

IMAGE_NAME = "research-observatory-plugin-probe-x86_64-pc-windows-msvc"
REPO = Path(__file__).resolve().parents[1]


def build(output: Path, report: Path) -> None:
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("LPAC probe build requires Windows x64")
    output = output.resolve()
    report = report.resolve()
    if output.exists() or report.exists():
        raise RuntimeError("LPAC probe output and report must be new paths")
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    target = output.parent / "cargo-target"
    command = [
        "cargo",
        "build",
        "--release",
        "--locked",
        "--offline",
        "--package",
        "research-observatory-lpac-probe",
        "--target-dir",
        str(target),
    ]
    subprocess.run(command, cwd=REPO, check=True, capture_output=True, timeout=180)
    image_relative = f"{IMAGE_NAME}/{IMAGE_NAME}.exe"
    image = output / image_relative
    image.parent.mkdir(parents=True)
    shutil.copy2(target / "release" / f"{IMAGE_NAME}.exe", image)
    if not (output / image_relative).is_file():
        raise RuntimeError("LPAC probe image was not built")
    files = []
    total = 0
    for path in sorted(output.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise RuntimeError("LPAC probe output contains a redirect")
        if not path.is_file():
            continue
        data = path.read_bytes()
        total += len(data)
        if total > 134_217_728:
            raise RuntimeError("LPAC probe output exceeds 128 MiB")
        files.append({"path": path.relative_to(output).as_posix(), "sha256": hashlib.sha256(data).hexdigest()})
    document = {
        "schemaVersion": "1.0",
        "documentType": "disposable-lpac-probe-package",
        "imagePath": image_relative,
        "files": files,
    }
    report.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    build(arguments.output, arguments.report)


if __name__ == "__main__":
    main()
