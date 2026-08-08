#!/usr/bin/env python3
"""Generate the static capability/slice planning review site for Research Observatory."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    import mistune
except ImportError:  # pragma: no cover - generated site still works with plain Markdown fallback
    mistune = None


SITE_SCHEMA_VERSION = "1.0"
REVIEW_INTERFACE_RELEASE = "1.3.5"
FEEDBACK_SCHEMA_VERSION = "1.1"
OTHER_SENTINEL = "__OTHER__"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"{path}: unterminated YAML front matter")
    return yaml.safe_load(text[4:end]) or {}, text[end + 5 :]


def strip_first_h1(markdown: str) -> str:
    return re.sub(r"\A\s*#\s+[^\n]+\n+", "", markdown, count=1)


def extract_section(markdown: str, number: int) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{number}\.\s+.*?(?=^##\s+\d+\.|\Z)")
    match = pattern.search(markdown)
    return match.group(0) if match else ""


def markdown_renderer():
    if mistune is None:
        return lambda value: f"<pre class='markdown-fallback'>{html.escape(value)}</pre>"
    return mistune.create_markdown(escape=False, plugins=["table", "task_lists"])


MD = markdown_renderer()


def render_markdown(markdown: str) -> str:
    return MD(markdown)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def status_badge(status: str | None) -> str:
    label = status or "unknown"
    css = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f'<span class="status status-{esc(css)}">{esc(label.replace("-", " ").title())}</span>'


def relative_assets(depth: int) -> str:
    return "../" * depth + "assets"


def shell(*, title: str, body: str, depth: int, page_type: str, capability_id: str | None = None) -> str:
    assets = relative_assets(depth)
    cap_attr = f' data-capability-id="{esc(capability_id)}"' if capability_id else ""
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{esc(title)} - Research Observatory Planning Review</title>
  <link rel="stylesheet" href="{assets}/review.css">
</head>
<body data-page-type="{esc(page_type)}"{cap_attr}>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <header class="site-header">
    <a class="brand" href="{'../' * depth}index.html" aria-label="Planning review home">
      <span class="brand-mark" aria-hidden="true">RO</span>
      <span><strong>Research Observatory</strong><small>Planning Review</small></span>
    </a>
    <div class="header-actions">
      <button class="button button-quiet" type="button" data-theme-toggle aria-label="Toggle light and dark theme">Theme</button>
    </div>
  </header>
  {body}
  <footer class="site-footer">
    <span>Static, local-first review surface</span>
    <span>Capability decisions precede implementation</span>
  </footer>
  <script src="{assets}/review.js"></script>
</body>
</html>
"""


def layout(*, breadcrumbs: str, sidebar: str, main: str) -> str:
    return f"""
  <div class="page-frame">
    <aside class="side-panel" aria-label="Planning navigation">{sidebar}</aside>
    <main id="main-content" class="main-panel">
      <nav class="breadcrumbs" aria-label="Breadcrumb">{breadcrumbs}</nav>
      {main}
    </main>
  </div>
"""


def capability_nav(capabilities: list[dict[str, Any]], active: str | None, prefix: str = "") -> str:
    items = []
    for cap in capabilities:
        cid = cap["id"]
        cls = " active" if cid == active else ""
        href = f"{prefix}{cid}/index.html"
        items.append(
            f'<a class="nav-item{cls}" href="{href}"><span>{esc(cid)}</span><small>{esc(cap["title"])}</small></a>'
        )
    return "<h2>Capabilities</h2><nav class='cap-nav'>" + "".join(items) + "</nav>"


def slice_nav(slices: list[dict[str, Any]], active: str | None) -> str:
    rows = []
    for index, sl in enumerate(slices, start=1):
        sid = sl["slice_id"]
        cls = " active" if sid == active else ""
        rows.append(
            f'<a class="slice-nav-item{cls}" href="{esc(sl["page_name"])}"><b>{index}</b><span><strong>{esc(sid)}</strong><small>{esc(sl["title"])}</small></span></a>'
        )
    return "<h2>Capability slices</h2><nav class='slice-nav'>" + "".join(rows) + "</nav>"


def decision_card(decision: dict[str, Any], plan_hash: str) -> str:
    did = decision["id"]
    candidates = decision.get("candidates", [])
    recommended = decision.get("recommendation")
    selected = decision.get("selected_option")
    options = []
    for idx, candidate in enumerate(candidates):
        oid = f"{did}-option-{idx}"
        checked = " checked" if selected == candidate else ""
        rec = '<span class="recommended">Recommended</span>' if candidate == recommended else ""
        options.append(
            f"""<label class="decision-option" for="{esc(oid)}">
  <input id="{esc(oid)}" type="radio" name="{esc(did)}" value="{esc(candidate)}" data-decision-option{checked}>
  <span><strong>{esc(candidate)}</strong>{rec}</span>
</label>"""
        )
    other_id = f"{did}-option-other"
    options.append(
        f"""<label class="decision-option decision-option-other" for="{esc(other_id)}">
  <input id="{esc(other_id)}" type="radio" name="{esc(did)}" value="{OTHER_SENTINEL}" data-decision-option data-other-choice>
  <span><strong>Other</strong><small>Propose a direction not listed above</small></span>
</label>
<label class="other-option-field" data-other-option-field>
  <span>Brief Other description</span>
  <input type="text" maxlength="180" data-decision-other placeholder="Briefly name the alternative direction" aria-describedby="{esc(did)}-other-help">
  <small id="{esc(did)}-other-help">Required when Other is selected. Use the feedback field below for detailed reasoning and constraints.</small>
</label>"""
    )
    return f"""
<section class="decision-card" data-decision-id="{esc(did)}" data-recommendation="{esc(recommended)}" data-plan-hash="{esc(plan_hash)}">
  <div class="decision-heading">
    <div><span class="eyebrow">{esc(did)}</span><h3>{esc(decision.get('title'))}</h3></div>
    {status_badge(decision.get('status'))}
  </div>
  <p class="decision-basis">{esc(decision.get('recommendation_basis'))}</p>
  <fieldset><legend>Resolved selection (change only to override)</legend>{''.join(options)}</fieldset>
  <label class="field-label">Detailed feedback, rationale, or implementation conditions
    <textarea rows="4" data-decision-rationale placeholder="Optional for the recommendation; required for any override, including Other."></textarea>
  </label>
  <p class="decision-meta">Required ADR: <code>{esc(decision.get('required_adr') or 'None currently identified')}</code></p>
</section>
"""


def build_site(repo: Path, output: Path, selected_capability: str | None = None) -> dict[str, Any]:
    backlog = yaml.safe_load((repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
    backlog_caps = {cap["id"]: cap for cap in backlog.get("capabilities", [])}
    cap_plan_dir = repo / "planning/capability-plans"
    slice_plan_dir = repo / "planning/slice-plans"
    all_cap_paths = sorted(cap_plan_dir.glob("CAP-*.md"))
    if selected_capability and selected_capability not in {path.stem for path in all_cap_paths}:
        raise ValueError(f"No capability plan found for {selected_capability}")
    # The site is a coherent generated set. Always rebuild all pages so links, hashes, and the manifest remain synchronized.
    cap_paths = all_cap_paths
    capabilities: list[dict[str, Any]] = []
    for path in all_cap_paths:
        meta, _ = read_frontmatter(path)
        capabilities.append({"id": meta["capability_id"], "title": meta["title"]})

    # Rebuild into a clean directory so stale pages or convenience launchers cannot
    # be mistaken for governed review pages or break page-count validation.
    generated_at = datetime.now(timezone.utc).isoformat()
    existing_manifest = output / "manifest.json"
    if existing_manifest.exists():
        try:
            existing_generated_at = json.loads(existing_manifest.read_text(encoding="utf-8")).get("generated_at")
            if isinstance(existing_generated_at, str) and existing_generated_at.strip():
                generated_at = existing_generated_at
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "review.css").write_text(REVIEW_CSS, encoding="utf-8")
    (assets / "review.js").write_text(REVIEW_JS, encoding="utf-8")

    manifest: dict[str, Any] = {
        "schema_version": SITE_SCHEMA_VERSION,
        "document_type": "planning-review-site-manifest",
        "baseline": str(backlog.get("baseline", "1.3")),
        "supplemental_release": "1.3.4",
        "review_interface_release": REVIEW_INTERFACE_RELEASE,
        "generated_at": generated_at,
        "entry_point": "index.html",
        "feedback_schema_version": FEEDBACK_SCHEMA_VERSION,
        "capabilities": [],
    }

    cards = []
    for path in all_cap_paths:
        meta, _ = read_frontmatter(path)
        cid = meta["capability_id"]
        decision_count = len(meta.get("decisions", []))
        unresolved = len(meta.get("open_blocking_decisions", []))
        cards.append(f"""
<a class="capability-card" href="{esc(cid)}/index.html">
  <div class="capability-card-top"><span class="eyebrow">{esc(cid)}</span>{status_badge(meta.get('status'))}</div>
  <h2>{esc(meta.get('title'))}</h2>
  <dl><div><dt>Slices</dt><dd>{len(meta.get('slice_ids', []))}</dd></div><div><dt>Decisions</dt><dd>{decision_count}</dd></div><div><dt>Open</dt><dd>{unresolved}</dd></div></dl>
  <span class="text-link">Review capability plan</span>
</a>""")
    landing_main = f"""
<section class="hero compact">
  <span class="eyebrow">Decision-complete capability planning</span>
  <h1>Planning review center</h1>
  <p>Review the preselected best-in-class defaults, override only where warranted, approve all slice plans together, then allow the coding agent to execute the capability as a long-running campaign.</p>
</section>
<section class="callout callout-info"><h2>How to use this site</h2><ol><li>Select a capability.</li><li>Confirm the preselected decisions near the top, or override an option with rationale.</li><li>Review every slice page and its task sequence.</li><li>Approve the capability directly when the defaults stand; export decision-response JSON only when preserving overrides or notes.</li></ol></section>
<section class="capability-grid">{''.join(cards)}</section>
"""
    landing = shell(
        title="Planning review center",
        page_type="landing",
        depth=0,
        body=layout(
            breadcrumbs='<span aria-current="page">Planning review</span>',
            sidebar=capability_nav(capabilities, None),
            main=landing_main,
        ),
    )
    (output / "index.html").write_text(landing, encoding="utf-8")

    for cap_path in cap_paths:
        meta, body_md = read_frontmatter(cap_path)
        cid = meta["capability_id"]
        cap_dir = output / cid
        cap_dir.mkdir(parents=True, exist_ok=True)
        cap_hash = sha256(cap_path)
        backlog_cap = backlog_caps.get(cid, {})

        slice_files = sorted((slice_plan_dir / cid).glob("*.md"))
        slices: list[dict[str, Any]] = []
        for path in slice_files:
            smeta, sbody = read_frontmatter(path)
            page_name = f"{smeta['slice_id']}.html"
            slices.append(
                {
                    "path": path,
                    "meta": smeta,
                    "body": sbody,
                    "slice_id": smeta["slice_id"],
                    "title": smeta["title"],
                    "page_name": page_name,
                    "sha256": sha256(path),
                }
            )

        decisions_html = "".join(decision_card(decision, cap_hash) for decision in meta.get("decisions", []))
        slice_cards = []
        for idx, sl in enumerate(slices, start=1):
            smeta = sl["meta"]
            slice_cards.append(f"""
<a class="slice-card" href="{esc(sl['page_name'])}">
  <div class="slice-card-index">{idx}</div>
  <div><span class="eyebrow">{esc(sl['slice_id'])}</span><h3>{esc(sl['title'])}</h3>
  <p>{len(smeta.get('task_ids', []))} tasks · {esc(smeta.get('wave'))} · {esc(smeta.get('priority'))}</p></div>
  {status_badge(smeta.get('status'))}
</a>""")

        capability_main = f"""
<section class="hero compact">
  <div class="hero-top"><div><span class="eyebrow">{esc(cid)} · Capability decision and execution plan</span><h1>{esc(meta.get('title'))}</h1></div>{status_badge(meta.get('status'))}</div>
  <p>Review the completed recommendation register before implementation. Once approved, the campaign executes all slices continuously except for documented infeasibility or genuinely new consequential evidence.</p>
  <dl class="summary-grid"><div><dt>Slices</dt><dd>{len(slices)}</dd></div><div><dt>Decisions</dt><dd>{len(meta.get('decisions', []))}</dd></div><div><dt>Open blockers</dt><dd>{len(meta.get('open_blocking_decisions', []))}</dd></div><div><dt>Plan hash</dt><dd><code>{cap_hash[:12]}</code></dd></div></dl>
</section>
<section class="review-toolbar" data-review-toolbar>
  <div><h2>Resolved recommendations and capability approval</h2><p>Best-in-class recommendations are preselected and decision-complete. Confirm them, override a documented option with rationale, or select Other and provide both a brief description and detailed rationale. Export a review record only when preserving overrides or notes; one explicit capability approval still authorizes implementation.</p></div>
  <div class="review-progress" aria-live="polite"><strong data-selected-count>0</strong> / {len(meta.get('decisions', []))} selected</div>
  <label class="field-label">Reviewer name<input type="text" data-reviewer-name placeholder="Name or review role"></label>
  <label class="field-label">Capability-level notes<textarea rows="3" data-review-notes placeholder="Cross-slice constraints, required benchmarks, or approval conditions"></textarea></label>
  <label class="approval-check"><input type="checkbox" data-approval-intent> Request approval of the capability packet and every slice plan after feedback is applied</label>
  <div class="button-row"><button class="button" type="button" data-accept-recommendations>Restore recommended defaults</button><button class="button button-quiet" type="button" data-clear-decisions>Clear draft overrides</button><button class="button button-primary" type="button" data-export-feedback>Export decision-response JSON</button></div>
  <div class="feedback-message" data-feedback-message role="status"></div>
  <details><summary>Automation commands</summary><pre><code>python tools/planctl.py --repo . review {esc(cid)}
python tools/planctl.py --repo . approve {esc(cid)} --by "&lt;reviewer&gt;" --commit &lt;git-sha&gt;
# Only for overrides or notes:
python tools/planctl.py --repo . apply-feedback {esc(cid)} &lt;downloaded-json&gt;
python tools/planctl.py --repo . approve {esc(cid)} --feedback &lt;downloaded-json&gt; --by "&lt;reviewer&gt;" --commit &lt;git-sha&gt;
python tools/planctl.py --repo . ready {esc(cid)} --require-approved</code></pre></details>
</section>
<section id="decision-register" class="section-heading"><span class="eyebrow">Decision register</span><h2>Confirm resolved defaults or record overrides</h2><p>Each researched best-in-class recommendation is already selected and decision-complete. Capability approval authorizes the current set. Any documented alternative requires rationale. Other additionally requires a brief description.</p></section>
<div class="decision-list">{decisions_html}</div>
<section class="section-heading"><span class="eyebrow">Slice sequence</span><h2>Review the implementation plan slice by slice</h2></section>
<div class="slice-list">{''.join(slice_cards)}</div>
<details class="plan-details"><summary>Read the full capability plan</summary><article class="plan-article">{render_markdown(strip_first_h1(body_md))}</article></details>
"""
        cap_page = shell(
            title=f"{cid} {meta.get('title')}",
            page_type="capability",
            capability_id=cid,
            depth=1,
            body=layout(
                breadcrumbs=f'<a href="../index.html">Planning review</a><span>/</span><span aria-current="page">{esc(cid)}</span>',
                sidebar=capability_nav(capabilities, cid, prefix="../") + slice_nav(slices, None),
                main=capability_main,
            ),
        )
        (cap_dir / "index.html").write_text(cap_page, encoding="utf-8")

        open_decision_count = len(meta.get("open_blocking_decisions", []))
        if open_decision_count:
            gate_heading = f"Resolve {open_decision_count} capability decision{'s' if open_decision_count != 1 else ''} before implementation"
            gate_text = "Decision options and approval controls are kept on the capability page so the complete cross-slice set is reviewed once."
        else:
            gate_heading = "Recommendations resolved; one capability approval remains"
            gate_text = "All material decisions are complete with the researched recommendations preselected. Reviewers only need to confirm or override the defaults and give the single capability approval."

        for index, sl in enumerate(slices):
            smeta = sl["meta"]
            section4 = extract_section(sl["body"], 4)
            section9 = extract_section(sl["body"], 9)
            prev_link = slices[index - 1]["page_name"] if index > 0 else "index.html"
            next_link = slices[index + 1]["page_name"] if index + 1 < len(slices) else "index.html"
            slice_main = f"""
<section class="hero compact">
  <div class="hero-top"><div><span class="eyebrow">{esc(sl['slice_id'])} · Slice {index + 1} of {len(slices)}</span><h1>{esc(sl['title'])}</h1></div>{status_badge(smeta.get('status'))}</div>
  <p>This plan expands the authoritative backlog tasks without creating a second hierarchy. It becomes executable only after the capability decisions and all slice plans are approved together.</p>
  <dl class="summary-grid"><div><dt>Wave</dt><dd>{esc(smeta.get('wave'))}</dd></div><div><dt>Priority</dt><dd>{esc(smeta.get('priority'))}</dd></div><div><dt>Tasks</dt><dd>{len(smeta.get('task_ids', []))}</dd></div><div><dt>Plan hash</dt><dd><code>{sl['sha256'][:12]}</code></dd></div></dl>
</section>
<section class="callout callout-warning">
  <div><span class="eyebrow">Capability decision gate</span><h2>{esc(gate_heading)}</h2><p>{esc(gate_text)}</p></div>
  <a class="button button-primary" href="index.html#decision-register">Review capability decisions</a>
</section>
<section class="decision-summary"><div class="section-heading"><span class="eyebrow">Slice decisions</span><h2>Recommended implementation selections</h2></div><article class="plan-article compact-article">{render_markdown(section4)}</article></section>
<section class="task-summary"><div class="section-heading"><span class="eyebrow">Implementation sequence</span><h2>Authoritative task plan</h2></div><article class="plan-article compact-article">{render_markdown(section9)}</article></section>
<details class="plan-details" open><summary>Read the complete slice plan</summary><article class="plan-article">{render_markdown(strip_first_h1(sl['body']))}</article></details>
<nav class="page-turn" aria-label="Slice navigation"><a class="button button-quiet" href="{esc(prev_link)}">Previous</a><a class="button button-primary" href="{esc(next_link)}">Next</a></nav>
"""
            slice_page = shell(
                title=f"{sl['slice_id']} {sl['title']}",
                page_type="slice",
                capability_id=cid,
                depth=1,
                body=layout(
                    breadcrumbs=f'<a href="../index.html">Planning review</a><span>/</span><a href="index.html">{esc(cid)}</a><span>/</span><span aria-current="page">{esc(sl["slice_id"])}</span>',
                    sidebar=capability_nav(capabilities, cid, prefix="../") + slice_nav(slices, sl["slice_id"]),
                    main=slice_main,
                ),
            )
            (cap_dir / sl["page_name"]).write_text(slice_page, encoding="utf-8")

        manifest["capabilities"].append(
            {
                "capability_id": cid,
                "title": meta.get("title"),
                "plan_path": str(cap_path.relative_to(repo)).replace(os.sep, "/"),
                "plan_sha256": cap_hash,
                "page": f"{cid}/index.html",
                "decision_count": len(meta.get("decisions", [])),
                "slice_count": len(slices),
                "slices": [
                    {
                        "slice_id": sl["slice_id"],
                        "title": sl["title"],
                        "plan_path": str(sl["path"].relative_to(repo)).replace(os.sep, "/"),
                        "plan_sha256": sl["sha256"],
                        "page": f"{cid}/{sl['page_name']}",
                        "task_count": len(sl["meta"].get("task_ids", [])),
                    }
                    for sl in slices
                ],
            }
        )

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total_slices = sum(len(item.get("slices", [])) for item in manifest["capabilities"])
    readme = f"""# Static planning review site

Open `index.html` in a browser. Review interface release {REVIEW_INTERFACE_RELEASE}; canonical planning supplement 1.3.4. The site contains {len(manifest['capabilities'])} capability pages and {total_slices} individual slice pages. Every researched best-in-class recommendation is already selected and treated as a completed planning decision. The site lets a reviewer confirm the defaults, record a reasoned documented override, choose Other with a brief description plus detailed rationale, add notes, and export a JSON feedback record before the single explicit capability approval.

Canonical commands:

```bash
python tools/planctl.py --repo . review CAP-XX
python tools/planctl.py --repo . adopt-recommendations CAP-XX  # already complete for authored packets
python tools/planctl.py --repo . approve CAP-XX --by "Reviewer" --commit <git-sha>
# Only when an override or note was exported:
python tools/planctl.py --repo . apply-feedback CAP-XX <downloaded-json>
python tools/planctl.py --repo . approve CAP-XX --feedback <downloaded-json> --by "Reviewer" --commit <git-sha>
```

The Markdown plans remain authoritative. The review site is a generated human review surface and must be regenerated and validated after plan changes.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", default="planning/review-site")
    parser.add_argument("--capability")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    output = (repo / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output).resolve()
    manifest = build_site(repo, output, args.capability)
    entry = output / (args.capability or "") / "index.html" if args.capability else output / "index.html"
    print(f"Generated planning review site: {entry.as_uri()}")
    print(f"Manifest: {(output / 'manifest.json').as_posix()}")
    return 0


REVIEW_CSS = r'''
:root {
  color-scheme: light;
  --canvas: #f5f7fb;
  --surface: #ffffff;
  --surface-soft: #eef3fb;
  --surface-strong: #dce8fb;
  --text: #10233d;
  --text-soft: #536985;
  --line: #cad7e8;
  --line-strong: #9eb7d8;
  --primary: #2563eb;
  --primary-strong: #1748b5;
  --primary-soft: #e9f0ff;
  --success: #18794e;
  --success-soft: #e8f7ef;
  --warning: #9a6500;
  --warning-soft: #fff4d8;
  --danger: #b42318;
  --danger-soft: #ffebe8;
  --shadow: 0 12px 30px rgba(16, 35, 61, .09);
  --radius: 12px;
  --font-ui: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-display: Georgia, "Times New Roman", serif;
}
html[data-theme="dark"] {
  color-scheme: dark;
  --canvas: #061527;
  --surface: #0b1f37;
  --surface-soft: #102740;
  --surface-strong: #173454;
  --text: #f4f8ff;
  --text-soft: #a9bbd3;
  --line: #294563;
  --line-strong: #41698f;
  --primary: #5b91ff;
  --primary-strong: #83adff;
  --primary-soft: #132f57;
  --success: #55c78a;
  --success-soft: #123c2b;
  --warning: #f0bd4e;
  --warning-soft: #483615;
  --danger: #ff867c;
  --danger-soft: #4b211f;
  --shadow: 0 16px 36px rgba(0, 0, 0, .25);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--canvas); color: var(--text); font-family: var(--font-ui); line-height: 1.55; }
a { color: var(--primary); }
button, input, textarea { font: inherit; }
.skip-link { position: fixed; top: -50px; left: 1rem; z-index: 100; padding: .7rem 1rem; background: var(--primary); color: white; border-radius: 8px; }
.skip-link:focus { top: 1rem; }
.site-header { position: sticky; top: 0; z-index: 20; height: 64px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; background: color-mix(in srgb, var(--surface) 94%, transparent); border-bottom: 1px solid var(--line); backdrop-filter: blur(12px); }
.brand { display: flex; align-items: center; gap: 12px; color: var(--text); text-decoration: none; }
.brand-mark { display: grid; place-items: center; width: 34px; height: 34px; border: 1px solid var(--primary); color: var(--primary); border-radius: 50%; font-weight: 800; font-size: .78rem; }
.brand span:last-child { display: grid; line-height: 1.15; }
.brand small { color: var(--text-soft); font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; }
.page-frame { min-height: calc(100vh - 108px); display: grid; grid-template-columns: 270px minmax(0, 1fr); }
.side-panel { position: sticky; top: 64px; height: calc(100vh - 64px); overflow: auto; padding: 24px 16px; border-right: 1px solid var(--line); background: var(--surface); }
.side-panel h2 { margin: 0 8px 10px; color: var(--text-soft); font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; }
.cap-nav, .slice-nav { display: grid; gap: 6px; margin-bottom: 28px; }
.nav-item, .slice-nav-item { display: grid; text-decoration: none; color: var(--text); border: 1px solid transparent; border-radius: 9px; padding: 10px 11px; }
.nav-item small, .slice-nav-item small { color: var(--text-soft); }
.nav-item:hover, .slice-nav-item:hover, .nav-item.active, .slice-nav-item.active { background: var(--primary-soft); border-color: var(--line-strong); }
.nav-item.active span, .slice-nav-item.active strong { color: var(--primary); }
.slice-nav-item { grid-template-columns: 26px 1fr; align-items: start; gap: 6px; }
.slice-nav-item b { display: grid; place-items: center; width: 22px; height: 22px; background: var(--surface-soft); border-radius: 50%; color: var(--text-soft); font-size: .7rem; }
.slice-nav-item span { display: grid; }
.slice-nav-item strong { font-size: .78rem; }
.slice-nav-item small { font-size: .74rem; }
.main-panel { width: min(1320px, 100%); padding: 28px clamp(20px, 4vw, 54px) 64px; }
.breadcrumbs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; color: var(--text-soft); font-size: .82rem; }
.breadcrumbs a { color: var(--text-soft); text-decoration: none; }
.hero { border: 1px solid var(--line); border-radius: var(--radius); padding: clamp(22px, 4vw, 38px); background: linear-gradient(135deg, var(--surface), var(--surface-soft)); box-shadow: var(--shadow); }
.hero.compact { margin-bottom: 22px; }
.hero h1 { max-width: 900px; margin: 5px 0 8px; font: 700 clamp(2rem, 4vw, 3.25rem)/1.05 var(--font-display); letter-spacing: -.025em; }
.hero p { max-width: 920px; margin: 0; color: var(--text-soft); font-size: 1.04rem; }
.hero-top { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.eyebrow { color: var(--primary); font-weight: 800; font-size: .72rem; letter-spacing: .1em; text-transform: uppercase; }
.status { display: inline-flex; align-items: center; width: fit-content; padding: .27rem .56rem; border: 1px solid var(--line); border-radius: 999px; font-size: .7rem; font-weight: 800; letter-spacing: .03em; white-space: nowrap; }
.status-proposed, .status-pending, .status-recommended { color: var(--warning); background: var(--warning-soft); }
.status-approved, .status-accepted, .status-complete { color: var(--success); background: var(--success-soft); }
.status-rejected, .status-reopened { color: var(--danger); background: var(--danger-soft); }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(110px, 1fr)); gap: 10px; margin: 24px 0 0; }
.summary-grid div, .capability-card dl div { padding: 12px 14px; border: 1px solid var(--line); border-radius: 9px; background: var(--surface); }
dt { color: var(--text-soft); font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; }
dd { margin: 3px 0 0; font-weight: 750; }
.callout { display: flex; justify-content: space-between; align-items: center; gap: 22px; margin: 20px 0; padding: 18px 20px; border: 1px solid var(--line-strong); border-radius: var(--radius); background: var(--surface); }
.callout h2 { margin: 2px 0; font: 700 1.35rem/1.2 var(--font-display); }
.callout p { margin: 0; color: var(--text-soft); }
.callout-info { border-left: 5px solid var(--primary); }
.callout-warning { border-left: 5px solid var(--warning); background: var(--warning-soft); }
.capability-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.capability-card { display: block; padding: 20px; text-decoration: none; color: var(--text); border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); box-shadow: 0 5px 16px rgba(16,35,61,.05); }
.capability-card:hover { transform: translateY(-2px); box-shadow: var(--shadow); border-color: var(--line-strong); }
.capability-card-top { display: flex; justify-content: space-between; gap: 12px; }
.capability-card h2 { margin: 10px 0 16px; font: 700 1.3rem/1.25 var(--font-display); }
.capability-card dl { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.capability-card dl div { padding: 8px; }
.text-link { color: var(--primary); font-weight: 750; }
.review-toolbar { position: relative; margin: 20px 0 28px; padding: 20px; border: 1px solid var(--line-strong); border-radius: var(--radius); background: var(--surface); box-shadow: var(--shadow); }
.review-toolbar h2 { margin: 0; font: 700 1.5rem/1.2 var(--font-display); }
.review-toolbar p { margin: 4px 0 16px; color: var(--text-soft); }
.review-progress { position: absolute; top: 20px; right: 20px; padding: .45rem .7rem; background: var(--primary-soft); color: var(--primary); border-radius: 999px; font-size: .8rem; }
.field-label { display: grid; gap: 6px; margin: 12px 0; color: var(--text-soft); font-weight: 700; font-size: .78rem; }

.other-option-field { display: none; margin: 4px 0 10px 30px; padding: 12px; border: 1px dashed var(--primary); border-radius: 8px; background: var(--primary-soft); }
.other-option-field.is-visible { display: grid; gap: 7px; }
.other-option-field > span { font-weight: 800; font-size: .82rem; }
.other-option-field small, .decision-option small { display: block; margin-top: 3px; color: var(--text-soft); font-size: .75rem; }
.other-option-field input { width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 10px 11px; background: var(--canvas); color: var(--text); }
.decision-option-other { border-style: dashed; }

input[type="text"], textarea { width: 100%; border: 1px solid var(--line); border-radius: 8px; padding: 10px 11px; background: var(--canvas); color: var(--text); }
input:focus, textarea:focus, button:focus, a:focus { outline: 3px solid color-mix(in srgb, var(--primary) 30%, transparent); outline-offset: 2px; }
.approval-check { display: flex; align-items: flex-start; gap: 9px; margin: 14px 0; font-weight: 700; }
.button-row { display: flex; flex-wrap: wrap; gap: 8px; }
.button { display: inline-flex; justify-content: center; align-items: center; min-height: 40px; padding: 8px 13px; border: 1px solid var(--line-strong); border-radius: 8px; background: var(--surface-soft); color: var(--text); text-decoration: none; font-weight: 750; cursor: pointer; }
.button:hover { border-color: var(--primary); }
.button-primary { color: white; background: var(--primary); border-color: var(--primary); }
.button-quiet { background: transparent; }
.feedback-message { margin-top: 10px; color: var(--text-soft); }
.review-toolbar details { margin-top: 14px; }
.review-toolbar pre, .plan-article pre { overflow: auto; padding: 14px; border-radius: 9px; background: #08192d; color: #ecf4ff; }
.section-heading { margin: 30px 0 14px; }
.section-heading h2 { margin: 4px 0 3px; font: 700 1.75rem/1.15 var(--font-display); }
.section-heading p { margin: 0; color: var(--text-soft); }
.decision-list { display: grid; gap: 14px; }
.decision-card { scroll-margin-top: 84px; padding: 18px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
.decision-heading { display: flex; justify-content: space-between; gap: 16px; }
.decision-heading h3 { margin: 3px 0 0; font: 700 1.2rem/1.25 var(--font-display); }
.decision-basis { color: var(--text-soft); }
.decision-card fieldset { display: grid; gap: 8px; margin: 12px 0; padding: 0; border: 0; }
.decision-card legend { margin-bottom: 8px; font-weight: 800; font-size: .78rem; color: var(--text-soft); }
.decision-option { display: flex; align-items: flex-start; gap: 10px; padding: 11px; border: 1px solid var(--line); border-radius: 9px; background: var(--canvas); cursor: pointer; }
.decision-option:has(input:checked) { border-color: var(--primary); background: var(--primary-soft); }
.decision-option input { margin-top: 4px; }
.recommended { display: inline-flex; margin-left: 8px; padding: .16rem .42rem; border-radius: 999px; color: var(--success); background: var(--success-soft); font-size: .67rem; font-weight: 800; }
.decision-meta { color: var(--text-soft); font-size: .8rem; }
.slice-list { display: grid; gap: 10px; }
.slice-card { display: grid; grid-template-columns: 42px 1fr auto; align-items: center; gap: 14px; padding: 15px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); text-decoration: none; color: var(--text); }
.slice-card:hover { border-color: var(--primary); box-shadow: var(--shadow); }
.slice-card-index { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; background: var(--primary-soft); color: var(--primary); font-weight: 850; }
.slice-card h3 { margin: 2px 0; font: 700 1.08rem/1.25 var(--font-display); }
.slice-card p { margin: 0; color: var(--text-soft); font-size: .8rem; }
.plan-details { margin-top: 24px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
.plan-details > summary { padding: 16px 18px; cursor: pointer; font-weight: 800; }
.plan-article { padding: 0 20px 24px; overflow-wrap: anywhere; }
.plan-article h2 { margin-top: 30px; font: 700 1.65rem/1.2 var(--font-display); border-bottom: 1px solid var(--line); padding-bottom: 7px; }
.plan-article h3 { margin-top: 23px; font: 700 1.2rem/1.25 var(--font-display); }
.plan-article blockquote { margin: 16px 0; padding: 12px 15px; border-left: 4px solid var(--primary); background: var(--primary-soft); }
.plan-article table { width: 100%; border-collapse: collapse; display: block; overflow-x: auto; }
.plan-article th, .plan-article td { min-width: 120px; padding: 9px; border: 1px solid var(--line); text-align: left; vertical-align: top; }
.plan-article th { background: var(--surface-soft); }
.plan-article code { padding: .12rem .3rem; border-radius: 4px; background: var(--surface-soft); }
.compact-article { padding: 0; }
.compact-article h2 { font-size: 1.25rem; }
.task-summary, .decision-summary { margin: 22px 0; padding: 18px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
.page-turn { display: flex; justify-content: space-between; margin-top: 24px; }
.site-footer { min-height: 44px; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding: 12px 24px; border-top: 1px solid var(--line); color: var(--text-soft); font-size: .76rem; background: var(--surface); }
.markdown-fallback { white-space: pre-wrap; }
@media (max-width: 980px) {
  .page-frame { grid-template-columns: 1fr; }
  .side-panel { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .cap-nav { grid-template-columns: repeat(auto-fit, minmax(190px,1fr)); }
  .slice-nav { grid-template-columns: repeat(auto-fit, minmax(230px,1fr)); }
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .site-header { padding: 0 14px; }
  .main-panel { padding: 20px 14px 50px; }
  .side-panel { padding: 16px 10px; }
  .hero-top, .callout { align-items: flex-start; flex-direction: column; }
  .review-progress { position: static; width: fit-content; margin: 8px 0; }
  .summary-grid { grid-template-columns: 1fr 1fr; }
  .slice-card { grid-template-columns: 34px 1fr; }
  .slice-card .status { grid-column: 2; }
}
@media print {
  .site-header, .side-panel, .site-footer, .review-toolbar, .page-turn { display: none !important; }
  .page-frame { display: block; }
  .main-panel { width: 100%; padding: 0; }
  details { display: block; }
  details > summary { display: none; }
  body { background: white; color: #10233d; }
}
'''


REVIEW_JS = r'''
(() => {
  const root = document.documentElement;
  const themeKey = "ro-planning-review-theme";
  const otherSentinel = "__OTHER__";
  const savedTheme = localStorage.getItem(themeKey);
  if (savedTheme === "dark" || savedTheme === "light") root.dataset.theme = savedTheme;
  else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) root.dataset.theme = "dark";

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      localStorage.setItem(themeKey, root.dataset.theme);
    });
  });

  const capabilityId = document.body.dataset.capabilityId;
  if (!capabilityId || document.body.dataset.pageType !== "capability") return;

  const cards = Array.from(document.querySelectorAll("[data-decision-id]"));
  const stateKey = `ro-planning-review:${capabilityId}`;
  const reviewer = document.querySelector("[data-reviewer-name]");
  const notes = document.querySelector("[data-review-notes]");
  const approvalIntent = document.querySelector("[data-approval-intent]");
  const selectedCount = document.querySelector("[data-selected-count]");
  const message = document.querySelector("[data-feedback-message]");

  const toggleOther = (card) => {
    const checked = card.querySelector("[data-decision-option]:checked");
    const field = card.querySelector("[data-other-option-field]");
    const input = card.querySelector("[data-decision-other]");
    const visible = Boolean(checked && checked.value === otherSentinel);
    if (field) field.classList.toggle("is-visible", visible);
    if (input) {
      input.required = visible;
      input.setAttribute("aria-hidden", visible ? "false" : "true");
    }
  };

  const readState = () => {
    try { return JSON.parse(localStorage.getItem(stateKey) || "{}"); }
    catch (_) { return {}; }
  };
  const state = readState();
  if (reviewer) reviewer.value = state.reviewer || "";
  if (notes) notes.value = state.notes || "";
  if (approvalIntent) approvalIntent.checked = Boolean(state.approval_intent);

  cards.forEach((card) => {
    const id = card.dataset.decisionId;
    const saved = state.decisions && state.decisions[id];
    if (saved) {
      const choice = Array.from(card.querySelectorAll("[data-decision-option]")).find((input) => input.value === saved.selected_option);
      if (choice) choice.checked = true;
      const other = card.querySelector("[data-decision-other]");
      if (other) other.value = saved.other_option || "";
      const rationale = card.querySelector("[data-decision-rationale]");
      if (rationale) rationale.value = saved.rationale || "";
    }
    toggleOther(card);
  });

  const collect = () => {
    const decisions = {};
    cards.forEach((card) => {
      const id = card.dataset.decisionId;
      const checked = card.querySelector("[data-decision-option]:checked");
      const other = card.querySelector("[data-decision-other]");
      const rationale = card.querySelector("[data-decision-rationale]");
      decisions[id] = {
        selected_option: checked ? checked.value : null,
        other_option: other ? other.value.trim() : "",
        recommendation: card.dataset.recommendation,
        rationale: rationale ? rationale.value.trim() : ""
      };
    });
    return {
      reviewer: reviewer ? reviewer.value.trim() : "",
      notes: notes ? notes.value.trim() : "",
      approval_intent: approvalIntent ? approvalIntent.checked : false,
      decisions
    };
  };

  const save = () => {
    cards.forEach(toggleOther);
    const value = collect();
    localStorage.setItem(stateKey, JSON.stringify(value));
    const count = Object.values(value.decisions).filter((item) => item.selected_option).length;
    if (selectedCount) selectedCount.textContent = String(count);
    return value;
  };

  document.addEventListener("input", (event) => {
    if (event.target.closest("[data-review-toolbar]") || event.target.closest("[data-decision-id]")) save();
  });
  document.addEventListener("change", (event) => {
    if (event.target.closest("[data-review-toolbar]") || event.target.closest("[data-decision-id]")) save();
  });

  const acceptButton = document.querySelector("[data-accept-recommendations]");
  if (acceptButton) acceptButton.addEventListener("click", () => {
    cards.forEach((card) => {
      const recommended = card.dataset.recommendation;
      const option = Array.from(card.querySelectorAll("[data-decision-option]")).find((input) => input.value === recommended);
      if (option) option.checked = true;
      const other = card.querySelector("[data-decision-other]");
      if (other) other.value = "";
      toggleOther(card);
    });
    save();
    if (message) message.textContent = "Recommended defaults restored. Review any intended overrides before capability approval.";
  });

  const clearButton = document.querySelector("[data-clear-decisions]");
  if (clearButton) clearButton.addEventListener("click", () => {
    cards.forEach((card) => {
      card.querySelectorAll("[data-decision-option]").forEach((input) => { input.checked = false; });
      const other = card.querySelector("[data-decision-other]");
      if (other) other.value = "";
      const rationale = card.querySelector("[data-decision-rationale]");
      if (rationale) rationale.value = "";
      toggleOther(card);
    });
    save();
    if (message) message.textContent = "Decision selections and draft overrides cleared.";
  });

  const exportButton = document.querySelector("[data-export-feedback]");
  if (exportButton) exportButton.addEventListener("click", () => {
    const value = save();
    const missing = Object.entries(value.decisions).filter(([, item]) => !item.selected_option).map(([id]) => id);
    const missingOther = Object.entries(value.decisions)
      .filter(([, item]) => item.selected_option === otherSentinel && !item.other_option)
      .map(([id]) => id);
    const alternativeWithoutRationale = Object.entries(value.decisions)
      .filter(([, item]) => item.selected_option && item.selected_option !== item.recommendation && !item.rationale)
      .map(([id]) => id);
    if (missing.length) {
      if (message) message.textContent = `Select an option for: ${missing.join(", ")}`;
      return;
    }
    if (missingOther.length) {
      if (message) message.textContent = `Enter a brief Other description for: ${missingOther.join(", ")}`;
      return;
    }
    if (alternativeWithoutRationale.length) {
      if (message) message.textContent = `Add detailed rationale for non-recommended selections: ${alternativeWithoutRationale.join(", ")}`;
      return;
    }
    const planHash = cards[0] ? cards[0].dataset.planHash : "";
    const payload = {
      schema_version: "1.1",
      document_type: "capability-decision-feedback",
      capability_id: capabilityId,
      capability_plan_sha256: planHash,
      reviewer: value.reviewer || null,
      reviewed_at: new Date().toISOString(),
      requested_action: value.approval_intent ? "approve-capability-and-slices" : "record-feedback",
      capability_notes: value.notes,
      decisions: Object.entries(value.decisions).map(([id, item]) => ({
        id,
        selected_option: item.selected_option,
        other_option: item.selected_option === otherSentinel ? item.other_option : null,
        accepted_recommendation: item.selected_option === item.recommendation,
        rationale: item.rationale || null
      }))
    };
    const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${capabilityId}-decision-feedback.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    if (message) message.textContent = `Downloaded ${anchor.download}. Apply it with planctl from the repository root.`;
  });

  save();
})();
'''


if __name__ == "__main__":
    raise SystemExit(main())
