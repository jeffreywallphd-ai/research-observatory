"""Synthetic protected CAP-04.S04 source-overlap workload.

Fixture creation is excluded from timings. The timed operations use the real
Core, rights, current-user DPAPI and SQLCipher adapters on a reopened project.
"""

from __future__ import annotations

import csv
import hashlib
import io
import time
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
from research_observatory_core.config import CoreSettings
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.main import create_runtime_app
from research_observatory_core.ports.import_previews import PreviewCreate, PreviewDraftChange
from research_observatory_core.reconciliation.contracts import SourceAddress
from research_observatory_core.storage import open_canonical_database
from research_observatory_core.workflow_executor import WorkerCapacity

from tests.connectors.test_connector_authority import ConnectorAuthorityFixture
from tests.service import test_import_preview_service as runtime_fixture
from tests.service.test_import_review_scale_windows import _memory

RECORDS = 64
ITEMS = RECORDS
PAGE_LIMIT = 32
FIXTURE_VERSION = "synthetic-protected-corpus-overlap-64-v1"


def _application(vault: Path, nonce: str):
    return create_runtime_app(
        settings=CoreSettings(),
        profile_vault_root=vault,
        workflow_context=NativeWorkflowContext("b" * 32, nonce * 32),
        capability_digest=capability_token_digest("a" * 64),
        expected_authority="127.0.0.1:49152",
    )


def _post(client, route: str, body: dict) -> dict:
    response = client.post(route, json=body)
    if response.status_code != 200:
        raise AssertionError(f"protected benchmark request failed: {route} {response.status_code}")
    return response.json()


def _policy(root: str, project_id: str, address: dict, assertion_id: str, *, connector: bool = False) -> dict:
    subject = {
        "projectId": project_id,
        "sourceAssertionRevisionId": assertion_id,
        "address": address,
        "copyId": assertion_id,
        "copyLocation": "local-source",
        "resourceClass": "metadata",
    }
    uses = [(action, "corpus-report") for action in ("derive", "inspect")]
    if connector:
        uses += [(action, "corpus-membership") for action in ("store", "inspect", "derive", "index")]
    return {
        "root": root,
        "commandId": new_uuid_v7(),
        "subject": subject,
        "permissions": [
            {
                "use": {
                    "action": action,
                    "purpose": purpose,
                    "destinationKind": "local-project",
                    "provider": None,
                    "region": None,
                    "shareGroup": None,
                },
                "value": "permitted",
                "basis": "researcher-confirmed",
                "confidence": "confirmed",
                "evidenceRevisionIds": [assertion_id],
            }
            for action, purpose in uses
        ],
        "expectedPredecessorRevisionId": None,
        "confirmed": True,
    }


def _members(imports, root: str, preview: str, revision: str) -> list:
    result = []
    after = 0
    while True:
        page = imports.import_manifest_members(root, preview, revision_id=revision, after=after, limit=100)
        result.extend(page)
        if len(page) < 100:
            return result
        after = page[-1].ordinal


def _second_source(imports, root: str, project_id: str, *, number: int) -> tuple[dict, str]:
    grant = ImportPermission(value="permitted", basis="researcher-confirmed")
    rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
    preview = new_uuid_v7()
    raw = f"title,doi\nSynthetic overlap {number},10.99999/reconcile-001\n".encode()
    imports.create(
        root,
        PreviewCreate(
            preview_id=preview,
            source_name=f"synthetic-overlap-{number}.csv",
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
    draft = drafts.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=imports.actor("2" * 32)))
    imports.schedule_commit(root, preview, revision=draft.revision, request_id=new_uuid_v7())
    imports.run_pending()
    manifest = imports.import_manifest(root, preview)
    if manifest is None:
        raise AssertionError("second synthetic import unavailable")
    selected = next(
        (member for member in _members(imports, root, preview, manifest.revision_id) if member.decision.included), None
    )
    if selected is None:
        raise AssertionError("second synthetic source unavailable")
    address = {
        "kind": "import-member",
        "contextId": preview,
        "revisionId": manifest.revision_id,
        "ordinal": selected.ordinal,
        "recordKey": selected.record_key,
    }
    return address, manifest.revision_id


def _setup(directory: Path, *, items: int) -> dict:
    helper = runtime_fixture.ImportRuntimeCompositionTests()
    app = _application(directory / "vault", "c")
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
                "parentDirectory": str(directory),
                "directoryName": "project",
                "displayName": "Synthetic source overlap",
                "primaryUseCase": "theory-synthesis",
                "researchObjective": "Measure local canonical source overlap without remote access.",
            },
        )
        root, project_id = project["root"], project["projectId"]
        _post(client, "/projects/open", {"root": root})
        runtime = app.state.runtime
        authority = ConnectorAuthorityFixture()
        authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
        if authority.intent("local-only").status != "accepted":
            raise AssertionError("synthetic Intent unavailable")
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        document = io.StringIO(newline="")
        writer = csv.writer(document)
        writer.writerow(("title", "doi", "year", "language"))
        for index in range(RECORDS):
            writer.writerow(
                (
                    f"Synthetic source-overlap work {index:03d}",
                    f"10.99999/reconcile-{index:03d}",
                    "2025" if index % 3 == 0 else "",
                    "en" if index % 4 == 0 else "",
                )
            )
        raw, preview = document.getvalue().encode("utf-8"), new_uuid_v7()
        imports = runtime.imports
        imports.create(
            root,
            PreviewCreate(
                preview_id=preview,
                source_name="synthetic-corpus.csv",
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
        draft_repo = imports._adapters(Path(root), project_id).previews
        draft = draft_repo.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=imports.actor("2" * 32)))
        imports.schedule_commit(root, preview, revision=draft.revision, request_id=new_uuid_v7())
        imports.run_pending()
        manifest = imports.import_manifest(root, preview)
        if manifest is None:
            raise AssertionError("synthetic import manifest unavailable")
        imported = _members(imports, root, preview, manifest.revision_id)
        included = [member for member in imported if member.decision.included]
        if len(included) != RECORDS or len({member.ordinal for member in imported}) != len(imported):
            raise AssertionError(
                f"synthetic accepted import inventory changed: {len(imported)} records, {len(included)} included"
            )
        item_by_work: dict[str, dict] = {}
        for member in included[:items]:
            address = {
                "kind": "import-member",
                "contextId": preview,
                "revisionId": manifest.revision_id,
                "ordinal": member.ordinal,
                "recordKey": member.record_key,
            }
            work = _post(
                client, "/projects/reconciliation/exact", {"root": root, "commandId": new_uuid_v7(), "source": address}
            )
            if work["disposition"] != "new-work" or not work["workId"]:
                raise AssertionError("synthetic distinct-work reconciliation changed")
            item = _post(
                client,
                "/projects/corpus/create",
                {
                    "root": root,
                    "commandId": new_uuid_v7(),
                    "workId": work["workId"],
                    "workRevisionId": work["workRevisionId"],
                    "source": address,
                },
            )
            _post(
                client,
                "/projects/corpus/rights/publish",
                _policy(root, project_id, address, work["assertionRevisionId"]),
            )
            item_by_work[work["workId"]] = item
        intent = next((row for row in runtime.intents.workspace(root).history if row.status == "accepted"), None)
        if intent is None:
            raise AssertionError("accepted Intent unavailable")
        source_keys = ["import:" + manifest.revision_id]
        timed_source: dict | None = None
        timed_source_id: str | None = None
        target_revision: str | None = None
        target_item_id: str | None = None
        for number in (1, 2, 3):
            second, second_revision = _second_source(runtime.imports, root, project_id, number=number)
            merged = _post(
                client, "/projects/reconciliation/exact", {"root": root, "commandId": new_uuid_v7(), "source": second}
            )
            second_source = runtime.imports.reconciliation_source(root, SourceAddress.model_validate(second))
            target = item_by_work.get(merged["workId"])
            if target is None or merged["disposition"] != "exact-linked":
                raise AssertionError("synthetic overlap did not reconcile to existing work")
            rebound = runtime.corpus.rebind(
                root,
                target["itemId"],
                expected_revision_id=target["revisionId"],
                command_id=new_uuid_v7(),
                next_work_id=merged["workId"],
                next_work_revision_id=merged["workRevisionId"],
                reason_code="new-source-record",
                protocol_revision_id=intent.revision_id,
                evidence_revision_ids=(merged["workRevisionId"],),
                trace_id="3" * 32,
            )
            _post(
                client,
                "/projects/corpus/rights/publish",
                _policy(root, project_id, second, merged["assertionRevisionId"], connector=True),
            )
            source_keys.append("import:" + second_revision)
            target_item_id, target_revision = rebound.item_id, rebound.revision_id
            if number < 3:
                appended = runtime.corpus.add_path(
                    root,
                    rebound.item_id,
                    expected_revision_id=rebound.revision_id,
                    command_id=new_uuid_v7(),
                    source=SourceAddress.model_validate(second),
                    reason_code="new-import-path",
                    protocol_revision_id=intent.revision_id,
                    evidence_revision_ids=(second_source.source_revision_id,),
                    trace_id="3" * 32,
                )
                item_by_work[merged["workId"]] = appended.model_dump(mode="json", by_alias=True)
                target_revision = appended.revision_id
            else:
                timed_source, timed_source_id = second, second_source.source_revision_id
        _post(client, "/projects/close", {"root": root})
    if timed_source is None or timed_source_id is None or target_revision is None or target_item_id is None:
        raise AssertionError("synthetic timed source unavailable")
    return {
        "root": root,
        "projectId": project_id,
        "itemCount": items,
        "sourceKeys": tuple(source_keys),
        "targetItemId": target_item_id,
        "targetRevisionId": target_revision,
        "secondAddress": timed_source,
        "secondSourceRevisionId": timed_source_id,
        "intentRevisionId": intent.revision_id,
    }


def _size(root: str) -> int:
    state = Path(root) / "state"
    return sum(
        path.stat().st_size for name in ("project.sqlite3", "project.sqlite3-wal") if (path := state / name).exists()
    )


def _drill(client, root: str, snapshot: str, *, limit: int) -> tuple[list[dict], list[dict]]:
    cursor = None
    pages = []
    members = []
    while True:
        started = time.perf_counter_ns()
        page = _post(
            client,
            "/projects/corpus/reports/drill",
            {
                "root": root,
                "snapshotId": snapshot,
                "filter": {"kind": "all"},
                "cursor": cursor,
                "limit": limit,
            },
        )
        seconds = (time.perf_counter_ns() - started) / 1e9
        if page["snapshotId"] != snapshot or len(page["members"]) > limit or not page["members"]:
            raise AssertionError("report drill page changed")
        members.extend(page["members"])
        pages.append({"count": len(page["members"]), "seconds": seconds})
        next_cursor = page["nextCursor"]
        if next_cursor is None:
            return pages, members
        if next_cursor == cursor:
            raise AssertionError("report cursor did not progress")
        cursor = next_cursor


def run_workload(directory: Path, *, items: int = ITEMS) -> dict:
    if items not in (2, ITEMS):
        raise ValueError("unsupported synthetic benchmark fixture size")
    fixture = _setup(directory, items=items)
    root = fixture["root"]
    if (Path(root) / "state/project.sqlite3").read_bytes()[:16] == b"SQLite format 3\x00":
        raise AssertionError("project database is plaintext")
    helper = runtime_fixture.ImportRuntimeCompositionTests()
    app = _application(directory / "vault", "e")
    provider_calls: list[bool] = []

    def unexpected_provider():
        provider_calls.append(True)
        raise AssertionError("provider transport during report measurement")

    with helper.client(app) as client:
        _post(client, "/projects/open", {"root": root})
        runtime = app.state.runtime
        runtime.connectors._transport_factory = unexpected_provider
        before_bytes = _size(root)
        started = time.perf_counter_ns()
        updated = runtime.corpus.add_path(
            root,
            fixture["targetItemId"],
            expected_revision_id=fixture["targetRevisionId"],
            command_id=new_uuid_v7(),
            source=fixture["secondAddress"],
            reason_code="new-import-path",
            protocol_revision_id=fixture["intentRevisionId"],
            evidence_revision_ids=(fixture["secondSourceRevisionId"],),
            trace_id="4" * 32,
        )
        update_seconds = (time.perf_counter_ns() - started) / 1e9
        if len(updated.discovery_path_ids) != 4:
            raise AssertionError("incremental overlap path did not publish")
        after_update_bytes = _size(root)
        reports = []
        for phase in ("first-after-reopen-plus-update", "repeat-same-corpus"):
            started = time.perf_counter_ns()
            report = _post(client, "/projects/corpus/reports/create", {"root": root, "commandId": new_uuid_v7()})
            seconds = (time.perf_counter_ns() - started) / 1e9
            if report["memberCount"] != items or report["discoveryPathCount"] != items + 3:
                raise AssertionError("report count differs from canonical fixture")
            contributions = {
                part["sourceKey"]: (part["itemCount"], part["discoveryPathCount"])
                for part in report["sourceContributions"]
            }
            expected = {fixture["sourceKeys"][0]: (items, items)} | {key: (1, 1) for key in fixture["sourceKeys"][1:]}
            if contributions != expected or len(report["sourceOverlaps"]) != 6:
                raise AssertionError("report source contribution differs")
            if any((part["itemCount"], part["discoveryPathPairCount"]) != (1, 1) for part in report["sourceOverlaps"]):
                raise AssertionError("report source pair differs")
            reports.append({"phase": phase, "seconds": seconds, "snapshotId": report["snapshotId"], "summary": report})
        if reports[0]["snapshotId"] == reports[1]["snapshotId"]:
            raise AssertionError("repeat report reused sealed snapshot")
        if any(
            reports[0]["summary"][key] != reports[1]["summary"][key]
            for key in ("memberCount", "discoveryPathCount", "sourceContributions", "sourceOverlaps", "coverage")
        ):
            raise AssertionError("repeat report changed unchanged corpus facts")
        started = time.perf_counter_ns()
        inspected = _post(
            client, "/projects/corpus/reports/inspect", {"root": root, "snapshotId": reports[1]["snapshotId"]}
        )
        inspect_seconds = (time.perf_counter_ns() - started) / 1e9
        if inspected != reports[1]["summary"]:
            raise AssertionError("saved report inspection differs")
        pages, members = _drill(client, root, reports[1]["snapshotId"], limit=PAGE_LIMIT)
        if len(members) != items or len({member["itemId"] for member in members}) != items:
            raise AssertionError("paged drill does not enumerate exact canonical items")
        matched = next((member for member in members if member["itemId"] == fixture["targetItemId"]), None)
        if matched is None or matched["itemRevisionId"] != updated.revision_id or len(matched["paths"]) != 4:
            raise AssertionError("overlap aggregate does not drill to updated item")
        after_report_bytes = _size(root)
        _post(client, "/projects/close", {"root": root})
    with open_canonical_database(
        Path(root) / "state/project.sqlite3", expected_project_id=fixture["projectId"]
    ) as connection:
        projection = tuple(
            connection.execute(
                "SELECT left_source_key,right_source_key,item_count,discovery_path_pair_count "
                "FROM corpus_source_overlap_totals WHERE project_id=?",
                (fixture["projectId"],),
            ).fetchall()
        )
    if len(projection) != 6 or any(tuple(row[2:]) != (1, 1) for row in projection) or provider_calls:
        raise AssertionError("protected projection or no-egress boundary differs")
    return {
        "fixtureVersion": FIXTURE_VERSION if items == ITEMS else "diagnostic-2-v1",
        "itemCount": items,
        "discoveryPathCount": items + 3,
        "sourceRootCount": 4,
        "sourcePairCount": 6,
        "actualDPAPIAndSQLCipher": True,
        "providerNetworkDuringMeasurement": len(provider_calls),
        "timings": {
            "incrementalUpdateSeconds": update_seconds,
            "firstReportAfterReopenAndUpdateSeconds": reports[0]["seconds"],
            "repeatReportSeconds": reports[1]["seconds"],
            "inspectSeconds": inspect_seconds,
            "firstDrillPageSeconds": pages[0]["seconds"],
            "laterDrillPageSeconds": pages[1]["seconds"] if len(pages) > 1 else None,
        },
        "pageSizes": [part["count"] for part in pages],
        "databaseBytes": {"before": before_bytes, "afterUpdate": after_update_bytes, "afterReport": after_report_bytes},
        "memory": _memory(),
    }
