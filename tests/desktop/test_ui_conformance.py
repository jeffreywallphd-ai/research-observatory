from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "design" / "ui-reference"
sys.path.insert(0, str(REPO / "tools"))

from ui_conformance import (  # noqa: E402
    Context,
    approval_lineage_errors,
    approval_record_errors,
    baseline_document_errors,
    baseline_history_errors,
    check_accessibility,
    check_routes,
    check_tokens,
    check_visual,
    check_workflows,
    font_face_available,
    load_context,
    new_page,
    open_browser,
    provenance_only_reference_ratification,
    set_page,
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
        schema_path = root / "verification" / "desktop-ui-baseline.schema.json"
        schema_path.parent.mkdir(parents=True)
        shutil.copy2(REPO / "verification" / "desktop-ui-baseline.schema.json", schema_path)
        config = json.loads((REPO / "verification" / "extensions" / "desktop-ui.json").read_text(encoding="utf-8"))
        site = json.loads((reference / "SITE_MANIFEST.json").read_text(encoding="utf-8"))
        workflow_document = json.loads((reference / "WORKFLOW_CATALOG.json").read_text(encoding="utf-8"))
        coverage = json.loads((reference / "CAPABILITY_COVERAGE.json").read_text(encoding="utf-8"))
        pages = [str(item["file"]) for item in site["pages"]]
        return Context(
            root,
            config,
            reference,
            target,
            site,
            workflow_document["workflows"],
            coverage["page_contracts"],
            pages,
        )

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
            implementation = root / "apps" / "desktop" / "src" / "Application.test.tsx"
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

    def test_every_exact_page_region_contract_is_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            index = context.target / "index.html"
            index.write_text(
                index.read_text(encoding="utf-8").replace('<footer class="trust-footer">', "<footer>"),
                encoding="utf-8",
                newline="\n",
            )

            result = check_routes(context)

        self.assertFalse(result["ok"])
        self.assertEqual(
            sum(len(contract["required_regions"]) for contract in context.page_contracts.values()),
            result["details"]["requiredRegionContracts"],
        )
        self.assertTrue(any("trust/provenance footer" in error for error in result["errors"]))

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
                context.page_contracts,
                context.pages,
            )

            result = check_workflows(mutated)

        self.assertFalse(result["ok"])
        self.assertTrue(any("ordered primary navigation differs" in error for error in result["errors"]))

    def test_workflow_links_must_be_tab_reachable_and_keyboard_activatable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            app = context.target / "assets" / "app.js"
            app.write_text(
                app.read_text(encoding="utf-8").replace("<a class=", '<a tabindex="-1" class='),
                encoding="utf-8",
                newline="\n",
            )
            rapid = context.workflows["rapid-orientation"]
            reduced = Context(
                context.repo,
                context.config,
                context.reference,
                context.target,
                context.site,
                {"rapid-orientation": rapid},
                context.page_contracts,
                context.pages,
            )

            result = check_workflows(reduced)

        self.assertFalse(result["ok"])
        self.assertTrue(any("keyboard focus order differs" in error for error in result["errors"]))

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
                context.page_contracts,
                ["index.html"],
            )

            result = check_accessibility(reduced)

        self.assertFalse(result["ok"])
        self.assertTrue(any("document language must be en" in error for error in result["errors"]))

    def test_controlled_font_check_rejects_a_missing_face(self) -> None:
        context = load_context(REPO)
        playwright, browser = open_browser(context)
        try:
            page = new_page(browser, context)
            try:
                set_page(page, context, "index.html")
                self.assertTrue(font_face_available(page, "Segoe UI"))
                self.assertFalse(font_face_available(page, "DefinitelyMissingFont-9B6F"))
            finally:
                page.context.close()
        finally:
            browser.close()
            playwright.stop()

    def test_strict_baseline_and_approval_records_reject_malformed_history_shapes(self) -> None:
        schema = json.loads((REPO / "verification" / "desktop-ui-baseline.schema.json").read_text(encoding="utf-8"))
        malformed = json.loads((REPO / "verification" / "baselines" / "desktop-ui.json").read_text())
        malformed["settings"] = "not-an-object"
        malformed["platform"] = "junk-platform"
        malformed["entries"]["index.html::light"]["width"] = -1440
        malformed["entries"]["index.html::light"]["height"] = 0

        baseline_errors = baseline_document_errors(malformed, "historical", schema)
        approval_errors = approval_record_errors(
            {"reference_id": malformed["referenceId"], "status": "approved"},
            "historical-approval",
            malformed["referenceId"],
        )

        self.assertTrue(baseline_errors)
        self.assertTrue(any("settings" in error for error in baseline_errors))
        self.assertTrue(any("approval fields must be exact" in error for error in approval_errors))

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
            schema_path = root / "verification" / "desktop-ui-baseline.schema.json"
            schema_path.parent.mkdir(parents=True)
            shutil.copy2(REPO / "verification" / "desktop-ui-baseline.schema.json", schema_path)
            baseline_path = root / "verification" / "baselines" / "desktop-ui.json"
            settings = json.loads(
                (REPO / "verification" / "extensions" / "desktop-ui.json").read_text(encoding="utf-8")
            )["visual"]
            initial = {
                "schemaVersion": "1.0",
                "documentType": "desktop-ui-visual-baseline",
                "referenceId": "REF-1",
                "referencePackageSha256": "1" * 64,
                "referenceApprovalCommit": "0" * 40,
                "platform": settings["platform"],
                "playwrightVersion": settings["playwrightVersion"],
                "browserVersion": settings["browserVersion"],
                "settings": settings,
                "entries": {
                    f"page.html::{theme}": {
                        "page": "page.html",
                        "theme": theme,
                        "width": settings["viewport"]["width"],
                        "height": settings["viewport"]["height"],
                        "sha256": "1" * 64,
                    }
                    for theme in ("light", "dark")
                },
            }
            self.write_json(baseline_path, initial)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve initial baseline")
            approval_commit = self.git(root, "rev-parse", "HEAD")
            current = json.loads(json.dumps(initial))
            current["referenceApprovalCommit"] = approval_commit
            current["entries"]["page.html::light"]["sha256"] = "2" * 64
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
            context = Context(root, config, root, root, {}, {}, {}, [])

            with mock.patch("ui_conformance.approval_lineage_errors", return_value=[]):
                errors = baseline_history_errors(context, current)

        self.assertTrue(any("requires a new approved reference ID" in error for error in errors), errors)

    def test_repaired_current_baseline_does_not_hide_a_malformed_historical_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Baseline Test")
            self.git(root, "config", "user.email", "ui-baseline@example.invalid")
            schema_path = root / "verification" / "desktop-ui-baseline.schema.json"
            schema_path.parent.mkdir(parents=True)
            shutil.copy2(REPO / "verification" / "desktop-ui-baseline.schema.json", schema_path)
            approval = root / "design" / "ui-reference" / "APPROVAL.yaml"
            approval.parent.mkdir(parents=True)
            approval.write_text("status: approved\n", encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "establish approval")
            approval_commit = self.git(root, "rev-parse", "HEAD")
            baseline_path = root / "verification" / "baselines" / "desktop-ui.json"
            canonical = json.loads(
                (REPO / "verification" / "baselines" / "desktop-ui.json").read_text(encoding="utf-8")
            )
            canonical["referenceApprovalCommit"] = approval_commit
            malformed = json.loads(json.dumps(canonical))
            malformed["settings"] = "not-an-object"
            malformed["platform"] = "junk"
            malformed["entries"]["index.html::light"]["width"] = -1
            malformed["entries"]["index.html::light"]["height"] = 0
            self.write_json(baseline_path, malformed)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "malformed historical baseline")
            self.write_json(baseline_path, canonical)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "repair current baseline")
            context = Context(
                root,
                {
                    "visual": {"baselinePath": "verification/baselines/desktop-ui.json"},
                    "normativeSources": {"style": "design/ui-reference/STYLE_GUIDE.md"},
                },
                root,
                root,
                {},
                {},
                {},
                [],
            )

            with mock.patch("ui_conformance.approval_lineage_errors", return_value=[]):
                errors = baseline_history_errors(context, canonical)

        self.assertTrue(any("settings" in error and "not of type 'object'" in error for error in errors), errors)

    def test_post_approval_package_mutation_cannot_be_laundered_through_a_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Baseline Test")
            self.git(root, "config", "user.email", "ui-baseline@example.invalid")
            shutil.copytree(REFERENCE, root / "design" / "ui-reference")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve exact reference package")
            approval_commit = self.git(root, "rev-parse", "HEAD")
            self.git(root, "checkout", "-b", "package-change")
            css = root / "design" / "ui-reference" / "assets" / "app.css"
            css.write_text(
                css.read_text(encoding="utf-8") + "\n.post-approval { color: red; }\n",
                encoding="utf-8",
                newline="\n",
            )
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["file_hashes"]["assets/app.css"] = hashlib.sha256(css.read_bytes()).hexdigest()
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "mutate package without approval")
            self.git(root, "checkout", "main")
            (root / "unrelated.txt").write_text("mainline\n", encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "mainline work")
            self.git(root, "merge", "--no-ff", "package-change", "-m", "merge unapproved package")
            baseline_commit = self.git(root, "rev-parse", "HEAD")
            package_sha256 = hashlib.sha256(
                json.dumps(manifest["file_hashes"], sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            baseline = {
                "referenceId": manifest["reference_id"],
                "referencePackageSha256": package_sha256,
                "referenceApprovalCommit": approval_commit,
            }

            errors = approval_lineage_errors(root, baseline, baseline_commit)

        self.assertTrue(any("did not exist at the cited approval commit" in error for error in errors), errors)
        self.assertTrue(any("changed after its cited approval commit" in error for error in errors), errors)

    def test_provenance_only_ratification_cannot_change_the_visual_contract(self) -> None:
        previous = json.loads((REPO / "verification" / "baselines" / "desktop-ui.json").read_text(encoding="utf-8"))
        previous["referencePackageSha256"] = "1" * 64
        previous["referenceApprovalCommit"] = "1" * 40
        ratified = json.loads(json.dumps(previous))
        ratified["referencePackageSha256"] = "2" * 64
        ratified["referenceApprovalCommit"] = "2" * 40

        self.assertTrue(provenance_only_reference_ratification(previous, ratified))

        changed_visual = json.loads(json.dumps(ratified))
        changed_visual["entries"]["index.html::light"]["sha256"] = "3" * 64
        self.assertFalse(provenance_only_reference_ratification(previous, changed_visual))

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
