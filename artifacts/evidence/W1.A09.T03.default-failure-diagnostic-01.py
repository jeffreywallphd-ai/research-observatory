"""Path-free diagnostic of unchanged Core creation at the actual Shell default.

One synthetic UUID target and an isolated retained vault; no native build/UI or
normal account-vault access. A failure is an adverse observation, never a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "t03_default_diagnostic", REPO / "artifacts/evidence/W1.A09.T03.default-core-check-01.py"
)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, choices=range(1, 10), required=True)
    args = parser.parse_args()
    report = REPO / f"artifacts/evidence/W1.A09.T03.default-failure-diagnostic-{args.attempt:02d}.json"
    assert not report.exists()
    inputs = subprocess.check_output(
        ["git", "ls-files", "--", "services/core-api/src"], cwd=REPO, text=True, encoding="utf-8"
    ).splitlines()
    inputs += [
        "artifacts/evidence/W1.A09.T03.default-core-check-01.py",
        "artifacts/evidence/W1.A09.T03.default-failure-diagnostic-01.py",
        "artifacts/evidence/W1.A09.T03.runtime-principal-check-01.py",
    ]

    def hashes() -> dict[str, str]:
        return {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in inputs}

    before = hashes()
    with runner.DirectoryPins() as pins:
        pins.pin_chain(runner.REPORTS)
        pins.pin_chain(runner.TEMP)
        root = Path(tempfile.mkdtemp(prefix="directory-default-diagnostic-", dir=runner.TEMP))
        core = runner.ActualCore(root, pins)
        outcomes = {}
        phase = "startup"
        failed = False
        try:
            core.ready()
            phase = "fresh-create"
            product = root / "Research Observatory"
            outcomes["fresh"] = runner.create_reopen_collision(core, product, "fresh-control")
            from research_observatory_core.windows_credentials import default_windows_profile_vault_path

            actual = default_windows_profile_vault_path().parent.parent
            core.pin_chain_or_stop(actual)
            child = "t03-default-proof-" + uuid.uuid4().hex
            with (root / "retained-project-association.json").open("x", encoding="utf-8") as association:
                json.dump({"project": str(actual / child), "vault": str(product / "security/profile-default"),
                           "synthetic": True, "notAnOrdinaryProductionProject": True}, association)
            phase = "actual-default-create"
            outcomes["actualDefault"] = runner.create_reopen_collision(core, actual, child)
        except AssertionError:
            failed = True  # Never publish exception text, arguments or account paths.
        finally:
            core.stop()
        stable = hashes() == before
        payload = {
            "status": "FAIL" if failed or not stable else "PASS_WITHIN_DIAGNOSTIC_SCOPE",
            "phase": phase, "sourceHashes": before, "inputsUnchanged": stable,
            "fixture": root.relative_to(REPO).as_posix(), "fixturesRetained": True,
            "outcomes": outcomes, "diagnostics": core.diagnostics,
            "scope": "Unchanged Core/DPAPI/SQLCipher with fixture vault/temp and one UUID actual-default target. "
                     "No native/renderer/packaging or authentication proof. No ordinary user vault/policy access.",
        }
        pins.revalidate()
        with report.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
    print(json.dumps({key: value for key, value in payload.items() if key != "sourceHashes"}))
    return int(failed or not stable)


if __name__ == "__main__":
    raise SystemExit(main())
