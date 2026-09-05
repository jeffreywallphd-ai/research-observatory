from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from product_style_check import (  # noqa: E402
    analyze_product_style_sources,
    capture_source_identity,
    load_product_style_sources,
    png_dimensions,
    product_style_analysis,
    read_capture_bundle,
    write_capture_bundle,
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


class CaptureBundleTests(unittest.TestCase):
    @staticmethod
    def png_bytes(pixel: bytes = b"\xff\xff\xff") -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack("!2I5B", 16, 12, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + pixel * 16) * 12))
            + chunk(b"IEND", b"")
        )

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name).resolve()
        (self.repo / "captures").mkdir()
        (self.repo / "source.txt").write_text("source\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Capture fixture")
        self.git("config", "user.email", "capture@example.invalid")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "producer")
        self.producer = self.git("rev-parse", "HEAD").decode().strip()
        self.contract = [
            {
                "caseId": "projects:light:16x12",
                "surfaceId": "projects",
                "stateId": "empty",
                "theme": "light",
                "viewport": {"width": 16, "height": 12},
                "role": "product",
                "referencePage": "projects.html",
                "width": 16,
                "height": 12,
            }
        ]
        self.png = self.png_bytes()

    def git(self, *args: str) -> bytes:
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True).stdout

    def snapshot(self) -> dict[str, Any]:
        return {"producerCommit": self.producer, "input": (self.repo / "source.txt").read_text()}

    def render(self, capture: Any) -> tuple[list[str], dict[str, Any]]:
        capture(self.contract[0], self.png)
        return [], {"geometry": {"width": 16, "height": 12}}

    def publish(self, render: Any = None) -> Path:
        return write_capture_bundle(self.repo, "captures/run-01", self.contract, self.snapshot, render or self.render)

    def deliver(self) -> str:
        self.git("add", "captures/run-01")
        self.git("commit", "-qm", "deliver captures")
        return self.git("rev-parse", "HEAD").decode().strip()

    def test_real_git_delivery_roundtrip_requires_immutable_authentication(self) -> None:
        manifest = self.publish()
        with self.assertRaises(ValueError):
            read_capture_bundle(self.repo, manifest, self.producer, self.contract)
        delivery = self.deliver()
        result = read_capture_bundle(self.repo, manifest, delivery, self.contract)
        self.assertEqual(result["producer"]["producerCommit"], self.producer)
        self.assertNotEqual(self.producer, delivery)

    def test_duplicate_missing_extra_and_invalid_png_captures_never_publish(self) -> None:
        for label in ["duplicate", "missing", "extra", "truncated", "wrong-dimensions", "nonfinite"]:
            with self.subTest(label=label):

                def bad_render(capture: Any, label: str = label) -> tuple[list[str], dict[str, Any]]:
                    if label == "missing":
                        return [], {}
                    metadata = dict(self.contract[0])
                    if label == "extra":
                        metadata["theme"] = "dark"
                    if label == "wrong-dimensions":
                        metadata["width"] = 20
                    capture(metadata, self.png[:30] if label == "truncated" else self.png)
                    if label == "duplicate":
                        capture(metadata, self.png)
                    return [], {"width": float("nan")} if label == "nonfinite" else {}

                with self.assertRaises(ValueError):
                    write_capture_bundle(self.repo, f"captures/{label}", self.contract, self.snapshot, bad_render)
                self.assertFalse((self.repo / "captures" / label / "manifest.json").exists())

    def test_no_overwrite_and_interruption_leave_no_completion_marker(self) -> None:
        def interrupted(capture: Any) -> Any:
            capture(self.contract[0], self.png)
            raise RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            self.publish(interrupted)
        self.assertFalse((self.repo / "captures/run-01/manifest.json").exists())
        self.assertEqual(len(list((self.repo / "captures/run-01").glob("*.png"))), 1)
        with self.assertRaises((OSError, ValueError)):
            self.publish()

    def test_source_change_during_capture_never_publishes(self) -> None:
        def changed(capture: Any) -> Any:
            result = self.render(capture)
            (self.repo / "source.txt").write_text("changed\n")
            return result

        with self.assertRaisesRegex(ValueError, "producer"):
            self.publish(changed)
        self.assertFalse((self.repo / "captures/run-01/manifest.json").exists())

    def test_co_tampered_manifest_and_png_fail_against_delivery(self) -> None:
        manifest = self.publish()
        delivery = self.deliver()
        document = json.loads(manifest.read_text())
        capture = document["captures"][0]
        altered = self.png_bytes(b"\0\0\0")
        (manifest.parent / capture["file"]).write_bytes(altered)
        capture["sha256"] = hashlib.sha256(altered).hexdigest()
        manifest.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "delivery"):
            read_capture_bundle(self.repo, manifest, delivery, self.contract)

    def test_exact_current_and_committed_inventory_and_contract_are_required(self) -> None:
        manifest = self.publish()
        delivery = self.deliver()
        with self.assertRaises(ValueError):
            read_capture_bundle(self.repo, manifest, delivery, [])
        (manifest.parent / "extra.png").write_bytes(self.png)
        with self.assertRaises(ValueError):
            read_capture_bundle(self.repo, manifest, delivery, self.contract)
        self.git("add", "captures/run-01/extra.png")
        self.git("commit", "-qm", "extra inventory")
        with self.assertRaises(ValueError):
            read_capture_bundle(self.repo, manifest, self.git("rev-parse", "HEAD").decode().strip(), self.contract)

    def test_traversal_alias_and_duplicate_contract_rejected(self) -> None:
        for path in ["../escape", "captures/../escape", "captures//alias", "captures/./alias", "captures\\alias"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                write_capture_bundle(self.repo, path, self.contract, self.snapshot, self.render)
        with self.assertRaises(ValueError):
            write_capture_bundle(self.repo, "captures/duplicate", self.contract * 2, self.snapshot, self.render)

    def test_real_producer_git_boundary_rejects_untracked_dirty_and_stale_hash(self) -> None:
        source = self.repo / "source.txt"
        files = {"source.txt": hashlib.sha256(source.read_bytes()).hexdigest()}
        identity = capture_source_identity(self.repo, self.producer, files)
        self.assertEqual(identity["source.txt"], self.git("rev-parse", "HEAD:source.txt").decode().strip())
        with self.assertRaises(ValueError):
            capture_source_identity(self.repo, self.producer, {"untracked.txt": "0" * 64})
        with self.assertRaises(ValueError):
            capture_source_identity(self.repo, self.producer, {"source.txt": "0" * 64})
        source.write_text("changed\n")
        with self.assertRaises(ValueError):
            capture_source_identity(
                self.repo, self.producer, {"source.txt": hashlib.sha256(source.read_bytes()).hexdigest()}
            )

    def test_producer_index_flags_cannot_hide_changed_bytes(self) -> None:
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.git("update-index", "--no-assume-unchanged", "--no-skip-worktree", "source.txt")
                (self.repo / "source.txt").write_text("source\n")
                self.git("update-index", flag, "source.txt")
                source = self.repo / "source.txt"
                source.write_text("changed\n")
                with self.assertRaises(ValueError):
                    capture_source_identity(
                        self.repo, self.producer, {"source.txt": hashlib.sha256(source.read_bytes()).hexdigest()}
                    )

    def test_producer_git_binding_preserves_declared_text_normalization(self) -> None:
        (self.repo / ".gitattributes").write_text("source.txt text eol=lf\n", encoding="utf-8")
        self.git("add", ".gitattributes")
        self.git("commit", "-qm", "declare text normalization")
        commit = self.git("rev-parse", "HEAD").decode().strip()
        source = self.repo / "source.txt"
        source.write_bytes(b"source\r\n")
        result = capture_source_identity(
            self.repo, commit, {"source.txt": hashlib.sha256(source.read_bytes()).hexdigest()}
        )
        self.assertEqual(result["source.txt"], self.git("rev-parse", "HEAD:source.txt").decode().strip())

    @unittest.skipUnless(os.name == "nt", "actual Windows junction boundary")
    def test_junction_capture_paths_are_rejected_without_touching_target(self) -> None:
        manifest = self.publish()
        original = manifest.read_bytes()
        delivery = self.deliver()
        alias = self.repo / "captures/alias"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(manifest.parent)], check=True, capture_output=True)
        try:
            with self.assertRaises(ValueError):
                read_capture_bundle(self.repo, alias / "manifest.json", delivery, self.contract)
            with self.assertRaises(ValueError):
                write_capture_bundle(self.repo, "captures/alias/nested", self.contract, self.snapshot, self.render)
            self.assertEqual(manifest.read_bytes(), original)
        finally:
            alias.rmdir()

    def test_png_crc_completion_pixels_and_trailing_bytes_are_checked(self) -> None:
        self.assertEqual(png_dimensions(self.png), (16, 12))
        corrupted = bytearray(self.png)
        corrupted[20] ^= 1
        for payload in [bytes(corrupted), self.png[:-12], self.png + b"extra", self.png[:33] + self.png[-12:]]:
            with self.subTest(payload=len(payload)), self.assertRaises(ValueError):
                png_dimensions(payload)

    def test_directory_replacement_during_publication_is_denied(self) -> None:
        def replaced(capture: Any) -> Any:
            result = self.render(capture)
            source = self.repo / "captures/run-01"
            source.rename(self.repo / "captures/replaced")
            source.mkdir()
            return result

        with self.assertRaises((OSError, ValueError)):
            self.publish(replaced)
        self.assertFalse((self.repo / "captures/run-01/manifest.json").exists())

    def test_late_png_change_cannot_pass_a_bundle_read(self) -> None:
        import product_style_check

        manifest = self.publish()
        delivery = self.deliver()
        png = next(manifest.parent.glob("*.png"))
        original = product_style_check._git_bytes

        def mutate_after_validation(repo: Path, *args: str) -> bytes:
            result = original(repo, *args)
            if args[0] == "ls-tree":
                png.write_bytes(self.png_bytes(b"\0\0\0"))
            return result

        with (
            patch.object(product_style_check, "_git_bytes", mutate_after_validation),
            self.assertRaises((OSError, ValueError)),
        ):
            read_capture_bundle(self.repo, manifest, delivery, self.contract)


if __name__ == "__main__":
    unittest.main()
