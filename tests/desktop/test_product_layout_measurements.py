from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import (  # noqa: E402
    DIRECTORY_PICKER_FIXTURE,
    choose_fixture_directory,
    core_workflow_catalog_json,
    inline_product_index,
)
from product_layout_measurements import (  # noqa: E402
    PANEL_FLOW_GEOMETRY,
    SHELL_GEOMETRY,
    panel_flow_errors,
    shell_geometry_errors,
)


def valid_flow():
    return {
        "display": "grid",
        "singleColumn": True,
        "gap": 12,
        "top": 100,
        "bottom": 188,
        "paddingStart": 0,
        "paddingEnd": 0,
        "borderStart": 0,
        "borderEnd": 0,
        "childCount": 3,
        "children": [
            {"tag": "p", "top": 100, "bottom": 120, "marginStart": 0, "marginEnd": 0},
            {"tag": "p", "top": 132, "bottom": 152, "marginStart": 0, "marginEnd": 0},
            {"tag": "div", "top": 164, "bottom": 188, "marginStart": 0, "marginEnd": 0},
        ],
    }


def rect(top, bottom, left=0, right=240):
    return {"top": top, "bottom": bottom, "left": left, "right": right, "height": bottom - top, "width": right - left}


def valid_shell(stacked=False):
    return {
        "stacked": stacked,
        "sidebar": rect(64, 400 if stacked else 1400),
        "body": rect(64, 1400, 0, 720 if stacked else 1440),
        "main": rect(400 if stacked else 64, 1400, 0 if stacked else 240, 720 if stacked else 1440),
        "footer": rect(1400, 1450, 0, 720 if stacked else 1440),
        "clientWidth": 720 if stacked else 1440,
        "scrollWidth": 720 if stacked else 1440,
    }


class ProductLayoutMeasurementsTests(unittest.TestCase):
    def test_layout_sampler_is_a_bound_capture_producer_input(self):
        from product_style_check import CAPTURE_SOURCE_FILES

        self.assertIn("tools/product_layout_measurements.py", CAPTURE_SOURCE_FILES)

    def test_flow_rejects_additive_margins_and_false_gap_or_edge_reports(self):
        baseline = valid_flow()
        self.assertEqual([], panel_flow_errors([baseline], require_paragraph_pair=True))
        changes = [
            lambda f: f["children"][0].update(marginStart=14),
            lambda f: f["children"][1].update(marginEnd=14),
            lambda f: f["children"][1].update(top=160, bottom=180),
            lambda f: f.update(top=98),
            lambda f: f.update(bottom=190),
            lambda f: f.update(gap=float("nan")),
            lambda f: f.update(childCount=0),
            lambda f: f["children"][0].update(top=float("inf")),
            lambda f: f.update(singleColumn="false"),
            lambda f: f.update(children=None),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                broken = copy.deepcopy(baseline)
                change(broken)
                self.assertTrue(panel_flow_errors([broken], require_paragraph_pair=True))
        self.assertTrue(panel_flow_errors(None))
        self.assertTrue(panel_flow_errors([], require_paragraph_pair=True))
        explicit = copy.deepcopy(baseline)
        explicit["children"][-1].update(top=168, bottom=192, marginStart=4)
        explicit["bottom"] = 192
        self.assertEqual([], panel_flow_errors([explicit]))
        multi_column = copy.deepcopy(baseline)
        multi_column["singleColumn"] = False
        multi_column["children"][1].update(top=100, bottom=120)
        self.assertEqual([], panel_flow_errors([multi_column]))

    def test_sidebar_rejects_viewport_cap_without_changing_width_or_tokens(self):
        for stacked in (False, True):
            baseline = valid_shell(stacked)
            self.assertEqual([], shell_geometry_errors(baseline, stacked=stacked))
            for key in ("sidebar", "main", "body", "footer"):
                broken = copy.deepcopy(baseline)
                broken[key]["bottom"] = float("nan")
                self.assertTrue(shell_geometry_errors(broken, stacked=stacked))
            self.assertTrue(shell_geometry_errors(None, stacked=stacked))
            self.assertTrue(shell_geometry_errors(baseline, stacked=not stacked))
        broken = valid_shell()
        broken["sidebar"] = rect(64, 900)
        self.assertTrue(any("reach the footer" in error for error in shell_geometry_errors(broken, stacked=False)))
        broken = valid_shell(True)
        broken["sidebar"] = rect(64, 420)
        self.assertTrue(any("overlaps" in error for error in shell_geometry_errors(broken, stacked=True)))
        broken = valid_shell()
        broken["scrollWidth"] = 1450
        self.assertTrue(shell_geometry_errors(broken, stacked=False))

    def test_minimal_shared_shell_is_genuinely_short_and_fills_the_viewport(self):
        # Explicit CSS consumer fixture, not an invented short application state.
        styles = "\n".join(
            (REPO / path).read_text(encoding="utf-8")
            for path in (
                "design/ui-reference/assets/tokens.css",
                "packages/ui-components/src/styles.css",
                "apps/desktop/src/app.css",
            )
        )
        document = f"""<!doctype html><html><head><style>{styles}</style></head><body>
          <div class="application-shell"><header class="topbar">Shared shell fixture</header>
            <div class="shell-body"><aside class="sidebar"><nav><button>Home</button></nav></aside>
              <main><section class="ro-page-region"><h1 class="ro-typography">Empty fixture</h1></section></main>
            </div><footer class="trust-footer">Fixture only; no project</footer>
          </div></body></html>"""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(reduced_motion="reduce")
                page.set_content(document)
                for width, height in ((1440, 900), (1280, 720), (720, 450)):
                    for theme in ("light", "dark"):
                        with self.subTest(width=width, theme=theme):
                            page.set_viewport_size({"width": width, "height": height})
                            page.locator("html").evaluate("(node, theme) => node.dataset.theme = theme", theme)
                            page.evaluate(
                                "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
                            )
                            self.assertLessEqual(page.evaluate("document.documentElement.scrollHeight"), height)
                            shell = page.evaluate(SHELL_GEOMETRY)
                            self.assertAlmostEqual(height, shell["footer"]["bottom"], delta=0.5)
                            self.assertEqual([], shell_geometry_errors(shell, stacked=width == 720))
                # A shell that shrinks to its content must not receive a false
                # short-page pass merely because its own three edges still meet.
                page.set_viewport_size({"width": 1440, "height": 900})
                page.add_style_tag(content=".application-shell { min-height: 0; }")
                self.assertLess(page.evaluate(SHELL_GEOMETRY)["footer"]["bottom"], 700)
            finally:
                browser.close()

    def test_actual_product_flow_and_sidebar_with_keyboard_scrolling(self):
        document = inline_product_index(REPO)
        adapter = (REPO / "tests/desktop/fixtures/task_center_interactions.js").read_text(encoding="utf-8")
        adapter = adapter.replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO)) + DIRECTORY_PICKER_FIXTURE
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(reduced_motion="reduce", locale="en-US", timezone_id="UTC")
                context.add_init_script(adapter)
                context.route(
                    "**/*",
                    lambda route: (
                        route.fulfill(status=200, content_type="text/html", body=document)
                        if route.request.url == "http://tauri.localhost/index.html"
                        else route.abort()
                    ),
                )
                page = context.new_page()
                page.goto("http://tauri.localhost/index.html")
                page.wait_for_function("document.body.dataset.applicationReady === 'true'")
                for width, height in ((1440, 900), (1280, 720), (720, 450)):
                    for theme in ("light", "dark"):
                        with self.subTest(state="initial-empty-home", width=width, theme=theme):
                            page.set_viewport_size({"width": width, "height": height})
                            page.locator("html").evaluate("(node, theme) => node.dataset.theme = theme", theme)
                            self.assertEqual(
                                [], shell_geometry_errors(page.evaluate(SHELL_GEOMETRY), stacked=width == 720)
                            )
                page.set_viewport_size({"width": 1440, "height": 900})

                def open_tool(name):
                    disclosure = page.locator("[data-all-tools]")
                    if disclosure.get_attribute("open") is None:
                        disclosure.locator("summary").click()
                    disclosure.get_by_role("button", name=name, exact=True).click()

                open_tool("Local projects")
                choose_fixture_directory(page, "project-root", "C:/Research/study-one")
                page.get_by_role("button", name="Open project", exact=True).click()
                page.locator("[data-current-project]").wait_for(state="visible")
                for tool, selector in (
                    ("Local projects", "[data-projects-workspace]"),
                    ("Task Center", "[data-task-center-workspace]"),
                ):
                    open_tool(tool)
                    workspace = page.locator(selector)
                    workspace.wait_for(state="visible")
                    if tool == "Task Center":
                        page.locator(".task-center-list li").first.wait_for(state="visible")
                    for width, height in ((1440, 900), (1280, 720), (720, 450)):
                        for theme in ("light", "dark"):
                            with self.subTest(tool=tool, width=width, theme=theme):
                                page.set_viewport_size({"width": width, "height": height})
                                page.locator("html").evaluate("(node, theme) => node.dataset.theme = theme", theme)
                                page.evaluate("document.fonts.ready")
                                flows = workspace.evaluate(PANEL_FLOW_GEOMETRY)
                                errors = panel_flow_errors(flows, require_paragraph_pair=tool == "Task Center")
                                errors += shell_geometry_errors(page.evaluate(SHELL_GEOMETRY), stacked=width == 720)
                                # Natural key traversal starts from a clicked disclosure,
                                # not a programmatically focused navigation button.
                                summary = page.locator("[data-all-tools] summary")
                                if page.locator("[data-all-tools]").get_attribute("open") is not None:
                                    summary.click()
                                errors += shell_geometry_errors(page.evaluate(SHELL_GEOMETRY), stacked=width == 720)
                                summary.click()
                                errors += shell_geometry_errors(page.evaluate(SHELL_GEOMETRY), stacked=width == 720)
                                buttons = page.locator("[data-all-tools] button:not(:disabled)")
                                for index in range(buttons.count()):
                                    page.keyboard.press("Tab")
                                    self.assertTrue(
                                        buttons.nth(index).evaluate("node => node === document.activeElement")
                                    )
                                    page.wait_for_function(
                                        "parseFloat(getComputedStyle(document.activeElement).outlineWidth) >= 2"
                                    )
                                    self.assertTrue(
                                        buttons.nth(index).evaluate(
                                            "node => {const r=node.getBoundingClientRect(); "
                                            "return r.top>=-.5 && r.bottom<=innerHeight+.5;}"
                                        )
                                    )
                                for index in range(buttons.count() - 2, -1, -1):
                                    page.keyboard.press("Shift+Tab")
                                    self.assertTrue(
                                        buttons.nth(index).evaluate("node => node === document.activeElement")
                                    )
                                page.evaluate("scrollTo(0, document.documentElement.scrollHeight)")
                                errors += shell_geometry_errors(page.evaluate(SHELL_GEOMETRY), stacked=width == 720)
                                self.assertEqual([], errors)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
