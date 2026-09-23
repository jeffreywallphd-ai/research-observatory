"""Narrow built-import-pane contrast/reflow evidence; native transport is a double."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "services/core-api/src"))

from desktop_app_check import (  # noqa: E402
    DIRECTORY_PICKER_FIXTURE,
    choose_fixture_directory,
    contrast_ratio,
    core_workflow_catalog_json,
    font_face_available,
    inline_product_index,
    product_build_errors,
)

from tests.service import test_import_review_api as api_fixture  # noqa: E402

# Inspect rendered text, including scrollable content, rather than token names alone.
# Transparent backgrounds are composited through ancestors; unsupported images or
# non-disabled opacity fail visibly instead of silently omitting a sample.
TEXT_COLORS = r"""root => {
  const rgba = value => {
    const m = value.match(/^rgba?\(([^)]+)\)$/);
    if (!m) throw new Error('unsupported computed color');
    const values = m[1].split(',').map(Number);
    return [...values.slice(0, 3), values[3] ?? 1];
  };
  const blend = (front, back) => front.slice(0, 3).map((v, i) => v * front[3] + back[i] * (1 - front[3]));
  const background = el => {
    if (!el) throw new Error('missing opaque canvas');
    const css = getComputedStyle(el), color = rgba(css.backgroundColor);
    if (css.backgroundImage !== 'none') throw new Error('unmeasured background image');
    return color[3] === 1 ? color.slice(0, 3) : blend(color, background(el.parentElement));
  };
  const hex = color => '#' + color.map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const candidates = new Set(root.querySelectorAll('input:not([type=checkbox]), select'));
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    if (walker.currentNode.textContent.trim()) candidates.add(walker.currentNode.parentElement);
  }
  const samples = [];
  for (const el of candidates) {
    if (!el.getClientRects().length || el.closest('[hidden], [disabled]')) continue;
    const css = getComputedStyle(el);
    if (css.visibility !== 'visible' || css.display === 'none') continue;
    for (let ancestor = el; ancestor; ancestor = ancestor.parentElement) {
      if (Number(getComputedStyle(ancestor).opacity) !== 1) throw new Error('unmeasured opacity');
    }
    const bg = background(el), fg = blend(rgba(css.color), bg);
    const size = parseFloat(css.fontSize), bold = Number(css.fontWeight) >= 700;
    samples.push({tag: el.tagName, classes: el.getAttribute('class'), foreground: hex(fg), background: hex(bg),
      minimum: size >= 24 || bold && size >= 18.6667 ? 3 : 4.5});
  }
  return samples;
}"""


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


class ImportVisualTests(unittest.TestCase):
    def test_import_panes_contrast_reflow_and_controlled_theme_snapshots(self):
        self.assertEqual("", git("status", "--porcelain"))
        self.assertEqual([], product_build_errors(REPO))
        head = git("rev-parse", "HEAD")
        fixture = Path(tempfile.mkdtemp(prefix="import-visual-", dir=REPO / "artifacts/tmp"))
        report = {
            "status": "RUNNING",
            "head": head,
            "samples": [],
            "screenshots": [],
            "scope": "built renderer, fixture Core, native transport double; not native or protected-storage proof",
        }
        try:
            self._exercise(fixture, report)
            self.assertEqual(head, git("rev-parse", "HEAD"))
            self.assertEqual("", git("status", "--porcelain"))
            report["status"] = "PASS"
        except BaseException as error:
            report.update(status="FAIL", failureType=type(error).__name__)
            raise
        finally:
            (fixture / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {"report": (fixture / "result.json").relative_to(REPO).as_posix(), "status": report["status"]}
                )
            )

    def _exercise(self, fixture, report):
        api = api_fixture.ImportReviewApiTests(methodName="runTest")
        with patch("research_observatory_core.import_preview_service.ImportPreviewService.start"):
            api.setUp()
        self.addCleanup(api.doCleanups)
        f = api.fixture
        api.post("begin-review")
        f.service.schedule_summary(f.root, api.preview, revision=1)
        f.service.run_pending()
        f.service.detach(f.root)
        f.projects.close(root=f.root, trace_id="1" * 32)

        def native(command, args):
            self.assertEqual("core_api_request", command)
            request = args["request"]
            headers = {"Content-Type": "application/json"}
            if request["ifMatch"] is not None:
                headers["If-Match"] = request["ifMatch"]
            if request["idempotencyKey"] is not None:
                headers["Idempotency-Key"] = request["idempotencyKey"]
            response = api.client.request(request["method"], request["path"], content=request["body"], headers=headers)
            return {
                "status": response.status_code,
                "contentType": response.headers["content-type"].split(";")[0],
                "traceId": response.headers["x-trace-id"],
                "etag": response.headers.get("etag"),
                "body": response.text,
            }

        script = (
            (REPO / "tests/desktop/fixtures/task_center_interactions.js")
            .read_text("utf-8")
            .replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO))
        )
        script += (
            DIRECTORY_PICKER_FIXTURE
            + """;
        (() => {
          const prior = window.__TAURI_INTERNALS__.invoke;
          window.__TAURI_INTERNALS__.invoke = (command, args) => command === 'core_api_request'
            ? window.__import_visual_native(command, args) : prior(command, args);
        })();"""
        )
        playwright = self.enterContext(sync_playwright())
        browser = playwright.chromium.launch(headless=True)
        self.addCleanup(browser.close)
        visual = json.loads((REPO / "verification/extensions/desktop-ui.json").read_text("utf-8"))["visual"]
        self.assertEqual(visual["browserVersion"], browser.version)
        self.assertEqual(visual["playwrightVersion"], importlib.metadata.version("playwright"))
        report.update(
            browser=browser.version,
            playwright=importlib.metadata.version("playwright"),
            deviceScaleFactor=1,
            locale="en-US",
            timezone="UTC",
            reducedMotion="reduce",
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            locale="en-US",
            timezone_id="UTC",
            reduced_motion="reduce",
        )
        document = inline_product_index(REPO)
        report["builtDocumentSha256"] = hashlib.sha256(document.encode()).hexdigest()
        context.route(
            "**/*",
            lambda route: (
                route.fulfill(status=200, content_type="text/html", body=document)
                if route.request.url == "http://tauri.localhost/index.html"
                else route.abort()
            ),
        )
        page = context.new_page()
        page.set_default_timeout(7000)
        page.expose_function("__import_visual_native", native)
        page.add_init_script(script)
        page.goto("http://tauri.localhost/index.html", wait_until="load")
        page.wait_for_function("document.body.dataset.applicationReady === 'true'")
        report["fonts"] = {font: font_face_available(page, font) for font in visual["requiredFonts"]}
        self.assertTrue(all(report["fonts"].values()), report["fonts"])
        menu = page.locator("[data-all-tools]")

        def navigate(name):
            if menu.get_attribute("open") is None:
                menu.locator("summary").click()
            menu.get_by_role("button", name=name, exact=True).click()

        navigate("Local projects")
        choose_fixture_directory(page, "project-root", f.root)
        page.get_by_role("button", name="Open project", exact=True).click()
        page.get_by_text("Exclusive local session open", exact=True).wait_for()
        navigate("Ingestion & Reconciliation")
        page.locator(".import-batches").get_by_role("button").first.click()
        commit = page.get_by_label("Import commit", exact=True)
        commit.get_by_text("No commit job reported", exact=True).wait_for()
        workspace = page.locator("[data-import-workspace]")

        def inspect(state):
            for theme in ("light", "dark"):
                if page.locator("html").get_attribute("data-theme") != theme:
                    page.locator("[data-theme-toggle]").click()
                expect(page.locator("html")).to_have_attribute("data-theme", theme)
                for width, height in ((1440, 900), (1280, 720), (720, 450)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.evaluate("() => document.fonts.ready")
                    self.assertTrue(page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"))
                    geometry = workspace.evaluate("""el => ({
                      viewport: document.documentElement.clientWidth,
                      document: document.documentElement.scrollWidth,
                      left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right,
                      tables: [...el.querySelectorAll('.ro-table-region, .ro-table-scroll')].map(node => ({
                        left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right,
                        tabIndex: node.tabIndex, overflowX: getComputedStyle(node).overflowX}))
                    })""")
                    self.assertLessEqual(geometry["document"], geometry["viewport"] + 1, geometry)
                    self.assertGreaterEqual(geometry["left"], 0)
                    self.assertLessEqual(geometry["right"], geometry["viewport"] + 1)
                    self.assertGreater(len(geometry["tables"]), 0, "expected import tables were not measured")
                    for table in geometry["tables"]:
                        self.assertGreaterEqual(table["left"], geometry["left"] - 1)
                        self.assertLessEqual(table["right"], geometry["right"] + 1)
                        self.assertEqual(0, table["tabIndex"])
                        self.assertIn(table["overflowX"], ("auto", "scroll"))
                    colors = workspace.evaluate(TEXT_COLORS)
                    self.assertGreater(len(colors), 30)
                    for color in colors:
                        color["ratio"] = contrast_ratio(color["foreground"], color["background"])
                    report["samples"].append(
                        {
                            "state": state,
                            "theme": theme,
                            "width": width,
                            "height": height,
                            "geometry": geometry,
                            "textColors": colors,
                        }
                    )
                    self.assertTrue(
                        all(row["ratio"] >= row["minimum"] for row in colors),
                        [row for row in colors if row["ratio"] < row["minimum"]],
                    )
                    path = fixture / f"{state}-{theme}-{width}.png"
                    commit.screenshot(path=str(path), animations="disabled")
                    report["screenshots"].append(
                        {
                            "path": path.relative_to(REPO).as_posix(),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                    )

        commit.get_by_role("button", name="Review commit…", exact=True).click()
        expect(page.get_by_role("heading", name="Confirm draft 1", exact=True)).to_be_focused()
        inspect("confirmation")
        commit.get_by_role("button", name="Commit this draft", exact=True).click()
        commit.get_by_text("Commit runnable", exact=True).wait_for()
        f.service.run_pending()
        commit.get_by_role("button", name="Refresh commit status", exact=True).click()
        commit.get_by_text("Committed — awaiting reconciliation", exact=True).wait_for()
        commit.get_by_role("button", name="Open import manifest", exact=True).click()
        manifest = page.get_by_label("Import manifest", exact=True)
        manifest.get_by_role("table").wait_for()
        expect(manifest.locator(".ro-table-scroll")).to_have_count(1)
        expect(manifest.get_by_role("columnheader")).to_have_count(5)
        inspect("manifest")
        page.goto("about:blank")


if __name__ == "__main__":
    unittest.main()
