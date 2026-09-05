"""Focused actual Windows supervisor/Core project-contract qualification."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import tool_environment  # noqa: E402


def seed_canonical_lineage(project_root: str, vault_root: str) -> None:
    """Append synthetic canonical revisions only inside the runner-owned fixture."""
    sys.path.insert(0, str(REPO / "services/core-api/src"))
    from research_observatory_core.projects import ProjectLifecycleService
    from research_observatory_core.repositories import create_sqlite_unit_of_work_factory
    from research_observatory_core.storage import configure_protected_database_provider
    from research_observatory_core.windows_credentials import create_windows_database_key_provider
    from test_provenance import draft, event

    root = Path(project_root).resolve(strict=True)
    vault = Path(vault_root).resolve(strict=True)
    temporary = (REPO / "artifacts/tmp").resolve(strict=True)
    assert root.parent.name == "projects"
    assert root.parent.parent == vault.parent
    assert vault.name == "vault"
    assert vault.parent.parent == temporary
    assert vault.parent.name.startswith("project-native-contract-")
    configure_protected_database_provider(create_windows_database_key_provider(vault))
    projects = ProjectLifecycleService()
    try:
        opened = projects.open(root=str(root), trace_id="b" * 32)
        factory = create_sqlite_unit_of_work_factory(root / "state/project.sqlite3", opened.project_id)
        with factory() as unit:
            first = unit.aggregates.append(draft(1), event(0), expected_revision=None)
            unit.commit()
        with factory() as unit:
            second = unit.aggregates.append(draft(2), event(1), expected_revision=0)
            unit.commit()
        print(json.dumps({"firstRevisionId": first.revision_id, "secondRevisionId": second.revision_id}))
    finally:
        projects.shutdown()


@unittest.skipUnless(os.name == "nt", "Windows x64 native qualification")
class NativeProjectContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.environment, _, cargo = tool_environment(REPO)
        build = subprocess.run(
            [str(cargo), "build", "--locked", "-p", "research-observatory-desktop", "--features",
             "integration-harness", "--example", "project_contract_probe"],
            cwd=REPO, env=cls.environment, capture_output=True, text=True, encoding="utf-8", timeout=180,
        )
        if build.returncode:
            raise AssertionError(build.stderr)

    def test_packaged_path_spelling_does_not_admit_redirected_executable(self) -> None:
        import _winapi

        # Retain these inert fixtures for inspection. The native probe validates
        # their paths only and never executes the synthetic .exe bytes.
        fixture_parent = (REPO / "artifacts/tmp").resolve(strict=True)
        fixture = Path(tempfile.mkdtemp(prefix="project-native-path-", dir=fixture_parent))
        self.assertEqual(fixture_parent, fixture.resolve(strict=True).parent)
        target = fixture / "canonical"
        target.mkdir()
        executable = target / "research-observatory-core-x86_64-pc-windows-msvc.exe"
        executable.write_bytes(b"Synthetic path fixture; never executable.")
        redirect = fixture / "redirect"
        _winapi.CreateJunction(str(target), str(redirect))
        self.assertTrue(redirect.is_junction())

        def check(candidate: str, accepted: bool) -> None:
            result = subprocess.run(
                [str(REPO / "target/debug/examples/project_contract_probe.exe"),
                 "--check-packaged-path", candidate],
                cwd=REPO, env=self.environment, capture_output=True, text=True,
                encoding="utf-8", timeout=15,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                {"accepted": accepted, "code": None if accepted else "RO-CORE-INTEGRITY-FAILED"},
                json.loads(result.stdout),
            )

        check(str(executable), True)
        check("\\\\?\\" + str(executable), True)
        check(str(redirect / executable.name), False)
        check("\\\\?\\" + str(redirect / executable.name), False)

        link_parent = fixture / "symbolic"
        link_parent.mkdir()
        symbolic = link_parent / executable.name
        try:
            symbolic.symlink_to(executable)
        except OSError as error:
            if error.winerror != 1314:
                raise
            symbolic_result = "unavailable: Windows did not grant symbolic-link creation privilege"
        else:
            self.assertTrue(symbolic.is_symlink())
            check(str(symbolic), False)
            check("\\\\?\\" + str(symbolic), False)
            symbolic_result = "denied in plain and verbatim forms"
        print(json.dumps({
            "packagedPath": {"plainAndVerbatim": "accepted", "junctionRedirects": "denied",
                             "symbolicLinks": symbolic_result},
            "fixtureDirectory": fixture.relative_to(REPO).as_posix(), "fixturesRetained": True,
        }, sort_keys=True))

    def test_generated_requests_reach_actual_native_and_protected_core(self) -> None:
        result = subprocess.run(
            [str(REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe"),
             str(REPO / "artifacts/evidence/W1.A09.T02.native-check-01.mjs")],
            cwd=REPO, env=self.environment, capture_output=True, text=True, encoding="utf-8", timeout=180,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertGreater(report["outcomes"]["retainedLineageNodes"], 1)
        self.assertTrue(report["outcomes"]["restartPreservedIntentWorkflowAndLineage"])
        self.assertTrue(report["outcomes"]["readRetryCreatedNothing"])
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--seed-lineage":
        seed_canonical_lineage(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
