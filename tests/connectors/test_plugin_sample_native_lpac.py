"""Run the published sample in the signed Windows LPAC worker with synthetic broker data."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_manifest import verify_plugin_package  # noqa: E402
from research_observatory_core.connectors.plugin_result import PluginWorkerPage  # noqa: E402

from workers.windows import recovery_guardian  # noqa: E402
from workers.windows.connector_launcher import WorkerResult, run_connector  # noqa: E402
from workers.windows.lpac_launcher import LPACError  # noqa: E402
from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime  # noqa: E402

SAMPLE = REPO / "docs/developer/sample_repository"
ENTRY = "plugin/connector.py"
SEARCH_CASES = (
    SAMPLE / "fixtures/search-page-1.case.json",
    SAMPLE / "fixtures/search-page-2.case.json",
)


@unittest.skipUnless(os.name == "nt", "Windows x64 LPAC qualification")
class SampleConnectorNativeLpacTests(unittest.TestCase):
    def setUp(self) -> None:
        build_path = os.environ.get("RO_W2_SIGNED_WORKER_BUILD")
        guardian_path = os.environ.get("RO_W2_CORE_SIDECAR_GUARDIAN")
        if not build_path or not guardian_path:
            self.skipTest("locally signed worker and frozen Core guardian are required")
        build = Path(build_path).resolve(strict=True)
        guardian = Path(guardian_path).resolve(strict=True)
        self.runtime = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        self.guardian_command = [str(guardian), "--plugin-acl-guardian"]
        source = (SAMPLE / ENTRY).read_bytes()
        manifest = (SAMPLE / "manifest.json").read_bytes()
        signing_key = SigningKey(b"\x5d" * 32)
        self.package = verify_plugin_package(
            manifest,
            signing_key.sign(manifest).signature,
            {ENTRY: source},
            {"sample-repository-publisher": bytes(signing_key.verify_key)},
        )
        self.package_files = {ENTRY: source}

    def _run_case(self, case: dict, response: dict) -> tuple[WorkerResult, list[dict]]:
        calls: list[dict] = []

        def broker(call: dict) -> bytes:
            calls.append(call)
            return json.dumps(response, separators=(",", ":")).encode("utf-8")

        with patch.object(recovery_guardian, "_guardian_command", return_value=self.guardian_command):
            result = run_connector(
                self.runtime,
                self.package,
                self.package_files,
                job_nonce=secrets.token_hex(16),
                invocation_id=case["invocationId"],
                operation=case["operation"],
                input_data=json.dumps(case["input"], separators=(",", ":")).encode("utf-8"),
                broker_callback=broker,
            )
        return result, calls

    def test_two_sample_pages_execute_inside_signed_lpac_worker(self) -> None:
        for path in SEARCH_CASES:
            with self.subTest(case=path.name):
                case = json.loads(path.read_text(encoding="utf-8"))
                result, calls = self._run_case(case, case["brokerResponse"])
                self.assertEqual([case["brokerCall"]], calls)
                self.assertEqual(1, result.broker_calls)
                self.assertIs(result.token["appContainer"], True)
                self.assertIs(result.token["lessPrivileged"], True)
                self.assertEqual(0, result.token["capabilityCount"])
                output = json.loads(result.output)
                self.assertEqual(case["output"], output)
                PluginWorkerPage.model_validate(output)

    def test_malformed_broker_page_fails_closed_without_echoing_content(self) -> None:
        case = json.loads(SEARCH_CASES[0].read_text(encoding="utf-8"))
        broker_response = json.loads(json.dumps(case["brokerResponse"]))
        broker_response["records"][0]["privateToken"] = "SYNTHETIC-PRIVATE-DO-NOT-ECHO"
        calls: list[dict] = []

        def broker(call: dict) -> bytes:
            calls.append(call)
            return json.dumps(broker_response, separators=(",", ":")).encode("utf-8")

        with (
            patch.object(recovery_guardian, "_guardian_command", return_value=self.guardian_command),
            self.assertRaises(LPACError) as denied,
        ):
            run_connector(
                self.runtime,
                self.package,
                self.package_files,
                job_nonce=secrets.token_hex(16),
                invocation_id=case["invocationId"],
                operation=case["operation"],
                input_data=json.dumps(case["input"], separators=(",", ":")).encode("utf-8"),
                broker_callback=broker,
            )
        self.assertEqual([case["brokerCall"]], calls)
        self.assertNotIn("SYNTHETIC-PRIVATE-DO-NOT-ECHO", str(denied.exception))


class SignedCoreFixtureRuntime:
    """Test-only selected dependency; execution uses the actual signed LPAC launcher."""

    def __init__(self) -> None:
        from workers.windows.runtime_inventory import APPLICATION_INVENTORY_PUBLIC_KEY, SignedWorkerRuntime

        build = Path(os.environ["RO_W2_SIGNED_WORKER_BUILD"]).resolve(strict=True)
        self.guardian = Path(os.environ["RO_W2_CORE_SIDECAR_GUARDIAN"]).resolve(strict=True)
        expected = os.environ["RO_W2_CORE_SIDECAR_GUARDIAN_SHA256"].lower()
        scratch = (REPO / "artifacts/tmp").resolve(strict=True)
        assert build.parent == scratch and scratch in self.guardian.parents
        for selected in (build, self.guardian):
            for item in (selected, *selected.parents):
                assert not item.is_symlink() and not item.is_junction()
                if item == scratch:
                    break
        assert hashlib.sha256(self.guardian.read_bytes()).hexdigest() == expected
        self.runtime = SignedWorkerRuntime(
            build / "package",
            (build / "inventory.json").read_bytes(),
            (build / "inventory.sig").read_bytes(),
            APPLICATION_INVENTORY_PUBLIC_KEY,
        )
        self.actual_results: list[WorkerResult] = []

    def load(self) -> SignedWorkerRuntime:
        from workers.windows.runtime_inventory import verify_worker_runtime

        verify_worker_runtime(self.runtime)
        return self.runtime

    def available(self) -> bool:
        self.load()
        return True

    def run(self, runtime: SignedWorkerRuntime, package: Any, files: dict[str, bytes], **kwargs: Any) -> WorkerResult:
        from workers.windows import recovery_guardian
        from workers.windows.connector_launcher import run_connector

        assert runtime is self.runtime
        with patch.object(
            recovery_guardian, "_guardian_command", return_value=[str(self.guardian), "--plugin-acl-guardian"]
        ):
            result = run_connector(runtime, package, files, **kwargs)
        assert result.token["appContainer"] is True
        assert result.token["lessPrivileged"] is True
        assert result.token["capabilityCount"] == 0
        assert result.token["allApplicationPackagesDenied"] is True
        self.actual_results.append(result)
        return result


def protected_core_phase(directory: Path, phase: str) -> None:
    import httpx2
    from fastapi.testclient import TestClient
    from research_observatory_core import main as core_main
    from research_observatory_core.authentication import NativeWorkflowContext, capability_token_digest
    from research_observatory_core.config import CoreSettings
    from research_observatory_core.connector_service import ConnectorRetention
    from research_observatory_core.connectors.plugin_broker import PluginNetworkBroker
    from research_observatory_core.connectors.plugin_grants import (
        PluginEnableConfirmation,
        PluginGrantActor,
        PluginGrantProblem,
    )
    from research_observatory_core.connectors.plugin_manifest import PluginInvocationRequest
    from research_observatory_core.connectors.plugin_trust import PluginTrustDecision
    from research_observatory_core.domain_contracts import new_uuid_v7
    from research_observatory_core.plugin_consent import PluginConsentProblem
    from research_observatory_core.plugin_job_repository import PluginPublishedPage
    from research_observatory_core.plugin_runtime import InstalledPluginRuntime
    from research_observatory_core.plugin_worker import PluginWorkerProblem
    from research_observatory_core.ports.plugin_jobs import PluginJobRepositoryProblem
    from research_observatory_core.storage import open_canonical_database

    from tests.connectors.test_connector_authority import ConnectorAuthorityFixture
    from tests.connectors.test_plugin_broker import streamed

    check = unittest.TestCase()

    def stage(label: str) -> None:
        print("RO-S05-STAGE:" + label, flush=True)

    stage("select-real-runtime")
    check.assertFalse(InstalledPluginRuntime().available())
    selected = SignedCoreFixtureRuntime()
    calls: list[tuple[str | None, str | None]] = []
    entered, release = threading.Event(), threading.Event()
    sample = REPO / "docs/developer/sample_repository"
    cases = [json.loads((sample / f"fixtures/search-page-{i}.case.json").read_bytes()) for i in (1, 2)]

    def respond(request: httpx2.Request) -> httpx2.Response:
        check.assertEqual("GET", request.method)
        check.assertEqual("repository.example.invalid", request.url.host)
        check.assertNotIn("authorization", request.headers)
        query = request.url.params.get("query")
        calls.append((query, request.url.params.get("cursor")))
        if query == "synthetic-cancel":
            entered.set()
            check.assertTrue(release.wait(15), "cancel fixture was not released")
        if query == "synthetic-error":
            return streamed(httpx2.Response(200, json={"unexpected": True}))
        return streamed(
            httpx2.Response(200, json=cases[1 if request.url.params.get("cursor") else 0]["brokerResponse"])
        )

    def broker(**kwargs: Any) -> PluginNetworkBroker:
        return PluginNetworkBroker(**kwargs, transport_factory=lambda *_: httpx2.MockTransport(respond))

    directory = directory.resolve(strict=True)
    check.assertEqual((REPO / "artifacts/tmp").resolve(strict=True), directory.parent)
    check.assertFalse(directory.is_symlink() or directory.is_junction())
    vault = directory / "vault"
    bearer = secrets.token_hex(32)
    with patch.object(core_main, "InstalledPluginRuntime", return_value=selected):
        app = core_main.create_runtime_app(
            settings=CoreSettings(),
            profile_vault_root=vault,
            workflow_context=NativeWorkflowContext(secrets.token_hex(16), secrets.token_hex(16)),
            capability_digest=capability_token_digest(bearer),
            expected_authority="127.0.0.1:49152",
        )
    client = TestClient(
        app,
        base_url="http://127.0.0.1:49152",
        headers={"Authorization": "Bearer " + bearer},
        client=("127.0.0.1", 50000),
    )
    state_file = directory / "synthetic-state.json"
    if phase == "crash-denied":
        crash_state = json.loads(state_file.read_bytes())
        crash_root = Path(crash_state["root"]).resolve(strict=True)
        check.assertEqual(directory, crash_root.parent)

        def project_bytes() -> dict[str, str]:
            return {
                path.relative_to(crash_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in crash_root.rglob("*")
                if path.is_file()
            }

        before = project_bytes()
        check.assertIn(".locks/session.lock", before)
        with client as http:
            denied = http.post("/projects/open", json={"root": str(crash_root)})
            check.assertEqual(409, denied.status_code)
            check.assertEqual("RO-CORE-PROJECT-ALREADY-OPEN", denied.json()["code"])
        check.assertEqual(before, project_bytes())
        check.assertEqual(2, len(crash_state["pageInvocations"]))
        print(
            "RO-S05-PROTECTED-JOURNEY:"
            + json.dumps(
                {
                    "phase": phase,
                    "ok": True,
                    "foreignLockDenied": True,
                    "projectBytesUnchanged": True,
                    "preservedProjectFiles": len(before),
                    "retainedPageReferences": 2,
                }
            ),
            flush=True,
        )
        return
    with (
        patch("research_observatory_core.connectors.plugin_dispatch.PluginNetworkBroker", side_effect=broker),
        client as http,
    ):
        if phase == "create":
            created = http.post(
                "/projects",
                json={
                    "parentDirectory": str(directory),
                    "directoryName": "synthetic-project",
                    "displayName": "Synthetic plugin project",
                    "primaryUseCase": "theory-synthesis",
                    "researchObjective": "Synthetic metadata inspection",
                },
            )
            check.assertEqual(200, created.status_code)
            root, project_id = created.json()["root"], created.json()["projectId"]
            state: dict[str, Any] = {"root": root, "projectId": project_id}
        else:
            state = json.loads(state_file.read_bytes())
            root, project_id = state["root"], state["projectId"]
        check.assertEqual(directory, Path(root).resolve(strict=True).parent)
        check.assertEqual(200, http.post("/projects/open", json={"root": root}).status_code)
        stage("project-opened")
        runtime = app.state.runtime
        admin, consent, worker = runtime.plugin_admin, runtime.plugin_consent, runtime.plugin_worker
        check.assertIsNotNone(admin)
        check.assertIsNotNone(consent)
        check.assertIsNotNone(worker)
        assert admin is not None and consent is not None and worker is not None
        actor = admin.actor("a" * 32)

        def published_page(invocation_id):
            # Production adapters run beneath the open-project guard. Reading
            # encrypted input outside it reverses project/database lock order
            # against the actual background pumps and is not a valid fixture.
            return worker._action(
                root, lambda binding: binding.adapters.jobs.result(binding.adapters.jobs.input(invocation_id))
            )

        def wait(job_id, expected):
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                status = worker.status(root, project_id, job_id)
                if status.state in {"succeeded", "failed", "cancelled"}:
                    check.assertEqual(expected, status.state)
                    return status
                time.sleep(0.05)
            check.fail("protected plugin job did not reach terminal state")

        def persisted_pages():
            pages: list[PluginPublishedPage] = []
            for identity in state["pageInvocations"]:
                page = published_page(identity)
                check.assertIsInstance(page, PluginPublishedPage)
                assert isinstance(page, PluginPublishedPage)
                pages.append(page)
            first, second = pages
            check.assertEqual(
                ("next-page", "page-2", "exhausted"), (first.continuation, first.next_cursor, second.continuation)
            )
            check.assertEqual(["plugin.sample.repository"] * 2, [page.plan.source_id for page in pages])
            check.assertEqual(["plugin.sample.repository"] * 2, [page.records[0].provider_id for page in pages])
            check.assertEqual(first.retrieved_at, first.records[0].retrieved_at)
            check.assertEqual("not-reported", first.records[0].terms.license.state)
            check.assertEqual("reported", second.records[0].terms.license.state)
            check.assertEqual("CC0-1.0", second.records[0].terms.license.value)
            check.assertEqual([False, False], [page.broker_responses[0].redacted for page in pages])

            def canonical_metadata(binding):
                check.assertEqual(project_id, binding.project_id)
                with open_canonical_database(
                    Path(root) / "state/project.sqlite3", expected_project_id=project_id
                ) as database:
                    rights = database.execute(
                        "SELECT rights_status FROM aggregate_revisions WHERE project_id=? AND revision_id IN (?,?)",
                        (project_id, first.revision_id, second.revision_id),
                    ).fetchall()
                    lineage = database.execute(
                        "SELECT related_revision_id FROM provenance_ledger_relations "
                        "WHERE project_id=? AND relation_type='wasDerivedFrom' AND entity_revision_id=?",
                        (project_id, second.revision_id),
                    ).fetchall()
                return rights, lineage

            rights, lineage = worker._action(root, canonical_metadata)
            check.assertEqual(["unknown", "unknown"], [row[0] for row in rights])
            check.assertIn(first.revision_id, {row[0] for row in lineage})
            check.assertNotEqual(b"SQLite format 3\x00", (Path(root) / "state/project.sqlite3").read_bytes()[:16])
            for identity, page in zip(state["pageInvocations"], pages, strict=True):
                check.assertEqual(state["pageRevisions"][identity], page.revision_id)
                check.assertEqual("succeeded", worker.status(root, project_id, state["pageJobs"][identity]).state)
            return pages

        if phase in {"reopen", "crash"}:
            check.assertEqual(state["actorId"], actor.actor_id)
            grant = admin.current_grant_persisted(root, project_id, "sample.repository")
            assert grant is not None
            check.assertEqual(state["enabledGrant"], grant.model_dump(mode="json"))
            persisted_pages()
            check.assertEqual("cancelled", wait(state["pendingJob"], "cancelled").state)
            check.assertIsNone(published_page(state["pendingInvocation"]))
            for preview in state["oldPreviews"]:
                with check.assertRaises(PluginConsentProblem):
                    consent.authority(root, preview)
            check.assertEqual([], calls)
            check.assertEqual([], selected.actual_results)
            if phase == "crash":
                print(
                    "RO-S05-PROTECTED-JOURNEY:"
                    + json.dumps(
                        {"phase": phase, "ok": True, "durablePages": 2, "ownedSessionCrash": True, "egressCalls": 0}
                    ),
                    flush=True,
                )
                os._exit(0)  # Retain this owned lock; the next process must deny takeover.
            check.assertEqual(200, http.post("/projects/close", json={"root": root}).status_code)
            print(
                "RO-S05-PROTECTED-JOURNEY:"
                + json.dumps(
                    {"phase": phase, "ok": True, "durablePages": 2, "lostConsentCancelled": True, "egressCalls": 0}
                ),
                flush=True,
            )
            return

        authority = ConnectorAuthorityFixture("runTest")
        assert runtime.intents is not None and runtime.privacy is not None
        authority.root, authority.service, authority.privacy = root, runtime.intents, runtime.privacy
        authority.intent(providers=("plugin.sample.repository",))
        authority.policy()
        stage("intent-and-policy-accepted")
        key = SigningKey(b"\x5d" * 32)
        raw_manifest = (sample / "manifest.json").read_bytes()
        container = io.BytesIO()
        with zipfile.ZipFile(container, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", raw_manifest)
            archive.writestr("manifest.sig", key.sign(raw_manifest).signature)
            archive.writestr("plugin/connector.py", (sample / "plugin/connector.py").read_bytes())
        raw_package = container.getvalue()
        session = admin.context(root, project_id)
        intake = admin.create(root, project_id, session)
        admin.chunk(root, project_id, session, intake.intake_id, 1, raw_package)
        sealed = admin.seal(
            root,
            project_id,
            session,
            intake.intake_id,
            archive_sha256="sha256:" + hashlib.sha256(raw_package).hexdigest(),
            byte_length=len(raw_package),
            chunk_count=1,
            trace_id=actor.trace_id,
        )
        check.assertIsNotNone(sealed.review)
        check.assertIsNotNone(sealed.package_token)
        assert sealed.review is not None and sealed.package_token is not None
        stage("package-sealed")
        public_key = bytes(key.verify_key)
        trust_decision = PluginTrustDecision(
            new_uuid_v7(),
            sealed.review.publisher_key_id,
            "sha256:" + hashlib.sha256(public_key).hexdigest(),
            None,
            "trust",
        )
        system = PluginGrantActor(actor.actor_id, actor.trace_id, actor.occurred_at, actor_type="system")
        with check.assertRaisesRegex(PluginGrantProblem, "plugin-grant-actor-invalid"):
            admin.trust_decide(root, project_id, session, trust_decision, public_key, actor=system)
        trusted = admin.trust_decide(root, project_id, session, trust_decision, public_key, actor=actor)
        reviewed = admin.review(root, project_id, session, sealed.package_token, trace_id=actor.trace_id).review
        assert reviewed is not None and trusted.public_key_sha256 is not None and trusted.revision is not None
        confirmation = PluginEnableConfirmation(
            action_id=new_uuid_v7(),
            project_id=project_id,
            plugin_id=reviewed.plugin_id,
            plugin_version=reviewed.plugin_version,
            publisher_key_id=reviewed.publisher_key_id,
            trusted_key_sha256=trusted.public_key_sha256,
            trusted_key_revision=trusted.revision,
            package_sha256=reviewed.package_sha256,
            manifest_sha256=reviewed.manifest_sha256,
            permissions=reviewed.permissions,
            destinations=reviewed.destinations,
            operations=reviewed.operations,
            data_classes=reviewed.data_classes,
            credential_scopes=reviewed.credential_scopes,
            expected_revision=None,
        )
        with check.assertRaisesRegex(PluginGrantProblem, "plugin-grant-actor-invalid"):
            admin.enable(root, project_id, session, sealed.package_token, confirmation, actor=system)
        check.assertIsNone(admin.current_grant_persisted(root, project_id, reviewed.plugin_id))
        check.assertEqual(
            "enabled", admin.enable(root, project_id, session, sealed.package_token, confirmation, actor=actor).status
        )
        enabled_grant = admin.current_grant_persisted(root, project_id, reviewed.plugin_id)
        assert enabled_grant is not None
        retention = ConnectorRetention.model_validate(
            {
                "rights": {
                    purpose: {"value": "permitted", "basis": "researcher-confirmed"} for purpose in ("store", "inspect")
                },
                "retainBody": True,
            }
        )
        state.update(
            actorId=actor.actor_id,
            enabledGrant=enabled_grant.model_dump(mode="json"),
            pageInvocations=[],
            pageRevisions={},
            pageJobs={},
            oldPreviews=[],
        )
        stage("human-grant-enabled")

        def prepare(document, *, confirm=True):
            wire = json.dumps(document, separators=(",", ":")).encode()
            request = PluginInvocationRequest(
                project_id=project_id,
                invocation_id=new_uuid_v7(),
                scientific_request_sha256="sha256:" + hashlib.sha256(wire).hexdigest(),
                operation="search",
                destination=reviewed.destinations[1],
            )
            preview = consent.preview(
                root,
                project_id,
                reviewed.package_sha256,
                reviewed.manifest_sha256,
                sealed.review.signature_sha256,
                request,
                retention,
                actor=actor,
            )
            state["oldPreviews"].append(preview.preview_id)
            if confirm:
                consent.confirm(root, project_id, preview.preview_id, confirmation=preview.confirmation)
            return request, wire, preview

        plaintext: list[bytes] = []
        for index, case in enumerate(cases):
            document = dict(case["input"])
            if index:
                document["previousInvocationId"] = state["pageInvocations"][0]
            request, wire, preview = prepare(document, confirm=False)
            with check.assertRaises(PluginConsentProblem):
                worker.submit(root, preview.preview_id, request, wire)
            consent.confirm(root, project_id, preview.preview_id, confirmation=preview.confirmation)
            job = worker.submit(root, preview.preview_id, request, wire)
            stage(f"page-{index + 1}-submitted")
            wait(job.job_id, "succeeded")
            stage(f"page-{index + 1}-published")
            page = published_page(request.invocation_id)
            check.assertIsInstance(page, PluginPublishedPage)
            assert isinstance(page, PluginPublishedPage)
            state["pageInvocations"].append(request.invocation_id)
            state["pageRevisions"][request.invocation_id] = page.revision_id
            state["pageJobs"][request.invocation_id] = job.job_id
            plaintext.append(wire)
        check.assertEqual(2, len(calls))
        check.assertEqual([None, "page-2"], [cursor for _, cursor in calls])
        check.assertEqual(2, len(selected.actual_results))
        persisted_pages()
        stage("two-pages-verified")
        request, wire, preview = prepare(
            dict(cases[1]["input"], cursor="forged-cursor", previousInvocationId=state["pageInvocations"][0])
        )
        with check.assertRaisesRegex(PluginWorkerProblem, "page-predecessor-denied"):
            worker.submit(root, preview.preview_id, request, wire)
        with check.assertRaises(PluginJobRepositoryProblem):
            worker._action(root, lambda binding: binding.adapters.jobs.input(request.invocation_id))
        check.assertEqual(2, len(calls))
        request, wire, preview = prepare({"query": "synthetic-error", "pageSize": 1})
        job = worker.submit(root, preview.preview_id, request, wire)
        failed = wait(job.job_id, "failed")
        stage("malformed-page-denied")
        check.assertIsNotNone(failed.diagnostic_code)
        check.assertIsNone(published_page(request.invocation_id))
        request, wire, preview = prepare({"query": "synthetic-cancel", "pageSize": 1})
        job = worker.submit(root, preview.preview_id, request, wire)
        try:
            check.assertTrue(entered.wait(40), "worker never reached synthetic broker")
            worker.cancel(root, project_id, job.job_id)
        finally:
            release.set()
        wait(job.job_id, "cancelled")
        stage("active-job-cancelled")
        check.assertIsNone(published_page(request.invocation_id))
        persisted_pages()
        physical = [path for path in (Path(root) / "objects").rglob("*") if path.is_file()]
        check.assertTrue(physical)
        for path in physical:
            for wire in plaintext:
                check.assertNotIn(wire, path.read_bytes())
        with worker._runner:
            request, wire, preview = prepare({"query": "synthetic-restart", "pageSize": 1})
            job = worker.submit(root, preview.preview_id, request, wire)
            check.assertEqual(0, worker.status(root, project_id, job.job_id).attempt_count)
            check.assertEqual("runnable", worker.status(root, project_id, job.job_id).state)
            state.update(pendingInvocation=request.invocation_id, pendingJob=job.job_id)
            state_file.write_bytes((json.dumps(state, indent=2) + "\n").encode())
            # Hold only the test runner gate so the durable job stays unstarted
            # until the real close route signals/drains workers and releases its
            # own session. No stale-lock recovery or lock-file removal is used.
            check.assertEqual(200, http.post("/projects/close", json={"root": root}).status_code)
        check.assertFalse((Path(root) / ".locks/session.lock").exists())
        print(
            "RO-S05-PROTECTED-JOURNEY:"
            + json.dumps(
                {
                    "phase": phase,
                    "ok": True,
                    "durablePages": 2,
                    "egressCalls": len(calls),
                    "forgedCursorDenied": True,
                    "malformedPageDenied": True,
                    "activeCancellation": True,
                    "orderlyCloseWithDurableUnstartedJob": True,
                    "ownedLockReleased": True,
                }
            ),
            flush=True,
        )


@unittest.skipUnless(os.name == "nt", "Windows DPAPI/SQLCipher and signed LPAC integration")
class ProtectedSampleCoreJourneyTests(unittest.TestCase):
    def test_signed_sample_protected_core_orderly_restart_and_crash_open_denial(self) -> None:
        required = ("RO_W2_SIGNED_WORKER_BUILD", "RO_W2_CORE_SIDECAR_GUARDIAN", "RO_W2_CORE_SIDECAR_GUARDIAN_SHA256")
        if not all(os.environ.get(name) for name in required):
            self.skipTest("explicit signed worker and hash-bound frozen guardian are required")
        scratch = (REPO / "artifacts/tmp").resolve(strict=True)
        directory = Path(tempfile.mkdtemp(prefix="s05-protected-journey-", dir=scratch)).resolve(strict=True)
        # Retain the owned protected fixture and all child output for review,
        # including failures. No automatic teardown erases adverse evidence.
        for phase in ("create", "reopen", "crash", "crash-denied"):
            command = [sys.executable, "-B", __file__, "--protected-core-phase", phase, "--scratch", str(directory)]
            try:
                started = time.monotonic()
                completed = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=180, check=False)
            except subprocess.TimeoutExpired as error:
                for suffix, output in (("stdout", error.stdout), ("stderr", error.stderr)):
                    raw = output.encode() if isinstance(output, str) else output or b""
                    (directory / f"{phase}.{suffix}.log").write_bytes(raw)
                raise
            (directory / f"{phase}.stdout.log").write_text(completed.stdout, encoding="utf-8")
            (directory / f"{phase}.stderr.log").write_text(completed.stderr, encoding="utf-8")
            self.assertEqual(0, completed.returncode, f"protected phase {phase} failed; owned private logs retained")
            markers = [
                line.removeprefix("RO-S05-PROTECTED-JOURNEY:")
                for line in completed.stdout.splitlines()
                if line.startswith("RO-S05-PROTECTED-JOURNEY:")
            ]
            self.assertEqual(1, len(markers))
            report = json.loads(markers[0])
            self.assertEqual(phase, report["phase"])
            self.assertIs(report["ok"], True)
            if phase == "crash-denied":
                self.assertIs(report["foreignLockDenied"], True)
                self.assertIs(report["projectBytesUnchanged"], True)
                self.assertEqual(2, report["retainedPageReferences"])
            else:
                self.assertEqual(2, report["durablePages"])
            report["durationSeconds"] = round(time.monotonic() - started, 3)
            print("RO-S05-PROTECTED-JOURNEY:" + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    if "--protected-core-phase" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--protected-core-phase", choices=("create", "reopen", "crash", "crash-denied"), required=True
        )
        parser.add_argument("--scratch", type=Path, required=True)
        arguments = parser.parse_args()
        protected_core_phase(arguments.scratch, arguments.protected_core_phase)
    else:
        unittest.main()
