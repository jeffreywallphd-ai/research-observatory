from __future__ import annotations

import copy
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import (  # noqa: E402
    QUALIFICATION_NEUTRAL_SURFACE_BACKGROUND,
    command_plan,
    component_catalog_browser_errors,
    core_workflow_catalog_json,
    design_system_errors,
    inline_product_index,
    page_error_collector,
    product_build_errors,
    product_style_qualification_errors,
    qualification_capture_contract,
    qualification_measurement_errors,
    runtime_frame_errors,
    security_errors,
    style_surface_matrix_errors,
    tool_environment,
)


def valid_style_surface_matrix() -> dict[str, Any]:
    responsive = []
    for width, height, padding in ((1440, 900, 28), (1280, 720, 20), (720, 450, 16)):
        light_surface = "rgb(255, 255, 255)"
        dark_surface = "rgb(11, 31, 55)"
        text_scale = 2 if width == 720 else 1
        responsive.append(
            {
                "viewport": [width, height],
                "documentOverflow": False,
                "contentDocumentOverflow": False,
                "mainPaddingInlineStart": padding,
                "topbarHeight": 64,
                "sidebarWidth": 240 if width == 1440 else width,
                "pageGap": 24,
                "gridGap": 16,
                "controlHeight": 40,
                "primaryControlHeight": 44,
                "states": {"empty": True, "recovery": True, "warning": True},
                "surfaces": {
                    "card": {"paddingInlineStart": 16, "borderRadius": 10},
                    "panel": {"paddingInlineStart": 16, "borderRadius": 10},
                    "form": {"display": "grid", "rowGap": 20},
                    "control": {"height": 40, "borderRadius": 10},
                    "notice": {"display": "grid", "paddingInlineStart": 16, "borderRadius": 10},
                    "actionRow": {"display": "flex", "flexWrap": "wrap"},
                    "dialog": {
                        "display": "grid",
                        "overflowY": "auto",
                        "width": 640 if width == 720 else 400,
                        "height": 370 if width == 720 else 275,
                        "paddingInlineStart": 20 * text_scale,
                        "borderRadius": 10 * text_scale,
                        "focusContained": True,
                        "containedVerticalOverflow": width == 720,
                        "scrolledWithinSurface": True,
                        "scaledClientHeight": 368 if width == 720 else 273,
                        "scaledScrollHeight": 624 if width == 720 else 273,
                    },
                },
                "themes": {
                    "light": {
                        "theme": "light",
                        "surface1": light_surface,
                        "surface2": "rgb(248, 250, 253)",
                        "textDefault": "rgb(36, 59, 85)",
                        "cardBackground": light_surface,
                        "panelBackground": light_surface,
                        "noticeBackground": "rgb(248, 250, 253)",
                        "cardColor": "rgb(36, 59, 85)",
                    },
                    "dark": {
                        "theme": "dark",
                        "surface1": dark_surface,
                        "surface2": "rgb(16, 39, 64)",
                        "textDefault": "rgb(215, 226, 239)",
                        "cardBackground": dark_surface,
                        "panelBackground": dark_surface,
                        "noticeBackground": "rgb(16, 39, 64)",
                        "cardColor": "rgb(215, 226, 239)",
                    },
                },
                "reducedMotion": [{"transitionDuration": "0.00001s", "animationDuration": "0.01ms"}],
                "textScalePercent": 200 if width == 720 else 100,
                "textScale": {
                    "initialRootFontSize": 16,
                    "rootFontSize": 16 * text_scale,
                    "bodyFontSize": 14 * text_scale,
                    "dialogFontSize": 14 * text_scale,
                    "headingFontSize": 18 * text_scale,
                    "available": True,
                    "profileNameLength": len("Local profile"),
                    "scaledDocumentOverflow": False,
                    "documentClientWidth": width,
                    "documentScrollWidth": width,
                    "triggerHitTarget": True,
                    "allActionsWithinTopbar": True,
                    "sidebarAfterTopbar": True,
                    "topbarBottom": 128 if width == 720 else 64,
                    "triggerBottom": 112 if width == 720 else 52,
                    "maxActionBottom": 112 if width == 720 else 52,
                    "sidebarTop": 128 if width == 720 else 64,
                },
            }
        )
    tables = {
        name: {
            "accessibleName": name,
            "tabIndex": 0,
            "focused": True,
            "focusOutlineWidth": 2,
            "overflowX": "auto",
            "documentOverflow": False,
            "containedHorizontalOverflow": name != "Recent diagnostics table scroll region",
            "rowCount": 10 if name == "Audit lineage table scroll region" else 4,
            **{
                field: 8 if name == "Recent diagnostics table scroll region" else 12
                for field in (
                    "headerPaddingInlineStart",
                    "headerPaddingInlineEnd",
                    "headerPaddingBlockStart",
                    "headerPaddingBlockEnd",
                    "dataPaddingInlineStart",
                    "dataPaddingInlineEnd",
                    "dataPaddingBlockStart",
                    "dataPaddingBlockEnd",
                )
            },
            "headerRowHeight": 38 if name == "Recent diagnostics table scroll region" else 44,
            "dataRowHeight": 38 if name == "Recent diagnostics table scroll region" else 44,
        }
        for name in (
            "Recent diagnostics table scroll region",
            "Recalculation impact table scroll region",
            "Audit lineage table scroll region",
        )
    }

    return {
        "responsive": responsive,
        "longProfile": {
            "baseline": {
                "available": True,
                "rootFontSize": 16,
                "bodyFontSize": 14,
                "profileNameLength": 80,
                "scaledDocumentOverflow": False,
                "documentClientWidth": 720,
                "documentScrollWidth": 720,
                "normalClick": True,
                "triggerHitTarget": True,
                "allActionsWithinTopbar": True,
                "sidebarAfterTopbar": True,
                "topbarBottom": 114,
                "maxActionBottom": 100,
                "sidebarTop": 114,
            },
            "scaled": {
                "available": True,
                "rootFontSize": 32,
                "bodyFontSize": 28,
                "profileNameLength": 80,
                "scaledDocumentOverflow": False,
                "documentClientWidth": 720,
                "documentScrollWidth": 720,
                "normalClick": True,
                "triggerHitTarget": True,
                "allActionsWithinTopbar": True,
                "sidebarAfterTopbar": True,
                "topbarBottom": 531,
                "maxActionBottom": 500,
                "sidebarTop": 531,
            },
        },
        "tableRegions": tables,
        "longContent": {
            "containedVerticalOverflow": True,
            "scrolledWithinSurface": True,
            "documentOverflow": False,
        },
        "lockRecovery": {
            "locked": True,
            "recoveryRequired": True,
            "noticeVisible": True,
            "focusContained": True,
            "documentOverflow": False,
        },
        "errorState": {"visible": True, "color": "rgb(198, 40, 40)", "dangerToken": "rgb(198, 40, 40)"},
    }


def valid_product_style_qualification_matrix() -> dict[str, Any]:
    workspaces = (
        ("projects", "Local projects", ["projects.html", "new-project.html"], "populated-project-list"),
        ("home", "Project home", ["index.html"], "project-ready"),
        ("intent", "Research intent", ["intent-contract.html"], "accepted-intent"),
        ("tasks", "Task Center", ["task-center.html"], "populated-task-center"),
        ("audit", "Audit & lineage", ["audit-lineage.html"], "populated-lineage"),
        ("settings", "Project settings", ["project-settings.html"], "project-settings"),
        (
            "application-settings",
            "Application settings",
            ["application-settings.html"],
            "application-settings",
        ),
        ("diagnostics", "Diagnostics & support", ["help-onboarding.html"], "populated-diagnostics"),
    )
    cases: list[dict[str, Any]] = []
    for workspace_id, _, pages, state_id in workspaces:
        for width, height in ((1440, 900), (1280, 720), (720, 450)):
            for theme in ("light", "dark"):
                cases.append(
                    {
                        "caseId": f"workspace:{workspace_id}:{theme}:{width}x{height}",
                        "surfaceId": workspace_id,
                        "stateId": state_id,
                        "theme": theme,
                        "viewport": {"width": width, "height": height},
                        "role": "product",
                        "referencePage": pages[0],
                        "width": width,
                        "height": height,
                        "geometry": {
                            "documentClientWidth": width,
                            "documentScrollWidth": width,
                            "surfaceLeft": 16,
                            "surfaceTop": 80,
                            "surfaceRight": width - 16,
                            "surfaceBottom": height + 80,
                            "surfaceWidth": width - 32,
                            "surfaceHeight": height,
                        },
                        "focus": {
                            "targetCount": 2,
                            "targetFocused": True,
                            "accessibleName": "Representative action",
                            "outlineWidth": 2,
                        },
                        "overflow": {
                            "documentHorizontal": False,
                            "surfaceOverflowX": "visible",
                            "surfaceOverflowY": "visible",
                        },
                        "themeTokens": {
                            "theme": theme,
                            "surface1": "rgb(255, 255, 255)" if theme == "light" else "rgb(11, 31, 55)",
                            "textDefault": "rgb(36, 59, 85)" if theme == "light" else "rgb(215, 226, 239)",
                            "workspaceBackground": ("rgb(255, 255, 255)" if theme == "light" else "rgb(11, 31, 55)"),
                        },
                        "reducedMotion": {
                            "mediaMatches": True,
                            "transitionDuration": "0s",
                            "animationDuration": "0s",
                        },
                    }
                )
    designated_cases: list[dict[str, Any]] = []
    for surface_id, state_id, reference_page in (
        ("application-lock", "locked", "application-settings.html"),
        ("local-service-boundary", "recovery-required", "application-settings.html"),
        ("shortcut-dialog", "shortcut-dialog", "help-onboarding.html"),
    ):
        for theme in ("light", "dark"):
            designated_cases.append(
                {
                    "caseId": f"boundary:{state_id}:{theme}:720x450",
                    "surfaceId": surface_id,
                    "stateId": state_id,
                    "theme": theme,
                    "viewport": {"width": 720, "height": 450},
                    "role": "product",
                    "referencePage": reference_page,
                    "width": 720,
                    "height": 450,
                    "geometry": {
                        "surfaceLeft": 24,
                        "surfaceTop": 24,
                        "surfaceRight": 696,
                        "surfaceBottom": 426,
                        "surfaceWidth": 672,
                        "surfaceHeight": 402,
                    },
                    "focus": {
                        "targetFocused": True,
                        "focusContained": True,
                        "accessibleName": "Recovery action" if state_id != "shortcut-dialog" else "Close shortcuts",
                        "outlineWidth": 2,
                    },
                    "overflow": {
                        "documentHorizontal": False,
                        "containedVertical": state_id == "shortcut-dialog",
                        "scrolledWithinSurface": state_id == "shortcut-dialog",
                    },
                    "stateVisible": True,
                }
            )
    return {
        "workspaces": [
            {
                "id": workspace_id,
                "label": label,
                "pageContractIds": pages,
                "referencePage": pages[0],
                "stateId": state_id,
            }
            for workspace_id, label, pages, state_id in workspaces
        ],
        "cases": cases,
        "designatedCases": designated_cases,
    }


class DesktopAppCheckTests(unittest.TestCase):
    def test_neutral_workspace_measurement_is_not_replaced_by_tonal_or_hidden_panels(self) -> None:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                for theme, background in (("light", "rgb(255, 255, 255)"), ("dark", "rgb(11, 31, 55)")):
                    page.set_content(
                        '<section id="workspace"><div class="ro-panel" data-tone="success" '
                        'style="background:rgb(0, 128, 0)">Ready</div>'
                        '<div class="ro-card" style="display:none;background:rgb(255,0,0)">Hidden</div>'
                        f'<div class="ro-panel" data-tone="neutral" style="background:{background}">'
                        'Create a project</div></section>'
                    )
                    workspace = page.locator("#workspace")
                    self.assertEqual(background, workspace.evaluate(QUALIFICATION_NEUTRAL_SURFACE_BACKGROUND))
                    neutral = page.locator('[data-tone="neutral"]')
                    self.assertEqual(background, neutral.evaluate(QUALIFICATION_NEUTRAL_SURFACE_BACKGROUND))
                    neutral.evaluate("node => node.style.background = 'rgb(255, 0, 0)'")
                    measured = workspace.evaluate(QUALIFICATION_NEUTRAL_SURFACE_BACKGROUND)
                    self.assertEqual("rgb(255, 0, 0)", measured)
                    self.assertNotEqual(background, measured)
                    for invalid in (measured, None):
                        matrix = valid_product_style_qualification_matrix()
                        case = next(item for item in matrix["cases"]
                                    if item["surfaceId"] == "projects" and item["theme"] == theme)
                        case["themeTokens"]["workspaceBackground"] = invalid
                        self.assertTrue(any(
                            f"apply {theme} workspace tokens" in error
                            for error in product_style_qualification_errors(matrix)
                        ))
                    neutral.evaluate("node => node.style.visibility = 'hidden'")
                    self.assertIsNone(workspace.evaluate(QUALIFICATION_NEUTRAL_SURFACE_BACKGROUND))
                    neutral.evaluate("node => node.style.visibility = 'visible'")
                    neutral.evaluate("node => node.hidden = true")
                    self.assertIsNone(workspace.evaluate(QUALIFICATION_NEUTRAL_SURFACE_BACKGROUND))
                    neutral.evaluate("node => node.remove()")
                    self.assertIsNone(workspace.evaluate(QUALIFICATION_NEUTRAL_SURFACE_BACKGROUND))
            finally:
                browser.close()

    def test_qualification_measurements_bind_renderer_geometry_and_reachable_states(self) -> None:
        case = {
            "surfaceId": "home",
            "stateId": "project-ready",
            "width": 1440,
            "theme": "light",
            "fonts": {"Segoe UI": True, "Georgia": True, "Consolas": True},
            "observedEnvironment": {
                "deviceScaleFactor": 1,
                "locale": "en-US",
                "timezoneId": "UTC",
                "now": 1786190400000,
                "random": 0.25,
            },
            "stateVisible": True,
            "stateWitness": {"home": True},
            "focus": {"targetInViewport": True},
            "geometry": {"mainPadding": 28},
            "semantic": [
                {
                    "kind": "card",
                    "padding": 16,
                    "radius": 10,
                    "gap": 12,
                    "minHeight": 0,
                    "height": 120,
                    "display": "grid",
                    "wrap": "nowrap",
                    "overflowX": "visible",
                },
                {
                    "kind": "control",
                    "padding": 16,
                    "radius": 10,
                    "gap": 0,
                    "minHeight": 40,
                    "height": 40,
                    "display": "inline-block",
                    "wrap": "nowrap",
                    "overflowX": "visible",
                },
                {
                    "kind": "grid",
                    "padding": 0,
                    "radius": 0,
                    "gap": 16,
                    "minHeight": 0,
                    "height": 120,
                    "display": "grid",
                    "wrap": "nowrap",
                    "overflowX": "visible",
                },
            ],
        }
        self.assertEqual([], qualification_measurement_errors(case))
        mutations = [
            lambda item: item["stateWitness"].__setitem__("home", False),
            lambda item: item["fonts"].__setitem__("Georgia", False),
            lambda item: item["observedEnvironment"].__setitem__("now", 0),
            lambda item: item["observedEnvironment"].__setitem__("deviceScaleFactor", 2),
            lambda item: item["geometry"].__setitem__("mainPadding", 27),
            lambda item: item["focus"].__setitem__("targetInViewport", False),
            lambda item: item["semantic"].pop(),
            lambda item: item["semantic"][0].__setitem__("padding", 17),
            lambda item: item["semantic"][0].__setitem__("radius", 25),
            lambda item: item["semantic"][1].__setitem__("minHeight", 24),
            lambda item: item["semantic"][2].__setitem__("gap", float("nan")),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(case)
            mutate(changed)
            self.assertTrue(qualification_measurement_errors(changed))

    def test_product_style_qualification_contract_is_exact_and_rejects_matrix_gaps(self) -> None:
        capture_contract = qualification_capture_contract(REPO)
        self.assertEqual(108, len(capture_contract))
        self.assertEqual(54, len({item["caseId"] for item in capture_contract}))
        self.assertEqual({"product", "reference"}, {item["role"] for item in capture_contract})
        self.assertTrue(
            all(
                set(item)
                == {
                    "caseId",
                    "surfaceId",
                    "stateId",
                    "theme",
                    "viewport",
                    "role",
                    "referencePage",
                    "width",
                    "height",
                }
                for item in capture_contract
            )
        )
        self.assertTrue(
            all(item["viewport"] == {"width": item["width"], "height": item["height"]} for item in capture_contract)
        )
        baseline = valid_product_style_qualification_matrix()
        self.assertEqual([], product_style_qualification_errors(baseline))

        mutations = {
            "missing workspace": (
                lambda matrix: matrix["workspaces"].pop(),
                "missing implemented workspaces",
            ),
            "duplicate workspace": (
                lambda matrix: matrix["workspaces"].append(copy.deepcopy(matrix["workspaces"][0])),
                "duplicate workspaces",
            ),
            "workspace mapping": (
                lambda matrix: matrix["workspaces"][0].__setitem__("pageContractIds", ["new-project.html"]),
                "workspace mapping differs",
            ),
            "missing theme": (
                lambda matrix: matrix["cases"].__setitem__(
                    slice(None), [case for case in matrix["cases"] if case["theme"] != "dark"]
                ),
                "missing workspace/theme/viewport cases",
            ),
            "missing viewport": (
                lambda matrix: matrix["cases"].__setitem__(
                    slice(None),
                    [case for case in matrix["cases"] if case["viewport"] != {"width": 1280, "height": 720}],
                ),
                "missing workspace/theme/viewport cases",
            ),
            "duplicate workspace theme viewport": (
                lambda matrix: matrix["cases"].append(copy.deepcopy(matrix["cases"][0])),
                "duplicate workspace/theme/viewport cases",
            ),
            "nonfinite geometry": (
                lambda matrix: matrix["cases"][0]["geometry"].__setitem__("surfaceWidth", float("nan")),
                "missing or nonfinite geometry",
            ),
            "escaped geometry": (
                lambda matrix: matrix["cases"][0]["geometry"].__setitem__("surfaceRight", 2000),
                "geometry escapes horizontally",
            ),
            "missing focus name": (
                lambda matrix: matrix["cases"][0]["focus"].__setitem__("accessibleName", ""),
                "named visible keyboard focus",
            ),
            "invisible focus": (
                lambda matrix: matrix["cases"][0]["focus"].__setitem__("outlineWidth", 0),
                "named visible keyboard focus",
            ),
            "document overflow": (
                lambda matrix: matrix["cases"][0]["overflow"].__setitem__("documentHorizontal", True),
                "invalid overflow containment",
            ),
            "wrong theme token": (
                lambda matrix: matrix["cases"][0]["themeTokens"].__setitem__("workspaceBackground", "red"),
                "workspace tokens",
            ),
            "motion": (
                lambda matrix: matrix["cases"][0]["reducedMotion"].__setitem__("transitionDuration", "120ms"),
                "suppress motion",
            ),
            "missing designated state": (
                lambda matrix: matrix["designatedCases"].pop(),
                "missing designated cases",
            ),
            "duplicate designated state": (
                lambda matrix: matrix["designatedCases"].append(copy.deepcopy(matrix["designatedCases"][0])),
                "duplicate designated cases",
            ),
            "designated viewport escape": (
                lambda matrix: matrix["designatedCases"][0]["geometry"].__setitem__("surfaceRight", 800),
                "designated surface escapes the viewport",
            ),
            "designated focus containment": (
                lambda matrix: matrix["designatedCases"][0]["focus"].__setitem__("focusContained", False),
                "contained visible focus",
            ),
            "dialog scroll containment": (
                lambda matrix: next(case for case in matrix["designatedCases"] if case["stateId"] == "shortcut-dialog")[
                    "overflow"
                ].__setitem__("containedVertical", False),
                "dialog does not retain contained scrolling",
            ),
        }
        for name, (mutate, expected) in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(baseline)
                mutate(changed)
                self.assertTrue(any(expected in error for error in product_style_qualification_errors(changed)))

    def test_built_product_exposes_only_implemented_functional_workspaces_and_is_keyboard_accessible(self) -> None:
        errors, details = runtime_frame_errors(REPO)

        self.assertEqual([], errors)
        self.assertEqual(1, details["pages"])
        self.assertEqual(
            [
                "CAP-01",
                "CAP-02.S01.T03",
                "CAP-02.S04.T02",
                "CAP-02.S04.T03",
                "CAP-03.S02.T02",
                "CAP-03.S03.T03",
                "CAP-03.S05.T03",
                "CAP-03.S06.T02",
                "CAP-03.S06.T03",
                "CAP-03.S06.T04",
                "CAP-03.S06.T05",
            ],
            details["implementedCapabilities"],
        )
        self.assertTrue(details["adaptiveWorkflowNavigation"])
        self.assertTrue(details["workflowProfileMatrixValid"])
        matrix = details["workflowProfileMatrix"]
        # A new presentation does not relabel persisted scholarly workflows.
        activation = json.loads((REPO / "verification/extensions/desktop-ui.json").read_text(encoding="utf-8"))
        self.assertEqual("RO-UI-ACADEMIC-MINIMAL-1.6", activation["referenceId"])
        self.assertEqual("RO-UI-ACADEMIC-MINIMAL-1.5", matrix["referenceId"])
        self.assertEqual("1.5", matrix["referenceVersion"])
        self.assertEqual("1.0.0", matrix["profileCatalogVersion"])
        self.assertEqual(
            "sha256:0a3887774b30bb2d2d7fced5c9e43452e7e34993407a6122155b740814350e49",
            matrix["profileCatalogHash"],
        )
        self.assertEqual(
            "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2",
            matrix["intentGuidanceHash"],
        )
        self.assertTrue(matrix["allToolsAccessible"])
        self.assertEqual(14, len(matrix["profiles"]))
        self.assertEqual(
            {"hermeneutic-inquiry", "living-review", "manuscript-review-revision"},
            {profile["profileId"] for profile in matrix["profiles"] if profile["processForm"] == "revisitable"},
        )
        self.assertTrue(all(profile["valid"] for profile in matrix["profiles"]))
        self.assertTrue(details["intentMutationRaceGuarded"])
        self.assertEqual(0, details["referenceOnlyPages"])
        self.assertTrue(details["commandFocus"])
        self.assertTrue(details["skipLink"])
        self.assertTrue(details["shortcutDialog"])
        self.assertTrue(details["focusContainment"])
        self.assertTrue(details["focusRestoration"])
        self.assertTrue(details["focusVisible"])
        self.assertTrue(details["keyboardCommand"])
        self.assertTrue(details["homeShortcut"])
        self.assertTrue(details["themeToggle"])
        self.assertTrue(details["liveRegion"])
        self.assertTrue(details["boundaryState"])
        self.assertTrue(details["boundaryRecovery"])
        self.assertTrue(details["applicationLockEventAclStartup"])
        self.assertEqual(
            {
                "defaultNoLogin": True,
                "deniedListener": True,
                "timedOutListener": True,
                "malformedEvent": True,
            },
            details["applicationLockEventAclStartupCases"],
        )
        self.assertTrue(details["retainedInput"])
        self.assertTrue(details["diagnosticCopy"])
        self.assertEqual(3, details["responsiveCases"])
        self.assertEqual([28, 20, 16], [case["mainPaddingInlineStart"] for case in details["styleGeometry"]])
        self.assertTrue(all(case["topbarHeight"] == 64 for case in details["styleGeometry"]))
        self.assertTrue(all(case["pageGap"] == 24 for case in details["styleGeometry"]))
        self.assertTrue(all(case["gridGap"] == 16 for case in details["styleGeometry"]))
        self.assertTrue(all(case["controlHeight"] >= 40 for case in details["styleGeometry"]))
        self.assertTrue(all(case["primaryControlHeight"] >= 44 for case in details["styleGeometry"]))
        self.assertTrue(all(not case["documentOverflow"] for case in details["styleGeometry"]))
        self.assertEqual(240, details["styleGeometry"][0]["sidebarWidth"])
        style_matrix = details["styleSurfaceMatrix"]
        self.assertEqual([], style_surface_matrix_errors(style_matrix))
        self.assertEqual(
            {
                "Recent diagnostics table scroll region",
                "Recalculation impact table scroll region",
                "Audit lineage table scroll region",
            },
            set(style_matrix["tableRegions"]),
        )
        self.assertEqual(
            8,
            style_matrix["tableRegions"]["Recent diagnostics table scroll region"]["dataPaddingInlineStart"],
        )
        self.assertEqual(
            12,
            style_matrix["tableRegions"]["Audit lineage table scroll region"]["headerPaddingBlockStart"],
        )
        self.assertGreaterEqual(style_matrix["tableRegions"]["Audit lineage table scroll region"]["dataRowHeight"], 44)
        self.assertTrue(all(case["states"]["empty"] for case in style_matrix["responsive"]))
        self.assertTrue(all(case["states"]["recovery"] for case in style_matrix["responsive"]))
        self.assertTrue(all(case["states"]["warning"] for case in style_matrix["responsive"]))
        self.assertTrue(style_matrix["longContent"]["containedVerticalOverflow"])
        self.assertTrue(style_matrix["lockRecovery"]["focusContained"])
        self.assertTrue(style_matrix["errorState"]["visible"])
        self.assertEqual(32, style_matrix["responsive"][2]["textScale"]["rootFontSize"])
        self.assertEqual(28, style_matrix["responsive"][2]["textScale"]["bodyFontSize"])
        self.assertEqual(36, style_matrix["responsive"][2]["textScale"]["headingFontSize"])

        escaped_dialog = copy.deepcopy(style_matrix)
        escaped_dialog["responsive"][2]["surfaces"]["dialog"]["containedVerticalOverflow"] = False
        self.assertTrue(any("dialog" in error for error in style_surface_matrix_errors(escaped_dialog)))
        unnamed_table = copy.deepcopy(style_matrix)
        unnamed_table["tableRegions"]["Audit lineage table scroll region"]["accessibleName"] = None
        self.assertTrue(any("named and tabbable" in error for error in style_surface_matrix_errors(unnamed_table)))
        theme_drift = copy.deepcopy(style_matrix)
        theme_drift["responsive"][0]["themes"]["dark"]["cardBackground"] = "rgb(255, 0, 0)"
        self.assertTrue(any("--surface-1" in error for error in style_surface_matrix_errors(theme_drift)))
        self.assertEqual([], details["criticalViolations"])
        self.assertEqual([], details["requests"])
        self.assertEqual(6, details["designSystem"]["cases"])
        self.assertEqual(10_000, details["largeTable"]["totalRows"])
        self.assertEqual(50, details["largeTable"]["maximumRenderedRows"])
        self.assertTrue(details["largeTable"]["keyboardTransitions"])
        self.assertTrue(details["largeTable"]["focusPreserved"])
        self.assertTrue(details["largeTable"]["disabledBoundaries"])
        self.assertTrue(details["largeTable"]["compact"])

    def test_style_surface_matrix_rejects_each_named_regression(self) -> None:
        baseline = valid_style_surface_matrix()
        self.assertEqual([], style_surface_matrix_errors(baseline))

        mutations = {
            "missing geometry": (
                lambda matrix: matrix["responsive"][0].pop("topbarHeight"),
                "shell rhythm",
            ),
            "nonfinite geometry": (
                lambda matrix: matrix["responsive"][0].__setitem__("controlHeight", float("nan")),
                "undersized",
            ),
            "invalid geometry": (
                lambda matrix: matrix["responsive"][1]["surfaces"]["dialog"].__setitem__("width", "wide"),
                "escapes the viewport",
            ),
            "document overflow": (
                lambda matrix: matrix["responsive"][1].__setitem__("contentDocumentOverflow", True),
                "escapes the document",
            ),
            "table inventory": (
                lambda matrix: matrix["tableRegions"].pop("Recent diagnostics table scroll region"),
                "all three",
            ),
            "table focus": (
                lambda matrix: matrix["tableRegions"]["Audit lineage table scroll region"].__setitem__(
                    "focused", False
                ),
                "visible keyboard focus",
            ),
            "table cell padding": (
                lambda matrix: matrix["tableRegions"]["Recent diagnostics table scroll region"].__setitem__(
                    "dataPaddingInlineStart", 0
                ),
                "canonical padding",
            ),
            "table row height": (
                lambda matrix: matrix["tableRegions"]["Audit lineage table scroll region"].__setitem__(
                    "dataRowHeight", 12
                ),
                "representative minimum",
            ),
            "dialog containment": (
                lambda matrix: matrix["responsive"][2]["surfaces"]["dialog"].__setitem__(
                    "containedVerticalOverflow", False
                ),
                "dialog",
            ),
            "declared text scale without computed scale": (
                lambda matrix: matrix["responsive"][2]["textScale"].__setitem__("rootFontSize", 16),
                "computed 200% text scale",
            ),
            "scaled shortcut trigger overlap": (
                lambda matrix: matrix["responsive"][2]["textScale"].__setitem__("triggerHitTarget", False),
                "200% text Shortcuts trigger",
            ),
            "scaled long-profile document overflow": (
                lambda matrix: matrix["longProfile"]["scaled"].__setitem__("scaledDocumentOverflow", True),
                "long-profile shell escapes",
            ),
            "theme token": (
                lambda matrix: matrix["responsive"][0]["themes"]["dark"].__setitem__(
                    "cardBackground", "rgb(255, 0, 0)"
                ),
                "--surface-1",
            ),
            "reduced motion": (
                lambda matrix: matrix["responsive"][0]["reducedMotion"][0].__setitem__("transitionDuration", "0.12s"),
                "suppress motion",
            ),
            "required state": (
                lambda matrix: matrix["responsive"][0]["states"].__setitem__("empty", False),
                "empty, recovery, or warning",
            ),
            "long content": (
                lambda matrix: matrix["longContent"].__setitem__("containedVerticalOverflow", False),
                "long-content",
            ),
            "lock recovery": (
                lambda matrix: matrix["lockRecovery"].__setitem__("recoveryRequired", False),
                "locked recovery",
            ),
            "error state": (
                lambda matrix: matrix["errorState"].__setitem__("visible", False),
                "error notice",
            ),
        }
        for name, (mutate, expected) in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(baseline)
                mutate(changed)
                self.assertTrue(any(expected in error for error in style_surface_matrix_errors(changed)))

    def test_security_boundary_and_complete_command_plan(self) -> None:
        self.assertEqual([], security_errors(REPO))
        commands = command_plan(REPO)
        self.assertEqual(9, len(commands))
        rendered = [" ".join(command) for command in commands]
        self.assertTrue(any("ui-components" in command and "verify" in command for command in rendered))
        self.assertTrue(any("pnpm" in command and "build" in command for command in rendered))
        self.assertTrue(any("clippy" in command and "--locked" in command for command in rendered))
        self.assertTrue(any("cargo.exe test" in command and "--locked" in command for command in rendered))
        self.assertEqual("true", tool_environment(REPO)[0]["CI"])

    def test_external_development_url_and_privilege_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            source = REPO / "apps" / "desktop" / "src-tauri"
            shutil.copytree(source, root / "apps" / "desktop" / "src-tauri")
            config_path = root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["build"]["devUrl"] = "https://example.invalid"
            config["app"]["security"]["csp"] += "; connect-src https://example.invalid"
            config_path.write_text(json.dumps(config), encoding="utf-8", newline="\n")
            capability_path = root / "apps" / "desktop" / "src-tauri" / "capabilities" / "main-window.json"
            capability = json.loads(capability_path.read_text(encoding="utf-8"))
            capability["permissions"] = ["core:default"]
            capability_path.write_text(json.dumps(capability), encoding="utf-8", newline="\n")

            errors = security_errors(root)

        self.assertTrue(any("development URL" in error for error in errors))
        self.assertTrue(any("Tauri CSP" in error for error in errors))
        self.assertTrue(any("receive-only event permissions" in error for error in errors))

    def test_event_capability_rejects_missing_widened_or_renderer_write_authority(self) -> None:
        devtools = "core:webview:allow-internal-toggle-devtools"
        listen = "core:event:allow-listen"
        unlisten = "core:event:allow-unlisten"
        expected = [devtools, listen, unlisten]
        adversarial_capabilities = {
            "missing-listen": {"permissions": [devtools, unlisten]},
            "missing-unlisten": {"permissions": [devtools, listen]},
            "added-emit": {"permissions": [*expected, "core:event:allow-emit"]},
            "added-emit-to": {"permissions": [*expected, "core:event:allow-emit-to"]},
            "added-event-default": {"permissions": [*expected, "core:event:default"]},
            "added-core-default": {"permissions": [*expected, "core:default"]},
            "added-arbitrary-permission": {"permissions": [*expected, "core:app:allow-version"]},
            "widened-windows": {"permissions": expected, "windows": ["main", "*"]},
            "remote-origin": {
                "permissions": expected,
                "remote": {"urls": ["https://example.invalid"]},
            },
        }

        for case, mutation in adversarial_capabilities.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "repo"
                source = REPO / "apps" / "desktop" / "src-tauri"
                shutil.copytree(source, root / "apps" / "desktop" / "src-tauri")
                capability_path = root / "apps" / "desktop" / "src-tauri" / "capabilities" / "main-window.json"
                capability = json.loads(capability_path.read_text(encoding="utf-8"))
                capability.update(mutation)
                capability_path.write_text(json.dumps(capability), encoding="utf-8", newline="\n")

                errors = security_errors(root)

                self.assertTrue(
                    any("receive-only event permissions" in error for error in errors),
                    errors,
                )

    def test_generated_capability_projection_cannot_diverge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            source = REPO / "apps" / "desktop" / "src-tauri"
            shutil.copytree(source, root / "apps" / "desktop" / "src-tauri")
            generated_path = root / "apps" / "desktop" / "src-tauri" / "gen" / "schemas" / "capabilities.json"
            generated = json.loads(generated_path.read_text(encoding="utf-8"))
            generated["main-window"]["permissions"].append("core:event:allow-emit")
            generated_path.write_text(json.dumps(generated), encoding="utf-8", newline="\n")

            errors = security_errors(root)

        self.assertTrue(any("generated Tauri capability projection" in error for error in errors), errors)

    def test_product_bundle_rejects_reference_pages_and_tauri_fixture_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(
                REPO / "apps" / "desktop",
                root / "apps" / "desktop",
                ignore=shutil.ignore_patterns("dist", "node_modules", "target"),
            )
            for package in ("ui-components", "ui-tokens"):
                shutil.copytree(
                    REPO / "packages" / package,
                    root / "packages" / package,
                    ignore=shutil.ignore_patterns("node_modules", "target"),
                )
            for relative in ("Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / relative, destination)
            activation = root / "verification" / "extensions" / "desktop-ui.json"
            activation.parent.mkdir(parents=True)
            shutil.copy2(REPO / "verification" / "extensions" / "desktop-ui.json", activation)
            site = root / "design" / "ui-reference" / "SITE_MANIFEST.json"
            site.parent.mkdir(parents=True)
            shutil.copy2(REPO / "design" / "ui-reference" / "SITE_MANIFEST.json", site)
            component_source = root / "packages" / "ui-components" / "src" / "index.tsx"
            component_source.write_text(
                component_source.read_text(encoding="utf-8") + "\n// unbound product source\n",
                encoding="utf-8",
                newline="\n",
            )
            source_errors = product_build_errors(root)
            self.assertTrue(any("exact product build inputs" in error for error in source_errors), source_errors)
            shutil.copy2(REPO / "packages" / "ui-components" / "src" / "index.tsx", component_source)
            (root / "apps" / "desktop" / "product-dist" / "study-design.html").write_text(
                "<!doctype html><title>reference leak</title>", encoding="utf-8"
            )
            config_path = root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["build"]["frontendDist"] = "../dist"
            config_path.write_text(json.dumps(config), encoding="utf-8", newline="\n")

            errors = product_build_errors(root)

        self.assertTrue(any("only the functional index/runtime inventory" in error for error in errors), errors)
        self.assertTrue(any("serve only apps/desktop/product-dist" in error for error in errors), errors)
        self.assertTrue(any("reference-only pages" in error for error in errors), errors)

    def test_every_unreviewed_connection_source_fails_closed(self) -> None:
        for source in (
            "wss://example.invalid",
            "data:",
            "example.invalid",
            "ipc.evil:",
            "http://ipc.localhost.evil",
        ):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "repo"
                tauri = REPO / "apps" / "desktop" / "src-tauri"
                shutil.copytree(tauri, root / "apps" / "desktop" / "src-tauri")
                config_path = root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
                config = json.loads(config_path.read_text(encoding="utf-8"))
                config["app"]["security"]["csp"] = config["app"]["security"]["csp"].replace(
                    "connect-src ipc: http://ipc.localhost",
                    f"connect-src ipc: http://ipc.localhost {source}",
                )
                config_path.write_text(json.dumps(config), encoding="utf-8", newline="\n")

                errors = security_errors(root)

            self.assertTrue(any("offline source allowlist" in error for error in errors), errors)

    def test_design_system_is_reference_bound_and_rejects_all_literal_style_drift(self) -> None:
        self.assertEqual([], design_system_errors(REPO))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REPO / "packages" / "ui-tokens", root / "packages" / "ui-tokens")
            shutil.copytree(REPO / "packages" / "ui-components", root / "packages" / "ui-components")
            token_source = root / "design" / "ui-reference" / "assets" / "tokens.css"
            token_source.parent.mkdir(parents=True)
            shutil.copy2(REPO / "design" / "ui-reference" / "assets" / "tokens.css", token_source)
            shutil.copy2(REPO / "pnpm-lock.yaml", root / "pnpm-lock.yaml")
            styles = root / "packages" / "ui-components" / "src" / "styles.css"
            styles.write_text(styles.read_text(encoding="utf-8") + "\n.attack { color: red; }\n", encoding="utf-8")
            components = root / "packages" / "ui-components" / "src" / "index.tsx"
            components.write_text(
                components.read_text(encoding="utf-8")
                + "\nexport function Attack() { return <span style={{ color: 'red' }}>attack</span>; }\n",
                encoding="utf-8",
            )
            transport = root / "packages" / "ui-tokens" / "index.css"
            transport.write_text('@import "https://example.invalid/tokens.css";\n', encoding="utf-8")
            catalog = root / "packages" / "ui-components" / "catalog.html"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    'data-boundary-state="recovery-required"', 'data-boundary-state="failed"', 1
                ),
                encoding="utf-8",
                newline="\n",
            )

            errors = design_system_errors(root)

        self.assertTrue(any("governed tokens" in error for error in errors), errors)
        self.assertTrue(any("inline styles" in error for error in errors), errors)
        self.assertTrue(any("governed reference source" in error for error in errors), errors)
        self.assertTrue(any("every governed boundary state" in error for error in errors), errors)

    def test_product_styling_uses_shared_semantic_flow_primitives_and_canonical_geometry(self) -> None:
        token_styles = (REPO / "design" / "ui-reference" / "assets" / "tokens.css").read_text(encoding="utf-8")
        shared_styles = (REPO / "packages" / "ui-components" / "src" / "styles.css").read_text(encoding="utf-8")
        product_styles = (REPO / "apps" / "desktop" / "src" / "app.css").read_text(encoding="utf-8")
        app_sources = {
            path.name: path.read_text(encoding="utf-8")
            for path in (REPO / "apps" / "desktop" / "src" / "app").glob("*.tsx")
        }
        combined_sources = "\n".join(app_sources.values())

        semantic_primitives = {
            "ro-page-region",
            "ro-stack",
            "ro-cluster",
            "ro-grid",
            "ro-card",
            "ro-form",
            "ro-notice",
            "ro-table-region",
            "ro-dialog-surface",
            "ro-action-row",
        }
        for primitive in semantic_primitives:
            with self.subTest(primitive=primitive):
                self.assertRegex(shared_styles, rf"\.{re.escape(primitive)}(?![a-zA-Z0-9_-])")
                self.assertIn(primitive, combined_sources)

        for workspace in (
            "ApplicationSettingsWorkspace.tsx",
            "AuditLineageWorkspace.tsx",
            "DiagnosticsWorkspace.tsx",
            "IntentWorkspace.tsx",
            "ProjectHomeWorkspace.tsx",
            "ProjectSettingsWorkspace.tsx",
            "ProjectsWorkspace.tsx",
            "TaskCenterWorkspace.tsx",
        ):
            with self.subTest(workspace=workspace):
                self.assertIn("ro-page-region", app_sources[workspace])

        self.assertIn("padding: var(--content-padding)", product_styles)
        combined_styles = "\n".join((token_styles, shared_styles, product_styles))
        defined_properties = set(re.findall(r"(--[a-z0-9-]+)\s*:", combined_styles))
        referenced_properties = set(re.findall(r"var\((--[a-z0-9-]+)", combined_styles))
        self.assertEqual(set(), referenced_properties - defined_properties)
        self.assertNotIn("min-height: 2.75rem", product_styles)
        self.assertIsNone(re.search(r"\bstyle\s*=", combined_sources))

        shared_rules = tuple(
            (match.group("selectors"), match.group("body"))
            for match in re.finditer(
                r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}",
                re.sub(r"/\*.*?\*/", "", shared_styles, flags=re.DOTALL),
            )
        )
        primitive_contracts = {
            "ro-page-region": ("display: grid", "gap: var(--space-6)"),
            "ro-grid": ("display: grid", "gap: var(--grid-gap)"),
            "ro-card": (
                "padding: var(--ro-card-padding, var(--card-padding))",
                "border-radius: var(--radius-md)",
            ),
            "ro-form": ("display: grid", "gap: var(--space-5)"),
            "ro-table-region": ("max-width: 100%", "overflow: auto"),
            "ro-dialog-surface": ("max-height: calc(100vh - var(--space-10))", "overflow: auto"),
            "ro-action-row": ("display: flex", "flex-wrap: wrap"),
        }
        for primitive, declarations in primitive_contracts.items():
            with self.subTest(primitive_contract=primitive):
                applicable_bodies = "\n".join(
                    body
                    for selectors, body in shared_rules
                    if re.search(rf"\.{re.escape(primitive)}(?![a-zA-Z0-9_-])", selectors)
                )
                self.assertTrue(applicable_bodies)
                for expected in declarations:
                    self.assertIn(expected, applicable_bodies)
        form_control_bodies = "\n".join(body for selectors, body in shared_rules if ".ro-form :where(" in selectors)
        self.assertIn("min-height: var(--control-height-md)", form_control_bodies)

    def test_catalog_structure_and_accessible_name_cannot_be_satisfied_by_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REPO / "packages" / "ui-tokens", root / "packages" / "ui-tokens")
            shutil.copytree(REPO / "packages" / "ui-components", root / "packages" / "ui-components")
            token_source = root / "design" / "ui-reference" / "assets" / "tokens.css"
            token_source.parent.mkdir(parents=True)
            shutil.copy2(REPO / "design" / "ui-reference" / "assets" / "tokens.css", token_source)
            shutil.copy2(REPO / "pnpm-lock.yaml", root / "pnpm-lock.yaml")
            catalog_path = root / "packages" / "ui-components" / "catalog.html"
            catalog = catalog_path.read_text(encoding="utf-8")
            catalog = re.sub(r'<article class="ro-panel".*?</article>', "", catalog)
            catalog = catalog.replace('id="catalog-dialog-title"', "")
            catalog = catalog.replace("</main>", "<!-- ro-panel --></main>")
            catalog_path.write_text(catalog, encoding="utf-8")

            static_errors = design_system_errors(root)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                browser_errors, _ = component_catalog_browser_errors(root, context)
                context.close()
                browser.close()

        self.assertTrue(any("no structural ro-panel" in error for error in static_errors), static_errors)
        self.assertTrue(any("dangling or empty" in error for error in static_errors), static_errors)
        self.assertTrue(any("structural inventory" in error for error in browser_errors), browser_errors)
        self.assertTrue(any("semantics are incomplete" in error for error in browser_errors), browser_errors)


class ProjectRecoveryInteractionTests(unittest.TestCase):
    def test_readiness_catalog_retry_and_late_mutation_are_separate(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        document = inline_product_index(REPO)
        fixture = r"""(() => {
          const fixture = window.__PROJECT_RECOVERY__ = {
            state: 'starting', starts: 0, statuses: 0, reads: 0,
            catalog: 'failed', mutation: 'failed', mutations: [], resolveMutation: null
          };
          const catalog = __WORKFLOW_CATALOG__;
          const response = body => ({status: 200, contentType: 'application/json',
            traceId: '0123456789abcdef0123456789abcdef', etag: null, body: JSON.stringify(body)});
          const status = () => ({state: fixture.state, attempt: 1,
            retryAvailable: fixture.state === 'stopped',
            diagnosticReference: fixture.state === 'ready' ? null
              : fixture.state === 'starting' ? 'RO-CORE-STARTING' : 'RO-CORE-STOPPED'});
          window.__TAURI_INTERNALS__ = {
            transformCallback: () => 1,
            invoke: async (command, args) => {
              if (command === 'application_lock_status') return {
                schemaVersion: '1.0', state: 'unlocked', signInMode: 'none', policyRevision: 1,
                profileName: null, inactivityTimeoutMinutes: 0, configurationState: 'valid', reason: null,
                threatDisclosure: 'Application-session protection only; this is not Windows-account isolation.',
                retryAfterSeconds: 0, auditSequence: 0
              };
              if (command === 'application_lock_activity' || command === 'plugin:event|unlisten') return;
              if (command === 'plugin:event|listen') return 1;
              if (command === 'core_runtime_status') { fixture.statuses++; return status(); }
              if (command === 'core_runtime_start') {
                fixture.starts++;
                if (fixture.state === 'stopped') fixture.state = 'ready';
                return status();
              }
              if (command !== 'core_api_request') throw new Error('Unexpected fixture command');
              const request = args.request;
              if (request.path === '/workflow-profiles/catalog') {
                fixture.reads++;
                if (fixture.state !== 'ready' || fixture.catalog === 'failed') {
                  throw new Error('Bearer fixture-not-a-real-secret C:/private/fixture');
                }
                return response(catalog);
              }
              fixture.mutations.push(request);
              if (fixture.mutation === 'failed') throw new Error('Bearer fixture-not-a-real-secret C:/private/fixture');
              return await new Promise(resolve => { fixture.resolveMutation = () => resolve(response({
                schemaVersion: '1.0', projectId: '11111111-1111-4111-8111-111111111111',
                displayName: 'Late project fixture', templateId: 'theory-synthesis', lifecycleState: 'active',
                root: 'C:/Research/study-one', open: false, accessMode: 'closed', compatibilityState: 'compatible',
                packageFormatVersion: '1.0.0', backupRequiredBeforeRepair: false, recoveryAction: 'none', revision: 0,
                deleteConfirmation: 'delete:11111111-1111-4111-8111-111111111111'
              })); });
            }
          };
        })();""".replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html; charset=utf-8", body=document
            ) if route.request.url == "http://tauri.localhost/index.html" else route.abort())
            page = context.new_page()
            page.add_init_script(fixture)
            page_errors: list[str] = []
            page.on("pageerror", page_error_collector(page_errors))

            def open_tool(name: str) -> None:
                tools = page.locator("[data-all-tools]")
                if tools.get_attribute("open") is None:
                    tools.locator("summary").click()
                tools.get_by_role("button", name=name, exact=True).click()

            try:
                page.goto("http://tauri.localhost/index.html", wait_until="load")
                page.wait_for_function("document.body.dataset.applicationReady === 'true'")
                starts = page.evaluate("window.__PROJECT_RECOVERY__.starts")
                open_tool("Local projects")
                page.wait_for_function("window.__PROJECT_RECOVERY__.statuses > 0", timeout=5000)
                self.assertEqual(starts, page.evaluate("window.__PROJECT_RECOVERY__.starts"))
                self.assertEqual(0, page.evaluate("window.__PROJECT_RECOVERY__.reads"))
                page.locator("#project-parent-directory").fill("C:/Research")
                page.locator("#project-directory-name").fill("study-one")
                page.locator("#project-display-name").fill("Recovery study")
                page.locator("#project-research-objective").fill("Line one\nLine two\twith context")
                page.evaluate("window.__PROJECT_RECOVERY__.state = 'ready'")
                page.get_by_text("Could not load use cases", exact=True).wait_for(timeout=5000)
                self.assertNotIn("RO-CORE-PROJECT-ACTION-FAILED", page.locator("main").inner_text())
                self.assertNotIn("fixture-not-a-real-secret", page.locator("body").inner_text())
                self.assertEqual([], page.evaluate("window.__PROJECT_RECOVERY__.mutations"))
                page.evaluate("window.__PROJECT_RECOVERY__.catalog = 'ready'")
                page.get_by_role("button", name="Retry loading use cases", exact=True).click()
                page.locator("#project-primary-use-case").select_option("theory-synthesis")
                self.assertEqual("Recovery study", page.locator("#project-display-name").input_value())
                page.locator("#project-parent-directory").fill("relative-folder")
                page.get_by_role("button", name="Create project", exact=True).click()
                page.get_by_text("Review project details", exact=True).wait_for(timeout=5000)
                self.assertIn("No project request was sent.", page.locator("main").inner_text())
                self.assertEqual([], page.evaluate("window.__PROJECT_RECOVERY__.mutations"))
                self.assertEqual("Recovery study", page.locator("#project-display-name").input_value())
                page.locator("#project-parent-directory").fill("C:/Research")
                page.get_by_role("button", name="Create project", exact=True).click()
                page.get_by_text("RO-CORE-PROJECT-ACTION-FAILED", exact=True).wait_for(timeout=5000)
                self.assertEqual(1, page.evaluate("window.__PROJECT_RECOVERY__.mutations.length"))
                page.evaluate("window.__PROJECT_RECOVERY__.state = 'stopped'")
                service = page.locator("[data-local-service-boundary]")
                service.get_by_role("button", name="Retry", exact=True).wait_for(timeout=5000)
                service.get_by_role("button", name="Retry", exact=True).click()
                page.wait_for_function("window.__PROJECT_RECOVERY__.reads === 3", timeout=5000)
                self.assertEqual(1, page.evaluate("window.__PROJECT_RECOVERY__.mutations.length"))
                self.assertEqual(
                    "Line one\nLine two\twith context", page.locator("#project-research-objective").input_value()
                )
                page.evaluate("window.__PROJECT_RECOVERY__.mutation = 'pending'")
                page.get_by_role("button", name="Create project", exact=True).click()
                page.wait_for_function("window.__PROJECT_RECOVERY__.resolveMutation !== null")
                self.assertTrue(page.get_by_role("button", name="Create project", exact=True).is_disabled())
                open_tool("Diagnostics & support")
                page.evaluate("window.__PROJECT_RECOVERY__.resolveMutation()")
                open_tool("Local projects")
                self.assertNotIn("Late project fixture", page.locator("body").inner_text())
                self.assertEqual(2, page.evaluate("window.__PROJECT_RECOVERY__.mutations.length"))
                self.assertEqual([], page_errors)
            finally:
                page.close()
                context.close()
                browser.close()


class TaskCenterInteractionTests(unittest.TestCase):
    def test_commands_focus_failure_and_project_switch_are_bound_to_current_projection(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        document = inline_product_index(REPO)
        fixture = (
            (REPO / "tests" / "desktop" / "fixtures" / "task_center_interactions.js")
            .read_text(encoding="utf-8")
            .replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO))
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()

            def serve_application(route: Any) -> None:
                if route.request.url in {"http://tauri.localhost/", "http://tauri.localhost/index.html"}:
                    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)
                else:
                    route.abort()

            context.route("**/*", serve_application)
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", page_error_collector(page_errors))
            page.add_init_script(fixture)

            def open_desktop_tool(name: str) -> None:
                disclosure = page.locator("[data-all-tools]")
                if disclosure.get_attribute("open") is None:
                    disclosure.locator("summary").click()
                disclosure.get_by_role("button", name=name, exact=True).click()

            try:
                page.goto("http://tauri.localhost/index.html", wait_until="load")
                page.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
                open_desktop_tool("Local projects")
                page.locator("#project-parent-directory").fill("C:/Research")
                page.locator("#project-directory-name").fill("study-one")
                page.locator("#project-display-name").fill("Study One")
                page.locator("#project-research-objective").fill("Explain a bounded workflow.")
                page.locator("#project-primary-use-case").select_option("theory-synthesis")
                page.get_by_role("button", name="Create project", exact=True).click()
                page.get_by_label("Current project actions").get_by_role(
                    "button", name="Open project", exact=True
                ).click()
                page.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5_000)
                open_desktop_tool("Task Center")
                page.get_by_role("heading", name="project-a-extract", exact=True).wait_for(timeout=5_000)

                cancel = page.get_by_role("button", name="Cancel safely", exact=True)
                cancel.click()
                dialog = page.get_by_role("alertdialog")
                dialog.wait_for(state="visible", timeout=5_000)
                self.assertEqual("Keep current state", page.locator(":focus").inner_text())
                page.keyboard.press("Shift+Tab")
                self.assertEqual("Confirm", page.locator(":focus").inner_text())
                page.keyboard.press("Tab")
                self.assertEqual("Keep current state", page.locator(":focus").inner_text())
                page.keyboard.press("Escape")
                dialog.wait_for(state="detached", timeout=5_000)
                page.wait_for_function("document.activeElement?.textContent?.trim() === 'Cancel safely'", timeout=5_000)

                page.evaluate("window.__FAIL_NEXT_CANCEL__()")
                cancel.click()
                page.get_by_role("button", name="Confirm", exact=True).click()
                page.get_by_text("Task Center unavailable", exact=True).wait_for(timeout=5_000)
                page.wait_for_function(
                    "document.querySelector('[data-live-region]')?.textContent?.includes('Task Center command failed')",
                    timeout=5_000,
                )
                self.assertEqual(1, dialog.count())
                page.get_by_role("button", name="Keep current state", exact=True).click()
                page.wait_for_function("document.activeElement?.textContent?.trim() === 'Cancel safely'", timeout=5_000)

                cancel.click()
                page.get_by_role("button", name="Confirm", exact=True).click()
                dialog.wait_for(state="detached", timeout=5_000)
                page.get_by_text("cancelling", exact=True).wait_for(timeout=5_000)
                page.wait_for_function(
                    "document.activeElement?.getAttribute('aria-pressed') === 'true'",
                    timeout=5_000,
                )

                page.evaluate("window.__DELAY_NEXT_A__()")
                page.get_by_role("button", name="Refresh", exact=True).click()
                open_desktop_tool("Local projects")
                page.locator("#project-root").fill("C:/Research/study-two")
                page.locator("form").filter(has=page.locator("#project-root")).get_by_role(
                    "button", name="Open project", exact=True
                ).click()
                page.get_by_text("Study Two", exact=True).wait_for(timeout=5_000)
                open_desktop_tool("Task Center")
                page.get_by_role("heading", name="project-b-review", exact=True).wait_for(timeout=5_000)
                page.evaluate("window.__RESOLVE_A__()")
                page.wait_for_timeout(100)
                self.assertEqual(0, page.get_by_text("project-a-extract", exact=True).count())
                self.assertIn("Continuation of run", page.locator("[data-workflow-continuation]").inner_text())

                page.get_by_role("button", name="approved — resume workflow", exact=True).click()
                page.get_by_text("succeeded", exact=True).wait_for(timeout=5_000)
                self.assertEqual(0, page.get_by_role("heading", name="Decision required", exact=True).count())
                self.assertEqual([], page_errors)
            finally:
                page.close()
                context.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
