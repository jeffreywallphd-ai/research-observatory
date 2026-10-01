"""Protected, immutable corpus report snapshots over exact current item heads.

The writer streams the corpus under one SQLite transaction. It publishes the
complete member stream, source witnesses, provenance, and outbox together; a
limit or authority failure rolls back all report facts.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from .corpus.membership import CorpusProblem
from .corpus_report_model import (
    DIMENSIONS,
    CorpusReportAccumulator,
    CorpusReportDrillPage,
    CorpusReportFilter,
    CorpusReportMember,
    CorpusReportProblem,
    CorpusReportSnapshot,
    ReportField,
    ReportMembership,
    ReportPath,
    ReportRoute,
    ReportState,
    report_member_matches_filter,
    report_member_sha256,
)
from .corpus_repository import SqliteCorpusRepository
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.corpus import CorpusActor
from .reconciliation.contracts import SourceAssertion
from .reconciliation.exact import exact_keys
from .rights_policy import RightsAction, RightsDecision, RightsRequest, RightsUse
from .rights_repository import RightsProblem, SqliteRightsRepository, _digest
from .storage import (
    _DATABASE_ERRORS,
    CanonicalConnection,
    StorageProblem,
    _normalize_utc_millisecond,
    open_canonical_database,
)

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_BATCH = 256


class _Denied(Exception):
    def __init__(self, decision: RightsDecision, actor: CorpusActor) -> None:
        self.decision = decision
        self.actor = actor


class _StaleReadDenied(Exception):
    """A retained report witness failed after the read transaction began."""

    def __init__(self, snapshot_id: str, actor: CorpusActor, event_type: str, occurred_at: datetime) -> None:
        self.snapshot_id = snapshot_id
        self.actor = actor
        self.event_type = event_type
        self.occurred_at = occurred_at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _step(_name: str) -> None:
    """Deterministic rollback seam for migration/restart tests."""


def _now_utc() -> datetime:
    """Clock seam for retained report witness expiry and its audit timestamp."""

    return datetime.now(UTC)


class SqliteCorpusReportRepository:
    def __init__(self, database: Path, project_id: str) -> None:
        if not database.is_absolute() or not project_id:
            raise CorpusReportProblem("corpus-report-storage-invalid")
        self._database = database
        self._project = project_id

    @contextmanager
    def _transaction(self) -> Iterator[CanonicalConnection]:
        connection: CanonicalConnection | None = None
        try:
            connection = open_canonical_database(self._database, expected_project_id=self._project)
            # Rights evaluations append use decisions, including protected reads.
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except _Denied as denied:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if connection is not None:
                connection.close()
                connection = None
            try:
                SqliteRightsRepository(self._database, self._project).append_denied_attempt(
                    denied.decision, actor=denied.actor
                )
            except RightsProblem:
                raise CorpusReportProblem("corpus-report-rights-integrity-invalid") from None
            raise CorpusReportProblem("corpus-report-rights-denied") from None
        except _StaleReadDenied as denied:
            # The attempted allow decision (if any) belongs to the aborted
            # read. A separate content-free provenance event records the
            # stale snapshot denial without inventing a RightsDecision.
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if connection is not None:
                connection.close()
                connection = None
            try:
                self._append_stale_read_denial(denied)
            except (*_DATABASE_ERRORS, StorageProblem, OSError):
                raise CorpusReportProblem("corpus-report-rights-integrity-invalid") from None
            raise CorpusReportProblem("corpus-report-rights-denied") from None
        except CorpusReportProblem:
            raise
        except RightsProblem as error:
            if "integrity" in error.code or error.code == "rights-storage-invalid":
                raise CorpusReportProblem("corpus-report-rights-integrity-invalid") from None
            raise CorpusReportProblem("corpus-report-authority-denied") from None
        except CorpusProblem:
            raise CorpusReportProblem("corpus-report-authority-denied") from None
        except ValidationError, ValueError:
            raise CorpusReportProblem("corpus-report-integrity-invalid") from None
        except (*_DATABASE_ERRORS, StorageProblem, sqlite3.Error, OSError):
            raise CorpusReportProblem("corpus-report-storage-invalid") from None
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def _append_stale_read_denial(self, denied: _StaleReadDenied) -> None:
        connection = open_canonical_database(self._database, expected_project_id=self._project)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO provenance_events (event_id,project_id,revision_id,event_type,occurred_at,"
                "trace_id,actor_type,actor_id,record_sha256) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
                (
                    new_uuid_v7(),
                    self._project,
                    denied.event_type,
                    denied.occurred_at,
                    denied.actor.trace_id,
                    denied.actor.actor_type,
                    denied.actor.actor_id,
                    _sha(denied.snapshot_id),
                ),
            )
            connection.execute("COMMIT")
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def _authority(self, connection: CanonicalConnection, actor: CorpusActor) -> None:
        if (
            not is_uuid_v7(actor.actor_id)
            or actor.actor_type != "human"
            or _TRACE.fullmatch(actor.trace_id) is None
            or not is_uuid_v7(actor.intent_revision_id)
            or _HASH.fullmatch(actor.intent_sha256) is None
            or _HASH.fullmatch(actor.policy_sha256) is None
        ):
            raise CorpusReportProblem("corpus-report-command-invalid")
        try:
            _normalize_utc_millisecond(actor.occurred_at)
        except ValueError:
            raise CorpusReportProblem("corpus-report-command-invalid") from None
        SqliteCorpusRepository(self._database, self._project)._authority(connection, actor)

    def _source_for_path(
        self, connection: CanonicalConnection, path: sqlite3.Row
    ) -> tuple[str | None, SourceAssertion | None, str | None]:
        route = str(path[1])
        if route in {"recommendation", "manual"}:
            return None, None, None
        if route == "citation":
            rows = connection.execute(
                "SELECT revision_id,assertion_json FROM reconciliation_assertions "
                "WHERE project_id=? AND revision_id=? LIMIT 2",
                (self._project, path[2]),
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
                (self._project, path[2], route, path[4], path[3], path[5], path[6]),
            ).fetchall()
        if len(rows) != 1:
            raise CorpusReportProblem("corpus-report-source-unavailable")
        try:
            source = SourceAssertion.model_validate_json(str(rows[0][1]))
        except ValidationError:
            raise CorpusReportProblem("corpus-report-source-invalid") from None
        if source.project_id != self._project or (
            route in {"import-member", "connector-record"} and source.address.kind != route
        ):
            raise CorpusReportProblem("corpus-report-source-invalid")
        if route == "citation":
            key = None
        elif route == "import-member":
            key = "import:" + str(path[3])
        else:
            key = "connector:" + source.provider
        return str(rows[0][0]), source, key

    def _authorize_source(
        self,
        connection: CanonicalConnection,
        rights: SqliteRightsRepository,
        source: SourceAssertion,
        actor: CorpusActor,
        *,
        actions: tuple[RightsAction, ...],
    ) -> tuple[str, str, str, str, str, str | None]:
        subject = rights.source_metadata_subject_with_connection(connection, source)
        policy = rights.current_with_connection(connection, subject)
        if policy is None:
            # A report is a distinct derived purpose; the T01 membership bridge
            # never provides report authority.
            decision = rights.evaluate_with_connection(
                connection,
                RightsRequest(
                    actor_id=actor.actor_id,
                    subject=subject,
                    use=RightsUse(action=actions[0], purpose="corpus-report", destination_kind="local-project"),
                ),
                actor=actor,
            )
            raise _Denied(decision, actor)
        expiry: str | None = None
        for action in actions:
            decision = rights.evaluate_with_connection(
                connection,
                RightsRequest(
                    actor_id=actor.actor_id,
                    subject=subject,
                    use=RightsUse(action=action, purpose="corpus-report", destination_kind="local-project"),
                ),
                actor=actor,
            )
            if decision.code != "allow" or decision.policy_revision_id != policy.revision_id:
                raise _Denied(decision, actor)
            if decision.expires_at is not None:
                expiry = min(expiry, decision.expires_at) if expiry is not None else decision.expires_at
        policy_row = connection.execute(
            "SELECT policy_sha256 FROM rights_policy_revisions WHERE project_id=? AND revision_id=? "
            "AND subject_sha256=?",
            (self._project, policy.revision_id, _digest(subject.model_dump(mode="json", by_alias=True))),
        ).fetchone()
        if policy_row is None:
            raise CorpusReportProblem("corpus-report-rights-integrity-invalid")
        return (
            subject.source_assertion_revision_id,
            _digest(source.model_dump(mode="json", by_alias=True)),
            _digest(subject.model_dump(mode="json", by_alias=True)),
            policy.revision_id,
            str(policy_row[0]),
            expiry,
        )

    def _paths(self, connection: CanonicalConnection, item_id: str, item_revision_id: str) -> tuple[sqlite3.Row, ...]:
        rows = connection.execute(
            "SELECT p.path_id,p.kind,p.source_revision_id,p.context_revision_id,p.context_id,"
            "p.ordinal,p.record_key_sha256 FROM corpus_item_discovery_paths m "
            "JOIN corpus_discovery_paths p ON p.path_id=m.path_id AND p.project_id=m.project_id "
            "WHERE m.project_id=? AND m.item_id=? AND m.revision_id=? ORDER BY p.path_id LIMIT 1001",
            (self._project, item_id, item_revision_id),
        ).fetchall()
        if not rows or len(rows) > 1000:
            raise CorpusReportProblem("corpus-report-limit")
        return tuple(rows)

    @staticmethod
    def _fields(sources: tuple[tuple[str, SourceAssertion], ...]) -> tuple[ReportField, ...]:
        fields: list[ReportField] = []
        identifier_values: set[tuple[str, str, str]] = set()
        invalid_identifier = False
        for assertion_id, source in sources:
            keys = exact_keys(source.identifiers)
            identifier_values.update((scheme, value, assertion_id) for scheme, value in keys)
            invalid_identifier |= bool(source.identifiers) and not bool(keys)
        if identifier_values:
            scheme, _, identifier_witness = sorted(identifier_values)[0]
            fields.append(
                ReportField(dimension="identifier", state="known", value=scheme, witness_revision_id=identifier_witness)
            )
        else:
            fields.append(
                ReportField(
                    dimension="identifier",
                    state="unknown" if invalid_identifier or not sources else "not-reported",
                    value=None,
                    witness_revision_id=None,
                )
            )
        names = {
            "year": {"year", "publication-year"},
            "venue": {"venue", "journal", "container-title"},
            "language": {"language"},
            "discipline": {"discipline", "subject-area"},
            "oa": {"oa", "open-access"},
            "full-text": {"full-text", "fulltext"},
        }
        for dimension in DIMENSIONS[1:]:
            state: ReportState
            value: str | None
            witness: str | None
            observations = [
                (entry.observed.strip(), assertion_id)
                for assertion_id, source in sources
                for entry in source.fields
                if entry.name in names[dimension]
            ]
            if not observations:
                state, value, witness = "not-reported" if sources else "unknown", None, None
            elif any(not value or len(value) > 512 for value, _ in observations):
                state, value, witness = "unavailable", None, None
            else:
                normalized = {
                    (observed.casefold() if dimension in {"oa", "full-text"} else observed)
                    for observed, _ in observations
                }
                if (dimension in {"oa", "full-text"} and normalized - {"yes", "no"}) or len(normalized) != 1:
                    state, value, witness = "unknown", None, None
                else:
                    state, value = "known", next(iter(normalized))
                    witness = min(
                        assertion_id
                        for observed, assertion_id in observations
                        if (observed.casefold() if dimension in {"oa", "full-text"} else observed) == value
                    )
            fields.append(ReportField(dimension=dimension, state=state, value=value, witness_revision_id=witness))
        return tuple(fields)

    def _load_snapshot(self, connection: CanonicalConnection, snapshot_id: str) -> CorpusReportSnapshot:
        row = connection.execute(
            "SELECT summary_json,summary_sha256,member_count,members_sha256,path_count,source_count "
            "FROM corpus_report_snapshots "
            "WHERE project_id=? AND snapshot_id=?",
            (self._project, snapshot_id),
        ).fetchone()
        if row is None:
            raise CorpusReportProblem("corpus-report-not-found")
        raw = str(row[0])
        if _sha(raw) != row[1]:
            raise CorpusReportProblem("corpus-report-integrity-invalid")
        try:
            summary = CorpusReportSnapshot.model_validate_json(raw)
        except ValidationError:
            raise CorpusReportProblem("corpus-report-integrity-invalid") from None
        if (
            summary.snapshot_id,
            summary.project_id,
            summary.member_count,
            summary.discovery_path_count,
            summary.members_sha256,
        ) != (
            snapshot_id,
            self._project,
            row[2],
            row[4],
            row[3],
        ):
            raise CorpusReportProblem("corpus-report-integrity-invalid")
        stream = hashlib.sha256()
        count = 0
        previous = ""
        for ordinal, item_id, member_json, member_sha in connection.execute(
            "SELECT ordinal,item_id,member_json,member_sha256 FROM corpus_report_members "
            "WHERE snapshot_id=? AND project_id=? ORDER BY ordinal",
            (snapshot_id, self._project),
        ):
            count += 1
            if count > 100_000 or ordinal != count or not previous < item_id:
                raise CorpusReportProblem("corpus-report-integrity-invalid")
            encoded = (str(member_json) + "\n").encode("utf-8")
            if hashlib.sha256(encoded).hexdigest() != member_sha:
                raise CorpusReportProblem("corpus-report-integrity-invalid")
            stream.update(encoded)
            previous = str(item_id)
        if count != summary.member_count or stream.hexdigest() != summary.members_sha256:
            raise CorpusReportProblem("corpus-report-integrity-invalid")
        counts = connection.execute(
            "SELECT (SELECT COUNT(*) FROM corpus_report_paths WHERE snapshot_id=? AND project_id=?),"
            "(SELECT COUNT(*) FROM corpus_report_sources WHERE snapshot_id=? AND project_id=?)",
            (snapshot_id, self._project, snapshot_id, self._project),
        ).fetchone()
        if counts is None or tuple(counts) != (row[4], row[5]):
            raise CorpusReportProblem("corpus-report-integrity-invalid")
        return summary

    def _current_rights(self, connection: CanonicalConnection, snapshot_id: str, actor: CorpusActor) -> None:
        rights = SqliteRightsRepository(self._database, self._project)
        cursor = connection.execute(
            "SELECT s.source_assertion_revision_id,s.source_assertion_sha256,s.subject_sha256,"
            "s.policy_revision_id,s.policy_sha256,s.expires_at,a.assertion_json "
            "FROM corpus_report_sources s JOIN reconciliation_assertions a "
            "ON a.revision_id=s.source_assertion_revision_id AND a.project_id=s.project_id "
            "WHERE s.project_id=? AND s.snapshot_id=? ORDER BY s.source_assertion_revision_id",
            (self._project, snapshot_id),
        )
        for source_id, source_sha, subject_sha, policy_id, policy_sha, expiry, raw in cursor:
            now = _now_utc()
            if expiry is not None and datetime.fromisoformat(str(expiry).replace("Z", "+00:00")) <= now:
                raise _StaleReadDenied(snapshot_id, actor, "corpus.report-expired-read-denied", now)
            try:
                source = SourceAssertion.model_validate_json(str(raw))
            except ValidationError:
                raise CorpusReportProblem("corpus-report-integrity-invalid") from None
            observed = self._authorize_source(connection, rights, source, actor, actions=("inspect",))
            if observed[:5] != (source_id, source_sha, subject_sha, policy_id, policy_sha):
                raise _StaleReadDenied(snapshot_id, actor, "corpus.report-stale-witness-read-denied", _now_utc())

    def create(self, *, command_id: str, command_sha256: str, actor: CorpusActor) -> CorpusReportSnapshot:
        if not is_uuid_v7(command_id) or _HASH.fullmatch(command_sha256) is None:
            raise CorpusReportProblem("corpus-report-command-invalid")
        with self._transaction() as connection:
            self._authority(connection, actor)
            replay = connection.execute(
                "SELECT snapshot_id,command_sha256 FROM corpus_report_snapshots WHERE project_id=? AND command_id=?",
                (self._project, command_id),
            ).fetchone()
            if replay is not None:
                if replay[1] != command_sha256:
                    raise CorpusReportProblem("corpus-report-command-conflict")
                result = self._load_snapshot(connection, str(replay[0]))
                self._current_rights(connection, result.snapshot_id, actor)
                return result
            snapshot_id = new_uuid_v7()
            accumulator = CorpusReportAccumulator(snapshot_id=snapshot_id, project_id=self._project)
            rights = SqliteRightsRepository(self._database, self._project)
            source_witnesses: dict[str, tuple[str, str, str, str, str | None]] = {}
            last_item_id = ""
            path_count = 0
            while True:
                rows = connection.execute(
                    "SELECT s.item_id,s.revision_id,s.work_id,s.work_revision_id,s.membership,"
                    "s.duplicate_of_item_id "
                    "FROM corpus_item_states s JOIN aggregate_revisions r ON r.revision_id=s.revision_id "
                    "AND r.project_id=s.project_id AND r.aggregate_id=s.item_id "
                    "JOIN aggregate_revisions w ON w.revision_id=s.work_revision_id "
                    "AND w.project_id=s.project_id AND w.aggregate_id=s.work_id "
                    "JOIN reconciliation_work_states ws ON ws.revision_id=s.work_revision_id "
                    "AND ws.project_id=s.project_id AND ws.work_id=s.work_id "
                    "WHERE s.project_id=? AND s.item_id>? AND r.aggregate_kind='corpus-item' "
                    "AND r.revision=(SELECT MAX(h.revision) FROM aggregate_revisions h "
                    "WHERE h.project_id=r.project_id AND h.aggregate_id=r.aggregate_id) "
                    "AND ws.disposition='active' ORDER BY s.item_id LIMIT ?",
                    (self._project, last_item_id, _BATCH),
                ).fetchall()
                if not rows:
                    break
                for row in rows:
                    item_id, item_revision_id = str(row[0]), str(row[1])
                    raw_paths = self._paths(connection, item_id, item_revision_id)
                    report_paths: list[ReportPath] = []
                    metadata_sources: dict[str, SourceAssertion] = {}
                    path_witnesses: list[tuple[sqlite3.Row, str | None, str | None]] = []
                    for path in raw_paths:
                        source_id, source, key = self._source_for_path(connection, path)
                        if source_id is not None and source is not None:
                            if source_id not in source_witnesses:
                                witness = self._authorize_source(
                                    connection, rights, source, actor, actions=("derive", "inspect")
                                )
                                source_witnesses[source_id] = witness[1:]
                                connection.execute(
                                    "INSERT INTO corpus_report_sources (snapshot_id,project_id,"
                                    "source_assertion_revision_id,source_assertion_sha256,subject_sha256,"
                                    "policy_revision_id,policy_sha256,expires_at) VALUES (?,?,?,?,?,?,?,?)",
                                    (snapshot_id, self._project, *witness),
                                )
                            if (
                                path[1] in {"import-member", "connector-record"}
                                and connection.execute(
                                    "SELECT 1 FROM reconciliation_work_members WHERE project_id=? "
                                    "AND work_revision_id=? AND assertion_revision_id=? LIMIT 1",
                                    (self._project, row[3], source_id),
                                ).fetchone()
                                is not None
                            ):
                                metadata_sources[source_id] = source
                        path_rights = source_witnesses.get(source_id) if source_id is not None else None
                        report_paths.append(
                            ReportPath(
                                path_id=str(path[0]),
                                source_revision_id=str(path[2]),
                                context_revision_id=str(path[3]),
                                source_key=key,
                                route=cast(ReportRoute, str(path[1])),
                                metadata_assertion_status="retained"
                                if path_rights is not None
                                else "no-external-assertion",
                                report_inspect_status="allowed" if path_rights is not None else "unassessed",
                                rights_policy_revision_id=path_rights[2] if path_rights is not None else None,
                                rights_expires_at=path_rights[4] if path_rights is not None else None,
                                source_copy_availability="unknown",
                            )
                        )
                        path_witnesses.append((path, source_id, key))
                    # Work display labels may come from another, ungranted
                    # merged source. Only a title observed on an authorized
                    # target-Work assertion may enter this derived snapshot.
                    titles = {
                        field.observed.strip()
                        for source in metadata_sources.values()
                        for field in source.fields
                        if field.name == "title" and 1 <= len(field.observed.strip()) <= 512
                    }
                    label = next(iter(titles)) if len(titles) == 1 else None
                    member = CorpusReportMember(
                        snapshot_id=snapshot_id,
                        project_id=self._project,
                        item_id=item_id,
                        item_revision_id=item_revision_id,
                        work_id=str(row[2]),
                        work_revision_id=str(row[3]),
                        membership=cast(ReportMembership, str(row[4])),
                        duplicate_of_item_id=row[5],
                        display_label=label,
                        paths=tuple(report_paths),
                        fields=self._fields(tuple(sorted(metadata_sources.items()))),
                    )
                    accumulator.add(member)
                    member_json = _canonical(member.model_dump(mode="json", by_alias=True))
                    connection.execute(
                        "INSERT INTO corpus_report_members (snapshot_id,project_id,ordinal,item_id,"
                        "item_revision_id,work_id,work_revision_id,member_json,member_sha256) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            snapshot_id,
                            self._project,
                            accumulator.member_count,
                            item_id,
                            item_revision_id,
                            row[2],
                            row[3],
                            member_json,
                            report_member_sha256(member),
                        ),
                    )
                    for path, source_id, key in path_witnesses:
                        connection.execute(
                            "INSERT INTO corpus_report_paths (snapshot_id,project_id,item_id,item_revision_id,"
                            "path_id,source_assertion_revision_id,source_revision_id,source_key,route) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                snapshot_id,
                                self._project,
                                item_id,
                                item_revision_id,
                                path[0],
                                source_id,
                                path[2],
                                key,
                                path[1],
                            ),
                        )
                        path_count += 1
                    last_item_id = item_id
                _step("member-batch")
            summary = accumulator.finalize(
                intent_revision_id=actor.intent_revision_id,
                protocol_revision_id=actor.intent_revision_id,
                created_at=actor.occurred_at,
            )
            summary_json = _canonical(summary.model_dump(mode="json", by_alias=True))
            summary_sha = _sha(summary_json)
            provenance_id, outbox_id = new_uuid_v7(), new_uuid_v7()
            connection.execute(
                "INSERT INTO provenance_events (event_id,project_id,revision_id,event_type,occurred_at,"
                "trace_id,actor_type,actor_id,record_sha256) "
                "VALUES (?, ?, NULL, 'corpus.report-created', ?, ?, ?, ?, ?)",
                (
                    provenance_id,
                    self._project,
                    actor.occurred_at,
                    actor.trace_id,
                    actor.actor_type,
                    actor.actor_id,
                    summary_sha,
                ),
            )
            connection.execute(
                "INSERT INTO outbox_events (outbox_id,project_id,revision_id,event_type,occurred_at,"
                "available_at,state,attempt_count,published_at,idempotency_key,record_sha256) "
                "VALUES (?, ?, NULL, 'corpus.report-created', ?, ?, 'pending', 0, NULL, ?, ?)",
                (
                    outbox_id,
                    self._project,
                    actor.occurred_at,
                    actor.occurred_at,
                    "corpus-report-" + command_id,
                    summary_sha,
                ),
            )
            _step("before-seal")
            connection.execute(
                "INSERT INTO corpus_report_snapshots (snapshot_id,project_id,command_id,command_sha256,"
                "actor_id,trace_id,intent_revision_id,intent_sha256,privacy_sha256,protocol_revision_id,"
                "rule_version,created_at,member_count,path_count,source_count,members_sha256,summary_json,"
                "summary_sha256,provenance_event_id,outbox_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot_id,
                    self._project,
                    command_id,
                    command_sha256,
                    actor.actor_id,
                    actor.trace_id,
                    actor.intent_revision_id,
                    actor.intent_sha256,
                    actor.policy_sha256,
                    actor.intent_revision_id,
                    summary.rule_version,
                    actor.occurred_at,
                    summary.member_count,
                    path_count,
                    len(source_witnesses),
                    summary.members_sha256,
                    summary_json,
                    summary_sha,
                    provenance_id,
                    outbox_id,
                ),
            )
            _step("after-seal")
            return summary

    def summary(self, snapshot_id: str, *, actor: CorpusActor) -> CorpusReportSnapshot:
        if not is_uuid_v7(snapshot_id):
            raise CorpusReportProblem("corpus-report-command-invalid")
        with self._transaction() as connection:
            self._authority(connection, actor)
            summary = self._load_snapshot(connection, snapshot_id)
            self._current_rights(connection, snapshot_id, actor)
            return summary

    @staticmethod
    def _predicate(selected: CorpusReportFilter) -> tuple[str, tuple[object, ...]]:
        kind = selected.kind
        if kind == "all":
            return "1=1", ()
        if kind == "membership":
            return "json_extract(m.member_json,'$.membership')=?", (selected.membership,)
        if kind == "duplicate-linked":
            return "json_extract(m.member_json,'$.duplicateOfItemId') IS NOT NULL", ()
        if kind == "unattributed":
            return (
                "EXISTS (SELECT 1 FROM corpus_report_paths p WHERE p.snapshot_id=m.snapshot_id AND "
                "p.item_id=m.item_id AND p.source_key IS NULL)",
                (),
            )
        if kind in {"source", "route"}:
            field = "source_key" if kind == "source" else "route"
            return (
                "EXISTS (SELECT 1 FROM corpus_report_paths p WHERE p.snapshot_id=m.snapshot_id "
                f"AND p.item_id=m.item_id AND p.{field}=?)"
            ), (selected.source_key if kind == "source" else selected.route,)
        if kind in {"source-overlap", "route-overlap"}:
            field = "source_key" if kind == "source-overlap" else "route"
            values = (
                (selected.left_source_key, selected.right_source_key)
                if kind == "source-overlap"
                else (selected.left_route, selected.right_route)
            )
            clause = (
                "EXISTS (SELECT 1 FROM corpus_report_paths p WHERE p.snapshot_id=m.snapshot_id "
                f"AND p.item_id=m.item_id AND p.{field}=?)"
            )
            return f"{clause} AND {clause}", values
        clause = (
            "EXISTS (SELECT 1 FROM json_each(m.member_json,'$.fields') f WHERE "
            "json_extract(f.value,'$.dimension')=? AND json_extract(f.value,'$.state')=?"
        )
        coverage_values: tuple[object, ...] = (selected.dimension, selected.state)
        if selected.value is not None:
            clause += " AND json_extract(f.value,'$.value')=?"
            coverage_values += (selected.value,)
        return clause + ")", coverage_values

    @staticmethod
    def _encode_cursor(snapshot_id: str, selected: CorpusReportFilter, last_item_id: str) -> str:
        fingerprint = _sha(_canonical(selected.model_dump(mode="json", by_alias=True)))
        raw = _canonical({"snapshotId": snapshot_id, "filterSha256": fingerprint, "lastItemId": last_item_id})
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(snapshot_id: str, selected: CorpusReportFilter, after: str) -> str:
        try:
            value = json.loads(base64.urlsafe_b64decode(after + "=" * (-len(after) % 4)))
        except ValueError, UnicodeDecodeError:
            raise CorpusReportProblem("corpus-report-cursor-invalid") from None
        expected = _sha(_canonical(selected.model_dump(mode="json", by_alias=True)))
        if (
            not isinstance(value, dict)
            or value.get("snapshotId") != snapshot_id
            or value.get("filterSha256") != expected
            or not is_uuid_v7(value.get("lastItemId"))
        ):
            raise CorpusReportProblem("corpus-report-cursor-invalid")
        return value["lastItemId"]

    def page(
        self, snapshot_id: str, *, filter: CorpusReportFilter, after: str | None, limit: int, actor: CorpusActor
    ) -> CorpusReportDrillPage:
        if not is_uuid_v7(snapshot_id) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise CorpusReportProblem("corpus-report-command-invalid")
        try:
            selected = CorpusReportFilter.model_validate(filter)
        except ValidationError:
            raise CorpusReportProblem("corpus-report-filter-invalid") from None
        if after is not None and (not isinstance(after, str) or not 1 <= len(after) <= 512):
            raise CorpusReportProblem("corpus-report-cursor-invalid")
        with self._transaction() as connection:
            self._authority(connection, actor)
            self._load_snapshot(connection, snapshot_id)
            self._current_rights(connection, snapshot_id, actor)
            predicate, values = self._predicate(selected)
            last = self._decode_cursor(snapshot_id, selected, after) if after is not None else None
            if (
                last is not None
                and connection.execute(
                    "SELECT 1 FROM corpus_report_members m WHERE m.snapshot_id=? AND m.project_id=? "
                    "AND m.item_id=? AND " + predicate,
                    (snapshot_id, self._project, last, *values),
                ).fetchone()
                is None
            ):
                raise CorpusReportProblem("corpus-report-cursor-invalid")
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM corpus_report_members m WHERE m.snapshot_id=? AND m.project_id=? "
                    "AND " + predicate,
                    (snapshot_id, self._project, *values),
                ).fetchone()[0]
            )
            rows = connection.execute(
                "SELECT m.item_id,m.member_json,m.member_sha256 FROM corpus_report_members m "
                "WHERE m.snapshot_id=? AND m.project_id=? AND " + predicate + " AND m.item_id>? "
                "ORDER BY m.item_id LIMIT ?",
                (snapshot_id, self._project, *values, last or "", limit + 1),
            ).fetchall()
            more = len(rows) > limit
            members: list[CorpusReportMember] = []
            for item_id, raw, digest in rows[:limit]:
                try:
                    member = CorpusReportMember.model_validate_json(str(raw))
                except ValidationError:
                    raise CorpusReportProblem("corpus-report-integrity-invalid") from None
                if (
                    member.item_id != item_id
                    or report_member_sha256(member) != digest
                    or not report_member_matches_filter(member, selected)
                ):
                    raise CorpusReportProblem("corpus-report-integrity-invalid")
                members.append(member)
            cursor = self._encode_cursor(snapshot_id, selected, members[-1].item_id) if more else None
            return CorpusReportDrillPage(
                snapshot_id=snapshot_id,
                project_id=self._project,
                filter=selected,
                members=tuple(members),
                next_cursor=cursor,
                total=total,
            )


__all__ = ["SqliteCorpusReportRepository"]
