"""Corpus query lineage uses the real protected connector owner inventory."""

from __future__ import annotations

from research_observatory_core.corpus.membership import CorpusProblem
from research_observatory_core.corpus_query import ConnectorWorkerQueryResolver
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights

from tests.connectors.test_connector_workflow import ConnectorWorkflowFixture


class ConnectorCorpusQueryTests(ConnectorWorkflowFixture):
    def setUp(self) -> None:
        super().setUp()
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        self.rights = self.rights.model_copy(
            update={"rights": ImportRights(store=grant, inspect=grant, derive=grant, index=grant)}
        )

    def test_accepted_query_page_and_source_bind_without_new_egress_after_restart(self) -> None:
        preview, job = self.schedule()
        self.worker.run_pending()
        page = self.worker.reconciliation_sources(self.root, job.job_id, after=0, limit=1)
        self.assertEqual(1, len(page.addresses))
        address = page.addresses[0]
        source = self.worker.reconciliation_source(self.root, address)
        resolver = ConnectorWorkerQueryResolver(self.worker)
        self.assertEqual(preview.preview_id, resolver(self.root, address, source))
        self.assertEqual(
            preview.preview_id,
            self.projects.perform_open_project_action(
                root=self.root,
                require_write=True,
                action=lambda _path, _project: resolver(self.root, address, source),
            ),
        )
        self.assertEqual(1, len(self.calls))

        self.worker.shutdown()
        self.connectors = self.consent_service()
        self.worker = self.worker_service()
        resolver = ConnectorWorkerQueryResolver(self.worker)
        self.assertEqual(preview.preview_id, resolver(self.root, address, source))
        self.assertEqual(1, len(self.calls))

        with self.assertRaisesRegex(CorpusProblem, "corpus-connector-query-unavailable"):
            resolver(self.root, address.model_copy(update={"revision_id": new_uuid_v7()}), source)
        with self.assertRaisesRegex(CorpusProblem, "corpus-connector-query-unavailable"):
            resolver(self.root, address, source.model_copy(update={"source_sha256": "e" * 64}))
        with self.assertRaisesRegex(CorpusProblem, "corpus-connector-query-unavailable"):
            resolver(self.root, address.model_copy(update={"context_id": new_uuid_v7()}), source)
