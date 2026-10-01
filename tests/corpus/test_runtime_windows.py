"""Authenticated Core corpus entry through real Windows profile protection.

Source bytes and the native context are synthetic. Core project, Intent, privacy,
source, local actor, DPAPI and SQLCipher authorities are the production adapters.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.main import create_runtime_app
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewDraftChange
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors.test_connector_authority import ConnectorAuthorityFixture
from tests.service import test_import_preview_service as runtime_fixture


@unittest.skipUnless(os.name == "nt", "current-user DPAPI and SQLCipher required")
class CorpusRuntimeWindowsTests(unittest.TestCase):
    def test_authenticated_import_entry_denial_and_reopen(self) -> None:
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        with tempfile.TemporaryDirectory(prefix="ro-corpus-runtime-") as directory:
            vault = Path(directory) / "vault"

            def application(nonce: str):
                return create_runtime_app(
                    settings=CoreSettings(),
                    profile_vault_root=vault,
                    workflow_context=NativeWorkflowContext("b" * 32, nonce * 32),
                    capability_digest=capability_token_digest("a" * 64),
                    expected_authority="127.0.0.1:49152",
                )

            def post(client, route: str, body: dict, expected: int = 200) -> dict:
                response = client.post(route, json=body)
                self.assertEqual(expected, response.status_code, response.text)
                return response.json()

            with patch(
                "research_observatory_core.repositories._windows_worker_capacity",
                return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
            ):
                first = application("c")
                with helper.client(first) as client:
                    project = post(
                        client,
                        "/projects",
                        {
                            "parentDirectory": directory,
                            "directoryName": "project",
                            "displayName": "Synthetic corpus entry",
                            "primaryUseCase": "theory-synthesis",
                            "researchObjective": "Synthetic local source lineage",
                        },
                    )
                    root, project_id = project["root"], project["projectId"]
                    post(client, "/projects/open", {"root": root})
                    runtime = first.state.runtime
                    authority = ConnectorAuthorityFixture()
                    authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
                    accepted = authority.intent("local-only")
                    self.assertEqual("accepted", accepted.status)

                    grant = ImportPermission(value="permitted", basis="researcher-confirmed")
                    rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
                    imports = runtime.imports
                    preview = new_uuid_v7()
                    raw = b"title,doi\nSynthetic corpus source,10.99999/corpus-entry\n"
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
                    drafts = imports._adapters(Path(root), project_id).previews
                    draft = drafts.revise_draft(
                        preview, PreviewDraftChange(expected_revision=0, actor=imports.actor("2" * 32))
                    )
                    imports.schedule_commit(root, preview, revision=draft.revision, request_id=new_uuid_v7())
                    imports.run_pending()
                    manifest = imports.import_manifest(root, preview)
                    self.assertIsNotNone(manifest)
                    member = next(
                        member
                        for member in imports.import_manifest_members(
                            root, preview, revision_id=manifest.revision_id, after=0, limit=10
                        )
                        if member.decision.included
                    )
                    address = {
                        "kind": "import-member",
                        "contextId": preview,
                        "revisionId": manifest.revision_id,
                        "ordinal": member.ordinal,
                        "recordKey": member.record_key,
                    }
                    work = post(
                        client,
                        "/projects/reconciliation/exact",
                        {"root": root, "commandId": new_uuid_v7(), "source": address},
                    )
                    self.assertEqual("new-work", work["disposition"])
                    create = {
                        "root": root,
                        "commandId": new_uuid_v7(),
                        "workId": work["workId"],
                        "workRevisionId": work["workRevisionId"],
                        "source": address,
                    }
                    denied_principal = client.post(
                        "/projects/corpus/create", json=create, headers={"Authorization": ""}
                    )
                    self.assertEqual(401, denied_principal.status_code, denied_principal.text)
                    post(
                        client,
                        "/projects/corpus/create",
                        create | {"commandId": new_uuid_v7(), "source": address | {"recordKey": "f" * 64}},
                        403,
                    )
                    item = post(client, "/projects/corpus/create", create)
                    self.assertEqual(("candidate", "pending"), (item["membership"], item["review"]))
                    self.assertEqual(item, post(client, "/projects/corpus/create", create))
                    post(client, "/projects/corpus/create", create | {"workRevisionId": new_uuid_v7()}, 409)
                    read = {"root": root, "itemId": item["itemId"]}
                    self.assertEqual(item, post(client, "/projects/corpus/inspect", read))
                    actor_id = runtime.corpus._actor_id
                    included = runtime.corpus.decide(
                        root,
                        item["itemId"],
                        expected_revision_id=item["revisionId"],
                        command_id=new_uuid_v7(),
                        dimension="membership",
                        command="include",
                        next_value="included",
                        reason_code="criterion-met",
                        protocol_revision_id=accepted.revision_id,
                        evidence_revision_ids=(work["assertionRevisionId"],),
                        trace_id="3" * 32,
                    )
                    self.assertEqual("included", included.membership)
                    self.assertEqual(
                        included.model_dump(mode="json", by_alias=True), post(client, "/projects/corpus/inspect", read)
                    )
                    drafts.revise_draft(
                        preview,
                        PreviewDraftChange(
                            expected_revision=draft.revision,
                            actor=imports.actor("4" * 32),
                            rights=rights.model_copy(
                                update={"index": ImportPermission(value="denied", basis="researcher-confirmed")}
                            ),
                        ),
                    )
                    post(client, "/projects/corpus/create", create | {"commandId": new_uuid_v7()}, 403)
                    post(client, "/projects/close", {"root": root})

                restarted = application("d")
                with helper.client(restarted) as client:
                    post(client, "/projects/open", {"root": root})
                    self.assertEqual(
                        included.model_dump(mode="json", by_alias=True), post(client, "/projects/corpus/inspect", read)
                    )
                    self.assertEqual(actor_id, restarted.state.runtime.corpus._actor_id)
                    history = restarted.state.runtime.corpus.history(root, item["itemId"], trace_id="3" * 32)
                    self.assertEqual(2, len(history))
                    restored, paths, first_decision = history[0]
                    self.assertEqual(item, restored.model_dump(mode="json", by_alias=True))
                    self.assertIsNone(first_decision)
                    self.assertEqual(1, len(paths))
                    self.assertEqual(address["revisionId"], paths[0].context_revision_id)
                    self.assertEqual(member.source_record_revision_id, paths[0].source_revision_id)
                    self.assertIsNone(paths[0].predecessor_item_revision_id)
                    final, retained_paths, decision = history[1]
                    self.assertEqual(included, final)
                    self.assertEqual(paths, retained_paths)
                    self.assertIsNotNone(decision)
                    self.assertEqual(("candidate", "included"), (decision.previous_value, decision.next_value))
                    self.assertEqual(
                        (item["revisionId"], included.revision_id),
                        (decision.previous_revision_id, decision.next_revision_id),
                    )
                    self.assertEqual(
                        (actor_id, "criterion-met", accepted.revision_id),
                        (decision.actor_id, decision.reason_code, decision.protocol_revision_id),
                    )
                    self.assertEqual((work["assertionRevisionId"],), decision.evidence_revision_ids)
                    self.assertIsNone(decision.previous_decision_revision_id)
                    self.assertIsNone(decision.supersedes_decision_revision_id)
                    database_bytes = (Path(root) / "state/project.sqlite3").read_bytes()[:16]
                    self.assertNotEqual(b"SQLite format 3\x00", database_bytes)
                    post(client, "/projects/close", {"root": root})
