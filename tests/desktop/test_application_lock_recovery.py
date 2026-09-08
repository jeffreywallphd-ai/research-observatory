"""Built renderer regressions; simulated transport, not native/authentication proof."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import inline_product_index, product_build_errors  # noqa: E402

ADAPTER = r"""(() => {
  const callbacks = new Map();
  let next = 1;
  let listener;
  const state = window.__LOCK_TEST__ = {
    failure: __INITIAL__, calls: [], pending: [],
    snapshot: {
      schemaVersion: '1.0', state: 'unlocked', signInMode: __MODE__, policyRevision: 1,
      profileName: 'Synthetic private profile', inactivityTimeoutMinutes: 0,
      configurationState: 'valid', reason: null, retryAfterSeconds: 0, auditSequence: 1,
      threatDisclosure: 'Application-session protection only; this is not Windows-account isolation.'
    },
    emit: () => callbacks.get(listener)?.({event: 'application-lock-changed',
      id: listener, payload: {...state.snapshot}})
  };
  window.__TAURI_INTERNALS__ = {
    transformCallback: callback => { const id = next++; callbacks.set(id, callback); return id; },
    unregisterCallback: id => callbacks.delete(id),
    invoke: async (command, args) => {
      state.calls.push(command);
      if (command === 'plugin:event|listen') {
        if (args.event === 'application-lock-changed') listener = args.handler;
        return args.handler;
      }
      if (command === 'application_lock_status') {
        if (state.failure === 'reject') throw Error('synthetic transport failure');
        if (state.failure === 'hang') return new Promise(resolve => state.pending.push(resolve));
        if (state.failure === 'malformed') return {untrusted: true};
        return {...state.snapshot};
      }
      if (command === 'application_lock_hello_availability') return {
        schemaVersion: '1.0', provider: 'windows-hello', availability: 'available'
      };
      if (['plugin:event|unlisten', 'application_lock_activity', 'core_runtime_stop'].includes(command)) return;
      if (['core_runtime_start', 'core_runtime_status'].includes(command)) return {
        state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null
      };
      throw Error('unexpected synthetic command');
    }
  };
})();"""


class ApplicationLockRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        errors = product_build_errors(REPO)
        if errors:
            raise AssertionError(errors)
        cls.document = inline_product_index(REPO)

    def page(self, browser: Any, mode: str, initial: str = "", theme: str = "light") -> Any:
        context = browser.new_context(viewport={"width": 720, "height": 450}, reduced_motion="reduce")
        context.route(
            "**/*",
            lambda route: (
                route.fulfill(status=200, content_type="text/html", body=self.document)
                if route.request.url == "http://tauri.localhost/index.html"
                else route.abort()
            ),
        )
        page = context.new_page()
        self.page_errors: list[str] = []
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.add_init_script(ADAPTER.replace("__MODE__", json.dumps(mode)).replace("__INITIAL__", json.dumps(initial)))
        page.add_init_script(f"localStorage.setItem('research-observatory.theme', {json.dumps(theme)});")
        page.goto("http://tauri.localhost/index.html", wait_until="load")
        if not initial:
            page.locator(".application-shell[data-application-ready]").wait_for(timeout=5000)
            page.locator("#shell-command").fill("Synthetic private command")
        return page

    def assert_cleared(self, page: Any) -> None:
        self.assertEqual([], self.page_errors)
        self.assertEqual(0, page.locator("#shell-command, nav, footer, [data-local-service-boundary]").count())
        body = page.locator("body").inner_text()
        self.assertNotIn("Synthetic private", body)
        self.assertNotIn("locked manually", body)
        self.assertFalse(page.evaluate("window.__LOCK_TEST__.calls.some(c => /unlock|recovery|transition/.test(c))"))

    def test_all_modes_keep_truthful_failure_and_immutable_first_mode(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for mode in ("none", "windows-password", "windows-hello"):
                    for theme in ("light", "dark"):
                        with self.subTest(mode=mode, theme=theme):
                            page = self.page(browser, mode, theme=theme)
                            original = page.evaluate("JSON.stringify(window.__LOCK_TEST__.snapshot)")
                            page.evaluate("window.__LOCK_TEST__.failure = 'reject'")
                            page.get_by_role("alert").filter(has_text="status is unavailable").wait_for(timeout=5000)
                            self.assert_cleared(page)
                            self.assertEqual(original, page.evaluate("JSON.stringify(window.__LOCK_TEST__.snapshot)"))
                            body = page.locator("body").inner_text()
                            self.assertIn("Last confirmed sign-in mode:", body)
                            if mode == "none":
                                self.assertIn("No login", body)
                                self.assertIn("Close Research Observatory completely", body)
                                self.assertEqual(0, page.get_by_role("button").count())
                                page.wait_for_function("document.activeElement?.id === 'lock-monitoring-status'")
                            else:
                                label = "Windows Hello" if mode == "windows-hello" else "Windows password"
                                self.assertEqual(
                                    1, page.get_by_role("button", name=f"Unlock with {label}", exact=True).count()
                                )
                            page.evaluate("""() => {
                              const s = window.__LOCK_TEST__; s.failure = '';
                              s.snapshot = {...s.snapshot, signInMode: 'none', profileName: null, auditSequence: 2};
                              s.emit();
                            }""")
                            page.wait_for_timeout(1200)
                            self.assert_cleared(page)
                            self.assertIn("Last confirmed sign-in mode:", page.locator("body").inner_text())
                            if mode != "none":
                                self.assertEqual(
                                    1, page.get_by_role("button", name=f"Unlock with {label}", exact=True).count()
                                )
                            page.context.close()
            finally:
                browser.close()

    def test_initial_unknown_and_timeout_do_not_claim_no_login_or_authentication(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = self.page(browser, "none", initial="hang")
                page.get_by_text("Checking the application sign-in policy.", exact=True).wait_for(timeout=1000)
                self.assertEqual(0, page.get_by_role("button").count())
                page.get_by_role("alert").filter(has_text="status is unavailable").wait_for(timeout=5000)
                self.assertIn("Sign-in mode has not been confirmed", page.locator("body").inner_text())
                page.evaluate("""() => {
                  const s = window.__LOCK_TEST__; s.failure = '';
                  for (const resolve of s.pending) resolve({...s.snapshot});
                  s.emit();
                }""")
                page.wait_for_timeout(1200)
                self.assert_cleared(page)
                self.assertEqual(0, page.get_by_role("button").count())
                self.assertNotIn("No login", page.locator("body").inner_text())
                page.context.close()
            finally:
                browser.close()

    def test_genuine_policy_recovery_does_not_clear_latch_for_passive_unlock(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = self.page(browser, "none")
                page.evaluate("window.__LOCK_TEST__.failure = 'malformed'")
                page.get_by_role("alert").filter(has_text="status was invalid").wait_for(timeout=5000)
                self.assertEqual(0, page.get_by_role("button").count())
                page.evaluate("""() => {
                  const s = window.__LOCK_TEST__; s.failure = '';
                  s.snapshot = {...s.snapshot, state: 'locked', profileName: null,
                    configurationState: 'invalid', reason: 'configuration-invalid', auditSequence: 2};
                  s.emit();
                }""")
                page.get_by_role("button", name="Recover with Windows password", exact=True).wait_for(timeout=5000)
                page.evaluate("""() => {
                  const s = window.__LOCK_TEST__;
                  s.snapshot = {...s.snapshot, state: 'unlocked', configurationState: 'valid',
                    reason: null, auditSequence: 3}; s.emit();
                }""")
                page.wait_for_timeout(1200)
                self.assert_cleared(page)
                self.assertEqual(1, page.locator("[data-application-locked]").count())
                page.context.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
