"""Exercise exact selector and baseline-shape denials without altering the producer."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "tools"))
from ui_conformance import baseline_document_errors, load_context  # noqa: E402

candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
activation = json.loads((repo / "verification/extensions/desktop-ui.json").read_bytes())
results = []
with tempfile.TemporaryDirectory(prefix="w2-t02-selector-") as temporary:
    root = Path(temporary) / "repo"
    shutil.copytree(repo / "design/ui-reference", root / "design/ui-reference")
    (root / "verification/extensions").mkdir(parents=True)
    shutil.copyfile(repo / "verification/desktop-ui.schema.json", root / "verification/desktop-ui.schema.json")
    source = root / "apps/desktop/src/View.tsx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"export const View = () => null;\n")
    (root / "apps/desktop/dist").mkdir()
    cases = (
        ("valid selectors reach required build boundary", {}, "application manifest"),
        ("stale 1.7 selector", {"referenceId": "RO-UI-ACADEMIC-MINIMAL-1.7"}, "reference ID does not match"),
        (
            "mixed old package",
            {"referencePackageSha256": "dcf31147ee386d48e8ac95725d648ee2b08c74ef0dd42c139c5f78508a90f878"},
            "package SHA-256 does not match",
        ),
    )
    for name, change, expected in cases:
        value = copy.deepcopy(activation)
        value.update(change)
        (root / "verification/extensions/desktop-ui.json").write_bytes((json.dumps(value) + "\n").encode())
        try:
            load_context(root)
        except ValueError as error:
            if expected not in str(error):
                raise ValueError(f"wrong denial boundary for {name}: {error}") from error
            results.append({"case": name, "result": "PASS", "expectedDenial": expected})
        else:
            raise ValueError(f"required denial missing for {name}")

baseline = json.loads((repo / "verification/baselines/desktop-ui.json").read_bytes())
schema = json.loads((repo / "verification/desktop-ui-baseline.schema.json").read_bytes())
site = json.loads((repo / "design/ui-reference/SITE_MANIFEST.json").read_bytes())
pages = [item["file"] for item in site["pages"]]
if baseline_document_errors(baseline, "current", schema, pages):
    raise ValueError("positive current baseline shape failed")
for name in ("missing capture", "extra capture", "changed renderer viewport"):
    value = copy.deepcopy(baseline)
    key = next(iter(value["entries"]))
    if name == "missing capture":
        value["entries"].pop(key)
    elif name == "extra capture":
        value["entries"]["foreign-page.html::light"] = {**value["entries"][key], "page": "foreign-page.html"}
    else:
        value["settings"]["viewport"]["width"] -= 1
    errors = baseline_document_errors(value, name, schema, pages)
    if not errors:
        raise ValueError(f"required baseline denial missing for {name}")
    results.append({"case": name, "result": "PASS", "errors": errors})
if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip() != candidate:
    raise ValueError("HEAD changed during denial characterization")
report = {
    "ok": True,
    "candidateCommit": candidate,
    "scope": "physical isolated selector fixture and actual baseline structural validation; no native/Core claim",
    "cases": results,
}
(repo / f"artifacts/tmp/W2.A03.T02.consumer-denials-fresh-{candidate[:8]}.json").write_bytes(
    (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
)
print(json.dumps(report, sort_keys=True))
