"""Append-only R01 replay: actual keyboard focus and publication metadata shape.

The original preparation helper/evidence remain unchanged. All browser mutations
are isolated negative probes; no active reference, baseline or approval is written.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PRIOR_COMMIT = "d678d5f1be29d11dab38c402721b13e72694c9d5"
PREFIX = "planning/enabler-change-requests/ECR-0008.reference-1.6/"
spec = importlib.util.spec_from_file_location(
    "ecr8_original_preparation", ROOT / "artifacts/evidence/ECR-0008.reference-preparation-check-01.py"
)
assert spec is not None and spec.loader is not None
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
prep.OUT = ROOT / "artifacts/tmp/ecr8-reference16-preview-02"


def prior_blob(relative: str) -> str:
    return subprocess.run(
        ["git", "show", f"{PRIOR_COMMIT}:{PREFIX}{relative}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout


def keyboard_focus(page, button) -> dict:
    before = button.evaluate("node => getComputedStyle(node).boxShadow")
    for presses in range(1, 301):
        page.keyboard.press("Tab")
        if button.evaluate("node => node === document.activeElement"):
            break
    else:
        raise AssertionError("Button unreachable through actual Tab traversal")
    # Resolve the existing semantic token through the browser, not a duplicate
    # literal or a weak 'nonempty shadow' assertion. This probe is in memory only.
    state = button.evaluate("""node => {
      const probe = document.createElement('span');
      probe.style.boxShadow = 'var(--focus-ring)';
      node.parentElement.append(probe);
      const tokenShadow = getComputedStyle(probe).boxShadow;
      probe.remove();
      return {focusVisible:node.matches(':focus-visible'),
        shadow:getComputedStyle(node).boxShadow, tokenShadow,
        outline:getComputedStyle(node).outlineStyle,
        label:node.textContent.trim()};
    }""")
    state.update(tabPresses=presses, unfocusedShadow=before)
    assert state["focusVisible"], "Actual keyboard modality lost"
    assert state["shadow"] != before, f"No visible keyboard change: {state}"
    assert state["shadow"] == state["tokenShadow"] != "none", f"Focus token overridden: {state}"
    button.hover()
    assert button.evaluate("node => getComputedStyle(node).boxShadow") == state["tokenShadow"], (
        "Hover hides keyboard focus"
    )
    return state


def focus_replay() -> dict:
    config = json.loads((ROOT / "verification/extensions/desktop-ui.json").read_text())
    integrity = prep.integrity.validate(prep.CANDIDATE)
    config.update(
        mode="inert-proposal-preview",
        referenceId="RO-UI-ACADEMIC-MINIMAL-1.6",
        referencePackageSha256=integrity["reference_package_sha256"],
    )
    config["normativeSources"] = {
        key: value.replace("design/ui-reference", PREFIX.rstrip("/"))
        for key, value in config["normativeSources"].items()
    }
    site = json.loads((prep.CANDIDATE / "SITE_MANIFEST.json").read_text())
    workflows = json.loads((prep.CANDIDATE / "WORKFLOW_CATALOG.json").read_text())["workflows"]
    contracts = json.loads((prep.CANDIDATE / "CAPABILITY_COVERAGE.json").read_text())["page_contracts"]
    context = prep.ui.Context(
        ROOT,
        config,
        prep.CANDIDATE,
        prep.CANDIDATE,
        site,
        workflows,
        contracts,
        [item["file"] for item in site["pages"]],
    )
    runtime, browser = prep.ui.open_browser(context)
    result = {"positiveCases": [], "negativeCases": [], "negativeCommit": PRIOR_COMMIT}
    try:
        for theme in ("light", "dark"):
            for name in prep.PAGES:
                page = prep.ui.new_page(browser, context, {"width": 1440, "height": 900}, theme)
                try:
                    prep.ui.set_page(page, context, name, theme)
                    button = page.locator('[role="group"][aria-labelledby]:has(.directory-location) button')
                    chosen = keyboard_focus(page, button)
                    summaries = page.locator("details > summary").filter(has_text="separate reference examples")
                    for summary in summaries.all():
                        summary.focus()
                        page.keyboard.press("Enter")
                        assert summary.evaluate("node => node.parentElement.open")
                    retries = []
                    for retry in page.locator("details button.btn:not(:disabled)").all():
                        retries.append(keyboard_focus(page, retry))
                    assert retries, "No recovery action exercised"
                    disabled = page.locator("button.btn:disabled")
                    for item in disabled.all():
                        assert item.evaluate("node => getComputedStyle(node).boxShadow") == "none"
                    result["positiveCases"].append(
                        {
                            "page": name,
                            "theme": theme,
                            "folder": chosen,
                            "recovery": retries,
                            "disabledButtons": disabled.count(),
                        }
                    )
                finally:
                    page.context.close()
            # Replay the exact rejected CSS as an isolated browser style sheet.
            page = prep.ui.new_page(browser, context, {"width": 1440, "height": 900}, theme)
            try:
                prep.ui.set_page(page, context, "projects.html", theme)
                replaced = page.evaluate(
                    """({oldCss, currentCss}) => {
                  let replaced = 0;
                  for (const style of document.querySelectorAll('style')) {
                    if (style.textContent.includes(currentCss)) {
                      style.textContent = style.textContent.replace(currentCss, oldCss);
                      replaced++;
                    }
                  }
                  return replaced;
                }""",
                    {
                        "oldCss": prior_blob("assets/app.css"),
                        "currentCss": (prep.CANDIDATE / "assets/app.css").read_text(encoding="utf-8"),
                    },
                )
                assert replaced == 1, f"Negative control did not replace the exact stylesheet: {replaced}"
                try:
                    keyboard_focus(page, page.locator("#open-project-folder-choose"))
                except AssertionError as exc:
                    assert "No visible keyboard change" in str(exc), str(exc)
                    result["negativeCases"].append({"theme": theme, "rejected": True, "reason": str(exc)})
                else:
                    raise AssertionError("Rejected R01 CSS escaped the new focus assertion")
            finally:
                page.context.close()
    finally:
        browser.close()
        runtime.stop()
    return result


def metadata_replay() -> dict:
    # Clearly synthetic shape-only fixture. Actual authority ancestry, hashes and
    # owner authorization must be authenticated at T01; no fixture is persisted.
    proposed = yaml.safe_load((prep.CANDIDATE / "APPROVAL.yaml").read_text())
    mapped = dict(
        proposed,
        status="approved",
        approval_kind="human",
        approved_by="human:test-fixture",
        approved_at="2000-01-01T00:00:00Z",
        approval_basis="Synthetic shape-only test",
    )
    mapped["authority"] = dict(
        amendment_id="W1.A09",
        change_request_id="ECR-0008",
        approval_record="planning/wave-amendment-approvals/W1.A09.json",
        approval_record_sha256="a" * 64,
        approval_record_introduction_commit="b" * 40,
    )
    assert not prep.ui.approval_record_errors(mapped, "synthetic-fixture", mapped["reference_id"])
    original = yaml.safe_load(prior_blob("APPROVAL.yaml"))
    original.update(status="approved", approved_by="human:test-fixture", approved_at="2000-01-01T00:00:00Z")
    errors = prep.ui.approval_record_errors(original, "rejected-R01-mapping", original["reference_id"])
    assert len(errors) == 2, errors
    return {
        "supportedMappingAccepted": True,
        "rejectedMappingErrors": errors,
        "actualAuthorityAuthenticated": False,
        "scope": "Synthetic field shape only, no approval issued",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--focus-only", action="store_true")
    args = parser.parse_args()
    if not args.focus_only:
        assert prep.main() == 0
    prep.OUT.mkdir(exist_ok=True)
    result = {
        "documentType": "inert-reference-remediation-observation",
        "approval": False,
        "focus": focus_replay(),
        "metadata": metadata_replay(),
    }
    destination = prep.OUT / "remediation-observations.json"
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "positiveCases": len(result["focus"]["positiveCases"]),
                "negativeCases": len(result["focus"]["negativeCases"]),
                "report": str(destination),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
