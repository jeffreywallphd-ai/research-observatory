"""Generated clients validate actual version history and reject forged responses."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.reconciliation import test_version_repository as fixtures


class VersionClientTests(unittest.TestCase):
    def test_generated_client_binds_versions_preferences_and_status_to_commands(self):
        f = fixtures.VersionRepositoryTests(methodName="runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        target = f.register(f.f.a.assertion_revision_id, "version-of-record")
        notice = f.register(f.f.b.assertion_revision_id, "retraction")
        preferred_plan = f.plan("prefer", work_ids=(f.f.a.work_id,), version=target)
        preferred_command = f.command(preferred_plan)
        f.commit(preferred_command)
        context = f.context()
        plan = f.plan("relate", relation=f.relation(notice, target, kind="retracts"))
        preview = f.repo.preview_versions(plan, actor=f.actor, resolve=f.resolve)
        command = f.command(plan)
        outcome = f.commit(command)
        updated = f.context()
        page = f.repo.version_works(after=None, limit=32, resolve=f.resolve)
        values = dict(
            context=context, plan=plan, preview=preview, command=command, outcome=outcome, updated=updated, page=page
        )
        repo = Path(__file__).resolve().parents[2]
        node = repo / ".local/toolchains/node-v24.19.0-win-x64/node.exe"
        with tempfile.TemporaryDirectory(prefix="version-client-", dir=repo / "artifacts/tmp") as directory:
            path = Path(directory) / "synthetic-values.json"
            path.write_text(
                json.dumps({key: item.model_dump(mode="json", by_alias=True) for key, item in values.items()}),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(node) if node.exists() else shutil.which("node") or "node",
                    str(repo / "tests/reconciliation/verify-version-client.mjs"),
                    str(path),
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "NODE_NO_WARNINGS": "1"},
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Actual version client contracts: PASS", result.stdout)
