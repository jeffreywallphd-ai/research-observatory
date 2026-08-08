#!/usr/bin/env python3
"""Prepare, review, apply feedback, approve, validate, and gate capability planning artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

OTHER_SENTINEL = "__OTHER__"
OTHER_PREFIX = "Other: "


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower().replace("&", " and ")).strip("-")[:120]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_backlog(root: Path):
    data = yaml.safe_load((root / "planning/backlog.yaml").read_text(encoding="utf-8"))
    return data, {cap["id"]: cap for cap in data.get("capabilities", [])}


def frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"{path}: unterminated YAML front matter")
    return yaml.safe_load(text[4:end]) or {}, text[end + 5 :]


def write_plan(path: Path, meta: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000).rstrip()
        + "\n---\n"
        + body.lstrip("\n"),
        encoding="utf-8",
    )


def capability_plan_path(root: Path, capability: str) -> Path:
    return root / "planning/capability-plans" / f"{capability}.md"


def slice_plan_paths(root: Path, capability: str) -> list[Path]:
    return sorted((root / "planning/slice-plans" / capability).glob("*.md"))


def review_page(root: Path, capability: str | None = None) -> Path:
    base = root / "planning/review-site"
    return base / capability / "index.html" if capability else base / "index.html"


def generate_review(root: Path, capability: str | None = None) -> int:
    command = [sys.executable, str(root / "tools/plan_review_site.py"), "--repo", str(root)]
    if capability:
        command.extend(["--capability", capability])
    return subprocess.run(command, check=False).returncode


def print_review_link(root: Path, capability: str | None = None) -> None:
    page = review_page(root, capability)
    if page.exists():
        print(f"Planning review page: {page.as_uri()}")
        print(f"Repository-relative page: {page.relative_to(root).as_posix()}")
    else:
        print(f"Planning review page has not been generated: {page}")


def scaffold_capability(root: Path, cap: dict[str, Any]) -> Path:
    path = capability_plan_path(root, cap["id"])
    if path.exists():
        return path
    decision_id = f"{cap['id']}-D01"
    meta = {
        "plan_schema_version": "1.1",
        "document_type": "capability-decision-plan",
        "baseline": "1.3",
        "supplemental_release": "generated",
        "capability_id": cap["id"],
        "title": cap["title"],
        "status": "proposed",
        "execution_mode": "long-running-capability-campaign",
        "decision_completion": "pending",
        "open_blocking_decisions": [decision_id],
        "slice_ids": [item["id"] for item in cap.get("slices", [])],
        "decisions": [
            {
                "id": decision_id,
                "title": "Complete capability-wide decision inventory",
                "candidates": ["Recommended candidate to be researched", "Credible alternative to be researched"],
                "recommendation": "Recommended candidate to be researched",
                "recommendation_basis": "Complete primary-source research and cross-slice analysis before approval.",
                "selected_option": None,
                "status": "recommended",
                "required_adr": None,
            }
        ],
        "approval": {"status": "pending", "approved_by": None, "approved_at": None, "approved_commit": None},
    }
    headings = [
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
    sections = []
    for heading in headings:
        if heading == "## 4. Decision register":
            sections.append(
                heading
                + "\n\n| Decision | Candidates | Recommendation | Selected | Status |\n|---|---|---|---|---|\n"
                + f"| `{decision_id}` | Replace with researched candidates | Replace with explicit recommendation | Pending | Recommended |\n\n"
                + "Replace this placeholder with the complete decision inventory before approval."
            )
        else:
            sections.append(heading + "\n\nComplete this section before approval.")
    body = (
        f"# {cap['id']} - Capability decision and execution plan\n\n"
        "> **Generated proposed packet.** Inspect every slice, replace every placeholder with researched candidate options and an explicit recommendation, resolve the complete register, approve all slice plans, and then approve this packet before implementation.\n\n"
        "> **Review surface.** Run `python tools/planctl.py --repo . review "
        + cap["id"]
        + "` and use the generated static pages to review all options and slice plans.\n\n"
        + "\n\n".join(sections)
        + "\n"
    )
    write_plan(path, meta, body)
    return path


def scaffold_slice(root: Path, cap: dict[str, Any], slice_: dict[str, Any]) -> Path:
    folder = root / "planning/slice-plans" / cap["id"]
    path = folder / f"{slice_['id']}-{slug(slice_['title'])}.md"
    if path.exists():
        return path
    meta = {
        "plan_schema_version": "1.1",
        "document_type": "slice-implementation-plan",
        "baseline": "1.3",
        "supplemental_release": "generated",
        "capability_id": cap["id"],
        "capability_plan": f"planning/capability-plans/{cap['id']}.md",
        "planning_gate": "capability-decision-complete",
        "slice_id": slice_["id"],
        "title": slice_["title"],
        "status": "proposed",
        "wave": slice_.get("wave", "W?"),
        "priority": slice_.get("priority", "P?"),
        "deployment_profiles": slice_.get("deployment_profiles", []),
        "platform_targets": slice_.get("platform_targets", []),
        "task_ids": [task["id"] for task in slice_.get("tasks", [])],
        "ui_reference": "RO-UI-ACADEMIC-MINIMAL-1.3",
        "approval": {"status": "pending", "approved_by": None, "approved_at": None, "approved_commit": None},
    }
    headings = [
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
    task_lines = "\n\n".join(
        f"### `{task['id']}` - {task['title']}\n\nObjective: {task.get('objective', '')}\n\nComplete ordered implementation, acceptance, evidence, failure/recovery, security, and independent-review details."
        for task in slice_.get("tasks", [])
    )
    sections = []
    for heading in headings:
        sections.append(heading + "\n\n" + (task_lines if heading.startswith("## 9.") else "Complete this section before approval."))
    body = (
        f"# {slice_['id']} - {slice_['title']}\n\n"
        "> **Generated proposed plan.** Complete this plan using the Vision, Systems Design, authoritative backlog, approved experience reference, and current primary research. It cannot authorize implementation until approved with the capability packet.\n\n"
        f"> **Review surface.** Run `python tools/planctl.py --repo . review {cap['id']}` and use the generated capability and slice pages during the one-time planning review.\n\n"
        + "\n\n".join(sections)
        + "\n"
    )
    write_plan(path, meta, body)
    return path


def run_validator(root: Path, tool: str, capability: str, approved: bool) -> int:
    command = [sys.executable, str(root / "tools" / tool), "--repo", str(root), "--capability", capability]
    if approved:
        command.append("--require-approved")
    return subprocess.run(command, check=False).returncode


def validate(root: Path, capability: str, approved: bool) -> int:
    first = run_validator(root, "capability_plan_check.py", capability, approved)
    second = run_validator(root, "slice_plan_check.py", capability, approved)
    third = subprocess.run(
        [sys.executable, str(root / "tools/plan_review_check.py"), "--repo", str(root)], check=False
    ).returncode
    return 1 if first or second or third else 0


def decision_report(root: Path, capability: str) -> int:
    path = capability_plan_path(root, capability)
    if not path.exists():
        print(f"Missing capability plan. Run: python tools/planctl.py --repo . prepare {capability}")
        return 1
    meta, _ = frontmatter(path)
    rows = []
    for decision in meta.get("decisions", []):
        rows.append(
            {
                "id": decision.get("id"),
                "title": decision.get("title"),
                "candidates": decision.get("candidates"),
                "recommendation": decision.get("recommendation"),
                "selected_option": decision.get("selected_option"),
                "status": decision.get("status"),
                "required_adr": decision.get("required_adr"),
            }
        )
    print(
        yaml.safe_dump(
            {
                "capability_id": capability,
                "plan_status": meta.get("status"),
                "decision_completion": meta.get("decision_completion"),
                "open_blocking_decisions": meta.get("open_blocking_decisions"),
                "approval": meta.get("approval"),
                "decisions": rows,
            },
            sort_keys=False,
            allow_unicode=True,
        )
    )
    return 0


def load_feedback(path: Path, capability: str, current_plan_hash: str) -> dict[str, Any]:
    feedback = json.loads(path.read_text(encoding="utf-8"))
    if feedback.get("document_type") != "capability-decision-feedback":
        raise ValueError("Feedback document_type must be capability-decision-feedback")
    if feedback.get("schema_version") not in {"1.0", "1.1"}:
        raise ValueError("Unsupported feedback schema_version; expected 1.0 or 1.1")
    if feedback.get("capability_id") != capability:
        raise ValueError(f"Feedback is for {feedback.get('capability_id')}, not {capability}")
    if feedback.get("capability_plan_sha256") != current_plan_hash:
        raise ValueError("Feedback was generated from a different capability-plan revision; regenerate the review site and re-export")
    return feedback


def apply_feedback(root: Path, capability: str, feedback_path: Path, *, archive: bool = True, regenerate: bool = True) -> Path | None:
    plan_path = capability_plan_path(root, capability)
    meta, body = frontmatter(plan_path)
    feedback = load_feedback(feedback_path, capability, sha256(plan_path))
    by_id = {item["id"]: item for item in meta.get("decisions", [])}
    supplied = {item.get("id"): item for item in feedback.get("decisions", [])}
    unknown = sorted(set(supplied) - set(by_id))
    if unknown:
        raise ValueError(f"Feedback contains unknown decision IDs: {unknown}")
    if set(supplied) != set(by_id):
        missing = sorted(set(by_id) - set(supplied))
        raise ValueError(f"Feedback must resolve the complete capability decision set; missing {missing}")

    for decision_id, decision in by_id.items():
        item = supplied[decision_id]
        selected = item.get("selected_option")
        rationale = str(item.get("rationale") or "").strip()
        candidates = decision.setdefault("candidates", [])
        if selected == OTHER_SENTINEL:
            brief = " ".join(str(item.get("other_option") or "").split())
            if not brief:
                raise ValueError(f"{decision_id}: Other requires a brief other_option description")
            if len(brief) > 180:
                raise ValueError(f"{decision_id}: Other description exceeds 180 characters")
            if not rationale:
                raise ValueError(f"{decision_id}: Other requires detailed rationale")
            selected = OTHER_PREFIX + brief
            if selected not in candidates:
                candidates.append(selected)
        else:
            if selected not in candidates:
                raise ValueError(f"{decision_id}: selected option is not one of the documented candidates")
            if selected != decision.get("recommendation") and not rationale:
                raise ValueError(f"{decision_id}: a non-recommended selection requires rationale")
        decision["selected_option"] = selected
        decision["status"] = "accepted"

    meta["open_blocking_decisions"] = []
    meta["decision_completion"] = "complete"
    write_plan(plan_path, meta, body)

    archive_path: Path | None = None
    if archive:
        archive_dir = root / "planning/decision-feedback" / capability
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = re.sub(r"[^0-9T]+", "-", str(feedback.get("reviewed_at") or datetime.now(timezone.utc).isoformat())).strip("-")[:32]
        archive_path = archive_dir / f"{stamp}-{sha256(feedback_path)[:12]}.json"
        shutil.copy2(feedback_path, archive_path)

    if regenerate:
        generate_review(root, capability)
    return archive_path



def adopt_recommendations(root: Path, capability: str, *, regenerate: bool = True) -> int:
    """Resolve every fully researched decision to its documented recommendation.

    Placeholder candidate inventories are deliberately rejected. This command is intended
    after the planning agent has completed cross-slice research and authored the packet.
    """
    plan_path = capability_plan_path(root, capability)
    meta, body = frontmatter(plan_path)
    decisions = meta.get("decisions") or []
    if not decisions:
        raise ValueError("Capability packet has no decisions")
    placeholder_markers = ("to be researched", "replace with", "complete capability-wide decision inventory")
    for decision in decisions:
        recommendation = decision.get("recommendation")
        candidates = decision.get("candidates") or []
        joined = " ".join([str(decision.get("title", "")), str(recommendation or ""), *map(str, candidates)]).lower()
        if any(marker in joined for marker in placeholder_markers):
            raise ValueError(f"{decision.get('id')}: planning placeholders must be replaced by researched candidates before recommendation adoption")
        if recommendation not in candidates:
            raise ValueError(f"{decision.get('id')}: recommendation is not a documented candidate")
        decision["selected_option"] = recommendation
        decision["status"] = "accepted"
    meta["open_blocking_decisions"] = []
    meta["decision_completion"] = "complete"
    write_plan(plan_path, meta, body)
    if regenerate:
        generate_review(root, capability)
    print(f"Adopted {len(decisions)} best-in-class recommendations as completed decisions for {capability}.")
    print("The capability and slice plans remain proposed until the one explicit capability approval.")
    return 0

def approve(root: Path, capability: str, feedback_path: Path | None, approver: str, commit: str) -> int:
    plan_path = capability_plan_path(root, capability)
    tracked_paths = [plan_path] + slice_plan_paths(root, capability)
    originals = {path: path.read_text(encoding="utf-8") for path in tracked_paths}
    try:
        if feedback_path:
            apply_feedback(root, capability, feedback_path, archive=True, regenerate=False)
        meta, body = frontmatter(plan_path)
        unresolved = [item["id"] for item in meta.get("decisions", []) if item.get("status") != "accepted" or not item.get("selected_option")]
        if meta.get("open_blocking_decisions") or unresolved or meta.get("decision_completion") != "complete":
            raise ValueError("Capability decisions are not complete. Finish the researched packet and run adopt-recommendations, or apply a complete review-site override record.")
        approved_at = datetime.now(timezone.utc).isoformat()
        meta["status"] = "approved"
        meta["approval"] = {
            "status": "approved",
            "approved_by": approver,
            "approved_at": approved_at,
            "approved_commit": commit,
        }
        write_plan(plan_path, meta, body)
        for path in tracked_paths[1:]:
            slice_meta, slice_body = frontmatter(path)
            slice_meta["status"] = "approved"
            slice_meta["approval"] = {
                "status": "approved",
                "approved_by": approver,
                "approved_at": approved_at,
                "approved_commit": commit,
            }
            write_plan(path, slice_meta, slice_body)
        generate_review(root, capability)
        if validate(root, capability, True):
            raise ValueError("Approval-mode validation failed; all plan changes were rolled back")
    except Exception:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")
        generate_review(root, capability)
        raise
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("prepare", "validate", "ready", "decisions", "review", "adopt-recommendations"):
        command = sub.add_parser(name)
        command.add_argument("capability")
        if name in ("validate", "ready"):
            command.add_argument("--require-approved", action="store_true")

    apply_parser = sub.add_parser("apply-feedback")
    apply_parser.add_argument("capability")
    apply_parser.add_argument("feedback")

    approve_parser = sub.add_parser("approve")
    approve_parser.add_argument("capability")
    approve_parser.add_argument("--feedback")
    approve_parser.add_argument("--by", required=True)
    approve_parser.add_argument("--commit", required=True)

    args = parser.parse_args()
    root = Path(args.repo).resolve()
    _, caps = load_backlog(root)
    capability = args.capability
    if capability not in caps:
        print(f"Unknown capability {capability}", file=sys.stderr)
        return 2
    cap = caps[capability]

    try:
        if args.command == "prepare":
            created: list[Path] = []
            cap_path = capability_plan_path(root, capability)
            if not cap_path.exists():
                created.append(scaffold_capability(root, cap))
            for slice_ in cap.get("slices", []):
                expected = root / "planning/slice-plans" / capability / f"{slice_['id']}-{slug(slice_['title'])}.md"
                if not expected.exists():
                    created.append(scaffold_slice(root, cap, slice_))
            if created:
                for path in created:
                    print("Created", path.relative_to(root))
            else:
                print(f"All capability and slice planning artifacts already exist for {capability}.")
            generate_review(root, capability)
            print("Generated placeholders remain proposed until researched. After authoring the complete packet, run `adopt-recommendations`; the best-in-class defaults then count as completed decisions. One explicit capability approval is still required.")
            print_review_link(root, capability)
            return 0

        if args.command == "adopt-recommendations":
            result = adopt_recommendations(root, capability)
            print_review_link(root, capability)
            return result

        if args.command == "review":
            result = generate_review(root, capability)
            print_review_link(root, capability)
            return result

        if args.command == "decisions":
            result = decision_report(root, capability)
            generate_review(root, capability)
            print_review_link(root, capability)
            return result

        if args.command == "apply-feedback":
            archive = apply_feedback(root, capability, Path(args.feedback).resolve())
            print(f"Applied decision feedback to {capability}.")
            if archive:
                print(f"Archived feedback: {archive.relative_to(root)}")
            print("The capability and slice plans remain unapproved until the explicit approve command is run.")
            print("If feedback used Other, the brief description is now a canonical candidate; detailed rationale remains in the archived feedback record.")
            print_review_link(root, capability)
            return 0

        if args.command == "approve":
            feedback = Path(args.feedback).resolve() if args.feedback else None
            result = approve(root, capability, feedback, args.by, args.commit)
            print(f"Approved {capability} and all contained slice plans at commit {args.commit}.")
            print_review_link(root, capability)
            return result

        generate_review(root, capability)
        if args.command == "validate":
            result = validate(root, capability, args.require_approved)
            print_review_link(root, capability)
            return result
        if args.command == "ready":
            result = validate(root, capability, True)
            if result:
                print("Capability is not ready. Confirm or override the resolved recommendation defaults, approve the capability and all slice plans, and use the linked review pages.", file=sys.stderr)
            print_review_link(root, capability)
            return result
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        generate_review(root, capability)
        print_review_link(root, capability)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
