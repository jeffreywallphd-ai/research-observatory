"""Real Native Core session + Windows DPAPI + SQLCipher FTS, without a UI.

The seed uses synthetic bibliography and a declared capacity observation. No
parser/model execution or general machine-resource qualification is claimed.
"""

import shutil
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "services/core-api/src"), str(ROOT)]

from research_observatory_core import projects, storage  # noqa: E402
from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.derivative_keys import VaultDerivativeKeyProvider  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.lexical_index_repository import (  # noqa: E402
    CoreLexicalIndexService,
    IndexCleanupPending,
    IndexServiceProblem,
)
from research_observatory_core.lexical_source_repository import CanonicalIndexSources  # noqa: E402
from research_observatory_core.main import create_runtime_app  # noqa: E402
from research_observatory_core.ports.rights import RightsPermissionDraft  # noqa: E402
from research_observatory_core.reconciliation_repository import SqliteReconciliationRepository  # noqa: E402
from research_observatory_core.rights_policy import RightsUse  # noqa: E402
from research_observatory_core.search import parse_query  # noqa: E402
from research_observatory_core.windows_credentials import WindowsCredentialStore  # noqa: E402
from research_observatory_core.workflow_executor import WorkerCapacity  # noqa: E402

from tests.desktop.tools.seed_document_drop_fixture import seed  # noqa: E402
from tests.service import test_import_preview_service as runtime_fixtures  # noqa: E402


@unittest.skipUnless(sys.platform == "win32", "W3 actual Windows Native/DPAPI composition")
class NativeIndexServiceTests(unittest.TestCase):
    def test_actual_native_headless_rebuild_rights_and_session_reopen(self):
        scratch = Path(tempfile.mkdtemp(prefix="directory-dialog-index-native-", dir=ROOT / "artifacts/tmp"))
        self.assertEqual((ROOT / "artifacts/tmp").resolve(), scratch.parent.resolve())
        for name in ("projects", "vault", "temporary", "application-data", "webview"):
            (scratch / name).mkdir()
        selected = {name: value for name, value in seed(scratch).items() if isinstance(value, str)}
        project = scratch / "projects/document-drop-project"
        project_id = selected["projectId"]
        app = create_runtime_app(
            settings=CoreSettings(),
            profile_vault_root=scratch / "vault",
            workflow_context=NativeWorkflowContext("b" * 32, "c" * 32),
            capability_digest=capability_token_digest("a" * 64),
            expected_authority="127.0.0.1:49152",
        )
        helper = runtime_fixtures.ImportRuntimeCompositionTests()
        with (
            patch(
                "research_observatory_core.repositories._windows_worker_capacity",
                return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
            ),
            helper.client(app) as client,
        ):
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            runtime = app.state.runtime
            runtime.document_revisions.shutdown()
            session = runtime.attachments.context(str(project), project_id)
            with closing(
                storage.open_canonical_database(project / "state/project.sqlite3", expected_project_id=project_id)
            ) as db:
                source = (
                    SqliteReconciliationRepository(project / "state/project.sqlite3", project_id)
                    ._load(db, selected["sourceAssertionRevisionId"])
                    .assertion
                )
            item = runtime.corpus.create(
                str(project),
                command_id=new_uuid_v7(),
                work_id=selected["workId"],
                work_revision_id=selected["workRevisionId"],
                source=source.address,
                trace_id="1" * 32,
            )
            repository, _, _ = runtime.document_revisions._repository(str(project), project_id, session, "2" * 32)
            sources = CanonicalIndexSources(
                repository, resolve=lambda address: runtime.imports.reconciliation_source(str(project), address)
            )
            canonical = storage._database_protection_configuration().provider
            assert canonical is not None
            keys = VaultDerivativeKeyProvider(
                WindowsCredentialStore(scratch / "vault", audit_sink=lambda _event: None),
                profile_id="local-default",
                database_keys=canonical,
            )
            service = CoreLexicalIndexService(sources, keys, canonical)
            self.addCleanup(service.close)
            subject = sources.metadata_subject(source)
            permissions = tuple(
                RightsPermissionDraft(
                    use=RightsUse(action=action, purpose="local-search", destination_kind="local-project"),
                    value="permitted",
                    basis="researcher-confirmed",
                    confidence="confirmed",
                    evidence_revision_ids=(subject.source_assertion_revision_id,),
                    license_observation_revision_id=None,
                    entitlement_revision_id=None,
                    expires_at=None,
                )
                for action in ("inspect", "index")
            )
            runtime.corpus.publish_rights(
                str(project),
                command_id=new_uuid_v7(),
                subject=subject,
                permissions=permissions,
                expected_predecessor_revision_id=None,
                confirmed=True,
                trace_id="3" * 32,
            )
            generation = service.rebuild()
            self.assertEqual((item.item_id,), service.match(parse_query('title:"document drop"')))
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)
            with self.assertRaises(IndexServiceProblem):
                service.match(parse_query("document"))
            self.assertEqual(200, client.post("/projects/open", json={"root": str(project)}).status_code)
            with self.assertRaises(IndexServiceProblem):
                service.match(parse_query("document"))
            fresh_session = runtime.attachments.context(str(project), project_id)
            self.assertNotEqual(session, fresh_session)
            fresh_repository, _, _ = runtime.document_revisions._repository(
                str(project), project_id, fresh_session, "4" * 32
            )
            fresh = CoreLexicalIndexService(
                CanonicalIndexSources(
                    fresh_repository,
                    resolve=lambda address: runtime.imports.reconciliation_source(str(project), address),
                ),
                keys,
                canonical,
            )
            self.addCleanup(fresh.close)
            selected_generation = fresh.catalog.selected()
            assert selected_generation is not None
            self.assertEqual(generation.generation_id, selected_generation.generation_id)
            self.assertEqual((item.item_id,), fresh.match(parse_query('title:"document drop"')))
            self.assertEqual(200, client.post("/projects/close", json={"root": str(project)}).status_code)

            def current_service(root):
                context = runtime.attachments.context(str(root), project_id)
                document_repository, _, _ = runtime.document_revisions._repository(
                    str(root), project_id, context, "5" * 32
                )
                indexed = CoreLexicalIndexService(
                    CanonicalIndexSources(
                        document_repository,
                        resolve=lambda address: runtime.imports.reconciliation_source(str(root), address),
                    ),
                    keys,
                    canonical,
                )
                self.addCleanup(indexed.close)
                return indexed

            def rebuild_and_drain(indexed):
                try:
                    return indexed.rebuild()
                except IndexCleanupPending:
                    # A closed previous Core instance's durable writer fence
                    # expires naturally. No old-session token is transferred,
                    # forced termination used, or live lease overwritten.
                    time.sleep(31)
                    indexed.collect_obsolete()
                    chosen = indexed.catalog.selected()
                    assert chosen is not None
                    return chosen

            original = project
            relocated = scratch / "projects/relocated-project"
            self.assertTrue(original.resolve().is_relative_to(scratch.resolve()))
            self.assertTrue(relocated.parent.resolve().is_relative_to(scratch.resolve()))
            self.assertFalse(relocated.exists())
            original.rename(relocated)
            self.assertEqual(200, client.post("/projects/open", json={"root": str(relocated)}).status_code)
            relocated_service = current_service(relocated)
            with self.assertRaises(IndexServiceProblem):
                relocated_service.match(parse_query("document"))
            moved = rebuild_and_drain(relocated_service)
            self.assertNotEqual(generation.scope.lifecycle_sha256, moved.scope.lifecycle_sha256)
            self.assertEqual((item.item_id,), relocated_service.match(parse_query('title:"document drop"')))
            self.assertEqual(200, client.post("/projects/close", json={"root": str(relocated)}).status_code)

            # Use the real existing recovery source inventory to construct a
            # declared synthetic restore. Recovery UI/dead-owner verification
            # is not claimed here; Native open and derivative rebuild are real.
            directories, files = projects._recovery_paths(relocated, lambda: False)
            self.assertTrue(any((relocated / "indexes").iterdir()))
            self.assertFalse(any(path.is_relative_to(relocated / "indexes") for path in files))
            restored = scratch / "projects/restored-project"
            self.assertTrue(restored.parent.resolve().is_relative_to(scratch.resolve()))
            restored.mkdir()
            for name in projects._PROJECT_DIRECTORIES:
                (restored / name).mkdir()
            for directory in directories:
                (restored / directory.relative_to(relocated)).mkdir(parents=True, exist_ok=True)
            for path in files:
                destination = restored / path.relative_to(relocated)
                self.assertTrue(destination.parent.resolve().is_relative_to(restored.resolve()))
                shutil.copyfile(path, destination)
            self.assertEqual([], list((restored / "indexes").iterdir()))
            self.assertEqual(200, client.post("/projects/open", json={"root": str(restored)}).status_code)
            restored_service = current_service(restored)
            with self.assertRaises(IndexServiceProblem):
                restored_service.match(parse_query("document"))
            rebuilt = rebuild_and_drain(restored_service)
            self.assertNotEqual(moved.scope.lifecycle_sha256, rebuilt.scope.lifecycle_sha256)
            self.assertEqual((item.item_id,), restored_service.match(parse_query('title:"document drop"')))
            self.assertEqual(200, client.post("/projects/close", json={"root": str(restored)}).status_code)
            project = restored
        for path in (project / "indexes").iterdir():
            self.assertNotIn(b"Synthetic document drop Work", path.read_bytes())
