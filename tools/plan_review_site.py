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
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from planctl import _git_blob, governed_experience_binding

try:
    import mistune  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - generated site still works with plain Markdown fallback
    mistune = None


SITE_SCHEMA_VERSION = "1.4"
REVIEW_INTERFACE_RELEASE = "1.4.0"
FEEDBACK_SCHEMA_VERSION = "1.1"
OTHER_SENTINEL = "__OTHER__"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def amendment_identity_sort_key(identity: str) -> int:
    """Return the immutable numeric sequence for a canonical Wave amendment ID."""

    match = re.fullmatch(r"W\d+\.A(\d+)", identity)
    return int(match.group(1)) if match else 10**9


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


def extract_task_section(markdown: str, task_id: str) -> str:
    heading = re.compile(rf"(?m)^###\s+(?:9\.\d+\s+)?`?{re.escape(task_id)}`?(?:\s+[-—].*)?\s*$")
    matches = list(heading.finditer(markdown))
    if len(matches) > 1:
        raise ValueError(f"Task plan contains duplicate headings for {task_id}")
    if not matches:
        return ""
    start = matches[0].start()
    following = re.search(r"(?m)^###\s+", markdown[matches[0].end() :])
    end = matches[0].end() + following.start() if following else len(markdown)
    return markdown[start:end].rstrip() + "\n"


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def task_page_name(task_id: str) -> str:
    if not re.fullmatch(r"CAP-\d+\.S\d+\.T\d+", task_id):
        raise ValueError(f"Unsafe or unsupported task identity: {task_id}")
    return f"{task_id}.html"


def task_worksheet_projection(repo: Path, task_id: str) -> dict[str, str] | None:
    task_page_name(task_id)
    relative = Path("artifacts") / "evidence" / f"{task_id}.task-start.md"
    worksheet = repo / relative
    if not worksheet.is_file():
        return None
    return {
        "path": relative.as_posix(),
        "sha256": sha256(worksheet),
        "markdown": worksheet.read_text(encoding="utf-8"),
    }


def markdown_renderer():
    if mistune is None:
        return lambda value: (
            "<pre class='markdown-fallback'>"
            + html.escape("\n".join(line.rstrip() for line in value.splitlines()))
            + "</pre>"
        )
    return mistune.create_markdown(escape=False, plugins=["table", "task_lists"])


MD = markdown_renderer()


def render_markdown(markdown: str) -> str:
    return MD(markdown)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def display_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def slice_alias(title: str) -> str:
    return f"SLICE-{display_slug(title)}"


def status_badge(status: str | None) -> str:
    label = status or "unknown"
    css = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f'<span class="status status-{esc(css)}">{esc(label.replace("-", " ").title())}</span>'


def delivery_status(tasks: list[dict[str, Any]], completion: dict[str, Any] | None = None) -> str:
    """Project authoritative task state into one deliberately coarse delivery label."""

    states = [str(task.get("status", "NOT_STARTED")) for task in tasks]
    if (completion or {}).get("status") == "APPROVED" or (states and all(state == "DONE" for state in states)):
        return "completed"
    if any(state not in {"NOT_STARTED", "READY"} for state in states):
        return "in-progress"
    return "not-started"


def status_stack(decision_status: str | None, execution_status: str) -> str:
    return (
        '<span class="status-stack" aria-label="Decision and completion status">'
        f"{status_badge(decision_status)}{status_badge(execution_status)}</span>"
    )


def task_review_projection(task: dict[str, Any]) -> dict[str, Any]:
    control = task.get("review_control")
    return {
        "task_id": task.get("id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "mode": "append-only" if isinstance(control, dict) else "latest-review-only",
        "latest_review": task.get("review") or {},
        "review_control": control if isinstance(control, dict) else None,
    }


def amendment_exit_projection(amendment: dict[str, Any]) -> dict[str, Any]:
    completion = amendment.get("completion") or {}
    control = completion.get("exit_review_control")
    return {
        "amendment_id": amendment.get("id"),
        "mode": "append-only" if isinstance(control, dict) else "latest-completion-only",
        "latest_completion": {
            key: completion.get(key) for key in ("status", "reviewer", "reviewed_at", "evidence", "notes")
        },
        "exit_review_control": control if isinstance(control, dict) else None,
    }


def amendment_adoption_checkpoints(amendment: dict[str, Any], waves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_wave = amendment.get("target_wave")
    wave = next((item for item in waves if item.get("id") == target_wave), {})
    projections: list[dict[str, Any]] = []
    for checkpoint in wave.get("checkpoints") or []:
        references = [
            reference
            for reference in checkpoint.get("evidence") or []
            if isinstance(reference, dict)
            and reference.get("type") == "amendment-adoption-evidence"
            and reference.get("amendment_id") == amendment.get("id")
        ]
        if references:
            projections.append(
                {
                    "id": checkpoint.get("id"),
                    "kind": checkpoint.get("kind"),
                    "recorded_by": checkpoint.get("recorded_by"),
                    "recorded_at": checkpoint.get("recorded_at"),
                    "notes": checkpoint.get("notes"),
                    "evidence_references": references,
                }
            )
    return projections


def _review_values(values: list[Any] | None) -> str:
    if not values:
        return "None"
    return ", ".join(f"<code>{esc(value)}</code>" for value in values)


def _submission_packet_html(task_id: str, packet: dict[str, Any], *, current: bool) -> str:
    evidence = packet.get("evidence_reference") or {}
    marker = "data-current-submission" if current else "data-review-attempt"
    identity = f"{task_id}:{packet.get('id')}"
    heading = "Current immutable submission awaiting review" if current else "Immutable submission packet"
    return f"""
<section class="plan-details" {marker}="{esc(identity)}" data-packet-sha256="{esc(packet.get("packet_sha256"))}">
  <h4>{esc(heading)} <code>{esc(packet.get("id"))}</code></h4>
  <dl class="summary-grid"><div><dt>Packet SHA-256</dt><dd><code>{esc(packet.get("packet_sha256"))}</code></dd></div><div><dt>Candidate / base</dt><dd><code>{esc(packet.get("candidate_commit"))}</code> / <code>{esc(packet.get("base_commit"))}</code></dd></div><div><dt>Submitted</dt><dd>{esc(packet.get("submitted_by"))} at <code>{esc(packet.get("submitted_at"))}</code></dd></div><div><dt>Branch</dt><dd><code>{esc(packet.get("branch"))}</code></dd></div></dl>
  <p><strong>Evidence:</strong> <code>{esc(evidence.get("path"))}</code> · SHA-256 <code>{esc(evidence.get("sha256"))}</code> · commit <code>{esc(evidence.get("commit"))}</code></p>
  <p><strong>Frozen criteria / selection:</strong> <code>{esc(packet.get("acceptance_criteria_sha256"))}</code> / <code>{esc(packet.get("selection_sha256"))}</code></p>
  <p><strong>Changed paths:</strong> {_review_values(packet.get("changed_paths"))}</p>
  <p><strong>Selected checks:</strong> {_review_values(packet.get("selected_checks"))}</p>
  <p><strong>Deferred checks:</strong> {_review_values(packet.get("deferred_checks"))}</p>
  <p><strong>Selection rationale:</strong> {esc(packet.get("selection_rationale"))}</p>
  <p><strong>Prior round / replayed open findings:</strong> <code>{esc(packet.get("prior_attempt_id") or "None")}</code> / {_review_values(packet.get("open_finding_ids"))}</p>
  <p><strong>Root-cause escalation:</strong> {esc(packet.get("root_cause_analysis") or "Not required")}</p>
</section>"""


def task_review_history_html(task: dict[str, Any]) -> str:
    task_id = str(task.get("id") or "unknown-task")
    review = task.get("review") or {}
    control = task.get("review_control")
    if not isinstance(control, dict):
        return f"""
<section class="review-toolbar" data-task-review-id="{esc(task_id)}" data-review-mode="latest-review-only">
  <h3>{esc(task_id)} — {esc(task.get("title"))}</h3>
  <p><strong>Legacy latest-review-only projection.</strong> No append-only review rounds are recorded; this view does not fabricate historical attempts.</p>
  <dl class="summary-grid" data-current-review-projection="{esc(task_id)}" data-current-review-result="{esc(review.get("result") or "not-reviewed")}" data-current-reviewer="{esc(review.get("reviewer") or "none")}" data-current-reviewed-at="{esc(review.get("reviewed_at") or "none")}"><div><dt>Task status</dt><dd>{esc(task.get("status"))}</dd></div><div><dt>Latest result</dt><dd>{esc(review.get("result") or "not reviewed")}</dd></div><div><dt>Reviewer</dt><dd>{esc(review.get("reviewer") or "none")}</dd></div><div><dt>Reviewed at</dt><dd><code>{esc(review.get("reviewed_at") or "none")}</code></dd></div></dl>
  <p><strong>Latest notes:</strong> {esc(review.get("notes") or "None")}</p>
</section>"""

    attempts = control.get("attempts") or []
    open_findings: dict[str, dict[str, Any]] = {}
    rendered_attempts: list[str] = []
    for attempt in attempts:
        packet = attempt.get("submission") or {}
        attempt_id = str(packet.get("id") or "unknown-round")
        attempt_review = attempt.get("review") or {}
        ledger = attempt.get("ledger") or {}
        closures = attempt.get("closures") or []
        findings = attempt.get("findings") or []
        for closure in closures:
            open_findings.pop(str(closure.get("finding_id")), None)
        for finding in findings:
            open_findings[str(finding.get("id"))] = finding
        finding_rows = "".join(
            f'<li data-review-finding="{esc(task_id)}:{esc(attempt_id)}:{esc(finding.get("id"))}"><strong>{esc(finding.get("id"))} · {esc(finding.get("severity"))} · criterion {esc(finding.get("criterion_index"))}</strong> — {esc(finding.get("title"))}<br><small>Reproduce: {esc(finding.get("reproduction"))}<br>Required remediation: {esc(finding.get("required_remediation"))}<br>Blocking: {esc(finding.get("blocking"))}</small></li>'
            for finding in findings
        )
        closure_rows = "".join(
            f'<li data-review-closure="{esc(task_id)}:{esc(attempt_id)}:{esc(closure.get("finding_id"))}"><strong>{esc(closure.get("finding_id"))} · {esc(closure.get("disposition"))}</strong> — {esc(closure.get("evidence"))}</li>'
            for closure in closures
        )
        rendered_attempts.append(
            f"""
<article class="review-toolbar" data-review-round="{esc(task_id)}:{esc(attempt_id)}">
  <h3>Review round {esc(attempt_id)}</h3>
{_submission_packet_html(task_id, packet, current=False)}
  <dl class="summary-grid"><div><dt>Disposition</dt><dd>{esc(attempt_review.get("result"))}</dd></div><div><dt>Reviewer</dt><dd>{esc(attempt_review.get("reviewer"))}</dd></div><div><dt>Reviewed at</dt><dd><code>{esc(attempt_review.get("reviewed_at"))}</code></dd></div><div data-review-ledger="{esc(task_id)}:{esc(attempt_id)}" data-ledger-sha256="{esc(ledger.get("sha256"))}"><dt>Immutable ledger</dt><dd><code>{esc(ledger.get("path"))}</code><br><code>{esc(ledger.get("sha256"))}</code></dd></div></dl>
  <p><strong>Review notes:</strong> {esc(attempt_review.get("notes") or "None")}</p>
  <h4>Findings opened in this round</h4><ul class="gate-criteria">{finding_rows or "<li>None</li>"}</ul>
  <h4>Prior findings closed in this round</h4><ul class="gate-criteria">{closure_rows or "<li>None</li>"}</ul>
</article>"""
        )
    current = control.get("current_submission")
    current_html = _submission_packet_html(task_id, current, current=True) if isinstance(current, dict) else ""
    return f"""
<section data-task-review-id="{esc(task_id)}" data-review-mode="append-only">
  <div class="section-heading"><span class="eyebrow">Immutable task review history</span><h3>{esc(task_id)} — {esc(task.get("title"))}</h3><p>Completed rounds remain append-only. The latest legacy review object below is a labeled current projection, not a replacement for this history.</p></div>
{"".join(rendered_attempts) or "<p>No completed review round is recorded.</p>"}
{current_html}
  <section class="review-toolbar" data-current-review-projection="{esc(task_id)}" data-current-review-result="{esc(review.get("result") or "not-reviewed")}" data-current-reviewer="{esc(review.get("reviewer") or "none")}" data-current-reviewed-at="{esc(review.get("reviewed_at") or "none")}"><h4>Current latest-review projection</h4><dl class="summary-grid"><div><dt>Task status</dt><dd>{esc(task.get("status"))}</dd></div><div><dt>Latest result</dt><dd>{esc(review.get("result") or "not reviewed")}</dd></div><div><dt>Reviewer</dt><dd>{esc(review.get("reviewer") or "none")}</dd></div><div><dt>Reviewed at</dt><dd><code>{esc(review.get("reviewed_at") or "none")}</code></dd></div></dl><p><strong>Latest notes:</strong> {esc(review.get("notes") or "None")}</p><p><strong>Currently open findings:</strong> {_review_values(sorted(open_findings))}</p></section>
</section>"""


def _amendment_exit_submission_html(amendment_id: str, packet: dict[str, Any], *, current: bool) -> str:
    evidence = packet.get("evidence_reference") or {}
    marker = "data-exit-current-submission" if current else "data-exit-review-attempt"
    identity = f"{amendment_id}:{packet.get('id')}"
    heading = "Current immutable exit submission awaiting review" if current else "Immutable amendment-exit packet"
    return f"""
<section class="plan-details" {marker}="{esc(identity)}" data-exit-packet-sha256="{esc(packet.get("packet_sha256"))}" data-exit-evidence-amendment="{esc(evidence.get("amendment_id"))}" data-exit-evidence-path="{esc(evidence.get("path"))}" data-exit-evidence-sha256="{esc(evidence.get("sha256"))}" data-exit-evidence-commit="{esc(evidence.get("commit"))}">
  <h4>{esc(heading)} <code>{esc(packet.get("id"))}</code></h4>
  <dl class="summary-grid"><div><dt>Packet SHA-256</dt><dd><code>{esc(packet.get("packet_sha256"))}</code></dd></div><div><dt>Candidate / declared candidate</dt><dd><code>{esc(packet.get("candidate_commit"))}</code> / <code>{esc(packet.get("declared_candidate_commit"))}</code></dd></div><div><dt>Submitted</dt><dd>{esc(packet.get("submitted_by"))} at <code>{esc(packet.get("submitted_at"))}</code></dd></div><div><dt>Branch</dt><dd><code>{esc(packet.get("branch"))}</code></dd></div></dl>
  <p><strong>Bound exit evidence:</strong> amendment <code>{esc(evidence.get("amendment_id"))}</code> · <code>{esc(evidence.get("path"))}</code> · SHA-256 <code>{esc(evidence.get("sha256"))}</code> · commit <code>{esc(evidence.get("commit"))}</code></p>
  <p><strong>Frozen criteria / selected-check hashes:</strong> <code>{esc(packet.get("acceptance_criteria_sha256"))}</code> / <code>{esc(packet.get("selected_checks_sha256"))}</code></p>
  <p><strong>Selected checks:</strong> {_review_values(packet.get("selected_checks"))}</p>
  <p><strong>Prior round / replayed open findings:</strong> <code>{esc(packet.get("prior_attempt_id") or "None")}</code> / {_review_values(packet.get("open_finding_ids"))}</p>
</section>"""


def amendment_exit_review_html(amendment: dict[str, Any], adoption_checkpoints: list[dict[str, Any]]) -> str:
    amendment_id = str(amendment.get("id") or "unknown-amendment")
    completion = amendment.get("completion") or {}
    control = completion.get("exit_review_control")
    completion_attributes = (
        f'data-latest-completion-status="{esc(completion.get("status") or "PENDING")}" '
        f'data-latest-completion-reviewer="{esc(completion.get("reviewer") or "none")}" '
        f'data-latest-completion-reviewed-at="{esc(completion.get("reviewed_at") or "none")}" '
        f'data-latest-completion-notes="{esc(completion.get("notes") or "none")}"'
    )
    completion_evidence_html = "".join(
        f'<code data-latest-completion-evidence="{esc(amendment_id)}:{index}">{esc(reference)}</code>'
        for index, reference in enumerate(completion.get("evidence") or [], start=1)
    )
    if not isinstance(control, dict):
        history_html = """
  <p><strong>Legacy latest-completion-only projection.</strong> No immutable amendment-exit rounds are recorded; this view does not fabricate exit-review history.</p>"""
        mode = "latest-completion-only"
    else:
        mode = "append-only"
        rendered_attempts: list[str] = []
        open_findings: dict[str, dict[str, Any]] = {}
        for attempt in control.get("attempts") or []:
            packet = attempt.get("submission") or {}
            attempt_id = str(packet.get("id") or "unknown-round")
            review = attempt.get("review") or {}
            ledger = attempt.get("ledger") or {}
            closures = attempt.get("closures") or []
            findings = attempt.get("findings") or []
            for closure in closures:
                open_findings.pop(str(closure.get("finding_id")), None)
            for finding in findings:
                open_findings[str(finding.get("id"))] = finding
            finding_rows = "".join(
                f'<li data-exit-review-finding="{esc(amendment_id)}:{esc(attempt_id)}:{esc(finding.get("id"))}"><strong>{esc(finding.get("id"))} · {esc(finding.get("severity"))} · criterion {esc(finding.get("criterion_index"))}</strong> — {esc(finding.get("title"))}<br><small>Reproduce: {esc(finding.get("reproduction"))}<br>Required remediation: {esc(finding.get("required_remediation"))}<br>Blocking: {esc(finding.get("blocking"))}</small></li>'
                for finding in findings
            )
            closure_rows = "".join(
                f'<li data-exit-review-closure="{esc(amendment_id)}:{esc(attempt_id)}:{esc(closure.get("finding_id"))}"><strong>{esc(closure.get("finding_id"))} · {esc(closure.get("disposition"))}</strong> — {esc(closure.get("evidence"))}</li>'
                for closure in closures
            )
            rendered_attempts.append(
                f"""
<article class="review-toolbar" data-exit-review-round="{esc(amendment_id)}:{esc(attempt_id)}" data-reviewed-state-commit="{esc(review.get("reviewed_state_commit"))}">
  <h3>Amendment-exit review round {esc(attempt_id)}</h3>
{_amendment_exit_submission_html(amendment_id, packet, current=False)}
  <dl class="summary-grid"><div><dt>Disposition</dt><dd>{esc(review.get("result"))}</dd></div><div><dt>Reviewer</dt><dd>{esc(review.get("reviewer"))}</dd></div><div><dt>Reviewed state commit</dt><dd><code>{esc(review.get("reviewed_state_commit"))}</code></dd></div><div data-exit-review-ledger="{esc(amendment_id)}:{esc(attempt_id)}" data-exit-ledger-sha256="{esc(ledger.get("sha256"))}"><dt>Immutable ledger</dt><dd><code>{esc(ledger.get("path"))}</code><br><code>{esc(ledger.get("sha256"))}</code></dd></div></dl>
  <p><strong>Reviewed at / notes:</strong> <code>{esc(review.get("reviewed_at"))}</code> · {esc(review.get("notes") or "None")}</p>
  <h4>Findings opened in this round</h4><ul class="gate-criteria">{finding_rows or "<li>None</li>"}</ul>
  <h4>Prior findings closed in this round</h4><ul class="gate-criteria">{closure_rows or "<li>None</li>"}</ul>
</article>"""
            )
        current = control.get("current_submission")
        current_html = (
            _amendment_exit_submission_html(amendment_id, current, current=True) if isinstance(current, dict) else ""
        )
        history_html = (
            f'<div class="section-heading"><span class="eyebrow">Immutable amendment-exit history</span>'
            f"<p>Append-only v{esc(control.get('version'))}; completed rounds are not replaced by the latest completion projection.</p></div>"
            f"{''.join(rendered_attempts) or '<p>No completed amendment-exit round is recorded.</p>'}"
            f"{current_html}"
            f"<p><strong>Currently open exit findings:</strong> {_review_values(sorted(open_findings))}</p>"
        )

    checkpoint_html: list[str] = []
    for checkpoint in adoption_checkpoints:
        references = "".join(
            f'<li data-adoption-evidence="{esc(amendment_id)}:{esc(checkpoint.get("id"))}:{esc(index)}" data-adoption-evidence-amendment="{esc(reference.get("amendment_id"))}" data-adoption-evidence-sha256="{esc(reference.get("sha256"))}" data-adoption-evidence-commit="{esc(reference.get("commit"))}"><code>{esc(reference.get("path"))}</code> · SHA-256 <code>{esc(reference.get("sha256"))}</code> · commit <code>{esc(reference.get("commit"))}</code></li>'
            for index, reference in enumerate(checkpoint.get("evidence_references") or [], start=1)
        )
        checkpoint_html.append(
            f'<article class="plan-details" data-adoption-checkpoint="{esc(amendment_id)}:{esc(checkpoint.get("id"))}"><h4>Adoption checkpoint <code>{esc(checkpoint.get("id"))}</code></h4><p>{esc(checkpoint.get("kind"))} · {esc(checkpoint.get("recorded_by"))} at <code>{esc(checkpoint.get("recorded_at"))}</code></p><ul class="gate-criteria">{references}</ul><p><strong>Notes:</strong> {esc(checkpoint.get("notes") or "None")}</p></article>'
        )
    return f"""
<section data-amendment-exit-id="{esc(amendment_id)}" data-exit-review-mode="{esc(mode)}">
  <div class="section-heading"><span class="eyebrow">Amendment exit and adoption</span><h2>Independent amendment-exit review</h2></div>
{history_html}
  <section class="review-toolbar" data-latest-completion-projection="{esc(amendment_id)}" {completion_attributes}><h3>Latest completion projection</h3><dl class="summary-grid"><div><dt>Status</dt><dd>{esc(completion.get("status") or "PENDING")}</dd></div><div><dt>Reviewer</dt><dd>{esc(completion.get("reviewer") or "none")}</dd></div><div><dt>Reviewed at</dt><dd><code>{esc(completion.get("reviewed_at") or "none")}</code></dd></div><div><dt>Evidence</dt><dd>{completion_evidence_html or "None"}</dd></div></dl><p><strong>Latest notes:</strong> {esc(completion.get("notes") or "None")}</p></section>
  <div class="section-heading"><span class="eyebrow">Bound Wave checkpoint evidence</span><h3>Adoption checkpoints</h3><p>These typed references are retained separately from exit-review evidence and do not rewrite completion history.</p></div>
{"".join(checkpoint_html) or "<p>No bound amendment-adoption checkpoint is recorded.</p>"}
</section>"""


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
    <a class="brand" href="{"../" * depth}index.html" aria-label="Planning review home">
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
            f'<a class="nav-item{cls}" href="{href}"><span>{esc(cap["alias"])}</span>'
            f"<small>{esc(cid)} · {esc(cap['title'])}</small></a>"
        )
    return "<nav class='cap-nav' aria-label='Capabilities'>" + "".join(items) + "</nav>"


def wave_nav(waves: list[dict[str, Any]], active: str | None, prefix: str = "") -> str:
    items = []
    for wave in waves:
        wave_id = str(wave["id"])
        cls = " active" if wave_id == active else ""
        items.append(
            f'<a class="nav-item{cls}" href="{prefix}{esc(wave_id)}.html"><span>{esc(wave_id)}</span>'
            f"<small>{esc(wave.get('title'))}</small></a>"
        )
    return "<nav class='cap-nav' aria-label='Waves'>" + "".join(items) + "</nav>"


def planning_nav(
    *,
    capabilities: list[dict[str, Any]],
    waves: list[dict[str, Any]],
    active_capability: str | None,
    active_wave: str | None,
    capability_prefix: str,
    wave_prefix: str,
    default_tab: str,
) -> str:
    if default_tab not in {"capabilities", "waves"}:
        raise ValueError(f"Unsupported planning navigation tab: {default_tab}")
    capability_selected = "true" if default_tab == "capabilities" else "false"
    wave_selected = "true" if default_tab == "waves" else "false"
    capability_hidden = "" if default_tab == "capabilities" else " hidden"
    wave_hidden = "" if default_tab == "waves" else " hidden"
    return f"""
<div class="planning-nav" data-planning-nav data-default-tab="{esc(default_tab)}">
  <div class="planning-nav-tabs" role="tablist" aria-label="Planning views">
    <button id="planning-tab-capabilities" class="planning-nav-tab" type="button" role="tab" aria-selected="{capability_selected}" aria-controls="planning-panel-capabilities" data-nav-tab="capabilities">Capabilities</button>
    <button id="planning-tab-waves" class="planning-nav-tab" type="button" role="tab" aria-selected="{wave_selected}" aria-controls="planning-panel-waves" data-nav-tab="waves">Waves</button>
  </div>
  <section id="planning-panel-capabilities" class="planning-nav-panel" role="tabpanel" aria-labelledby="planning-tab-capabilities" data-nav-panel="capabilities"{capability_hidden}>
    {capability_nav(capabilities, active_capability, prefix=capability_prefix)}
  </section>
  <section id="planning-panel-waves" class="planning-nav-panel" role="tabpanel" aria-labelledby="planning-tab-waves" data-nav-panel="waves"{wave_hidden}>
    {wave_nav(waves, active_wave, prefix=wave_prefix)}
  </section>
</div>
"""


def slice_nav(slices: list[dict[str, Any]], active: str | None) -> str:
    rows = []
    for index, sl in enumerate(slices, start=1):
        sid = sl["slice_id"]
        cls = " active" if sid == active else ""
        rows.append(
            f'<a class="slice-nav-item{cls}" href="{esc(sl["page_name"])}"><b>{index}</b><span>'
            f"<strong>{esc(sl['alias'])}</strong><small>{esc(sid)} · {esc(sl['title'])}</small></span></a>"
        )
    return "<h2>Capability slices</h2><nav class='slice-nav'>" + "".join(rows) + "</nav>"


def task_nav(tasks: list[dict[str, Any]], active: str | None) -> str:
    rows = []
    for index, task in enumerate(tasks, start=1):
        task_id = str(task["task_id"])
        cls = " active" if task_id == active else ""
        rows.append(
            f'<a class="slice-nav-item{cls}" href="{esc(task["page_name"])}"><b>{index}</b><span>'
            f"<strong>{esc(task_id)}</strong><small>{esc(task['title'])}</small></span></a>"
        )
    return "<h2>Slice tasks</h2><nav class='slice-nav task-nav'>" + "".join(rows) + "</nav>"


def task_worksheet_html(worksheet: dict[str, str] | None, task_id: str) -> str:
    if worksheet is None:
        return (
            f'<p class="decision-meta" data-task-worksheet-absent="{esc(task_id)}">'
            "No optional task-start worksheet is assigned. This does not block execution.</p>"
        )
    return f"""
<details class="plan-details task-worksheet" open data-task-worksheet="{esc(task_id)}" data-worksheet-sha256="{esc(worksheet["sha256"])}">
  <summary>Assigned task-start worksheet</summary>
  <div class="worksheet-meta"><strong>Source:</strong> <code>{esc(worksheet["path"])}</code> · <strong>SHA-256:</strong> <code>{esc(worksheet["sha256"])}</code></div>
  <article class="plan-article">{render_markdown(worksheet["markdown"])}</article>
</details>"""


def task_values_html(values: list[Any] | None, *, empty: str = "None") -> str:
    if not values:
        return f"<p>{esc(empty)}</p>"
    return '<ul class="gate-criteria">' + "".join(f"<li>{esc(value)}</li>" for value in values) + "</ul>"


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
    <div><span class="eyebrow">{esc(did)}</span><h3>{esc(decision.get("title"))}</h3></div>
    {status_badge(decision.get("status"))}
  </div>
  <p class="decision-basis">{esc(decision.get("recommendation_basis"))}</p>
  <fieldset><legend>Resolved selection (change only to override)</legend>{"".join(options)}</fieldset>
  <label class="field-label">Detailed feedback, rationale, or implementation conditions
    <textarea rows="4" data-decision-rationale placeholder="Optional for the recommendation; required for any override, including Other."></textarea>
  </label>
  <p class="decision-meta">Binding Wave approval(s): <code>{esc(", ".join(decision.get("binding_waves") or []) or "Classification required")}</code> · Required ADR: <code>{esc(decision.get("required_adr") or "None currently identified")}</code></p>
</section>
"""


def classified_decisions(
    decisions: list[dict[str, Any]], wave_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    current = int(wave_id[1:])
    binding: list[dict[str, Any]] = []
    inherited: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []
    for decision in decisions:
        waves = decision.get("binding_waves") or []
        if not waves:
            unclassified.append(decision)
        elif wave_id in waves:
            binding.append(decision)
        elif all(int(str(item)[1:]) > current for item in waves):
            future.append(decision)
        else:
            inherited.append(decision)
    return binding, inherited, future, unclassified


def wave_decision_rows(decisions: list[dict[str, Any]], *, context: str) -> str:
    return "".join(
        f"<li><span><strong>{esc(decision.get('title'))}</strong><small>{esc(context)} · "
        f"Wave(s): {esc(', '.join(decision.get('binding_waves') or []) or 'unclassified')} · Selected: "
        f"{esc(decision.get('selected_option') or 'Pending')}</small></span>"
        f"{status_badge(decision.get('status'))}</li>"
        for decision in decisions
    )


def repository_file(repo: Path, relative: str, *, label: str) -> Path:
    """Resolve a declared review source without allowing a path escape."""
    if not relative or "\\" in relative or ":" in relative or re.search(r"(?:^|/)\.{1,2}(?:/|$)", relative):
        raise ValueError(f"{label} is not a canonical repository-relative POSIX path: {relative}")
    parts = Path(relative).parts
    if Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} contains an absolute or dot-segment path: {relative}")
    current = repo
    junction = getattr(os.path, "isjunction", lambda _path: False)
    for part in parts:
        current = current / part
        if (current.exists() or current.is_symlink()) and (current.is_symlink() or junction(current)):
            raise ValueError(f"{label} traverses a symlink or junction: {relative}")
    candidate = (repo / relative).resolve(strict=True)
    try:
        candidate.relative_to(repo.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"{label} escapes repository: {relative}") from exc
    if not candidate.is_file():
        raise ValueError(f"{label} is not a file: {relative}")
    return candidate


def load_enabler_change_requests(repo: Path, backlog: dict[str, Any]) -> list[dict[str, Any]]:
    """Load hash-bound ECR sources without flattening proposal and execution state."""

    approval_by_change: dict[str, tuple[Path, dict[str, Any]]] = {}
    approval_dir = repo / "planning/wave-amendment-approvals"
    for approval_source_path in sorted(approval_dir.glob("W*.A*.json")) if approval_dir.exists() else []:
        approval_source = json.loads(approval_source_path.read_text(encoding="utf-8"))
        change_id = approval_source.get("changeRequestId")
        if not isinstance(change_id, str) or not change_id:
            continue
        if change_id in approval_by_change:
            raise ValueError(f"Duplicate Wave-amendment approval records for {change_id}")
        approval_by_change[change_id] = (approval_source_path, approval_source)

    amendment_by_change = {
        str(amendment["change_request_id"]): amendment
        for amendment in backlog.get("wave_amendments", [])
        if isinstance(amendment, dict) and amendment.get("change_request_id")
    }
    records: list[dict[str, Any]] = []
    waves = backlog.get("waves") or []
    packet_dir = repo / "planning/enabler-change-requests"
    for packet_path in sorted(packet_dir.glob("ECR-*.packet.json")) if packet_dir.exists() else []:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        change_id = str(packet.get("changeRequestId") or "")
        if not change_id or packet_path.name != f"{change_id}.packet.json":
            raise ValueError(f"ECR packet identity/path mismatch: {packet_path}")
        declared_files: dict[str, dict[str, Any]] = {}
        for item in packet.get("files", []):
            relative = str(item.get("path") or "")
            source = repository_file(repo, relative, label=f"{change_id} declared source")
            actual = sha256(source)
            expected = str(item.get("sha256") or "").lower()
            if actual != expected:
                raise ValueError(f"{change_id} declared source hash mismatch: {relative}")
            declared_files[str(item.get("role") or relative)] = {
                "path": relative,
                "sha256": actual,
            }

        proposal = declared_files.get("canonical-proposal")
        review = declared_files.get("human-review")
        if proposal is None or review is None:
            raise ValueError(f"{change_id} must declare canonical-proposal and human-review files")

        governed_experience = dict(packet.get("governedExperience") or {})
        governed_experience_files: list[dict[str, Any]] = []
        reference_approval_status = "not-bound"
        governed_file_inventory = governed_experience.get("files") or []
        experience_binding, governed_file_errors = governed_experience_binding(repo, packet)
        if governed_file_errors:
            raise ValueError(governed_file_errors[0])
        for item in governed_file_inventory:
            relative = str(item.get("path") or "")
            expected = str(item.get("sha256") or "").lower()
            bound_file = {"path": relative, "sha256": expected}
            historical = bool(experience_binding) and relative.startswith("design/ui-reference/")
            source = (
                repo / relative
                if historical
                else repository_file(repo, relative, label=f"{change_id} governed experience")
            )
            if historical:
                bound_file["sourceCommit"] = experience_binding["packetCommit"]
            governed_experience_files.append(bound_file)
            if source.name == "APPROVAL.yaml":
                source_bytes = (
                    _git_blob(repo, experience_binding["packetCommit"], relative) if historical else source.read_bytes()
                )
                approval_record = yaml.safe_load(source_bytes or b"")
                if isinstance(approval_record, dict) and approval_record.get("reference_id") == governed_experience.get(
                    "referenceId"
                ):
                    reference_approval_status = str(approval_record.get("status") or "unknown").lower()
        governed_experience["files"] = governed_experience_files
        governed_experience["referenceApprovalStatus"] = reference_approval_status
        if experience_binding:
            governed_experience["sourceBinding"] = experience_binding

        packet_relative = packet_path.relative_to(repo).as_posix()
        packet_hash = sha256(packet_path)
        approval_tuple = approval_by_change.get(change_id)
        approval_path: Path | None = None
        approval: dict[str, Any] | None = None
        approval_hash: str | None = None
        if approval_tuple:
            approval_path, approval = approval_tuple
            approval_hash = sha256(approval_path)
            approved_packet = approval.get("packet") or {}
            if approved_packet.get("path") != packet_relative or approved_packet.get("sha256") != packet_hash:
                raise ValueError(f"{change_id} approval does not bind the current packet bytes")
            if (
                approved_packet.get("proposalPath") != proposal["path"]
                or approved_packet.get("proposalSha256") != proposal["sha256"]
            ):
                raise ValueError(f"{change_id} approval does not bind the current proposal bytes")

        amendment = amendment_by_change.get(change_id)
        lifecycle_status = ((amendment or {}).get("lifecycle") or {}).get("status")
        bootstrap = (amendment or {}).get("bootstrap") or {}
        bootstrap_status = bootstrap.get("status")
        campaign_status = ((amendment or {}).get("campaign") or {}).get("status")
        bootstrap_id = str((packet.get("bootstrapUnit") or {}).get("id") or "")
        scope_addenda: list[dict[str, Any]] = []
        for addendum_path in sorted(approval_dir.glob(f"{bootstrap_id}.addendum-*.json")):
            addendum = json.loads(addendum_path.read_text(encoding="utf-8"))
            if (
                addendum.get("status") != "APPROVED"
                or addendum.get("amendmentId") != packet.get("proposedAmendmentId")
                or addendum.get("bootstrapUnit") != bootstrap_id
            ):
                raise ValueError(f"{change_id} bootstrap scope-addendum identity/status mismatch")
            scope_addenda.append(
                {
                    "path": addendum_path.relative_to(repo).as_posix(),
                    "sha256": sha256(addendum_path),
                    "approved_by": addendum.get("approvedBy"),
                    "approved_at": addendum.get("approvedAt"),
                    "authorized_additional_paths": addendum.get("authorizedAdditionalPaths") or [],
                }
            )
        bootstrap_attempts = [dict(item) for item in bootstrap.get("attempts", [])]
        if bootstrap:
            bootstrap_attempts.append(
                {
                    "id": f"R{len(bootstrap_attempts) + 1:02d}",
                    "implementer": bootstrap.get("implementer"),
                    "implementation_commit": bootstrap.get("implementation_commit"),
                    "evidence": bootstrap.get("evidence") or [],
                    "review": bootstrap.get("review") or {},
                    "current_status": bootstrap_status,
                }
            )
        records.append(
            {
                "change_request_id": change_id,
                "amendment_id": packet.get("proposedAmendmentId"),
                "target_wave": packet.get("targetWave"),
                "classification": packet.get("classification"),
                "proposal_status": packet.get("status"),
                "proposal_execution_state": packet.get("executionState"),
                "packet_path": packet_relative,
                "packet_sha256": packet_hash,
                "proposal_path": proposal["path"],
                "proposal_sha256": proposal["sha256"],
                "review_path": review["path"],
                "review_sha256": review["sha256"],
                "approval_path": approval_path.relative_to(repo).as_posix() if approval_path else None,
                "approval_sha256": approval_hash,
                "approval_status": (approval or {}).get("status", "PENDING"),
                "approved_by": (approval or {}).get("approvedBy"),
                "approved_at": (approval or {}).get("approvedAt"),
                "authority": packet.get("authority") or {},
                "authority_chain": packet.get("authorityChain") or {},
                "migration_authority": packet.get("migrationAuthority") or {},
                "effective_base": (approval or {}).get("effectiveBase") or {},
                "bootstrap_unit": bootstrap_id,
                "bootstrap_attempts": bootstrap_attempts,
                "scope_addenda": scope_addenda,
                "slice_contributions": packet.get("sliceContributions") or [],
                "authorized_task_ids": packet.get("authorizedTaskIds") or [],
                "task_inventory": packet.get("taskInventory") or [],
                "refactor_budget": packet.get("refactorBudget") or {},
                "governed_experience": governed_experience,
                "task_reviews": [task_review_projection(task) for task in (amendment or {}).get("tasks", [])],
                "exit_review": amendment_exit_projection(amendment or {"id": packet.get("proposedAmendmentId")}),
                "adoption_checkpoints": amendment_adoption_checkpoints(amendment or {}, waves),
                "acceptance_criteria": packet.get("acceptanceCriteria") or [],
                "rollback": packet.get("rollback") or [],
                "lifecycle_status": lifecycle_status or "NOT_MATERIALIZED",
                "bootstrap_status": bootstrap_status or "NOT_SUBMITTED",
                "campaign_status": campaign_status or "NONE",
                "amendment": amendment,
                "packet": packet,
                "page": f"enablers/{change_id}.html",
            }
        )
    return records


def enabler_interrupts_wave(record: dict[str, Any], wave: dict[str, Any]) -> bool:
    if record.get("target_wave") != wave.get("id") or record.get("approval_status") != "APPROVED":
        return False
    if record.get("lifecycle_status") in {"ADOPTED", "DEFERRED", "WITHDRAWN"}:
        return False
    if record.get("lifecycle_status") != "NOT_MATERIALIZED":
        return True
    campaign = wave.get("campaign") or {}
    return campaign.get("status") == "PAUSED" and record.get("classification") == "gate-integrity-safety-defect"


def load_recovery_holds(repo: Path, backlog: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for hold in (backlog.get("control_plane") or {}).get("recovery_holds", []):
        request_id = str(hold.get("recovery_request_id") or "")
        packet_reference = hold.get("packet_reference") or {}
        approval_reference = hold.get("approval_reference") or {}
        packet_path = repository_file(repo, str(packet_reference.get("path") or ""), label=f"{request_id} packet")
        approval_path = repository_file(repo, str(approval_reference.get("path") or ""), label=f"{request_id} approval")
        if sha256(packet_path) != packet_reference.get("sha256") or sha256(approval_path) != approval_reference.get(
            "sha256"
        ):
            raise ValueError(f"{request_id} recovery authority hash mismatch")
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        if (
            packet.get("recoveryRequestId") != request_id
            or approval.get("recoveryRequestId") != request_id
            or (packet.get("controlHold") or {}).get("id") != hold.get("id")
        ):
            raise ValueError(f"{request_id} recovery identity mismatch")
        proposal_relative = str((approval.get("packet") or {}).get("proposalPath") or "")
        review_relative = str((approval.get("packet") or {}).get("reviewPath") or "")
        proposal_path = repository_file(repo, proposal_relative, label=f"{request_id} proposal")
        review_path = repository_file(repo, review_relative, label=f"{request_id} human review")
        if sha256(proposal_path) != (approval.get("packet") or {}).get("proposalSha256") or sha256(review_path) != (
            approval.get("packet") or {}
        ).get("reviewSha256"):
            raise ValueError(f"{request_id} recovery proposal/review hash mismatch")
        supplements = []
        for supplement in hold.get("supplements", []):
            supplement_id = str(supplement.get("id") or "")
            supplement_packet_reference = supplement.get("packet_reference") or {}
            supplement_approval_reference = supplement.get("approval_reference") or {}
            supplement_packet_path = repository_file(
                repo,
                str(supplement_packet_reference.get("path") or ""),
                label=f"{supplement_id} packet",
            )
            supplement_approval_path = repository_file(
                repo,
                str(supplement_approval_reference.get("path") or ""),
                label=f"{supplement_id} approval",
            )
            if sha256(supplement_packet_path) != supplement_packet_reference.get("sha256") or sha256(
                supplement_approval_path
            ) != supplement_approval_reference.get("sha256"):
                raise ValueError(f"{supplement_id} recovery supplement authority hash mismatch")
            supplement_packet = json.loads(supplement_packet_path.read_text(encoding="utf-8"))
            supplement_approval = json.loads(supplement_approval_path.read_text(encoding="utf-8"))
            if (
                supplement_packet.get("supplementId") != supplement_id
                or supplement_approval.get("supplementId") != supplement_id
                or supplement_packet.get("recoveryRequestId") != request_id
                or supplement_approval.get("recoveryRequestId") != request_id
            ):
                raise ValueError(f"{supplement_id} recovery supplement identity mismatch")
            supplements.append(
                {
                    "id": supplement_id,
                    "bootstrap_id": (supplement.get("bootstrap") or {}).get("id"),
                    "bootstrap_status": (supplement.get("bootstrap") or {}).get("status"),
                    "packet_path": supplement_packet_reference.get("path"),
                    "packet_sha256": supplement_packet_reference.get("sha256"),
                    "packet_commit": supplement_packet_reference.get("commit"),
                    "approval_path": supplement_approval_reference.get("path"),
                    "approval_sha256": supplement_approval_reference.get("sha256"),
                    "approval_commit": supplement_approval_reference.get("introduction_commit"),
                }
            )
        records.append(
            {
                "request_id": request_id,
                "hold_id": hold.get("id"),
                "target_wave": hold.get("target_wave"),
                "hold_status": hold.get("status"),
                "bootstrap": hold.get("bootstrap") or {},
                "post_bootstrap": hold.get("post_bootstrap") or {},
                "release_conditions": hold.get("release_conditions") or [],
                "packet_path": packet_path.relative_to(repo).as_posix(),
                "packet_sha256": packet_reference.get("sha256"),
                "packet_commit": packet_reference.get("commit"),
                "proposal_path": proposal_relative,
                "review_path": review_relative,
                "approval_path": approval_path.relative_to(repo).as_posix(),
                "approval_sha256": approval_reference.get("sha256"),
                "approval_commit": approval_reference.get("introduction_commit"),
                "authority_chain": packet.get("authorityChain") or {},
                "packet": packet,
                "approval": approval,
                "supplements": supplements,
            }
        )
    return records


def governed_experience_html(repo: Path, experience: dict[str, Any]) -> tuple[str, str]:
    """Keep historical hashes off mutable links and distinguish publication from adoption."""
    rows = "".join(
        (
            f"<li><code>{esc(item.get('sourceCommit'))}:{esc(item.get('path'))}</code>"
            f" — <code>{esc(item.get('sha256'))}</code> (immutable Git source)</li>"
            if item.get("sourceCommit")
            else f'<li><a href="{esc((repo / str(item.get("path"))).resolve().as_uri())}">'
            f"{esc(item.get('path'))}</a> — <code>{esc(item.get('sha256'))}</code></li>"
        )
        for item in experience.get("files", [])
    )
    summary = (
        f"Reference <code>{esc(experience.get('referenceId'))}</code> is already human-approved. "
        "Human approval of this ECR reaffirms and binds that existing authority unchanged; it does not reserve "
        "a new reference or authorize bootstrap materialization of reference approval."
        if experience.get("referenceApprovalStatus") == "approved"
        else f"Reference <code>{esc(experience.get('referenceId'))}</code> requires human approval: "
        f"{esc(experience.get('approvalRequired'))}. Approval reserves the reference; bootstrap must "
        "materialize its canonical approval before renderer implementation."
    )
    if experience.get("sourceBinding"):
        binding = experience["sourceBinding"]
        summary += (
            f" Historical binding at <code>{esc(binding['packetCommit'])}</code>. "
            f"The current published reference is <code>{esc(binding['currentReferenceId'])}</code>; "
            "publication does not retroactively change this packet's authority. "
            "Any effective-reference change still requires the successor amendment's qualified adoption."
        )
    return summary, rows


def _build_site_unlocked(repo: Path, output: Path, selected_capability: str | None = None) -> dict[str, Any]:
    backlog = yaml.safe_load((repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
    enabler_records = load_enabler_change_requests(repo, backlog)
    recovery_records = load_recovery_holds(repo, backlog)
    cap_plan_dir = repo / "planning/capability-plans"
    slice_plan_dir = repo / "planning/slice-plans"
    all_cap_paths = sorted(cap_plan_dir.glob("CAP-*.md"))
    if selected_capability and selected_capability not in {path.stem for path in all_cap_paths}:
        raise ValueError(f"No capability plan found for {selected_capability}")
    # The site is a coherent generated set. Always rebuild all pages so links, hashes, and the manifest remain synchronized.
    cap_paths = all_cap_paths
    backlog_capabilities = {cap["id"]: cap for cap in backlog.get("capabilities", [])}
    backlog_slices = {
        str(slice_["id"]): slice_
        for capability in backlog_capabilities.values()
        for slice_ in capability.get("slices", [])
    }
    backlog_tasks: dict[str, dict[str, Any]] = {}
    task_locations: dict[str, dict[str, str]] = {}
    for capability in backlog_capabilities.values():
        capability_id = str(capability["id"])
        for slice_ in capability.get("slices", []):
            slice_id = str(slice_["id"])
            for task in slice_.get("tasks", []):
                task_id = str(task["id"])
                page_name = task_page_name(task_id)
                if task_id in backlog_tasks:
                    raise ValueError(f"Duplicate task identity in backlog: {task_id}")
                backlog_tasks[task_id] = task
                task_locations[task_id] = {
                    "capability_id": capability_id,
                    "slice_id": slice_id,
                    "page": f"{capability_id}/{page_name}",
                }
    waves = [wave for wave in backlog.get("waves", []) if isinstance(wave, dict)]
    gates_by_wave = {
        str(gate.get("after_wave")): gate for gate in backlog.get("release_gates", []) if isinstance(gate, dict)
    }
    capabilities: list[dict[str, Any]] = []
    capability_plan_meta: dict[str, dict[str, Any]] = {}
    for path in all_cap_paths:
        meta, _ = read_frontmatter(path)
        cid = meta["capability_id"]
        capability_plan_meta[cid] = meta
        capabilities.append(
            {"id": cid, "alias": backlog_capabilities.get(cid, {}).get("alias", cid), "title": meta["title"]}
        )
    slice_plan_meta: dict[str, dict[str, Any]] = {}
    for path in slice_plan_dir.glob("CAP-*/*.md"):
        meta, _ = read_frontmatter(path)
        slice_plan_meta[str(meta["slice_id"])] = meta
    authored_capability_ids = {str(item["id"]) for item in capabilities}
    authored_task_ids = {
        task_id
        for task_id, location in task_locations.items()
        if location["capability_id"] in authored_capability_ids and location["slice_id"] in slice_plan_meta
    }

    # Rebuild into a clean directory so stale pages or convenience launchers cannot
    # be mistaken for governed review pages or break page-count validation.
    generated_at = datetime.now(UTC).isoformat()
    existing_manifest = output / "manifest.json"
    if existing_manifest.exists():
        try:
            existing_generated_at = json.loads(existing_manifest.read_text(encoding="utf-8")).get("generated_at")
            if isinstance(existing_generated_at, str) and existing_generated_at.strip():
                generated_at = existing_generated_at
        except OSError, json.JSONDecodeError, AttributeError:
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
        "waves": [],
        "capabilities": [],
        "enabler_change_requests": [],
        "governance_recoveries": [],
    }

    wave_cards = []
    for wave in waves:
        wave_id = str(wave["id"])
        wave_slices = [
            slice_
            for capability in backlog_capabilities.values()
            for slice_ in capability.get("slices", [])
            if slice_.get("wave") == wave_id
        ]
        wave_capability_ids = sorted({str(slice_["id"]).split(".")[0] for slice_ in wave_slices})
        approved_slices = sum(slice_.get("completion", {}).get("status") == "APPROVED" for slice_ in wave_slices)
        gate = gates_by_wave.get(wave_id, {})
        wave_tasks = [task for slice_ in wave_slices for task in slice_.get("tasks", [])]
        wave_cards.append(f"""
<a class="capability-card" href="waves/{esc(wave_id)}.html">
  <div class="capability-card-top"><span class="eyebrow">{esc(wave_id)} · {esc(wave.get("track"))}</span>{status_stack((wave.get("approval") or {}).get("status"), delivery_status(wave_tasks, wave.get("completion")))}</div>
  <h2>{esc(wave.get("title"))}</h2>
  <p>{esc(wave.get("goal"))}</p>
  <dl><div><dt>Capabilities</dt><dd>{len(wave_capability_ids)}</dd></div><div><dt>Slices</dt><dd>{approved_slices}/{len(wave_slices)}</dd></div><div><dt>Exit gate</dt><dd>{esc(gate.get("id"))}</dd></div></dl>
  <span class="text-link">Review complete Wave packet and gate</span>
</a>""")

    cards = []
    for path in all_cap_paths:
        meta, _ = read_frontmatter(path)
        cid = meta["capability_id"]
        cap_alias = backlog_capabilities.get(cid, {}).get("alias", cid)
        decision_count = len(meta.get("decisions", []))
        unresolved = len(meta.get("open_blocking_decisions", []))
        backlog_capability = backlog_capabilities.get(cid, {})
        capability_tasks = [task for slice_ in backlog_capability.get("slices", []) for task in slice_.get("tasks", [])]
        cards.append(f"""
<a class="capability-card" href="{esc(cid)}/index.html">
  <div class="capability-card-top"><span class="eyebrow">{esc(cap_alias)}</span>{status_stack(meta.get("status"), delivery_status(capability_tasks, backlog_capability.get("completion")))}</div>
  <h2>{esc(meta.get("title"))}</h2>
  <p><code>{esc(cid)}</code> is the immutable evidence key.</p>
  <dl><div><dt>Slices</dt><dd>{len(meta.get("slice_ids", []))}</dd></div><div><dt>Decisions</dt><dd>{decision_count}</dd></div><div><dt>Open</dt><dd>{unresolved}</dd></div></dl>
  <span class="text-link">Review capability plan</span>
</a>""")
    landing_main = f"""
<section class="hero compact">
  <span class="eyebrow">Decision-complete Wave planning</span>
  <h1>Planning review center</h1>
  <p>Review and approve one complete Wave packet, then execute its capability contributions and ordered slices as one durable campaign. Descriptive aliases are the default presentation; canonical numeric IDs remain immutable evidence keys.</p>
</section>
<section class="callout callout-info"><h2>How to use this site</h2><ol><li>Select the Wave being activated.</li><li>Review every contributing capability decision and ordered slice plan from the Wave page.</li><li>Use the linked capability pages when you need full rationale or an override.</li><li>Approve the complete Wave packet at one immutable commit; later Waves remain unapproved.</li></ol></section>
<section class="section-heading"><span class="eyebrow">Controlled change lane</span><h2>Enabler change requests</h2><p>Inspect proposal, immutable approval, materialization, campaign, and adoption states without flattening their history.</p></section>
<section class="capability-grid"><a class="capability-card" href="enablers/index.html"><div class="capability-card-top"><span class="eyebrow">ECR register</span>{status_badge("active" if enabler_records else "empty")}</div><h2>Workflow-control amendments</h2><p>{len(enabler_records)} hash-bound request{"s" if len(enabler_records) != 1 else ""}; generated links expose the exact authority chain and current execution boundary.</p><span class="text-link">Open enabler register</span></a><a class="capability-card" href="recoveries/index.html"><div class="capability-card-top"><span class="eyebrow">GRR register</span>{status_badge("active" if any(record["hold_status"] == "ACTIVE" for record in recovery_records) else "completed")}</div><h2>Governance recovery holds</h2><p>{len(recovery_records)} immutable recovery request{"s" if len(recovery_records) != 1 else ""}; active holds deny ordinary execution until their exact release conditions are met.</p><span class="text-link">Open recovery register</span></a></section>
<section class="section-heading"><span class="eyebrow">Primary execution axis</span><h2>Waves, campaigns, and exit gates</h2><p>Each Wave is approved and executed end to end, with independent slice reviews, integration checkpoints, and one explicit exit decision.</p></section>
<section class="capability-grid">{"".join(wave_cards)}</section>
<section class="section-heading"><span class="eyebrow">Product outcomes</span><h2>Capabilities</h2><p>Capabilities may contribute ordered slices to more than one wave.</p></section>
<section class="capability-grid">{"".join(cards)}</section>
"""
    landing = shell(
        title="Planning review center",
        page_type="landing",
        depth=0,
        body=layout(
            breadcrumbs='<span aria-current="page">Planning review</span>',
            sidebar=planning_nav(
                capabilities=capabilities,
                waves=waves,
                active_capability=None,
                active_wave=None,
                capability_prefix="",
                wave_prefix="waves/",
                default_tab="waves",
            ),
            main=landing_main,
        ),
    )
    (output / "index.html").write_text(landing, encoding="utf-8")

    enabler_dir = output / "enablers"
    enabler_dir.mkdir(parents=True, exist_ok=True)
    enabler_cards: list[str] = []
    for record in enabler_records:
        enabler_cards.append(
            f"""
<a class="capability-card" href="{esc(record["change_request_id"])}.html">
  <div class="capability-card-top"><span class="eyebrow">{esc(record["amendment_id"])} · {esc(record["target_wave"])}</span>{status_badge(record["approval_status"])}</div>
  <h2>{esc(record["change_request_id"])}</h2>
  <p>{esc(record["classification"])}</p>
  <dl><div><dt>Proposal</dt><dd>{esc(record["proposal_status"])}</dd></div><div><dt>Materialization</dt><dd>{esc(record["lifecycle_status"])}</dd></div><div><dt>Campaign</dt><dd>{esc(record["campaign_status"])}</dd></div></dl>
  <span class="text-link">Inspect exact authority and execution boundary</span>
</a>"""
        )
    enabler_index_main = f"""
<section class="hero compact">
  <span class="eyebrow">Append-only control history</span>
  <h1>Enabler change request register</h1>
  <p>Proposal, human approval, materialization, campaign, and adoption are separate states. An approval record authorizes only its exact hash-bound scope; it does not imply materialization or ordinary Wave resumption.</p>
</section>
<section class="capability-grid">{"".join(enabler_cards) if enabler_cards else "<p>No enabler change request packets are present.</p>"}</section>
"""
    enabler_index = shell(
        title="Enabler change request register",
        page_type="enabler-register",
        depth=1,
        body=layout(
            breadcrumbs='<a href="../index.html">Planning review</a><span>/</span><span aria-current="page">Enabler change requests</span>',
            sidebar=planning_nav(
                capabilities=capabilities,
                waves=waves,
                active_capability=None,
                active_wave=None,
                capability_prefix="../",
                wave_prefix="../waves/",
                default_tab="waves",
            ),
            main=enabler_index_main,
        ),
    )
    (enabler_dir / "index.html").write_text(enabler_index, encoding="utf-8")

    recovery_dir = output / "recoveries"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    recovery_cards = "".join(
        f'<a class="capability-card" href="{esc(record["request_id"])}.html"><div class="capability-card-top">'
        f'<span class="eyebrow">{esc(record["hold_id"])} · {esc(record["target_wave"])}</span>'
        f"{status_badge(record['hold_status'])}</div><h2>{esc(record['request_id'])}</h2>"
        f"<p>Bootstrap {esc(record['bootstrap'].get('id'))}: {esc(record['bootstrap'].get('status'))}; "
        f"supplements: {len(record['supplements'])}</p>"
        '<span class="text-link">Inspect immutable recovery authority and release conditions</span></a>'
        for record in recovery_records
    )
    recovery_index = shell(
        title="Governance recovery request register",
        page_type="recovery-register",
        depth=1,
        body=layout(
            breadcrumbs='<a href="../index.html">Planning review</a><span>/</span><span aria-current="page">Governance recovery</span>',
            sidebar=planning_nav(
                capabilities=capabilities,
                waves=waves,
                active_capability=None,
                active_wave=None,
                capability_prefix="../",
                wave_prefix="../waves/",
                default_tab="waves",
            ),
            main=f"""
<section class="hero compact"><span class="eyebrow">Fail-closed control recovery</span><h1>Governance recovery request register</h1><p>A GRR authorizes only its exact recovery bootstrap. It never approves the later ECR, task execution, Wave resume, or a release gate.</p></section>
<section class="capability-grid">{recovery_cards or "<p>No governance recovery requests are present.</p>"}</section>""",
        ),
    )
    (recovery_dir / "index.html").write_text(recovery_index, encoding="utf-8")

    for record in recovery_records:
        bootstrap = record["bootstrap"]
        post = record["post_bootstrap"]
        amendments = record["authority_chain"].get("orderedAmendments") or []
        authority_rows = "".join(
            f"<li><strong>{esc(item.get('id'))}</strong> — {esc(item.get('status'))}; packet "
            f"<code>{esc(item.get('packetCommit'))}</code>; approval "
            f"<code>{esc((item.get('approvalRecord') or {}).get('introductionCommit'))}</code></li>"
            for item in amendments
        )
        release_rows = "".join(f"<li>{esc(item)}</li>" for item in record["release_conditions"])
        supplement_rows = "".join(
            f"<li><strong>{esc(item['id'])}</strong> / <code>{esc(item['bootstrap_id'])}</code> — "
            f'{esc(item["bootstrap_status"])}; <a href="{esc((repo / item["packet_path"]).resolve().as_uri())}">packet</a> '
            f'<code>{esc(item["packet_sha256"])}</code>; <a href="{esc((repo / item["approval_path"]).resolve().as_uri())}">approval</a> '
            f"<code>{esc(item['approval_sha256'])}</code></li>"
            for item in record["supplements"]
        )
        detail = shell(
            title=f"{record['request_id']} governance recovery",
            page_type="recovery-detail",
            depth=1,
            body=layout(
                breadcrumbs=(
                    '<a href="../index.html">Planning review</a><span>/</span>'
                    '<a href="index.html">Governance recovery</a><span>/</span>'
                    f'<span aria-current="page">{esc(record["request_id"])}</span>'
                ),
                sidebar=planning_nav(
                    capabilities=capabilities,
                    waves=waves,
                    active_capability=None,
                    active_wave=record["target_wave"],
                    capability_prefix="../",
                    wave_prefix="../waves/",
                    default_tab="waves",
                ),
                main=f"""
<section class="hero compact"><div class="hero-top"><div><span class="eyebrow">{esc(record["hold_id"])}</span><h1>{esc(record["request_id"])} — governance recovery</h1></div>{status_badge(record["hold_status"])}</div><p>Target Wave {esc(record["target_wave"])}; bootstrap <code>{esc(bootstrap.get("id"))}</code> is {esc(bootstrap.get("status"))}.</p></section>
<section class="callout callout-warning"><h2>Ordinary execution is denied</h2><p>This immutable recovery approval authorizes only the bootstrap. It grants zero authority to {esc(post.get("required_change_request_id"))}/{esc(post.get("required_amendment_id"))}, proposed tasks, ordinary Wave resume, or gate approval.</p><p><strong>Recommendation:</strong> complete independent bootstrap review, then prepare and separately approve the exact ECR/amendment. Safe alternatives are leaving the hold active or recording a governed terminal disposition; direct execution is prohibited.</p></section>
<section class="review-toolbar"><h2>Hash-bound source records</h2><ul><li><a href="{esc((repo / record["packet_path"]).resolve().as_uri())}">Frozen packet</a> — <code>{esc(record["packet_sha256"])}</code> at <code>{esc(record["packet_commit"])}</code></li><li><a href="{esc((repo / record["proposal_path"]).resolve().as_uri())}">Canonical proposal</a></li><li><a href="{esc((repo / record["review_path"]).resolve().as_uri())}">Human review</a></li><li><a href="{esc((repo / record["approval_path"]).resolve().as_uri())}">Immutable approval</a> — <code>{esc(record["approval_sha256"])}</code> introduced at <code>{esc(record["approval_commit"])}</code></li><li><a href="../waves/{esc(record["target_wave"])}.html">Paused Wave packet</a></li></ul></section>
<section class="review-toolbar"><h2>Frozen predecessor authority</h2><ul>{authority_rows}</ul></section>
<section class="review-toolbar"><h2>Append-only recovery supplements</h2><ul>{supplement_rows or "<li>No supplemental bootstrap is installed.</li>"}</ul><p>A supplement authorizes only its sequential BNN bootstrap and never the repair amendment, ordinary task execution, Wave resume, hold release, or a gate.</p></section>
<section class="review-toolbar"><h2>Exact release conditions</h2><ul>{release_rows}</ul><p>After every condition is proven, release the hold through <code>python tools/recoveryctl.py --repo . release {esc(record["request_id"])} --agent &lt;agent&gt;</code>. The Wave remains PAUSED until an explicit ordinary resume.</p></section>""",
            ),
        )
        (recovery_dir / f"{record['request_id']}.html").write_text(detail, encoding="utf-8")
        manifest["governance_recoveries"].append(
            {
                key: record[key]
                for key in (
                    "request_id",
                    "hold_id",
                    "target_wave",
                    "hold_status",
                    "packet_path",
                    "packet_sha256",
                    "packet_commit",
                    "proposal_path",
                    "review_path",
                    "approval_path",
                    "approval_sha256",
                    "approval_commit",
                    "release_conditions",
                )
            }
            | {
                "bootstrap_id": bootstrap.get("id"),
                "bootstrap_status": bootstrap.get("status"),
                "supplements": record["supplements"],
                "page": f"recoveries/{record['request_id']}.html",
            }
        )

    for record in enabler_records:
        proposal_meta, proposal_body = read_frontmatter(repo / record["proposal_path"])
        authority = record["authority"]
        authority_chain = record["authority_chain"]
        effective_base = record["effective_base"]
        current_is_approved = record["approval_status"] == "APPROVED"
        current_authority_meaning = (
            "Human-approved bootstrap/task scope; adoption remains separate"
            if current_is_approved
            else "Pending, non-executable proposal; no bootstrap/task authority"
        )
        if authority_chain:
            wave_base = authority_chain.get("waveBase") or {}
            wave_id = wave_base.get("waveId") or record["target_wave"]
            enabler_authority_rows = [
                (
                    f"{wave_id} base approval",
                    wave_base.get("packetCommit"),
                    wave_base.get("approvalRecordCommit"),
                    "Original complete Wave packet",
                )
            ]
            predecessor_authority_rows: list[tuple[str, tuple[Any, Any, Any, str]]] = []
            for predecessor in authority_chain.get("orderedAmendments") or []:
                approval_reference = predecessor.get("approvalReference") or {}
                predecessor_authority_rows.append(
                    (
                        str(predecessor.get("id") or ""),
                        (
                            predecessor.get("id"),
                            predecessor.get("packetCommit"),
                            approval_reference.get("introductionCommit") or approval_reference.get("sha256"),
                            "Adopted predecessor authority; preserved unchanged",
                        ),
                    )
                )
            for reservation in authority_chain.get("reservedAmendments") or []:
                approval_reference = reservation.get("approvalReference") or {}
                supersession = reservation.get("supersededByMigration") or {}
                predecessor_authority_rows.append(
                    (
                        str(reservation.get("id") or ""),
                        (
                            f"{reservation.get('id')} · reserved",
                            reservation.get("packetCommit"),
                            approval_reference.get("introductionCommit") or approval_reference.get("sha256"),
                            (
                                "Approved but unmaterialized; superseded by "
                                f"{supersession.get('id') or 'recorded migration'} and never executable here"
                            ),
                        ),
                    )
                )
            enabler_authority_rows.extend(
                row
                for _, row in sorted(
                    predecessor_authority_rows,
                    key=lambda item: amendment_identity_sort_key(item[0]),
                )
            )
            migration_authority = record.get("migration_authority") or {}
            if migration_authority:
                enabler_authority_rows.append(
                    (
                        migration_authority.get("id") or "Migration authority",
                        migration_authority.get("commit"),
                        migration_authority.get("sha256"),
                        "Post-migration governance authority; does not grant product execution",
                    )
                )
        else:
            enabler_authority_rows = [
                (
                    "W1 base approval",
                    effective_base.get("originalPacketCommit") or authority.get("originalWavePacketCommit"),
                    effective_base.get("originalApprovalRecordCommit") or authority.get("originalApprovalRecordCommit"),
                    "Original complete Wave packet",
                ),
                (
                    authority.get("legacyAmendmentId") or "Legacy amendment",
                    effective_base.get("legacyAmendmentPacketCommit") or authority.get("legacyAmendmentPacketCommit"),
                    effective_base.get("legacyAmendmentRecordCommit") or authority.get("legacyAmendmentRecordCommit"),
                    "Previously approved delta; preserved as migrated history",
                ),
            ]
        enabler_authority_rows.append(
            (
                record["amendment_id"],
                record["packet_sha256"],
                record["approval_sha256"] or "pending",
                current_authority_meaning,
            )
        )
        rendered_authority = "".join(
            f"<tr><th>{esc(label)}</th><td><code>{esc(packet or 'missing')}</code></td>"
            f"<td><code>{esc(approval or 'missing')}</code></td><td>{esc(meaning)}</td></tr>"
            for label, packet, approval, meaning in enabler_authority_rows
        )
        task_badge = "authorized" if current_is_approved else "pending"
        task_rows = "".join(
            f"<li><span><strong>{esc(task.get('id'))} — {esc(task.get('title'))}</strong>"
            f"<small>{esc(task.get('objective'))}</small>"
            f"<small>Estimate {esc(task.get('estimate') or 'not declared')} · dependencies: "
            f"{esc(', '.join(str(item) for item in task.get('dependencies', [])) or 'none')}</small>"
            f"</span>{status_badge(task_badge)}</li>"
            for task in record["task_inventory"]
        )
        enabler_slice_rows = "".join(
            f'<details class="plan-details"><summary>{esc(item.get("id"))} — '
            f"{esc(item.get('title'))}</summary><p>{esc(item.get('objective'))}</p>"
            f"<p><strong>Work type:</strong> {esc(item.get('workType'))}. "
            f"<strong>Tasks:</strong> {esc(', '.join(str(task_id) for task_id in item.get('taskIds', [])))}. "
            f"<strong>Refactor tasks:</strong> "
            f"{esc(', '.join(str(task_id) for task_id in item.get('refactorTaskIds', [])) or 'none')}.</p>"
            f'<ul class="gate-criteria">'
            f"{''.join(f'<li>{esc(criterion)}</li>' for criterion in item.get('acceptanceCriteria', []))}"
            f"</ul></details>"
            for item in record.get("slice_contributions", [])
        )
        refactor_budget = record.get("refactor_budget") or {}
        refactor_baseline = refactor_budget.get("baseline") or {}
        refactor_policy = refactor_budget.get("limitPolicy") or {}
        refactor_rows = "".join(
            f"<tr><th><code>{esc(item.get('taskId'))}</code></th><td>{esc(item.get('estimate'))}</td>"
            f"<td>{esc(item.get('points'))}</td></tr>"
            for item in refactor_budget.get("refactorAllocations", [])
        )
        refactor_policy_detail = (
            f"Owner-directed exception by {esc(refactor_policy.get('authorizedBy'))}: "
            f"{esc(refactor_policy.get('authorization'))} Scope: "
            f"{esc(', '.join(str(task_id) for task_id in refactor_policy.get('scopeTaskIds', [])))}. "
            f"Rationale: {esc(refactor_policy.get('rationale'))}"
            if refactor_policy.get("mode") == "owner-directed-wave-exception"
            else f"Standard refactor limit: {esc(refactor_policy.get('limitPercent'))}%"
        )
        governed_experience = record.get("governed_experience") or {}
        governed_experience_summary, governed_experience_rows = governed_experience_html(repo, governed_experience)
        task_count = len(record["task_inventory"])
        task_completion = (
            "completion and independent approval of the one task"
            if task_count == 1
            else f"completion and independent approval of all {task_count} tasks"
        )
        approval_summary = (
            f"Approved by <strong>{esc(record['approved_by'])}</strong> at "
            f"<code>{esc(record['approved_at'])}</code>. Approval is not task materialization, amendment "
            "activation, adoption, Wave resumption, or release-gate approval."
            if current_is_approved
            else "No human approval is recorded. The proposal is non-executable and grants no bootstrap, task, "
            "amendment, Wave-resume, or release-gate authority."
        )
        authority_summary = (
            f"Effective ordinary W1 authority remains the approved base plus adopted ordered amendments. "
            f"{esc(record['amendment_id'])} authorizes only bootstrap unit "
            f"<code>{esc(record['bootstrap_unit'])}</code> and the exact bounded task inventory below until adoption."
            if current_is_approved
            else f"Effective ordinary W1 authority remains the approved base plus adopted ordered amendments. "
            f"{esc(record['amendment_id'])} is pending and non-executable. If separately approved, it would authorize "
            f"only bootstrap unit <code>{esc(record['bootstrap_unit'])}</code> and the exact bounded task inventory below."
        )
        inventory_heading = "Authorized bounded inventory" if current_is_approved else "Proposed bounded inventory"
        inventory_projection = "authorized packet inventory" if current_is_approved else "proposed packet inventory"
        safe_resume = (
            f"Continue the approved amendment through independently approved bootstrap, materialization, "
            f"{task_completion}, amendment-exit control/security review, and the W1 adoption checkpoint."
            if current_is_approved
            else f"First obtain independent approval of this exact packet and explicit human approval. Only then may "
            f"the amendment continue through independently approved bootstrap, materialization, {task_completion}, "
            "amendment-exit control/security review, and the W1 adoption checkpoint."
        )
        task_review_rows = "".join(
            task_review_history_html(task) for task in (record.get("amendment") or {}).get("tasks", [])
        )
        exit_review = amendment_exit_review_html(
            record.get("amendment") or {"id": record["amendment_id"], "completion": {}},
            record["adoption_checkpoints"],
        )
        criteria = "".join(f"<li>{esc(item)}</li>" for item in record["acceptance_criteria"])
        rollback = "".join(f"<li>{esc(item)}</li>" for item in record["rollback"])
        addendum_rows = "".join(
            f"<tr><th>Bootstrap scope addendum</th><td><code>{esc(addendum['path'])}</code></td>"
            f"<td><code>{esc(addendum['sha256'])}</code></td></tr>"
            for addendum in record["scope_addenda"]
        )
        addendum_scope = "".join(
            f"<li><code>{esc(path)}</code> — mechanically generated output approved by "
            f"{esc(addendum['approved_by'])} at <code>{esc(addendum['approved_at'])}</code></li>"
            for addendum in record["scope_addenda"]
            for path in addendum["authorized_additional_paths"]
        )
        bootstrap_attempt_rows = "".join(
            f"<tr><th>{esc(attempt['id'])}</th><td><code>{esc(attempt.get('implementation_commit'))}</code></td>"
            f"<td>{esc((attempt.get('review') or {}).get('result') or attempt.get('current_status') or 'pending')}</td>"
            f"<td>{esc((attempt.get('review') or {}).get('reviewer') or 'pending')}</td></tr>"
            for attempt in record["bootstrap_attempts"]
        )
        detail_main = f"""
<section class="hero compact">
  <div class="hero-top"><div><span class="eyebrow">{esc(record["amendment_id"])} · {
            esc(record["target_wave"])
        }</span><h1>{esc(record["change_request_id"])} — {esc(proposal_meta.get("title"))}</h1></div>{
            status_badge(record["approval_status"])
        }</div>
  <p>{
            esc(record["classification"])
        }. This page preserves the distinction between authorized scope and executable state.</p>
</section>
<section class="review-toolbar">
  <h2>Proposal, approval, materialization, and campaign state</h2>
  <dl class="summary-grid"><div><dt>Proposal record</dt><dd>{esc(record["proposal_status"])} / {
            esc(record["proposal_execution_state"])
        }</dd></div><div><dt>Human approval</dt><dd>{
            esc(record["approval_status"])
        }</dd></div><div><dt>Materialization lifecycle</dt><dd>{
            esc(record["lifecycle_status"])
        }</dd></div><div><dt>Amendment campaign</dt><dd>{esc(record["campaign_status"])}</dd></div></dl>
  <p>{approval_summary}</p>
</section>
<section class="review-toolbar">
  <h2>Hash-bound source records</h2>
  <table><thead><tr><th>Record</th><th>Repository-relative path</th><th>SHA-256</th></tr></thead><tbody>
  <tr><th>Proposal</th><td><code>{esc(record["proposal_path"])}</code></td><td><code>{
            esc(record["proposal_sha256"])
        }</code></td></tr>
  <tr><th>Packet</th><td><code>{esc(record["packet_path"])}</code></td><td><code>{
            esc(record["packet_sha256"])
        }</code></td></tr>
  <tr><th>Human review</th><td><code>{esc(record["review_path"])}</code></td><td><code>{
            esc(record["review_sha256"])
        }</code></td></tr>
  <tr><th>Approval</th><td><code>{esc(record["approval_path"] or "pending")}</code></td><td><code>{
            esc(record["approval_sha256"] or "pending")
        }</code></td></tr>
{addendum_rows}
  </tbody></table>
</section>
<section class="review-toolbar">
  <h2>Append-only bootstrap scope addenda</h2>
  <ul class="gate-criteria">{addendum_scope or "<li>None</li>"}</ul>
</section>
<section class="review-toolbar">
  <h2>Append-only bootstrap review attempts</h2>
  <table><thead><tr><th>Attempt</th><th>Frozen candidate</th><th>Disposition / state</th><th>Reviewer</th></tr></thead><tbody>{
            bootstrap_attempt_rows or '<tr><td colspan="4">Not submitted</td></tr>'
        }</tbody></table>
</section>
<section class="review-toolbar">
  <h2>Ordered Wave authority chain</h2>
  <table><thead><tr><th>Authority</th><th>Packet commit / hash</th><th>Record commit / hash</th><th>Meaning</th></tr></thead><tbody>{
            rendered_authority
        }</tbody></table>
  <p>{authority_summary}</p>
</section>
{
            f'''<section class="review-toolbar">
  <h2>Proposed slice contributions</h2>
  <p>These slices are packet data, not hard-coded review-page inventory. They remain non-executable until exact approval and independently approved bootstrap materialization.</p>
  {enabler_slice_rows}
</section>'''
            if enabler_slice_rows
            else ""
        }
{
            f'''<section class="review-toolbar">
  <h2>Refactor allocation and planning exception</h2>
  <dl class="summary-grid"><div><dt>Approved-Wave baseline</dt><dd>{esc(refactor_baseline.get("totalPoints"))} points at <code>{esc(refactor_baseline.get("sourceCommit"))}</code></dd></div><div><dt>Refactor allocation</dt><dd>{esc(refactor_budget.get("refactorPoints"))} points / {esc(refactor_budget.get("refactorSharePercent"))}%</dd></div><div><dt>Policy</dt><dd>{esc(refactor_policy.get("mode"))}</dd></div><div><dt>Method</dt><dd>{esc(refactor_budget.get("method"))}</dd></div></dl>
  <table><thead><tr><th>Refactor task</th><th>Estimate</th><th>Points</th></tr></thead><tbody>{refactor_rows or '<tr><td colspan="3">No refactor task declared</td></tr>'}</tbody></table>
  <p>{refactor_policy_detail}</p>
</section>'''
            if refactor_budget
            else ""
        }
{
            f'''<section class="review-toolbar">
  <h2>Governed experience proposal</h2>
  <p>{governed_experience_summary}</p>
  <ul class="gate-criteria">{governed_experience_rows}</ul>
</section>'''
            if governed_experience
            else ""
        }
<section class="review-toolbar">
  <h2>{inventory_heading}</h2><ul class="wave-slice-list">{task_rows}</ul>
  <h3>Exit criteria</h3><ul class="gate-criteria">{criteria}</ul>
</section>
<section class="section-heading"><span class="eyebrow">Executable projection</span><h2>Materialized task review packets and history</h2><p>The {
            inventory_projection
        } above remains distinct from current task state. Each task below shows either its complete append-only review control or an explicit legacy latest-review-only projection.</p></section>
{task_review_rows or "<p>No amendment task has been materialized.</p>"}
{exit_review}
<section class="callout callout-warning">
  <div><span class="eyebrow">Ordinary Wave execution remains stopped</span><h2>Safe resume boundary</h2><p>{
            safe_resume
        } The alternatives are an append-only defer or withdraw disposition with an explicit safe resume condition; editing or reapproving W1 in place is prohibited.</p></div>
</section>
<details class="plan-details"><summary>Rollback and recovery duties</summary><ul class="gate-criteria">{
            rollback
        }</ul></details>
<details class="plan-details"><summary>Read the canonical proposal</summary><article class="plan-article">{
            render_markdown(strip_first_h1(proposal_body))
        }</article></details>
"""
        detail_page = shell(
            title=f"{record['change_request_id']} {proposal_meta.get('title')}",
            page_type="enabler-detail",
            depth=1,
            body=layout(
                breadcrumbs=f'<a href="../index.html">Planning review</a><span>/</span><a href="index.html">Enabler change requests</a><span>/</span><span aria-current="page">{esc(record["change_request_id"])}</span>',
                sidebar=planning_nav(
                    capabilities=capabilities,
                    waves=waves,
                    active_capability=None,
                    active_wave=str(record["target_wave"]),
                    capability_prefix="../",
                    wave_prefix="../waves/",
                    default_tab="waves",
                ),
                main=detail_main,
            ),
        )
        (enabler_dir / f"{record['change_request_id']}.html").write_text(detail_page, encoding="utf-8")
        manifest["enabler_change_requests"].append(
            {
                key: record[key]
                for key in (
                    "change_request_id",
                    "amendment_id",
                    "target_wave",
                    "classification",
                    "proposal_status",
                    "proposal_execution_state",
                    "packet_path",
                    "packet_sha256",
                    "proposal_path",
                    "proposal_sha256",
                    "review_path",
                    "review_sha256",
                    "approval_path",
                    "approval_sha256",
                    "approval_status",
                    "lifecycle_status",
                    "bootstrap_status",
                    "campaign_status",
                    "bootstrap_attempts",
                    "slice_contributions",
                    "authorized_task_ids",
                    "refactor_budget",
                    "governed_experience",
                    "scope_addenda",
                    "task_reviews",
                    "exit_review",
                    "adoption_checkpoints",
                    "page",
                )
            }
        )

    wave_dir = output / "waves"
    wave_dir.mkdir(parents=True, exist_ok=True)
    for wave in waves:
        wave_id = str(wave["id"])
        gate = gates_by_wave.get(wave_id, {})
        increment_cards: list[str] = []
        wave_slice_count = 0
        wave_approved_count = 0
        wave_task_count = 0
        wave_done_count = 0
        wave_plan_count = 0
        wave_approved_plan_count = 0
        wave_decision_count = 0
        wave_accepted_decision_count = 0
        wave_unclassified_decision_count = 0
        wave_decision_ids: list[str] = []
        capability_ids: list[str] = []
        for capability in backlog_capabilities.values():
            increment_slices = [slice_ for slice_ in capability.get("slices", []) if slice_.get("wave") == wave_id]
            if not increment_slices:
                continue
            capability_id = str(capability["id"])
            capability_ids.append(capability_id)
            cap_meta = capability_plan_meta.get(capability_id, {})
            cap_decisions = cap_meta.get("decisions", [])
            binding_decisions, inherited_decisions, future_decisions, unclassified_decisions = classified_decisions(
                cap_decisions, wave_id
            )
            wave_decision_ids.extend(str(decision["id"]) for decision in binding_decisions)
            wave_decision_count += len(binding_decisions)
            wave_accepted_decision_count += sum(
                decision.get("status") == "accepted" and bool(decision.get("selected_option"))
                for decision in binding_decisions
            )
            wave_unclassified_decision_count += len(unclassified_decisions)
            wave_slice_count += len(increment_slices)
            wave_approved_count += sum(
                slice_.get("completion", {}).get("status") == "APPROVED" for slice_ in increment_slices
            )
            slice_rows: list[str] = []
            for slice_ in increment_slices:
                slice_tasks = slice_.get("tasks", [])
                wave_task_count += len(slice_tasks)
                wave_done_count += sum(task.get("status") == "DONE" for task in slice_tasks)
                label = slice_alias(str(slice_.get("title")))
                status = slice_.get("completion", {}).get("status")
                plan_status = slice_plan_meta.get(str(slice_["id"]), {}).get("status", "missing")
                wave_plan_count += int(plan_status != "missing")
                wave_approved_plan_count += int(plan_status == "approved")
                slice_id = str(slice_["id"])
                slice_open = any(
                    str(task.get("status")) in {"IN_PROGRESS", "REVIEW", "CHANGES_REQUESTED"} for task in slice_tasks
                )
                wave_task_rows: list[str] = []
                for task in slice_tasks:
                    task_id = str(task["id"])
                    task_open = str(task.get("status")) in {"IN_PROGRESS", "REVIEW", "CHANGES_REQUESTED"}
                    task_link = (
                        f'<a class="text-link" href="../{esc(capability_id)}/{esc(task_page_name(task_id))}">Open task page</a>'
                        if task_id in authored_task_ids
                        else '<span class="decision-meta">No authored task detail page is available.</span>'
                    )
                    wave_task_rows.append(
                        f'<details class="wave-task-card" data-wave-task="{esc(task_id)}"'
                        f"{' open' if task_open else ''}><summary><span><strong>{esc(task_id)}</strong>"
                        f"<small>{esc(task.get('title'))}</small></span>{status_badge(task.get('status'))}</summary>"
                        f'<div class="wave-card-body"><p>{esc(task.get("objective"))}</p>'
                        f"{task_link}</div></details>"
                    )
                slice_rows.append(
                    f'<details class="wave-slice-card" data-wave-slice="{esc(slice_id)}"'
                    f"{' open' if slice_open else ''}><summary><span><strong>{esc(label)}</strong>"
                    f"<small>{esc(slice_id)} · {esc(slice_.get('title'))}</small></span>"
                    f"{status_stack(plan_status, delivery_status(slice_tasks, slice_.get('completion')))}</summary>"
                    f'<div class="wave-card-body"><p>Plan: {esc(plan_status)} · Delivery: {esc(status)} · '
                    f"{len(slice_tasks)} task{'s' if len(slice_tasks) != 1 else ''}</p>"
                    f"{f'<a class="text-link" href="../{esc(capability_id)}/{esc(slice_id)}.html">Open slice page</a>' if slice_id in slice_plan_meta else '<span class="decision-meta">No authored slice detail page is available.</span>'}"
                    f'<div class="wave-task-list">{"".join(wave_task_rows)}</div></div></details>'
                )
            alias = capability.get("alias", capability_id)
            title = capability.get("title")
            capability_open = any(
                str(task.get("status")) in {"IN_PROGRESS", "REVIEW", "CHANGES_REQUESTED"}
                for slice_ in increment_slices
                for task in slice_.get("tasks", [])
            )
            capability_link = (
                f'<a class="text-link" href="../{esc(capability_id)}/index.html">Open capability page</a>'
                if capability_id in authored_capability_ids
                else '<span class="decision-meta">No authored capability detail page is available.</span>'
            )
            decision_groups = "".join(
                [
                    (
                        f'<details class="plan-details" open><summary>{len(binding_decisions)} binding {wave_id} '
                        f'decisions</summary><ul class="wave-slice-list">'
                        f"{wave_decision_rows(binding_decisions, context='Binding in this Wave')}</ul></details>"
                        if binding_decisions
                        else ""
                    ),
                    (
                        f'<details class="plan-details"><summary>{len(inherited_decisions)} inherited decisions '
                        f'(context only)</summary><ul class="wave-slice-list">'
                        f"{wave_decision_rows(inherited_decisions, context='Previously binding; not re-approved here')}"
                        f"</ul></details>"
                        if inherited_decisions
                        else ""
                    ),
                    (
                        f'<details class="plan-details"><summary>{len(future_decisions)} future decisions '
                        f'(nonbinding context)</summary><ul class="wave-slice-list">'
                        f"{wave_decision_rows(future_decisions, context='Future context; not authorized by this Wave')}"
                        f"</ul></details>"
                        if future_decisions
                        else ""
                    ),
                    (
                        f'<details class="plan-details" open><summary>{len(unclassified_decisions)} decisions require '
                        f'Wave classification</summary><ul class="wave-slice-list">'
                        f"{wave_decision_rows(unclassified_decisions, context='Classification required before approval')}"
                        f"</ul></details>"
                        if unclassified_decisions
                        else ""
                    ),
                ]
            )
            increment_cards.append(f"""
<details class="wave-capability" data-wave-capability="{esc(capability_id)}"{" open" if capability_open else ""}>
  <summary><div><span class="eyebrow">{esc(capability_id)} · immutable key</span><h2>{esc(alias)}</h2><p>{esc(title)}</p></div>{status_stack(cap_meta.get("status", "historical"), delivery_status([task for slice_ in increment_slices for task in slice_.get("tasks", [])]))}</summary>
  <div class="wave-card-body">
    {capability_link}
    {decision_groups if cap_decisions else '<p class="decision-meta">Historical foundation contribution; approval is bound by the Wave record.</p>'}
    <div class="wave-slice-list">{"".join(slice_rows)}</div>
  </div>
</details>""")

        criteria = "".join(f"<li>{esc(criterion)}</li>" for criterion in gate.get("criteria", []))
        unlocks = ", ".join(str(item) for item in gate.get("unlocks_waves", [])) or "No further wave"
        approval = gate.get("approval") or {}
        wave_approval = wave.get("approval") or {}
        wave_completion = wave.get("completion") or {}
        wave_execution_status = delivery_status(
            [
                task
                for capability in backlog_capabilities.values()
                for slice_ in capability.get("slices", [])
                if slice_.get("wave") == wave_id
                for task in slice_.get("tasks", [])
            ],
            wave_completion,
        )
        wave_enablers = [record for record in enabler_records if record.get("target_wave") == wave_id]
        interrupting_enablers = [record for record in wave_enablers if enabler_interrupts_wave(record, wave)]
        interruption_html = ""
        wave_recoveries = [
            record
            for record in recovery_records
            if record.get("target_wave") == wave_id and record.get("hold_status") == "ACTIVE"
        ]
        if wave_recoveries:
            recovery = wave_recoveries[0]
            bootstrap = recovery["bootstrap"]
            post = recovery["post_bootstrap"]
            latest_supplement = recovery["supplements"][-1] if recovery["supplements"] else None
            supplement_status = (
                f" Latest supplement <code>{esc(latest_supplement['id'])}</code> / "
                f"<code>{esc(latest_supplement['bootstrap_id'])}</code> is "
                f"{esc(latest_supplement['bootstrap_status'])}."
                if latest_supplement
                else ""
            )
            recovery_recommendation = (
                f"complete independent {esc(latest_supplement['bootstrap_id'])} review, then retry only the exact approved repair amendment"
                if latest_supplement and latest_supplement["bootstrap_status"] != "APPROVED"
                else "complete the exact separately approved ECR/amendment"
            )
            interruption_html = f"""
<section class="callout callout-warning" id="governance-recovery-interruption">
  <div><span class="eyebrow">Stopped at governance recovery hold</span><h2>{esc(wave_id)} ordinary execution is interrupted</h2>
  <p><a href="../recoveries/{esc(recovery["request_id"])}.html"><strong>{esc(recovery["request_id"])} / {esc(recovery["hold_id"])}</strong></a> is ACTIVE. Bootstrap <code>{esc(bootstrap.get("id"))}</code> is {esc(bootstrap.get("status"))}.{supplement_status} Ordinary task claims, Wave start/resume, amendment execution, and {esc(gate.get("id"))} progression fail closed.</p>
  <p><strong>Authority:</strong> packet <code>{esc(recovery["packet_sha256"])}</code> at <code>{esc(recovery["packet_commit"])}</code>; approval <code>{esc(recovery["approval_sha256"])}</code> introduced at <code>{esc(recovery["approval_commit"])}</code>. This authority is bootstrap-only and does not approve {esc(post.get("required_change_request_id"))}/{esc(post.get("required_amendment_id"))}.</p>
  <p><strong>Recommendation:</strong> {recovery_recommendation}. The safe alternative is to keep the hold and Wave paused. Direct execution or repeat Wave approval is prohibited.</p>
  <p><strong>Exact ordinary resume condition:</strong> B00 independently approved; {esc(post.get("required_amendment_id"))} separately approved, completed, independently exit-reviewed, and adopted with a control/security checkpoint; recovery hold released; then explicit ordinary Wave resume.</p></div>
</section>"""
        if interrupting_enablers:
            interruption_items_parts: list[str] = []
            for record in interrupting_enablers:
                authority = record["authority"]
                effective_base = record["effective_base"]
                base_packet = effective_base.get("originalPacketCommit") or authority.get("originalWavePacketCommit")
                legacy_id = effective_base.get("legacyAmendmentId") or authority.get("legacyAmendmentId")
                legacy_packet = effective_base.get("legacyAmendmentPacketCommit") or authority.get(
                    "legacyAmendmentPacketCommit"
                )
                interruption_items_parts.append(
                    f'<li><a href="../{esc(record["page"])}"><strong>{esc(record["change_request_id"])} / {esc(record["amendment_id"])}</strong></a> — '
                    f"approval {esc(record['approval_status'])}; materialization {esc(record['lifecycle_status'])}; "
                    f"bootstrap {esc(record['bootstrap_status'])}; campaign {esc(record['campaign_status'])}"
                    f"<small>Current ordinary authority: base <code>{esc(base_packet)}</code> + {esc(legacy_id)} "
                    f"<code>{esc(legacy_packet)}</code>. Approved interrupting scope: {esc(record['amendment_id'])} packet "
                    f"<code>{esc(record['packet_sha256'])}</code> and approval <code>{esc(record['approval_sha256'])}</code>; not ordinary authority until adopted.</small></li>"
                )
            interruption_items = "".join(interruption_items_parts)
            interruption_html += f"""
<section class="callout callout-warning" id="wave-amendment-interruption">
  <div><span class="eyebrow">Stopped at approved Wave amendment</span><h2>{esc(wave_id)} ordinary execution is interrupted</h2>
  <p>The immutable pre-Wave approval remains authoritative and must not be repeated. Ordinary task claims, Wave restart or resume, and {esc(gate.get("id"))} progression remain unavailable while this interrupting amendment is unfinished.</p>
  <ul>{interruption_items}</ul>
  <p><strong>Recommendation:</strong> continue the approved bounded amendment through bootstrap review, task materialization and independent completion, amendment-exit review, and the {esc(wave_id)} control/security adoption checkpoint. Legal alternatives are an append-only defer or withdraw disposition with an explicit safe resume condition. Editing or reapproving the Wave in place is prohibited.</p>
  <p><strong>Exact ordinary resume condition:</strong> every authorized amendment task is DONE and independently approved, the amendment exit is APPROVED, and the {esc(wave_id)} adoption checkpoint is recorded.</p></div>
</section>"""
        if wave_approval.get("status") == "APPROVED":
            readiness = "The complete pre-Wave packet is already approved and immutable"
            approval_action = (
                "<h3>Immutable authority</h3><p>Do not repeat this approval. Any later scope change must use the "
                "append-only enabler change request and Wave-amendment lane.</p>"
            )
        else:
            readiness = (
                "Ready for one commit-bound pre-Wave approval"
                if wave_plan_count == wave_slice_count
                and wave_decision_count == wave_accepted_decision_count
                and wave_unclassified_decision_count == 0
                else "Review incomplete—classify every contributing decision, resolve binding decisions, and approve every Wave slice plan"
            )
            approval_action = (
                f"<h3>Approval command after review</h3><pre><code>python tools/planctl.py --repo . wave approve {esc(wave_id)} "
                '--by "&lt;reviewer&gt;" --commit &lt;git-sha&gt;</code></pre>'
            )
        gate_main = f"""
<section class="hero compact">
  <div class="hero-top"><div><span class="eyebrow">{esc(wave.get("track"))} · durable Wave campaign</span><h1>{esc(wave_id)} — {esc(wave.get("title"))}</h1></div>{status_stack(wave_approval.get("status"), wave_execution_status)}</div>
  <p>{esc(wave.get("goal"))}</p>
  <dl class="summary-grid"><div><dt>Capability contributions</dt><dd>{len(capability_ids)}</dd></div><div><dt>Slice plans present</dt><dd>{wave_plan_count}/{wave_slice_count}</dd></div><div><dt>Binding decisions resolved</dt><dd>{wave_accepted_decision_count}/{wave_decision_count}</dd></div><div><dt>Delivery</dt><dd>{wave_done_count}/{wave_task_count} tasks</dd></div></dl>
</section>
{interruption_html}
<section class="review-toolbar">
  <div class="hero-top"><div><span class="eyebrow">One approval before execution</span><h2>Complete pre-Wave approval packet</h2></div>{status_badge(wave_approval.get("status"))}</div>
  <p>{esc(readiness)}. Approval covers exactly the decisions labeled <strong>Binding in this Wave</strong>, every {esc(wave_id)} slice plan, the cross-capability dependency order, risk register, verification obligations, and the exit-gate criteria at immutable commit <code>{esc(wave_approval.get("approved_commit") or "pending")}</code>. Inherited and future decisions are context only and are not authorized here.</p>
  <dl class="summary-grid"><div><dt>Status</dt><dd>{esc(wave_approval.get("status"))}</dd></div><div><dt>Approved by</dt><dd>{esc(wave_approval.get("approved_by") or "Pending")}</dd></div><div><dt>Approved at</dt><dd>{esc(wave_approval.get("approved_at") or "Pending")}</dd></div><div><dt>Campaign state</dt><dd>{esc((wave.get("campaign") or {}).get("status", "Not started"))}</dd></div></dl>
  {approval_action}
</section>
<section class="callout callout-info"><h2>Review and verification cadence while the Wave runs</h2><ol><li><strong>Task:</strong> risk-selected checks plus a focused independent scope/evidence disposition; expand only for high-risk boundaries.</li><li><strong>Slice:</strong> independent risk-focused end-to-end and adversarial deep review.</li><li><strong>Integration checkpoint:</strong> accumulated affected-profile checks when a shared interface, migration, security boundary, or coherent risk cluster closes.</li><li><strong>Wave exit:</strong> the complete affected/full suite, packaging, security, accessibility, performance, restart, recovery, and independent Wave review.</li></ol></section>
<section class="section-heading"><span class="eyebrow">Wave contents</span><h2>Capability contributions and ordered slices</h2><p>Each card is the portion of a capability delivered and independently reviewed within {esc(wave_id)}.</p></section>
<div class="wave-capability-list">{"".join(increment_cards)}</div>
<section class="review-toolbar">
  <div class="hero-top"><div><span class="eyebrow">Wave exit / successor activation</span><h2>{esc(gate.get("id"))} — {esc(wave_id)} exit / {esc(unlocks)} activation</h2></div>{status_badge(gate.get("status"))}</div>
  <p>{esc(gate.get("name"))}. Approval is legal only after all Wave tasks are DONE, every slice is independently approved, the full Wave-exit suite passes, independent Wave review is APPROVED, prior gates are approved, and the criteria below have exact evidence.</p>
  <ul class="gate-criteria">{criteria}</ul>
  <dl class="summary-grid"><div><dt>Gate status</dt><dd>{esc(gate.get("status"))}</dd></div><div><dt>Wave review</dt><dd>{esc(wave_completion.get("status"))}</dd></div><div><dt>Approved by</dt><dd>{esc(approval.get("approved_by") or "Pending")}</dd></div><div><dt>Unlocks</dt><dd>{esc(unlocks)}</dd></div></dl>
</section>
"""
        wave_page = shell(
            title=f"{wave_id} {wave.get('title')}",
            page_type="wave",
            depth=1,
            body=layout(
                breadcrumbs=f'<a href="../index.html">Planning review</a><span>/</span><span aria-current="page">{esc(wave_id)}</span>',
                sidebar=planning_nav(
                    capabilities=capabilities,
                    waves=waves,
                    active_capability=None,
                    active_wave=wave_id,
                    capability_prefix="../",
                    wave_prefix="",
                    default_tab="waves",
                ),
                main=gate_main,
            ),
        )
        (wave_dir / f"{wave_id}.html").write_text(wave_page, encoding="utf-8")
        manifest["waves"].append(
            {
                "wave_id": wave_id,
                "title": wave.get("title"),
                "track": wave.get("track"),
                "page": f"waves/{wave_id}.html",
                "capability_ids": capability_ids,
                "decision_ids": wave_decision_ids,
                "slice_ids": [
                    str(slice_["id"])
                    for capability in backlog_capabilities.values()
                    for slice_ in capability.get("slices", [])
                    if slice_.get("wave") == wave_id
                ],
                "task_ids": [
                    str(task["id"])
                    for capability in backlog_capabilities.values()
                    for slice_ in capability.get("slices", [])
                    if slice_.get("wave") == wave_id
                    for task in slice_.get("tasks", [])
                ],
                "slice_count": wave_slice_count,
                "task_count": wave_task_count,
                "exit_gate_id": gate.get("id"),
                "gate_status": gate.get("status"),
                "approval_status": wave_approval.get("status"),
                "completion_status": wave_completion.get("status"),
                "unlocks_waves": gate.get("unlocks_waves", []),
                "interrupting_change_request_ids": [record["change_request_id"] for record in interrupting_enablers],
                "interrupting_recovery_request_ids": [record["request_id"] for record in wave_recoveries],
            }
        )

    for cap_path in cap_paths:
        meta, body_md = read_frontmatter(cap_path)
        cid = meta["capability_id"]
        cap_alias = backlog_capabilities.get(cid, {}).get("alias", cid)
        cap_dir = output / cid
        cap_dir.mkdir(parents=True, exist_ok=True)
        cap_hash = sha256(cap_path)

        slice_file_by_id: dict[str, Path] = {}
        for slice_file in (slice_plan_dir / cid).glob("*.md"):
            slice_file_meta, _ = read_frontmatter(slice_file)
            slice_file_by_id[str(slice_file_meta["slice_id"])] = slice_file
        authoritative_slice_ids = [str(slice_["id"]) for slice_ in backlog_capabilities.get(cid, {}).get("slices", [])]
        slice_files = [
            slice_file_by_id[slice_id] for slice_id in authoritative_slice_ids if slice_id in slice_file_by_id
        ]
        slice_files.extend(
            slice_file_by_id[slice_id] for slice_id in sorted(set(slice_file_by_id) - set(authoritative_slice_ids))
        )
        slices: list[dict[str, Any]] = []
        for path in slice_files:
            smeta, sbody = read_frontmatter(path)
            page_name = f"{smeta['slice_id']}.html"
            backlog_slice = backlog_slices.get(str(smeta["slice_id"]), {})
            tasks = backlog_slice.get("tasks", [])
            task_entries = []
            for task in tasks:
                task_id = str(task["id"])
                plan_section = extract_task_section(sbody, task_id)
                if not plan_section:
                    raise ValueError(f"{path}: no authored task-plan heading found for {task_id}")
                task_entries.append(
                    {
                        "task": task,
                        "task_id": task_id,
                        "title": task.get("title"),
                        "page_name": task_page_name(task_id),
                        "worksheet": task_worksheet_projection(repo, task_id),
                        "plan_section": plan_section,
                        "plan_section_sha256": text_sha256(plan_section),
                    }
                )
            slices.append(
                {
                    "path": path,
                    "meta": smeta,
                    "body": sbody,
                    "slice_id": smeta["slice_id"],
                    "alias": slice_alias(smeta["title"]),
                    "title": smeta["title"],
                    "page_name": page_name,
                    "sha256": sha256(path),
                    "delivery_status": delivery_status(tasks, backlog_slice.get("completion")),
                    "tasks": tasks,
                    "task_entries": task_entries,
                }
            )

        decisions_html = "".join(decision_card(decision, cap_hash) for decision in meta.get("decisions", []))
        slice_cards = []
        for idx, sl in enumerate(slices, start=1):
            smeta = sl["meta"]
            slice_cards.append(f"""
<a class="slice-card" href="{esc(sl["page_name"])}">
  <div class="slice-card-index">{idx}</div>
  <div><span class="eyebrow">{esc(sl["alias"])}</span><h3>{esc(sl["title"])}</h3>
  <p>{len(smeta.get("task_ids", []))} tasks · {esc(smeta.get("wave"))} · {esc(smeta.get("priority"))}</p></div>
  {status_stack(smeta.get("status"), sl["delivery_status"])}
</a>""")

        wave_ids = list(dict.fromkeys(str(sl["meta"].get("wave")) for sl in slices))
        backlog_capability = backlog_capabilities.get(cid, {})
        capability_execution_status = delivery_status(
            [task for slice_ in backlog_capability.get("slices", []) for task in slice_.get("tasks", [])],
            backlog_capability.get("completion"),
        )
        wave_status_by_id = {str(item["id"]): (item.get("approval") or {}).get("status", "PENDING") for item in waves}
        pending_wave_commands = [
            f"python tools/planctl.py --repo . wave approve {esc(wave)} "
            '--by "&lt;reviewer&gt;" --commit &lt;git-sha&gt;'
            for wave in wave_ids
            if wave_status_by_id.get(wave) != "APPROVED"
        ]
        approved_wave_notes = [
            f"# {esc(wave)} approval is immutable; later changes use an append-only Wave amendment."
            for wave in wave_ids
            if wave_status_by_id.get(wave) == "APPROVED"
        ]
        wave_commands = "\n".join(pending_wave_commands + approved_wave_notes)
        capability_main = f"""
<section class="hero compact">
  <div class="hero-top"><div><span class="eyebrow">{esc(cid)} · immutable evidence key</span><h1>{esc(cap_alias)}</h1><p>{esc(meta.get("title"))}</p></div>{status_stack(meta.get("status"), capability_execution_status)}</div>
  <p>Review this capability's durable decisions as one part of each complete Wave packet. Execution is leased to the Wave, not to this capability.</p>
  <dl class="summary-grid"><div><dt>Slices</dt><dd>{len(slices)}</dd></div><div><dt>Decisions</dt><dd>{len(meta.get("decisions", []))}</dd></div><div><dt>Open blockers</dt><dd>{len(meta.get("open_blocking_decisions", []))}</dd></div><div><dt>Plan hash</dt><dd><code>{cap_hash[:12]}</code></dd></div></dl>
</section>
<section class="review-toolbar" data-review-toolbar>
  <div><h2>Capability decisions classified by Wave approval</h2><p>Best-in-class capability decisions are preselected and decision-complete. Their binding-Wave labels determine which exact pre-Wave packet authorizes them. Inherited and future decisions remain context only until their own Wave approval.</p></div>
  <div class="review-progress" aria-live="polite"><strong data-selected-count>0</strong> / {len(meta.get("decisions", []))} selected</div>
  <label class="field-label">Reviewer name<input type="text" data-reviewer-name placeholder="Name or review role"></label>
  <label class="field-label">Capability-level notes<textarea rows="3" data-review-notes placeholder="Cross-slice constraints, required benchmarks, or approval conditions"></textarea></label>
  <label class="approval-check"><input type="checkbox" data-approval-intent> Mark this capability review complete for inclusion in the active pre-Wave approval packet</label>
  <div class="button-row"><button class="button" type="button" data-accept-recommendations>Restore recommended defaults</button><button class="button button-quiet" type="button" data-clear-decisions>Clear draft overrides</button><button class="button button-primary" type="button" data-export-feedback>Export decision-response JSON</button></div>
  <div class="feedback-message" data-feedback-message role="status"></div>
  <details><summary>Automation commands</summary><pre><code>python tools/planctl.py --repo . review {esc(cid)}
{wave_commands}
# Only for overrides or notes:
python tools/planctl.py --repo . apply-feedback {esc(cid)} &lt;downloaded-json&gt;
python tools/planctl.py --repo . approve {esc(cid)} --wave &lt;active-wave&gt; --feedback &lt;downloaded-json&gt; --by "&lt;reviewer&gt;" --commit &lt;git-sha&gt;
python tools/planctl.py --repo . ready {esc(cid)} --wave &lt;active-wave&gt; --require-approved</code></pre></details>
</section>
<section id="decision-register" class="section-heading"><span class="eyebrow">Decision register</span><h2>Confirm resolved defaults or record overrides</h2><p>Each researched best-in-class recommendation is already selected and decision-complete. The decision's binding-Wave label controls when it is authorized. Any documented alternative requires rationale. Other additionally requires a brief description.</p></section>
<div class="decision-list">{decisions_html}</div>
<section class="section-heading"><span class="eyebrow">Slice sequence</span><h2>Review the implementation plan slice by slice</h2></section>
<div class="slice-list">{"".join(slice_cards)}</div>
<details class="plan-details"><summary>Read the full capability plan</summary><article class="plan-article">{render_markdown(strip_first_h1(body_md))}</article></details>
"""
        cap_page = shell(
            title=f"{cap_alias} ({cid}) {meta.get('title')}",
            page_type="capability",
            capability_id=cid,
            depth=1,
            body=layout(
                breadcrumbs=f'<a href="../index.html">Planning review</a><span>/</span><span aria-current="page">{esc(cap_alias)} ({esc(cid)})</span>',
                sidebar=planning_nav(
                    capabilities=capabilities,
                    waves=waves,
                    active_capability=cid,
                    active_wave=None,
                    capability_prefix="../",
                    wave_prefix="../waves/",
                    default_tab="capabilities",
                )
                + slice_nav(slices, None),
                main=capability_main,
            ),
        )
        (cap_dir / "index.html").write_text(cap_page, encoding="utf-8")

        open_decision_count = len(meta.get("open_blocking_decisions", []))
        if open_decision_count:
            gate_heading = f"Resolve {open_decision_count} capability decision{'s' if open_decision_count != 1 else ''} before implementation"
            gate_text = "Capability-wide decisions remain durable, but execution starts only after the complete active Wave packet is approved at one immutable commit."
        else:
            gate_heading = "Recommendations resolved; complete pre-Wave approval controls execution"
            gate_text = "Confirm or override capability defaults once, then approve the ordered slice plans for the wave being activated."

        for index, sl in enumerate(slices):
            smeta = sl["meta"]
            section4 = extract_section(sl["body"], 4)
            section9 = extract_section(sl["body"], 9)
            prev_link = slices[index - 1]["page_name"] if index > 0 else "index.html"
            next_link = slices[index + 1]["page_name"] if index + 1 < len(slices) else "index.html"
            task_cards = []
            for task_index, task_entry in enumerate(sl["task_entries"], start=1):
                task = task_entry["task"]
                review = task.get("review") or {}
                task_cards.append(f"""
<a class="task-card" href="{esc(task_entry["page_name"])}" data-slice-task="{esc(task_entry["task_id"])}">
  <div class="slice-card-index">{task_index}</div>
  <div><span class="eyebrow">{esc(task_entry["task_id"])}</span><h3>{esc(task_entry["title"])}</h3>
  <p>{esc(task.get("objective"))}</p><small>Review: {esc(review.get("result") or "not reviewed")} · Risk: {esc(task.get("risk"))}</small></div>
  {status_badge(task.get("status"))}
</a>""")
            slice_main = f"""
<section class="hero compact">
  <div class="hero-top"><div><span class="eyebrow">{esc(sl["slice_id"])} · ordered slice {index + 1} of {len(slices)}</span><h1>{esc(sl["alias"])}</h1><p>{esc(sl["title"])}</p></div>{status_stack(smeta.get("status"), sl["delivery_status"])}</div>
  <p>The descriptive label is the default presentation. The numeric slice ID preserves explicit dependency order and immutable evidence history. This plan becomes executable after the capability decisions and its wave's slice plans are approved.</p>
  <dl class="summary-grid"><div><dt>Wave</dt><dd>{esc(smeta.get("wave"))}</dd></div><div><dt>Priority</dt><dd>{esc(smeta.get("priority"))}</dd></div><div><dt>Tasks</dt><dd>{len(smeta.get("task_ids", []))}</dd></div><div><dt>Plan hash</dt><dd><code>{sl["sha256"][:12]}</code></dd></div></dl>
</section>
<section class="callout callout-warning">
  <div><span class="eyebrow">Capability decision gate</span><h2>{esc(gate_heading)}</h2><p>{esc(gate_text)}</p></div>
  <a class="button button-primary" href="index.html#decision-register">Review capability decisions</a>
</section>
<section class="decision-summary"><div class="section-heading"><span class="eyebrow">Slice decisions</span><h2>Recommended implementation selections</h2></div><article class="plan-article compact-article">{render_markdown(section4)}</article></section>
<section class="section-heading"><span class="eyebrow">Implementation sequence</span><h2>Tasks</h2><p>Open a task for its objective, acceptance criteria, implementation plan, verification inventory, optional worksheet, and immutable review history.</p></section>
<div class="task-list">{"".join(task_cards) or "<p>No authoritative task records are present for this slice.</p>"}</div>
<details class="plan-details"><summary>Read the complete task-by-task implementation plan</summary><article class="plan-article">{render_markdown(section9)}</article></details>
<details class="plan-details" open><summary>Read the complete slice plan</summary><article class="plan-article">{render_markdown(strip_first_h1(sl["body"]))}</article></details>
<nav class="page-turn" aria-label="Slice navigation"><a class="button button-quiet" href="{esc(prev_link)}">Previous</a><a class="button button-primary" href="{esc(next_link)}">Next</a></nav>
"""
            slice_page = shell(
                title=f"{sl['alias']} ({sl['slice_id']}) {sl['title']}",
                page_type="slice",
                capability_id=cid,
                depth=1,
                body=layout(
                    breadcrumbs=f'<a href="../index.html">Planning review</a><span>/</span><a href="index.html">{esc(cap_alias)}</a><span>/</span><span aria-current="page">{esc(sl["alias"])} ({esc(sl["slice_id"])})</span>',
                    sidebar=planning_nav(
                        capabilities=capabilities,
                        waves=waves,
                        active_capability=cid,
                        active_wave=str(smeta.get("wave")),
                        capability_prefix="../",
                        wave_prefix="../waves/",
                        default_tab="capabilities",
                    )
                    + slice_nav(slices, sl["slice_id"])
                    + task_nav(sl["task_entries"], None),
                    main=slice_main,
                ),
            )
            (cap_dir / sl["page_name"]).write_text(slice_page, encoding="utf-8")

            for task_index, task_entry in enumerate(sl["task_entries"]):
                task = task_entry["task"]
                task_id = task_entry["task_id"]
                review = task.get("review") or {}
                claim = task.get("claim") or {}
                claim_owner = task.get("owner") or claim.get("agent")
                claim_branch = task.get("branch") or claim.get("branch")
                claim_base = task.get("base_sha") or claim.get("base_sha")
                dependencies = []
                for dependency_id in task.get("dependencies", []):
                    dependency_id = str(dependency_id)
                    location = task_locations.get(dependency_id)
                    if location and dependency_id in authored_task_ids:
                        href = (
                            task_page_name(dependency_id)
                            if location["capability_id"] == cid
                            else f"../{location['capability_id']}/{task_page_name(dependency_id)}"
                        )
                        dependencies.append(
                            f'<li data-task-dependency="{esc(dependency_id)}"><a href="{esc(href)}"><code>{esc(dependency_id)}</code></a></li>'
                        )
                    else:
                        dependencies.append(
                            f'<li data-task-dependency="{esc(dependency_id)}"><code>{esc(dependency_id)}</code></li>'
                        )
                task_prev = sl["task_entries"][task_index - 1]["page_name"] if task_index > 0 else sl["page_name"]
                task_next = (
                    sl["task_entries"][task_index + 1]["page_name"]
                    if task_index + 1 < len(sl["task_entries"])
                    else sl["page_name"]
                )
                task_main = f"""
<section class="hero compact" data-task-page="{esc(task_id)}">
  <div class="hero-top"><div><span class="eyebrow">{esc(task_id)} · task {task_index + 1} of {len(sl["task_entries"])}</span><h1>{esc(task_entry["title"])}</h1><p>{esc(task.get("objective"))}</p></div>{status_badge(task.get("status"))}</div>
  <dl class="summary-grid"><div><dt>Wave</dt><dd>{esc(smeta.get("wave"))}</dd></div><div><dt>Slice</dt><dd><a href="{esc(sl["page_name"])}">{esc(sl["alias"])}</a></dd></div><div><dt>Risk / review</dt><dd>{esc(task.get("risk"))} / {esc(task.get("review_gate"))}</dd></div><div><dt>Latest review</dt><dd>{esc(review.get("result") or "not reviewed")}</dd></div></dl>
</section>
<section class="task-summary"><div class="section-heading"><span class="eyebrow">Authoritative task record</span><h2>Scope and acceptance</h2></div>
  <h3>Expected deliverables</h3>{task_values_html(task.get("deliverables"), empty="No deliverables recorded.")}
  <h3>Acceptance criteria</h3>{task_values_html(task.get("acceptance_criteria"), empty="No acceptance criteria recorded.")}
  <h3>Dependencies</h3>{'<ul class="gate-criteria" data-task-dependencies="' + esc("|".join(str(item) for item in task.get("dependencies", []))) + '">' + "".join(dependencies) + "</ul>" if dependencies else '<p data-task-dependencies="">None</p>'}
</section>
<section class="task-summary"><div class="section-heading"><span class="eyebrow">Verification inventory</span><h2>Profiles and commands</h2></div>
  <h3>Verification profiles</h3>{task_values_html(task.get("verification_profiles"), empty="No verification profile recorded.")}
  <h3>Commands</h3>{task_values_html(task.get("verification_commands"), empty="No verification command recorded.")}
  <p data-task-claim="{esc(task_id)}" data-task-owner="{esc(claim_owner or "unclaimed")}" data-task-branch="{esc(claim_branch or "none")}" data-task-base-sha="{esc(claim_base or "none")}"><strong>Claim projection:</strong> owner <code>{esc(claim_owner or "unclaimed")}</code> · branch <code>{esc(claim_branch or "none")}</code> · base <code>{esc(claim_base or "none")}</code></p>
</section>
<section class="task-summary" data-task-plan="{esc(task_id)}" data-task-plan-sha256="{esc(task_entry["plan_section_sha256"])}"><div class="section-heading"><span class="eyebrow">Approved implementation intent</span><h2>Task plan</h2></div><article class="plan-article compact-article">{render_markdown(task_entry["plan_section"])}</article></section>
<section class="section-heading"><span class="eyebrow">Task-start planning</span><h2>Assigned worksheet</h2><p>The worksheet is an optional planning aid and does not create a new approval or task state.</p></section>
{task_worksheet_html(task_entry["worksheet"], task_id)}
<section class="section-heading"><span class="eyebrow">Execution evidence</span><h2>Review packets, rounds, and current projection</h2><p>Append-only controls retain every immutable round and finding closure. Pre-policy tasks remain explicitly latest-review-only.</p></section>
{task_review_history_html(task)}
<nav class="page-turn" aria-label="Task navigation"><a class="button button-quiet" href="{esc(task_prev)}">Previous</a><a class="button button-primary" href="{esc(task_next)}">Next</a></nav>
"""
                task_page = shell(
                    title=f"{task_id} {task_entry['title']}",
                    page_type="task",
                    capability_id=cid,
                    depth=1,
                    body=layout(
                        breadcrumbs=(
                            f'<a href="../index.html">Planning review</a><span>/</span>'
                            f'<a href="index.html">{esc(cap_alias)}</a><span>/</span>'
                            f'<a href="{esc(sl["page_name"])}">{esc(sl["alias"])}</a><span>/</span>'
                            f'<span aria-current="page">{esc(task_id)}</span>'
                        ),
                        sidebar=planning_nav(
                            capabilities=capabilities,
                            waves=waves,
                            active_capability=cid,
                            active_wave=str(smeta.get("wave")),
                            capability_prefix="../",
                            wave_prefix="../waves/",
                            default_tab="capabilities",
                        )
                        + slice_nav(slices, sl["slice_id"])
                        + task_nav(sl["task_entries"], task_id),
                        main=task_main,
                    ),
                )
                (cap_dir / task_entry["page_name"]).write_text(task_page, encoding="utf-8")

        manifest["capabilities"].append(
            {
                "capability_id": cid,
                "capability_alias": cap_alias,
                "title": meta.get("title"),
                "plan_path": str(cap_path.relative_to(repo)).replace(os.sep, "/"),
                "plan_sha256": cap_hash,
                "page": f"{cid}/index.html",
                "decision_count": len(meta.get("decisions", [])),
                "slice_count": len(slices),
                "slices": [
                    {
                        "slice_id": sl["slice_id"],
                        "slice_alias": sl["alias"],
                        "wave": sl["meta"].get("wave"),
                        "title": sl["title"],
                        "plan_path": str(sl["path"].relative_to(repo)).replace(os.sep, "/"),
                        "plan_sha256": sl["sha256"],
                        "page": f"{cid}/{sl['page_name']}",
                        "task_count": len(sl["meta"].get("task_ids", [])),
                        "task_reviews": [task_review_projection(task) for task in sl["tasks"]],
                        "tasks": [
                            {
                                "task_id": task_entry["task_id"],
                                "title": task_entry["title"],
                                "status": task_entry["task"].get("status"),
                                "page": f"{cid}/{task_entry['page_name']}",
                                "dependencies": list(task_entry["task"].get("dependencies", [])),
                                "claim": {
                                    "owner": task_entry["task"].get("owner")
                                    or (task_entry["task"].get("claim") or {}).get("agent"),
                                    "branch": task_entry["task"].get("branch")
                                    or (task_entry["task"].get("claim") or {}).get("branch"),
                                    "base_sha": task_entry["task"].get("base_sha")
                                    or (task_entry["task"].get("claim") or {}).get("base_sha"),
                                },
                                "plan_section_sha256": task_entry["plan_section_sha256"],
                                "worksheet": (
                                    {
                                        "path": task_entry["worksheet"]["path"],
                                        "sha256": task_entry["worksheet"]["sha256"],
                                    }
                                    if task_entry["worksheet"]
                                    else None
                                ),
                            }
                            for task_entry in sl["task_entries"]
                        ],
                    }
                    for sl in slices
                ],
            }
        )

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total_slices = sum(len(item.get("slices", [])) for item in manifest["capabilities"])
    total_tasks = sum(
        len(slice_.get("tasks", []))
        for capability in manifest["capabilities"]
        for slice_ in capability.get("slices", [])
    )
    readme = f"""# Static planning review site

Open `index.html` in a browser. Review interface release {REVIEW_INTERFACE_RELEASE}; canonical planning supplement 1.3.4. The site contains {len(manifest["waves"])} Wave packet/gate pages, {len(manifest["capabilities"])} capability pages, {total_slices} individual slice pages, {total_tasks} individual task pages, {len(manifest["enabler_change_requests"])} hash-bound enabler change request pages, and {len(manifest["governance_recoveries"])} governance recovery pages plus their registers. A Wave page is the pre-execution approval surface: it aggregates every contributing capability decision, ordered slice plan, review cadence, exit-gate decision, and any interrupting append-only amendment or recovery hold. Its nested capability, slice, and task cards are generated from the authoritative backlog. Descriptive aliases are the default presentation; numeric IDs remain immutable evidence and ordering keys. Task pages display an optional task-start worksheet only when `artifacts/evidence/<TASK-ID>.task-start.md` exists; worksheet absence is non-blocking.

Canonical commands:

```bash
python tools/planctl.py --repo . wave review WN
python tools/planctl.py --repo . adopt-recommendations CAP-XX  # already complete for authored packets
python tools/planctl.py --repo . wave approve WN --by "Reviewer" --commit <git-sha>
# Only when an override or note was exported:
python tools/planctl.py --repo . apply-feedback CAP-XX <downloaded-json>
python tools/planctl.py --repo . wave approve WN --by "Reviewer" --commit <git-sha>
```

The Markdown plans remain authoritative. The review site is a generated human review surface and must be regenerated and validated after plan changes.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def build_site(repo: Path, output: Path, selected_capability: str | None = None) -> dict[str, Any]:
    """Build one coherent site while excluding concurrent destructive rebuilds."""
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / f".{output.name}.generation.lock"
    deadline = time.monotonic() + 60.0
    acquired = False
    while not acquired:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > 300.0
            except OSError:
                stale = False
            if stale:
                with suppress(OSError):
                    lock_path.unlink()
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for planning review-site generation lock: {lock_path}") from None
            time.sleep(0.05)
        else:
            try:
                os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
            finally:
                os.close(descriptor)
            acquired = True
    try:
        return _build_site_unlocked(repo, output, selected_capability)
    finally:
        with suppress(FileNotFoundError):
            lock_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", default="planning/review-site")
    parser.add_argument("--capability")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    output = (repo / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output).resolve()
    build_site(repo, output, args.capability)
    entry = output / (args.capability or "") / "index.html" if args.capability else output / "index.html"
    print(f"Generated planning review site: {entry.as_uri()}")
    print(f"Manifest: {(output / 'manifest.json').as_posix()}")
    return 0


REVIEW_CSS = r"""
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
.planning-nav { margin-bottom: 28px; }
.planning-nav-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin: 0 0 12px; padding: 4px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface-soft); }
.planning-nav-tab { min-width: 0; padding: 8px 6px; border: 1px solid transparent; border-radius: 7px; background: transparent; color: var(--text-soft); font-size: .76rem; font-weight: 800; cursor: pointer; }
.planning-nav-tab:hover { color: var(--text); border-color: var(--line); }
.planning-nav-tab[aria-selected="true"] { color: var(--primary); border-color: var(--line-strong); background: var(--surface); box-shadow: 0 2px 7px rgba(16,35,61,.08); }
.planning-nav-panel[hidden] { display: none; }
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
.status-stack { display: inline-grid; justify-items: end; gap: 5px; width: fit-content; }
.status-not-started { color: var(--text-soft); background: var(--surface-soft); }
.status-in-progress { color: var(--primary); background: var(--primary-soft); }
.status-completed { color: var(--success); background: var(--success-soft); }
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
.wave-capability-list { display: grid; gap: 14px; }
.wave-capability { border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); overflow: clip; }
.wave-capability > summary, .wave-slice-card > summary, .wave-task-card > summary { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 16px 18px; cursor: pointer; list-style-position: inside; }
.wave-capability > summary:hover, .wave-slice-card > summary:hover, .wave-task-card > summary:hover { background: var(--primary-soft); }
.wave-capability > summary:focus-visible, .wave-slice-card > summary:focus-visible, .wave-task-card > summary:focus-visible { outline: 3px solid var(--focus); outline-offset: -3px; }
.wave-capability h2 { margin: 4px 0; font: 700 1.25rem/1.2 var(--font-display); }
.wave-capability h2 a { color: var(--primary); text-decoration: none; }
.wave-capability p { margin: 4px 0; color: var(--text-soft); }
.wave-card-body { padding: 0 18px 18px; }
.wave-slice-list, .wave-task-list { display: grid; gap: 9px; margin: 16px 0 0; padding: 0; }
.wave-slice-card, .wave-task-card { border: 1px solid var(--line); border-radius: 9px; background: var(--canvas); overflow: clip; }
.wave-slice-card > summary > span, .wave-task-card > summary > span { display: grid; gap: 2px; }
.wave-slice-card > summary small, .wave-task-card > summary small { color: var(--text-soft); font-weight: 500; }
.wave-task-list { margin-left: 18px; }
.wave-task-card { background: var(--surface); }
.wave-task-card .wave-card-body { padding-top: 2px; }
.wave-slice-list { list-style-position: inside; }
.wave-slice-list li { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--canvas); }
.wave-slice-list li > span { display: grid; gap: 2px; font-weight: 750; }
.wave-slice-list a { color: var(--primary); text-decoration: none; }
.wave-slice-list small { color: var(--text-soft); font-weight: 500; }
.gate-criteria { display: grid; gap: 7px; padding-left: 22px; }
.slice-card { display: grid; grid-template-columns: 42px 1fr auto; align-items: center; gap: 14px; padding: 15px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); text-decoration: none; color: var(--text); }
.slice-card:hover { border-color: var(--primary); box-shadow: var(--shadow); }
.slice-card-index { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; background: var(--primary-soft); color: var(--primary); font-weight: 850; }
.slice-card h3 { margin: 2px 0; font: 700 1.08rem/1.25 var(--font-display); }
.slice-card p { margin: 0; color: var(--text-soft); font-size: .8rem; }
.task-list { display: grid; gap: 10px; }
.task-card { display: grid; grid-template-columns: 42px 1fr auto; align-items: center; gap: 14px; padding: 15px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); text-decoration: none; color: var(--text); }
.task-card:hover { border-color: var(--primary); box-shadow: var(--shadow); }
.task-card h3 { margin: 2px 0; font: 700 1.08rem/1.25 var(--font-display); }
.task-card p { margin: 0 0 4px; color: var(--text-soft); font-size: .8rem; }
.task-card small { color: var(--text-soft); }
.worksheet-meta { padding: 0 20px 8px; overflow-wrap: anywhere; color: var(--text-soft); }
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
  .slice-card .status-stack { grid-column: 2; justify-items: start; }
  .task-card { grid-template-columns: 34px 1fr; }
  .task-card .status { grid-column: 2; justify-self: start; }
  .wave-capability > summary, .wave-slice-card > summary, .wave-task-card > summary { align-items: flex-start; flex-direction: column; }
  .wave-task-list { margin-left: 0; }
}
@media print {
  .site-header, .side-panel, .site-footer, .review-toolbar, .page-turn { display: none !important; }
  .page-frame { display: block; }
  .main-panel { width: 100%; padding: 0; }
  details { display: block; }
  details > summary { display: none; }
  body { background: white; color: #10233d; }
}
"""


REVIEW_JS = r"""
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

  document.querySelectorAll("[data-planning-nav]").forEach((navigation) => {
    const tabs = Array.from(navigation.querySelectorAll("[data-nav-tab]"));
    const panels = Array.from(navigation.querySelectorAll("[data-nav-panel]"));
    const activate = (name, focus = false) => {
      tabs.forEach((tab) => {
        const selected = tab.dataset.navTab === name;
        tab.setAttribute("aria-selected", selected ? "true" : "false");
        tab.tabIndex = selected ? 0 : -1;
        if (selected && focus) tab.focus();
      });
      panels.forEach((panel) => { panel.hidden = panel.dataset.navPanel !== name; });
    };
    const initial = navigation.dataset.defaultTab || "capabilities";
    activate(initial);
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab.dataset.navTab || initial));
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        let next = index;
        if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = tabs.length - 1;
        activate(tabs[next].dataset.navTab || initial, true);
      });
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
    if (message) message.textContent = "Recommended defaults restored. Review any intended overrides before pre-Wave approval.";
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
      requested_action: value.approval_intent ? "include-in-pre-wave-approval" : "record-feedback",
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
"""


if __name__ == "__main__":
    raise SystemExit(main())
