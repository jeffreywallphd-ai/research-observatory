"""Collect fresh, bounded activation proof without changing tracked inputs."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYTHON = str(REPO / ".venv/Scripts/python.exe")
BASE = "ca8b1448e094b637bbd06c3129b69a78df792619"
DELIVERY = "8804a66c9acd23ab8e398197fd46654bccfc1a09"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def main() -> None:
    candidate = git("rev-parse", "HEAD")
    if git("status", "--porcelain"):
        raise ValueError("clean committed candidate required")
    prefix = f"artifacts/tmp/W2.A03.T02.final-{candidate[:8]}"
    result_path = REPO / f"{prefix}.json"
    if result_path.exists():
        raise ValueError("retain the prior attempt; use a new reviewed candidate")
    environment = dict(os.environ)
    environment["MYPYPATH"] = "tools"
    records: list[dict] = []

    def run(check_id: str, argv: list[str], expected: int = 0) -> dict:
        if git("rev-parse", "HEAD") != candidate:
            raise ValueError("HEAD drift before check")
        log = f"{prefix}.{check_id}.log"
        start = dt.datetime.now(dt.UTC)
        clock = time.monotonic()
        with (REPO / log).open("xb") as stream:
            process = subprocess.run(argv, cwd=REPO, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        finish = dt.datetime.now(dt.UTC)
        if git("rev-parse", "HEAD") != candidate or git("status", "--porcelain"):
            raise ValueError("candidate changed during check")
        record = {
            "id": check_id,
            "command": subprocess.list2cmdline(argv).replace(PYTHON, ".venv/Scripts/python.exe"),
            "workingDirectory": ".",
            "exitCode": process.returncode,
            "expectedExitCode": expected,
            "commit": candidate,
            "rawOutput": log,
            "rawOutputSha256": hashlib.sha256((REPO / log).read_bytes()).hexdigest(),
            "startedAt": start.isoformat(),
            "finishedAt": finish.isoformat(),
            "durationSeconds": round(time.monotonic() - clock, 3),
            "provenance": "Fresh local execution at fixed clean committed candidate; no cached result.",
        }
        print(json.dumps(record), flush=True)
        return record

    def py(*args: str) -> list[str]:
        return [PYTHON, "-B", *args]

    try:
        records.append(run("build", py("artifacts/evidence/W2.A03.T02.build-pinned.py")))
        if records[-1]["exitCode"]:
            return
        records.append(
            run(
                "product-runtime",
                py(
                    "-m",
                    "unittest",
                    "-v",
                    "tests.desktop.test_desktop_app_check.DesktopAppCheckTests."
                    "test_built_product_exposes_only_implemented_functional_workspaces_and_is_keyboard_accessible",
                ),
            )
        )
        if records[-1]["exitCode"]:
            return
        cases = ["tests.foundation.test_ui_reference_check"] + [
            f"tests.desktop.test_ui_conformance.UiConformanceTests.{name}"
            for name in (
                "test_active_presentation_requires_its_exact_compatibility_witness",
                "test_application_inventory_excludes_only_canonical_root_generated_directories",
                "test_application_mode_requires_a_bound_build_manifest",
                "test_application_inventory_detects_content_type_and_membership_races",
                "test_application_inventory_guard_holds_source_and_output_snapshot_through_completion",
                "test_strict_baseline_and_approval_records_reject_malformed_history_shapes",
                "test_controlled_font_check_rejects_a_missing_face",
                "test_same_reference_baseline_rewrite_requires_new_approval",
                "test_visual_mismatch_maps_to_normative_page_contract",
            )
        ]
        quality = [
            "tests/desktop/test_desktop_app_check.py",
            "tests/desktop/test_ui_conformance.py",
            "tests/foundation/test_ui_reference_check.py",
        ]
        jobs = [
            ("focused-units", py("-m", "unittest", "-v", *cases)),
            (
                "capture-guards",
                py(
                    "-m",
                    "unittest",
                    "-v",
                    *[
                        f"tests.desktop.test_product_style_check.CaptureBundleTests.{name}"
                        for name in (
                            "test_duplicate_missing_extra_and_invalid_png_captures_never_publish",
                            "test_source_change_during_capture_never_publishes",
                            "test_co_tampered_manifest_and_png_fail_against_delivery",
                        )
                    ],
                ),
            ),
            ("selector-denials", py("artifacts/evidence/W2.A03.T02.consumer-denial-probe.py")),
            ("accessibility-browser", py("artifacts/evidence/W2.A03.T02.accessibility-probe.py")),
            ("delivery", py("artifacts/evidence/W2.A03.T02.capture-producer.py", "--delivery-commit", DELIVERY)),
            ("adr", py("tools/adr_check.py", "--repo", ".", "--base", BASE, "--head", candidate)),
            ("ui-gate", py("tools/ui_change_gate.py", "--repo", ".", "--base", BASE, "--head", candidate)),
            ("ruff", py("-m", "ruff", "check", *quality)),
            ("format", py("-m", "ruff", "format", "--check", *quality)),
            ("mypy", py("-m", "mypy", "--no-namespace-packages", *quality)),
            ("diff", ["git", "diff", "--check", BASE, candidate]),
            ("backlog", py("tools/taskctl.py", "--file", "planning/backlog.yaml", "validate")),
            ("views", py("tools/backlog_views.py", "--repo", ".", "--check")),
            ("site", py("tools/plan_review_check.py", "--repo", ".")),
        ]
        for kind in ("tokens", "routes", "workflows", "visual", "accessibility"):
            jobs.append(
                (
                    f"ui-{kind}",
                    py(
                        "tools/ui_conformance.py",
                        "--repo",
                        ".",
                        "--check",
                        kind,
                        "--report",
                        f"{prefix}.ui-{kind}.json",
                    ),
                )
            )
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(run, name, argv, 1 if name == "ui-accessibility" else 0): name for name, argv in jobs
            }
            for future in concurrent.futures.as_completed(futures):
                records.append(future.result())
    finally:
        result_path.write_bytes(
            (
                json.dumps(
                    {"candidateCommit": candidate, "checks": sorted(records, key=lambda item: item["id"])}, indent=2
                )
                + "\n"
            ).encode()
        )
    if any(item["exitCode"] != item["expectedExitCode"] for item in records):
        raise SystemExit("Unexpected result; preserve report and diagnose before retry")


if __name__ == "__main__":
    main()
