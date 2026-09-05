from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "design" / "ui-reference"
sys.path.insert(0, str(REPO / "tools"))

from ui_conformance import (  # noqa: E402
    APPLICATION_EXCLUDED_DIRECTORIES,
    Context,
    application_inventory_guard,
    application_inventory_shape,
    approval_lineage_errors,
    approval_record_errors,
    baseline_document_errors,
    baseline_history_errors,
    check_accessibility,
    check_routes,
    check_tokens,
    check_visual,
    check_workflows,
    file_inventory,
    font_face_available,
    implementation_files,
    independently_rejected_maintenance_baseline_snapshot,
    load_context,
    new_page,
    open_browser,
    provenance_only_reference_ratification,
    set_page,
    wave_slice_authority_bound_approval_errors,
    wave_slice_proposal_consumption_errors,
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

    def wave_slice_authority_fixture(
        self,
        temporary: str,
        *,
        extra_proposal_path: bool = False,
        merge_projection: bool = False,
        substitute_slice: bool = False,
    ) -> tuple[Path, dict[str, Any], str, str]:
        root = Path(temporary) / "repo"
        root.mkdir()
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.name", "UI Authority Test")
        self.git(root, "config", "user.email", "ui-authority@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")
        approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
        manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
        slice_relative = "planning/slice-plans/CAP-03/CAP-03.S05-fixture.md"
        slice_path = root / slice_relative

        old_approval = {
            "status": "approved",
            "approved_by": "repository-owner",
            "approved_at": "2026-08-01T00:00:00+00:00",
            "approved_commit": "0" * 40,
        }

        def write_backlog(wave_approval: dict[str, Any]) -> None:
            path = root / "planning" / "backlog.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump({"waves": [{"id": "W1", "approval": wave_approval}]}, sort_keys=False),
                encoding="utf-8",
                newline="\n",
            )

        def write_slice(slice_approval: dict[str, Any]) -> None:
            metadata = {
                "document_type": "slice-implementation-plan",
                "capability_id": "CAP-03",
                "slice_id": "CAP-03.S05",
                "status": "approved",
                "wave": "W1",
                "approval": slice_approval,
            }
            slice_path.parent.mkdir(parents=True, exist_ok=True)
            slice_path.write_text(
                "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n# Stable fixture plan\n",
                encoding="utf-8",
                newline="\n",
            )

        write_backlog(old_approval)
        write_slice(old_approval)
        approval_path.parent.mkdir(parents=True, exist_ok=True)
        approval_path.write_text("reference_id: REF-1\nstatus: approved\n", encoding="utf-8", newline="\n")
        manifest_path.write_text("reference_id: REF-1\nstatus: approved\n", encoding="utf-8", newline="\n")
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", "freeze Wave packet")
        packet = self.git(root, "rev-parse", "HEAD")

        projected = {
            "status": "APPROVED",
            "approved_by": "repository-owner",
            "approved_at": "2026-09-01T00:00:00+00:00",
            "approved_commit": packet,
            "slice_ids": ["CAP-03.S05"],
        }
        if merge_projection:
            self.git(root, "checkout", "-b", "projection-injection")
        write_backlog(projected)
        write_slice(
            {
                "status": "approved",
                "approved_by": projected["approved_by"],
                "approved_at": projected["approved_at"],
                "approved_commit": packet,
            }
        )
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", "materialize Wave approval projection")
        if merge_projection:
            self.git(root, "checkout", "main")
            self.git(
                root,
                "merge",
                "--no-ff",
                "projection-injection",
                "-m",
                "inject Wave approval projection through merge",
            )

        if substitute_slice:
            substituted = yaml.safe_load(slice_path.read_text(encoding="utf-8").split("---", 2)[1])
            substituted["title"] = "Substituted after Wave approval"
            slice_path.write_text(
                "---\n" + yaml.safe_dump(substituted, sort_keys=False) + "---\n# Stable fixture plan\n",
                encoding="utf-8",
                newline="\n",
            )
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "substitute approved slice authority")

        proposal_authority = {
            "wave_id": "W1",
            "slice_id": "CAP-03.S05",
            "approved_wave_commit": packet,
            "slice_plan": slice_relative,
        }
        proposal = {
            "reference_id": "REF-2",
            "version": "2",
            "status": "proposed",
            "approval_kind": "pending-human",
            "approved_by": None,
            "approved_at": None,
            "approval_basis": "Await exact human approval.",
            "authority": proposal_authority,
            "supersedes": "REF-1",
            "scope": {"normative": ["fixture"], "illustrative": ["values"]},
            "implementation_rule": "Approval precedes implementation.",
            "deferred_surfaces": [],
        }
        approval_path.write_text(yaml.safe_dump(proposal, sort_keys=False), encoding="utf-8", newline="\n")
        proposal_manifest = {
            "reference_id": "REF-2",
            "version": "2",
            "status": "proposed",
            "file_hashes": {"APPROVAL.yaml": hashlib.sha256(approval_path.read_bytes()).hexdigest()},
        }
        manifest_path.write_text(yaml.safe_dump(proposal_manifest, sort_keys=False), encoding="utf-8", newline="\n")
        if extra_proposal_path:
            (root / "unrelated.txt").write_text("not governance\n", encoding="utf-8", newline="\n")
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", "propose reference")
        proposal_commit = self.git(root, "rev-parse", "HEAD")

        approved = {
            **proposal,
            "status": "approved",
            "approval_kind": "human",
            "approved_by": "human:repository-owner",
            "approved_at": "2026-09-03T00:00:00+00:00",
            "approval_basis": "Repository owner approved the exact proposal.",
            "authority": {**proposal_authority, "proposal_commit": proposal_commit},
        }
        approval_path.write_text(yaml.safe_dump(approved, sort_keys=False), encoding="utf-8", newline="\n")
        approved_manifest = {
            **proposal_manifest,
            "status": "approved",
            "file_hashes": {"APPROVAL.yaml": hashlib.sha256(approval_path.read_bytes()).hexdigest()},
        }
        manifest_path.write_text(yaml.safe_dump(approved_manifest, sort_keys=False), encoding="utf-8", newline="\n")
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", "approve reference")
        approval_commit = self.git(root, "rev-parse", "HEAD")
        return root, approved, proposal_commit, approval_commit

    def test_canonical_token_and_route_contracts_pass_with_normative_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            token_result = check_tokens(context)
            route_result = check_routes(context)

        self.assertTrue(token_result["ok"], token_result["errors"])
        self.assertTrue(route_result["ok"], route_result["errors"])
        self.assertEqual(109, token_result["details"]["tokens"])
        approved_routes = json.loads((REPO / "design" / "ui-reference" / "SITE_MANIFEST.json").read_text())["pages"]
        self.assertEqual(len(approved_routes), route_result["details"]["routes"])
        self.assertEqual("design/ui-reference/assets/tokens.css", token_result["normativeSources"]["tokens"])
        self.assertIn("mock names", route_result["illustrativeExclusions"])

    def test_fixture_mode_refuses_to_mask_an_application_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REFERENCE, root / "design" / "ui-reference")
            (root / "verification" / "extensions").mkdir(parents=True)
            fixture_config = json.loads(
                (REPO / "verification" / "extensions" / "desktop-ui.json").read_text(encoding="utf-8")
            )
            fixture_config["mode"] = "approved-reference-fixture"
            fixture_config["targetRoot"] = "design/ui-reference"
            self.write_json(root / "verification" / "extensions" / "desktop-ui.json", fixture_config)
            shutil.copy2(
                REPO / "verification" / "desktop-ui.schema.json",
                root / "verification" / "desktop-ui.schema.json",
            )
            implementation = root / "apps" / "desktop" / "src" / "Application.test.tsx"
            implementation.parent.mkdir(parents=True)
            implementation.write_text("export const View = () => null;\n", encoding="utf-8", newline="\n")

            with self.assertRaisesRegex(ValueError, "cannot remain active"):
                load_context(root)

    def test_implementation_inventory_excludes_dependency_and_build_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            package = root / "packages" / "ui-components"
            source = package / "src" / "index.tsx"
            source.parent.mkdir(parents=True)
            source.write_text("export const Component = () => null;\n", encoding="utf-8", newline="\n")
            for directory in ("node_modules", "dist", "target"):
                generated = package / directory / "dependency.tsx"
                generated.parent.mkdir(parents=True)
                generated.write_text("export const Dependency = () => null;\n", encoding="utf-8", newline="\n")
                authored = package / "src" / directory / "Attack.tsx"
                authored.parent.mkdir(parents=True)
                authored.write_text("export const Attack = () => null;\n", encoding="utf-8", newline="\n")

            observed = implementation_files(root, ["packages/ui-components"])

        self.assertEqual(
            [
                "packages/ui-components/src/dist/Attack.tsx",
                "packages/ui-components/src/index.tsx",
                "packages/ui-components/src/node_modules/Attack.tsx",
                "packages/ui-components/src/target/Attack.tsx",
            ],
            observed,
        )

    def test_application_inventory_excludes_only_canonical_root_generated_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            application = root / "apps" / "desktop"
            expected: list[str] = []
            for directory in ("node_modules", "dist", "target"):
                generated = application / directory / "dependency.tsx"
                generated.parent.mkdir(parents=True, exist_ok=True)
                generated.write_text("export const Dependency = () => null;\n", encoding="utf-8", newline="\n")
                authored = application / "src" / directory / "Attack.tsx"
                authored.parent.mkdir(parents=True, exist_ok=True)
                authored.write_text("export const Attack = () => null;\n", encoding="utf-8", newline="\n")
                expected.append(authored.relative_to(root).as_posix())

            observed = file_inventory(root, application, excluded_directories=APPLICATION_EXCLUDED_DIRECTORIES)
            held_files, _ = application_inventory_shape(
                root,
                ((application, APPLICATION_EXCLUDED_DIRECTORIES),),
            )

        self.assertEqual(sorted(expected), sorted(observed))
        self.assertEqual(sorted(expected), sorted(path.relative_to(root).as_posix() for path in held_files))

    def test_application_mode_requires_a_bound_build_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REFERENCE, root / "design" / "ui-reference")
            shutil.copytree(REFERENCE, root / "apps" / "desktop" / "dist")
            source = root / "apps" / "desktop" / "src" / "View.tsx"
            source.parent.mkdir(parents=True)
            source.write_text("export const View = () => null;\n", encoding="utf-8", newline="\n")
            (root / "verification" / "extensions").mkdir(parents=True)
            shutil.copy2(
                REPO / "verification" / "extensions" / "desktop-ui.json",
                root / "verification" / "extensions" / "desktop-ui.json",
            )
            shutil.copy2(
                REPO / "verification" / "desktop-ui.schema.json",
                root / "verification" / "desktop-ui.schema.json",
            )

            with self.assertRaisesRegex(ValueError, "application manifest"):
                load_context(root)

    def test_application_inventory_detects_content_type_and_membership_races(self) -> None:
        for inventory_kind in ("source", "artifact"):
            for mutation in ("content", "type", "membership"):
                with (
                    self.subTest(inventory_kind=inventory_kind, mutation=mutation),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    root = Path(temporary) / "repo"
                    inventory_root = root / "apps" / "desktop" / ("src" if inventory_kind == "source" else "dist")
                    inventory_root.mkdir(parents=True)
                    source = inventory_root / "View.tsx"
                    source.write_text("export const value = 1;\n", encoding="utf-8", newline="\n")

                    def mutate(
                        mutation_kind: str = mutation,
                        source_path: Path = source,
                        root_path: Path = inventory_root,
                    ) -> None:
                        if mutation_kind == "content":
                            source_path.write_text("export const value = 2;\n", encoding="utf-8", newline="\n")
                        elif mutation_kind == "type":
                            source_path.unlink()
                            source_path.mkdir()
                        else:
                            (root_path / "Late.tsx").write_text(
                                "export const late = true;\n", encoding="utf-8", newline="\n"
                            )

                    with self.assertRaisesRegex((OSError, ValueError), "inventory|regular file"):
                        file_inventory(root, inventory_root, after_first_pass=mutate)

    def test_application_inventory_guard_holds_source_and_output_snapshot_through_completion(self) -> None:
        for inventory_kind in ("source", "artifact"):
            for mutation in ("content", "type", "membership"):
                with (
                    self.subTest(inventory_kind=inventory_kind, mutation=mutation),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    root = Path(temporary) / "repo"
                    source_root = root / "apps" / "desktop"
                    artifact_root = source_root / "dist"
                    source_root.mkdir(parents=True)
                    artifact_root.mkdir()
                    source = (source_root if inventory_kind == "source" else artifact_root) / "entry.txt"
                    source.write_text("before\n", encoding="utf-8", newline="\n")
                    for relative in (
                        "Cargo.toml",
                        "Cargo.lock",
                        "package.json",
                        "pnpm-lock.yaml",
                        "verification/extensions/desktop-ui.json",
                    ):
                        external = root / relative
                        external.parent.mkdir(parents=True, exist_ok=True)
                        external.write_text("governed\n", encoding="utf-8", newline="\n")

                    with (
                        self.assertRaises((OSError, ValueError)),
                        application_inventory_guard(root, source_root, artifact_root),
                    ):
                        if mutation == "content":
                            source.write_text("after\n", encoding="utf-8", newline="\n")
                        elif mutation == "type":
                            source.unlink()
                            source.mkdir()
                        else:
                            (source.parent / "late.txt").write_text("late\n", encoding="utf-8", newline="\n")

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
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
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

    def test_actual_authority_bound_v14_approval_shape_is_exact(self) -> None:
        approval = yaml.safe_load(
            self.git(
                REPO,
                "show",
                "9f26bd47c653b1c4dd6c3be94c2feefceeb96c4b:design/ui-reference/APPROVAL.yaml",
            )
        )

        errors = approval_record_errors(approval, "v1.4-approval", "RO-UI-ACADEMIC-MINIMAL-1.4")

        self.assertEqual([], errors)
        malformed = dict(approval)
        malformed.pop("approval_kind")
        malformed_errors = approval_record_errors(
            malformed,
            "malformed-v1.4-approval",
            "RO-UI-ACADEMIC-MINIMAL-1.4",
        )
        self.assertTrue(any("approval fields must be exact" in error for error in malformed_errors), malformed_errors)

    def test_actual_wave_slice_bound_v15_approval_shape_is_exact(self) -> None:
        approval = yaml.safe_load(
            self.git(REPO, "show", "7ec1b27d72c189216d7a203586b7339202733531:design/ui-reference/APPROVAL.yaml")
        )

        errors = approval_record_errors(approval, "v1.5-approval", "RO-UI-ACADEMIC-MINIMAL-1.5")

        self.assertEqual([], errors)
        self.assertEqual(
            {
                "wave_id",
                "slice_id",
                "approved_wave_commit",
                "proposal_commit",
                "slice_plan",
            },
            set(approval["authority"]),
        )

    def test_actual_wave_slice_bound_v15_approval_resolves_exact_authority(self) -> None:
        approval = yaml.safe_load(
            self.git(REPO, "show", "7ec1b27d72c189216d7a203586b7339202733531:design/ui-reference/APPROVAL.yaml")
        )

        errors = wave_slice_authority_bound_approval_errors(
            REPO,
            approval,
            "7ec1b27d72c189216d7a203586b7339202733531",
            "design/ui-reference/APPROVAL.yaml",
        )

        self.assertEqual([], errors)

    def test_wave_slice_bound_approval_rejects_unresolvable_wave_authority(self) -> None:
        approval = yaml.safe_load(
            self.git(REPO, "show", "7ec1b27d72c189216d7a203586b7339202733531:design/ui-reference/APPROVAL.yaml")
        )
        approval["authority"]["approved_wave_commit"] = "0" * 40

        errors = wave_slice_authority_bound_approval_errors(
            REPO,
            approval,
            "7ec1b27d72c189216d7a203586b7339202733531",
            "design/ui-reference/APPROVAL.yaml",
        )

        self.assertTrue(any("approved Wave authority commit cannot be resolved" in error for error in errors), errors)

    def test_active_presentation_requires_its_exact_compatibility_witness(self) -> None:
        with (
            mock.patch(
                "ui_conformance.presentation_compatibility_errors", return_value=["missing exact witness"]
            ) as verify,
            self.assertRaisesRegex(ValueError, "invalid presentation compatibility.*missing exact witness"),
        ):
            load_context(REPO)
        verify.assert_called_once_with(
            REPO,
            "RO-UI-ACADEMIC-MINIMAL-1.6",
            "8d7fdc7ae43f04477ab55574542ad928500270f48d100bec74c4872ccb4366ea",
        )

    def test_actual_amendment_bound_v16_approval_shape_is_exact(self) -> None:
        approval = yaml.safe_load((REFERENCE / "APPROVAL.yaml").read_text(encoding="utf-8"))
        self.assertEqual([], approval_record_errors(approval, "v1.6-approval", "RO-UI-ACADEMIC-MINIMAL-1.6"))
        self.assertEqual(
            {
                "amendment_id",
                "change_request_id",
                "approval_record",
                "approval_record_sha256",
                "approval_record_introduction_commit",
            },
            set(approval["authority"]),
        )

    def test_wave_slice_bound_approval_accepts_exact_projection_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, approval, _, approval_commit = self.wave_slice_authority_fixture(temporary)

            errors = wave_slice_authority_bound_approval_errors(
                root,
                approval,
                approval_commit,
                "design/ui-reference/APPROVAL.yaml",
            )

        self.assertEqual([], errors)

    def test_wave_slice_bound_approval_rejects_extra_proposal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, approval, _, approval_commit = self.wave_slice_authority_fixture(
                temporary,
                extra_proposal_path=True,
            )

            errors = wave_slice_authority_bound_approval_errors(
                root,
                approval,
                approval_commit,
                "design/ui-reference/APPROVAL.yaml",
            )

        self.assertTrue(any("proposal must change only" in error for error in errors), errors)

    def test_wave_slice_bound_approval_rejects_multiparent_projection_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, approval, _, approval_commit = self.wave_slice_authority_fixture(
                temporary,
                merge_projection=True,
            )

            errors = wave_slice_authority_bound_approval_errors(
                root,
                approval,
                approval_commit,
                "design/ui-reference/APPROVAL.yaml",
            )

        self.assertTrue(any("projection is not the direct child" in error for error in errors), errors)

    def test_wave_slice_bound_approval_rejects_slice_authority_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, approval, _, approval_commit = self.wave_slice_authority_fixture(
                temporary,
                substitute_slice=True,
            )

            errors = wave_slice_authority_bound_approval_errors(
                root,
                approval,
                approval_commit,
                "design/ui-reference/APPROVAL.yaml",
            )

        self.assertTrue(any("immutable slice approval projection" in error for error in errors), errors)

    def test_wave_slice_proposal_consumption_rejects_sibling_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, approved, proposal_commit, _ = self.wave_slice_authority_fixture(temporary)
            approval_path = root / "design" / "ui-reference" / "APPROVAL.yaml"
            manifest_path = root / "design" / "ui-reference" / "REFERENCE_MANIFEST.yaml"
            self.git(root, "checkout", "-b", "sibling", proposal_commit)
            sibling = {**approved, "approved_at": "2026-09-03T00:01:00+00:00"}
            approval_path.write_text(yaml.safe_dump(sibling, sort_keys=False), encoding="utf-8", newline="\n")
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "approved"
            manifest["file_hashes"] = {"APPROVAL.yaml": hashlib.sha256(approval_path.read_bytes()).hexdigest()}
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve same proposal on sibling")
            self.git(root, "checkout", "main")
            self.git(root, "merge", "-s", "ours", "sibling", "-m", "merge sibling approval")
            head = self.git(root, "rev-parse", "HEAD")

            errors = wave_slice_proposal_consumption_errors(
                root,
                head,
                "design/ui-reference/APPROVAL.yaml",
            )

        self.assertTrue(any("multiple reachable approvals" in error for error in errors), errors)

    def test_actual_authority_bound_v14_approval_resolves_to_immutable_approved_record(self) -> None:
        baseline = {
            "referenceId": "RO-UI-ACADEMIC-MINIMAL-1.4",
            "referencePackageSha256": "034d592ea97c35113ac802f885a469f89f9c72ad2548740347bef00f7484310e",
            "referenceApprovalCommit": "9f26bd47c653b1c4dd6c3be94c2feefceeb96c4b",
        }

        errors = approval_lineage_errors(REPO, baseline, self.git(REPO, "rev-parse", "HEAD"))

        self.assertEqual([], errors)

    def test_reachable_repository_baseline_history_is_valid(self) -> None:
        config = json.loads((REPO / "verification" / "extensions" / "desktop-ui.json").read_text(encoding="utf-8"))
        site = json.loads((REFERENCE / "SITE_MANIFEST.json").read_text(encoding="utf-8"))
        workflows = json.loads((REFERENCE / "WORKFLOW_CATALOG.json").read_text(encoding="utf-8"))["workflows"]
        page_contracts = json.loads((REFERENCE / "CAPABILITY_COVERAGE.json").read_text(encoding="utf-8"))[
            "page_contracts"
        ]
        pages = [str(item["file"]) for item in site["pages"]]
        context = Context(REPO, config, REFERENCE, REFERENCE, site, workflows, page_contracts, pages)
        baseline = json.loads((REPO / "verification" / "baselines" / "desktop-ui.json").read_text(encoding="utf-8"))

        errors = baseline_history_errors(context, baseline)

        self.assertEqual([], errors)

    def test_adopted_maintenance_makes_exact_rejected_candidate_history_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            self.git(Path(temporary), "clone", "--shared", str(REPO), str(root))
            self.git(root, "config", "user.name", "Adopted Maintenance Test")
            self.git(root, "config", "user.email", "adopted-maintenance@example.invalid")
            record_path = root / "planning" / "governance-migrations" / "GOV-MAINT-0010.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("status") != "adopted":
                candidate = self.git(root, "rev-parse", "HEAD")
                attempts = record["reviewAttempts"]
                review_number = len(attempts) + 1
                review_id = f"GOV-MAINT-0010.R{review_number:02d}"
                relative_review = f"planning/governance-migrations/GOV-MAINT-0010.review-R{review_number:02d}.json"
                candidate_paths = self.git(
                    root,
                    "diff-tree",
                    "--root",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    candidate,
                ).splitlines()
                review = {
                    "schemaVersion": "1.0",
                    "documentType": "governance-control-maintenance-review",
                    "maintenanceId": "GOV-MAINT-0010",
                    "reviewId": review_id,
                    "reviewedCommit": candidate,
                    "reviewer": "agent:prospective-independent-reviewer",
                    "reviewedAt": "2026-09-03T12:30:00+00:00",
                    "disposition": "APPROVED",
                    "authorityPreserved": True,
                    "candidateChangedPaths": sorted(candidate_paths),
                    "findings": [],
                }
                review_path = root / relative_review
                self.write_json(review_path, review)
                attempt = {
                    "reviewId": review_id,
                    "reviewedCommit": candidate,
                    "reviewer": review["reviewer"],
                    "reviewedAt": review["reviewedAt"],
                    "disposition": "APPROVED",
                    "findings": [],
                    "path": relative_review,
                    "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
                }
                record.update(status="adopted", reviewAttempts=[*attempts, attempt], review=attempt)
                self.write_json(record_path, record)
                self.git(root, "add", "--", str(record_path.relative_to(root)), relative_review)
                self.git(root, "commit", "-m", "materialize prospective independent adoption")

            config = json.loads((root / "verification" / "extensions" / "desktop-ui.json").read_text(encoding="utf-8"))
            reference = root / "design" / "ui-reference"
            site = json.loads((reference / "SITE_MANIFEST.json").read_text(encoding="utf-8"))
            workflows = json.loads((reference / "WORKFLOW_CATALOG.json").read_text(encoding="utf-8"))["workflows"]
            page_contracts = json.loads((reference / "CAPABILITY_COVERAGE.json").read_text(encoding="utf-8"))[
                "page_contracts"
            ]
            pages = [str(item["file"]) for item in site["pages"]]
            context = Context(root, config, reference, reference, site, workflows, page_contracts, pages)
            baseline = json.loads((root / "verification" / "baselines" / "desktop-ui.json").read_text(encoding="utf-8"))

            errors = baseline_history_errors(context, baseline)

        self.assertEqual([], errors)

    def test_rejected_maintenance_snapshot_requires_exact_adopted_attestation(self) -> None:
        relative = "verification/baselines/desktop-ui.json"
        record = {
            "reviewAttempts": [
                {
                    "reviewedCommit": "1" * 40,
                    "disposition": "CHANGES_REQUESTED",
                }
            ]
        }
        with (
            mock.patch("ui_change_gate.commit_paths", return_value={relative}),
            mock.patch("ui_change_gate.reviewed_preimplementation_maintenance_errors", return_value=[]),
            mock.patch(
                "ui_conformance.git",
                return_value="planning/governance-migrations/GOV-MAINT-0001.json",
            ),
            mock.patch("ui_conformance.git_json_at", return_value=(record, b"{}", None)),
        ):
            accepted = independently_rejected_maintenance_baseline_snapshot(
                REPO,
                "1" * 40,
                "2" * 40,
                relative,
            )

        self.assertTrue(accepted)

    def test_unattested_maintenance_snapshot_cannot_suppress_lineage_failure(self) -> None:
        relative = "verification/baselines/desktop-ui.json"
        with (
            mock.patch("ui_change_gate.commit_paths", return_value={relative}),
            mock.patch(
                "ui_change_gate.reviewed_preimplementation_maintenance_errors",
                return_value=["missing adopted independent review"],
            ),
        ):
            accepted = independently_rejected_maintenance_baseline_snapshot(
                REPO,
                "1" * 40,
                "2" * 40,
                relative,
            )

        self.assertFalse(accepted)

    def test_authority_bound_reference_cannot_reuse_a_prior_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Authority Test")
            self.git(root, "config", "user.email", "ui-authority@example.invalid")
            reference = root / "design" / "ui-reference"
            (reference / "assets").mkdir(parents=True)
            css = reference / "assets" / "app.css"
            css.write_text("body { color: black; }\n", encoding="utf-8", newline="\n")

            def approval(reference_id: str, *, authority: dict[str, str] | None = None) -> dict[str, Any]:
                value: dict[str, Any] = {
                    "reference_id": reference_id,
                    "version": reference_id.rsplit("-", 1)[-1],
                    "status": "approved",
                    "approved_by": "human:repository-owner" if authority else "repository-owner",
                    "approved_at": "2026-08-30T06:03:51+00:00",
                    "approval_basis": "Exact immutable authority fixture.",
                    "supersedes": "REF-1.3" if authority else None,
                    "scope": {"normative": ["fixture"], "illustrative": ["fixture values"]},
                    "implementation_rule": "Approval precedes implementation.",
                    "deferred_surfaces": [],
                }
                if authority is not None:
                    value.update(approval_kind="human", authority=authority)
                return value

            def write_reference(value: dict[str, Any]) -> str:
                approval_path = reference / "APPROVAL.yaml"
                approval_path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8", newline="\n")
                governed = ["APPROVAL.yaml", "assets/app.css"]
                file_hashes = {
                    relative: hashlib.sha256((reference / relative).read_bytes()).hexdigest() for relative in governed
                }
                manifest = {
                    "reference_id": value["reference_id"],
                    "version": value["version"],
                    "status": "approved",
                    "approval_file": "APPROVAL.yaml",
                    "canonical_token_file": "assets/app.css",
                    "style_guides": ["assets/app.css"],
                    "workflow_catalog": "assets/app.css",
                    "page_contracts": "assets/app.css",
                    "page_inventory": "assets/app.css",
                    "site_manifest": "assets/app.css",
                    "generator": "assets/app.css",
                    "validator": "assets/app.css",
                    "governed_files": governed,
                    "file_hashes": file_hashes,
                }
                (reference / "REFERENCE_MANIFEST.yaml").write_text(
                    yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n"
                )
                return hashlib.sha256(
                    json.dumps(file_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()

            write_reference(approval("REF-1.3"))
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve prior reference")

            packet_path = root / "planning" / "enabler-change-requests" / "ECR-0004.packet.json"
            packet = {
                "documentType": "enabler-change-request-packet",
                "changeRequestId": "ECR-0004",
                "proposedAmendmentId": "W1.A05",
                "targetWave": "W1",
                "status": "pending-approval",
                "executionState": "non-executable",
            }
            self.write_json(packet_path, packet)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "record exact amendment packet")
            packet_commit = self.git(root, "rev-parse", "HEAD")
            packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()

            record_path = root / "planning" / "wave-amendment-approvals" / "W1.A05.json"
            record = {
                "schemaVersion": "1.0",
                "documentType": "wave-amendment-approval",
                "amendmentId": "W1.A05",
                "changeRequestId": "ECR-0004",
                "targetWave": "W1",
                "status": "APPROVED",
                "approvedBy": "repository-owner",
                "approvedAt": "2026-08-30T06:03:51+00:00",
                "decision": "Approve the exact fixture packet.",
                "packet": {
                    "commit": packet_commit,
                    "path": "planning/enabler-change-requests/ECR-0004.packet.json",
                    "sha256": packet_sha,
                },
                "effectiveBase": {},
                "authorizedTaskIds": ["W1.A05.T04"],
                "bootstrapUnit": "W1.A05.B00",
                "independentPacketReview": {},
            }
            self.write_json(record_path, record)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "record human amendment approval")
            authority_commit = self.git(root, "rev-parse", "HEAD")
            authority = {
                "amendment_id": "W1.A05",
                "change_request_id": "ECR-0004",
                "approval_record": "planning/wave-amendment-approvals/W1.A05.json",
                "approval_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
                "approval_record_introduction_commit": authority_commit,
            }
            package = write_reference(approval("REF-1.4", authority=authority))
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve authority-bound reference")

            css.write_text("body { color: red; }\n", encoding="utf-8", newline="\n")
            fabricated = approval("REF-1.4", authority=authority)
            fabricated["approved_at"] = "2026-08-30T07:03:51+00:00"
            package = write_reference(fabricated)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "fabricate reapproval with reused authority")
            fabricated_approval = self.git(root, "rev-parse", "HEAD")
            (root / "baseline-marker.txt").write_text("baseline\n", encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "record fabricated baseline")
            baseline_commit = self.git(root, "rev-parse", "HEAD")
            baseline = {
                "referenceId": "REF-1.4",
                "referencePackageSha256": package,
                "referenceApprovalCommit": fabricated_approval,
            }

            errors = approval_lineage_errors(root, baseline, baseline_commit)

        self.assertTrue(any("authority" in error and "prior reference approval" in error for error in errors), errors)

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

    def test_historical_baselines_use_the_route_inventory_from_their_own_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Baseline Test")
            self.git(root, "config", "user.email", "ui-baseline@example.invalid")
            schema_path = root / "verification" / "desktop-ui-baseline.schema.json"
            schema_path.parent.mkdir(parents=True)
            shutil.copy2(REPO / "verification" / "desktop-ui-baseline.schema.json", schema_path)
            settings = json.loads(
                (REPO / "verification" / "extensions" / "desktop-ui.json").read_text(encoding="utf-8")
            )["visual"]
            site_path = root / "design" / "ui-reference" / "SITE_MANIFEST.json"
            self.write_json(site_path, {"pages": [{"file": "index.html"}]})
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve first route inventory")
            approval_one = self.git(root, "rev-parse", "HEAD")
            baseline_path = root / "verification" / "baselines" / "desktop-ui.json"

            def baseline(reference: str, package: str, approval: str, pages: list[str]) -> dict[str, Any]:
                return {
                    "schemaVersion": "1.0",
                    "documentType": "desktop-ui-visual-baseline",
                    "referenceId": reference,
                    "referencePackageSha256": package,
                    "referenceApprovalCommit": approval,
                    "platform": settings["platform"],
                    "playwrightVersion": settings["playwrightVersion"],
                    "browserVersion": settings["browserVersion"],
                    "settings": settings,
                    "entries": {
                        f"{page}::{theme}": {
                            "page": page,
                            "theme": theme,
                            "width": settings["viewport"]["width"],
                            "height": settings["viewport"]["height"],
                            "sha256": package,
                        }
                        for page in pages
                        for theme in ("light", "dark")
                    },
                }

            self.write_json(baseline_path, baseline("REF-1", "1" * 64, approval_one, ["index.html"]))
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "record first visual baseline")
            self.write_json(
                site_path,
                {"pages": [{"file": "index.html"}, {"file": "application-settings.html"}]},
            )
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve expanded route inventory")
            approval_two = self.git(root, "rev-parse", "HEAD")
            current = baseline(
                "REF-2",
                "2" * 64,
                approval_two,
                ["index.html", "application-settings.html"],
            )
            self.write_json(baseline_path, current)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "record expanded visual baseline")
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
                ["index.html", "application-settings.html"],
            )

            with mock.patch("ui_conformance.approval_lineage_errors", return_value=[]):
                errors = baseline_history_errors(context, current)

        self.assertEqual([], errors)

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

    def test_reference_only_mutation_and_restore_remains_visible_in_baseline_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Baseline Test")
            self.git(root, "config", "user.email", "ui-baseline@example.invalid")
            self.git(root, "config", "core.autocrlf", "false")
            reference = root / "design" / "ui-reference"
            shutil.copytree(REFERENCE, reference)
            schema_path = root / "verification" / "desktop-ui-baseline.schema.json"
            schema_path.parent.mkdir(parents=True)
            shutil.copy2(REPO / "verification" / "desktop-ui-baseline.schema.json", schema_path)
            approval_path = reference / "APPROVAL.yaml"
            approval = {
                "reference_id": "REF-1.3",
                "version": "1.3",
                "status": "approved",
                "approved_by": "repository-owner",
                "approved_at": "2026-09-01T00:00:00+00:00",
                "approval_basis": "Exact legacy reference fixture.",
                "supersedes": None,
                "scope": {"normative": ["fixture"], "illustrative": ["values"]},
                "implementation_rule": "Approval precedes implementation.",
                "deferred_surfaces": [],
            }
            approval_path.write_text(yaml.safe_dump(approval, sort_keys=False), encoding="utf-8", newline="\n")
            manifest_path = reference / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest.update(reference_id="REF-1.3", version="1.3", status="approved")

            def governed_hashes() -> dict[str, str]:
                return {
                    relative: hashlib.sha256(
                        (reference / relative).read_bytes().replace(b"\r\n", b"\n")
                        if (reference / relative).suffix.lower()
                        in {".css", ".html", ".js", ".json", ".md", ".mjs", ".py", ".ts", ".tsx", ".yaml", ".yml"}
                        else (reference / relative).read_bytes()
                    ).hexdigest()
                    for relative in manifest["governed_files"]
                }

            manifest["file_hashes"] = governed_hashes()
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "approve exact reference")
            approval_commit = self.git(root, "rev-parse", "HEAD")
            package = hashlib.sha256(
                json.dumps(manifest["file_hashes"], sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            baseline_path = root / "verification" / "baselines" / "desktop-ui.json"
            baseline = json.loads((REPO / "verification" / "baselines" / "desktop-ui.json").read_text(encoding="utf-8"))
            baseline.update(
                referenceId="REF-1.3",
                referencePackageSha256=package,
                referenceApprovalCommit=approval_commit,
            )
            self.write_json(baseline_path, baseline)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "record bound visual baseline")

            css_path = reference / "assets" / "app.css"
            approved_css = css_path.read_bytes()
            approved_manifest = manifest_path.read_bytes()
            css_path.write_bytes(approved_css + b"\n.unapproved { color: red; }\n")
            manifest["file_hashes"] = governed_hashes()
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "mutate reference without approval")
            css_path.write_bytes(approved_css)
            manifest_path.write_bytes(approved_manifest)
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "restore approved reference bytes")
            site = json.loads((reference / "SITE_MANIFEST.json").read_text(encoding="utf-8"))
            pages = [str(item["file"]) for item in site["pages"]]
            context = Context(
                root,
                {
                    "visual": {"baselinePath": "verification/baselines/desktop-ui.json"},
                    "normativeSources": {"style": "design/ui-reference/STYLE_GUIDE.md"},
                },
                reference,
                reference,
                site,
                {},
                {},
                pages,
            )

            errors = baseline_history_errors(context, baseline)

        self.assertTrue(
            any("visual baseline does not bind the exact approved reference package" in error for error in errors),
            errors,
        )

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

    def test_ratification_exception_still_validates_legacy_approval_and_claimed_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            self.git(root, "init", "-b", "main")
            self.git(root, "config", "user.name", "UI Baseline Test")
            self.git(root, "config", "user.email", "ui-baseline@example.invalid")
            reference = root / "design" / "ui-reference"
            shutil.copytree(REFERENCE, reference)
            approval = reference / "APPROVAL.yaml"
            approval.write_text(
                "reference_id: RO-UI-ACADEMIC-MINIMAL-1.3\nstatus: approved\n",
                encoding="utf-8",
                newline="\n",
            )
            manifest_path = reference / "REFERENCE_MANIFEST.yaml"
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["file_hashes"]["APPROVAL.yaml"] = hashlib.sha256(approval.read_bytes()).hexdigest()
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "malformed legacy approval")
            approval_commit = self.git(root, "rev-parse", "HEAD")
            (root / "baseline-marker.txt").write_text("baseline\n", encoding="utf-8", newline="\n")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "legacy baseline")
            baseline_commit = self.git(root, "rev-parse", "HEAD")
            baseline = {
                "referenceId": "RO-UI-ACADEMIC-MINIMAL-1.3",
                "referencePackageSha256": "1" * 64,
                "referenceApprovalCommit": approval_commit,
            }

            errors = approval_lineage_errors(
                root,
                baseline,
                baseline_commit,
                verify_package_at_original_approval=False,
            )

        self.assertTrue(any("approval fields must be exact" in error for error in errors), errors)
        self.assertTrue(any("does not bind the exact approved reference package" in error for error in errors), errors)

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

    def test_transient_visual_mismatch_requires_two_matching_targeted_retries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context = self.context_copy(temporary)
            baseline_path = context.repo / "verification" / "baselines" / "desktop-ui.json"
            baseline_path.parent.mkdir(parents=True)
            shutil.copy2(REPO / "verification" / "baselines" / "desktop-ui.json", baseline_path)
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            observed = json.loads(json.dumps(baseline["entries"]))
            observed["index.html::dark"]["sha256"] = "0" * 64
            retry = {"index.html::dark": baseline["entries"]["index.html::dark"]}
            with (
                mock.patch("ui_conformance.baseline_history_errors", return_value=[]),
                mock.patch(
                    "ui_conformance.render_visuals",
                    side_effect=[(observed, []), (retry, []), (retry, [])],
                ) as renderer,
            ):
                result = check_visual(context)

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(2, result["details"]["stabilizedRetries"])
        self.assertEqual(3, renderer.call_count)


if __name__ == "__main__":
    unittest.main()
