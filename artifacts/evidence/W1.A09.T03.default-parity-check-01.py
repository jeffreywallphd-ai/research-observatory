"""Read-only dev/release default resolution; no Core startup or vault access."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests/service"))
from test_native_project_contract import project_probe_input_hashes  # noqa: E402


def main() -> None:
    helper = REPO / "artifacts/evidence/W1.A09.T03.default-core-check-01.py"
    own_before = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    helper_before = hashlib.sha256(helper.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("default_check", helper)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    from research_observatory_core.windows_credentials import default_windows_profile_vault_path

    record_name = "artifacts/evidence/W1.A09.T03.native-builds-05.json"
    record_bytes = (REPO / record_name).read_bytes()
    builds = json.loads(record_bytes)["builds"]
    before = project_probe_input_hashes()
    assert [build["profile"] for build in builds] == ["debug", "release"]
    assert all(build["inputSha256"] == before for build in builds)
    parent = default_windows_profile_vault_path().parent.parent
    runner.plain_directory(parent)
    initial = parent.stat()
    outcomes = []
    for build in builds:
        profile = build["profile"]
        result = runner.run_native_resolver(REPO / f"target/{profile}/examples/project_contract_probe.exe", build)
        assert result["kind"] == "actual-default-parent"
        assert result["readOnly"] is True and result["fixtureSubstitution"] is False
        assert result["debugAssertions"] == (profile == "debug")
        assert result["outcome"]["status"] == "available" and Path(result["outcome"]["path"]) == parent
        outcomes.append(
            {"profile": profile, "matchesActualShellCoreParent": True, "executableSha256": build["executableSha256"]}
        )
    runner.plain_directory(parent)
    final = parent.stat()
    assert (initial.st_dev, initial.st_ino, initial.st_mtime_ns) == (final.st_dev, final.st_ino, final.st_mtime_ns)
    assert before == project_probe_input_hashes()
    assert (REPO / record_name).read_bytes() == record_bytes
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == own_before
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == helper_before
    print(
        json.dumps(
            {
                "taskId": "W1.A09.T03",
                "status": "PASS_WITHIN_READ_ONLY_SCOPE",
                "buildRecord": record_name,
                "buildRecordSha256": hashlib.sha256(record_bytes).hexdigest(),
                "runnerSha256": own_before,
                "helperSha256": helper_before,
                "outcomes": outcomes,
                "inputsUnchanged": True,
                "parentIdentityAndMtimeUnchanged": True,
                "scope": "Real debug/release native Shell default resolver only. No project creation, Core startup, "
                "vault/policy access or authentication proof.",
            }
        )
    )


if __name__ == "__main__":
    main()
