"""Opt-in synthetic max-source fixture and independent SQLCipher writer.

The Reader's Windows handler test uses this narrow product fixture. Seeding
declares synthetic inspection/capacity and executes no model. The later Native
read/cancel handlers, supervised Core, encrypted objects and writer are real.
No key material, research content or command lines enter the writer protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "services/core-api/src")]


def confined(path: Path) -> Path:
    scratch = (REPO / "artifacts/tmp").resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved.parent != scratch or not resolved.name.startswith("directory-dialog-viewer-native-"):
        raise ValueError("native-viewer-fixture-not-confined")
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("native-viewer-fixture-redirected")
        if part == scratch:
            break
    return resolved


def seed(*, accepted: bool = False) -> Path:
    from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
    from research_observatory_core.config import CoreSettings
    from research_observatory_core.document_attachment_repository import LocalDocumentAttachmentService
    from research_observatory_core.domain_contracts import new_uuid_v7
    from research_observatory_core.main import create_runtime_app
    from research_observatory_core.workflow_executor import WorkerCapacity

    from tests.desktop.fixtures.bounded_pdf import write_bounded_pdf
    from tests.desktop.tools.seed_document_drop_fixture import seed as seed_work
    from tests.service.test_import_preview_service import ImportRuntimeCompositionTests

    root = Path(tempfile.mkdtemp(prefix="directory-dialog-viewer-native-", dir=REPO / "artifacts/tmp"))
    root = confined(root)
    for name in ("projects", "vault", "temporary", "application-data", "webview"):
        (root / name).mkdir()
    selected = seed_work(root)
    project_root = (root / "projects/document-drop-project").resolve(strict=True)
    app = create_runtime_app(
        settings=CoreSettings(),
        profile_vault_root=root / "vault",
        workflow_context=NativeWorkflowContext("b" * 32, "c" * 32),
        capability_digest=capability_token_digest("a" * 64),
        expected_authority="127.0.0.1:49152",
    )
    helper = ImportRuntimeCompositionTests()
    with (
        patch(
            "research_observatory_core.repositories._windows_worker_capacity",
            return_value=WorkerCapacity(4, 4 * 1024**3, 0, 4 * 1024**3),
        ),
        helper.client(app) as client,
    ):
        opened = client.post("/projects/open", json={"root": str(project_root)})
        assert opened.status_code == 200 and opened.json()["projectId"] == selected["projectId"]
        runtime = app.state.runtime.attachments
        session = runtime.context(str(project_root), selected["projectId"])

        def authored(service, actor):
            operation, command = new_uuid_v7(), new_uuid_v7()

            def inspection(source, **_):
                digest, size = hashlib.sha256(), 0
                while block := source.read(65536):
                    digest.update(block)
                    size += len(block)
                return SimpleNamespace(
                    format="plain-text" if accepted else "pdf",
                    media_type="text/plain" if accepted else "application/pdf",
                    size_bytes=size,
                    sha256=digest.hexdigest(),
                )

            local = LocalDocumentAttachmentService(
                service._database, selected["projectId"], service._objects, inspector=inspection
            )
            with tempfile.TemporaryFile(dir=root / "temporary") as source:
                if accepted:
                    source.write(b"SYNTHETIC Native accepted-structure source.\n")
                    source.seek(0)
                else:
                    write_bounded_pdf(source, pages=500, byte_length=128 * 1024**2)
                    source.seek(-1024 * 1024, 2)
                tail_digest = hashlib.sha256(source.read(1024 * 1024)).hexdigest()
                source.seek(0)
                candidate = local.stage(
                    source,
                    source_name="synthetic-accepted-viewer.txt" if accepted else "synthetic-maximum-viewer.pdf",
                    declared_media_type="text/plain" if accepted else "application/pdf",
                    source_assertion_revision_id=selected["sourceAssertionRevisionId"],
                    work_id=selected["workId"],
                    work_revision_id=selected["workRevisionId"],
                    version_id=selected["versionId"],
                    version_revision_id=selected["versionRevisionId"],
                    actor=actor,
                    operation_id=operation,
                    session_id=session,
                )
            attachment = local.commit(
                candidate.candidate_id,
                confirmation_sha256=candidate.candidate_sha256,
                command_id=command,
                actor=actor,
                operation_id=operation,
                session_id=session,
                match_confirmed=True,
                permitted_use="project-only",
                exact_selection=tuple(
                    selected[key]
                    for key in (
                        "sourceAssertionRevisionId",
                        "workId",
                        "workRevisionId",
                        "versionId",
                        "versionRevisionId",
                    )
                ),
            )
            return candidate, attachment, tail_digest

        candidate, attachment, tail_digest = runtime._action(
            str(project_root), selected["projectId"], session, "1" * 32, authored
        )
        accepted_receipts = None
        if accepted:
            publish_derive(runtime, project_root, selected["projectId"], session, candidate, "permitted")
            normal = seed_revision(
                app,
                project_root,
                selected["projectId"],
                session,
                attachment.attachment_id,
                "SYNTHETIC accepted Native text.",
            )
            large = seed_revision(
                app,
                project_root,
                selected["projectId"],
                session,
                attachment.attachment_id,
                "S" * 65536,
                expected=normal.revision_id,
            )
            denied_candidate, denied_attachment, _ = runtime._action(
                str(project_root), selected["projectId"], session, "1" * 32, authored
            )
            publish_derive(runtime, project_root, selected["projectId"], session, denied_candidate, "permitted")
            denied = seed_revision(
                app,
                project_root,
                selected["projectId"],
                session,
                denied_attachment.attachment_id,
                "SYNTHETIC denied derivative.",
            )
            publish_derive(runtime, project_root, selected["projectId"], session, denied_candidate, "denied")

            def binding(item, original):
                return {
                    "selector": {
                        "attachmentId": original.attachment_id,
                        "documentRevisionId": original.document_revision_id,
                        "normalizedRevisionId": item.revision_id,
                    },
                    "nodeId": item.structure.nodes[0].node_id,
                }

            accepted_receipts = {
                "normal": binding(normal, attachment),
                "large": binding(large, attachment),
                "denied": binding(denied, denied_attachment),
            }
        assert client.post("/projects/close", json={"root": str(project_root)}).status_code == 200
    assert (project_root / "state/project.sqlite3").read_bytes()[:16] != b"SQLite format 3\x00"
    receipt = {
        "schemaVersion": "1.0",
        "projectId": selected["projectId"],
        "root": str(project_root),
        "selector": {
            "attachmentId": attachment.attachment_id,
            "documentRevisionId": attachment.document_revision_id,
            "normalizedRevisionId": None,
        },
        "sourceSha256": candidate.object_sha256,
        "sourceBytes": candidate.byte_length,
        "tailSha256": tail_digest,
        "pages": None if accepted else 500,
        "seedAdapters": ["synthetic-inspection", "synthetic-capacity"],
        "modelExecuted": False,
    }
    if accepted_receipts is not None:
        receipt["acceptedFixtures"] = accepted_receipts
        receipt["seedAdapters"].append("explicitly-synthetic-parser-output-through-real-revision-apis")
    with (root / "viewer-receipt.json").open("x", encoding="utf-8") as target:
        json.dump(receipt, target)
    return root


def publish_derive(runtime, root, project, session, candidate, value):
    """Publish actual copy-specific rights; never mutate policy tables."""
    from research_observatory_core.domain_contracts import new_uuid_v7
    from research_observatory_core.ports.rights import RightsPermissionDraft
    from research_observatory_core.rights_policy import RightsUse

    def publish(service, actor):
        prior = service._rights.current(candidate.rights_subject, actor=actor)
        assert prior is not None
        permissions = tuple(
            RightsPermissionDraft(
                use=RightsUse(
                    action=action,
                    purpose="document-attachment" if action == "store" else "document-analysis",
                    destination_kind="local-project",
                ),
                value=value if action == "derive" else "permitted",
                basis="researcher-confirmed",
                confidence="confirmed",
                grantee_actor_id=actor.actor_id,
                evidence_revision_ids=(candidate.source_assertion_revision_id,),
            )
            for action in ("store", "inspect", "derive")
        )
        service._rights.publish_draft(
            candidate.rights_subject,
            permissions,
            prior.revision_id,
            command_id=new_uuid_v7(),
            command_sha256="5" * 64,
            actor=actor,
        )

    runtime._action(str(root), project, session, "1" * 32, publish)


def seed_revision(app, root, project, session, attachment, raw, *, expected=None):
    """Retain and human-accept authored IR through the real repository APIs."""
    from research_observatory_core.document_attachment_repository import LocalParserArtifactStager
    from research_observatory_core.document_parse_workflow import DocumentParseInput
    from research_observatory_core.document_revisions import DocumentRevisionAcceptance
    from research_observatory_core.domain_contracts import new_uuid_v7
    from research_observatory_core.parsing.contracts import DocumentIR
    from research_observatory_core.parsing.requests import ParseSuccess
    from research_observatory_core.parsing.selection import (
        ParserRegistry,
        RegisteredParser,
        SelectionSource,
        select_parser,
    )

    from tests.parsing import contract_fixtures
    from tests.workflows.test_local_workflow_executor import WORKER_A

    service = app.state.runtime.document_revisions
    repository, selected, actor = service._repository(str(root), project, session, "1" * 32)
    source = repository.source(attachment)
    selection = select_parser(
        (SelectionSource(source, "available", "primary"),),
        ParserRegistry(
            (RegisteredParser(contract_fixtures.descriptor("ro-native-text", ("plain-text",)), "available"),)
        ),
        primary_attachment_id=attachment,
    )
    intent = service.imports._action(str(root), lambda binding: service.imports._intent(binding))
    inputs = DocumentParseInput(
        project_id=project,
        command_id=new_uuid_v7(),
        actor_id=actor.actor_id,
        session_id=session,
        source=source,
        selection=selection,
        intent=intent,
        policy_sha256=actor.policy_sha256,
    )
    job = repository.submit(inputs)
    now = service.now()
    claim = repository.queue.claim_next(
        worker_id=WORKER_A,
        concurrency_classes=("document",),
        activity_types=("document-parse",),
        now=now,
        lease_duration_ms=30000,
    )
    assert claim is not None and claim.job_id == job.job_id
    repository.queue.start(claim, now=now)
    request = inputs.request(claim)
    stager = LocalParserArtifactStager(
        selected._database,
        selected._objects,
        claim=claim,
        request=request,
        actor=repository.actor,
        guard=repository.guard,
        now=service.now,
    )
    artifact = stager(
        request,
        b'{"synthetic-parser-output":true}',
        media_type="application/vnd.research-observatory.text-parser-output+json",
        cancelled=lambda: False,
    )
    wire = contract_fixtures.ir(request.binding, raw=raw).model_dump(mode="json", by_alias=True)
    wire["rawArtifacts"] = [artifact.model_dump(mode="json", by_alias=True)]
    retained, _ = repository.retain(
        claim,
        request,
        ParseSuccess(schema_version="1.0", kind="success", binding=request.binding, ir=DocumentIR.model_validate(wire)),
        stopped=lambda: False,
    )
    return repository.accept(
        DocumentRevisionAcceptance(
            command_id=new_uuid_v7(),
            result_id=retained.result_id,
            expected_current_revision_id=expected or source.document_revision_id,
            confirmation_sha256=hashlib.sha256(retained.model_dump_json(by_alias=True).encode()).hexdigest(),
            decision="accept-structure",
        )
    )


def writer(root: Path) -> None:
    import sqlcipher3.dbapi2 as sqlcipher
    from research_observatory_core.windows_credentials import create_windows_database_key_provider

    root = confined(root)
    receipt = json.loads((root / "viewer-receipt.json").read_text(encoding="utf-8"))
    project_root = Path(receipt["root"]).resolve(strict=True)
    if project_root.parent != root / "projects":
        raise ValueError("native-viewer-project-not-confined")
    provider = create_windows_database_key_provider(root / "vault")
    connection = sqlcipher.connect(
        (project_root / "state/project.sqlite3").as_uri() + "?mode=rw", uri=True, timeout=0, isolation_level=None
    )
    try:
        with provider.active_key(receipt["projectId"], create=False) as lease:
            lease.use(lambda material: connection.execute("PRAGMA key = \"x'" + material.hex() + "'\""))
        before = connection.execute(
            "SELECT storage_state,verified_at FROM object_records WHERE project_id=? AND object_sha256=?",
            (receipt["projectId"], receipt["sourceSha256"]),
        ).fetchone()
        assert before is not None and before[0] == "available"
        print(json.dumps({"kind": "writer-ready", "protected": True}), flush=True)
        for line in sys.stdin:
            if len(line) > 128:
                raise ValueError("native-writer-command-too-large")
            command = json.loads(line)
            if command == {"action": "close"}:
                return
            if command not in ({"action": "observe"}, {"action": "commit"}):
                raise ValueError("native-writer-command-invalid")
            began = time.perf_counter()
            while True:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    if command["action"] == "commit":
                        updated = connection.execute(
                            "UPDATE object_records SET verified_at=verified_at WHERE project_id=? AND object_sha256=?",
                            (receipt["projectId"], receipt["sourceSha256"]),
                        )
                        assert updated.rowcount == 1
                        connection.execute("COMMIT")
                        after = connection.execute(
                            "SELECT storage_state,verified_at FROM object_records "
                            "WHERE project_id=? AND object_sha256=?",
                            (receipt["projectId"], receipt["sourceSha256"]),
                        ).fetchone()
                        assert before == after
                    else:
                        connection.execute("ROLLBACK")
                    print(
                        json.dumps(
                            {
                                "kind": "writer-result",
                                "outcome": "committed" if command["action"] == "commit" else "available",
                                "preserved": True,
                                "elapsedMs": (time.perf_counter() - began) * 1000,
                            }
                        ),
                        flush=True,
                    )
                    break
                except sqlcipher.OperationalError as error:
                    if "locked" not in str(error).lower():
                        raise
                    if command["action"] == "observe" or time.perf_counter() - began >= 1:
                        print(
                            json.dumps(
                                {
                                    "kind": "writer-result",
                                    "outcome": "busy",
                                    "elapsedMs": (time.perf_counter() - began) * 1000,
                                }
                            ),
                            flush=True,
                        )
                        break
                    time.sleep(0.005)
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "seed-accepted", "writer"))
    parser.add_argument("--fixture", type=Path)
    arguments = parser.parse_args()
    if arguments.action in {"seed", "seed-accepted"}:
        if os.name != "nt":
            raise RuntimeError("windows-principal-required")
        print(
            json.dumps({"fixture": str(seed(accepted=arguments.action == "seed-accepted")), "modelExecuted": False}),
            flush=True,
        )
    elif arguments.fixture is not None:
        writer(arguments.fixture)
    else:
        raise ValueError("native-viewer-fixture-required")
