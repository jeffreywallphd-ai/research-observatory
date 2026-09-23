"""Opt-in frozen Core import journey; creates only synthetic project vault keys.

Requires explicit user authorization before invocation. No test-vault substitution,
native UI, signing, performance or crash-recovery claim. Package report/hash and
its independently reviewed source commit are explicit local environment inputs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from build_manifest import guarded_atomic_write_json
from core_sidecar_build import load_build_contract, verify_artifact
from core_sidecar_performance_check import immutable_package_snapshot, read_line, validate_handshake

REPO = Path(__file__).resolve().parents[2]
PRODUCT_PATHS = ("services/core-api", "packages/contracts", "pyproject.toml", "uv.lock")
SOURCE = b"title,doi\nSynthetic frozen A,10.99999/frozen-a\nSynthetic frozen B,10.99999/frozen-b\n"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=REPO, text=True, encoding="utf-8").strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class HttpCore:
    def __init__(self, port, token):
        self.port, self.token = port, token

    def post(self, route, body, expected=200):
        return self.request(route, body, expected=expected)

    def request(self, route, body=None, *, expected=200, timeout=15):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{route}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response as response:
            if response.status != expected:
                raise AssertionError(f"{route}: HTTP {response.status}, expected {expected}")
            content = response.read(900_001)
            if len(content) > 900_000:
                raise AssertionError("bounded response exceeded")
        return json.loads(content)

    def ready(self, handshake):
        try:
            value = self.request("/readyz", timeout=0.5)
        except OSError, ValueError, AssertionError:
            return False
        return value == {
            "schemaVersion": "1.0",
            "service": "research-observatory-core",
            "version": handshake["buildId"],
            "state": "ready",
            "capabilities": handshake["capabilities"],
            "ready": True,
        }

    def wait(self, route, body):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = self.post(route, body)
            if value["jobState"] == "succeeded":
                return value
            if value["jobState"] in {"failed", "cancelled"}:
                raise AssertionError(f"{route}: terminal {value['jobState']}")
            time.sleep(0.05)
        raise AssertionError("small synthetic job observation timed out")


@contextmanager
def supervised(executable, fixture, phase, epoch):
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    environment.update(
        TEMP=str(fixture / "temp"),
        TMP=str(fixture / "temp"),
        PATH=str(Path(os.environ["SYSTEMROOT"]) / "System32"),
        RO_CORE_PROFILE="local",
        RO_CORE_BIND_HOST="127.0.0.1",
        RO_CORE_BIND_PORT="0",
        RO_CORE_LOG_LEVEL="INFO",
    )
    with (fixture / f"{phase}.stderr.log").open("wb") as error_log:
        process = subprocess.Popen(
            [str(executable), "--supervised"],
            cwd=fixture,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=error_log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            token = secrets.token_hex(32)
            process.stdin.write(f"auth {token} workflow {epoch} {secrets.token_hex(16)}\n".encode())
            process.stdin.flush()
            raw = read_line(process.stdout, 10)
            if len(raw) > 4096 or not raw.endswith(b"\n"):
                raise AssertionError("invalid bounded handshake")
            handshake = json.loads(raw)
            port = validate_handshake(handshake, process.pid)
            client = HttpCore(port, token)
            deadline = time.monotonic() + 10
            while not client.ready(handshake):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise AssertionError("frozen Core unavailable")
                time.sleep(0.05)
            yield client
            process.stdin.write(b"shutdown\n")
            process.stdin.flush()
            process.wait(timeout=5)
            if process.returncode != 0:
                raise AssertionError("frozen Core shutdown failed")
        finally:
            if process.poll() is None:
                process.kill()  # Exact child owned by this invocation only.
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout):
                stream.close()


def intake(client, project):
    native = {**project, **client.post("/native/imports/context", project)}
    permitted = {"value": "permitted", "basis": "researcher-confirmed"}
    preview = client.post(
        "/native/imports/create",
        {
            **native,
            "sourceName": "synthetic-frozen.csv",
            "formatName": "csv",
            "encoding": "utf-8",
            "delimiter": ",",
            "rights": {"store": permitted, "inspect": permitted},
        },
    )
    native["previewId"] = preview["previewId"]
    public = {"root": project["root"], "previewId": preview["previewId"]}
    client.post("/native/imports/chunk", {**native, "ordinal": 1, "data": base64.b64encode(SOURCE).decode()})
    client.post(
        "/native/imports/seal",
        {
            **native,
            "sourceSha256": hashlib.sha256(SOURCE).hexdigest(),
            "byteLength": len(SOURCE),
            "chunkCount": 1,
        },
    )
    client.post("/native/imports/schedule", native)
    client.wait("/projects/imports/status", public)
    draft = client.post("/projects/imports/begin-review", public)
    if draft["recordCount"] != 3:
        raise AssertionError("incomplete synthetic preview")
    return public, draft


def commit(client, public, draft):
    prepared = client.post("/projects/imports/commit/prepare", {**public, "revision": draft["revision"]})
    request = {**public, "revision": draft["revision"], "requestId": prepared["requestId"]}
    client.post("/projects/imports/commit/start", request)
    return client.wait("/projects/imports/commit/status", {**public, "requestId": prepared["requestId"]})["manifest"]


def manifest_address(project, manifest):
    if manifest["projectId"] != project["projectId"]:
        raise AssertionError("manifest belongs to another project")
    return {"root": project["root"], "previewId": manifest["previewId"], "revisionId": manifest["revisionId"]}


def canonical_counts(project):
    """Read only this invocation's created database; never enumerate vault records."""
    from research_observatory_core.storage import configure_protected_database_provider, open_canonical_database
    from research_observatory_core.windows_credentials import create_windows_database_key_provider

    path = Path(project["root"]) / "state/project.sqlite3"
    with path.open("rb") as source:
        if source.read(16) == b"SQLite format 3\x00":
            raise AssertionError("synthetic database is not protected")
    configure_protected_database_provider(create_windows_database_key_provider())
    database = open_canonical_database(path, expected_project_id=project["projectId"])
    try:
        return {
            table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "import_source_records",
                "import_manifests",
                "import_manifest_members",
                "import_manifest_seals",
            )
        }
    finally:
        database.close()


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("RO_RUN_IMPORT_FROZEN") == "1",
    "opt-in frozen test requires explicit synthetic-key authority and authenticated package",
)
class ImportFrozenWindowsTests(unittest.TestCase):
    def test_frozen_import_reimport_cancel_and_restart(self):
        head = git("rev-parse", "HEAD")
        self.assertEqual("", git("status", "--porcelain"), "commit inputs before qualification")
        product_commit = os.environ["RO_IMPORT_PRODUCT_COMMIT"]
        subprocess.run(["git", "merge-base", "--is-ancestor", product_commit, head], cwd=REPO, check=True)
        self.assertEqual("", git("diff", product_commit, head, "--", *PRODUCT_PATHS))
        package_report = Path(os.environ["RO_IMPORT_PACKAGE_REPORT"])
        self.assertEqual(package_report.absolute(), package_report.resolve(strict=True))
        report_sha = digest(package_report)
        self.assertEqual(os.environ["RO_IMPORT_PACKAGE_REPORT_SHA256"], report_sha)
        package = json.loads(package_report.read_text(encoding="utf-8"))
        # The build report resides at <producer repo>/artifacts/tmp/report.json.
        producer_repo = package_report.parents[2]
        root = producer_repo / package["artifact"]
        scratch = producer_repo / "artifacts/tmp"
        self.assertTrue(root.resolve(strict=True).is_relative_to(scratch.resolve(strict=True)))
        self.assertEqual(root.absolute(), root.resolve(strict=True))
        manifest = package["manifest"]
        schema = json.loads((REPO / "packages/contracts/core-api/sidecar-artifact.schema.json").read_text())
        contract = load_build_contract(REPO)
        self.assertEqual([], verify_artifact(root, manifest, schema=schema, contract=contract))
        output_root = REPO / "artifacts/tmp"
        self.assertEqual(output_root.absolute(), output_root.resolve(strict=True))
        fixture = Path(tempfile.mkdtemp(prefix="import-frozen-windows-", dir=output_root))
        (fixture / "temp").mkdir()
        (fixture / "projects").mkdir()
        report = {
            "outcome": "running",
            "head": head,
            "productCommit": product_commit,
            "toolSha256": digest(Path(__file__)),
            "packageReportSha256": report_sha,
            "entrypointSha256": digest(root / manifest["entrypoint"]),
            "fixture": fixture.relative_to(REPO).as_posix(),
            "fixturesRetained": True,
            "scope": "frozen Core, real loopback HTTP/control pipe, protected storage and workers",
            "limitations": [
                "synthetic supervisor, not native app",
                "not signing or performance proof",
                "not crash recovery",
            ],
        }

        def save():
            guarded_atomic_write_json(REPO, fixture / "result.json", report, output_root)

        save()
        try:
            # Match the existing package benchmark's disposable-copy boundary.
            # Never apply temporary immutability permissions to the build output.
            snapshot_parent = Path(tempfile.mkdtemp(prefix="import-frozen-package-", dir=scratch))
            snapshot_root = snapshot_parent / "package"
            shutil.copytree(root, snapshot_root)
            report["packageSnapshot"] = snapshot_parent.relative_to(producer_repo).as_posix()
            save()
            epoch = secrets.token_hex(16)
            with immutable_package_snapshot(producer_repo, snapshot_root, manifest):
                self.assertEqual([], verify_artifact(snapshot_root, manifest, schema=schema, contract=contract))
                with supervised(snapshot_root / manifest["entrypoint"], fixture, "create", epoch) as client:
                    created = client.post(
                        "/projects",
                        {
                            "parentDirectory": str(fixture / "projects"),
                            "directoryName": "synthetic-frozen",
                            "displayName": "Synthetic frozen qualification",
                            "primaryUseCase": "theory-synthesis",
                            "researchObjective": "Synthetic frozen import qualification",
                        },
                    )
                    project = {key: created[key] for key in ("root", "projectId")}
                    self.assertEqual(fixture / "projects/synthetic-frozen", Path(project["root"]))
                    client.post("/projects/open", {"root": project["root"]})
                    cancelled, _ = intake(client, project)
                    self.assertIsNone(client.post("/projects/imports/commit/latest", cancelled))
                    client.post("/projects/imports/cancel", cancelled)
                    self.assertEqual("cancelled", client.post("/projects/imports/status", cancelled)["state"])
                    denied = client.post("/projects/imports/commit/latest", cancelled, expected=409)
                    self.assertEqual("RO-CORE-IMPORT-REVIEW-UNAVAILABLE", denied["code"])
                    report["afterCancellation"] = canonical_counts(project)
                    self.assertTrue(all(value == 0 for value in report["afterCancellation"].values()))
                    public, draft = intake(client, project)
                    summary_address = {**public, "revision": draft["revision"]}
                    client.post("/projects/imports/summary/start", summary_address)
                    summary = client.wait("/projects/imports/summary", summary_address)
                    self.assertEqual(2, summary["counts"]["includedRecords"])
                    self.assertEqual(3, summary["counts"]["sourceRows"])
                    diagnostic = client.post("/projects/imports/report", {**summary_address, "after": 0, "limit": 100})
                    self.assertTrue(diagnostic["complete"])
                    self.assertNotIn("Synthetic frozen", diagnostic["csv"])
                    self.assertNotIn("10.99999/", diagnostic["csv"])
                    self.assertNotIn(project["root"], diagnostic["csv"])
                    first = commit(client, public, draft)
                    self.assertEqual((2, 2, 3), (first["createdCount"], first["selectedCount"], first["recordCount"]))
                    again, second_draft = intake(client, project)
                    second = commit(client, again, second_draft)
                    self.assertEqual(first, second, "identical reimport must reuse the original manifest")
                    client.post("/projects/close", {"root": project["root"]})
                self.assertEqual([], verify_artifact(snapshot_root, manifest, schema=schema, contract=contract))
                with supervised(snapshot_root / manifest["entrypoint"], fixture, "reopen", epoch) as client:
                    client.post("/projects/open", {"root": project["root"]})
                    self.assertEqual(first, client.post("/projects/imports/commit/latest", again)["manifest"])
                    members = client.post(
                        "/projects/imports/manifest/members",
                        {
                            **manifest_address(project, first),
                            "after": 0,
                            "limit": 100,
                        },
                    )
                    self.assertTrue(members["complete"])
                    self.assertEqual([1, 2, 3], [row["ordinal"] for row in members["records"]])
                    self.assertEqual([False, True, True], [row["included"] for row in members["records"]])
                    self.assertEqual(
                        2, len({row["sourceRecordRevisionId"] for row in members["records"] if row["included"]})
                    )
                    self.assertTrue(all(row["comparison"] == "not-compared" for row in members["records"]))
                    review = client.post("/projects/imports/review", again)
                    self.assertEqual("permitted", review["rights"]["inspect"]["value"])
                    self.assertEqual("unknown", review["rights"]["export"]["value"])
                    client.post("/projects/close", {"root": project["root"]})
                self.assertEqual([], verify_artifact(snapshot_root, manifest, schema=schema, contract=contract))
            self.assertEqual([], verify_artifact(root, manifest, schema=schema, contract=contract))
            report["afterReimportAndRestart"] = canonical_counts(project)
            self.assertEqual(
                {
                    "import_source_records": 2,
                    "import_manifests": 1,
                    "import_manifest_members": 3,
                    "import_manifest_seals": 1,
                },
                report["afterReimportAndRestart"],
            )
            self.assertEqual(head, git("rev-parse", "HEAD"))
            self.assertEqual("", git("status", "--porcelain"))
            self.assertEqual(report_sha, digest(package_report))
            report.update(
                outcome="passed",
                manifest=first,
                members=members,
                rights=review["rights"],
                processes=2,
                summaryCounts=summary["counts"],
                diagnosticSha256=hashlib.sha256(diagnostic["csv"].encode()).hexdigest(),
            )
        except BaseException as error:
            report.update(outcome="failed", failureType=type(error).__name__)
            raise
        finally:
            save()
            print(
                json.dumps(
                    {"report": (fixture / "result.json").relative_to(REPO).as_posix(), "outcome": report["outcome"]}
                )
            )


class FrozenJourneyControlTests(unittest.TestCase):
    def test_count_audit_is_project_scoped_and_closes_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state").mkdir()
            (root / "state/project.sqlite3").write_bytes(b"synthetic ciphertext")
            database = Mock()
            database.execute.side_effect = RuntimeError("synthetic read failure")
            with (
                patch("research_observatory_core.windows_credentials.create_windows_database_key_provider"),
                patch("research_observatory_core.storage.configure_protected_database_provider"),
                patch("research_observatory_core.storage.open_canonical_database", return_value=database) as opened,
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic read failure"):
                    canonical_counts({"root": str(root), "projectId": "synthetic-project"})
                opened.assert_called_once_with(root / "state/project.sqlite3", expected_project_id="synthetic-project")
                database.execute.assert_called_once_with("SELECT COUNT(*) FROM import_source_records")
                database.close.assert_called_once_with()

    def test_reimport_manifest_uses_accepted_preview_authority(self):
        project = {"root": "synthetic", "projectId": "project"}
        accepted = {"projectId": "project", "previewId": "original-preview", "revisionId": "revision"}
        self.assertEqual(
            {"root": "synthetic", "previewId": "original-preview", "revisionId": "revision"},
            manifest_address(project, accepted),
        )
        with self.assertRaisesRegex(AssertionError, "another project"):
            manifest_address(project, {**accepted, "projectId": "other"})

    def test_readiness_uses_private_transport_and_exact_payload(self):
        client = HttpCore(12345, "synthetic")
        handshake = {"buildId": "0.1.0", "capabilities": ["synthetic-capability"]}
        expected = {
            "schemaVersion": "1.0",
            "service": "research-observatory-core",
            "version": "0.1.0",
            "state": "ready",
            "capabilities": ["synthetic-capability"],
            "ready": True,
        }
        with patch("urllib.request.build_opener") as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = json.dumps(expected).encode()
            self.assertTrue(client.ready(handshake))
            proxy, redirects = build.call_args.args
            self.assertEqual({}, proxy.proxies)
            self.assertIsInstance(redirects, NoRedirect)
            request = build.return_value.open.call_args.args[0]
            self.assertEqual("GET", request.get_method())
            self.assertEqual("http://127.0.0.1:12345/readyz", request.full_url)
            response.read.return_value = json.dumps({**expected, "ready": False}).encode()
            self.assertFalse(client.ready(handshake))

    def test_redirects_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_failed_job_is_not_accepted_or_retried(self):
        client = HttpCore(1, "synthetic")
        with patch.object(client, "post", return_value={"jobState": "failed"}) as post:
            with self.assertRaisesRegex(AssertionError, "terminal failed"):
                client.wait("/projects/imports/status", {})
            self.assertEqual(1, post.call_count)

    def test_reimport_uses_explicit_prepare_identity(self):
        client = HttpCore(1, "synthetic")
        with (
            patch.object(client, "post", side_effect=[{"requestId": "prepared"}, {}]) as post,
            patch.object(client, "wait", return_value={"manifest": {"revisionId": "accepted"}}),
        ):
            self.assertEqual({"revisionId": "accepted"}, commit(client, {"previewId": "preview"}, {"revision": 4}))
            self.assertEqual(
                {"previewId": "preview", "revision": 4, "requestId": "prepared"}, post.call_args_list[1].args[1]
            )
