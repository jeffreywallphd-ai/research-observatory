"""Real Windows native supervisor, Core, protected persistence and browser client."""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright

from tests.reconciliation.native_fixture import prepare
from tests.reconciliation.test_renderer import RendererHarness

REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "nt", "Windows native supervisor, DPAPI and SQLCipher required")
class NativeReconciliationRendererTests(RendererHarness):
    def test_native_review_retry_reversal_and_restart_preserve_protected_history(self):
        directory = Path(tempfile.mkdtemp(prefix="reconciliation-native-", dir=REPO / "artifacts/tmp"))
        project = prepare(directory)
        session = directory / "session"
        session.mkdir()
        sys.path.insert(0, str(REPO / "tools"))
        from desktop_app_check import tool_environment

        env, _, cargo = tool_environment(REPO)
        build = subprocess.run(
            [
                str(cargo),
                "build",
                "--locked",
                "--offline",
                "--features",
                "integration-harness",
                "--example",
                "supervised_core_harness",
            ],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.assertEqual(0, build.returncode, build.stdout + build.stderr)
        python_path = os.pathsep.join(
            str(REPO / item) for item in ("tests/service/fixtures", "services/core-api/src", ".venv/Lib/site-packages")
        )
        stderr = self.enterContext((directory / "native-stderr.log").open("w", encoding="utf-8"))
        process = subprocess.Popen(
            [
                str(REPO / "target/debug/examples/supervised_core_harness.exe"),
                getattr(sys, "_base_executable", sys.executable),
                str(REPO),
                python_path,
                str(directory / "vault"),
                str(session),
            ],
            cwd=REPO,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            encoding="utf-8",
        )
        self.addCleanup(self.stop_process, process)
        replies: queue.Queue[dict[str, Any]] = queue.Queue()
        stdin, stdout = process.stdin, process.stdout
        assert stdin is not None and stdout is not None

        def read():
            for line in stdout:
                replies.put(json.loads(line))
            replies.put({"kind": "closed"})

        threading.Thread(target=read, daemon=True).start()

        def exchange(value):
            stdin.write(json.dumps(value) + "\n")
            stdin.flush()
            return replies.get(timeout=30)

        self.assertEqual("ready", replies.get(timeout=30)["kind"])
        requests = []

        def transport(request):
            requests.append(request)
            reply = exchange(request)
            if reply["kind"] != "response":
                raise AssertionError(f"Native transport rejected the request: {reply.get('code', reply['kind'])}")
            return reply["response"]

        def post(route, body):
            response = transport(
                {"method": "POST", "path": route, "body": json.dumps(body), "ifMatch": None, "idempotencyKey": None}
            )
            self.assertEqual(200, response["status"], route)
            return json.loads(response["body"])

        post("/projects/open", {"root": project["root"]})
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            self.addCleanup(lambda: browser.close() if browser.is_connected() else None)
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            page.set_default_timeout(15000)
            page.expose_function("coreExchange", transport)
            page.goto(f"http://127.0.0.1:{self.server.server_port}/")
            page.evaluate(
                "project => window.mount(project)", {"root": project["root"], "projectId": project["projectId"]}
            )
            page.get_by_role("button", name="Generate duplicate candidates", exact=True).click()
            page.get_by_role("button", name="Compare candidate 1", exact=True).click()
            expect(page.get_by_role("heading", name="Compare source assertions", exact=True)).to_be_focused()
            self.assertEqual(3, page.get_by_role("checkbox").count())
            page.get_by_role("checkbox").last.check()
            page.get_by_label("Decision rationale", exact=True).fill(
                "Synthetic native split, retaining every source assertion."
            )
            page.get_by_role("button", name="Preview decision and affected objects", exact=True).click()
            page.evaluate("() => { window.flags.dropCommit = true; }")
            page.get_by_role("button", name="Apply reviewed decision", exact=True).click()
            page.get_by_role("button", name="Retry same decision", exact=True).click()
            expect(page.get_by_role("heading", name="Decision saved", exact=True)).to_be_focused()
            page.get_by_role("button", name="Review resulting Works or reverse the grouping", exact=True).click()
            expect(page.get_by_label("Action", exact=True)).to_have_value("merge")
            page.get_by_role("button", name="Preview decision and affected objects", exact=True).click()
            page.get_by_role("button", name="Apply reviewed decision", exact=True).click()
            expect(page.get_by_role("heading", name="Decision saved", exact=True)).to_be_focused()
            commands = [
                json.loads(request["body"])["command"]
                for request in requests
                if request["path"].endswith("review/commit")
            ]
            self.assertEqual(3, len(commands))
            self.assertEqual(commands[0], commands[1])
            saved = page.evaluate(
                "async value => await window.reconciliationClient.commitScholarlyReview(value)",
                {"root": project["root"], "command": commands[-1]},
            )
            page.evaluate("() => window.clearProtectedState()")
            self.assertEqual("restarted", exchange({"control": "restart"})["kind"])
            post("/projects/open", {"root": project["root"]})
            replay = page.evaluate(
                "async value => await window.reconciliationClient.commitScholarlyReview(value)",
                {"root": project["root"], "command": commands[-1]},
            )
            self.assertEqual(saved, replay)
            active = next(work for work in replay["workStates"] if work["disposition"] == "active")
            context = page.evaluate(
                "async value => await window.reconciliationClient.inspectScholarlyReviewContext(value)",
                {"root": project["root"], "workIds": [active["workId"]], "unassignedAssertionRevisionIds": []},
            )
            self.assertEqual(3, len(context["sources"]))
            self.assertEqual(1, len(context["inboundAliases"]))
            self.assertEqual(
                {"import-member", "connector-record"},
                {source["assertion"]["address"]["kind"] for source in context["sources"]},
            )
            self.assertEqual(
                "error",
                exchange(
                    {
                        "method": "POST",
                        "path": "/projects/reconciliation/review/commit",
                        "body": json.dumps(
                            {"root": project["root"], "command": commands[-1], "actorId": active["workId"]}
                        ),
                        "ifMatch": None,
                        "idempotencyKey": None,
                    }
                )["kind"],
            )
            page.screenshot(path=str(directory / "post-restart-cleared.png"))
            browser.close()
        post("/projects/close", {"root": project["root"]})
        self.stop_process(process)
        self.assertEqual(0, process.returncode)
        self.assertNotEqual(b"SQLite format 3\x00", (Path(project["root"]) / "state/project.sqlite3").read_bytes()[:16])
        report = {
            "fixtureKind": "synthetic-accepted-import-and-retained-connector",
            "nativeSupervisor": True,
            "generatedClient": True,
            "productionReviewComponents": True,
            "dpapiAndSqlcipher": True,
            "sameCommandRetry": True,
            "splitAndMerge": True,
            "restartPreserved": True,
            "nativeAuthorityInjectionDenied": True,
            "retainedSourceCount": len(context["sources"]),
            "providerNetworkDuringNativeReview": 0,
        }
        (directory / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report": (directory / "result.json").relative_to(REPO).as_posix()}), flush=True)

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
