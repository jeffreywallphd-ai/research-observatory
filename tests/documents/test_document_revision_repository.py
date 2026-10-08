"""Actual SQLCipher/encrypted revisions; explicitly synthetic parser output."""

import hashlib
import json
import sys
import threading
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.document_attachment_repository import LocalParserArtifactStager  # noqa: E402
from research_observatory_core.document_parse_workflow import DocumentParseInput  # noqa: E402
from research_observatory_core.document_revision_repository import LocalDocumentRevisionRepository  # noqa: E402
from research_observatory_core.document_revisions import (  # noqa: E402
    DocumentRevisionAcceptance,
    DocumentRevisionProblem,
)
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.object_store import _object_relative_path  # noqa: E402
from research_observatory_core.parsing.contracts import DocumentIR  # noqa: E402
from research_observatory_core.parsing.requests import ParseSuccess  # noqa: E402
from research_observatory_core.repositories import _SqliteWorkflowQueueRepository  # noqa: E402
from research_observatory_core.storage import open_canonical_database  # noqa: E402
from research_observatory_core.workflow_contracts import workflow_record_sha256  # noqa: E402

from tests.parsing import contract_fixtures, test_protected_parse_source  # noqa: E402
from tests.workflows import test_local_workflow_executor as workflows  # noqa: E402


class DocumentRevisionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.f = test_protected_parse_source.ProtectedParseSourceTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.permit()
        self.database = self.f.fixture.corpus.database
        self.now = self.f.actor.occurred_at
        self.actor = replace(self.f.actor, occurred_at=self.now)
        self.guard = lambda action: self.f.preview.service.in_native_session(
            self.f.preview.root, self.f.source.project_id, self.f.session, action
        )
        self.repository = self.reopen()
        self.queue = _SqliteWorkflowQueueRepository(self.database, self.f.source.project_id)
        self.intent = self.f.preview.service._action(
            self.f.preview.root, lambda binding: self.f.preview.service._intent(binding)
        )

    def reopen(self):
        return LocalDocumentRevisionRepository(
            self.database,
            self.f.source.project_id,
            self.f.fixture.store,
            actor=lambda: self.actor,
            guard=self.guard,
            now=lambda: self.now,
        )

    def parse(self, raw="Synthetic normalized text", *, change=None):
        inputs = DocumentParseInput(
            project_id=self.f.source.project_id,
            command_id=new_uuid_v7(),
            actor_id=self.actor.actor_id,
            session_id=self.f.session,
            source=self.f.source,
            selection=self.f.request.selection,
            intent=self.intent,
            policy_sha256=self.actor.policy_sha256,
        )
        job = self.repository.submit(inputs)
        claim = self.queue.claim_next(
            worker_id=workflows.WORKER_A,
            concurrency_classes=("document",),
            activity_types=("document-parse",),
            now=self.now,
            lease_duration_ms=30_000,
        )
        self.assertEqual(job.job_id, claim.job_id)
        self.queue.start(claim, now=self.now)
        request = inputs.request(claim)
        stager = LocalParserArtifactStager(
            self.database,
            self.f.fixture.store,
            claim=claim,
            request=request,
            actor=lambda: self.actor,
            guard=self.guard,
            now=lambda: self.now,
        )
        receipt = stager(
            request,
            b'{"synthetic-parser-output":true}',
            media_type="application/vnd.research-observatory.text-parser-output+json",
            cancelled=lambda: False,
        )
        value = contract_fixtures.ir(request.binding, raw=raw).model_dump(mode="json", by_alias=True)
        value["rawArtifacts"] = [receipt.model_dump(mode="json", by_alias=True)]
        if change:
            change(value)
        result = ParseSuccess(
            schema_version="1.0", kind="success", binding=request.binding, ir=DocumentIR.model_validate(value)
        )
        retained, marker = self.repository.retain(claim, request, result, stopped=lambda: False)
        self.assertEqual("succeeded", self.queue.get(job.job_id).state)
        self.assertEqual(1, len(marker.outputs))
        return retained

    def command(self, result, *, expected=None):
        return DocumentRevisionAcceptance(
            command_id=new_uuid_v7(),
            result_id=result.result_id,
            expected_current_revision_id=expected or self.f.source.document_revision_id,
            confirmation_sha256=hashlib.sha256(result.model_dump_json(by_alias=True).encode()).hexdigest(),
            decision="accept-structure",
        )

    def counts(self):
        with closing(open_canonical_database(self.database, expected_project_id=self.f.source.project_id)) as db:
            return {
                table: db.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
                for table in (
                    "aggregate_revisions",
                    "document_normalized_revisions",
                    "document_structure_elements",
                    "provenance_events",
                    "outbox_events",
                )
            }

    def test_retention_does_not_advance_source_acceptance_reparse_and_reopen_preserve_ids(self):
        first_result = self.parse()
        self.assertEqual(0, self.counts()["document_normalized_revisions"])
        first = self.repository.accept(self.command(first_result))
        self.assertEqual(self.f.source.document_id, first.document_id)
        self.assertEqual("unverified", first.scholarly_verification)
        second_result = self.parse("Different normalized text")
        second = self.repository.accept(self.command(second_result, expected=first.revision_id))
        self.assertEqual(first.revision_id, second.previous_revision_id)
        self.assertTrue(
            {x.canonical_id for x in first.element_identities}.isdisjoint(
                {x.canonical_id for x in second.element_identities}
            )
        )
        reopened = self.reopen()
        self.assertEqual(first, reopened.read(first.revision_id))
        self.assertEqual(second, reopened.read(second.revision_id))
        self.assertEqual((first.revision_id, second.revision_id), reopened.history(self.f.source.document_id))
        with self.f.fixture.store.open_parse_source(self.f.source, actor=self.actor) as original:
            self.assertEqual(b"Synthetic plain text full text\n", original.read())

    def test_exact_retry_has_no_new_publication_and_changed_command_conflicts(self):
        result = self.parse()
        command = self.command(result)
        accepted = self.repository.accept(command)
        before = self.counts()
        self.assertEqual(accepted, self.reopen().accept(command))
        self.assertEqual(before, self.counts())
        changed = command.model_copy(update={"confirmation_sha256": "0" * 64})
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.accept(changed)
        self.assertEqual(before, self.counts())

    def test_equal_base_has_one_winner_and_partial_retained_result_is_not_accepted(self):
        first_result, second_result = self.parse(), self.parse("Other")
        first_command, second_command = self.command(first_result), self.command(second_result)
        self.repository.accept(first_command)
        before = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.accept(second_command)
        self.assertEqual(before, self.counts())
        partial = self.parse(
            change=lambda value: value["quality"]["warnings"].append(
                {"code": "parser-partial-output", "severity": "warning", "nodeId": None, "detail": "Synthetic partial."}
            )
        )
        before_partial_acceptance = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.accept(self.command(partial))
        self.assertEqual(before_partial_acceptance, self.counts())

    def test_human_current_rights_and_session_are_required_even_for_retry(self):
        result = self.parse()
        command = self.command(result)
        self.repository.accept(command)
        before = self.counts()
        self.actor = replace(self.actor, actor_type="worker")
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.accept(command)
        self.assertEqual(before, self.counts())
        self.actor = replace(self.actor, actor_type="human")
        self.f.permit(derive="denied")
        after_rights_publication = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.repository.accept(command)
        self.assertEqual(after_rights_publication, self.counts())

    def test_publication_failure_rolls_back_decision_head_elements_and_events(self):
        result = self.parse()
        command = self.command(result)
        before = self.counts()
        with (
            patch(
                "research_observatory_core.document_revision_repository._publication_step",
                side_effect=RuntimeError("synthetic-before-commit"),
            ),
            self.assertRaises(DocumentRevisionProblem),
        ):
            self.repository.accept(command)
        self.assertEqual(before, self.counts())
        self.assertIsNotNone(self.repository.accept(command))

    def test_concurrent_equal_base_acceptance_has_exactly_one_durable_winner(self):
        commands = [self.command(self.parse()), self.command(self.parse("Other concurrent content"))]
        barrier = threading.Barrier(2)
        results, failures = [], []

        def accept(command):
            barrier.wait(timeout=5)
            try:
                results.append(self.reopen().accept(command))
            except DocumentRevisionProblem as error:
                failures.append(error.code)

        threads = [threading.Thread(target=accept, args=(command,)) for command in commands]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(1, len(results))
        self.assertEqual(["document-revision-predecessor-changed"], failures)
        self.assertEqual(1, self.counts()["document_normalized_revisions"])

    def test_retained_hierarchy_reference_and_citation_index_survive_reopen(self):
        def rich(value):
            original_binding, receipts = value["binding"], value["rawArtifacts"]
            value.update(contract_fixtures.rich_ir_wire())
            value["binding"], value["rawArtifacts"] = original_binding, receipts
            value["figures"][0]["previewStageId"] = None

        accepted = self.repository.accept(self.command(self.parse(change=rich)))
        self.assertEqual(accepted, self.reopen().read(accepted.revision_id))
        self.assertEqual(
            {"projection", "node", "reference", "citation"}, {item.role for item in accepted.element_identities}
        )
        self.assertEqual("ambiguous", accepted.structure.citations[0].resolution)
        self.assertEqual(2, len(accepted.structure.references))

    def test_corrupt_accepted_ciphertext_denies_read_and_preserves_head(self):
        accepted = self.repository.accept(self.command(self.parse()))
        with closing(open_canonical_database(self.database, expected_project_id=self.f.source.project_id)) as db:
            digest = db.execute(
                "SELECT object_sha256 FROM document_normalized_revisions WHERE revision_id=?", (accepted.revision_id,)
            ).fetchone()[0]
        path = self.f.fixture.project_root / "objects" / _object_relative_path(self.f.source.project_id, digest)
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        before = self.counts()
        with self.assertRaises(DocumentRevisionProblem):
            self.reopen().read(accepted.revision_id)
        self.assertEqual(before, self.counts())

    def test_changed_complete_workflow_definition_is_denied_even_with_valid_hashes(self):
        claims = []
        original = _SqliteWorkflowQueueRepository.claim_next

        def observed(queue, *args, **kwargs):
            claim = original(queue, *args, **kwargs)
            claims.append(claim)
            return claim

        with patch.object(_SqliteWorkflowQueueRepository, "claim_next", observed):
            self.parse()
        claim = claims[0]
        authority = self.repository.queue.authority(claim.job_id)
        self.assertIsNotNone(self.repository.claim_input(claim))
        definition = json.loads(authority.definition_json)
        snapshot = json.loads(authority.snapshot_json)
        definition["steps"][0]["permissions"]["network"] = "policy-controlled"
        snapshot["definition"]["contentHash"] = workflow_record_sha256(definition)
        altered = replace(
            authority,
            definition_json=json.dumps(definition, sort_keys=True, separators=(",", ":")),
            snapshot_json=json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
            definition_record_sha256=workflow_record_sha256(definition),
            snapshot_record_sha256=workflow_record_sha256(snapshot),
        )
        with patch.object(self.repository.queue, "authority", return_value=altered), self.assertRaises(ValueError):
            self.repository.claim_input(claim)


if __name__ == "__main__":
    unittest.main(verbosity=2)
