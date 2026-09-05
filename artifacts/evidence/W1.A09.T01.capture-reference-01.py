"""One-shot exact-reference capture before downstream consumer rebinding.

Uses the unchanged controlled renderer and baseline writer. The temporary
Context targets the authenticated reference itself, not the stale application
fixture. It grants no application conformance, control review or adoption.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import ui_conformance as ui  # noqa: E402


def main() -> None:
    producer = ui.git(REPO, "rev-parse", "HEAD")
    if ui.git(REPO, "diff", "HEAD", "--name-only"):
        raise ValueError("capture requires an unchanged committed producer")
    output = REPO / "artifacts/evidence/W1.A09.T01.reference-captures-01"
    if output.exists():
        raise ValueError("capture directory already exists; never overwrite evidence")
    witness_path = REPO / ui.PRESENTATION_WITNESS_PATH
    witness_bytes = witness_path.read_bytes()
    witness = json.loads(witness_bytes)
    presentation = witness["presentation"]
    reference_id = presentation["referenceId"]
    package = presentation["referencePackageSha256"]
    errors = ui.presentation_compatibility_errors(REPO, reference_id, package)
    if errors:
        raise ValueError("; ".join(errors))
    reference = REPO / "design/ui-reference"
    validated = ui.validate_reference(reference, None)
    if not validated["ok"] or validated["reference_package_sha256"] != package:
        raise ValueError("reference changed after exact publication verification")
    config_path = REPO / "verification/extensions/desktop-ui.json"
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    baseline_path = REPO / config["visual"]["baselinePath"]
    prior_bytes = baseline_path.read_bytes()
    prior = json.loads(prior_bytes)
    # Authenticate real bytes, not just Git's potentially suppressed stat
    # observations. Include every loaded repository tool dependency.
    input_names = {
        Path(__file__).resolve().relative_to(REPO).as_posix(),
        config_path.relative_to(REPO).as_posix(),
        baseline_path.relative_to(REPO).as_posix(),
        ui.PRESENTATION_WITNESS_PATH,
    }
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename:
            candidate = Path(filename).resolve()
            if candidate.is_relative_to(REPO / "tools") and candidate.suffix == ".py":
                input_names.add(candidate.relative_to(REPO).as_posix())
    producer_inputs: dict[str, bytes] = {}
    for relative in sorted(input_names):
        payload = ui.stable_file_bytes(REPO, ui.confined_path(REPO, relative))
        committed, error = ui.git_blob_at(REPO, producer, relative)
        if error or committed is None or ui.canonical_payload(relative, payload) != committed:
            raise ValueError(f"producer input differs from committed bytes: {relative}")
        producer_inputs[relative] = payload
    if (
        config_bytes != producer_inputs[config_path.relative_to(REPO).as_posix()]
        or prior_bytes != producer_inputs[baseline_path.relative_to(REPO).as_posix()]
    ):
        raise ValueError("config or predecessor baseline changed while authenticating inputs")
    if prior["referenceId"] != "RO-UI-ACADEMIC-MINIMAL-1.5" or prior["settings"] != config["visual"]:
        raise ValueError("expected unchanged predecessor renderer settings and semantic1.5 baseline")
    baseline_predecessor = ui.git(REPO, "log", "-1", "--format=%H", "--", config["visual"]["baselinePath"])
    config["referenceId"] = reference_id
    config["referencePackageSha256"] = package
    site = json.loads((reference / "SITE_MANIFEST.json").read_bytes())
    workflows = json.loads((reference / "WORKFLOW_CATALOG.json").read_bytes())["workflows"]
    contracts = json.loads((reference / "CAPABILITY_COVERAGE.json").read_bytes())["page_contracts"]
    pages = [item["file"] for item in site["pages"]]
    if len(pages) != 33 or set(pages) != set(contracts) or len(workflows) != 14:
        raise ValueError("unexpected approved page/workflow inventory")
    context = ui.Context(REPO, config, reference, reference, site, workflows, contracts, pages)
    cases = [(theme, page) for theme in config["visual"]["colorSchemes"] for page in pages]
    captured: list[dict[str, str]] = []
    output.mkdir()
    original_screenshot = ui.Page.screenshot

    def retain_screenshot(page: ui.Page, *args, **kwargs) -> bytes:
        # Preserve exactly the renderer's call and returned bytes. No image
        # substitution, post-processing, selective recapture or tolerance change.
        payload = original_screenshot(page, *args, **kwargs)
        theme, name = cases[len(captured)]
        expected_page = ui.soup(reference / name).body["data-page"]
        if page.locator("body").get_attribute("data-page") != expected_page:
            raise ValueError("capture ordering does not match actual rendered page")
        if page.locator("html").get_attribute("data-theme") != theme:
            raise ValueError("capture theme differs from actual rendered state")
        filename = f"{name.removesuffix('.html')}--{theme}.png"
        with (output / filename).open("xb") as handle:
            handle.write(payload)
        captured.append({"case": f"{name}::{theme}", "file": filename, "sha256": hashlib.sha256(payload).hexdigest()})
        return payload

    with patch.object(ui.Page, "screenshot", new=retain_screenshot):
        baseline = ui.write_baseline(context, reference_id)
    if len(captured) != 66 or set(baseline["entries"]) != {item["case"] for item in captured}:
        raise ValueError("fresh capture set is incomplete")
    for capture in captured:
        if baseline["entries"][capture["case"]]["sha256"] != capture["sha256"]:
            raise ValueError("baseline does not bind the actual fresh PNG bytes")
    if config_path.read_bytes() != config_bytes or witness_path.read_bytes() != witness_bytes:
        raise ValueError("activation or witness changed during capture")
    final_reference = ui.validate_reference(reference, None)
    if not final_reference["ok"] or final_reference["reference_package_sha256"] != package:
        raise ValueError("approved reference changed during capture")
    if ui.git(REPO, "rev-parse", "HEAD") != producer:
        raise ValueError("producer changed during capture")
    for relative, initial in producer_inputs.items():
        if (
            relative != baseline_path.relative_to(REPO).as_posix()
            and ui.stable_file_bytes(REPO, ui.confined_path(REPO, relative)) != initial
        ):
            raise ValueError(f"producer input changed during capture: {relative}")
    if ui.git(REPO, "diff", "--cached", "--name-only", "--", *sorted(input_names)):
        raise ValueError("producer index changed during capture")
    changes = ui.git(REPO, "diff", "HEAD", "--name-only").splitlines()
    if changes != [config["visual"]["baselinePath"]]:
        raise ValueError("capture changed tracked inputs beyond the new baseline")
    report = {
        "schemaVersion": "1.0",
        "documentType": "reference-only-fresh-capture-evidence",
        "generatedAt": datetime.now(UTC).isoformat(),
        "producerCommit": producer,
        "producerInputs": {
            name: hashlib.sha256(ui.canonical_payload(name, payload)).hexdigest()
            for name, payload in producer_inputs.items()
        },
        "referenceId": reference_id,
        "referenceApprovalCommit": presentation["approvalCommit"],
        "referencePackageSha256": package,
        "witnessSha256": hashlib.sha256(witness_bytes.replace(b"\r\n", b"\n")).hexdigest(),
        "priorBaselineCommit": baseline_predecessor,
        "priorBaselineSha256": hashlib.sha256(prior_bytes.replace(b"\r\n", b"\n")).hexdigest(),
        "baselineSha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        "settings": config["visual"],
        "captures": captured,
        "changedFromPrior": [key for key, entry in baseline["entries"].items() if prior["entries"].get(key) != entry],
        "scope": "Fresh approved-reference observations only; not application conformance or independent review.",
        "errors": [],
    }
    with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"captures": len(captured), "changed": len(report["changedFromPrior"]), "producer": producer}))


if __name__ == "__main__":
    main()
