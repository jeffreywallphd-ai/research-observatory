"""Synthetic accepted import/connector inputs in real Windows protected storage."""

import csv
import hashlib
import io
from pathlib import Path
from unittest.mock import patch

import httpx2
from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.main import create_runtime_app
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewDraftChange
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors import test_connector_authority as authority_fixture
from tests.connectors import test_source_slice_runtime as source_fixture
from tests.connectors.test_connector_transport import BytesStream
from tests.service import test_import_preview_service as runtime_fixture


def prepare(directory: Path, *, records: int = 2) -> dict[str, str]:
    if records not in (2, 202):
        raise ValueError("unsupported synthetic reconciliation fixture size")
    document = source_fixture.documents(1)["crossref"]
    calls = []

    async def respond(wire):
        calls.append(wire.url.host)
        if wire.url.host != "api.crossref.org":
            raise AssertionError("Unexpected synthetic provider destination")
        response = httpx2.Response(200, json=document)
        return httpx2.Response(200, headers=response.headers, stream=BytesStream(response.content))

    def post(client, route, body):
        response = client.post(route, json=body)
        if response.status_code != 200:
            raise AssertionError(f"Synthetic setup failed: {route} {response.status_code}")
        return response.json()

    app = create_runtime_app(
        settings=CoreSettings(),
        profile_vault_root=directory / "vault",
        workflow_context=NativeWorkflowContext("b" * 32, "c" * 32),
        capability_digest=capability_token_digest("a" * 64),
        expected_authority="127.0.0.1:49152",
    )
    helper = runtime_fixture.ImportRuntimeCompositionTests()
    grant = ImportPermission(value="permitted", basis="researcher-confirmed")
    rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
    with (
        patch(
            "research_observatory_core.repositories._windows_worker_capacity",
            return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
        ),
        helper.client(app) as client,
    ):
        runtime = app.state.runtime
        runtime.connectors._transport_factory = lambda: httpx2.MockTransport(respond)
        project = post(
            client,
            "/projects",
            {
                "parentDirectory": str(directory),
                "directoryName": "project",
                "displayName": "Synthetic native reconciliation",
                "primaryUseCase": "theory-synthesis",
                "researchObjective": "Verify reversible scholarly identity under protected local authority.",
            },
        )
        root, identity = project["root"], project["projectId"]
        post(client, "/projects/open", {"root": root})
        authority = authority_fixture.ConnectorAuthorityFixture()
        authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
        authority.intent(providers=("crossref",))
        authority.policy()
        source = document["message"]["items"][0]
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(("title", "doi"))
        for index in range(records):
            cluster = index // 2
            writer.writerow(
                (
                    source["title"][0] if cluster == 0 else f"Synthetic reconciliation cluster {cluster:03d}",
                    source["DOI"] if cluster == 0 else f"10.99999/reconcile-{cluster:03d}",
                )
            )
        raw, preview = text.getvalue().encode(), new_uuid_v7()
        imports = runtime.imports
        imports.create(
            root,
            PreviewCreate(
                preview_id=preview,
                source_name="synthetic.csv",
                format_name="csv",
                rights=rights,
                actor=imports.actor("1" * 32),
            ),
        )
        imports.append_chunk(root, preview, ordinal=1, data=raw)
        imports.seal(
            root,
            preview,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id="1" * 32,
        )
        imports.schedule(root, preview)
        imports.run_pending()
        repository = imports._adapters(Path(root), identity).previews
        draft = repository.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=imports.actor("2" * 32)))
        imports.schedule_commit(root, preview, revision=draft.revision, request_id=new_uuid_v7())
        imports.run_pending()
        manifest = imports.import_manifest(root, preview)
        included = 0
        if manifest is not None:
            after = 0
            while True:
                page = repository.manifest_members(manifest.revision_id, after=after, limit=100)
                included += sum(member.decision.included for member in page)
                if len(page) < 100:
                    break
                after = page[-1].ordinal
        if included != records:
            raise AssertionError("Synthetic accepted import is incomplete")
        request = source_fixture.source_request("crossref", identity, 1)
        confirmed = post(
            client,
            "/projects/connectors/previews",
            {
                "root": root,
                "request": request.model_dump(mode="json", by_alias=True),
                "retention": {"rights": rights.model_dump(mode="json", by_alias=True), "retainBody": True},
            },
        )
        job = post(
            client,
            "/projects/connectors/confirmations",
            {"root": root, "previewId": confirmed["previewId"], "confirmation": confirmed["confirmation"]},
        )
        runtime.connectors.run_pending()
        if (
            post(client, "/projects/connectors/jobs/status", {"root": root, "jobId": job["jobId"]})["state"]
            != "succeeded"
        ):
            raise AssertionError("Synthetic retained connector is incomplete")
        authority.policy(False)
        post(client, "/projects/close", {"root": root})
    if (
        calls != ["api.crossref.org"]
        or (Path(root) / "state/project.sqlite3").read_bytes()[:16] == b"SQLite format 3\x00"
    ):
        raise AssertionError("Protected synthetic fixture boundary differs")
    return {"root": root, "projectId": identity, "previewId": preview, "manifestRevisionId": manifest.revision_id}
