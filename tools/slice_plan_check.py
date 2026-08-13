#!/usr/bin/env python3
"""Validate Research Observatory slice implementation plans."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

REQUIRED_HEADINGS = [
    "## 0. Plan control",
    "## 1. Purpose and contribution to the larger vision",
    "## 2. Scope",
    "## 3. Authority, dependencies, and campaign stop conditions",
    "## 4. Selected implementation decisions",
    "## 5. Architecture and implementation design",
    "## 6. User experience and approved reference",
    "## 7. Security, privacy, rights and research integrity",
    "## 8. Failure, cancellation, restart and recovery",
    "## 9. Task-by-task implementation plan",
    "## 10. Slice-wide verification matrix",
    "## 11. Performance and resource budgets",
    "## 12. Observability and provenance",
    "## 13. Adjacent-slice handoffs",
    "## 14. Migration and backward compatibility",
    "## 15. Required slice evidence bundle",
    "## 16. Definition of Ready",
    "## 17. Definition of Done",
    "## 18. Risks and mitigations",
    "## 19. Required ADRs and human decisions",
    "## 20. Research and standards basis",
    "## 21. AI implementation runbook",
]


def frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unterminated YAML front matter")
    return yaml.safe_load(text[4:end]) or {}, text[end + 5 :]


def indexes(backlog: dict[str, Any]):
    caps, slices = {}, {}
    for cap in backlog.get("capabilities", []):
        caps[cap["id"]] = cap
        for sl in cap.get("slices", []):
            sl = dict(sl)
            sl["capability_id"] = cap["id"]
            slices[sl["id"]] = sl
    return caps, slices


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--capability", action="append", help="Validate complete coverage for this capability; repeatable")
    ap.add_argument("--wave", help="Require approval only for slice plans in this wave")
    ap.add_argument("--require-approved", action="store_true")
    ns = ap.parse_args()
    root = Path(ns.repo).resolve()
    backlog = yaml.safe_load((root / "planning/backlog.yaml").read_text(encoding="utf-8"))
    caps, slices = indexes(backlog)
    plan_root = root / "planning/slice-plans"
    schema = json.loads((plan_root / "slice-plan.schema.json").read_text(encoding="utf-8"))
    selected = set(ns.capability or [])
    errors: list[str] = []
    seen: dict[str, Path] = {}
    plans = []

    paths = sorted(plan_root.glob("CAP-*/*.md"))
    if selected:
        paths = [p for p in paths if p.parent.name in selected]
    for path in paths:
        try:
            meta, body = frontmatter(path)
        except Exception as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
            continue
        for err in jsonschema.Draft202012Validator(schema).iter_errors(meta):
            errors.append(f"{path.relative_to(root)}: schema {err.message}")
        sid_value, cid_value = meta.get("slice_id"), meta.get("capability_id")
        sid = sid_value if isinstance(sid_value, str) else ""
        cid = cid_value if isinstance(cid_value, str) else ""
        if not sid:
            errors.append(f"{path.relative_to(root)}: slice_id must be a non-empty string")
            continue
        if not cid:
            errors.append(f"{path.relative_to(root)}: capability_id must be a non-empty string")
            continue
        if sid in seen:
            errors.append(f"duplicate plan for {sid}: {seen[sid]} and {path}")
        seen[sid] = path
        plans.append((path, meta, body))
        if sid not in slices:
            errors.append(f"{path.relative_to(root)}: unknown slice {sid}")
            continue
        sl = slices[sid]
        if cid != sl["capability_id"]:
            errors.append(f"{sid}: capability mismatch {cid}")
        capability_plan = meta.get("capability_plan")
        if capability_plan != f"planning/capability-plans/{cid}.md":
            errors.append(f"{sid}: capability_plan link is incorrect")
        if not isinstance(capability_plan, str) or not (root / capability_plan).exists():
            errors.append(f"{sid}: linked capability plan is missing")
        if meta.get("title") != sl.get("title"):
            errors.append(f"{sid}: title mismatch")
        expected = [t["id"] for t in sl.get("tasks", [])]
        if meta.get("task_ids") != expected:
            errors.append(f"{sid}: task_ids must exactly match backlog order")
        for heading in REQUIRED_HEADINGS:
            if heading not in body:
                errors.append(f"{sid}: missing heading {heading}")
        for tid in expected:
            if tid not in body:
                errors.append(f"{sid}: body does not cover {tid}")
        words = len(re.findall(r"\b\w+[\w’-]*\b", body))
        if words < 1800:
            errors.append(f"{sid}: plan is too thin ({words} words; minimum 1800)")
        if ns.require_approved and (ns.wave is None or meta.get("wave") == ns.wave):
            approval = meta.get("approval") or {}
            if meta.get("status") != "approved" or approval.get("status") != "approved":
                errors.append(f"{sid}: plan is not approved")
            for key in ("approved_by", "approved_at", "approved_commit"):
                if not approval.get(key):
                    errors.append(f"{sid}: approval.{key} is required")

    for cid in selected:
        if cid not in caps:
            errors.append(f"unknown capability {cid}")
            continue
        for sl in caps[cid].get("slices", []):
            if sl["id"] not in seen:
                errors.append(f"{cid}: missing slice plan {sl['id']}; run `python tools/planctl.py prepare {cid}`")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    scope = ",".join(sorted(selected)) if selected else "all authored plans"
    print(
        f"Valid slice implementation plans: {len(plans)}; scope={scope}; wave={ns.wave or 'all'}; "
        f"approval_required={ns.require_approved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
