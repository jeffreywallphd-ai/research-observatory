from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from product_style_check import (  # noqa: E402
    analyze_product_style_sources,
    load_product_style_sources,
    product_style_analysis,
)

TOKEN_SOURCE = """:root {
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --surface-1: #ffffff;
}
"""


def exception_record(entries: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "documentType": "product-style-analysis-exceptions",
        "authority": "ECR-0007/W1.A08.T01",
        "reviewBoundary": "independent-commit-bound-task-review",
        "exceptions": entries or [],
    }


def exception_entry(
    signature: str,
    *,
    identifier: str = "W1-A08-T01-C01",
    kind: str = "raw-geometry",
) -> dict[str, str]:
    return {
        "id": identifier,
        "kind": kind,
        "signature": signature,
        "scope": "composition",
        "rationale": (
            "This exact composition-specific residual is intentionally bounded and cannot be "
            "expressed as reusable semantic component geometry."
        ),
    }


def analyze(
    css_sources: dict[str, str] | None = None,
    renderer_sources: dict[str, str] | None = None,
    exceptions: Any | None = None,
) -> dict[str, Any]:
    return analyze_product_style_sources(
        TOKEN_SOURCE,
        css_sources or {},
        renderer_sources or {},
        exception_record() if exceptions is None else exceptions,
    )


def write_minimal_repository(root: Path, *, include_exception: bool = True) -> None:
    files = {
        "design/ui-reference/assets/tokens.css": TOKEN_SOURCE,
        "packages/ui-components/src/styles.css": ".ro-card { padding: var(--space-2); }\n",
        "apps/desktop/src/app.css": ".application-shell { display: grid; }\n",
        "apps/desktop/src/main.tsx": "export const application = true;\n",
    }
    for relative, contents in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    if include_exception:
        target = root / "verification/product-style-exceptions.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(exception_record()), encoding="utf-8")


class ProductStyleCheckTests(unittest.TestCase):
    def test_real_repository_satisfies_product_style_contract(self) -> None:
        result = product_style_analysis(REPO)

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["details"]["cssRuleCount"], 0)
        self.assertGreater(result["details"]["rendererFileCount"], 0)
        self.assertEqual(result["details"]["physicalDirectionalDeclarations"], [])
        self.assertLessEqual(
            result["details"]["selectorSpecificity"]["maximum"],
            result["details"]["selectorSpecificity"]["limits"],
        )
        self.assertTrue(
            {
                "apps/desktop/src/app.css",
                "packages/ui-components/src/styles.css",
            }.issubset(result["details"]["stylePaths"])
        )

    def test_normalized_material_duplicates_fail_within_one_file(self) -> None:
        result = analyze(
            {
                "apps/desktop/src/app.css": """
                    .first { display: grid; gap: var(--space-1); padding: var(--space-2); }
                    .second {
                      padding: var(--space-2);
                      display:   grid;
                      gap: var(--space-1);
                    }
                """
            }
        )

        self.assertFalse(result["ok"])
        duplicate_errors = [error for error in result["errors"] if "[duplicate-declaration-group]" in error]
        self.assertEqual(len(duplicate_errors), 1, result["errors"])
        self.assertIn(".first", duplicate_errors[0])
        self.assertIn(".second", duplicate_errors[0])

    def test_normalized_material_duplicates_fail_when_copied_across_files(self) -> None:
        result = analyze(
            {
                "apps/desktop/src/app.css": (".first { display: grid; gap: var(--space-1); padding: var(--space-2); }"),
                "packages/ui-components/src/styles.css": (
                    ".second { padding: var(--space-2); gap: var(--space-1); display: grid; }"
                ),
            }
        )

        self.assertFalse(result["ok"])
        duplicate_errors = [error for error in result["errors"] if "[duplicate-declaration-group]" in error]
        self.assertEqual(len(duplicate_errors), 1, result["errors"])
        self.assertIn("apps/desktop/src/app.css::.first", duplicate_errors[0])
        self.assertIn("packages/ui-components/src/styles.css::.second", duplicate_errors[0])

    def test_id_and_over_class_budget_selectors_fail(self) -> None:
        cases = {
            "id": "#forbidden { color: var(--surface-1); }",
            "class-budget": ".one.two.three { color: var(--surface-1); }",
        }
        for label, source in cases.items():
            with self.subTest(label=label):
                result = analyze({"apps/desktop/src/app.css": source})
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any("[selector-specificity]" in error for error in result["errors"]),
                    result["errors"],
                )

    def test_raw_geometry_recognizes_alternate_css_length_units(self) -> None:
        result = analyze({"apps/desktop/src/app.css": ".ro-card { padding: 1em; }"})

        self.assertFalse(result["ok"])
        self.assertTrue(
            any("[raw-geometry]" in error and "padding: 1em" in error for error in result["errors"]),
            result["errors"],
        )

    def test_raw_geometry_covers_logical_dimension_properties(self) -> None:
        result = analyze({"apps/desktop/src/app.css": (".ro-card { min-inline-size: 31px; block-size: 13em; }")})

        self.assertFalse(result["ok"])
        raw_errors = [error for error in result["errors"] if "[raw-geometry]" in error]
        self.assertEqual(len(raw_errors), 2, result["errors"])
        self.assertTrue(any("min-inline-size: 31px" in error for error in raw_errors))
        self.assertTrue(any("block-size: 13em" in error for error in raw_errors))

    def test_exception_record_is_exact_and_fail_closed(self) -> None:
        raw_source = {"apps/desktop/src/app.css": ".ro-card { padding: 1em; }"}

        with self.subTest(case="missing-exception"):
            result = analyze(raw_source, exceptions=exception_record())
            self.assertFalse(result["ok"])
            self.assertTrue(any("[raw-geometry]" in error for error in result["errors"]), result["errors"])

        with self.subTest(case="invalid-record"):
            invalid = exception_record(
                [
                    {
                        **exception_entry("raw-geometry|apps/desktop/src/app.css"),
                        "id": "wildcard",
                        "rationale": "too short",
                    }
                ]
            )
            result = analyze({}, exceptions=invalid)
            self.assertFalse(result["ok"])
            self.assertTrue(any("[exception-record]" in error for error in result["errors"]), result["errors"])

        with self.subTest(case="stale-exception"):
            stale = exception_record(
                [exception_entry("raw-geometry|apps/desktop/src/app.css|global|.gone|padding|1em")]
            )
            result = analyze({}, exceptions=stale)
            self.assertFalse(result["ok"])
            self.assertTrue(any("stale" in error for error in result["errors"]), result["errors"])

        with self.subTest(case="overbroad-exception"):
            overbroad = exception_record([exception_entry("raw-geometry|*")])
            result = analyze(raw_source, exceptions=overbroad)
            self.assertFalse(result["ok"])
            self.assertTrue(any("[raw-geometry]" in error for error in result["errors"]), result["errors"])
            self.assertTrue(any("wildcard" in error for error in result["errors"]), result["errors"])

    def test_missing_exception_file_fails_repository_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_minimal_repository(root, include_exception=False)

            result = product_style_analysis(root)

        self.assertFalse(result["ok"])
        self.assertTrue(any("[source-read]" in error for error in result["errors"]), result["errors"])

    def test_physical_direction_declarations_fail(self) -> None:
        result = analyze({"apps/desktop/src/app.css": (".panel { margin-left: var(--space-1); text-align: right; }")})

        self.assertFalse(result["ok"])
        physical_errors = [error for error in result["errors"] if "[physical-direction]" in error]
        self.assertEqual(len(physical_errors), 2, result["errors"])
        self.assertTrue(any("margin-left" in error for error in physical_errors))
        self.assertTrue(any("text-align" in error for error in physical_errors))

    def test_renderer_inline_style_and_css_in_js_fail(self) -> None:
        result = analyze(
            renderer_sources={
                "apps/desktop/src/Inline.tsx": (
                    "export function Inline() { return <div style={{ display: 'grid' }} />; }"
                ),
                "apps/desktop/src/Styled.tsx": (
                    "const StyledPanel = styled.div; export const panel = <StyledPanel />;"
                ),
            }
        )

        self.assertFalse(result["ok"])
        escape_errors = [error for error in result["errors"] if "[renderer-style-escape]" in error]
        self.assertEqual(len(escape_errors), 2, result["errors"])
        self.assertTrue(any("inline style attribute" in error for error in escape_errors))
        self.assertTrue(any("CSS-in-JS styled factory" in error for error in escape_errors))

    def test_undefined_and_duplicate_in_block_custom_properties_fail(self) -> None:
        result = analyze(
            {
                "apps/desktop/src/app.css": """
                    .panel {
                      --ro-local-gap: var(--space-1);
                      --ro-local-gap: var(--space-2);
                      color: var(--not-defined);
                    }
                """
            }
        )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any("[undefined-custom-property]" in error and "--not-defined" in error for error in result["errors"]),
            result["errors"],
        )
        self.assertTrue(
            any("[duplicate-custom-property]" in error and "--ro-local-gap" in error for error in result["errors"]),
            result["errors"],
        )

    def test_product_css_cannot_create_a_second_semantic_token_source(self) -> None:
        cases = {
            "canonical-redefinition": (
                ":root { --space-1: 99px; }",
                "[canonical-token-redefinition]",
            ),
            "unapproved-token-namespace": (
                ":root { --product-space: 1rem; }",
                "[second-token-source]",
            ),
        }
        for label, (source, expected) in cases.items():
            with self.subTest(label=label):
                result = analyze({"apps/desktop/src/app.css": source})
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any(expected in error for error in result["errors"]),
                    result["errors"],
                )

    def test_repository_loading_discovers_added_production_css(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_minimal_repository(root)
            added = root / "apps/desktop/src/features/new-surface.css"
            added.parent.mkdir(parents=True, exist_ok=True)
            added.write_text(".ro-card { padding: 1em; }\n", encoding="utf-8")

            _, css_sources, renderer_sources, _ = load_product_style_sources(root)
            result = product_style_analysis(root)

        self.assertIn("apps/desktop/src/features/new-surface.css", css_sources)
        self.assertEqual(css_sources["apps/desktop/src/features/new-surface.css"], ".ro-card { padding: 1em; }\n")
        self.assertIn("apps/desktop/src/main.tsx", renderer_sources)
        self.assertFalse(result["ok"])
        self.assertTrue(any("[raw-geometry]" in error for error in result["errors"]), result["errors"])


if __name__ == "__main__":
    unittest.main()
