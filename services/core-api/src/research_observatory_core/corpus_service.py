"""Local corpus commands fenced by current project, Intent, policy and source.

All durable output identities are minted by Core inside repository builders.
Import and connector paths resolve current source rights; connector discovery
also needs a trusted query-revision resolver. Citation paths are human-attested
and refer only to an exact retained Work member verified by the repository.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from .connectors.broker import utc_now
from .corpus.membership import (
    CorpusDecision,
    CorpusItemRevision,
    CorpusProblem,
    Dimension,
    DiscoveryPath,
    append_discovery_path,
    apply_decision,
    rebind_work,
)
from .corpus_report_model import CorpusReportDrillPage, CorpusReportFilter, CorpusReportProblem, CorpusReportSnapshot
from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ingestion.preview_workflow import fingerprint
from .ports.corpus import CorpusActor, CorpusConnectorQueryResolver, CorpusRepository
from .ports.corpus_reports import CorpusReportRepository
from .ports.import_previews import PreviewProblem
from .ports.reconciliation import ReconciliationConnectorSourceService, ReconciliationSourceService
from .ports.repositories import IntentRevisionRepository, RepositoryProblem
from .ports.rights import (
    RightsOutputRecheckState,
    RightsPermissionDraft,
    RightsProblem,
    RightsRecheckScope,
    RightsRepository,
)
from .privacy import PrivacyPolicyProblem, ProjectPrivacyService
from .projects import ProjectLifecycleProblem, ProjectLifecycleService
from .reconciliation.contracts import ReconciliationProblem, SourceAddress, SourceAssertion
from .research_intents import IntentProblem, validated_workflow_authority
from .rights_policy import RightsDecision, RightsPolicyRevision, RightsRequest, RightsSubject, RightsUse

_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_REASON = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z\Z")


def _identity(value: object) -> str:
    if not isinstance(value, str) or not is_uuid_v7(value):
        raise CorpusProblem("corpus-command-invalid")
    return value


def _evidence(values: object) -> tuple[str, ...]:
    if (
        not isinstance(values, tuple)
        or not 1 <= len(values) <= 64
        or any(not isinstance(value, str) or not is_uuid_v7(value) for value in values)
        or values != tuple(sorted(set(values)))
    ):
        raise CorpusProblem("corpus-evidence-invalid")
    return values


def _reason(value: object) -> str:
    if not isinstance(value, str) or _REASON.fullmatch(value) is None:
        raise CorpusProblem("corpus-reason-invalid")
    return value


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or _TIME.fullmatch(value) is None:
        raise CorpusProblem("corpus-actor-unavailable")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise CorpusProblem("corpus-actor-unavailable") from None
    if parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z") != value:
        raise CorpusProblem("corpus-actor-unavailable")
    return value


def _digest(operation: str, actor: CorpusActor, command_id: str, **values: object) -> str:
    """Bind command meaning, excluding retry-varying trace/time and minted IDs."""

    payload = {
        "operation": operation,
        "commandId": command_id,
        "actorId": actor.actor_id,
        "intentRevisionId": actor.intent_revision_id,
        "intentSha256": actor.intent_sha256,
        "policySha256": actor.policy_sha256,
        **values,
    }
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


class CorpusService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        privacy: ProjectPrivacyService,
        *,
        imports: ReconciliationSourceService,
        connectors: ReconciliationConnectorSourceService,
        repository_factory: Callable[[Path, str], CorpusRepository],
        intent_factory: Callable[[Path, str], IntentRevisionRepository],
        actor_id: str,
        connector_query: CorpusConnectorQueryResolver | None = None,
        rights_repository_factory: Callable[[Path, str], RightsRepository] | None = None,
        report_repository_factory: Callable[[Path, str], CorpusReportRepository] | None = None,
        now: Callable[[], str] = utc_now,
    ) -> None:
        if not is_uuid_v7(actor_id):
            raise CorpusProblem("corpus-actor-unavailable")
        self._projects, self._privacy = projects, privacy
        self._imports, self._connectors = imports, connectors
        self._repository, self._intents = repository_factory, intent_factory
        self._rights_repository = rights_repository_factory
        self._report_repository = report_repository_factory
        self._actor_id, self._connector_query, self._now = actor_id, connector_query, now

    def _rights(self, path: Path, project_id: str) -> RightsRepository:
        if self._rights_repository is None:
            raise CorpusProblem("corpus-rights-unavailable")
        return self._rights_repository(path, project_id)

    def _reports(self, path: Path, project_id: str) -> CorpusReportRepository:
        if self._report_repository is None:
            raise CorpusProblem("corpus-report-unavailable")
        return self._report_repository(path, project_id)

    def create_report(self, root: str, *, command_id: str, trace_id: str) -> CorpusReportSnapshot:
        """Materialize one complete, immutable projection under current authority."""

        _identity(command_id)

        def action(_repo: CorpusRepository, actor: CorpusActor, _intent: str, path: Path, project_id: str):
            return self._reports(path, project_id).create(
                command_id=command_id,
                command_sha256=_digest("create-report", actor, command_id, projectId=project_id),
                actor=actor,
            )

        return self._with_authority(root, trace_id, action)

    def inspect_report(self, root: str, snapshot_id: str, *, trace_id: str) -> CorpusReportSnapshot:
        _identity(snapshot_id)
        return self._with_authority(
            root,
            trace_id,
            lambda _repo, actor, _intent, path, project_id: self._reports(path, project_id).summary(
                snapshot_id, actor=actor
            ),
            require_write=False,
        )

    def drill_report(
        self,
        root: str,
        snapshot_id: str,
        *,
        filter: CorpusReportFilter,
        cursor: str | None,
        limit: int,
        trace_id: str,
    ) -> CorpusReportDrillPage:
        _identity(snapshot_id)
        try:
            selected = CorpusReportFilter.model_validate(filter)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None
        if (
            isinstance(limit, bool)
            or not 1 <= limit <= 100
            or (cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 512))
        ):
            raise CorpusProblem("corpus-command-invalid")
        return self._with_authority(
            root,
            trace_id,
            lambda _repo, actor, _intent, path, project_id: self._reports(path, project_id).page(
                snapshot_id, filter=selected, after=cursor, limit=limit, actor=actor
            ),
            require_write=False,
        )

    def publish_rights(
        self,
        root: str,
        *,
        command_id: str,
        subject: RightsSubject,
        permissions: tuple[RightsPermissionDraft, ...],
        expected_predecessor_revision_id: str | None,
        confirmed: bool,
        trace_id: str,
    ) -> RightsPolicyRevision:
        """Publish an explicit researcher decision; Core mints durable IDs after replay."""

        if confirmed is not True or not is_uuid_v7(command_id):
            raise CorpusProblem("corpus-command-invalid")
        try:
            subject = RightsSubject.model_validate(subject)
            permissions = tuple(RightsPermissionDraft.model_validate(value) for value in permissions)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None

        def action(_repo: CorpusRepository, actor: CorpusActor, _intent: str, path: Path, project_id: str):
            if subject.project_id != project_id:
                raise CorpusProblem("corpus-rights-denied")
            command_hash = _digest(
                "publish-rights",
                actor,
                command_id,
                projectId=project_id,
                subject=subject.model_dump(mode="json", by_alias=True),
                permissions=[value.model_dump(mode="json", by_alias=True) for value in permissions],
                expectedPredecessorRevisionId=expected_predecessor_revision_id,
            )
            return self._rights(path, project_id).publish_draft(
                subject,
                permissions,
                expected_predecessor_revision_id,
                command_id=command_id,
                command_sha256=command_hash,
                actor=actor,
            )

        return self._with_authority(root, trace_id, action)

    def current_rights(self, root: str, subject: RightsSubject, *, trace_id: str) -> RightsPolicyRevision | None:
        try:
            subject = RightsSubject.model_validate(subject)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None
        return self._with_authority(
            root,
            trace_id,
            lambda _repo, actor, _intent, path, project: self._rights(path, project).current(subject, actor=actor),
            require_write=False,
        )

    def rights_recheck_scope(self, root: str, subject: RightsSubject, *, trace_id: str) -> RightsRecheckScope | None:
        try:
            subject = RightsSubject.model_validate(subject)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None
        return self._with_authority(
            root,
            trace_id,
            lambda _repo, actor, _intent, path, project: self._rights(path, project).recheck_scope(
                subject, actor=actor
            ),
            require_write=False,
        )

    def output_rights_rechecks(self, root: str, output_revision_id: str, *, trace_id: str) -> RightsOutputRecheckState:
        """Read protected output-specific rights markers and pending scope."""

        if not is_uuid_v7(output_revision_id):
            raise CorpusProblem("corpus-command-invalid")
        return self._with_authority(
            root,
            trace_id,
            lambda _repo, actor, _intent, path, project: self._rights(path, project).output_rechecks(
                output_revision_id, actor=actor
            ),
            require_write=False,
        )

    def advance_rights_rechecks(
        self, root: str, subject: RightsSubject, *, batch_size: int, trace_id: str
    ) -> RightsRecheckScope | None:
        try:
            subject = RightsSubject.model_validate(subject)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None
        if isinstance(batch_size, bool) or not 1 <= batch_size <= 1_000:
            raise CorpusProblem("corpus-command-invalid")
        return self._with_authority(
            root,
            trace_id,
            lambda _repo, actor, _intent, path, project: self._rights(path, project).advance_rechecks(
                subject, actor=actor, batch_size=batch_size
            ),
        )

    def evaluate_rights(self, root: str, subject: RightsSubject, use: RightsUse, *, trace_id: str) -> RightsDecision:
        try:
            subject, use = RightsSubject.model_validate(subject), RightsUse.model_validate(use)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None

        def action(_repo: CorpusRepository, actor: CorpusActor, _intent: str, path: Path, project_id: str):
            if subject.project_id != project_id:
                raise CorpusProblem("corpus-rights-denied")
            return self._rights(path, project_id).evaluate(
                RightsRequest(actor_id=actor.actor_id, subject=subject, use=use), actor=actor
            )

        return self._with_authority(root, trace_id, action)

    def _with_authority[Result](
        self,
        root: str,
        trace_id: str,
        action: Callable[[CorpusRepository, CorpusActor, str, Path, str], Result],
        *,
        require_write: bool = True,
    ) -> Result:
        if not isinstance(trace_id, str) or _TRACE.fullmatch(trace_id) is None:
            raise CorpusProblem("corpus-trace-invalid")

        def guarded(path: Path, project_id: str) -> Result:
            intents = self._intents(path, project_id)
            bridge = intents.project_identity()
            if bridge is None or bridge.manifest_project_id != project_id:
                raise CorpusProblem("corpus-intent-unavailable")
            _, revisions, _, _ = validated_workflow_authority(intents, expected_project_id=bridge.domain_project_id)
            if (
                not revisions
                or revisions[0].get("status") != "accepted"
                or revisions[0].get("projectId") != bridge.domain_project_id
            ):
                raise CorpusProblem("corpus-intent-unavailable")
            current = revisions[0]
            revision_id = current.get("revisionId")
            if not isinstance(revision_id, str) or not is_uuid_v7(revision_id):
                raise CorpusProblem("corpus-intent-unavailable")
            content_hash = current.get("revisionContentHash")
            if not isinstance(content_hash, str) or not content_hash.startswith("sha256:"):
                raise CorpusProblem("corpus-intent-unavailable")
            intent_hash = content_hash.removeprefix("sha256:")
            if _HASH.fullmatch(intent_hash) is None:
                raise CorpusProblem("corpus-intent-unavailable")
            policy = self._privacy.get(str(path))
            if policy.project_id != project_id:
                raise CorpusProblem("corpus-policy-unavailable")
            policy_hash = fingerprint(policy.model_dump(mode="json", by_alias=True)).removeprefix("sha256:")
            actor = CorpusActor(
                actor_id=self._actor_id,
                trace_id=trace_id,
                occurred_at=_timestamp(self._now()),
                intent_revision_id=revision_id,
                intent_sha256=intent_hash,
                policy_sha256=policy_hash,
            )
            return action(self._repository(path, project_id), actor, revision_id, path, project_id)

        try:
            return self._projects.perform_open_project_action(root=root, require_write=require_write, action=guarded)
        except ProjectLifecycleProblem, RepositoryProblem, PrivacyPolicyProblem, IntentProblem:
            raise CorpusProblem("corpus-authority-unavailable") from None
        except RightsProblem as error:
            if "integrity" in error.code or error.code in {"rights-storage-invalid", "rights-transaction-required"}:
                raise CorpusProblem("corpus-rights-integrity-invalid") from None
            if error.code == "rights-clock-unavailable":
                raise CorpusProblem("corpus-actor-unavailable") from None
            if error.code in {"rights-predecessor-stale", "rights-command-conflict", "rights-impact-limit"}:
                raise CorpusProblem("corpus-command-conflict") from None
            if error.code in {"rights-command-invalid", "rights-request-invalid", "rights-policy-invalid"}:
                raise CorpusProblem("corpus-command-invalid") from None
            raise CorpusProblem("corpus-rights-denied") from None
        except CorpusReportProblem as error:
            if error.code in {
                "corpus-report-integrity-invalid",
                "corpus-report-storage-invalid",
                "corpus-report-rights-integrity-invalid",
                "corpus-report-source-invalid",
            }:
                raise CorpusProblem("corpus-report-integrity-invalid") from None
            if error.code == "corpus-report-not-found":
                raise CorpusProblem("corpus-report-not-found") from None
            if error.code == "corpus-report-limit":
                raise CorpusProblem("corpus-report-limit") from None
            if error.code in {
                "corpus-report-command-invalid",
                "corpus-report-filter-invalid",
                "corpus-report-cursor-invalid",
            }:
                raise CorpusProblem("corpus-command-invalid") from None
            if error.code == "corpus-report-command-conflict":
                raise CorpusProblem("corpus-command-conflict") from None
            raise CorpusProblem("corpus-rights-denied") from None

    def _source(self, path: Path, project_id: str, address: SourceAddress) -> tuple[SourceAssertion, str | None]:
        if address.kind == "connector-record" and self._connector_query is None:
            raise CorpusProblem("corpus-connector-query-unavailable")
        service = self._imports if address.kind == "import-member" else self._connectors
        try:
            source = SourceAssertion.model_validate(service.reconciliation_source(str(path), address))
            if source.project_id != project_id or source.address != address:
                raise CorpusProblem("corpus-source-mismatch")
            # The repository decides the current, exact-copy rights under its
            # protected writer. Legacy import rights are only a metadata bridge
            # when no newer policy exists for this retained assertion/copy.
            query_revision_id = None
            if address.kind == "connector-record" and self._connector_query is not None:
                query_revision_id = self._connector_query(str(path), address, source)
                if not isinstance(query_revision_id, str) or not is_uuid_v7(query_revision_id):
                    raise CorpusProblem("corpus-connector-query-unavailable")
            return source, query_revision_id
        except ReconciliationProblem, PreviewProblem, ValidationError, ValueError, TypeError:
            raise CorpusProblem("corpus-source-unavailable") from None

    @staticmethod
    def _path(
        item_id: str,
        source: SourceAssertion,
        query_revision_id: str | None,
        *,
        occurred_at: str,
        predecessor_item_revision_id: str | None,
    ) -> DiscoveryPath:
        address = source.address
        return DiscoveryPath(
            path_id=new_uuid_v7(),
            project_id=source.project_id,
            item_id=item_id,
            kind=address.kind,
            direction="source-to-corpus-item",
            occurred_at=occurred_at,
            predecessor_item_revision_id=predecessor_item_revision_id,
            source_revision_id=source.source_revision_id,
            context_id=address.context_id,
            context_revision_id=address.revision_id,
            ordinal=address.ordinal,
            record_key_sha256=address.record_key,
            query_revision_id=query_revision_id,
        )

    @staticmethod
    def _current(current: CorpusItemRevision, project_id: str, item_id: str, expected: str) -> CorpusItemRevision:
        current = CorpusItemRevision.model_validate(current)
        if current.project_id != project_id or current.item_id != item_id:
            raise CorpusProblem("corpus-item-scope-mismatch")
        if current.revision_id != expected:
            raise CorpusProblem("corpus-predecessor-stale")
        return current

    def create(
        self,
        root: str,
        *,
        command_id: str,
        work_id: str,
        work_revision_id: str,
        source: SourceAddress,
        trace_id: str,
    ) -> CorpusItemRevision:
        _identity(command_id), _identity(work_id), _identity(work_revision_id)
        try:
            source = SourceAddress.model_validate(source)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None

        def action(repo: CorpusRepository, actor: CorpusActor, _intent: str, path: Path, project_id: str):
            prepared, query_revision_id = self._source(path, project_id, source)
            command_hash = _digest(
                "create",
                actor,
                command_id,
                projectId=project_id,
                workId=work_id,
                workRevisionId=work_revision_id,
                source=prepared.model_dump(mode="json", by_alias=True),
                queryRevisionId=query_revision_id,
            )

            def build() -> tuple[CorpusItemRevision, DiscoveryPath]:
                item_id = new_uuid_v7()
                discovery = self._path(
                    item_id,
                    prepared,
                    query_revision_id,
                    occurred_at=actor.occurred_at,
                    predecessor_item_revision_id=None,
                )
                item = CorpusItemRevision(
                    project_id=project_id,
                    item_id=item_id,
                    revision_id=new_uuid_v7(),
                    previous_revision_id=None,
                    work_id=work_id,
                    work_revision_id=work_revision_id,
                    membership="candidate",
                    review="pending",
                    duplicate_of_item_id=None,
                    availability="unknown",
                    discovery_path_ids=(discovery.path_id,),
                    decision_revision_id=None,
                )
                return item, discovery

            return repo.create(
                command_id=command_id, command_sha256=command_hash, actor=actor, source=prepared, build=build
            )

        return self._with_authority(root, trace_id, action)

    def create_citation(
        self,
        root: str,
        *,
        command_id: str,
        work_id: str,
        work_revision_id: str,
        citing_work_id: str,
        citing_work_revision_id: str,
        source_assertion_revision_id: str,
        trace_id: str,
    ) -> CorpusItemRevision:
        """Create a candidate from a human-attested route, not a verified citation fact."""

        for value in (
            command_id,
            work_id,
            work_revision_id,
            citing_work_id,
            citing_work_revision_id,
            source_assertion_revision_id,
        ):
            _identity(value)

        def action(repo: CorpusRepository, actor: CorpusActor, _intent: str, _path: Path, project_id: str):
            command_hash = _digest(
                "create-citation",
                actor,
                command_id,
                projectId=project_id,
                workId=work_id,
                workRevisionId=work_revision_id,
                citingWorkId=citing_work_id,
                citingWorkRevisionId=citing_work_revision_id,
                sourceAssertionRevisionId=source_assertion_revision_id,
            )

            def build() -> tuple[CorpusItemRevision, DiscoveryPath]:
                item_id = new_uuid_v7()
                discovery = DiscoveryPath(
                    path_id=new_uuid_v7(),
                    project_id=project_id,
                    item_id=item_id,
                    kind="citation",
                    direction="source-to-corpus-item",
                    occurred_at=actor.occurred_at,
                    predecessor_item_revision_id=None,
                    source_revision_id=source_assertion_revision_id,
                    context_id=citing_work_id,
                    context_revision_id=citing_work_revision_id,
                    citing_work_revision_id=citing_work_revision_id,
                )
                item = CorpusItemRevision(
                    project_id=project_id,
                    item_id=item_id,
                    revision_id=new_uuid_v7(),
                    previous_revision_id=None,
                    work_id=work_id,
                    work_revision_id=work_revision_id,
                    membership="candidate",
                    review="pending",
                    duplicate_of_item_id=None,
                    availability="unknown",
                    discovery_path_ids=(discovery.path_id,),
                    decision_revision_id=None,
                )
                return item, discovery

            return repo.create_citation(
                command_id=command_id,
                command_sha256=command_hash,
                actor=actor,
                work_id=work_id,
                work_revision_id=work_revision_id,
                citing_work_id=citing_work_id,
                citing_work_revision_id=citing_work_revision_id,
                source_assertion_revision_id=source_assertion_revision_id,
                build=build,
            )

        return self._with_authority(root, trace_id, action)

    def decide(
        self,
        root: str,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        dimension: str,
        command: str,
        next_value: str,
        reason_code: str,
        protocol_revision_id: str,
        evidence_revision_ids: tuple[str, ...],
        trace_id: str,
    ) -> CorpusItemRevision:
        for value in (item_id, expected_revision_id, command_id, protocol_revision_id):
            _identity(value)
        _reason(reason_code)
        evidence = _evidence(evidence_revision_ids)
        if (
            dimension not in {"membership", "review", "duplicate", "availability"}
            or not isinstance(command, str)
            or _REASON.fullmatch(command) is None
            or not isinstance(next_value, str)
            or not 1 <= len(next_value) <= 64
        ):
            raise CorpusProblem("corpus-command-invalid")

        def action(repo: CorpusRepository, actor: CorpusActor, intent: str, _path: Path, project_id: str):
            if protocol_revision_id != intent:
                raise CorpusProblem("corpus-protocol-unavailable")
            command_hash = _digest(
                "decide",
                actor,
                command_id,
                projectId=project_id,
                itemId=item_id,
                expectedRevisionId=expected_revision_id,
                dimension=dimension,
                command=command,
                nextValue=next_value,
                reasonCode=reason_code,
                protocolRevisionId=protocol_revision_id,
                evidenceRevisionIds=evidence,
            )

            def build(observed: CorpusItemRevision) -> CorpusDecision:
                current = self._current(observed, project_id, item_id, expected_revision_id)
                previous = {
                    "membership": current.membership,
                    "review": current.review,
                    "duplicate": current.duplicate_of_item_id or "none",
                    "availability": current.availability,
                }[dimension]
                decision = CorpusDecision(
                    decision_id=new_uuid_v7(),
                    project_id=project_id,
                    item_id=item_id,
                    previous_revision_id=current.revision_id,
                    next_revision_id=new_uuid_v7(),
                    dimension=cast(Dimension, dimension),
                    command=command,
                    previous_value=previous,
                    next_value=next_value,
                    previous_decision_revision_id=current.decision_revision_id,
                    actor_id=actor.actor_id,
                    reason_code=reason_code,
                    protocol_revision_id=protocol_revision_id,
                    evidence_revision_ids=evidence,
                    occurred_at=actor.occurred_at,
                )
                apply_decision(current, decision)
                return decision

            return repo.decide(
                item_id,
                expected_revision_id=expected_revision_id,
                command_id=command_id,
                command_sha256=command_hash,
                actor=actor,
                build=build,
            )

        return self._with_authority(root, trace_id, action)

    def add_path(
        self,
        root: str,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        source: SourceAddress,
        reason_code: str,
        protocol_revision_id: str,
        evidence_revision_ids: tuple[str, ...],
        trace_id: str,
    ) -> CorpusItemRevision:
        for value in (item_id, expected_revision_id, command_id, protocol_revision_id):
            _identity(value)
        _reason(reason_code)
        evidence = _evidence(evidence_revision_ids)
        try:
            source = SourceAddress.model_validate(source)
        except ValidationError:
            raise CorpusProblem("corpus-command-invalid") from None

        def action(repo: CorpusRepository, actor: CorpusActor, intent: str, path: Path, project_id: str):
            if protocol_revision_id != intent:
                raise CorpusProblem("corpus-protocol-unavailable")
            prepared, query_revision_id = self._source(path, project_id, source)
            if prepared.source_revision_id not in evidence:
                raise CorpusProblem("corpus-evidence-invalid")
            command_hash = _digest(
                "add-path",
                actor,
                command_id,
                projectId=project_id,
                itemId=item_id,
                expectedRevisionId=expected_revision_id,
                source=prepared.model_dump(mode="json", by_alias=True),
                queryRevisionId=query_revision_id,
                reasonCode=reason_code,
                protocolRevisionId=protocol_revision_id,
                evidenceRevisionIds=evidence,
            )

            def build(observed: CorpusItemRevision) -> tuple[DiscoveryPath, CorpusDecision]:
                current = self._current(observed, project_id, item_id, expected_revision_id)
                discovery = self._path(
                    item_id,
                    prepared,
                    query_revision_id,
                    occurred_at=actor.occurred_at,
                    predecessor_item_revision_id=current.revision_id,
                )
                decision = CorpusDecision(
                    decision_id=new_uuid_v7(),
                    project_id=project_id,
                    item_id=item_id,
                    previous_revision_id=current.revision_id,
                    next_revision_id=new_uuid_v7(),
                    dimension="discovery",
                    command="add-discovery",
                    previous_value=current.discovery_fingerprint,
                    next_value=discovery.path_id,
                    previous_decision_revision_id=current.decision_revision_id,
                    actor_id=actor.actor_id,
                    reason_code=reason_code,
                    protocol_revision_id=protocol_revision_id,
                    evidence_revision_ids=evidence,
                    occurred_at=actor.occurred_at,
                )
                append_discovery_path(current, discovery, decision)
                return discovery, decision

            return repo.add_path(
                item_id,
                expected_revision_id=expected_revision_id,
                command_id=command_id,
                command_sha256=command_hash,
                actor=actor,
                source=prepared,
                build=build,
            )

        return self._with_authority(root, trace_id, action)

    def add_citation_path(
        self,
        root: str,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        citing_work_id: str,
        citing_work_revision_id: str,
        source_assertion_revision_id: str,
        reason_code: str,
        protocol_revision_id: str,
        evidence_revision_ids: tuple[str, ...],
        trace_id: str,
    ) -> CorpusItemRevision:
        """Record a human-attested citation discovery route, not a verified citation fact.

        The repository must verify the exact retained assertion belongs to the
        active citing Work before invoking the builder in its writer transaction.
        """

        for value in (
            item_id,
            expected_revision_id,
            command_id,
            citing_work_id,
            citing_work_revision_id,
            source_assertion_revision_id,
            protocol_revision_id,
        ):
            _identity(value)
        _reason(reason_code)
        evidence = _evidence(evidence_revision_ids)
        if source_assertion_revision_id not in evidence:
            raise CorpusProblem("corpus-evidence-invalid")

        def action(repo: CorpusRepository, actor: CorpusActor, intent: str, _path: Path, project_id: str):
            if protocol_revision_id != intent:
                raise CorpusProblem("corpus-protocol-unavailable")
            command_hash = _digest(
                "add-citation-path",
                actor,
                command_id,
                projectId=project_id,
                itemId=item_id,
                expectedRevisionId=expected_revision_id,
                citingWorkId=citing_work_id,
                citingWorkRevisionId=citing_work_revision_id,
                sourceAssertionRevisionId=source_assertion_revision_id,
                reasonCode=reason_code,
                protocolRevisionId=protocol_revision_id,
                evidenceRevisionIds=evidence,
            )

            def build(observed: CorpusItemRevision) -> tuple[DiscoveryPath, CorpusDecision]:
                current = self._current(observed, project_id, item_id, expected_revision_id)
                discovery = DiscoveryPath(
                    path_id=new_uuid_v7(),
                    project_id=project_id,
                    item_id=item_id,
                    kind="citation",
                    direction="source-to-corpus-item",
                    occurred_at=actor.occurred_at,
                    predecessor_item_revision_id=current.revision_id,
                    source_revision_id=source_assertion_revision_id,
                    context_id=citing_work_id,
                    context_revision_id=citing_work_revision_id,
                    citing_work_revision_id=citing_work_revision_id,
                )
                decision = CorpusDecision(
                    decision_id=new_uuid_v7(),
                    project_id=project_id,
                    item_id=item_id,
                    previous_revision_id=current.revision_id,
                    next_revision_id=new_uuid_v7(),
                    dimension="discovery",
                    command="add-discovery",
                    previous_value=current.discovery_fingerprint,
                    next_value=discovery.path_id,
                    previous_decision_revision_id=current.decision_revision_id,
                    actor_id=actor.actor_id,
                    reason_code=reason_code,
                    protocol_revision_id=protocol_revision_id,
                    evidence_revision_ids=evidence,
                    occurred_at=actor.occurred_at,
                )
                append_discovery_path(current, discovery, decision)
                return discovery, decision

            return repo.add_citation_path(
                item_id,
                expected_revision_id=expected_revision_id,
                command_id=command_id,
                command_sha256=command_hash,
                actor=actor,
                citing_work_id=citing_work_id,
                citing_work_revision_id=citing_work_revision_id,
                source_assertion_revision_id=source_assertion_revision_id,
                build=build,
            )

        return self._with_authority(root, trace_id, action)

    def rebind(
        self,
        root: str,
        item_id: str,
        *,
        expected_revision_id: str,
        command_id: str,
        next_work_id: str,
        next_work_revision_id: str,
        reason_code: str,
        protocol_revision_id: str,
        evidence_revision_ids: tuple[str, ...],
        trace_id: str,
    ) -> CorpusItemRevision:
        for value in (
            item_id,
            expected_revision_id,
            command_id,
            next_work_id,
            next_work_revision_id,
            protocol_revision_id,
        ):
            _identity(value)
        _reason(reason_code)
        evidence = _evidence(evidence_revision_ids)
        if next_work_revision_id not in evidence:
            raise CorpusProblem("corpus-evidence-invalid")

        def action(repo: CorpusRepository, actor: CorpusActor, intent: str, _path: Path, project_id: str):
            if protocol_revision_id != intent:
                raise CorpusProblem("corpus-protocol-unavailable")
            command_hash = _digest(
                "rebind",
                actor,
                command_id,
                projectId=project_id,
                itemId=item_id,
                expectedRevisionId=expected_revision_id,
                nextWorkId=next_work_id,
                nextWorkRevisionId=next_work_revision_id,
                reasonCode=reason_code,
                protocolRevisionId=protocol_revision_id,
                evidenceRevisionIds=evidence,
            )

            def build(observed: CorpusItemRevision) -> CorpusDecision:
                current = self._current(observed, project_id, item_id, expected_revision_id)
                decision = CorpusDecision(
                    decision_id=new_uuid_v7(),
                    project_id=project_id,
                    item_id=item_id,
                    previous_revision_id=current.revision_id,
                    next_revision_id=new_uuid_v7(),
                    dimension="work-reference",
                    command="rebind-work",
                    previous_value=current.work_revision_id,
                    next_value=next_work_revision_id,
                    previous_decision_revision_id=current.decision_revision_id,
                    next_work_id=next_work_id,
                    actor_id=actor.actor_id,
                    reason_code=reason_code,
                    protocol_revision_id=protocol_revision_id,
                    evidence_revision_ids=evidence,
                    occurred_at=actor.occurred_at,
                )
                rebind_work(current, decision)
                return decision

            return repo.rebind(
                item_id,
                expected_revision_id=expected_revision_id,
                command_id=command_id,
                command_sha256=command_hash,
                actor=actor,
                build=build,
            )

        return self._with_authority(root, trace_id, action)

    def inspect(self, root: str, item_id: str, *, trace_id: str) -> CorpusItemRevision:
        _identity(item_id)
        return self._with_authority(
            root,
            trace_id,
            lambda repo, actor, _intent, _path, _project: repo.inspect(item_id, actor=actor),
            require_write=False,
        )

    def history(
        self, root: str, item_id: str, *, trace_id: str
    ) -> tuple[tuple[CorpusItemRevision, tuple[DiscoveryPath, ...], CorpusDecision | None], ...]:
        _identity(item_id)
        return self._with_authority(
            root,
            trace_id,
            lambda repo, actor, _intent, _path, _project: repo.history(item_id, actor=actor),
            require_write=False,
        )
