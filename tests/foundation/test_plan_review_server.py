"""Real loopback and source-boundary proof for the display-only review server."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import plan_review_server as server_module  # noqa: E402
from plan_review_server import ASSETS, Projection, ReviewServer, SourceChanged  # noqa: E402


class LiveReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "planning/capability-plans").mkdir(parents=True)
        (self.root / "planning/slice-plans/CAP-06").mkdir(parents=True)
        self.data: dict[str, Any] = {
            "waves": [
                {
                    "id": "W3",
                    "title": "Search",
                    "approval": {"status": "APPROVED", "approved_commit": "a" * 40},
                    "campaign": {"status": "PAUSED", "owner": "PRIVATE-OWNER", "worktree": "PRIVATE-PATH"},
                }
            ],
            "capabilities": [
                {
                    "id": "CAP-06",
                    "alias": "Search",
                    "title": "Local search",
                    "slices": [
                        {
                            "id": "CAP-06.S01",
                            "wave": "W3",
                            "title": "Lexical",
                            "outcome": "Traceable lexical retrieval",
                            "depends_on": ["CAP-05.S01"],
                            "tasks": [
                                {
                                    "id": "CAP-06.S01.T01",
                                    "status": "READY",
                                    "title": "<script>unsafe()</script>",
                                    "owner": "PRIVATE-OWNER",
                                    "lease": {"claimed_by": "PRIVATE-OWNER"},
                                    "acceptance_criteria": ["Keep evidence"],
                                }
                            ],
                        }
                    ],
                }
            ],
            "release_gates": [
                {
                    "id": "G3",
                    "after_wave": "W3",
                    "status": "PENDING",
                    "name": "Evidence workbench",
                    "criteria": ["Fresh full qualification"],
                    "unlocks_waves": ["W4"],
                }
            ],
        }
        self.write_backlog()
        self.cap = self.root / "planning/capability-plans/CAP-06.md"
        self.cap.write_text(
            "---\ncapability_id: CAP-06\ntitle: Search\ndecisions:\n- id: CAP-06-D01\n  title: Engine\n"
            "  binding_waves: [W3]\n  selected_option: SQLite\n---\n# Canonical body\n<script>unsafe()</script>\n",
            encoding="utf-8",
        )
        self.slice = self.root / "planning/slice-plans/CAP-06/CAP-06.S01-lexical.md"
        self.slice.write_text("---\nslice_id: CAP-06.S01\nstatus: approved\n---\n# Slice body\n", encoding="utf-8")
        self.assets = self.root / "site-assets"
        shutil.copytree(ASSETS, self.assets)
        self.server = ReviewServer(self.root, 0, assets=self.assets)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def write_backlog(self) -> None:
        (self.root / "planning/backlog.yaml").write_text(yaml.safe_dump(self.data), encoding="utf-8")

    def request(self, path: str, method: str = "GET", headers: dict[str, str] | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_actual_live_json_changes_without_generation_and_keeps_canonical_bytes(self) -> None:
        for arguments in (
            ["init"],
            ["add", "."],
            [
                "-c",
                "user.name=Synthetic Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-m",
                "Synthetic display fixture",
            ],
        ):
            subprocess.run(["git", *arguments], cwd=self.root, capture_output=True, check=True)
        originals = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        status, headers, body = self.request("/api/review/W3")
        self.assertEqual(200, status)
        model = json.loads(body)
        self.assertEqual("PAUSED", model["selected"]["campaign"]["status"])
        self.assertEqual(2, len(model["plans"]))
        self.assertEqual("SQLite", model["plans"][0]["decisions"][0]["selected_option"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual("nosniff", headers["X-Content-Type-Options"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("PRIVATE-", body.decode())
        self.assertEqual(originals, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(
            b"", subprocess.check_output(["git", "--no-optional-locks", "status", "--porcelain"], cwd=self.root)
        )
        self.data["capabilities"][0]["slices"][0]["tasks"][0]["status"] = "DONE"
        self.write_backlog()
        changed = json.loads(self.request("/api/review/W3")[2])
        self.assertNotEqual(model["fingerprint"], changed["fingerprint"])
        self.assertEqual("DONE", next(item for item in changed["entities"] if item["kind"] == "task")["status"])
        self.assertFalse((self.root / "planning/review-site").exists())

    def test_routes_assets_head_unknown_sources_and_no_directory_browsing(self) -> None:
        for route in ("/", "/waves/W3.html", "/CAP-06/index.html", "/CAP-06/CAP-06.S01.T01.html"):
            with self.subTest(route=route):
                status, headers, body = self.request(route)
                self.assertEqual(200, status)
                self.assertEqual((ASSETS / "index.html").read_bytes(), body)
                head_status, head_headers, head_body = self.request(route, "HEAD")
                self.assertEqual(200, head_status)
                self.assertEqual(headers["Content-Length"], head_headers["Content-Length"])
                self.assertEqual(b"", head_body)
        for route in (
            "/planning/backlog.yaml",
            "/.git/config",
            "/../planning/backlog.yaml",
            "/%2e%2e/private",
            "/assets/../plan_review_server.py",
            "/api/review/W99",
            "/waves/W99.html",
            "/api/review?path=.git/config",
        ):
            with self.subTest(route=route):
                self.assertEqual(404, self.request(route)[0])
        status, _, asset = self.request("/assets/live-review.js")
        self.assertEqual(200, status)
        self.assertEqual(hashlib.sha256((ASSETS / "review.js").read_bytes()).digest(), hashlib.sha256(asset).digest())

    def test_mutations_and_cross_origin_or_host_requests_are_denied(self) -> None:
        original = (self.root / "planning/backlog.yaml").read_bytes()
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"):
            with self.subTest(method=method):
                status, headers, _ = self.request("/api/review", method)
                self.assertEqual(405, status)
                self.assertEqual("GET, HEAD", headers["Allow"])
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Origin": "null"}):
            with self.subTest(headers=headers):
                self.assertEqual(403, self.request("/api/review", headers=headers)[0])
        self.assertEqual(original, (self.root / "planning/backlog.yaml").read_bytes())

    def test_invalid_changed_source_never_returns_previous_success(self) -> None:
        self.assertEqual(200, self.request("/api/review")[0])
        (self.root / "planning/backlog.yaml").write_text("waves: [broken", encoding="utf-8")
        status, _, body = self.request("/api/review")
        self.assertEqual(503, status)
        self.assertNotIn(str(self.root), body.decode())
        self.assertNotIn("entities", json.loads(body))
        self.write_backlog()
        self.assertEqual(200, self.request("/api/review")[0])

    def test_source_drift_and_duplicate_plan_fail_closed(self) -> None:
        projection = Projection(self.root)
        read = projection._read
        calls = 0

        def drift(relative: str) -> bytes:
            nonlocal calls
            result = read(relative)
            if relative == "planning/backlog.yaml":
                calls += 1
                if calls == 2:
                    return result + b"\n"
            return result

        with patch.object(projection, "_read", side_effect=drift), self.assertRaises(SourceChanged):
            projection.read("W3")
        duplicate = self.slice.with_name("CAP-06.S01-duplicate.md")
        duplicate.write_bytes(self.slice.read_bytes())
        self.assertEqual(503, self.request("/api/review/CAP-06.S01")[0])

    def test_plan_identity_mismatch_is_not_displayed_as_a_valid_plan(self) -> None:
        self.cap.write_text("---\ncapability_id: CAP-99\n---\nWrong plan\n", encoding="utf-8")
        self.assertEqual(503, self.request("/api/review/CAP-06")[0])

    def test_gate_conditions_and_legacy_amendment_identity_remain_visible(self) -> None:
        self.data["wave_amendments"] = [{"id": "W1.A01", "lifecycle": {"status": "ADOPTED"}}]
        self.write_backlog()
        gate = json.loads(self.request("/api/review/G3")[2])["selected"]
        self.assertEqual("Evidence workbench", gate["name"])
        self.assertEqual(["Fresh full qualification"], gate["criteria"])
        self.assertEqual(["W4"], gate["unlocks_waves"])
        self.assertEqual(200, self.request("/amendments/W1.A01.html")[0])
        slice_ = json.loads(self.request("/api/review/CAP-06.S01")[2])["selected"]
        self.assertEqual("Traceable lexical retrieval", slice_["outcome"])
        self.assertEqual(["CAP-05.S01"], slice_["depends_on"])

    def test_mid_projection_plan_creation_and_duplicate_inventory_are_denied(self) -> None:
        original_read = self.server.projection._read
        created = False

        def add_duplicate(relative: str) -> bytes:
            nonlocal created
            raw = original_read(relative)
            if relative.endswith("CAP-06.S01-lexical.md") and not created:
                created = True
                self.slice.with_name("CAP-06.S01-new-duplicate.md").write_bytes(raw)
            return raw

        with patch.object(self.server.projection, "_read", side_effect=add_duplicate):
            self.assertEqual(503, self.request("/api/review/CAP-06.S01")[0])
        cap_bytes = self.cap.read_bytes()
        self.cap.unlink()
        calls = 0

        def create_missing(relative: str) -> bytes:
            nonlocal calls
            raw = original_read(relative)
            if relative == "planning/backlog.yaml":
                calls += 1
                if calls == 2:
                    self.cap.write_bytes(cap_bytes)
            return raw

        with patch.object(self.server.projection, "_read", side_effect=create_missing):
            self.assertEqual(503, self.request("/api/review/CAP-06")[0])

    def test_invalid_numeric_alias_and_byte_bounds_return_no_stale_view(self) -> None:
        self.assertEqual(200, self.request("/api/review")[0])
        for text in (
            "waves: [{id: W3, title: .nan}]\ncapabilities: []\n",
            "waves: &w [{id: W3, title: *w}]\ncapabilities: []\n",
            "waves: [{id: W3, campaign: [invalid]}]\ncapabilities: []\n",
        ):
            with self.subTest(text=text):
                (self.root / "planning/backlog.yaml").write_text(text, encoding="utf-8")
                self.assertEqual(503, self.request("/api/review")[0])
        self.write_backlog()
        with patch.object(server_module, "MAX_SOURCE_BYTES", 32):
            self.assertEqual(503, self.request("/api/review")[0])
        with patch.object(server_module, "MAX_RESPONSE_BYTES", 32):
            self.assertEqual(503, self.request("/api/review")[0])

    def test_asset_drift_denies_until_restart_and_linked_assets_cannot_start(self) -> None:
        script = self.assets / "review.js"
        original = script.read_bytes()
        script.write_bytes(original + b"\n// changed during running server\n")
        self.assertEqual(503, self.request("/api/review")[0])
        script.write_bytes(original)
        self.assertEqual(200, self.request("/api/review")[0])
        private = self.root / "private-asset.txt"
        private.write_text("synthetic PRIVATE-ASSET", encoding="utf-8")
        script.unlink()
        try:
            script.symlink_to(private)
        except OSError as error:
            self.skipTest(f"Actual symbolic-link creation authority unavailable: {type(error).__name__}")
        with self.assertRaisesRegex(ValueError, "Linked review"):
            ReviewServer(self.root, 0, assets=self.assets)

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_actual_windows_junction_cannot_supply_review_assets(self) -> None:
        outside = self.root / "outside-assets"
        shutil.copytree(self.assets, outside)
        linked = self.root / "linked-assets"
        environment = dict(os.environ, RO_TEST_LINK=str(linked), RO_TEST_TARGET=str(outside))
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "New-Item -ItemType Junction -Path $env:RO_TEST_LINK "
                "-Target $env:RO_TEST_TARGET -ErrorAction Stop | Out-Null",
            ],
            env=environment,
            capture_output=True,
            check=True,
        )
        try:
            self.assertTrue(os.path.isjunction(linked))
            with self.assertRaisesRegex(ValueError, "Linked review"):
                ReviewServer(self.root, 0, assets=linked)
        finally:
            os.rmdir(linked)
        self.assertTrue((outside / "index.html").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
