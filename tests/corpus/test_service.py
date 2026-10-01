"""Core corpus trust boundary denies untrusted commands before publication."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from research_observatory_core.corpus.membership import (
    CorpusDecision,
    CorpusItemRevision,
    CorpusProblem,
    DiscoveryPath,
    append_discovery_path,
    apply_decision,
    rebind_work,
)
from research_observatory_core.corpus_service import CorpusService
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ports.corpus import CorpusActor
from research_observatory_core.ports.reconciliation import (
    ReconciliationConnectorSourceService,
    ReconciliationSourceService,
)
from research_observatory_core.ports.repositories import IntentProjectIdentity
from research_observatory_core.privacy import ProjectPrivacyService
from research_observatory_core.projects import ProjectLifecycleProblem, ProjectLifecycleService
from research_observatory_core.reconciliation.contracts import SourceAddress, SourceAssertion

ROOT = Path("C:/synthetic-corpus-project")
PROJECT = "02e2e404-5b49-438e-9b59-ed562626b658"
OTHER_PROJECT = "02e2e404-5b49-438e-9b59-ed562626b659"
DOMAIN_PROJECT = "01a0f503-65f9-763e-af00-aacc9aca6494"
INTENT = "01a0f503-663c-77d1-b0a7-445355a0d8ab"
ACTOR = "01a0f503-6680-7ab3-a4ab-b29f2fe10c31"
WORK = "01a0f503-66b0-731c-8e38-3266c225a178"
WORK_REVISION = "01a0f503-66b1-70aa-98cb-578709242ce8"
NEXT_WORK = "01a0f503-66b2-7443-9caa-46f39ec00f23"
NEXT_WORK_REVISION = "01a0f503-66b3-7040-a811-bc2673c290b0"
SOURCE = "01a0f503-66b4-7d41-aa2c-37d912c84004"
SECOND_SOURCE = "01a0f503-66b5-72f6-8d29-e2d56fecad94"
COMMAND = "01a0f503-66b7-77ef-a2e1-179131d50cd8"
SECOND_COMMAND = "01a0f503-66b8-7c94-b890-31202a63db20"
THIRD_COMMAND = "01a0f503-66b9-75b2-9e29-e435120b0fb6"
FOURTH_COMMAND = "01a0f503-66ba-7d58-867e-033918829f64"
TRACE = "1" * 32
NOW = "2026-09-30T20:00:00.000Z"

type CorpusHistory = tuple[tuple[CorpusItemRevision, tuple[DiscoveryPath, ...], CorpusDecision | None], ...]


def required[T](value: T | None) -> T:
    if value is None:
        raise AssertionError("expected repository output")
    return value


def address(*, connector: bool = False, second: bool = False) -> SourceAddress:
    return SourceAddress(
        kind="connector-record" if connector else "import-member",
        context_id="01a0f503-66bb-7d58-867e-033918829f64",
        revision_id="01a0f503-66bc-7d58-867e-033918829f64",
        ordinal=0 if connector else (2 if second else 1),
        record_key=None if connector else ("b" if second else "a") * 64,
    )


def source_assertion(value: SourceAddress, *, source_id: str = SOURCE, permitted: bool = True) -> SourceAssertion:
    permission = ImportPermission(value="permitted", basis="researcher-confirmed") if permitted else ImportPermission()
    return SourceAssertion(
        project_id=PROJECT,
        address=value,
        source_revision_id=source_id,
        provider="local-import" if value.kind == "import-member" else "synthetic-connector",
        identifiers=(),
        fields=(),
        rights=ImportRights(store=permission, inspect=permission, derive=permission, index=permission),
        source_sha256="c" * 64,
    )


class FakeProjects:
    def __init__(self) -> None:
        self.calls = 0
        self.writable = True

    def perform_open_project_action(self, *, root, require_write, action):
        self.calls += 1
        assert root == str(ROOT)
        if require_write and not self.writable:
            raise ProjectLifecycleProblem(409, "RO-CORE-PROJECT-READ-ONLY", "Read-only", "Denied", "Retry")
        return action(ROOT, PROJECT)


class FakeSources:
    def __init__(self, assertion: SourceAssertion) -> None:
        self.assertion = assertion
        self.calls = 0

    def reconciliation_source(self, root: str, source: SourceAddress) -> SourceAssertion:
        self.calls += 1
        assert root == str(ROOT)
        return self.assertion


class FakeRepository:
    def __init__(self) -> None:
        self.items: dict[str, CorpusItemRevision] = {}
        self.commands: dict[str, tuple[str, CorpusItemRevision]] = {}
        self.publications = 0
        self.builders = 0
        self.last_actor: CorpusActor | None = None
        self.last_source: SourceAssertion | None = None
        self.last_path: DiscoveryPath | None = None
        self.last_decision: CorpusDecision | None = None
        self.history_result: CorpusHistory = ()
        self.history_calls = 0
        self.citation_members = {(NEXT_WORK, NEXT_WORK_REVISION, SECOND_SOURCE)}
        self.last_citation_path: DiscoveryPath | None = None
        self.last_citation_decision: CorpusDecision | None = None

    def _replay(self, command_id, command_sha256):
        if command_id not in self.commands:
            return None
        digest, outcome = self.commands[command_id]
        if digest != command_sha256:
            raise CorpusProblem("corpus-command-conflict")
        return outcome

    def _publish(self, command_id, digest, result):
        self.items[result.item_id] = result
        self.commands[command_id] = (digest, result)
        self.publications += 1
        return result

    def create(self, *, command_id, command_sha256, actor, source, build):
        self.last_actor, self.last_source = actor, source
        replay = self._replay(command_id, command_sha256)
        if replay is not None:
            return replay
        self.builders += 1
        item, path = build()
        assert source.source_revision_id == path.source_revision_id
        self.last_path = path
        return self._publish(command_id, command_sha256, item)

    def create_citation(
        self,
        *,
        command_id,
        command_sha256,
        actor,
        work_id,
        work_revision_id,
        citing_work_id,
        citing_work_revision_id,
        source_assertion_revision_id,
        build,
    ):
        self.last_actor = actor
        replay = self._replay(command_id, command_sha256)
        if replay is not None:
            return replay
        if (citing_work_id, citing_work_revision_id, source_assertion_revision_id) not in self.citation_members:
            raise CorpusProblem("corpus-citation-source-invalid")
        if (work_id, work_revision_id) != (WORK, WORK_REVISION):
            raise CorpusProblem("corpus-work-unavailable")
        self.builders += 1
        item, path = build()
        assert path.kind == "citation" and path.source_revision_id == source_assertion_revision_id
        assert (path.context_id, path.context_revision_id) == (citing_work_id, citing_work_revision_id)
        assert path.predecessor_item_revision_id is None
        self.last_path = path
        return self._publish(command_id, command_sha256, item)

    def decide(self, item_id, *, expected_revision_id, command_id, command_sha256, actor, build):
        self.last_actor = actor
        replay = self._replay(command_id, command_sha256)
        if replay is not None:
            return replay
        current = self.items[item_id]
        assert current.revision_id == expected_revision_id
        self.builders += 1
        decision = build(current)
        self.last_decision = decision
        return self._publish(command_id, command_sha256, apply_decision(current, decision))

    def add_path(self, item_id, *, expected_revision_id, command_id, command_sha256, actor, source, build):
        self.last_actor, self.last_source = actor, source
        replay = self._replay(command_id, command_sha256)
        if replay is not None:
            return replay
        current = self.items[item_id]
        assert current.revision_id == expected_revision_id
        self.builders += 1
        path, decision = build(current)
        assert path.source_revision_id == source.source_revision_id
        self.last_path = path
        return self._publish(command_id, command_sha256, append_discovery_path(current, path, decision))

    def add_citation_path(
        self,
        item_id,
        *,
        expected_revision_id,
        command_id,
        command_sha256,
        actor,
        citing_work_id,
        citing_work_revision_id,
        source_assertion_revision_id,
        build,
    ):
        self.last_actor = actor
        replay = self._replay(command_id, command_sha256)
        if replay is not None:
            return replay
        current = self.items[item_id]
        if current.revision_id != expected_revision_id:
            raise CorpusProblem("corpus-predecessor-stale")
        if (citing_work_id, citing_work_revision_id, source_assertion_revision_id) not in self.citation_members:
            raise CorpusProblem("corpus-citation-source-invalid")
        self.builders += 1
        path, decision = build(current)
        assert path.kind == "citation"
        assert (path.context_id, path.context_revision_id, path.citing_work_revision_id) == (
            citing_work_id,
            citing_work_revision_id,
            citing_work_revision_id,
        )
        assert path.source_revision_id == source_assertion_revision_id
        assert source_assertion_revision_id in decision.evidence_revision_ids
        self.last_citation_path, self.last_citation_decision = path, decision
        return self._publish(command_id, command_sha256, append_discovery_path(current, path, decision))

    def rebind(self, item_id, *, expected_revision_id, command_id, command_sha256, actor, build):
        self.last_actor = actor
        replay = self._replay(command_id, command_sha256)
        if replay is not None:
            return replay
        current = self.items[item_id]
        assert current.revision_id == expected_revision_id
        self.builders += 1
        decision = build(current)
        return self._publish(command_id, command_sha256, rebind_work(current, decision))

    def inspect(self, item_id, *, actor):
        self.last_actor = actor
        return self.items[item_id]

    def history(self, item_id, *, actor):
        self.last_actor = actor
        self.history_calls += 1
        return self.history_result


@dataclass
class ServiceFixture:
    projects: FakeProjects
    sources: FakeSources
    repository: FakeRepository
    policy: SimpleNamespace
    current_intent: dict
    service: CorpusService


def fixture() -> ServiceFixture:
    projects = FakeProjects()
    sources = FakeSources(source_assertion(address()))
    repository = FakeRepository()
    policy = SimpleNamespace(
        project_id=PROJECT,
        model_dump=lambda **_: {"projectId": PROJECT, "networkPolicy": "offline", "revision": 0},
    )
    current_intent = {
        "status": "accepted",
        "projectId": DOMAIN_PROJECT,
        "revisionId": INTENT,
        "revisionContentHash": "sha256:" + "d" * 64,
    }
    intents = SimpleNamespace(
        project_identity=lambda: IntentProjectIdentity(PROJECT, DOMAIN_PROJECT),
    )
    service = CorpusService(
        cast(ProjectLifecycleService, projects),
        cast(ProjectPrivacyService, SimpleNamespace(get=lambda _root: policy)),
        imports=cast(ReconciliationSourceService, sources),
        connectors=cast(ReconciliationConnectorSourceService, sources),
        repository_factory=lambda _path, _project: repository,
        intent_factory=lambda _path, _project: intents,
        actor_id=ACTOR,
        now=lambda: NOW,
    )
    return ServiceFixture(projects, sources, repository, policy, current_intent, service)


class CorpusServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.f = fixture()
        patcher = patch(
            "research_observatory_core.corpus_service.validated_workflow_authority",
            side_effect=lambda _repo, **_: (None, (self.f.current_intent,), (), ()),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def create(self, *, command_id=COMMAND, source=None):
        return self.f.service.create(
            str(ROOT),
            command_id=command_id,
            work_id=WORK,
            work_revision_id=WORK_REVISION,
            source=source or address(),
            trace_id=TRACE,
        )

    def test_create_mints_core_ids_and_exact_retry_uses_same_result_without_builder(self) -> None:
        first = self.create()
        self.assertEqual(("candidate", "pending"), first.conditions)
        self.assertNotIn(first.item_id, {WORK, WORK_REVISION, COMMAND})
        self.assertEqual(1, self.f.repository.builders)
        self.f.service._now = lambda: "2026-10-01T20:00:00.000Z"
        self.assertEqual(
            first,
            self.f.service.create(
                str(ROOT),
                command_id=COMMAND,
                work_id=WORK,
                work_revision_id=WORK_REVISION,
                source=address(),
                trace_id="2" * 32,
            ),
        )
        self.assertEqual(1, self.f.repository.builders)
        self.assertEqual(1, self.f.repository.publications)
        actor = required(self.f.repository.last_actor)
        source = required(self.f.repository.last_source)
        self.assertEqual(INTENT, actor.intent_revision_id)
        self.assertEqual(ACTOR, actor.actor_id)
        self.assertEqual(SOURCE, source.source_revision_id)

    def test_connector_discovery_uses_only_the_trusted_resolved_query_revision(self) -> None:
        connector_address = address(connector=True)
        self.f.sources.assertion = source_assertion(connector_address, source_id=connector_address.revision_id)
        seen = []

        def resolve(root, requested, prepared):
            seen.append((root, requested, prepared))
            return connector_address.context_id

        self.f.service._connector_query = resolve
        created = self.create(source=connector_address)
        path = required(self.f.repository.last_path)
        self.assertEqual("candidate", created.membership)
        self.assertEqual(
            (connector_address.context_id, connector_address.revision_id),
            (path.query_revision_id, path.context_revision_id),
        )
        self.assertEqual([(str(ROOT), connector_address, self.f.sources.assertion)], seen)

        self.f.service._connector_query = lambda *_args: WORK
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-conflict"):
            self.create(source=connector_address)

    def test_citation_can_be_the_initial_human_attested_discovery_route(self) -> None:
        params = dict(
            command_id=COMMAND,
            work_id=WORK,
            work_revision_id=WORK_REVISION,
            citing_work_id=NEXT_WORK,
            citing_work_revision_id=NEXT_WORK_REVISION,
            source_assertion_revision_id=SECOND_SOURCE,
        )
        created = self.f.service.create_citation(str(ROOT), trace_id=TRACE, **params)
        path = required(self.f.repository.last_path)
        self.assertEqual(("candidate", "pending"), created.conditions)
        self.assertEqual(
            ("citation", "source-to-corpus-item", NOW, None, NEXT_WORK, SECOND_SOURCE),
            (
                path.kind,
                path.direction,
                path.occurred_at,
                path.predecessor_item_revision_id,
                path.context_id,
                path.source_revision_id,
            ),
        )
        self.f.service._now = lambda: "2026-10-01T20:00:00.000Z"
        self.assertEqual(created, self.f.service.create_citation(str(ROOT), trace_id="2" * 32, **params))
        self.assertEqual(1, self.f.repository.builders)
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-conflict"):
            self.f.service.create_citation(
                str(ROOT),
                trace_id=TRACE,
                **(params | {"source_assertion_revision_id": SOURCE}),
            )

    def test_history_routes_oldest_first_through_current_authority(self) -> None:
        created = self.create()
        first_path = required(self.f.repository.last_path)
        included = self.f.service.decide(
            str(ROOT),
            created.item_id,
            expected_revision_id=created.revision_id,
            command_id=SECOND_COMMAND,
            dimension="membership",
            command="include",
            next_value="included",
            reason_code="criterion-met",
            protocol_revision_id=INTENT,
            evidence_revision_ids=(SOURCE,),
            trace_id=TRACE,
        )
        decision = self.f.repository.last_decision
        expected = ((created, (first_path,), None), (included, (first_path,), decision))
        self.f.repository.history_result = expected
        self.assertEqual(expected, self.f.service.history(str(ROOT), created.item_id, trace_id=TRACE))
        self.assertEqual(1, self.f.repository.history_calls)
        actor = required(self.f.repository.last_actor)
        self.assertEqual(ACTOR, actor.actor_id)
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-invalid"):
            self.f.service.history(str(ROOT), "not-an-id", trace_id=TRACE)
        self.f.current_intent["status"] = "draft"
        with self.assertRaisesRegex(CorpusProblem, "corpus-intent-unavailable"):
            self.f.service.history(str(ROOT), created.item_id, trace_id=TRACE)
        self.assertEqual(1, self.f.repository.history_calls)

    def test_decide_add_path_and_rebind_stamp_trusted_actor_protocol_and_predecessor(self) -> None:
        created = self.create()
        entry_path = required(self.f.repository.last_path)
        self.assertEqual(
            ("source-to-corpus-item", NOW, None),
            (entry_path.direction, entry_path.occurred_at, entry_path.predecessor_item_revision_id),
        )
        included = self.f.service.decide(
            str(ROOT),
            created.item_id,
            expected_revision_id=created.revision_id,
            command_id=SECOND_COMMAND,
            dimension="membership",
            command="include",
            next_value="included",
            reason_code="criterion-met",
            protocol_revision_id=INTENT,
            evidence_revision_ids=(SOURCE,),
            trace_id=TRACE,
        )
        self.assertEqual("included", included.membership)
        self.assertEqual(created.revision_id, included.previous_revision_id)
        self.assertEqual(included, self.f.service.inspect(str(ROOT), included.item_id, trace_id=TRACE))
        self.f.sources.assertion = source_assertion(address(second=True), source_id=SECOND_SOURCE)
        added = self.f.service.add_path(
            str(ROOT),
            included.item_id,
            expected_revision_id=included.revision_id,
            command_id=THIRD_COMMAND,
            source=address(second=True),
            reason_code="new-import",
            protocol_revision_id=INTENT,
            evidence_revision_ids=(SECOND_SOURCE,),
            trace_id=TRACE,
        )
        added_path = required(self.f.repository.last_path)
        self.assertEqual(
            ("source-to-corpus-item", NOW, included.revision_id),
            (added_path.direction, added_path.occurred_at, added_path.predecessor_item_revision_id),
        )
        self.assertEqual(2, len(added.discovery_path_ids))
        rebound = self.f.service.rebind(
            str(ROOT),
            added.item_id,
            expected_revision_id=added.revision_id,
            command_id=FOURTH_COMMAND,
            next_work_id=NEXT_WORK,
            next_work_revision_id=NEXT_WORK_REVISION,
            reason_code="work-split",
            protocol_revision_id=INTENT,
            evidence_revision_ids=(NEXT_WORK_REVISION,),
            trace_id=TRACE,
        )
        self.assertEqual((NEXT_WORK, NEXT_WORK_REVISION), (rebound.work_id, rebound.work_revision_id))
        self.assertEqual(4, self.f.repository.publications)

    def test_changed_command_with_same_retry_id_conflicts_without_new_ids(self) -> None:
        created = self.create()
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-conflict"):
            self.f.service.create(
                str(ROOT),
                command_id=COMMAND,
                work_id=NEXT_WORK,
                work_revision_id=WORK_REVISION,
                source=address(),
                trace_id=TRACE,
            )
        self.assertEqual(created, self.f.repository.items[created.item_id])
        self.assertEqual(1, self.f.repository.builders)

    def test_human_attested_citation_path_uses_exact_retained_work_member_and_replays(self) -> None:
        created = self.create()
        source_reads = self.f.sources.calls
        added = self.f.service.add_citation_path(
            str(ROOT),
            created.item_id,
            expected_revision_id=created.revision_id,
            command_id=SECOND_COMMAND,
            citing_work_id=NEXT_WORK,
            citing_work_revision_id=NEXT_WORK_REVISION,
            source_assertion_revision_id=SECOND_SOURCE,
            reason_code="human-citation-attestation",
            protocol_revision_id=INTENT,
            evidence_revision_ids=(SECOND_SOURCE,),
            trace_id=TRACE,
        )
        path = required(self.f.repository.last_citation_path)
        decision = required(self.f.repository.last_citation_decision)
        self.assertEqual("citation", path.kind)
        self.assertEqual(
            ("source-to-corpus-item", NOW, created.revision_id),
            (path.direction, path.occurred_at, path.predecessor_item_revision_id),
        )
        self.assertEqual(SECOND_SOURCE, path.source_revision_id)
        self.assertEqual(
            (NEXT_WORK, NEXT_WORK_REVISION, NEXT_WORK_REVISION),
            (path.context_id, path.context_revision_id, path.citing_work_revision_id),
        )
        self.assertEqual(("discovery", "add-discovery"), (decision.dimension, decision.command))
        self.assertEqual(
            (ACTOR, INTENT, (SECOND_SOURCE,)),
            (decision.actor_id, decision.protocol_revision_id, decision.evidence_revision_ids),
        )
        self.assertEqual(created.revision_id, added.previous_revision_id)
        self.assertEqual(2, len(added.discovery_path_ids))
        self.assertEqual(source_reads, self.f.sources.calls)
        self.f.service._now = lambda: "2026-10-01T20:00:00.000Z"
        self.assertEqual(
            added,
            self.f.service.add_citation_path(
                str(ROOT),
                created.item_id,
                expected_revision_id=created.revision_id,
                command_id=SECOND_COMMAND,
                citing_work_id=NEXT_WORK,
                citing_work_revision_id=NEXT_WORK_REVISION,
                source_assertion_revision_id=SECOND_SOURCE,
                reason_code="human-citation-attestation",
                protocol_revision_id=INTENT,
                evidence_revision_ids=(SECOND_SOURCE,),
                trace_id="2" * 32,
            ),
        )
        self.assertEqual(2, self.f.repository.builders)
        self.assertEqual(2, self.f.repository.publications)

    def test_citation_denies_unbound_assertion_protocol_and_stale_target(self) -> None:
        created = self.create()
        kwargs = dict(
            expected_revision_id=created.revision_id,
            command_id=SECOND_COMMAND,
            citing_work_id=NEXT_WORK,
            citing_work_revision_id=NEXT_WORK_REVISION,
            source_assertion_revision_id=SECOND_SOURCE,
            reason_code="human-citation-attestation",
            protocol_revision_id=INTENT,
            evidence_revision_ids=(SECOND_SOURCE,),
            trace_id=TRACE,
        )
        with self.assertRaisesRegex(CorpusProblem, "corpus-evidence-invalid"):
            self.f.service.add_citation_path(
                str(ROOT), created.item_id, **(kwargs | {"evidence_revision_ids": (SOURCE,)})
            )
        with self.assertRaisesRegex(CorpusProblem, "corpus-protocol-unavailable"):
            self.f.service.add_citation_path(
                str(ROOT), created.item_id, **(kwargs | {"protocol_revision_id": WORK_REVISION})
            )
        with self.assertRaisesRegex(CorpusProblem, "corpus-citation-source-invalid"):
            self.f.service.add_citation_path(
                str(ROOT),
                created.item_id,
                **(kwargs | {"source_assertion_revision_id": SOURCE, "evidence_revision_ids": (SOURCE,)}),
            )
        with self.assertRaisesRegex(CorpusProblem, "corpus-predecessor-stale"):
            self.f.service.add_citation_path(
                str(ROOT), created.item_id, **(kwargs | {"expected_revision_id": WORK_REVISION})
            )
        self.assertEqual(1, self.f.repository.publications)
        self.assertEqual(1, self.f.repository.builders)

    def test_changed_current_policy_conflicts_with_exact_retry(self) -> None:
        created = self.create()
        self.f.policy.model_dump = lambda **_: {"projectId": PROJECT, "networkPolicy": "offline", "revision": 1}
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-conflict"):
            self.create()
        self.assertEqual(created, self.f.repository.items[created.item_id])
        self.assertEqual(1, self.f.repository.builders)

    def test_read_only_intent_policy_and_cross_project_source_deny_before_write(self) -> None:
        self.f.projects.writable = False
        with self.assertRaisesRegex(CorpusProblem, "corpus-authority-unavailable"):
            self.create()
        self.f.projects.writable = True
        self.f.current_intent["status"] = "draft"
        with self.assertRaisesRegex(CorpusProblem, "corpus-intent-unavailable"):
            self.create()
        self.f.current_intent["status"] = "accepted"
        self.f.policy.project_id = OTHER_PROJECT
        with self.assertRaisesRegex(CorpusProblem, "corpus-policy-unavailable"):
            self.create()
        self.f.policy.project_id = PROJECT
        self.f.sources.assertion = self.f.sources.assertion.model_copy(update={"project_id": OTHER_PROJECT})
        with self.assertRaisesRegex(CorpusProblem, "corpus-source-mismatch"):
            self.create()
        self.assertEqual(0, self.f.repository.publications)

    def test_read_only_project_can_inspect_typed_history_without_write(self) -> None:
        created = self.create()
        path = required(self.f.repository.last_path)
        self.f.repository.history_result = ((created, (path,), None),)
        self.f.projects.writable = False
        self.assertEqual(created, self.f.service.inspect(str(ROOT), created.item_id, trace_id=TRACE))
        self.assertEqual(
            ((created, (path,), None),), self.f.service.history(str(ROOT), created.item_id, trace_id=TRACE)
        )
        with self.assertRaisesRegex(CorpusProblem, "corpus-authority-unavailable"):
            self.f.service.decide(
                str(ROOT),
                created.item_id,
                expected_revision_id=created.revision_id,
                command_id=SECOND_COMMAND,
                dimension="membership",
                command="include",
                next_value="included",
                reason_code="criterion-met",
                protocol_revision_id=INTENT,
                evidence_revision_ids=(SOURCE,),
                trace_id=TRACE,
            )

    def test_revoked_source_and_unsupported_connector_deny_before_write(self) -> None:
        self.f.sources.assertion = source_assertion(address(), permitted=False)
        with self.assertRaisesRegex(CorpusProblem, "corpus-rights-denied"):
            self.create()
        self.assertEqual(0, self.f.repository.publications)
        self.f.sources.assertion = source_assertion(address(connector=True))
        before = self.f.sources.calls
        with self.assertRaisesRegex(CorpusProblem, "corpus-connector-query-unavailable"):
            self.create(source=address(connector=True))
        self.assertEqual(before, self.f.sources.calls)
        self.assertEqual(0, self.f.repository.publications)

    def test_malformed_ids_and_unaccepted_protocol_deny_content_free(self) -> None:
        before = self.f.projects.calls
        with self.assertRaisesRegex(CorpusProblem, "corpus-command-invalid"):
            self.f.service.create(
                str(ROOT),
                command_id="not-an-id",
                work_id=WORK,
                work_revision_id=WORK_REVISION,
                source=address(),
                trace_id=TRACE,
            )
        self.assertEqual(before, self.f.projects.calls)
        created = self.create()
        with self.assertRaisesRegex(CorpusProblem, "corpus-protocol-unavailable"):
            self.f.service.decide(
                str(ROOT),
                created.item_id,
                expected_revision_id=created.revision_id,
                command_id=SECOND_COMMAND,
                dimension="membership",
                command="include",
                next_value="included",
                reason_code="criterion-met",
                protocol_revision_id=NEXT_WORK_REVISION,
                evidence_revision_ids=(SOURCE,),
                trace_id=TRACE,
            )
        self.assertEqual(1, self.f.repository.publications)
