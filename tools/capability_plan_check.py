#!/usr/bin/env python3
"""Validate capability decision plans and the one-time planning gate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

REQUIRED_HEADINGS = [
    "## 0. Control and authority",
    "## 1. Capability outcome and production-ready exit",
    "## 2. Slice map and end-to-end dependency logic",
    "## 3. Decision-making protocol",
    "## 4. Decision register",
    "## 5. Cross-slice architecture contract",
    "## 6. Experience and workflow contract",
    "## 7. Security, privacy, rights and research-integrity decisions",
    "## 8. Capability-wide verification strategy",
    "## 9. Long-running execution contract",
    "## 10. Plan and approval checklist",
    "## 11. Research and technical basis",
    "## 12. Approval record",
]


def frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unterminated YAML front matter")
    return yaml.safe_load(text[4:end]) or {}, text[end + 5 :]


def body_decision_ids(body: str) -> list[str]:
    if "## 4. Decision register" not in body:
        return []
    section = body.split("## 4. Decision register", 1)[1]
    if "## 5." in section:
        section = section.split("## 5.", 1)[0]
    return re.findall(r"`(CAP-[0-9]{2}-D[0-9]{2,3})`", section)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--capability", action="append", help="Validate only the named capability; repeatable")
    ap.add_argument("--require-approved", action="store_true")
    ns = ap.parse_args()

    root = Path(ns.repo).resolve()
    backlog = yaml.safe_load((root / "planning/backlog.yaml").read_text(encoding="utf-8"))
    caps = {c["id"]: c for c in backlog.get("capabilities", [])}
    pdir = root / "planning/capability-plans"
    schema = json.loads((pdir / "capability-plan.schema.json").read_text(encoding="utf-8"))
    selected = set(ns.capability or [])
    errors: list[str] = []

    for cid in selected:
        if cid not in caps:
            errors.append(f"unknown capability {cid}")
        elif not (pdir / f"{cid}.md").exists():
            errors.append(f"{cid}: missing capability plan; run `python tools/planctl.py prepare {cid}`")

    paths = sorted(pdir.glob("CAP-*.md"))
    if selected:
        paths = [p for p in paths if p.stem in selected]

    for path in paths:
        try:
            meta, body = frontmatter(path)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        for err in jsonschema.Draft202012Validator(schema).iter_errors(meta):
            errors.append(f"{path.name}: schema {err.message}")
        cid = meta.get("capability_id")
        if cid not in caps:
            errors.append(f"{path.name}: unknown capability {cid}")
            continue
        cap = caps[cid]
        expected_slices = [s["id"] for s in cap.get("slices", [])]
        if meta.get("title") != cap.get("title"):
            errors.append(f"{cid}: title mismatch with backlog")
        if meta.get("slice_ids") != expected_slices:
            errors.append(f"{cid}: slice_ids must exactly match backlog order")
        for heading in REQUIRED_HEADINGS:
            if heading not in body:
                errors.append(f"{cid}: missing heading {heading}")

        decisions = meta.get("decisions") or []
        ids = [d.get("id") for d in decisions]
        if len(ids) != len(set(ids)):
            errors.append(f"{cid}: duplicate decision IDs")
        if set(meta.get("open_blocking_decisions") or []) - set(ids):
            errors.append(f"{cid}: open_blocking_decisions contains unknown decision IDs")
        table_ids = body_decision_ids(body)
        if set(ids) != set(table_ids):
            errors.append(f"{cid}: front-matter decision IDs do not match the decision register table")
        for d in decisions:
            candidates = d.get("candidates") or []
            recommendation = d.get("recommendation")
            selected_option = d.get("selected_option")
            if recommendation not in candidates:
                errors.append(f"{cid}: {d.get('id')} recommendation must be one of candidates")
            if selected_option is not None and selected_option not in candidates:
                errors.append(f"{cid}: {d.get('id')} selected_option must be one of candidates")

        # Authored packets may remain unapproved, but their researched best-in-class
        # defaults must already be completed decisions. Generated placeholder packets
        # are the only allowed pending state.
        if meta.get("supplemental_release") != "generated":
            if meta.get("decision_completion") != "complete":
                errors.append(f"{cid}: authored packet must have decision_completion complete")
            if meta.get("open_blocking_decisions"):
                errors.append(f"{cid}: authored packet must not retain open blocking decisions")
            placeholder_markers = (
                "to be researched",
                "replace with",
                "placeholder",
                "tbd",
                "todo",
                "recommended candidate",
            )
            for d in decisions:
                if d.get("status") != "accepted" or not d.get("selected_option"):
                    errors.append(f"{cid}: authored decision {d.get('id')} must be selected and accepted")
                searchable = " ".join(
                    [str(d.get("title", "")), str(d.get("recommendation", "")), *map(str, d.get("candidates") or [])]
                ).lower()
                if any(marker in searchable for marker in placeholder_markers):
                    errors.append(f"{cid}: authored decision {d.get('id')} still contains a planning placeholder")

        if ns.require_approved:
            approval = meta.get("approval") or {}
            if meta.get("status") != "approved":
                errors.append(f"{cid}: status must be approved")
            if meta.get("decision_completion") != "complete":
                errors.append(f"{cid}: decision_completion must be complete")
            if meta.get("open_blocking_decisions"):
                errors.append(f"{cid}: open_blocking_decisions must be empty")
            if approval.get("status") != "approved":
                errors.append(f"{cid}: approval.status must be approved")
            for key in ("approved_by", "approved_at", "approved_commit"):
                if not approval.get(key):
                    errors.append(f"{cid}: approval.{key} is required")
            for d in decisions:
                if d.get("status") != "accepted":
                    errors.append(f"{cid}: decision {d.get('id')} must be accepted")
                if not d.get("selected_option"):
                    errors.append(f"{cid}: decision {d.get('id')} requires selected_option")
            for sid in expected_slices:
                if not isinstance(cid, str):
                    errors.append(f"{path.name}: capability_id must be a string")
                    break
                matches = list((root / "planning/slice-plans" / cid).glob(f"{sid}-*.md"))
                if len(matches) != 1:
                    errors.append(f"{cid}: expected exactly one slice plan for {sid}")
                    continue
                smeta, _ = frontmatter(matches[0])
                approval2 = smeta.get("approval") or {}
                if smeta.get("status") != "approved" or approval2.get("status") != "approved":
                    errors.append(f"{cid}: slice plan {sid} is not approved")
                for key in ("approved_by", "approved_at", "approved_commit"):
                    if not approval2.get(key):
                        errors.append(f"{cid}: slice plan {sid} approval.{key} is required")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    scope = ",".join(sorted(selected)) if selected else "all authored"
    print(f"Valid capability decision plans: {len(paths)}; scope={scope}; approval_required={ns.require_approved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
