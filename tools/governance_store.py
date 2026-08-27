#!/usr/bin/env python3
"""Fixture-only atomic journal append and generic interrupted-append recovery.

This module intentionally has no CLI and no knowledge of the live backlog. A
caller must provide an existing directory; only the fixed journal transaction
files inside that directory can be written.
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict, cast

import governance_kernel
import governance_receipt

SCHEMA_VERSION = "1.0"
STATE_TYPE = "governance-journal-state"
TRANSACTION_TYPE = "governance-append-transaction"
STORE_CAPABILITY = "journal.compare-and-swap.v1"
STATE_FILE = ".governance-journal.json"
TRANSACTION_FILE = ".governance-append.json"
LOCK_FILE = ".governance-journal.lock"


class StorePaths(TypedDict):
    root: Path
    state: Path
    transaction: Path
    lock: Path


class PreparedAppend(TypedDict):
    transactionHash: str
    predecessorStateHash: str
    successorStateHash: str
    receiptHash: str


class StoreError(governance_kernel.KernelValidationError):
    """Raised when fixture-store state or a requested transition fails closed."""


class _WindowsLocker(Protocol):
    LK_NBLCK: int
    LK_UNLCK: int

    def locking(self, descriptor: int, mode: int, length: int) -> None: ...


class _PosixLocker(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, descriptor: int, operation: int) -> None: ...


def _require_exact_fields(document: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(document)
    if actual != expected:
        difference = sorted(str(item) for item in actual ^ expected)
        raise StoreError(f"{label} fields differ: {difference[0] if difference else '<unknown>'}")


def _is_redirected(path: Path) -> bool:
    if path.is_symlink() or getattr(os.path, "isjunction", lambda _path: False)(path):
        return True
    try:
        attributes = os.lstat(path).st_file_attributes
    except AttributeError, OSError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def store_paths(root: Path) -> StorePaths:
    candidate = Path(root)
    if not candidate.exists() or not candidate.is_dir() or _is_redirected(candidate):
        raise StoreError("Governance fixture-store root must be an existing, non-redirected directory")
    resolved = candidate.resolve(strict=True)
    if any((ancestor / ".git").exists() for ancestor in (resolved, *resolved.parents)):
        raise StoreError("Governance fixture store must be outside every Git worktree")
    paths: StorePaths = {
        "root": resolved,
        "state": resolved / STATE_FILE,
        "transaction": resolved / TRANSACTION_FILE,
        "lock": resolved / LOCK_FILE,
    }
    for path in (paths["state"], paths["transaction"], paths["lock"]):
        if _is_redirected(path):
            raise StoreError(f"Governance fixture-store path is redirected: {path.name}")
    return paths


@contextmanager
def _store_lock(paths: StorePaths):
    handle = paths["lock"].open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                windows_locker = cast(_WindowsLocker, importlib.import_module("msvcrt"))
                windows_locker.locking(handle.fileno(), windows_locker.LK_NBLCK, 1)
            else:
                posix_locker = cast(_PosixLocker, importlib.import_module("fcntl"))
                posix_locker.flock(
                    handle.fileno(),
                    posix_locker.LOCK_EX | posix_locker.LOCK_NB,
                )
        except OSError as exc:
            raise StoreError("Governance fixture store is locked by another operation") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                windows_locker = cast(_WindowsLocker, importlib.import_module("msvcrt"))
                windows_locker.locking(handle.fileno(), windows_locker.LK_UNLCK, 1)
            else:
                posix_locker = cast(_PosixLocker, importlib.import_module("fcntl"))
                posix_locker.flock(handle.fileno(), posix_locker.LOCK_UN)
    finally:
        handle.close()


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".governance-", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _remove_transaction(path: Path) -> None:
    path.unlink()


def _state_hash(state: Mapping[str, Any]) -> str:
    return governance_kernel.document_hash(state, "stateHash")


def _transaction_hash(transaction: Mapping[str, Any]) -> str:
    return governance_kernel.document_hash(transaction, "transactionHash")


def genesis_state() -> dict[str, Any]:
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": STATE_TYPE,
        "capabilities": [STORE_CAPABILITY],
        "events": [],
        "receipts": [],
        "projection": governance_kernel.initial_projection(),
        "stateHash": "",
    }
    state["stateHash"] = _state_hash(state)
    return state


def validate_state(state: Mapping[str, Any]) -> None:
    _require_exact_fields(
        state,
        {"schemaVersion", "documentType", "capabilities", "events", "receipts", "projection", "stateHash"},
        "Governance journal state",
    )
    events = state.get("events")
    receipts = state.get("receipts")
    if (
        state.get("schemaVersion") != SCHEMA_VERSION
        or state.get("documentType") != STATE_TYPE
        or state.get("capabilities") != [STORE_CAPABILITY]
        or not isinstance(events, list)
        or not isinstance(receipts, list)
        or len(events) != len(receipts)
        or state.get("stateHash") != _state_hash(state)
    ):
        raise StoreError("Governance journal state identity, content, or hash is invalid")
    projection = governance_kernel.initial_projection()
    for raw_event, raw_receipt in zip(events, receipts, strict=True):
        if not isinstance(raw_event, dict) or not isinstance(raw_receipt, dict):
            raise StoreError("Governance journal event or receipt is invalid")
        event = cast(governance_kernel.GovernanceEvent, raw_event)
        receipt = cast(governance_receipt.TransitionReceipt, raw_receipt)
        after = governance_kernel.apply_event(projection, event)
        governance_receipt.validate_receipt(
            receipt,
            event=event,
            before_projection=projection,
            after_projection=after,
            expected_git_binding=receipt["gitBinding"],
        )
        projection = after
    governance_kernel.validate_projection(projection)
    if state.get("projection") != projection:
        raise StoreError("Governance journal projection differs from event replay")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StoreError(f"Governance fixture-store JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_bytes(), object_pairs_hook=_unique_object)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise StoreError(f"Cannot read {label}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise StoreError(f"{label} must be a JSON object")
    return loaded


def _read_state(paths: StorePaths) -> dict[str, Any]:
    if not paths["state"].is_file():
        raise StoreError("Governance fixture store is not initialized")
    state = _read_json(paths["state"], "governance journal state")
    validate_state(state)
    return state


def initialize_store(root: Path) -> str:
    paths = store_paths(root)
    with _store_lock(paths):
        if paths["transaction"].exists():
            raise StoreError("Cannot initialize while an append transaction is pending")
        if paths["state"].exists():
            state = _read_state(paths)
        else:
            state = genesis_state()
            _atomic_write(paths["state"], governance_kernel.canonical_bytes(state))
        return cast(str, state["stateHash"])


def read_state(root: Path) -> dict[str, Any]:
    paths = store_paths(root)
    with _store_lock(paths):
        return copy.deepcopy(_read_state(paths))


def _build_successor(
    predecessor: dict[str, Any],
    event: governance_kernel.GovernanceEvent,
    git_binding: governance_receipt.GitBinding,
    check_results: Mapping[str, bool],
) -> tuple[dict[str, Any], governance_receipt.TransitionReceipt]:
    before = cast(dict[str, Any], predecessor["projection"])
    after = governance_kernel.apply_event(before, event)
    receipt = governance_receipt.build_receipt(
        event=event,
        before_projection=before,
        after_projection=after,
        git_binding=git_binding,
        check_results=check_results,
    )
    successor = copy.deepcopy(predecessor)
    successor["events"].append(copy.deepcopy(event))
    successor["receipts"].append(copy.deepcopy(receipt))
    successor["projection"] = after
    successor["stateHash"] = _state_hash(successor)
    validate_state(successor)
    return successor, receipt


def _build_transaction(predecessor: dict[str, Any], successor: dict[str, Any]) -> dict[str, Any]:
    transaction = {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": TRANSACTION_TYPE,
        "predecessor": copy.deepcopy(predecessor),
        "successor": copy.deepcopy(successor),
        "transactionHash": "",
    }
    transaction["transactionHash"] = _transaction_hash(transaction)
    validate_transaction(transaction)
    return transaction


def validate_transaction(transaction: Mapping[str, Any]) -> None:
    _require_exact_fields(
        transaction,
        {"schemaVersion", "documentType", "predecessor", "successor", "transactionHash"},
        "Governance append transaction",
    )
    predecessor = transaction.get("predecessor")
    successor = transaction.get("successor")
    if not isinstance(predecessor, dict) or not isinstance(successor, dict):
        raise StoreError("Governance append transaction states are invalid")
    validate_state(predecessor)
    validate_state(successor)
    if (
        transaction.get("schemaVersion") != SCHEMA_VERSION
        or transaction.get("documentType") != TRANSACTION_TYPE
        or transaction.get("transactionHash") != _transaction_hash(transaction)
        or successor["events"][:-1] != predecessor["events"]
        or successor["receipts"][:-1] != predecessor["receipts"]
        or len(successor["events"]) != len(predecessor["events"]) + 1
        or successor["capabilities"] != predecessor["capabilities"]
    ):
        raise StoreError("Governance append transaction ancestry or hash is invalid")


def _read_transaction(paths: StorePaths) -> dict[str, Any]:
    if not paths["transaction"].is_file():
        raise StoreError("No governance append transaction is pending")
    transaction = _read_json(paths["transaction"], "governance append transaction")
    validate_transaction(transaction)
    return transaction


def prepare_append(
    root: Path,
    *,
    expected_state_hash: str,
    event: governance_kernel.GovernanceEvent,
    git_binding: governance_receipt.GitBinding,
    check_results: Mapping[str, bool],
) -> PreparedAppend:
    paths = store_paths(root)
    with _store_lock(paths):
        if paths["transaction"].exists():
            raise StoreError("A governance append transaction is already pending")
        predecessor = _read_state(paths)
        if predecessor["stateHash"] != expected_state_hash:
            raise StoreError("Governance journal compare-and-swap state differs")
        successor, receipt = _build_successor(predecessor, event, git_binding, check_results)
        transaction = _build_transaction(predecessor, successor)
        _atomic_write(paths["transaction"], governance_kernel.canonical_bytes(transaction))
        return {
            "transactionHash": transaction["transactionHash"],
            "predecessorStateHash": predecessor["stateHash"],
            "successorStateHash": successor["stateHash"],
            "receiptHash": receipt["receiptHash"],
        }


def _require_transaction_hash(transaction: dict[str, Any], expected_transaction_hash: str) -> None:
    if transaction["transactionHash"] != expected_transaction_hash:
        raise StoreError("Governance append transaction differs from the expected hash")


def _current_boundary(state: dict[str, Any], transaction: dict[str, Any]) -> Literal["predecessor", "successor"]:
    state_hash = state["stateHash"]
    if state_hash == transaction["predecessor"]["stateHash"]:
        return "predecessor"
    if state_hash == transaction["successor"]["stateHash"]:
        return "successor"
    raise StoreError("Governance journal state is outside the pending transaction boundary")


def commit_prepared(root: Path, *, expected_transaction_hash: str) -> str:
    paths = store_paths(root)
    with _store_lock(paths):
        transaction = _read_transaction(paths)
        _require_transaction_hash(transaction, expected_transaction_hash)
        state = _read_state(paths)
        boundary = _current_boundary(state, transaction)
        if boundary == "predecessor":
            _atomic_write(paths["state"], governance_kernel.canonical_bytes(transaction["successor"]))
        _remove_transaction(paths["transaction"])
        return cast(str, transaction["successor"]["stateHash"])


def append_event(
    root: Path,
    *,
    expected_state_hash: str,
    event: governance_kernel.GovernanceEvent,
    git_binding: governance_receipt.GitBinding,
    check_results: Mapping[str, bool],
) -> PreparedAppend:
    prepared = prepare_append(
        root,
        expected_state_hash=expected_state_hash,
        event=event,
        git_binding=git_binding,
        check_results=check_results,
    )
    committed = commit_prepared(root, expected_transaction_hash=prepared["transactionHash"])
    if committed != prepared["successorStateHash"]:
        raise StoreError("Committed governance journal state differs from the prepared successor")
    return prepared


def recover_append(
    root: Path,
    *,
    expected_transaction_hash: str,
    action: Literal["complete", "rollback"],
) -> str:
    if action not in {"complete", "rollback"}:
        raise StoreError("Governance append recovery action must be complete or rollback")
    paths = store_paths(root)
    with _store_lock(paths):
        transaction = _read_transaction(paths)
        _require_transaction_hash(transaction, expected_transaction_hash)
        state = _read_state(paths)
        _current_boundary(state, transaction)
        target = transaction["successor"] if action == "complete" else transaction["predecessor"]
        if state["stateHash"] != target["stateHash"]:
            _atomic_write(paths["state"], governance_kernel.canonical_bytes(target))
        _remove_transaction(paths["transaction"])
        return cast(str, target["stateHash"])
