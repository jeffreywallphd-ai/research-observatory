"""Synthetic external-input adapter for retired-controller tests, never live authority.

The historical descriptors, schemas and Git hashes remain unchanged. Only the
expected digest operand for reading a non-authoritative local witness is replaced
in a test-only clone of the actual validator. This proves witness mechanics, not
the authenticity of any researcher's private historical witness.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import importlib
import inspect
import stat
import tempfile
import textwrap
import types
import unittest
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import patch

WITNESS_PATH = "artifacts/evidence/W1.A04.B00.json"
HISTORICAL_BOOTSTRAP_CANDIDATE = "214ac1aac53b4396ee29f7a935ddcac2a34618b6"
SYNTHETIC_WITNESS = (
    b'{"fixture":"synthetic-non-authoritative-trigger","historicalEvidence":false,'
    b'"taskId":"W1.A04.B00","commit":"214ac1aac53b4396ee29f7a935ddcac2a34618b6"}\n'
)
SYNTHETIC_SHA256 = hashlib.sha256(SYNTHETIC_WITNESS).hexdigest()
HISTORICAL_SHA256 = "4a9d944ff95972b449b617bc384306c7023e79d31d6b427e6b6f4678cd58b22c"
VALIDATORS = (
    ("gcrctl", "validate_trigger", "path", "TRIGGER_SHA256"),
    ("gcr2ctl", "validate_trigger", "path", "TRIGGER_SHA256"),
    ("gcr3ctl", "validate_trigger", "path", "TRIGGER_SHA256"),
    ("gcr4ctl", "validate_trigger", "path", "TRIGGER_SHA256"),
    ("gcr5ctl", "validate_witness", "path", "TRIGGER_SHA256"),
    ("gcr7ctl", "validate_witness", "path", "TRIGGER_SHA256"),
    ("recoveryctl", "require_supplement_workspace", "witness_path", "CONTROL_RECOVERY_TRIGGER_SHA256"),
    ("recoveryctl", "validate_b02_scope_lifecycle_backlog", "witness", "CONTROL_RECOVERY_TRIGGER_SHA256"),
)
BOOTSTRAP_VALIDATORS = (
    ("taskctl", "recovery_supplement_authority_errors"),
    ("recoveryctl", "validate_preappend_supplement_boundary"),
)


def require_temporary_root(repo: Path, source_repo: Path, *, allow_missing: bool = False) -> Path:
    """Check confinement and every resolved ancestor before any filesystem write."""
    root = repo.absolute()
    source = source_repo.resolve(strict=True)
    temporary = Path(tempfile.gettempdir()).resolve(strict=True)
    admitted = False
    for base in (temporary, source):
        if root.is_relative_to(base):
            relative = root.relative_to(base)
            admitted = admitted or bool(relative.parts and relative.parts[0].startswith("tmp"))
    if not admitted or root == source or root.resolve(strict=False) != root:
        raise AssertionError("A nonredirected owned temporary fixture root is required")
    if allow_missing and not root.exists():
        FixtureWitnesses.require_plain_directory(root.parent)
    else:
        FixtureWitnesses.require_plain_directory(root)
    return root


def adapted_validator(original: types.FunctionType, variable: str, constant: str) -> types.FunctionType:
    """Fail if the selected source is not exactly the reviewed digest comparison."""
    if (original.__module__, original.__name__, variable, constant) not in VALIDATORS:
        raise AssertionError("Only the explicitly reviewed witness validators may be adapted")
    if original.__globals__[constant] != HISTORICAL_SHA256:
        raise AssertionError("Historical witness descriptor changed")
    source = textwrap.dedent(inspect.getsource(original))
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise AssertionError("Expected one undecorated validator function")
    if tree.body[0].decorator_list:
        raise AssertionError("A decorated validator requires a new fixture review")
    expected = ast.parse(f"sha256({variable}.read_bytes()) != {constant}", mode="eval").body
    matches = [node for node in ast.walk(tree) if ast.dump(node) == ast.dump(expected)]
    if len(matches) != 1:
        raise AssertionError("Witness digest comparison changed or is ambiguous")
    comparison = matches[0]
    assert isinstance(comparison, ast.Compare)
    comparison.comparators[0] = ast.copy_location(ast.Constant(SYNTHETIC_SHA256), comparison.comparators[0])
    ast.fix_missing_locations(tree)
    namespace = dict(original.__globals__)
    exec(compile(tree, inspect.getfile(original), "exec"), namespace)
    return namespace[original.__name__]


def bootstrap_fixture_digest(
    target: dict[str, Any],
    request: str,
    wave: str,
    supplement: str,
    bootstrap: str,
    *,
    allow_s03: bool = False,
) -> Any:
    """Model only a pinned external input; never alias an actual byte hash."""
    evidence = target.get("evidence") or {}
    if evidence.get("path") != WITNESS_PATH:
        return evidence.get("sha256")
    pairs = {("GRR-0002.S01", "GRR-0002.B01"), ("GRR-0002.S02", "GRR-0002.B02")}
    if allow_s03:
        pairs.add(("GRR-0002.S03", "GRR-0002.B03"))
    expected = {
        "id": "W1.A04.B00",
        "candidateCommit": HISTORICAL_BOOTSTRAP_CANDIDATE,
        "evidence": {"path": WITNESS_PATH, "sha256": HISTORICAL_SHA256, "commit": HISTORICAL_BOOTSTRAP_CANDIDATE},
    }
    if request != "GRR-0002" or wave != "W1" or (supplement, bootstrap) not in pairs or target != expected:
        raise AssertionError("Synthetic bootstrap input requires the exact historical descriptor and identity")
    return SYNTHETIC_SHA256


def adapted_bootstrap_validator(original: types.FunctionType) -> types.FunctionType:
    identity = (original.__module__, original.__name__)
    if identity not in BOOTSTRAP_VALIDATORS:
        raise AssertionError("Only explicitly reviewed bootstrap-input validators may be adapted")
    parameters: tuple[str, ...]
    if identity[0] == "taskctl":
        parameters = ("data", "repo", "hold", "supplement")
        comparison = 'hashlib.sha256(evidence_payload).hexdigest() != evidence.get("sha256")'
        replacement = (
            '_fixture_bootstrap_expected_sha256(target_bootstrap, hold.get("recovery_request_id"), '
            'hold.get("target_wave"), supplement_id, bootstrap_id)'
        )
    else:
        parameters = ("repo", "packet", "data", "hold", "wave", "blocked_task", "installed", "require_installed")
        comparison = 'sha256(evidence_payload) != evidence.get("sha256")'
        replacement = (
            '_fixture_bootstrap_expected_sha256(bootstrap, packet.get("recoveryRequestId"), '
            'packet.get("targetWave"), packet.get("supplementId"), '
            '(packet.get("supplementalBootstrap") or {}).get("id"), allow_s03=True)'
        )
    if tuple(inspect.signature(original).parameters) != parameters:
        raise AssertionError("Bootstrap validator signature changed")
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].decorator_list:
        raise AssertionError("Expected one undecorated bootstrap validator")
    expected = ast.parse(comparison, mode="eval").body
    matches = [node for node in ast.walk(tree) if ast.dump(node) == ast.dump(expected)]
    if len(matches) != 1:
        raise AssertionError("Bootstrap digest comparison changed or is ambiguous")
    selected = matches[0]
    assert isinstance(selected, ast.Compare)
    selected.comparators[0] = ast.copy_location(ast.parse(replacement, mode="eval").body, selected.comparators[0])
    ast.fix_missing_locations(tree)
    namespace = dict(original.__globals__)
    namespace["_fixture_bootstrap_expected_sha256"] = bootstrap_fixture_digest
    exec(compile(tree, inspect.getfile(original), "exec"), namespace)
    return namespace[original.__name__]


class FixtureWitnesses(ExitStack):
    """Explicitly registered temporary Git roots; restore validators on exit."""

    def __init__(self, source_repo: Path) -> None:
        super().__init__()
        self.source_repo = source_repo.resolve(strict=True)
        self.roots: set[Path] = set()

    def __enter__(self) -> FixtureWitnesses:
        super().__enter__()
        try:
            for module_name, name, variable, constant in VALIDATORS:
                module = importlib.import_module(module_name)
                original = getattr(module, name)
                clone = adapted_validator(original, variable, constant)
                self.enter_context(patch.object(module, name, self.guarded(original, clone)))
            for module_name, name in BOOTSTRAP_VALIDATORS:
                module = importlib.import_module(module_name)
                original = getattr(module, name)
                clone = adapted_bootstrap_validator(original)
                self.enter_context(patch.object(module, name, self.guarded_bootstrap(original, clone)))
        except BaseException:
            self.close()
            raise
        return self

    def guarded(self, original: types.FunctionType, clone: types.FunctionType) -> Any:
        @functools.wraps(original)
        def validate(repo: Path, *args: Any, **kwargs: Any) -> Any:
            self.require_registered(repo)
            return clone(repo, *args, **kwargs)

        return validate

    def guarded_bootstrap(self, original: types.FunctionType, clone: types.FunctionType) -> Any:
        signature = inspect.signature(original)

        @functools.wraps(original)
        def validate(*args: Any, **kwargs: Any) -> Any:
            self.require_registered(signature.bind(*args, **kwargs).arguments["repo"])
            return clone(*args, **kwargs)

        return validate

    def require_registered(self, repo: Path) -> None:
        # Check the root before any witness access, including metadata traversal.
        if repo.absolute() not in self.roots or repo.resolve(strict=True) != repo.absolute():
            raise AssertionError("Synthetic witness access requires an exact registered temporary root")

    def register(self, repo: Path) -> None:
        root = require_temporary_root(repo, self.source_repo)
        if (
            not (root / ".git").is_dir()
            or (root / ".git").is_symlink()
            or (root / ".git").resolve(strict=True) != root / ".git"
        ):
            raise AssertionError("Only explicitly owned temporary Git repositories may be registered")
        self.roots.add(root)

    def write(self, repo: Path) -> Path:
        self.register(repo)
        target = repo / WITNESS_PATH
        parent = repo
        for part in PurePosixPath(WITNESS_PATH).parts[:-1]:
            # Check every existing ancestor before making even one directory.
            self.require_plain_directory(parent)
            parent = parent / part
            try:
                parent.lstat()
            except FileNotFoundError:
                parent.mkdir()
            self.require_plain_directory(parent)
        with target.open("xb") as output:
            output.write(SYNTHETIC_WITNESS)
        return target

    @staticmethod
    def require_plain_directory(path: Path) -> None:
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or path.resolve(strict=True) != path.absolute()
        ):
            raise AssertionError("Synthetic witness parent must not be redirected")


def install_synthetic_witness(test: unittest.TestCase, repo: Path, source_repo: Path) -> Path:
    adapter = getattr(test, "_historical_witness_fixture", None)
    if adapter is None:
        adapter = test.enterContext(FixtureWitnesses(source_repo))
        test._historical_witness_fixture = adapter  # type: ignore[attr-defined]
    return adapter.write(repo)


def historical_bytes(source_repo: Path, revision: str, relative: str, expected_sha256: str) -> bytes:
    """Read one explicit tracked historical input; never recover a local witness."""
    import subprocess

    parsed = PurePosixPath(relative)
    if (
        relative == WITNESS_PATH
        or not relative
        or "\\" in relative
        or ":" in relative
        or parsed.is_absolute()
        or parsed.as_posix() != relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or len(revision) != 40
        or any(c not in "0123456789abcdef" for c in revision)
    ):
        raise AssertionError("An exact non-witness historical input is required")
    payload = subprocess.check_output(["git", "show", f"{revision}:{relative}"], cwd=source_repo)
    variants = (payload, payload.replace(b"\r\n", b"\n"), payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    for candidate in variants:
        if hashlib.sha256(candidate).hexdigest() == expected_sha256:
            return candidate
    raise AssertionError("Historical raw/canonical bytes do not match the fixture's unchanged authority pin")


def init_shared_repository(repo: Path, source_repo: Path) -> None:
    """Borrow source Git objects read-only, without clone transport or source config.

    The caller owns the new fixture and must keep source objects available until
    its cleanup. Only the fixture's local metadata is written.
    """
    import subprocess

    repo = require_temporary_root(repo, source_repo, allow_missing=True)
    repo.mkdir(exist_ok=True)
    if any(repo.iterdir()):
        raise AssertionError("Historical Git fixture must start empty")
    common = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=source_repo, text=True
        ).strip()
    )
    objects = (common / "objects").resolve(strict=True)
    if not objects.is_dir() or any(c in str(objects) for c in "\n\r"):
        raise AssertionError("Expected one exact existing source object store")
    subprocess.run(["git", "init", "-b", "codex/historical-fixture", str(repo)], check=True, capture_output=True)
    with (repo / ".git/objects/info/alternates").open("x", encoding="utf-8", newline="\n") as output:
        output.write(objects.as_posix() + "\n")


def checkout_historical_repository(repo: Path, source_repo: Path, revision: str, branch: str) -> None:
    """Owned tracked snapshot with original Git ancestry; no private witness restore."""
    import subprocess

    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise AssertionError("Historical checkout requires an exact commit")
    init_shared_repository(repo, source_repo)
    if subprocess.check_output(["git", "ls-tree", "--name-only", revision, "--", WITNESS_PATH], cwd=repo).strip():
        raise AssertionError("Historical checkout must not restore the protected witness")
    subprocess.run(["git", "config", "core.autocrlf", "true"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-B", branch, revision], cwd=repo, capture_output=True, check=True)
