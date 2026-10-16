"""Private derivative-only guarded I/O; never widens canonical DB path authority."""

from __future__ import annotations

import os
import stat
import threading
import weakref
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

from .object_store import _FileCandidate, _held_cleanup_candidate
from .projects import _stable_directories
from .storage import StorageProblem, _close_windows_handles, _native_io_path, _open_windows_guards, _redirect

_LOCK = threading.Lock()
_GENERATIONS: weakref.WeakValueDictionary[str, threading.RLock] = weakref.WeakValueDictionary()
_SIDECARS = ("-wal", "-shm", "-journal")
_ROLES = ("", *_SIDECARS)


def _bootstrap_step(_name: str) -> None:
    """Deterministic owned-process interruption seam; no authority mutation."""


def _create_bootstrap(
    path: Path, witness: Callable[[dict[str, tuple[int, int]]], None] | None
) -> dict[Path, tuple[int, int]]:
    """Windows kernel owns unwitnessed CREATE_NEW files through process death.

    Only a committed complete canonical witness permits making them persistent.
    Release DELETE-access handles before normal deny-delete guards are acquired;
    the caller must compare every reacquired identity before opening SQLCipher.
    """
    if os.name != "nt":
        raise IndexPathProblem("protected bootstrap is unqualified on this platform")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create.restype = wintypes.HANDLE
    disposition = kernel.SetFileInformationByHandle
    disposition.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    disposition.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    descriptors: dict[Path, int] = {}
    identities: dict[Path, tuple[int, int]] = {}
    try:
        for role in _ROLES:
            candidate = path.with_name(path.name + role)
            # Noninheritable, CREATE_NEW, READ|WRITE|DELETE, OPEN_REPARSE_POINT,
            # DELETE_ON_CLOSE. Share delete only during this private bootstrap.
            handle = create(_native_io_path(candidate), 0xC0010000, 7, None, 1, 0x04200080, None)
            if handle == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDWR | os.O_NOINHERIT | getattr(os, "O_BINARY", 0))
            except BaseException:
                kernel.CloseHandle(handle)
                raise
            descriptors[candidate] = descriptor
            os.set_inheritable(descriptor, False)
            held = os.fstat(descriptor)
            identity = _identity(candidate)
            if (held.st_dev, held.st_ino) != identity or held.st_nlink != 1:
                raise IndexPathProblem("bootstrap file authority changed")
            identities[candidate] = identity
            _bootstrap_step("created-" + (role or "main"))
        if witness is not None:
            witness({role: identities[path.with_name(path.name + role)] for role in _ROLES})
        _bootstrap_step("witness-committed")
        for role in _ROLES:
            candidate = path.with_name(path.name + role)
            flags = wintypes.DWORD(8)  # FileDispositionInfoEx: clear ON_CLOSE.
            if not disposition(
                msvcrt.get_osfhandle(descriptors[candidate]), 21, ctypes.byref(flags), ctypes.sizeof(flags)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            _bootstrap_step("retained-" + (role or "main"))
        return identities
    finally:
        for descriptor in reversed(tuple(descriptors.values())):
            os.close(descriptor)


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
        self,
        root: Path,
        generation_id: str,
        *,
        create: bool,
        retirement: bool = False,
        recovery_probe: bool = False,
        bootstrap: Callable[[dict[str, tuple[int, int]]], None] | None = None,
    ) -> None:
        self.path = root / "indexes" / ("lexical-" + generation_id + ".sqlite3")
        self._main_handles: list[int] = []
        self._sidecar_handles: list[int] = []
        self._files: dict[Path, tuple[int, int]] = {}
        self._descriptors: dict[Path, int] = {}
        self._directories: dict[Path, tuple[int, int]] = {}
        self._ancestors = ExitStack()
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
            self._ancestors.enter_context(_stable_directories(list(directories)))
            journal = self.path.with_name(self.path.name + "-journal")
            if create and (journal.exists() or _redirect(journal)):
                raise IndexPathProblem("preexisting index journal is unavailable")
            if create:
                self._files = _create_bootstrap(self.path, bootstrap)
                self.journal_created = True
            else:
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
                if not create and not path.exists() and not _redirect(path):
                    descriptor = os.open(
                        _native_io_path(path), os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600
                    )
                    os.close(descriptor)
                    self._created_sidecars.add(path)
                    if suffix == "-journal":
                        self.journal_created = True
                if not create:
                    self._files[path] = _identity(path)
                elif _identity(path) != self._files[path]:
                    raise IndexPathProblem("bootstrap file authority changed")
                self._hold_descriptor(path)
                self._sidecar_handles.extend(_open_windows_guards(self.path.parent, path))
            self.check()
            if create:
                _bootstrap_step("guards-acquired")
        except BaseException:
            self.close(clean_sidecars=False)
            raise

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

    @property
    def file_identities(self) -> dict[str, tuple[int, int]]:
        self.check()
        return {role: self._files[self.path.with_name(self.path.name + role)] for role in _ROLES}

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
            try:
                self._ancestors.close()
            finally:
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


def purge_bootstrap(
    root: Path,
    generation_id: str,
    *,
    authorize: Callable[[dict[str, tuple[int, int]]], None],
    revoke: Callable[[], None],
) -> None:
    """Retire only canonically witnessed, never-source-admitted file identities.

    Missing roles are valid after partial kernel cleanup. Unknown or substituted
    names are preserved. Acquire all DELETE handles before key revocation.
    """
    path = root / "indexes" / ("lexical-" + generation_id + ".sqlite3")
    if (
        not root.is_absolute()
        or root.resolve(strict=True) != root
        or len(generation_id) != 36
        or any(c not in "0123456789abcdef-" for c in generation_id)
    ):
        raise IndexPathProblem("bootstrap location is invalid")
    with _LOCK:
        lock = _GENERATIONS.setdefault(os.path.normcase(str(path)), threading.RLock())
    if not lock.acquire(timeout=0.25):
        raise IndexPathProblem("index readers have not drained")
    try:
        with ExitStack() as holds:
            directories = [*reversed(path.parent.parents), path.parent]
            holds.enter_context(_stable_directories(directories))
            for directory in directories:
                _identity(directory, directory=True)
            known = {path.with_name(path.name + role): role for role in _ROLES}

            def inventory() -> set[Path]:
                observed = {
                    entry
                    for entry in path.parent.iterdir()
                    if os.path.normcase(entry.name).startswith(os.path.normcase(path.name))
                }
                if not observed <= known.keys():
                    raise IndexPathProblem("unknown bootstrap names are preserved")
                return observed

            observed = inventory()
            identities = {}
            deletions = []
            for candidate in sorted(observed):
                identity = _identity(candidate)
                value = candidate.stat(follow_symlinks=False)
                bound = _FileCandidate(
                    "indexes", Path(_native_io_path(candidate)), path.parent, identity, value.st_size, value.st_mtime_ns
                )
                _rename, delete, reader = holds.enter_context(_held_cleanup_candidate(bound))
                held = os.fstat(reader.fileno())
                identities[known[candidate]] = (held.st_dev, held.st_ino)
                deletions.append(delete)
            if inventory() != observed:
                raise IndexPathProblem("bootstrap names changed during drain")
            authorize(identities)
            revoke()
            for delete in deletions:
                delete()
        assert_retired_absent(root, generation_id)
    finally:
        lock.release()


__all__ = ["IndexFileGuard", "IndexPathProblem"]
