"""Private derivative-only guarded I/O; never widens canonical DB path authority."""

from __future__ import annotations

import os
import stat
import threading
import weakref
from collections.abc import Callable
from pathlib import Path

from .object_store import _FileCandidate, _held_cleanup_candidate
from .projects import _stable_directories
from .storage import StorageProblem, _close_windows_handles, _native_io_path, _open_windows_guards, _redirect

_LOCK = threading.Lock()
_GENERATIONS: weakref.WeakValueDictionary[str, threading.RLock] = weakref.WeakValueDictionary()
_SIDECARS = ("-wal", "-shm", "-journal")


class IndexPathProblem(RuntimeError):
    """No paths or derivative content in a confinement failure."""


def _present(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def assert_retired_absent(root: Path, generation_id: str) -> None:
    path = root / "indexes" / ("lexical-" + generation_id + ".sqlite3")
    directories = [*reversed(path.parent.parents), path.parent]
    with _stable_directories(directories):
        if any(_present(path.with_name(path.name + suffix)) for suffix in ("", *_SIDECARS)):
            raise IndexPathProblem("retired index names are not absent")


def _identity(path: Path, *, directory: bool = False) -> tuple[int, int]:
    value = path.stat(follow_symlinks=False)
    if (
        _redirect(path)
        or (not stat.S_ISDIR(value.st_mode) if directory else not stat.S_ISREG(value.st_mode) or value.st_nlink != 1)
        or path.resolve(strict=True) != path
    ):
        raise IndexPathProblem("index path authority is unavailable")
    return value.st_dev, value.st_ino


class IndexFileGuard:
    """Hold ancestor, DB and all possible WAL-profile sidecar names through close.

    Core's Native project scope supplies the root. This adapter accepts only
    its own generated filename in the governed indexes class. Canonical helpers
    reused here are metadata/handle primitives; no DatabaseKeyLease is accepted.
    """

    def __init__(
        self, root: Path, generation_id: str, *, create: bool, retirement: bool = False, recovery_probe: bool = False
    ) -> None:
        self.path = root / "indexes" / ("lexical-" + generation_id + ".sqlite3")
        self._main_handles: list[int] = []
        self._sidecar_handles: list[int] = []
        self._files: dict[Path, tuple[int, int]] = {}
        self._descriptors: dict[Path, int] = {}
        self._directories: dict[Path, tuple[int, int]] = {}
        self._locked = False
        self._retirement = retirement
        self._recovery_probe = recovery_probe
        self.journal_created = False
        self._created_sidecars: set[Path] = set()
        self._lock: threading.RLock
        try:
            if (
                not root.is_absolute()
                or root.resolve(strict=True) != root
                or self.path.parent != root / "indexes"
                or self.path.name != "lexical-" + generation_id + ".sqlite3"
                or any(c not in "0123456789abcdef-" for c in generation_id)
                or len(generation_id) != 36
            ):
                raise IndexPathProblem("index location is invalid")
            # Reject all redirected ancestors, not only the immediate parent.
            directories = (*reversed(self.path.parent.parents), self.path.parent)
            self._directories = {path: _identity(path, directory=True) for path in directories}
            with _LOCK:
                self._lock = _GENERATIONS.setdefault(os.path.normcase(str(self.path)), threading.RLock())
            if not self._lock.acquire(timeout=0.25):
                raise IndexPathProblem("index readers have not drained")
            self._locked = True
            journal = self.path.with_name(self.path.name + "-journal")
            if create and (journal.exists() or _redirect(journal)):
                raise IndexPathProblem("preexisting index journal is unavailable")
            if create:
                descriptor = os.open(
                    _native_io_path(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600
                )
                os.close(descriptor)
            self._files[self.path] = _identity(self.path)
            self._hold_descriptor(self.path)
            for directory in directories:
                self._main_handles.extend(_open_windows_guards(directory, self.path))
            for suffix in _SIDECARS:
                path = self.path.with_name(self.path.name + suffix)
                if recovery_probe:
                    continue
                if retirement:
                    if _present(path):
                        raise IndexPathProblem("retired sidecars need authenticated recovery")
                    continue
                if not path.exists() and not _redirect(path):
                    descriptor = os.open(
                        _native_io_path(path), os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600
                    )
                    os.close(descriptor)
                    self._created_sidecars.add(path)
                    if suffix == "-journal":
                        self.journal_created = True
                self._files[path] = _identity(path)
                self._hold_descriptor(path)
                self._sidecar_handles.extend(_open_windows_guards(self.path.parent, path))
            self.check()
        except OSError, StorageProblem, IndexPathProblem:
            self.close(clean_sidecars=False)
            raise IndexPathProblem("index file authority is unavailable") from None

    def _hold_descriptor(self, path: Path) -> None:
        descriptor = os.open(_native_io_path(path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        self._descriptors[path] = descriptor
        held = os.fstat(descriptor)
        if held.st_nlink != 1 or (held.st_dev, held.st_ino) != self._files[path]:
            raise IndexPathProblem("index file authority changed")

    def check(self) -> None:
        try:
            if not self._locked:
                raise IndexPathProblem("index file authority is unavailable")
            for path, expected in self._directories.items():
                if _identity(path, directory=True) != expected:
                    raise IndexPathProblem("index ancestor authority changed")
            for path, expected in self._files.items():
                held = os.fstat(self._descriptors[path])
                if _identity(path) != expected or (held.st_dev, held.st_ino) != expected or held.st_nlink != 1:
                    raise IndexPathProblem("index file authority changed")
            # A fresh owned zero-byte sentinel pins the rollback-journal name.
            # Fresh DB bootstrap uses MEMORY then WAL; existing DBs must already
            # be WAL. The sentinel must never acquire data in either case.
            journal = self.path.with_name(self.path.name + "-journal")
            if self._recovery_probe:
                pass
            elif self._retirement:
                if any(_present(self.path.with_name(self.path.name + suffix)) for suffix in _SIDECARS):
                    raise IndexPathProblem("retired sidecar authority changed")
            elif os.fstat(self._descriptors[journal]).st_size != 0:
                raise IndexPathProblem("index journal authority is unavailable")
        except OSError, StorageProblem:
            raise IndexPathProblem("index file authority is unavailable") from None

    @property
    def journal_identity(self) -> str:
        value = self._files[self.path.with_name(self.path.name + "-journal")]
        return str(value[0]) + ":" + str(value[1])

    @property
    def file_identity(self) -> tuple[int, int]:
        self.check()
        return self._files[self.path]

    def close(self, *, clean_sidecars: bool) -> None:
        """SQLCipher must already be closed; purge only checkpointed owned names.

        Keeping deny-delete handles through SQLCipher close can leave its empty
        sidecars. Remove those exact identities under the held ancestors. A
        different reader's deny-delete handles prevent premature removal.
        """
        candidates = []
        failure = None
        try:
            if clean_sidecars:
                self.check()
                for path, descriptor in self._descriptors.items():
                    if path == self.path:
                        continue
                    value = os.fstat(descriptor)
                    if path.name.endswith(("-wal", "-journal")) and value.st_size != 0:
                        raise IndexPathProblem("index cleanup checkpoint is incomplete")
                    candidates.append(
                        _FileCandidate(
                            "indexes",
                            Path(_native_io_path(path)),
                            self.path.parent,
                            self._files[path],
                            value.st_size,
                            value.st_mtime_ns,
                        )
                    )
        except OSError, StorageProblem, IndexPathProblem:
            # A failed identity check must still release every lifetime hold.
            candidates = []
            failure = IndexPathProblem("index cleanup authority is unavailable")
        _close_windows_handles(self._sidecar_handles)
        self._sidecar_handles = []
        for path, descriptor in tuple(self._descriptors.items()):
            if path != self.path:
                os.close(descriptor)
                del self._descriptors[path]
        try:
            if clean_sidecars:
                for candidate in candidates:
                    try:
                        # The newly opened deletion handle authenticates the
                        # previously held inode/size/mtime before disposition.
                        # No path-based deletion follows a released guard.
                        with _held_cleanup_candidate(candidate) as (_rename, delete, _reader):
                            delete()
                    except FileNotFoundError:
                        continue
                    except PermissionError:
                        # Another held reader is still live; its final close
                        # owns cleanup. This is not permission to purge a DB.
                        continue
        finally:
            _close_windows_handles(self._main_handles)
            self._main_handles = []
            for descriptor in self._descriptors.values():
                os.close(descriptor)
            self._descriptors = {}
            if self._locked:
                self._locked = False
                self._lock.release()
        if failure is not None:
            raise failure

    def purge_retired(self, revoke: Callable[[], None]) -> None:
        """Internal retirement only, after canonical deselection.

        Acquire every exact DELETE handle before any disposition. Directory
        lifetime holds and the generation mutex remain until all readers drain
        and deletion finishes; a live reader preserves the entire candidate.
        Revocation follows successful drain/identity/DELETE-handle acquisition.
        """
        try:
            self.check()
            if not self._retirement:
                raise IndexPathProblem("index retirement preparation is unavailable")
            candidates = []
            ordered = sorted(self._descriptors, key=lambda path: path == self.path)
            for path in ordered:
                value = os.fstat(self._descriptors[path])
                candidates.append(
                    _FileCandidate(
                        "indexes",
                        Path(_native_io_path(path)),
                        self.path.parent,
                        self._files[path],
                        value.st_size,
                        value.st_mtime_ns,
                    )
                )
            _close_windows_handles(self._sidecar_handles)
            self._sidecar_handles = []
            # Each existing helper pair is (directory, database). Release only
            # file holds; every ancestor is still pinned during disposition.
            _close_windows_handles(self._main_handles[1::2])
            self._main_handles = self._main_handles[::2]
            for descriptor in self._descriptors.values():
                os.close(descriptor)
            self._descriptors = {}
            with _held_cleanup_candidate(candidates[0]) as (_rename, delete, _reader):
                # This DELETE handle now excludes new writers. No recovery key
                # is destroyed until drain, identity and absence are proven.
                if any(_present(self.path.with_name(self.path.name + suffix)) for suffix in _SIDECARS):
                    raise IndexPathProblem("retired sidecars appeared during drain")
                revoke()
                delete()
        except OSError, StorageProblem, IndexPathProblem:
            raise IndexPathProblem("retired index cleanup is incomplete") from None
        finally:
            self.close(clean_sidecars=False)


__all__ = ["IndexFileGuard", "IndexPathProblem"]
