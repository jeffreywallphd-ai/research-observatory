"""Authenticated rights publication across real Windows DPAPI and SQLCipher restart."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import TypedDict
from unittest.mock import patch

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.main import create_runtime_app
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewDraftChange
from research_observatory_core.storage import open_canonical_database
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors.test_connector_authority import ConnectorAuthorityFixture
from tests.service import test_import_preview_service as runtime_fixture


class RightsPermissionPayload(TypedDict):
    use: dict[str, str | None]
    value: str
    basis: str
    confidence: str
    evidenceRevisionIds: list[str]


@unittest.skipUnless(os.name == "nt", "current-user DPAPI and SQLCipher required")
class RightsRuntimeWindowsTests(unittest.TestCase):
    def test_authenticated_policy_replay_restart_and_revocation_block_corpus_use(self) -> None:
        helper = runtime_fixture.ImportRuntimeCompositionTests()
        with tempfile.TemporaryDirectory(prefix="ro-rights-runtime-") as directory:
            vault = Path(directory) / "vault"

            def application(nonce: str):
                return create_runtime_app(
                    settings=CoreSettings(),
                    profile_vault_root=vault,
                    workflow_context=NativeWorkflowContext("b" * 32, nonce * 32),
                    capability_digest=capability_token_digest("a" * 64),
                    expected_authority="127.0.0.1:49152",
                )

            def post(client, route: str, body: dict, expected: int = 200, *, trace_id: str | None = None) -> dict:
                response = client.post(route, json=body, headers={"x-trace-id": trace_id} if trace_id else None)
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
                            "displayName": "Synthetic rights boundary",
                            "primaryUseCase": "theory-synthesis",
                            "researchObjective": "Local source-specific permissions",
                        },
                    )
                    root, project_id = project["root"], project["projectId"]
                    post(client, "/projects/open", {"root": root})
                    runtime = first.state.runtime
                    authority = ConnectorAuthorityFixture()
                    authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
                    self.assertEqual("accepted", authority.intent("local-only").status)

                    grant = ImportPermission(value="permitted", basis="researcher-confirmed")
                    imports = runtime.imports
                    preview = new_uuid_v7()
                    raw = b"title,doi\nSynthetic rights source,10.99999/rights-boundary\n"
                    imports.create(
                        root,
                        PreviewCreate(
                            preview_id=preview,
                            source_name="synthetic.csv",
                            format_name="csv",
                            rights=ImportRights(store=grant, inspect=grant, derive=grant, index=grant),
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
                        item
                        for item in imports.import_manifest_members(
                            root, preview, revision_id=manifest.revision_id, after=0, limit=10
                        )
                        if item.decision.included
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
                    assertion_id = work["assertionRevisionId"]
                    subject = {
                        "projectId": project_id,
                        "sourceAssertionRevisionId": assertion_id,
                        "address": address,
                        "copyId": assertion_id,
                        "copyLocation": "local-source",
                        "resourceClass": "metadata",
                    }
                    inspect_use = {
                        "action": "inspect",
                        "purpose": "corpus-membership",
                        "destinationKind": "local-project",
                        "provider": None,
                        "region": None,
                        "shareGroup": None,
                    }
                    evaluation = {"root": root, "subject": subject, "use": inspect_use}
                    bridged = post(client, "/projects/corpus/rights/evaluate", evaluation)
                    self.assertEqual(("allow", "legacy-import-bridge"), (bridged["code"], bridged["authorityKind"]))
                    self.assertEqual(bridged["governingAssertionIds"], [assertion_id])
                    self.assertIsNone(bridged["policyRevisionId"])
                    permissions: list[RightsPermissionPayload] = [
                        {
                            "use": inspect_use | {"action": action},
                            "value": "permitted",
                            "basis": "researcher-confirmed",
                            "confidence": "confirmed",
                            "evidenceRevisionIds": [assertion_id],
                        }
                        for action in ("store", "inspect", "derive", "index")
                    ]
                    remote_use = {
                        "action": "model-use",
                        "purpose": "corpus-membership",
                        "destinationKind": "remote-model",
                        "provider": "synthetic-provider",
                        "region": "us-east-1",
                        "shareGroup": None,
                    }
                    permissions.append(permissions[0] | {"use": remote_use})
                    publish = {
                        "root": root,
                        "commandId": new_uuid_v7(),
                        "subject": subject,
                        "permissions": permissions,
                        "expectedPredecessorRevisionId": None,
                        "confirmed": True,
                    }
                    denied_confirmation = post(
                        client, "/projects/corpus/rights/publish", publish | {"confirmed": False}, 422
                    )
                    self.assertEqual("RO-CORE-CORPUS-INVALID", denied_confirmation["code"])
                    self.assertEqual(
                        "legacy-import-bridge",
                        post(client, "/projects/corpus/rights/evaluate", evaluation)["authorityKind"],
                    )
                    unauthenticated = client.post(
                        "/projects/corpus/rights/publish", json=publish, headers={"Authorization": ""}
                    )
                    self.assertEqual(401, unauthenticated.status_code)
                    initial = post(client, "/projects/corpus/rights/publish", publish)
                    self.assertEqual(initial, post(client, "/projects/corpus/rights/publish", publish))
                    self.assertEqual(
                        initial,
                        post(client, "/projects/corpus/rights/current", {"root": root, "subject": subject}),
                    )
                    initial_scope = post(
                        client, "/projects/corpus/rights/recheck-scope", {"root": root, "subject": subject}
                    )
                    self.assertEqual(
                        (initial["revisionId"], "complete"),
                        (initial_scope["rightsRevisionId"], initial_scope["disposition"]),
                    )
                    self.assertEqual("allow", post(client, "/projects/corpus/rights/evaluate", evaluation)["code"])
                    remote_trace = "3" * 32
                    self.assertEqual(
                        "require-confirmation",
                        post(
                            client,
                            "/projects/corpus/rights/evaluate",
                            evaluation | {"use": remote_use},
                            trace_id=remote_trace,
                        )["code"],
                    )
                    with closing(
                        open_canonical_database(Path(root) / "state/project.sqlite3", expected_project_id=project_id)
                    ) as connection:
                        remote_audit = connection.execute(
                            "SELECT decision_code,reason_code FROM rights_use_decisions "
                            "WHERE project_id=? AND trace_id=? AND use_action='model-use'",
                            (project_id, remote_trace),
                        ).fetchall()
                    self.assertEqual(
                        [("require-confirmation", "rights-further-authority-required")],
                        [tuple(row) for row in remote_audit],
                    )
                    create = {
                        "root": root,
                        "commandId": new_uuid_v7(),
                        "workId": work["workId"],
                        "workRevisionId": work["workRevisionId"],
                        "source": address,
                    }
                    item = post(client, "/projects/corpus/create", create)
                    self.assertEqual("candidate", item["membership"])
                    self.assertNotEqual(
                        b"SQLite format 3\x00", (Path(root) / "state/project.sqlite3").read_bytes()[:16]
                    )
                    post(client, "/projects/close", {"root": root})

                restarted = application("d")
                with helper.client(restarted) as client:
                    post(client, "/projects/open", {"root": root})
                    self.assertEqual(
                        initial,
                        post(client, "/projects/corpus/rights/current", {"root": root, "subject": subject}),
                    )
                    self.assertEqual("allow", post(client, "/projects/corpus/rights/evaluate", evaluation)["code"])
                    revoked_permissions = [
                        permission | {"value": "denied"} if permission["use"]["action"] == "index" else permission
                        for permission in permissions
                    ]
                    revoked = post(
                        client,
                        "/projects/corpus/rights/publish",
                        publish
                        | {
                            "commandId": new_uuid_v7(),
                            "expectedPredecessorRevisionId": initial["revisionId"],
                            "permissions": revoked_permissions,
                        },
                    )
                    revoked_scope = post(
                        client, "/projects/corpus/rights/recheck-scope", {"root": root, "subject": subject}
                    )
                    self.assertEqual(
                        (revoked["revisionId"], "complete"),
                        (revoked_scope["rightsRevisionId"], revoked_scope["disposition"]),
                    )
                    self.assertEqual(
                        "deny",
                        post(
                            client,
                            "/projects/corpus/rights/evaluate",
                            evaluation | {"use": inspect_use | {"action": "index"}},
                        )["code"],
                    )
                    with closing(
                        open_canonical_database(Path(root) / "state/project.sqlite3", expected_project_id=project_id)
                    ) as connection:
                        before_denial = tuple(
                            connection.execute(
                                "SELECT COUNT(*) FROM " + table + " WHERE project_id=?", (project_id,)
                            ).fetchone()[0]
                            for table in ("corpus_item_states", "material_dependency_outputs")
                        )
                    denial_trace = "4" * 32
                    blocked = post(
                        client,
                        "/projects/corpus/create",
                        create | {"commandId": new_uuid_v7()},
                        403,
                        trace_id=denial_trace,
                    )
                    self.assertEqual("RO-CORE-CORPUS-DENIED", blocked["code"])
                    post(client, "/projects/close", {"root": root})

                after_revocation = application("e")
                with helper.client(after_revocation) as client:
                    post(client, "/projects/open", {"root": root})
                    self.assertEqual(
                        revoked,
                        post(client, "/projects/corpus/rights/current", {"root": root, "subject": subject}),
                    )
                    self.assertEqual(
                        "deny",
                        post(
                            client,
                            "/projects/corpus/rights/evaluate",
                            evaluation | {"use": inspect_use | {"action": "index"}},
                        )["code"],
                    )
                    self.assertEqual(
                        "RO-CORE-CORPUS-DENIED",
                        post(client, "/projects/corpus/create", create | {"commandId": new_uuid_v7()}, 403)["code"],
                    )
                    durable_scope = post(
                        client, "/projects/corpus/rights/recheck-scope", {"root": root, "subject": subject}
                    )
                    self.assertEqual(
                        (revoked["revisionId"], "complete"),
                        (durable_scope["rightsRevisionId"], durable_scope["disposition"]),
                    )
                    output_guard = post(
                        client,
                        "/projects/corpus/rights/output-rechecks",
                        {"root": root, "outputRevisionId": item["revisionId"]},
                    )
                    self.assertFalse(output_guard["propagationPending"])
                    self.assertFalse(output_guard["propagationUnknown"])
                    self.assertTrue(
                        any(
                            marker["kind"] == "exact" and marker["rightsRevisionId"] == revoked["revisionId"]
                            for marker in output_guard["markers"]
                        )
                    )
                    with closing(
                        open_canonical_database(Path(root) / "state/project.sqlite3", expected_project_id=project_id)
                    ) as connection:
                        self.assertEqual(
                            before_denial,
                            tuple(
                                connection.execute(
                                    "SELECT COUNT(*) FROM " + table + " WHERE project_id=?", (project_id,)
                                ).fetchone()[0]
                                for table in ("corpus_item_states", "material_dependency_outputs")
                            ),
                        )
                        denied_audit = connection.execute(
                            "SELECT d.decision_code,d.reason_code,d.policy_revision_id,d.policy_sha256,"
                            "d.actor_id,d.source_assertion_revision_id,d.use_action,r.policy_sha256,"
                            "d.authority_kind,d.source_assertion_sha256,a.payload_sha256 "
                            "FROM rights_use_decisions d JOIN rights_policy_revisions r "
                            "ON r.project_id=d.project_id AND r.revision_id=d.policy_revision_id "
                            "JOIN reconciliation_assertions a ON a.project_id=d.project_id "
                            "AND a.revision_id=d.source_assertion_revision_id "
                            "WHERE d.project_id=? AND d.trace_id=? AND d.event_kind='denied-attempt'",
                            (project_id, denial_trace),
                        ).fetchall()
                        self.assertEqual(len(denied_audit), 1)
                        self.assertEqual(
                            tuple(denied_audit[0][index] for index in (0, 1, 2, 5, 6)),
                            ("deny", "rights-explicit-denial", revoked["revisionId"], assertion_id, "index"),
                        )
                        self.assertEqual(denied_audit[0][3], denied_audit[0][7])
                        self.assertEqual(denied_audit[0][4], runtime.corpus._actor_id)
                        self.assertEqual(denied_audit[0][8], "policy")
                        self.assertEqual(denied_audit[0][9], denied_audit[0][10])
                        self.assertEqual(
                            1,
                            connection.execute(
                                "SELECT COUNT(*) FROM corpus_item_states WHERE project_id=?", (project_id,)
                            ).fetchone()[0],
                        )
                        self.assertEqual(
                            1,
                            connection.execute(
                                "SELECT COUNT(*) FROM rights_policy_rechecks WHERE project_id=? "
                                "AND rights_revision_id=? AND output_revision_id=? AND reason='RIGHTS_POLICY'",
                                (project_id, revoked["revisionId"], item["revisionId"]),
                            ).fetchone()[0],
                        )
                    post(client, "/projects/close", {"root": root})


if __name__ == "__main__":
    unittest.main()
