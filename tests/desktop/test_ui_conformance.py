from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "design" / "ui-reference"
sys.path.insert(0, str(REPO / "tools"))

from ui_conformance import (  # noqa: E402
    Context,
    baseline_history_errors,
    check_accessibility,
    check_routes,
    check_tokens,
    check_visual,
    check_workflows,
    load_context,
)


class UiConformanceTests(unittest.TestCase):
    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")

    def context_copy(self, temporary: str) -> Context:
        root = Path(temporary) / "repo"
        reference = root / "design" / "ui-reference"
        target = root / "target"
        shutil.copytree(REFERENCE, reference, ignore=shutil.ignore_patterns("previews", "__pycache__"))
        shutil.copytree(REFERENCE, target, ignore=shutil.ignore_patterns("previews", "__pycache__"))
        config = json.loads((REPO / "verification" / "extensions" / "desktop-ui.json").read_text(encoding="utf-8"))
        site = json.loads((reference / "SITE_MANIFEST.json").read_text(encoding="utf-8"))
        workflow_document = json.loads((reference / "WORKFLOW_CATALOG.json").read_text(encoding="utf-8"))
        pages = [str(item["file"]) for item in site["pages"]]
        return Context(root, config, reference, target, site, workflow_document["workflows"], pages)

    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    def test_canonical_token_and_route_contracts_pass_with_normative_mapping(self) -> None:
        context = load_context(REPO)

        token_result = check_tokens(context)
        route_result = check_routes(context)

        self.assertTrue(token_result["ok"], token_result["errors"])
        self.assertTrue(route_result["ok"], route_result["errors"])
        self.assertEqual(109, token_result["details"]["tokens"])
        self.assertEqual(32, route_result["details"]["routes"])
        self.assertEqual("design/ui-reference/assets/tokens.css", token_result["normativeSources"]["tokens"])
        self.assertIn("mock names", route_result["illustrativeExclusions"])

    def test_fixture_mode_refuses_to_mask_an_application_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REFERENCE, root / "design" / "ui-reference")
            (root / "verification" / "extensions").mkdir(parents=True)
            shutil.copy2(
                REPO / "verification" / "extensions" / "desktop-ui.json",
                root / "verification" / "extensions" / "desktop-ui.json",
            )
            shutil.copy2(
                REPO / "verification" / "desktop-ui.schema.json",
                root / "verification" / "desktop-ui.schema.json",
            )
            implementation = root / "apps" / "desktop" / "src" / "View.tsx"
            implementation.parent.mkdir(parents=True)
            implementation.write_text("export const View = () => null;\n", encoding="utf-8", newline="\n")

            with self.assertRaisesRegex(ValueError, "cannot remain active"):
                load_context(root)

    def test_token_and_supporting_navigation_drift_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            tokens = context.target / "assets" / "tokens.css"
            tokens.write_text(
                tokens.read_text(encoding="utf-8").replace("--brand-600: #2563eb", "--brand-600: #000000"),
                encoding="utf-8",
                newline="\n",
            )
            index = context.target / "index.html"
            index.write_text(
                index.read_text(encoding="utf-8").replace("data-all-tools", "data-all-tools-removed", 1),
                encoding="utf-8",
                newline="\n",
            )

            token_result = check_tokens(context)
            route_result = check_routes(context)

        self.assertFalse(token_result["ok"])
        self.assertTrue(any("semantic token drift" in error for error in token_result["errors"]))
        self.assertFalse(route_result["ok"])
        self.assertTrue(any("supporting-tool navigation differs" in error for error in route_result["errors"]))

    def test_workflow_order_drift_fails_against_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            rapid = context.workflows["rapid-orientation"]
            mutated = Context(
                context.repo,
                context.config,
                context.reference,
                context.target,
                context.site,
                {"rapid-orientation": {"steps": list(reversed(rapid["steps"]))}},
                context.pages,
            )

            result = check_workflows(mutated)

        self.assertFalse(result["ok"])
        self.assertTrue(any("ordered primary navigation differs" in error for error in result["errors"]))

    def test_accessibility_and_responsive_contract_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            index = context.target / "index.html"
            index.write_text(
                index.read_text(encoding="utf-8").replace('<html lang="en"', '<html lang="fr"', 1),
                encoding="utf-8",
                newline="\n",
            )
            reduced = Context(
                context.repo,
                context.config,
                context.reference,
                context.target,
                context.site,
                context.workflows,
                ["index.html"],
            )

            result = check_accessibility(reduced)

        self.assertFalse(result["ok"])
        self.assertTrue(any("document language must be en" in error for error in result["errors"]))

    def test_same_reference_baseline_rewrite_requires_new_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Baseline Test")
            self.git(root, "config", "user.email", "ui-baseline@example.invalid")
            approval = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval.parent.mkdir(parents=True)
            approval.write_text("status: approved\n", encoding="utf-8", newline="\n")
            baseline_path = root / "verification" / "baselines" / "desktop-ui.json"
            self.write_json(baseline_path, {"referenceId": "REF-1", "entries": {"page::light": "one"}})
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve initial baseline")
            approval_commit = self.git(root, "rev-parse", "HEAD")
            current = {
                "referenceId": "REF-1",
                "referenceApprovalCommit": approval_commit,
                "entries": {"page::light": "two"},
            }
            self.write_json(baseline_path, current)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "rewrite same reference baseline")
            (root / "unrelated.txt").write_text("later commit\n", encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "attempt to launder baseline rewrite")
            config = {
                "visual": {"baselinePath": "verification/baselines/desktop-ui.json"},
                "normativeSources": {"style": "design/ui-reference/STYLE_GUIDE.md"},
            }
            context = Context(root, config, root, root, {}, {}, [])

            errors = baseline_history_errors(context, current)

        self.assertTrue(any("requires a new approved reference ID" in error for error in errors), errors)

    def test_visual_mismatch_maps_to_normative_page_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            baseline_path = context.repo / "verification" / "baselines" / "desktop-ui.json"
            baseline = {
                "referenceId": context.config["referenceId"],
                "referencePackageSha256": context.config["referencePackageSha256"],
                "platform": context.config["visual"]["platform"],
                "playwrightVersion": context.config["visual"]["playwrightVersion"],
                "browserVersion": context.config["visual"]["browserVersion"],
                "settings": context.config["visual"],
                "entries": {"index.html::light": {"sha256": "old"}},
            }
            self.write_json(baseline_path, baseline)
            observed = {"index.html::light": {"sha256": "new"}}
            with (
                mock.patch("ui_conformance.baseline_history_errors", return_value=[]),
                mock.patch("ui_conformance.render_visuals", return_value=(observed, [])),
            ):
                result = check_visual(context)

        self.assertFalse(result["ok"])
        self.assertTrue(any("CAPABILITY_COVERAGE.json#index.html" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
