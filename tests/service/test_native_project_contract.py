"""Focused actual Windows supervisor/Core project-contract qualification."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import PRODUCT_MANIFEST, PRODUCT_ROOT, product_build_errors, tool_environment  # noqa: E402
from ui_conformance import confined_path, stable_file_bytes  # noqa: E402


def project_probe_build_command(cargo: Path, *, release: bool = False) -> list[str]:
    """Examples need the same Common Controls v6 activation as Tauri's main bin.

    Tauri's resource compiler attaches the production manifest to binary targets,
    not this example. Keep the correction in the example verification build;
    do not broaden production settings, dependencies or privileges.
    """
    return [
        str(cargo),
        "rustc",
        "--message-format=json",
        "--locked",
        "--offline",
        "-p",
        "research-observatory-desktop",
        "--features",
        "integration-harness",
        "--example",
        "project_contract_probe",
        *(["--release"] if release else []),
        "--",
        "-C",
        "link-arg=/MANIFEST:EMBED",
        "-C",
        "link-arg=/MANIFESTUAC:level='asInvoker' uiAccess='false'",
        "-C",
        "link-arg=/MANIFESTDEPENDENCY:type='win32' name='Microsoft.Windows.Common-Controls' "
        "version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'",
    ]


def assert_project_probe_manifest(executable: Path) -> None:
    """Inspect the linked PE, not just the requested linker arguments."""
    import pefile

    with pefile.PE(str(executable)) as image:
        manifests = [
            language.data.struct
            for kind in image.DIRECTORY_ENTRY_RESOURCE.entries
            if kind.id == 24
            for name in kind.directory.entries
            for language in name.directory.entries
        ]
        assert len(manifests) == 1
        resource = manifests[0]
        manifest = ET.fromstring(image.get_data(resource.OffsetToData, resource.Size))
    dependencies = manifest.findall("./{*}dependency/{*}dependentAssembly/{*}assemblyIdentity")
    assert [item.attrib for item in dependencies] == [
        {
            "type": "win32",
            "name": "Microsoft.Windows.Common-Controls",
            "version": "6.0.0.0",
            "processorArchitecture": "*",
            "publicKeyToken": "6595b64144ccf1df",
            "language": "*",
        }
    ]
    levels = manifest.findall(".//{*}requestedExecutionLevel")
    assert len(levels) == 1 and levels[0].attrib == {"level": "asInvoker", "uiAccess": "false"}


def project_probe_input_hashes() -> dict[str, str]:
    """Validate the frontend before trusting its exact source/artifact inventory."""
    manifest_path = confined_path(REPO, PRODUCT_MANIFEST)
    manifest_bytes = stable_file_bytes(REPO, manifest_path)
    errors = product_build_errors(REPO)
    assert not errors, "Invalid desktop product build: " + "; ".join(errors)
    assert stable_file_bytes(REPO, manifest_path) == manifest_bytes, (
        "Desktop product manifest changed during validation"
    )
    manifest = json.loads(manifest_bytes)
    product_inputs = {
        **manifest["sourceFiles"],
        **{f"{PRODUCT_ROOT}/{name}": digest for name, digest in manifest["artifacts"].items()},
    }
    inputs = subprocess.check_output(
        ["git", "ls-files", "--", "Cargo.toml", "Cargo.lock", "apps/desktop/src-tauri"],
        cwd=REPO,
        text=True,
        encoding="utf-8",
    ).splitlines()
    inputs += [
        "apps/desktop/src-tauri/src/directory_picker.rs",  # Also bind pre-commit characterization.
        "tests/service/test_native_project_contract.py",
        "tools/desktop_app_check.py",
        "tools/ui_conformance.py",
        "design/ui-reference/SITE_MANIFEST.json",
        PRODUCT_MANIFEST,
    ]
    observed = {
        name: hashlib.sha256(stable_file_bytes(REPO, confined_path(REPO, name))).hexdigest()
        for name in sorted(set(inputs) | product_inputs.keys())
    }
    assert all(observed[name] == digest for name, digest in product_inputs.items()), (
        "Desktop product inputs changed after validation"
    )
    assert observed[PRODUCT_MANIFEST] == hashlib.sha256(manifest_bytes).hexdigest(), (
        "Desktop product manifest changed after validation"
    )
    return observed


def build_project_probe(*, release: bool = False) -> dict:
    """Bind validated native, renderer and artifact bytes across actual linking."""
    before = project_probe_input_hashes()
    environment, _, cargo = tool_environment(REPO)
    command = project_probe_build_command(cargo, release=release)
    result = subprocess.run(
        command, cwd=REPO, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=180
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    assert before == project_probe_input_hashes(), (
        "Native implementation or product build inputs changed while compiling"
    )
    profile = "release" if release else "debug"
    executable = REPO / f"target/{profile}/examples/project_contract_probe.exe"
    # An inherited Cargo target override must not cause us to attest an older
    # binary at the usual path. Bind Cargo's actual compiler-artifact event.
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    linked = [
        event.get("executable")
        for event in events
        if event.get("reason") == "compiler-artifact"
        and event.get("target", {}).get("name") == "project_contract_probe"
        and event.get("target", {}).get("kind") == ["example"]
    ]
    assert len(linked) == 1 and linked[0] == str(executable), "Cargo did not report the expected probe executable"
    assert_project_probe_manifest(executable)
    return {
        "profile": profile,
        "argv": ["{cargo}", *command[1:]],
        "inputSha256": before,
        "executableSha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "embeddedCommonControls6AsInvokerVerified": True,
        "executablePathConfirmedByCargo": True,
    }


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
        cls.environment, _, _ = tool_environment(REPO)
        native_inputs = subprocess.check_output(
            [
                "git",
                "ls-files",
                "--",
                "Cargo.toml",
                "Cargo.lock",
                "apps/desktop/src-tauri",
            ],
            cwd=REPO,
            text=True,
            encoding="utf-8",
        ).splitlines()

        def hashes() -> dict[str, str]:
            return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in native_inputs}

        before = hashes()
        cls.build_binding = build_project_probe()
        if before != hashes():
            raise AssertionError("Native inputs changed while Cargo was building the probe.")
        cls.environment = {**cls.environment, "RO_PROJECT_PROBE_BUILD_INPUTS": json.dumps(before)}

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
                [str(REPO / "target/debug/examples/project_contract_probe.exe"), "--check-packaged-path", candidate],
                cwd=REPO,
                env=self.environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
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
        print(
            json.dumps(
                {
                    "packagedPath": {
                        "plainAndVerbatim": "accepted",
                        "junctionRedirects": "denied",
                        "symbolicLinks": symbolic_result,
                    },
                    "fixtureDirectory": fixture.relative_to(REPO).as_posix(),
                    "fixturesRetained": True,
                },
                sort_keys=True,
            )
        )

    def test_generated_requests_reach_actual_native_and_protected_core(self) -> None:
        result = subprocess.run(
            [
                str(REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe"),
                str(REPO / "artifacts/evidence/W1.A09.T02.native-check-01.mjs"),
            ],
            cwd=REPO,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertGreater(report["outcomes"]["retainedLineageNodes"], 1)
        self.assertTrue(report["outcomes"]["restartPreservedIntentWorkflowAndLineage"])
        self.assertTrue(report["outcomes"]["readRetryCreatedNothing"])
        print(json.dumps(report, sort_keys=True))

    def test_probe_rejects_missing_or_substituted_build_binding_before_launch(self) -> None:
        fixture_parent = REPO / "artifacts/tmp"
        before = {path.name for path in fixture_parent.glob("project-native-contract-*")}
        substituted = json.loads(self.environment["RO_PROJECT_PROBE_BUILD_INPUTS"])
        substituted["apps/desktop/src-tauri/src/supervisor.rs"] = "0" * 64
        for binding in ("null", json.dumps(substituted)):
            with self.subTest(binding="missing" if binding == "null" else "substituted"):
                result = subprocess.run(
                    [
                        str(REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe"),
                        str(REPO / "artifacts/evidence/W1.A09.T02.native-check-01.mjs"),
                    ],
                    cwd=REPO,
                    env={**self.environment, "RO_PROJECT_PROBE_BUILD_INPUTS": binding},
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=45,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn("native input hashes must match the successful Cargo build interval", result.stderr)
                self.assertEqual("", result.stdout)
        self.assertEqual(before, {path.name for path in fixture_parent.glob("project-native-contract-*")})


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--seed-lineage":
        seed_canonical_lineage(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
