"""Small real-process protected restart proof, not a native/package/crash benchmark."""

import base64
import hashlib
import json
import multiprocessing
import os
import secrets
import tempfile
import threading
import time
import traceback
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights

from tests.service import test_import_review_scale_windows as scale
from tests.service.test_import_commit_scale_windows import _commit_facts


def _post(client, route, body):
    result = client.post(route, json=body)
    if result.status_code != 200:
        raise AssertionError(f"{route}: HTTP {result.status_code}")
    return result.json()


def _wait(project_root, project_id, job_id):
    queue = scale.sqlite_workflow_queue_repository(Path(project_root), project_id)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        job = queue.get(job_id)
        if job.state in {"succeeded", "failed", "cancelled"}:
            if job.state != "succeeded":
                raise AssertionError(f"worker {job.state}: {job.diagnostic_code}")
            return
        time.sleep(0.05)
    raise AssertionError("small restart fixture did not finish within 25 seconds")


def _child(fixture, phase, state, sender):
    fixture = Path(fixture)
    with (fixture / f"{phase}.log").open("w", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
        try:
            result = _run_phase(fixture, phase, state)
            sender.send({"ok": True, "pid": os.getpid(), "state": result})
        except BaseException as error:
            traceback.print_exc()
            sender.send({"ok": False, "errorType": type(error).__name__})
            raise
        finally:
            sender.close()


def _run_phase(fixture, phase, state):
    h = scale.ImportReviewScaleWindowsTests(methodName="runTest")
    h.vault, h.epoch, h.capability = fixture / "vault", state["epoch"], secrets.token_hex(32)
    with h._client() as client:
        if phase == "interrupt":
            created = _post(
                client,
                "/projects",
                {
                    "parentDirectory": str(fixture / "projects"),
                    "directoryName": "synthetic-restart",
                    "displayName": "Synthetic restart",
                    "primaryUseCase": "theory-synthesis",
                    "researchObjective": "Synthetic import restart proof",
                },
            )
            state.update(root=created["root"], projectId=created["projectId"])
        else:
            facts = _commit_facts(Path(state["root"]) / "state/project.sqlite3", state["projectId"])
            expected = 0 if phase == "recover" else 1
            assert facts["counts"]["import_source_records"] == expected
            assert facts["counts"]["import_manifests"] == expected
            assert facts["acceptedCommitOutputs"] == expected
        _post(client, "/projects/open", {"root": state["root"]})
        if phase == "interrupt":
            project = {"root": state["root"], "projectId": state["projectId"]}
            native = {**project, **_post(client, "/native/imports/context", project)}
            granted = ImportPermission(value="permitted", basis="researcher-confirmed")
            preview = _post(
                client,
                "/native/imports/create",
                {
                    **native,
                    "sourceName": "synthetic-restart.csv",
                    "formatName": "csv",
                    "encoding": "utf-8",
                    "delimiter": ",",
                    "rights": ImportRights(store=granted, inspect=granted).model_dump(by_alias=True),
                },
            )
            state["previewId"] = preview["previewId"]
            native["previewId"] = state["previewId"]
            source = b"title,doi\nSynthetic restart record,10.99999/restart-fixture\n"
            _post(client, "/native/imports/chunk", {**native, "ordinal": 1, "data": base64.b64encode(source).decode()})
            _post(
                client,
                "/native/imports/seal",
                {
                    **native,
                    "sourceSha256": hashlib.sha256(source).hexdigest(),
                    "byteLength": len(source),
                    "chunkCount": 1,
                },
            )
            scheduled = _post(client, "/native/imports/schedule", native)
            _wait(state["root"], state["projectId"], scheduled["jobId"])
        public = {"root": state["root"], "previewId": state["previewId"]}
        if phase == "interrupt":
            _post(client, "/projects/imports/begin-review", public)
            prepared = _post(client, "/projects/imports/commit/prepare", {**public, "revision": 1})
            state["requestId"] = prepared["requestId"]
            entered = threading.Event()

            def pause_after_write(step):
                if step == "source-record-created":
                    entered.set()
                    # Test scheduling seam only. The actual close route supplies
                    # the stop signal and the real protected writer rolls back.
                    active = client.app.state.runtime.imports._publications[Path(state["root"])]
                    assert active.requested.wait(5), "close did not signal publication"

            with patch(
                "research_observatory_core.import_commit_repository._publication_step_completed", pause_after_write
            ):
                scheduled = _post(
                    client, "/projects/imports/commit/start", {**public, "revision": 1, "requestId": state["requestId"]}
                )
                state["jobId"] = scheduled["jobId"]
                assert entered.wait(10), "worker never entered the real atomic writer"
                _post(client, "/projects/close", {"root": state["root"]})
            facts = _commit_facts(Path(state["root"]) / "state/project.sqlite3", state["projectId"])
            assert all(
                facts["counts"][name] == 0
                for name in (
                    "import_source_records",
                    "import_manifests",
                    "import_manifest_members",
                    "import_manifest_seals",
                )
            )
            assert facts["acceptedCommitOutputs"] == 0
            assert facts["attempts"] == [{"attempt": 1, "state": "failed", "diagnosticCode": "dependency-unavailable"}]
            state["interruptedFacts"] = facts
        else:
            # The native resume epoch is intentionally retained across these
            # Core processes; each Core/native instance and project session is new.
            # Reopen restores only existing authorized work, not a synthetic job.
            _wait(state["root"], state["projectId"], state["jobId"])
            latest = _post(client, "/projects/imports/commit/latest", public)
            assert latest["requestId"] == state["requestId"]
            assert latest["jobId"] == state["jobId"]
            assert latest["jobState"] == "succeeded"
            if phase == "replay":
                assert latest["manifest"] == state["manifest"]
            state["manifest"] = latest["manifest"]
            replay = _post(
                client, "/projects/imports/commit/start", {**public, "revision": 1, "requestId": state["requestId"]}
            )
            assert replay["manifest"] == latest["manifest"]
            facts = _commit_facts(Path(state["root"]) / "state/project.sqlite3", state["projectId"])
            assert facts["counts"]["import_source_records"] == 1
            assert facts["counts"]["import_manifests"] == 1
            assert facts["counts"]["import_manifest_members"] == 2
            assert facts["counts"]["import_manifest_seals"] == 1
            assert facts["acceptedCommitOutputs"] == 1
            assert facts["attempts"] == [
                {"attempt": 1, "state": "failed", "diagnosticCode": "dependency-unavailable"},
                {"attempt": 2, "state": "succeeded", "diagnosticCode": None},
            ]
            state[phase + "Facts"] = facts
            _post(client, "/projects/close", {"root": state["root"]})
    return state


@unittest.skipUnless(os.name == "nt", "real Windows DPAPI/SQLCipher process restart")
class ImportCommitProcessWindowsTests(unittest.TestCase):
    def test_interrupted_publication_recovers_across_processes_and_replays_once(self):
        scratch = scale.REPO / "artifacts/tmp"
        self.assertEqual(scratch.absolute(), scratch.resolve(strict=True))
        fixture = Path(tempfile.mkdtemp(prefix="import-commit-process-", dir=scratch))
        (fixture / "vault").mkdir()
        (fixture / "projects").mkdir()
        state, pids = {"epoch": secrets.token_hex(16)}, []
        report = {"outcome": "running", "head": scale._head(), "phases": [], "fixturesRetained": True}
        report_path = fixture / "result.json"
        started = time.monotonic()
        try:
            spawn = multiprocessing.get_context("spawn")
            for phase in ("interrupt", "recover", "replay"):
                receiver, sender = spawn.Pipe(duplex=False)
                child = spawn.Process(target=_child, args=(str(fixture), phase, state, sender))
                child.start()
                sender.close()
                try:
                    self.assertTrue(receiver.poll(45), f"{phase}: no child result; inspect confined fixture log")
                    result = receiver.recv()
                    child.join(5)
                    self.assertFalse(child.is_alive(), f"{phase}: child did not exit")
                    self.assertTrue(result["ok"], result.get("errorType"))
                    self.assertEqual(0, child.exitcode)
                    pids.append(result["pid"])
                    state = result["state"]
                    report["phases"].append({"phase": phase, "exitCode": child.exitcode})
                finally:
                    if child.is_alive():
                        child.terminate()  # Only the exact test-owned child.
                        child.join(5)
                    receiver.close()
            self.assertEqual(3, len(set(pids)))
            self.assertEqual(1, state["interruptedFacts"]["attempts"][0]["attempt"])
            self.assertEqual(state["recoverFacts"], state["replayFacts"])
            report.update(outcome="passed", distinctProcesses=3, facts=state["replayFacts"])
        except BaseException as error:
            report.update(outcome="failed", failureType=type(error).__name__)
            raise
        finally:
            report["elapsedSeconds"] = time.monotonic() - started
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"outcome": report["outcome"], "fixture": fixture.relative_to(scale.REPO).as_posix()}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
