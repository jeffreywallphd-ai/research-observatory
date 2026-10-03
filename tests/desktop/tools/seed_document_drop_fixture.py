"""Seed one protected, synthetic Work/version for the built Windows drop probe.

This is a disposable test composition. It uses the real Core project, import,
reconciliation and version services with a Windows-backed database key, then
closes Core before the native Tauri fixture opens the same project. Stdout is
ID-only JSON; local fixture paths remain in ignored artifacts/tmp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.domain_contracts import new_uuid_v7  # noqa: E402
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights  # noqa: E402
from research_observatory_core.main import create_runtime_app  # noqa: E402
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewDraftChange  # noqa: E402
from research_observatory_core.workflow_executor import WorkerCapacity  # noqa: E402

from tests.connectors import test_connector_authority as authority_fixture  # noqa: E402
from tests.service import test_import_preview_service as runtime_fixture  # noqa: E402


def _post(client, route: str, body: dict) -> dict:
    response = client.post(route, json=body)
    if response.status_code != 200:
        raise RuntimeError(f"synthetic Core seed failed at {route}: status {response.status_code}")
    return response.json()


def published_seed_selection(before: dict, published: list[dict], context: dict) -> dict[str, str]:
    """Bind the seed to the post-registration Work and exact version context."""
    if len(published) != 1 or len(context.get("works", ())) != 1 or len(context.get("versions", ())) != 1:
        raise RuntimeError("synthetic published Work/version is not exact")
    current = published[0]
    contextual = context["works"][0]
    if (
        current.get("workId") != before.get("workId")
        or current.get("revisionId") == before.get("revisionId")
        or current.get("assertionRevisionIds") != before.get("assertionRevisionIds")
        or contextual.get("workId") != current.get("workId")
        or contextual.get("revisionId") != current.get("revisionId")
        or contextual.get("assertionRevisionIds") != current.get("assertionRevisionIds")
    ):
        raise RuntimeError("synthetic published Work identity changed")
    version = context["versions"][0]
    return {
        "workId": current["workId"],
        "workRevisionId": current["revisionId"],
        "versionId": version["versionId"],
        "versionRevisionId": version["revisionId"],
        "sourceAssertionRevisionId": current["assertionRevisionIds"][0],
    }


def seed(fixture_root: Path) -> dict[str, object]:
    fixture_root = fixture_root.resolve(strict=True)
    temporary_parent = (ROOT / "artifacts/tmp").resolve(strict=True)
    if fixture_root.parent != temporary_parent or not fixture_root.name.startswith("directory-dialog-"):
        raise ValueError("drop fixture must be a disposable directory-dialog child")
    projects = (fixture_root / "projects").resolve(strict=True)
    vault = (fixture_root / "vault").resolve(strict=True)
    temporary = (fixture_root / "temporary").resolve(strict=True)
    if projects.parent != fixture_root or vault.parent != fixture_root or temporary.parent != fixture_root:
        raise ValueError("drop fixture directory containment changed")
    source_file = temporary / "document-drop-source.txt"
    source_file.write_bytes(b"Synthetic scholarly full text for local attachment boundary testing.\n" * 32)

    app = create_runtime_app(
        settings=CoreSettings(),
        profile_vault_root=vault,
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
        project = _post(
            client,
            "/projects",
            {
                "parentDirectory": str(projects),
                "directoryName": "document-drop-project",
                "displayName": "Synthetic document drop",
                "primaryUseCase": "theory-synthesis",
                "researchObjective": "Verify local full-text attachment to a selected synthetic Work/version.",
            },
        )
        root = project["root"]
        project_id = project["projectId"]
        _post(client, "/projects/open", {"root": root})
        authority = authority_fixture.ConnectorAuthorityFixture()
        authority.root = root
        authority.service = app.state.runtime.intents
        authority.privacy = app.state.runtime.privacy
        authority.intent(mode="local-only", providers=())

        imports = app.state.runtime.imports
        preview_id = new_uuid_v7()
        raw = b"title,doi\nSynthetic document drop Work,10.99999/document-drop\n"
        imports.create(
            root,
            PreviewCreate(
                preview_id=preview_id,
                source_name="document-drop-bibliography.csv",
                format_name="csv",
                rights=rights,
                actor=imports.actor("1" * 32),
            ),
        )
        imports.append_chunk(root, preview_id, ordinal=1, data=raw)
        imports.seal(
            root,
            preview_id,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            byte_length=len(raw),
            chunk_count=1,
            trace_id="1" * 32,
        )
        imports.schedule(root, preview_id)
        imports.run_pending()
        repository = imports._adapters(Path(root), project_id).previews
        draft = repository.revise_draft(
            preview_id,
            PreviewDraftChange(expected_revision=0, actor=imports.actor("2" * 32)),
        )
        imports.schedule_commit(root, preview_id, revision=draft.revision, request_id=new_uuid_v7())
        imports.run_pending()
        manifest = imports.import_manifest(root, preview_id)
        if manifest is None:
            raise RuntimeError("synthetic import did not publish a manifest")

        request_id = _post(client, "/projects/reconciliation/batches/prepare", {"root": root})["requestId"]
        scheduled = _post(
            client,
            "/projects/reconciliation/batches/schedule",
            {"root": root, "requestId": request_id},
        )
        app.state.runtime.reconciliation.run_pending()
        batch = _post(
            client,
            "/projects/reconciliation/batches/status",
            {"root": root, "requestId": request_id, "jobId": scheduled["jobId"]},
        )
        if batch["state"] != "succeeded":
            raise RuntimeError("synthetic reconciliation batch did not succeed")
        works = _post(
            client,
            "/projects/reconciliation/versions/works",
            {"root": root, "after": None, "limit": 32},
        )["items"]
        if len(works) != 1 or len(works[0]["assertionRevisionIds"]) != 1:
            raise RuntimeError("synthetic Work identity is not exact")
        work = works[0]
        context = _post(
            client,
            "/projects/reconciliation/versions/context",
            {"root": root, "workIds": [work["workId"]]},
        )
        if context["versions"]:
            raise RuntimeError("synthetic version unexpectedly exists")
        plan = {
            "schemaVersion": "1.0",
            "action": "register",
            "workIds": [work["workId"]],
            "contextSha256": context["contextSha256"],
            "rationale": "Synthetic selected manifestation for native OS-drop proof.",
            "definition": {
                "kind": "accepted-manuscript",
                "assertionRevisionIds": work["assertionRevisionIds"],
                "date": {"precision": "not-reported", "value": None},
            },
            "version": None,
            "relation": None,
            "previousPreferenceRevisionId": None,
        }
        preview = _post(
            client,
            "/projects/reconciliation/versions/preview",
            {"root": root, "plan": plan},
        )
        _post(
            client,
            "/projects/reconciliation/versions/commit",
            {
                "root": root,
                "command": {
                    "commandId": preview["commandId"],
                    "plan": plan,
                    "expectedPreviewSha256": preview["previewSha256"],
                },
            },
        )
        published_works = _post(
            client,
            "/projects/reconciliation/versions/works",
            {"root": root, "after": None, "limit": 32},
        )["items"]
        final_context = _post(
            client,
            "/projects/reconciliation/versions/context",
            {"root": root, "workIds": [work["workId"]]},
        )
        selection = published_seed_selection(work, published_works, final_context)
        _post(client, "/projects/close", {"root": root})

    if (Path(root) / "state/project.sqlite3").read_bytes()[:16] == b"SQLite format 3\x00":
        raise RuntimeError("synthetic project database is plaintext")
    return {
        "schemaVersion": "1.0",
        "projectId": project_id,
        **selection,
        "syntheticSourceSha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
        "protectedDatabase": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(seed(arguments.fixture_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
