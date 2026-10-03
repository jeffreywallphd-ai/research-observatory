"""Mounted selected-version renderer and opaque native-port behavior.

The normal version context comes from a disposable Core project. Synthetic
two-Work and stale-revision responses retain the generated reply fingerprint.
Attachment outcomes are synthetic; this does not qualify native file admission,
OS drop or Core attachment persistence.
"""

from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "services/core-api/src"))

from desktop_app_check import (  # noqa: E402
    DIRECTORY_PICKER_FIXTURE,
    choose_fixture_directory,
    core_workflow_catalog_json,
    inline_product_index,
)

from tests.reconciliation import test_version_api as version_fixture  # noqa: E402

ATTACHMENT_HOST = r""";
(() => {
  const prior = window.__TAURI_INTERNALS__.invoke;
  const callbacks = new Map();
  let callbackId = 100;
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {unregisterListener: () => {}};
  window.__TAURI_INTERNALS__.transformCallback = (callback, once) => {
    const id = ++callbackId;
    callbacks.set(id, callback);
    return id;
  };
  const selection = request => request.selection;
  const fingerprint = async value => {
    const canonical = item => Array.isArray(item) ? '[' + item.map(canonical).join(',') + ']'
      : item && typeof item === 'object'
      ? '{' + Object.keys(item).sort()
        .map(key => canonical(key) + ':' + canonical(item[key])).join(',') + '}'
      : JSON.stringify(item).replace(/[\u007f-\uffff]/g,
        char => '\\u' + char.charCodeAt(0).toString(16).padStart(4, '0'));
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(value)));
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2,'0')).join('');
  };
  const sessionId = 'a'.repeat(32);
  const candidateId = '01900000-0000-7000-8000-000000000080';
  const secondWorkId = 'f1900000-0000-7000-8000-000000000090';
  const secondWorkRevisionId = 'f1900000-0000-7000-8000-000000000091';
  const state = window.__ATTACH_TEST__ = {
    ready: false, begin: [], commit: [], cancel: [], status: [], failure: null,
    commitFailure: null, listener: null, lastEvent: null, durable: null, retryRequest: null,
    ambiguous: false, staleVersion: false, statusOverride: null,
    holdStatus: false, releaseStatus: null,
  };
  const emit = payload => {
    state.lastEvent = payload;
    const callback = callbacks.get(state.listener);
    if (callback) callback({event:'document_attachment_result', id:1, payload});
  };
  window.__EMIT_ATTACHMENT__ = emit;
  window.__EMIT_REPLACEMENT__ = () => {
    const request = state.begin.at(-1);
    emit({schemaVersion:'1.0', status:'candidate', operationId:request.operationId,
      sessionId, selection:selection(request),
      candidate:{candidateId:'01900000-0000-7000-8000-000000000083', sourceName:'replacement.pdf',
        byteLength:64, format:'pdf', confirmationSha256:'e'.repeat(64), confirmationRequired:true}});
  };
  window.__TAURI_INTERNALS__.invoke = async (command, args) => {
    if (command === 'application_lock_status')
      return {...await prior(command, args), signInMode:'windows-password', policyRevision:1};
    if (command === 'application_lock_now') {
      await window.__attachment_test_lock();
      return {...await prior('application_lock_status', {}), signInMode:'windows-password', policyRevision:1,
        state:'locked', profileName:null, reason:'manual', auditSequence:1};
    }
    if (command === 'application_lock_unlock')
      return {schemaVersion:'1.0', outcome:'succeeded', reasonCode:'RO-LOCK-UNLOCKED',
        snapshot:{...await prior('application_lock_status', {}), signInMode:'windows-password', policyRevision:1,
          state:'unlocked', reason:null, auditSequence:2}};
    if (command === 'plugin:event|listen' && args.event === 'document_attachment_result') {
      state.listener = args.handler;
      return 1;
    }
    if (command === 'plugin:event|unlisten' && args.event === 'document_attachment_result') {
      callbacks.delete(state.listener);
      state.listener = null;
      return;
    }
    if (command === 'core_api_request') {
      const route = args.request.path;
      const versionContext = route.includes('/reconciliation/versions/context');
      const versionWorks = route.includes('/reconciliation/versions/works');
      let requestArgs = args;
      if (state.ambiguous && versionContext) {
        const body = JSON.parse(args.request.body);
        body.workIds = [state.begin[0].selection.workId];
        requestArgs = {request:{...args.request, body:JSON.stringify(body)}};
      }
      const response = await window.__attachment_test_native(command, requestArgs);
      if (versionContext) state.lastContextStatus = response.status;
      if (response.status !== 200 || !versionContext && !versionWorks) return response;
      const body = JSON.parse(response.body);
      if (state.ambiguous && versionWorks) body.items.push({...body.items[0], workId:secondWorkId,
        revisionId:secondWorkRevisionId});
      if (state.ambiguous && versionContext) {
        body.works.push({...body.works[0], workId:secondWorkId, revisionId:secondWorkRevisionId});
        body.preferenceStates.push({...body.preferenceStates[0], workId:secondWorkId});
        body.placements[0].state = 'requires-review';
        body.placements[0].workIds = [body.works[0].workId, secondWorkId];
      }
      if (state.staleVersion && versionContext) body.versions[0].revisionId = '01900000-0000-7000-8000-000000000092';
      if (versionContext && (state.ambiguous || state.staleVersion)) {
        const {contextSha256, ...context} = body;
        body.contextSha256 = await fingerprint(context);
      }
      if (versionContext) state.lastContextBody = body;
      return {...response, body:JSON.stringify(body)};
    }
    if (command === 'document_attachment_capabilities')
      return {schemaVersion:'1.0', status:state.ready ? 'ready' : 'unavailable', projectId:args.projectId};
    if (command === 'document_attachment_status') {
      const request = args.request;
      state.status.push(request);
      if (!state.ready) throw new Error('native attachment unavailable');
      if (state.holdStatus) await new Promise(resolve => { state.releaseStatus = resolve; });
      if (state.statusOverride
        && ['failed', 'cancelled', 'unavailable', 'denied'].includes(state.statusOverride.status))
        state.retryRequest = null;
      return state.statusOverride
        ? {schemaVersion:'1.0', status:state.statusOverride.status, selection:request.selection,
          operationId:request.operationId ?? '01900000-0000-7000-8000-000000000084',
          commandId:Object.hasOwn(state.statusOverride, 'commandId')
            ? state.statusOverride.commandId : request.commandId,
          attachmentId:state.statusOverride.attachmentId ?? null,
          documentRevisionId:state.statusOverride.documentRevisionId ?? null, code:state.statusOverride.code,
          retryRequest:state.statusOverride.retryRequest ?? null}
        : state.retryRequest && JSON.stringify(state.retryRequest.selection) === JSON.stringify(request.selection)
        ? {schemaVersion:'1.0', status:'unconfirmed', selection:request.selection,
          operationId:state.retryRequest.operationId, commandId:state.retryRequest.commandId,
          attachmentId:null, documentRevisionId:null, code:null, retryRequest:state.retryRequest}
        : state.durable && JSON.stringify(state.durable.selection) === JSON.stringify(request.selection)
        ? {...state.durable, operationId:request.operationId ?? state.durable.operationId,
          commandId:request.commandId ?? state.durable.commandId}
        : {schemaVersion:'1.0', status:'metadata-only', selection:request.selection,
          operationId:request.operationId, commandId:request.commandId,
          attachmentId:null, documentRevisionId:null, code:null, retryRequest:null};
    }
    if (command === 'document_attachment_begin') {
      const request = args.request;
      state.begin.push(request);
      if (!state.ready) return {schemaVersion:'1.0', status:'unavailable', operationId:request.operationId};
      const failure = state.failure;
      state.failure = null;
      setTimeout(() => emit(failure ? {
        schemaVersion:'1.0', status:'rejected', operationId:request.operationId,
        sessionId, selection:selection(request), code:failure,
      } : {
        schemaVersion:'1.0', status:'candidate', operationId:request.operationId,
        sessionId, selection:selection(request),
        candidate:{candidateId, sourceName:'synthetic.pdf', byteLength:42, format:'pdf',
          confirmationSha256:'d'.repeat(64), confirmationRequired:true},
      }), 0);
      return {schemaVersion:'1.0', status:'armed', operationId:request.operationId, sessionId};
    }
    if (command === 'document_attachment_cancel') { state.cancel.push(args.request); return; }
    if (command === 'document_attachment_commit') {
      const request = args.request;
      state.commit.push(request);
      if (state.commitFailure) {
        const code = state.commitFailure;
        state.commitFailure = null;
        if (code === 'throw') {
          state.retryRequest = request;
          throw new Error('simulated lost native reply');
        }
        state.retryRequest = null;
        return {schemaVersion:'1.0', status:'rejected', operationId:request.operationId,
          sessionId, selection:request.selection, code};
      }
      state.retryRequest = null;
      state.durable = {schemaVersion:'1.0', status:'processing', selection:request.selection,
        operationId:request.operationId, commandId:request.commandId,
        attachmentId:'01900000-0000-7000-8000-000000000081',
        documentRevisionId:'01900000-0000-7000-8000-000000000082', code:null, retryRequest:null};
      return {schemaVersion:'1.0', status:'attached', operationId:request.operationId,
        sessionId, selection:request.selection, candidateId:request.candidateId,
        attachmentId:'01900000-0000-7000-8000-000000000081',
        documentRevisionId:'01900000-0000-7000-8000-000000000082'};
    }
    return prior(command, args);
  };
})();"""


class DocumentAttachmentInteractionTests(unittest.TestCase):
    def test_selected_version_native_intents_denial_cancel_and_return(self):
        fixture = version_fixture.VersionApiTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        work = fixture.ok("works", after=None, limit=32)["items"][0]
        original = fixture.ok("context", workIds=[work["workId"]])
        plan = dict(
            schemaVersion="1.0",
            action="register",
            workIds=[work["workId"]],
            contextSha256=original["contextSha256"],
            rationale="Synthetic manifestation for UI test",
            definition=dict(
                kind="accepted-manuscript",
                assertionRevisionIds=work["assertionRevisionIds"],
                date=dict(precision="not-reported", value=None),
            ),
            version=None,
            relation=None,
            previousPreferenceRevisionId=None,
        )
        preview = fixture.ok("preview", plan=plan)
        fixture.ok(
            "commit",
            command=dict(commandId=preview["commandId"], plan=plan, expectedPreviewSha256=preview["previewSha256"]),
        )
        version = fixture.ok("context", workIds=[work["workId"]])["versions"][0]
        fixture.f.service.detach(fixture.f.root)
        closed = fixture.client.post("/projects/close", json={"root": fixture.f.root})
        self.assertEqual(200, closed.status_code, closed.text)

        def native(command, args):
            self.assertEqual("core_api_request", command)
            request = args["request"]
            headers = {"Content-Type": "application/json"}
            if request["ifMatch"] is not None:
                headers["If-Match"] = request["ifMatch"]
            if request["idempotencyKey"] is not None:
                headers["Idempotency-Key"] = request["idempotencyKey"]
            response = fixture.client.request(
                request["method"], request["path"], content=request["body"], headers=headers
            )
            return {
                "status": response.status_code,
                "contentType": response.headers["content-type"].split(";")[0],
                "traceId": response.headers["x-trace-id"],
                "etag": response.headers.get("etag"),
                "body": response.text,
            }

        def lock_native():
            fixture.f.service.detach(fixture.f.root)
            response = fixture.client.post("/projects/close", json={"root": fixture.f.root})
            self.assertEqual(200, response.status_code, response.text)
            return True

        script = (REPO / "tests/desktop/fixtures/task_center_interactions.js").read_text("utf-8")
        script = script.replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO))
        script += DIRECTORY_PICKER_FIXTURE + ATTACHMENT_HOST
        with sync_playwright() as playwright, ExitStack() as cleanup:
            browser = playwright.chromium.launch(headless=True)
            cleanup.callback(browser.close)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            cleanup.callback(context.close)
            document = inline_product_index(REPO)
            context.route(
                "**/*",
                lambda route: (
                    route.fulfill(status=200, content_type="text/html", body=document)
                    if route.request.url == "http://tauri.localhost/index.html"
                    else route.abort()
                ),
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.expose_function("__attachment_test_native", native)
            page.expose_function("__attachment_test_lock", lock_native)
            page.add_init_script(script)
            page.goto("http://tauri.localhost/index.html", wait_until="load")
            page.wait_for_function("document.body.dataset.applicationReady === 'true'")
            menu = page.locator("[data-all-tools]")
            menu.locator("summary").click()
            menu.get_by_role("button", name="Local projects", exact=True).click()
            choose_fixture_directory(page, "project-root", fixture.f.root)
            page.get_by_role("button", name="Open project", exact=True).click()
            page.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5000)
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Ingestion & Reconciliation", exact=True).click()
            page.get_by_role("button", name="Open Work versions", exact=True).click()
            page.get_by_label(f"Select Work {work['workId']}", exact=False).check()
            page.get_by_role("button", name="Review selected Work versions", exact=True).click()
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_text("Native attachment unavailable", exact=True).wait_for()
            self.assertIn("Attachment status unavailable", panel.inner_text())
            self.assertNotIn("no local copy attached", panel.inner_text())
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_disabled())
            self.assertEqual(0, panel.locator('input[type="file"]').count())
            self.assertIn(version["revisionId"], panel.inner_text())
            panel.get_by_role("button", name="Return to Work versions").click()
            page.evaluate("window.__ATTACH_TEST__.ready = true")
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'failed', code:'unsafe-content'}")
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_text("Authoritative status: attachment failed", exact=False).wait_for()
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_enabled())
            self.assertTrue(panel.get_by_role("button", name="Arm native file drop").is_enabled())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = null")
            page.evaluate("window.__ATTACH_TEST__.failure = 'password-protected'")
            panel.get_by_role("button", name="Choose local full-text file…").click()
            page.wait_for_timeout(500)
            self.assertIn(
                "password protected",
                panel.inner_text(),
                f"native state={page.evaluate('window.__ATTACH_TEST__')} page errors={errors}",
            )
            page.evaluate("window.__EMIT_REPLACEMENT__()")
            self.assertEqual(0, panel.get_by_role("heading", name="Pending document candidate").count())
            for code, phrase in (
                ("unsafe-content", "failed safety inspection"),
                ("oversize", "128 MiB limit"),
                ("rights-denied", "Rights deny local attachment"),
                ("interrupted", "was interrupted"),
            ):
                page.evaluate("code => { window.__ATTACH_TEST__.failure = code; }", code)
                panel.get_by_role("button", name="Choose local full-text file…").click()
                panel.locator("p[role='status']").filter(has_text=phrase).wait_for()
                self.assertEqual(0, panel.get_by_role("heading", name="Pending document candidate").count())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'denied', code:'rights-denied'}")
            panel.get_by_label("Source assertion for this version").select_option("")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_text("Authoritative status: attachment denied", exact=False).wait_for()
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_disabled())
            self.assertTrue(panel.get_by_role("button", name="Arm native file drop").is_disabled())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'cancelled', code:null}")
            panel.get_by_label("Source assertion for this version").select_option("")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_text("Authoritative status: attachment cancelled", exact=False).wait_for()
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_enabled())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'unavailable', code:'worker-unavailable'}")
            panel.get_by_label("Source assertion for this version").select_option("")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_text("Authoritative status: attachment unavailable", exact=False).wait_for()
            self.assertTrue(panel.get_by_role("button", name="Arm native file drop").is_enabled())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = null")
            panel.get_by_label("Source assertion for this version").select_option("")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_text("Authoritative status: metadata only", exact=False).wait_for()
            panel.get_by_role("button", name="Choose another file…").click()
            panel.get_by_role("heading", name="Pending document candidate").wait_for()
            panel.get_by_role("button", name="Cancel attachment").click()
            page.wait_for_function("document.activeElement?.textContent?.includes('Attach full text to this version')")
            self.assertEqual(0, page.get_by_role("region", name="Selected-version attachment").count())
            page.evaluate("window.__EMIT_REPLACEMENT__()")
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            self.assertEqual(0, panel.get_by_role("heading", name="Pending document candidate").count())
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_role("button", name="Arm native file drop").click()
            panel.get_by_role("heading", name="Pending document candidate").wait_for()
            self.assertEqual("drop", page.evaluate("window.__ATTACH_TEST__.begin.at(-1).mode"))
            panel.press("Escape")
            page.wait_for_function("document.activeElement?.textContent?.includes('Attach full text to this version')")
            self.assertEqual(0, page.get_by_role("region", name="Selected-version attachment").count())
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            self.assertEqual(0, panel.get_by_role("heading", name="Pending document candidate").count())
            panel.get_by_role("button", name="Choose local full-text file…").click()
            panel.get_by_role("heading", name="Pending document candidate").wait_for()
            panel.get_by_label("I confirm this file belongs to the selected Work and version shown above.").check()
            panel.get_by_label("Permitted use").select_option("unknown")
            self.assertTrue(panel.get_by_role("button", name="Attach to selected version").is_disabled())
            panel.get_by_label("Permitted use").select_option("project-only")
            page.evaluate("window.__EMIT_REPLACEMENT__()")
            panel.get_by_text("replacement.pdf", exact=False).wait_for()
            self.assertFalse(
                panel.get_by_label(
                    "I confirm this file belongs to the selected Work and version shown above."
                ).is_checked()
            )
            self.assertEqual("", panel.get_by_label("Permitted use").input_value())
            panel.get_by_label("I confirm this file belongs to the selected Work and version shown above.").check()
            panel.get_by_label("Permitted use").select_option("project-only")
            page.evaluate("window.__ATTACH_TEST__.commitFailure = 'throw'")
            panel.get_by_role("button", name="Attach to selected version").click()
            panel.get_by_text("reply was not confirmed", exact=False).wait_for()
            self.assertTrue(panel.get_by_role("button", name="Return to Work versions").is_disabled())
            self.assertTrue(panel.get_by_label("Source assertion for this version").is_disabled())
            self.assertTrue(page.get_by_role("button", name="Back to Works", exact=True).is_disabled())
            self.assertTrue(page.get_by_role("button", name="Refresh version evidence", exact=True).is_disabled())
            panel.press("Escape")
            self.assertEqual(1, panel.count())
            commit_count = len(page.evaluate("window.__ATTACH_TEST__.commit"))
            cancel_count = len(page.evaluate("window.__ATTACH_TEST__.cancel"))
            page.evaluate("window.__ATTACH_TEST__.staleVersion = true")
            panel.get_by_role("button", name="Retry same attachment decision").click()
            panel.get_by_text("An earlier attachment decision may have succeeded", exact=False).wait_for()
            self.assertEqual(commit_count, len(page.evaluate("window.__ATTACH_TEST__.commit")))
            self.assertEqual(cancel_count, len(page.evaluate("window.__ATTACH_TEST__.cancel")))
            self.assertTrue(panel.get_by_role("button", name="Return to Work versions").is_disabled())
            page.evaluate("window.__ATTACH_TEST__.staleVersion = false")
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Local projects", exact=True).click()
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Task Center", exact=True).click()
            page.get_by_text("Saved decision", exact=False).wait_for()
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Ingestion & Reconciliation", exact=True).click()
            self.assertEqual(0, page.get_by_role("region", name="Selected-version attachment").count())
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Task Center", exact=True).click()
            page.get_by_text("Saved decision", exact=False).wait_for()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_role("button", name="Retry same attachment decision").wait_for()
            panel.get_by_role("button", name="Retry same attachment decision").click()
            panel.get_by_text("Native attachment response reported", exact=False).wait_for()
            self.assertTrue(panel.get_by_role("button", name="Open in Document Reader · pending viewer").is_disabled())
            requests = page.evaluate("window.__ATTACH_TEST__")
            self.assertEqual("choose", requests["begin"][0]["mode"])
            self.assertEqual(version["versionId"], requests["begin"][0]["selection"]["versionId"])
            self.assertEqual(version["revisionId"], requests["commit"][0]["selection"]["versionRevisionId"])
            self.assertEqual(requests["commit"][0], requests["commit"][1])
            self.assertEqual("01900000-0000-7000-8000-000000000083", requests["commit"][1]["candidateId"])
            self.assertGreaterEqual(len(requests["cancel"]), 2)
            self.assertNotIn("root", requests["begin"][0])
            self.assertNotIn("sourcePath", str(requests["begin"]))
            panel.get_by_text(
                "Authoritative status: attachment recorded; local processing is pending.", exact=False
            ).wait_for()
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Task Center", exact=True).click()
            page.get_by_role("heading", name="Task Center", exact=True).wait_for()
            page.get_by_text("Saved decision", exact=False).wait_for()
            page.get_by_text(
                "Authoritative status: attachment recorded; local processing is pending.", exact=False
            ).wait_for()
            self.assertIn(
                "01900000-0000-7000-8000-000000000081",
                page.get_by_text("Earlier native response reported attachment", exact=False).inner_text(),
            )
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_text(version["revisionId"], exact=False).wait_for()
            for state, problem_code, recoverable in (
                ("failed", "interrupted", True),
                ("cancelled", None, True),
                ("unavailable", "worker-unavailable", True),
                ("denied", "rights-denied", False),
                ("failed", "unsafe-content", True),
            ):
                page.evaluate(
                    "value => { window.__ATTACH_TEST__.statusOverride = value; }",
                    {"status": state, "code": problem_code},
                )
                panel.get_by_role("button", name="View Task Center").click()
                page.get_by_role("status").filter(has_text=f"Authoritative status: attachment {state}").wait_for()
                page.get_by_role("button", name="Return to selected Work/version").click()
                panel = page.get_by_role("region", name="Selected-version attachment")
                panel.get_by_text(f"Authoritative status: attachment {state}", exact=False).wait_for()
                self.assertIn("Earlier native response reported attachment", panel.inner_text())
                for name in ("Choose local full-text file…", "Arm native file drop", "Cancel attachment"):
                    self.assertEqual(
                        recoverable,
                        panel.get_by_role("button", name=name).is_enabled(),
                        f"state={state} code={problem_code} control={name}",
                    )
                self.assertEqual(
                    recoverable,
                    panel.get_by_label("Source assertion for this version").is_enabled(),
                    f"state={state} code={problem_code} source selector",
                )
                self.assertEqual(0, panel.get_by_role("heading", name="Pending document candidate").count())
                panel.get_by_role("status").filter(has_text=f"Authoritative status: attachment {state}").wait_for()

            begin_count = len(page.evaluate("window.__ATTACH_TEST__.begin"))
            page.evaluate("window.__ATTACH_TEST__.staleVersion = true")
            panel.get_by_role("button", name="Choose local full-text file…").click()
            panel.get_by_text("An earlier attachment decision may have succeeded", exact=False).wait_for()
            self.assertEqual(begin_count, len(page.evaluate("window.__ATTACH_TEST__.begin")))
            self.assertIn("Earlier native response reported attachment", panel.inner_text())
            page.evaluate("window.__ATTACH_TEST__.staleVersion = false")

            saved_decision = page.evaluate("window.__ATTACH_TEST__.commit.at(-1)")
            commit_count = len(page.evaluate("window.__ATTACH_TEST__.commit"))
            page.evaluate(
                "request => { window.__ATTACH_TEST__.statusOverride = "
                "{status:'unconfirmed', code:null, retryRequest:request}; }",
                saved_decision,
            )
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("status").filter(
                has_text="Authoritative status: the saved attachment decision has no confirmed result"
            ).wait_for()
            page.evaluate("window.__ATTACH_TEST__.holdStatus = true")
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            page.wait_for_function("window.__ATTACH_TEST__.releaseStatus !== null")
            panel.get_by_role("button", name="Return to Work versions").focus()
            page.evaluate(
                "() => { const state = window.__ATTACH_TEST__; state.holdStatus = false; "
                "state.releaseStatus(); state.releaseStatus = null; }"
            )
            panel.get_by_role("status").filter(
                has_text="Authoritative status: the saved attachment decision has no confirmed result"
            ).wait_for()
            self.assertIn("Return to Work versions", page.evaluate("document.activeElement?.textContent"))
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_disabled())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'failed', code:'interrupted'}")
            panel.get_by_role("button", name="Retry same attachment decision").click()
            page.wait_for_function("count => window.__ATTACH_TEST__.commit.length === count + 1", arg=commit_count)
            self.assertEqual(saved_decision, page.evaluate("window.__ATTACH_TEST__.commit.at(-1)"))
            self.assertEqual(begin_count, len(page.evaluate("window.__ATTACH_TEST__.begin")))
            panel.get_by_role("status").filter(has_text="Authoritative status: attachment failed").wait_for()
            self.assertEqual(
                saved_decision["commandId"], page.evaluate("window.__ATTACH_TEST__.status.at(-1).commandId")
            )
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_enabled())
            altered_decision = {**saved_decision, "candidateId": "01900000-0000-7000-8000-000000000098"}
            page.evaluate(
                "request => { window.__ATTACH_TEST__.statusOverride = "
                "{status:'unconfirmed', code:null, retryRequest:request}; }",
                altered_decision,
            )
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_text("native status did not match the exact saved attachment decision", exact=False).wait_for()
            self.assertEqual(0, panel.get_by_role("button", name="Retry same attachment decision").count())
            self.assertEqual(commit_count + 1, len(page.evaluate("window.__ATTACH_TEST__.commit")))
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_disabled())
            panel.get_by_role("button", name="View Task Center").click()
            self.assertIn(
                "01900000-0000-7000-8000-000000000081",
                page.get_by_text("Earlier native response reported attachment", exact=False).inner_text(),
            )
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            page.evaluate(
                "request => { window.__ATTACH_TEST__.statusOverride = "
                "{status:'unconfirmed', code:null, retryRequest:request}; }",
                saved_decision,
            )
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_role("status").filter(
                has_text="Authoritative status: the saved attachment decision has no confirmed result"
            ).wait_for()
            self.assertIn("Earlier native response reported attachment", panel.inner_text())
            page.evaluate("window.__ATTACH_TEST__.commitFailure = 'throw'")
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'failed', code:'interrupted'}")
            commit_count = len(page.evaluate("window.__ATTACH_TEST__.commit"))
            panel.get_by_role("button", name="Retry same attachment decision").click()
            page.wait_for_function("count => window.__ATTACH_TEST__.commit.length === count + 1", arg=commit_count)
            self.assertEqual(saved_decision, page.evaluate("window.__ATTACH_TEST__.commit.at(-1)"))
            panel.get_by_role("status").filter(has_text="Authoritative status: attachment failed").wait_for()
            self.assertEqual(0, panel.get_by_role("button", name="Retry same attachment decision").count())
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_enabled())
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_role("status").filter(has_text="Authoritative status: attachment failed").wait_for()
            self.assertIn("Earlier native response reported attachment", panel.inner_text())
            page.evaluate(
                "window.__ATTACH_TEST__.statusOverride = "
                "{status:'failed', code:'interrupted', "
                "attachmentId:'01900000-0000-7000-8000-000000000098', "
                "documentRevisionId:'01900000-0000-7000-8000-000000000099'}"
            )
            panel.get_by_role("button", name="View Task Center").click()
            historical = page.get_by_text("Earlier native response reported attachment", exact=False).inner_text()
            self.assertIn("01900000-0000-7000-8000-000000000081", historical)
            self.assertNotIn("01900000-0000-7000-8000-000000000098", historical)
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_role("status").filter(has_text="Authoritative status: attachment failed").wait_for()
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_disabled())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'failed', code:'interrupted'}")
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_role("status").filter(has_text="Authoritative status: attachment failed").wait_for()
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_enabled())
            for terminal, code, recoverable, retry_failure in (
                ("failed", "interrupted", True, "interrupted"),
                ("unavailable", "worker-unavailable", True, "throw"),
                ("denied", "rights-denied", False, "throw"),
            ):
                page.evaluate("window.__ATTACH_TEST__.statusOverride = null")
                panel.get_by_role("button", name="Choose local full-text file…").click()
                panel.get_by_role("heading", name="Pending document candidate").wait_for()
                panel.get_by_label("I confirm this file belongs to the selected Work and version shown above.").check()
                panel.get_by_label("Permitted use").select_option("project-only")
                panel.get_by_role("button", name="Attach to selected version").click()
                panel.get_by_text("Native attachment response reported", exact=False).wait_for()
                decision = page.evaluate("window.__ATTACH_TEST__.commit.at(-1)")
                page.evaluate(
                    "request => { window.__ATTACH_TEST__.statusOverride = "
                    "{status:'unconfirmed', code:null, retryRequest:request}; }",
                    decision,
                )
                panel.get_by_role("button", name="View Task Center").click()
                page.get_by_role("button", name="Return to selected Work/version").click()
                panel = page.get_by_role("region", name="Selected-version attachment")
                panel.get_by_role("status").filter(
                    has_text="Authoritative status: the saved attachment decision has no confirmed result"
                ).wait_for()
                self.assertIn("Earlier native response reported attachment", panel.inner_text())
                if menu.get_attribute("open") is None:
                    menu.locator("summary").click()
                menu.get_by_role("button", name="Task Center", exact=True).click()
                page.get_by_text("Saved decision", exact=False).wait_for()
                self.assertIn(
                    "01900000-0000-7000-8000-000000000081",
                    page.get_by_text("Earlier native response reported attachment", exact=False).inner_text(),
                )
                page.get_by_role("button", name="Return to selected Work/version").click()
                panel = page.get_by_role("region", name="Selected-version attachment")
                panel.get_by_role("button", name="Retry same attachment decision").wait_for()
                page.evaluate("failure => { window.__ATTACH_TEST__.commitFailure = failure; }", retry_failure)
                page.evaluate(
                    "value => { window.__ATTACH_TEST__.statusOverride = value; }",
                    {"status": terminal, "code": code},
                )
                commit_count = len(page.evaluate("window.__ATTACH_TEST__.commit"))
                panel.get_by_role("button", name="Retry same attachment decision").click()
                page.wait_for_function("count => window.__ATTACH_TEST__.commit.length === count + 1", arg=commit_count)
                self.assertEqual(decision, page.evaluate("window.__ATTACH_TEST__.commit.at(-1)"))
                panel.get_by_role("status").filter(has_text=f"Authoritative status: attachment {terminal}").wait_for()
                self.assertEqual(0, panel.get_by_role("button", name="Retry same attachment decision").count())
                self.assertEqual(
                    recoverable,
                    panel.get_by_role("button", name="Choose local full-text file…").is_enabled(),
                    f"terminal={terminal} retry_failure={retry_failure}",
                )
                self.assertIn("Earlier native response reported attachment", panel.inner_text())
            page.evaluate("window.__ATTACH_TEST__.statusOverride = null")
            panel.get_by_role("button", name="Return to Work versions").focus()
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            active_markup = page.evaluate("document.activeElement?.outerHTML")
            attach_row_markup = page.get_by_role(
                "button", name="Attach full text to this version", exact=True
            ).evaluate_all("(nodes) => nodes.map(n => [n.outerHTML, n.isConnected, n.disabled])")
            self.assertIn(
                "Attach full text to this version",
                page.evaluate("document.activeElement?.textContent"),
                f"active={active_markup} row={attach_row_markup} errors={errors}",
            )
            self.assertEqual(0, page.get_by_role("region", name="Selected-version attachment").count())
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            self.assertEqual(
                1,
                menu.get_by_role("button", name="Task Center", exact=True).count(),
                f"menu={menu.inner_text()} open={menu.get_attribute('open')}",
            )
            menu.get_by_role("button", name="Task Center", exact=True).click()
            self.assertEqual(1, page.get_by_role("button", name="Return to selected Work/version").count())
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Ingestion & Reconciliation", exact=True).click()
            self.assertEqual(0, page.get_by_role("region", name="Selected-version attachment").count())
            page.get_by_role("button", name="Open Work versions", exact=True).click()
            page.get_by_label(f"Select Work {work['workId']}", exact=False).check()
            page.get_by_role("button", name="Review selected Work versions", exact=True).click()
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_text(
                "Authoritative status: attachment recorded; local processing is pending.", exact=False
            ).wait_for()
            panel.get_by_role("button", name="View Task Center").click()
            self.assertIn(
                "01900000-0000-7000-8000-000000000082",
                page.get_by_text("Last checked attachment status identified attachment", exact=False).inner_text(),
            )
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Ingestion & Reconciliation", exact=True).click()
            self.assertEqual(0, page.get_by_role("region", name="Selected-version attachment").count())
            page.evaluate("window.__ATTACH_TEST__.ambiguous = true")
            page.get_by_role("button", name="Open Work versions", exact=True).click()
            page.wait_for_timeout(500)
            versions_region = page.locator("[data-reconciliation-versions]")
            versions_text = (
                versions_region.inner_text() if versions_region.count() else page.locator("main").inner_text()[-5000:]
            )
            self.assertEqual(
                1,
                page.get_by_label(f"Select Work {work['workId']}", exact=False).count(),
                f"page={versions_text} errors={errors}",
            )
            page.get_by_label(f"Select Work {work['workId']}", exact=False).check()
            page.get_by_label("Select Work f1900000-0000-7000-8000-000000000090", exact=False).check()
            page.get_by_role("button", name="Review selected Work versions", exact=True).click()
            page.wait_for_timeout(400)
            core_context = page.evaluate(
                "({status:window.__ATTACH_TEST__.lastContextStatus, body:window.__ATTACH_TEST__.lastContextBody})"
            )
            self.assertEqual(
                1,
                page.get_by_role("button", name="Attach full text to this version", exact=True).count(),
                f"page={page.locator('main').inner_text()[-3000:]} core={core_context} errors={errors}",
            )
            self.assertTrue(
                page.get_by_role("button", name="Attach full text to this version", exact=True).is_disabled()
            )
            page.get_by_role("button", name="Back to Works", exact=True).click()
            page.get_by_role("button", name="Close Work versions", exact=True).click()
            page.evaluate("window.__ATTACH_TEST__.ambiguous = false; window.__ATTACH_TEST__.durable = null")
            page.get_by_role("button", name="Open Work versions", exact=True).click()
            page.get_by_label(f"Select Work {work['workId']}", exact=False).check()
            page.get_by_role("button", name="Review selected Work versions", exact=True).click()
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            before_stale = len(page.evaluate("window.__ATTACH_TEST__.begin"))
            page.evaluate("window.__ATTACH_TEST__.staleVersion = true")
            panel.get_by_role("button", name="Choose local full-text file…").click()
            page.wait_for_timeout(400)
            self.assertIn(
                "The Work, version or source changed. Refresh current evidence before retrying.",
                panel.inner_text(),
                f"core={page.evaluate('window.__ATTACH_TEST__.lastContextBody')} errors={errors}",
            )
            self.assertEqual(before_stale, len(page.evaluate("window.__ATTACH_TEST__.begin")))
            self.assertEqual(0, panel.get_by_role("heading", name="Pending document candidate").count())
            page.evaluate("window.__ATTACH_TEST__.staleVersion = false")
            panel.get_by_role("button", name="Return to Work versions").click()
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_role("button", name="Choose local full-text file…").click()
            panel.get_by_role("heading", name="Pending document candidate").wait_for()
            panel.get_by_label("I confirm this file belongs to the selected Work and version shown above.").check()
            panel.get_by_label("Permitted use").select_option("project-only")
            page.evaluate("window.__ATTACH_TEST__.commitFailure = 'rights-denied'")
            panel.get_by_role("button", name="Attach to selected version").click()
            panel.get_by_text("Rights deny local attachment", exact=False).wait_for()
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("heading", name="Task Center", exact=True).wait_for()
            self.assertEqual(0, page.get_by_text("Saved decision", exact=False).count())
            self.assertEqual(0, page.get_by_text("Attachment operation", exact=False).count())
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Ingestion & Reconciliation", exact=True).click()
            page.get_by_role("button", name="Open Work versions", exact=True).click()
            page.get_by_label(f"Select Work {work['workId']}", exact=False).check()
            page.get_by_role("button", name="Review selected Work versions", exact=True).click()
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_role("button", name="Choose local full-text file…").click()
            panel.get_by_role("heading", name="Pending document candidate").wait_for()
            panel.get_by_label("I confirm this file belongs to the selected Work and version shown above.").check()
            panel.get_by_label("Permitted use").select_option("project-only")
            page.evaluate("window.__ATTACH_TEST__.commitFailure = 'throw'")
            panel.get_by_role("button", name="Attach to selected version").click()
            panel.get_by_text("reply was not confirmed", exact=False).wait_for()
            pending_after_loss = page.evaluate("window.__ATTACH_TEST__.retryRequest")
            self.assertIsNotNone(pending_after_loss)
            page.get_by_role("button", name="Lock", exact=True).click()
            page.get_by_text("Unlock with Windows password", exact=False).wait_for()
            self.assertNotIn(version["versionId"], page.locator("body").inner_text())
            page.evaluate("window.__EMIT_REPLACEMENT__()")
            self.assertNotIn(version["versionId"], page.locator("body").inner_text())
            page.get_by_role("button", name="Unlock with Windows password", exact=True).click()
            page.get_by_text("No project open", exact=False).wait_for()
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Local projects", exact=True).click()
            choose_fixture_directory(page, "project-root", fixture.f.root)
            page.get_by_role("button", name="Open project", exact=True).click()
            page.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5000)
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Task Center", exact=True).click()
            self.assertEqual(0, page.get_by_role("button", name="Return to selected Work/version").count())
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name="Ingestion & Reconciliation", exact=True).click()
            page.get_by_role("button", name="Open Work versions", exact=True).click()
            page.get_by_label(f"Select Work {work['workId']}", exact=False).check()
            page.get_by_role("button", name="Review selected Work versions", exact=True).click()
            page.get_by_role("button", name="Attach full text to this version", exact=True).click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_label("Source assertion for this version").select_option(work["assertionRevisionIds"][0])
            panel.get_by_text(
                "Authoritative status: the saved attachment decision has no confirmed result", exact=False
            ).wait_for()
            panel.get_by_role("button", name="Retry same attachment decision").wait_for()
            self.assertEqual(pending_after_loss, page.evaluate("window.__ATTACH_TEST__.retryRequest"))
            old_operation_id = pending_after_loss["operationId"]
            begin_before_stale = len(page.evaluate("window.__ATTACH_TEST__.begin"))
            commit_before_stale = len(page.evaluate("window.__ATTACH_TEST__.commit"))
            page.evaluate(
                "window.__ATTACH_TEST__.statusOverride = "
                "{status:'unavailable', code:'candidate-unavailable', commandId:null}"
            )
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_role("button", name="Retry same attachment decision").wait_for()
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_disabled())
            page.evaluate(
                "window.__ATTACH_TEST__.statusOverride = {status:'unavailable', code:'interrupted', commandId:null}"
            )
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_text("belongs to an earlier session and cannot be retried", exact=False).wait_for()
            self.assertEqual(0, panel.get_by_role("button", name="Retry same attachment decision").count())
            self.assertTrue(panel.get_by_role("button", name="Choose local full-text file…").is_enabled())
            self.assertTrue(panel.get_by_role("button", name="Return to Work versions").is_enabled())
            self.assertEqual(begin_before_stale, len(page.evaluate("window.__ATTACH_TEST__.begin")))
            self.assertEqual(commit_before_stale, len(page.evaluate("window.__ATTACH_TEST__.commit")))
            self.assertEqual(
                pending_after_loss["operationId"], page.evaluate("window.__ATTACH_TEST__.status.at(-1).operationId")
            )
            self.assertEqual(
                pending_after_loss["commandId"], page.evaluate("window.__ATTACH_TEST__.status.at(-1).commandId")
            )
            page.evaluate("window.__ATTACH_TEST__.statusOverride = null")
            panel.get_by_role("button", name="Choose local full-text file…").click()
            panel.get_by_role("heading", name="Pending document candidate").wait_for()
            panel.get_by_label("I confirm this file belongs to the selected Work and version shown above.").check()
            panel.get_by_label("Permitted use").select_option("project-only")
            page.evaluate("window.__ATTACH_TEST__.commitFailure = 'throw'")
            panel.get_by_role("button", name="Attach to selected version").click()
            panel.get_by_text("reply was not confirmed", exact=False).wait_for()
            pending_after_loss = page.evaluate("window.__ATTACH_TEST__.retryRequest")
            self.assertNotEqual(pending_after_loss["operationId"], old_operation_id)
            commits_before_retry = len(page.evaluate("window.__ATTACH_TEST__.commit"))
            panel.get_by_role("button", name="Retry same attachment decision").click()
            panel.get_by_text("Native attachment response reported", exact=False).wait_for()
            self.assertEqual(commits_before_retry + 1, len(page.evaluate("window.__ATTACH_TEST__.commit")))
            self.assertEqual(pending_after_loss, page.evaluate("window.__ATTACH_TEST__.commit.at(-1)"))
            page.evaluate("window.__ATTACH_TEST__.statusOverride = {status:'failed', code:'interrupted'}")
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            panel.get_by_role("status").filter(has_text="Authoritative status: attachment failed").wait_for()
            panel.get_by_role("button", name="Choose local full-text file…").click()
            panel.get_by_role("heading", name="Pending document candidate").wait_for()
            panel.get_by_label("I confirm this file belongs to the selected Work and version shown above.").check()
            panel.get_by_label("Permitted use").select_option("project-only")
            page.evaluate("window.__ATTACH_TEST__.statusOverride = null")
            page.evaluate("window.__ATTACH_TEST__.commitFailure = 'throw'")
            panel.get_by_role("button", name="Attach to selected version").click()
            panel.get_by_text("reply was not confirmed", exact=False).wait_for()
            panel.get_by_role("button", name="View Task Center").click()
            page.get_by_role("status").filter(
                has_text="Authoritative status: the saved attachment decision has no confirmed result"
            ).wait_for()
            page.evaluate(
                "window.__ATTACH_TEST__.statusOverride = {status:'processing', code:null, "
                "attachmentId:'01900000-0000-7000-8000-000000000081', "
                "documentRevisionId:'01900000-0000-7000-8000-000000000082'}"
            )
            page.evaluate("window.__ATTACH_TEST__.holdStatus = true")
            commits_before_status = len(page.evaluate("window.__ATTACH_TEST__.commit"))
            page.get_by_role("button", name="Return to selected Work/version").click()
            panel = page.get_by_role("region", name="Selected-version attachment")
            page.wait_for_function("window.__ATTACH_TEST__.releaseStatus !== null")
            panel.get_by_role("button", name="View Task Center").focus()
            page.evaluate(
                "() => { const state = window.__ATTACH_TEST__; state.holdStatus = false; "
                "state.releaseStatus(); state.releaseStatus = null; }"
            )
            panel.get_by_role("status").filter(
                has_text="Authoritative status: attachment recorded; local processing is pending."
            ).wait_for()
            self.assertIn("View Task Center", page.evaluate("document.activeElement?.textContent"))
            self.assertEqual(commits_before_status, len(page.evaluate("window.__ATTACH_TEST__.commit")))
            self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
