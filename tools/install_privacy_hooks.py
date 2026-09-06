"""Prepare pinned local privacy hooks; Git configuration activation is separate."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
import sys
import sysconfig
import uuid
import zipfile
from pathlib import Path

from prospective_privacy import YAML_SOURCE_NAMES, reviewed_artifacts

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
            "--config", str(base / "gitleaks.toml"), *REVIEW_ARGUMENTS, *PARSER_ARGUMENTS, *extra]
runpy.run_path(str(base / "guard.py"), run_name="__main__")
"""


def yaml_parser_archive() -> bytes:
    """Snapshot only the existing locked dependency's pure Python sources, never live imports."""
    package = Path(sysconfig.get_path("purelib")) / "yaml"
    package.relative_to(Path(sys.prefix))
    if package.is_symlink() or package.resolve() != package.absolute():
        raise ValueError("Redirected YAML dependency")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in YAML_SOURCE_NAMES:
            source = package / name
            if source.is_symlink() or not source.is_file():
                raise ValueError("Incomplete YAML dependency")
            raw = source.read_bytes()
            if name == "__init__.py" and b"__version__ = '6.0.3'" not in raw:
                raise ValueError("The repository-locked YAML dependency is required")
            info = zipfile.ZipInfo("yaml/" + source.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return output.getvalue()


def prepare(repo: Path, scanner: Path, review: Path | None = None, review_sha256: str | None = None) -> Path:
    repo, scanner = repo.resolve(), scanner.resolve()
    policy_raw = (repo / ".privacy-baseline.json").read_bytes()
    policy = json.loads(policy_raw)
    if hashlib.sha256(scanner.read_bytes()).hexdigest() != policy["scannerSha256"]:
        raise ValueError("Pinned scanner is required")
    runtime = Path(sys.executable).resolve()
    if not runtime.is_file():
        raise ValueError("Install the repository Python environment first")
    review_raw = None
    if (review is None) != (review_sha256 is None):
        raise ValueError("Review file and independently supplied digest are both required")
    if review is not None:
        if review.is_symlink() or review.resolve() != review.absolute():
            raise ValueError("Redirected artifact review rejected")
        review.resolve().relative_to(repo / ".local")
        review_raw = review.read_bytes()
        if hashlib.sha256(review_raw).hexdigest() != review_sha256:
            raise ValueError("Artifact review differs from independently supplied digest")
    target = repo / ".local" / ("push-guard-" + uuid.uuid4().hex)
    if target.parent.is_symlink() or target.parent.resolve() != target.parent:
        raise ValueError("Redirected local state rejected")
    target.mkdir(parents=False, exist_ok=False)
    outputs = {
        "guard.py": (repo / "tools/prospective_privacy.py").read_bytes(),
        "policy.json": policy_raw,
        "gitleaks.toml": CONFIG,
    }
    if review_raw is not None:
        # Validate against the same fixed scanner config used by this snapshot.
        with (target / "validation-config.toml").open("xb") as stream:
            stream.write(CONFIG)
        reviewed_artifacts(json.loads(review_raw), policy, target / "validation-config.toml")
        outputs["reviewed-artifacts.json"] = review_raw
        preservation = json.loads(review_raw).get("preservation")
        if preservation is not None:
            if hashlib.sha256(outputs["guard.py"]).hexdigest() != preservation["workerSha256"]:
                raise ValueError("Parser worker differs from independently reviewed preservation inputs")
            parser = yaml_parser_archive()
            if hashlib.sha256(parser).hexdigest() != preservation["parserSha256"]:
                raise ValueError("YAML parser differs from independently reviewed preservation inputs")
            outputs["yaml-parser.zip"] = parser
    pins = {path: hashlib.sha256(raw).hexdigest() for path, raw in outputs.items()}
    source = LAUNCHER.replace("PINS", repr(pins)).replace("SCANNER_HASH", repr(policy["scannerSha256"]))
    source = source.replace("SCANNER", repr(str(scanner)))
    source = source.replace("REPO", repr(str(repo)))
    review_args = ["--review-registry", str(target / "reviewed-artifacts.json")] if review_raw is not None else []
    source = source.replace("REVIEW_ARGUMENTS", repr(review_args))
    parser_args = ["--yaml-parser", str(target / "yaml-parser.zip")] if "yaml-parser.zip" in outputs else []
    source = source.replace("PARSER_ARGUMENTS", repr(parser_args))
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
    parser.add_argument("--review", type=Path)
    parser.add_argument("--review-sha256")
    args = parser.parse_args()
    try:
        result = prepare(args.repo, args.scanner, args.review, args.review_sha256)
        print(json.dumps({"status": "PREPARED_NOT_ACTIVE", "hooksPath": str(result)}))
        return 0
    except ValueError, OSError, KeyError:
        print("Hook preparation failed. No Git configuration changed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
