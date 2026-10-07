"""Actual SQLCipher/encrypted reads; parser is an explicitly synthetic port double."""

import json
import sys
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

import sqlcipher3.dbapi2 as sqlcipher  # type: ignore[import-untyped]  # noqa: E402
from research_observatory_core import storage  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.parsing.contracts import (  # noqa: E402
    AcquisitionOrigin,
    LocalOrigin,
    ParseAttempt,
    ParseBinding,
)
from research_observatory_core.parsing.pipeline import stage_parse  # noqa: E402
from research_observatory_core.parsing.requests import ParseRequest, ParseSuccess  # noqa: E402
from research_observatory_core.parsing.selection import (  # noqa: E402
    ParserRegistry,
    RegisteredParser,
    SelectionSource,
    select_parser,
    selection_sha256,
)
from research_observatory_core.parsing.source import LocalProtectedParseSource, source_identity  # noqa: E402
from research_observatory_core.ports.object_store import ObjectAccessDenied  # noqa: E402
from research_observatory_core.ports.parsing import AuthenticatedParseDelivery, ParseSourceObjectStore  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402

from tests.database_key_fixtures import InMemoryDatabaseKeyProvider  # noqa: E402
from tests.documents import test_local_attachment as attachment_fixtures  # noqa: E402
from tests.documents import test_oa_acquisition as acquisition_fixtures  # noqa: E402
from tests.parsing.contract_fixtures import descriptor, ir  # noqa: E402


class ProtectedParseSourceTests(unittest.TestCase):
    def setUp(self):
        f = self.fixture = attachment_fixtures.LocalAttachmentServiceTests(methodName="runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        if self._testMethodName == "test_deduplicated_ciphertext_origin_is_not_copy_authority":
            prior_command = replace(
                attachment_fixtures.AttachmentStagingTests.command(),
                media_type="text/plain",
                creation_source="connector-acquisition",
            )
            f.store.put(BytesIO(b"Synthetic plain text full text\n"), prior_command)
        candidate = self.candidate = f.stage()
        policy = f.publish_right(candidate, inspect=True)
        self.policy = policy
        self.attachment = f.service.commit(
            candidate.candidate_id,
            confirmation_sha256=candidate.candidate_sha256,
            command_id=new_uuid_v7(),
            actor=f.corpus.actor,
        )
        self.source = source_identity(self.attachment, candidate, LocalOrigin(kind="local-import"))
        self.actor = f.corpus.actor
        self.preview = f.corpus._fixture.fixture.fixture.fixture.fixture
        self.session = self.preview.service.native_context(self.preview.root, candidate.project_id)
        self._protect_database()

        def guard(action):
            return self.preview.service.in_native_session(
                self.preview.root, self.source.project_id, self.session, action
            )

        self.sources = LocalProtectedParseSource(f.store, guard=guard)
        producer = descriptor("ro-native-text", ("plain-text",))
        selection = select_parser(
            (SelectionSource(self.source, "available", "primary"),),
            ParserRegistry((RegisteredParser(producer, "available"),)),
            primary_attachment_id=self.source.attachment_id,
        )
        self.request = ParseRequest(
            schema_version="1.0",
            selection=selection,
            binding=ParseBinding(
                source=self.source,
                producer=producer,
                selection_sha256=selection_sha256(selection),
                attempt=ParseAttempt(
                    job_id=new_uuid_v7(), attempt_id=new_uuid_v7(), activity_version="document-parse-1"
                ),
            ),
        )
        self.called = 0
        self.after_read = lambda: None
        self.stopped = False
        owner = self

        class Parser:
            def parse(self, request, stream, *, cancelled):
                owner.called += 1
                raw = stream.read().decode("utf-8")
                owner.assertEqual("Synthetic plain text full text\n", raw)
                owner.assertFalse(hasattr(stream, "write"))
                owner.assertFalse(hasattr(stream, "name"))
                owner.after_read()
                value = ir(request.binding, raw=raw)
                wire = (
                    ParseSuccess(schema_version="1.0", kind="success", binding=request.binding, ir=value)
                    .model_dump_json(by_alias=True)
                    .encode()
                )
                return AuthenticatedParseDelivery(
                    wire,
                    request.binding.producer,
                    request.binding.attempt.job_id,
                    request.binding.attempt.attempt_id,
                    (),
                )

        self.parser = Parser()

    def _protect_database(self):
        database = self.fixture.corpus.database
        keys = InMemoryDatabaseKeyProvider()
        with keys.active_key(self.source.project_id, create=True) as lease:
            material = lease.use(bytes)
        protected = database.with_name("protected-parse-fixture.sqlite3")
        source = sqlcipher.connect(database.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            source.execute("ATTACH DATABASE ? AS protected KEY ?", (str(protected), "x'" + material.hex() + "'"))
            source.execute("SELECT sqlcipher_export('protected')").fetchone()
            source.execute(f"PRAGMA protected.application_id={storage.APPLICATION_ID}")
            source.execute(f"PRAGMA protected.user_version={storage.DATABASE_SCHEMA_VERSION}")
            self.assertEqual("wal", source.execute("PRAGMA protected.journal_mode=WAL").fetchone()[0])
            source.execute("DETACH DATABASE protected")
        finally:
            source.close()
        database.unlink()
        for suffix in ("-wal", "-shm"):
            database.with_name(database.name + suffix).unlink(missing_ok=True)
        protected.replace(database)
        with storage._DATABASE_PROTECTION_LOCK:
            previous = storage._DATABASE_PROTECTION
        storage.configure_protected_database_provider(keys)

        def restore():
            with storage._DATABASE_PROTECTION_LOCK:
                storage._DATABASE_PROTECTION = previous

        self.addCleanup(restore)
        self.assertNotEqual(b"SQLite format 3\x00", database.read_bytes()[:16])

    def permit(self, derive="permitted"):
        self.policy = self.fixture.rights.publish_draft(
            self.candidate.rights_subject,
            tuple(
                RightsPermissionDraft(
                    use=RightsUse(
                        action=action,
                        purpose="document-attachment" if action == "store" else "document-analysis",
                        destination_kind="local-project",
                    ),
                    value=derive if action == "derive" else "permitted",
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    evidence_revision_ids=(self.source.source_assertion_revision_id,),
                    license_observation_revision_id=None,
                    entitlement_revision_id=None,
                    expires_at=None,
                )
                for action in ("store", "inspect", "derive")
            ),
            self.policy.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="5" * 64,
            actor=self.actor,
        )

    def canonical(self):
        with storage.open_canonical_database(
            self.fixture.corpus.database, expected_project_id=self.source.project_id
        ) as db:
            return tuple(tuple(row) for row in db.execute("SELECT * FROM documents ORDER BY revision_id").fetchall())

    def execute(self, request=None, actor=None):
        return stage_parse(
            request or self.request,
            self.parser,
            self.sources,
            actor=actor or self.actor,
            cancelled=lambda: self.stopped,
        )

    def test_inspect_does_not_grant_derive_and_success_uses_exact_encrypted_copy(self):
        before = self.canonical()
        denied = self.execute()
        self.assertEqual("failure", denied.kind)
        self.assertEqual(0, self.called)
        self.assertFalse(hasattr(denied, "ir"))
        self.permit()
        result = self.execute()
        self.assertEqual("success", result.kind)
        self.assertEqual(self.source, result.ir.binding.source)
        self.assertEqual(before, self.canonical())
        object_files = [path for path in (self.fixture.project_root / "objects").rglob("*") if path.is_file()]
        self.assertTrue(object_files)
        self.assertTrue(all(b"Synthetic plain text full text" not in path.read_bytes() for path in object_files))
        self.assertEqual(1, self.called)

    def test_deduplicated_ciphertext_origin_is_not_copy_authority(self):
        with storage.open_canonical_database(
            self.fixture.corpus.database, expected_project_id=self.source.project_id
        ) as db:
            creator = db.execute(
                "SELECT creation_source FROM object_records WHERE object_sha256=?", (self.source.object_sha256,)
            ).fetchone()[0]
        self.assertEqual("connector-acquisition", creator)
        self.assertEqual("local-import", self.source.provenance.kind)
        self.assertEqual("failure", self.execute().kind)
        self.assertEqual(0, self.called)
        self.permit()
        before = self.canonical()
        result = self.execute()
        self.assertEqual("success", result.kind)
        self.assertEqual(before, self.canonical())
        self.assertEqual(1, self.called)

    def test_derive_change_between_selection_and_read_denies_before_execution(self):
        self.permit()
        self.permit(derive="denied")
        before = self.canonical()
        self.assertEqual("failure", self.execute().kind)
        self.assertEqual(0, self.called)
        self.assertEqual(before, self.canonical())

    def test_rights_change_before_delivery_releases_writer_and_exposes_no_ir(self):
        self.permit()
        before = self.canonical()
        self.after_read = lambda: self.permit(derive="denied")
        result = self.execute()
        self.assertEqual("failure", result.kind)
        self.assertEqual("parse-delivery-denied", result.code)
        self.assertFalse(hasattr(result, "ir"))
        self.assertEqual(1, self.called)
        self.assertEqual(before, self.canonical())

    def test_actual_project_close_and_reopen_refuses_old_session_delivery(self):
        self.permit()
        before = self.canonical()

        def close_and_reopen():
            self.preview.service.detach(self.preview.root)
            self.preview.projects.close(root=self.preview.root, trace_id="f" * 32)
            self.preview.projects.open(root=self.preview.root, trace_id="f" * 32)
            self.preview.service.attach(self.preview.root)
            self.assertNotEqual(
                self.session, self.preview.service.native_context(self.preview.root, self.source.project_id)
            )

        self.after_read = close_and_reopen
        result = self.execute()
        self.assertEqual("failure", result.kind)
        self.assertFalse(hasattr(result, "ir"))
        self.assertEqual(before, self.canonical())

    def test_stale_intent_privacy_and_identical_digest_foreign_source_are_denied(self):
        self.permit()
        for actor in (replace(self.actor, intent_sha256="f" * 64), replace(self.actor, policy_sha256="e" * 64)):
            with self.subTest(actor_hash=actor.intent_sha256):
                self.assertEqual("failure", self.execute(actor=actor).kind)
        original = self.request.model_dump(mode="json", by_alias=True)
        for field in (
            "attachmentId",
            "candidateId",
            "documentRevisionId",
            "sourceAssertionRevisionId",
            "workRevisionId",
            "versionRevisionId",
            "projectId",
        ):
            value = json.loads(json.dumps(original))
            alternate = new_uuid_v7()
            for item in (value["binding"]["source"], value["selection"]["candidates"][0]["source"]):
                item[field] = alternate
            value["selection"]["selectedAttachmentId"] = value["binding"]["source"]["attachmentId"]
            from research_observatory_core.parsing.selection import ParserSelection

            value["binding"]["selectionSha256"] = selection_sha256(ParserSelection.model_validate(value["selection"]))
            with self.subTest(field=field):
                self.assertEqual("failure", self.execute(ParseRequest.model_validate(value)).kind)
        self.assertEqual(0, self.called)

    def test_cancel_and_crash_cannot_publish_partial_structure(self):
        self.permit()
        before = self.canonical()
        self.stopped = True
        self.assertEqual("cancelled", self.execute().kind)
        self.assertEqual(0, self.called)
        self.stopped = False

        def stop():
            self.stopped = True

        self.after_read = stop
        cancelled = self.execute()
        self.assertEqual("cancelled", cancelled.kind)
        self.assertFalse(hasattr(cancelled, "ir"))
        self.stopped = False

        def crash():
            raise RuntimeError("PRIVATE-SYNTHETIC-PARSER-ERROR")

        self.after_read = crash
        failed = self.execute()
        self.assertEqual("failure", failed.kind)
        self.assertEqual("parser-failed", failed.code)
        self.assertFalse(hasattr(failed, "ir"))
        self.assertNotIn("PRIVATE-SYNTHETIC", str(failed))
        self.assertEqual(before, self.canonical())


class AcquiredParseSourceTests(unittest.TestCase):
    """Real retained receipt and encrypted copy; declared synthetic transport."""

    def test_remote_origin_requires_exact_retained_receipt_and_current_copy_rights(self):
        f = acquisition_fixtures.AcquisitionIntegrationTests(methodName="runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.permission()
        candidate = f.acquire()
        attachment = f.commit(candidate)
        with storage.open_canonical_database(f.database, expected_project_id=f.project) as db:
            row = db.execute(
                "SELECT location_id,receipt_sha256 FROM document_acquisition_sources WHERE candidate_id=?",
                (candidate.candidate_id,),
            ).fetchone()
            before = tuple(tuple(item) for item in db.execute("SELECT * FROM documents ORDER BY revision_id"))
        source = source_identity(
            attachment,
            candidate,
            AcquisitionOrigin(kind="remote-acquisition", location_id=row[0], receipt_sha256=row[1]),
        )
        self.assertIsInstance(f.objects, ParseSourceObjectStore)
        assert isinstance(f.objects, ParseSourceObjectStore)
        objects = f.objects
        with self.assertRaises(ObjectAccessDenied):
            objects.open_parse_source(source, actor=f.actor)
        rights = f.repository.rights
        prior = rights.current(candidate.rights_subject, actor=f.actor)
        self.assertIsNotNone(prior)
        assert prior is not None
        rights.publish_draft(
            candidate.rights_subject,
            tuple(
                RightsPermissionDraft(
                    use=RightsUse(
                        action=action,
                        purpose="document-attachment" if action == "store" else "document-analysis",
                        destination_kind="local-project",
                    ),
                    value="permitted",
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    grantee_actor_id=f.actor.actor_id,
                    evidence_revision_ids=(candidate.source_assertion_revision_id,),
                    license_observation_revision_id=None,
                    entitlement_revision_id=None,
                )
                for action in ("store", "inspect", "derive")
            ),
            prior.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="9" * 64,
            actor=f.actor,
        )
        with objects.open_parse_source(source, actor=f.actor) as stream:
            self.assertEqual(b"Synthetic acquired full text.\n", stream.read())
        for provenance in (
            LocalOrigin(kind="local-import"),
            AcquisitionOrigin(kind="remote-acquisition", location_id=new_uuid_v7(), receipt_sha256=row[1]),
            AcquisitionOrigin(kind="remote-acquisition", location_id=row[0], receipt_sha256="f" * 64),
        ):
            forged = source.model_copy(update={"provenance": provenance})
            with self.subTest(origin=provenance.kind), self.assertRaises(ObjectAccessDenied):
                objects.open_parse_source(forged, actor=f.actor)
        with storage.open_canonical_database(f.database, expected_project_id=f.project) as db:
            self.assertEqual(
                before, tuple(tuple(item) for item in db.execute("SELECT * FROM documents ORDER BY revision_id"))
            )
        self.assertEqual(1, f.count("document_attachment_assertions"))


if __name__ == "__main__":
    unittest.main()
