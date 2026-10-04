"""Retain actual reference-fixture PNGs; this does not prove native product behavior."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from product_style_check import (  # noqa: E402
    capture_producer_snapshot,
    capture_source_identity,
    read_capture_bundle,
    write_capture_bundle,
)
from ui_conformance import (  # noqa: E402
    confined_path,
    font_face_available,
    load_context,
    new_page,
    open_browser,
    set_page,
    stable_file_bytes,
    windows_path_locks,
)

SCRIPT = "artifacts/evidence/W2.A03.T02.capture-producer.py"
BUNDLE = "artifacts/evidence/W2.A03.T02.baseline-captures"
REFERENCE = "RO-UI-ACADEMIC-MINIMAL-1.8"
PACKAGE = "cd8995fdcea2fe44452eaa1fdd258b6f9fab5714cbd443a81a8e5b4251220b94"


def snapshot(commit: str | None = None) -> dict[str, Any]:
    value = capture_producer_snapshot(REPO, commit)
    for relative in (
        SCRIPT,
        "verification/baselines/desktop-ui.json",
        "verification/desktop-ui-baseline.schema.json",
    ):
        value["inputSha256"][relative] = hashlib.sha256(
            stable_file_bytes(REPO, confined_path(REPO, relative))
        ).hexdigest()
    value["inputSha256"] = dict(sorted(value["inputSha256"].items()))
    value["inputGitBlobs"] = capture_source_identity(REPO, value["producerCommit"], value["inputSha256"])
    return value


def context_and_contract() -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
    context = load_context(REPO)
    visual = context.config["visual"]
    baseline = json.loads(stable_file_bytes(REPO, REPO / visual["baselinePath"]))
    if context.config["referenceId"] != REFERENCE or baseline["referenceId"] != REFERENCE:
        raise ValueError("exact approved 1.8 identity required")
    if context.config["referencePackageSha256"] != PACKAGE or baseline["referencePackageSha256"] != PACKAGE:
        raise ValueError("exact approved 1.8 package required")
    if baseline["settings"] != visual:
        raise ValueError("baseline renderer settings differ from activation")
    if len(context.pages) != 33 or visual["colorSchemes"] != ["light", "dark"] or len(baseline["entries"]) != 66:
        raise ValueError("exact 33-page/66-capture light/dark inventory required")
    contract = [
        {
            "caseId": f"approved-reference-baseline:{name}:{theme}",
            "surfaceId": name,
            "stateId": "initial",
            "theme": theme,
            "viewport": visual["viewport"],
            "role": "reference",
            "referencePage": name,
            "width": visual["viewport"]["width"],
            "height": visual["viewport"]["height"],
        }
        for theme in visual["colorSchemes"]
        for name in context.pages
    ]
    return context, baseline, contract


def produce() -> dict[str, Any]:
    if Path(__file__).resolve() != REPO / SCRIPT:
        raise ValueError("execute only the committed task-owned producer")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO):
        raise ValueError("capture requires a clean committed candidate")
    producer = snapshot()
    paths = list(producer["inputSha256"])
    for root, key in (
        ("apps/desktop/product-dist", "productManifest"),
        ("apps/desktop/dist", "referenceBuildManifest"),
    ):
        paths.extend(f"{root}/{name}" for name in producer[key]["artifacts"])
        paths.append(f"{root}/application-manifest.json")
    with windows_path_locks([confined_path(REPO, path) for path in paths], directories=False):
        if snapshot() != producer:
            raise ValueError("producer changed before input locking")
        context, baseline, contract = context_and_contract()

        def render(capture: Any) -> tuple[list[str], dict[str, Any]]:
            errors: list[str] = []
            entries: dict[str, Any] = {}
            visual = context.config["visual"]
            if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
                raise ValueError("controlled Windows x64 required")
            if importlib.metadata.version("playwright") != visual["playwrightVersion"]:
                raise ValueError("pinned Playwright required")
            playwright, browser = open_browser(context)
            try:
                if browser.version != visual["browserVersion"]:
                    raise ValueError("pinned Chromium required")
                for theme in visual["colorSchemes"]:
                    page = new_page(browser, context, theme=theme)
                    try:
                        for metadata in [item for item in contract if item["theme"] == theme]:
                            name = metadata["referencePage"]
                            set_page(page, context, name, theme)
                            if any(not font_face_available(page, font) for font in visual["requiredFonts"]):
                                raise ValueError(f"required font unavailable: {name}")
                            payload = page.screenshot(
                                full_page=False, animations="disabled", caret="hide", scale="device"
                            )
                            key = f"{name}::{theme}"
                            entry = {
                                "page": name,
                                "theme": theme,
                                "width": metadata["width"],
                                "height": metadata["height"],
                                "sha256": hashlib.sha256(payload).hexdigest(),
                            }
                            if baseline["entries"].get(key) != entry:
                                errors.append(f"committed guarded baseline mismatch: {key}")
                            entries[key] = entry
                            capture(metadata, payload)
                    finally:
                        page.context.close()
            finally:
                browser.close()
                playwright.stop()
            return errors, {
                "scope": "33 approved reference fixture pages, initial light/dark viewport baseline",
                "captureCount": len(entries),
                "baselineEntries": dict(sorted(entries.items())),
                "nativeOrCoreProof": False,
                "productWorkflowQualification": False,
            }

        manifest = write_capture_bundle(REPO, BUNDLE, contract, snapshot, render)
    return {
        "ok": True,
        "manifest": manifest.relative_to(REPO).as_posix(),
        "producerCommit": producer["producerCommit"],
        "authentication": "structural-only; commit then verify exact delivery",
    }


def verify(delivery: str) -> dict[str, Any]:
    _, baseline, contract = context_and_contract()
    manifest = read_capture_bundle(REPO, REPO / BUNDLE / "manifest.json", delivery, contract)
    if manifest["producer"] != snapshot(manifest["producer"]["producerCommit"]):
        raise ValueError("producer source/build/baseline identity differs")
    if manifest["report"]["baselineEntries"] != baseline["entries"] or manifest["report"]["captureCount"] != 66:
        raise ValueError("retained report does not match guarded baseline")
    for item in manifest["captures"]:
        if item["sha256"] != baseline["entries"][f"{item['referencePage']}::{item['theme']}"]["sha256"]:
            raise ValueError("retained PNG differs from baseline")
    return {
        "ok": True,
        "deliveryCommit": delivery,
        "producerCommit": manifest["producer"]["producerCommit"],
        "captures": 66,
        "scope": manifest["report"]["scope"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-commit")
    args = parser.parse_args()
    print(json.dumps(verify(args.delivery_commit) if args.delivery_commit else produce(), sort_keys=True))
