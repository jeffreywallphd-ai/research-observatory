#!/usr/bin/env python3
"""Install the checksum-pinned Trivy scanner into checkout-local ignored state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tarfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

UrlOpener = Callable[[str], BinaryIO]


class InstallError(RuntimeError):
    """The scanner platform, download, checksum, archive, or version is invalid."""


def load_contract(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "security-toolchain.json").read_text(encoding="utf-8"))


def platform_key(system_name: str | None = None, machine_name: str | None = None) -> str:
    system_value = (system_name or platform.system()).lower()
    machine_value = (machine_name or platform.machine()).lower()
    systems = {"windows": "windows", "linux": "linux", "darwin": "macos"}
    architectures = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}
    if system_value not in systems or machine_value not in architectures:
        raise InstallError(f"unsupported Trivy platform: system={system_value}, machine={machine_value}")
    return f"{systems[system_value]}-{architectures[machine_value]}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scanner_version(executable: Path) -> str | None:
    try:
        result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    match = re.search(r"(?m)^Version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", result.stdout)
    return match.group(1) if result.returncode == 0 and match else None


def _safe_member_name(raw: str, executable_name: str) -> bool:
    path = PurePosixPath(raw.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and path.name == executable_name


def extract_executable(archive: Path, archive_type: str, executable_name: str, destination: Path) -> None:
    candidates: list[bytes] = []
    if archive_type == "zip":
        with zipfile.ZipFile(archive) as bundle:
            for zip_member in bundle.infolist():
                if not zip_member.is_dir() and _safe_member_name(zip_member.filename, executable_name):
                    candidates.append(bundle.read(zip_member))
    elif archive_type == "tar.gz":
        with tarfile.open(archive, "r:gz") as bundle:
            for tar_member in bundle.getmembers():
                if tar_member.isfile() and _safe_member_name(tar_member.name, executable_name):
                    extracted = bundle.extractfile(tar_member)
                    if extracted is not None:
                        candidates.append(extracted.read())
    else:
        raise InstallError(f"unsupported Trivy archive type: {archive_type}")
    if len(candidates) != 1:
        raise InstallError(f"expected exactly one safe {executable_name} in {archive.name}; found {len(candidates)}")
    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.write_bytes(candidates[0])
    if os.name != "nt":
        temporary.chmod(0o755)
    temporary.replace(destination)


def download(url: str, destination: Path, opener: UrlOpener = urllib.request.urlopen) -> None:
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with opener(url) as response, temporary.open("wb") as output:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                output.write(chunk)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def install(repo: Path, offline: bool = False, opener: UrlOpener = urllib.request.urlopen) -> Path:
    repo = repo.resolve()
    contract = load_contract(repo)
    if contract.get("schemaVersion") != "1.0" or contract.get("documentType") != "security-toolchain-contract":
        raise InstallError("security-toolchain.json contract identity is invalid")
    scanner = contract["scanner"]
    version = scanner["version"]
    key = platform_key()
    asset = scanner.get("assets", {}).get(key)
    if not isinstance(asset, dict):
        raise InstallError(f"security-toolchain.json has no asset for {key}")
    install_root = repo / ".local" / "toolchains" / "trivy" / version
    install_root.mkdir(parents=True, exist_ok=True)
    executable = install_root / asset["executable"]
    expected_executable_sha256 = asset["executableSha256"]
    if executable.exists() and sha256(executable) == expected_executable_sha256:
        installed = scanner_version(executable)
        if installed != version:
            raise InstallError(f"trusted Trivy bytes did not report pinned version {version}: {executable}")
        return executable

    downloads = repo / ".local" / "toolchains" / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / asset["file"]
    if archive.exists() and sha256(archive) != asset["sha256"]:
        raise InstallError(f"cached Trivy archive checksum mismatch: {archive}")
    if not archive.exists():
        if offline:
            raise InstallError(f"pinned Trivy archive is not cached for offline install: {archive}")
        url = f"{scanner['releaseBaseUrl'].rstrip('/')}/{asset['file']}"
        download(url, archive, opener=opener)
        actual = sha256(archive)
        if actual != asset["sha256"]:
            archive.unlink(missing_ok=True)
            raise InstallError(f"downloaded Trivy archive checksum mismatch: expected {asset['sha256']}, got {actual}")
    extract_executable(archive, asset["archive"], asset["executable"], executable)
    actual_executable_sha256 = sha256(executable)
    if actual_executable_sha256 != expected_executable_sha256:
        executable.unlink(missing_ok=True)
        raise InstallError(
            "extracted Trivy executable checksum mismatch: "
            f"expected {expected_executable_sha256}, got {actual_executable_sha256}"
        )
    installed = scanner_version(executable)
    if installed != version:
        raise InstallError(f"installed Trivy did not report pinned version {version}: {executable}")
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        executable = install(Path(args.repo), offline=args.offline)
    except (InstallError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Security scanner ready: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
