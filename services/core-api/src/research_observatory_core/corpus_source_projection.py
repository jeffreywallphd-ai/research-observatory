"""Transactional, rebuildable source-overlap counts for current CorpusItem heads.

These rows are an optimization over the append-only corpus history. They carry no
rights grant and are never the authority for a sealed report member or path.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterable
from itertools import combinations
from typing import Any, Protocol

from pydantic import ValidationError

from .reconciliation.contracts import SourceAssertion


class _Connection(Protocol):
    def execute(self, sql: str, parameters: Any = ()) -> Any: ...


class SourceProjectionProblem(RuntimeError):
    """A derived row or its source witness does not match canonical history."""


def source_for_path(
    connection: _Connection, project_id: str, path: sqlite3.Row
) -> tuple[str | None, SourceAssertion | None, str | None]:
    """Resolve exactly the source key used by immutable report paths."""

    route = str(path[1])
    if route in {"recommendation", "manual"}:
        return None, None, None
    if route == "citation":
        rows = connection.execute(
            "SELECT revision_id,assertion_json FROM reconciliation_assertions "
            "WHERE project_id=? AND revision_id=? LIMIT 2",
            (project_id, path[2]),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT revision_id,assertion_json FROM reconciliation_assertions "
            "WHERE project_id=? AND source_revision_id=? "
            "AND json_extract(assertion_json,'$.address.kind')=? "
            "AND json_extract(assertion_json,'$.address.contextId')=? "
            "AND json_extract(assertion_json,'$.address.revisionId')=? "
            "AND json_extract(assertion_json,'$.address.ordinal') IS ? "
            "AND json_extract(assertion_json,'$.address.recordKey') IS ? LIMIT 2",
            (project_id, path[2], route, path[4], path[3], path[5], path[6]),
        ).fetchall()
    if len(rows) != 1:
        raise SourceProjectionProblem("corpus-source-unavailable")
    try:
        source = SourceAssertion.model_validate_json(str(rows[0][1]))
    except ValidationError:
        raise SourceProjectionProblem("corpus-source-invalid") from None
    if source.project_id != project_id or (
        route in {"import-member", "connector-record"} and source.address.kind != route
    ):
        raise SourceProjectionProblem("corpus-source-invalid")
    if route == "citation":
        key = None
    elif route == "import-member":
        key = "import:" + str(path[3])
    else:
        key = "connector:" + source.provider
    return str(rows[0][0]), source, key


def source_counts_for_revision(
    connection: _Connection, project_id: str, item_id: str, revision_id: str, work_revision_id: str
) -> Counter[str]:
    active = connection.execute(
        "SELECT 1 FROM reconciliation_work_states WHERE project_id=? AND revision_id=? AND disposition='active'",
        (project_id, work_revision_id),
    ).fetchone()
    if active is None:
        return Counter()
    counts: Counter[str] = Counter()
    paths = connection.execute(
        "SELECT p.path_id,p.kind,p.source_revision_id,p.context_revision_id,p.context_id,"
        "p.ordinal,p.record_key_sha256 FROM corpus_item_discovery_paths m "
        "JOIN corpus_discovery_paths p ON p.path_id=m.path_id AND p.project_id=m.project_id "
        "WHERE m.project_id=? AND m.item_id=? AND m.revision_id=? ORDER BY p.path_id",
        (project_id, item_id, revision_id),
    ).fetchall()
    if not paths:
        raise SourceProjectionProblem("corpus-source-paths-unavailable")
    for path in paths:
        _, _, source_key = source_for_path(connection, project_id, path)
        if source_key is not None:
            counts[source_key] += 1
    return counts


def _encoded(counts: Counter[str]) -> str:
    return json.dumps(dict(sorted(counts.items())), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _decoded(raw: object) -> Counter[str]:
    try:
        value = json.loads(str(raw))
    except ValueError:
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid") from None
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not key or type(count) is not int or count < 1 for key, count in value.items()
    ):
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
    result: Counter[str] = Counter(value)
    if str(raw) != _encoded(result):
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
    return result


def _pair_counts(counts: Counter[str]) -> dict[tuple[str, str], int]:
    return {(left, right): counts[left] * counts[right] for left, right in combinations(sorted(counts), 2)}


def _adjust_source(connection: _Connection, project_id: str, key: str, item_delta: int, path_delta: int) -> None:
    if item_delta == path_delta == 0:
        return
    row = connection.execute(
        "SELECT item_count,discovery_path_count FROM corpus_source_totals WHERE project_id=? AND source_key=?",
        (project_id, key),
    ).fetchone()
    old_items, old_paths = (0, 0) if row is None else (int(row[0]), int(row[1]))
    items, paths = old_items + item_delta, old_paths + path_delta
    if items < 0 or paths < 0 or (items == 0) != (paths == 0):
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
    if items == 0:
        connection.execute("DELETE FROM corpus_source_totals WHERE project_id=? AND source_key=?", (project_id, key))
    elif row is None:
        connection.execute(
            "INSERT INTO corpus_source_totals (project_id,source_key,item_count,discovery_path_count) VALUES (?,?,?,?)",
            (project_id, key, items, paths),
        )
    else:
        connection.execute(
            "UPDATE corpus_source_totals SET item_count=?,discovery_path_count=? WHERE project_id=? AND source_key=?",
            (items, paths, project_id, key),
        )


def _adjust_pair(
    connection: _Connection, project_id: str, left: str, right: str, item_delta: int, path_delta: int
) -> None:
    if item_delta == path_delta == 0:
        return
    row = connection.execute(
        "SELECT item_count,discovery_path_pair_count FROM corpus_source_overlap_totals "
        "WHERE project_id=? AND left_source_key=? AND right_source_key=?",
        (project_id, left, right),
    ).fetchone()
    old_items, old_paths = (0, 0) if row is None else (int(row[0]), int(row[1]))
    items, paths = old_items + item_delta, old_paths + path_delta
    if items < 0 or paths < 0 or (items == 0) != (paths == 0):
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
    if items == 0:
        connection.execute(
            "DELETE FROM corpus_source_overlap_totals WHERE project_id=? AND left_source_key=? AND right_source_key=?",
            (project_id, left, right),
        )
    elif row is None:
        connection.execute(
            "INSERT INTO corpus_source_overlap_totals (project_id,left_source_key,right_source_key,"
            "item_count,discovery_path_pair_count) VALUES (?,?,?,?,?)",
            (project_id, left, right, items, paths),
        )
    else:
        connection.execute(
            "UPDATE corpus_source_overlap_totals SET item_count=?,discovery_path_pair_count=? "
            "WHERE project_id=? AND left_source_key=? AND right_source_key=?",
            (items, paths, project_id, left, right),
        )


def apply_source_projection(
    connection: _Connection,
    project_id: str,
    item_id: str,
    revision_id: str,
    previous_revision_id: str | None,
    work_revision_id: str,
) -> None:
    """Replace one item's contribution inside the caller's corpus transaction."""

    previous = connection.execute(
        "SELECT revision_id,work_revision_id,included_in_report,source_counts_json "
        "FROM corpus_source_item_heads WHERE project_id=? AND item_id=?",
        (project_id, item_id),
    ).fetchone()
    if (previous is None) != (previous_revision_id is None) or (
        previous is not None and str(previous[0]) != previous_revision_id
    ):
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
    old: Counter[str] = Counter()
    if previous is not None:
        old = _decoded(previous[3])
        canonical_old = source_counts_for_revision(connection, project_id, item_id, str(previous[0]), str(previous[1]))
        if old != canonical_old or int(previous[2]) != int(
            connection.execute(
                "SELECT COUNT(*) FROM reconciliation_work_states WHERE project_id=? AND revision_id=? "
                "AND disposition='active'",
                (project_id, previous[1]),
            ).fetchone()[0]
        ):
            raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
    new = source_counts_for_revision(connection, project_id, item_id, revision_id, work_revision_id)
    active = int(
        connection.execute(
            "SELECT COUNT(*) FROM reconciliation_work_states WHERE project_id=? AND revision_id=? "
            "AND disposition='active'",
            (project_id, work_revision_id),
        ).fetchone()[0]
    )
    for key in sorted(old.keys() | new.keys()):
        _adjust_source(connection, project_id, key, int(key in new) - int(key in old), new[key] - old[key])
    old_pairs, new_pairs = _pair_counts(old), _pair_counts(new)
    for left, right in sorted(old_pairs.keys() | new_pairs.keys()):
        _adjust_pair(
            connection,
            project_id,
            left,
            right,
            int((left, right) in new_pairs) - int((left, right) in old_pairs),
            new_pairs.get((left, right), 0) - old_pairs.get((left, right), 0),
        )
    connection.execute(
        "INSERT INTO corpus_source_item_heads (project_id,item_id,revision_id,work_revision_id,"
        "included_in_report,source_counts_json) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(project_id,item_id) DO UPDATE SET revision_id=excluded.revision_id,"
        "work_revision_id=excluded.work_revision_id,included_in_report=excluded.included_in_report,"
        "source_counts_json=excluded.source_counts_json",
        (project_id, item_id, revision_id, work_revision_id, active, _encoded(new)),
    )


def backfill_source_projection(connection: _Connection) -> None:
    """Populate the v20 cache from exact current heads while the migration writer is held."""

    for project_id, item_id, revision_id, work_revision_id in connection.execute(
        "SELECT s.project_id,s.item_id,s.revision_id,s.work_revision_id "
        "FROM corpus_item_states s JOIN aggregate_revisions r ON r.revision_id=s.revision_id "
        "AND r.project_id=s.project_id AND r.aggregate_id=s.item_id "
        "WHERE r.aggregate_kind='corpus-item' AND r.revision=(SELECT MAX(h.revision) "
        "FROM aggregate_revisions h WHERE h.project_id=r.project_id AND h.aggregate_id=r.aggregate_id) "
        "ORDER BY s.project_id,s.item_id"
    ).fetchall():
        # The predecessor is historical, but this is the first projected head.
        apply_source_projection(
            connection, str(project_id), str(item_id), str(revision_id), None, str(work_revision_id)
        )


def projected_source_summary(
    connection: _Connection,
    project_id: str,
    expected_members: int,
) -> tuple[tuple[tuple[str, int, int], ...], tuple[tuple[str, str, int, int], ...]]:
    head_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM corpus_source_item_heads WHERE project_id=? AND included_in_report=1",
            (project_id,),
        ).fetchone()[0]
    )
    if head_count != expected_members:
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
    sources = tuple(
        (str(key), int(items), int(paths))
        for key, items, paths in connection.execute(
            "SELECT source_key,item_count,discovery_path_count FROM corpus_source_totals "
            "WHERE project_id=? ORDER BY source_key",
            (project_id,),
        )
    )
    pairs = tuple(
        (str(left), str(right), int(items), int(paths))
        for left, right, items, paths in connection.execute(
            "SELECT left_source_key,right_source_key,item_count,discovery_path_pair_count "
            "FROM corpus_source_overlap_totals WHERE project_id=? ORDER BY left_source_key,right_source_key",
            (project_id,),
        )
    )
    return sources, pairs


def verify_report_member_projection(
    connection: _Connection,
    project_id: str,
    item_id: str,
    revision_id: str,
    source_keys: Iterable[str | None],
) -> None:
    row = connection.execute(
        "SELECT revision_id,included_in_report,source_counts_json FROM corpus_source_item_heads "
        "WHERE project_id=? AND item_id=?",
        (project_id, item_id),
    ).fetchone()
    expected = Counter(key for key in source_keys if key is not None)
    if row is None or str(row[0]) != revision_id or int(row[1]) != 1 or _decoded(row[2]) != expected:
        raise SourceProjectionProblem("corpus-source-projection-integrity-invalid")
