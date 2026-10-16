from __future__ import annotations

from pathlib import Path
import json
from urllib.parse import urlparse
import sys
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
site = json.loads((ROOT / "SITE_MANIFEST.json").read_text(encoding="utf-8"))
coverage = json.loads((ROOT / "CAPABILITY_COVERAGE.json").read_text(encoding="utf-8"))
workflow_catalog = json.loads((ROOT / "WORKFLOW_CATALOG.json").read_text(encoding="utf-8"))
html_files = sorted(ROOT.glob("*.html"))
required_assets = {"assets/tokens.css", "assets/app.css", "assets/print.css", "assets/app.js"}
expected_html = int(site.get("html_document_count", 0))
expected_products = int(site.get("product_page_count", 0))
page_names = {p.get("file") for p in site.get("pages", []) if isinstance(p, dict)}

for html_file in html_files:
    text = html_file.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "lxml")
    if not soup.title or "Research Observatory" not in soup.title.get_text(): errors.append(f"{html_file.name}: missing/incorrect title")
    linked = {tag.get("href") for tag in soup.find_all("link") if tag.get("href")}
    scripts = {tag.get("src") for tag in soup.find_all("script") if tag.get("src")}
    missing_shared = required_assets - (linked | scripts)
    if missing_shared: errors.append(f"{html_file.name}: missing shared assets {sorted(missing_shared)}")
    if not soup.find("main", id="main-content"): errors.append(f"{html_file.name}: missing main landmark")
    if not soup.find(attrs={"data-theme-toggle": True}): errors.append(f"{html_file.name}: missing theme toggle")
    if not soup.find("h1"): errors.append(f"{html_file.name}: missing h1")
    if not soup.find("nav"): errors.append(f"{html_file.name}: missing navigation landmark")
    ids = [node.get("id") for node in soup.find_all(id=True)]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates: errors.append(f"{html_file.name}: duplicate ids {duplicates}")
    for button in soup.find_all("button"):
        if not button.get_text(" ", strip=True) and not button.get("aria-label") and not button.get("title"):
            errors.append(f"{html_file.name}: unlabeled icon-only button")
    for tag, attr in [("a","href"),("link","href"),("script","src"),("img","src")]:
        for node in soup.find_all(tag):
            target=node.get(attr)
            if not target or target.startswith(("#","mailto:","https://","http://","javascript:")): continue
            local_path=(html_file.parent/urlparse(target).path).resolve()
            try: local_path.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{html_file.name}: target escapes package: {target}"); continue
            if not local_path.exists(): errors.append(f"{html_file.name}: broken local reference: {target}")

if len(html_files) != expected_html: errors.append(f"expected {expected_html} HTML files, found {len(html_files)}")
if len(page_names) != expected_products: errors.append(f"expected {expected_products} product pages, manifest contains {len(page_names)}")
if not page_names.issubset({p.name for p in html_files}): errors.append("SITE_MANIFEST references missing product pages")

for governed in ["APPROVAL.yaml","REFERENCE_MANIFEST.yaml","CAPABILITY_COVERAGE.md","CAPABILITY_COVERAGE.json","WORKFLOW_CATALOG.md","WORKFLOW_CATALOG.json","STYLE_GUIDE.md","PAGE_INVENTORY.md","SITE_MANIFEST.json"]:
    if not (ROOT/governed).exists(): errors.append(f"missing governed reference artifact: {governed}")

wf_map=workflow_catalog.get("workflows",{})
if len(wf_map) != 14: errors.append(f"workflow catalog must define exactly fourteen approved use cases; found {len(wf_map)}")
for key,profile in wf_map.items():
    if not profile.get("purpose") or not profile.get("output"): errors.append(f"workflow {key}: purpose and output required")
    steps=profile.get("steps",[])
    if not steps: errors.append(f"workflow {key}: no steps")
    for step in steps:
        if step not in page_names: errors.append(f"workflow {key} references missing/ungoverned page: {step}")

contracts=coverage.get("page_contracts",{})
missing_contracts=sorted(page_names-set(contracts))
if missing_contracts: errors.append(f"product pages missing contracts: {', '.join(missing_contracts)}")
for file_name in page_names:
    contract=contracts.get(file_name,{})
    if not contract.get("required_regions"): errors.append(f"{file_name}: page contract has no required regions")
    html=(ROOT/file_name).read_text(encoding="utf-8")
    for marker in ("data-workflow-select","data-workflow-nav","data-workflow-context"):
        if marker not in html: errors.append(f"{file_name}: missing adaptive-workflow marker {marker}")

capabilities=coverage.get("capabilities",[])
if len(capabilities) != 20: errors.append(f"coverage must describe 20 capabilities; found {len(capabilities)}")
cap_ids={c.get("capability") for c in capabilities}
for file_name,contract in contracts.items():
    for cap in contract.get("capabilities",[]):
        if cap not in cap_ids: errors.append(f"{file_name}: unknown capability {cap}")

required_production={"study-design.html","manuscript-blueprint.html","technical-reports.html","manuscript-studio.html","reviewer-simulation.html","revision-response.html"}
if not required_production.issubset(page_names): errors.append("research-production page set is incomplete")
new_project=(ROOT/"new-project.html").read_text(encoding="utf-8")
if new_project.count("data-workflow-choice") != 14: errors.append("new-project.html must present fourteen approved use-case choices")

if errors:
    print("Verification failed:")
    for error in errors: print(" -",error)
    sys.exit(1)
print(f"Verified {len(html_files)} HTML files, {len(page_names)} product pages, {len(wf_map)} workflows, and {len(capabilities)} capability records.")
