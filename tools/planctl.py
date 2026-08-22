#!/usr/bin/env python3
"""Prepare, review, approve, and validate Wave planning packets and their component plans."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

OTHER_SENTINEL = "__OTHER__"
OTHER_PREFIX = "Other: "
ECR_ID_PATTERN = re.compile(r"^ECR-[0-9]{4}$")
AMENDMENT_ID_PATTERN = re.compile(r"^W(?:[0-9]|1[01])\.A[0-9]{2}$")


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


def wave_capabilities(data: dict[str, Any], wave_id: str) -> list[dict[str, Any]]:
    return [
        capability
        for capability in data.get("capabilities", [])
        if any(slice_.get("wave") == wave_id for slice_ in capability.get("slices", []))
    ]


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


def wave_review_page(root: Path, wave_id: str) -> Path:
    return root / "planning" / "review-site" / "waves" / f"{wave_id}.html"


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


def print_wave_review_link(root: Path, wave_id: str) -> None:
    page = wave_review_page(root, wave_id)
    if page.exists():
        print(f"Pre-Wave approval page: {page.as_uri()}")
        print(f"Repository-relative page: {page.relative_to(root).as_posix()}")
    else:
        print(f"Pre-Wave approval page has not been generated: {page}")


def ecr_packet_path(root: Path, change_request_id: str) -> Path:
    if ECR_ID_PATTERN.fullmatch(change_request_id) is None:
        raise ValueError(f"Invalid enabler change request identity {change_request_id!r}")
    return root / "planning" / "enabler-change-requests" / f"{change_request_id}.packet.json"


def ecr_review_page(root: Path, change_request_id: str) -> Path:
    generated = root / "planning" / "review-site" / "enablers" / f"{change_request_id}.html"
    if generated.exists():
        return generated
    return root / "planning" / "enabler-change-requests" / f"{change_request_id}-review.html"


def print_ecr_review_links(root: Path, change_request_id: str) -> None:
    page = ecr_review_page(root, change_request_id)
    packet = ecr_packet_path(root, change_request_id)
    proposal = packet.with_name(f"{change_request_id}.md")
    for label, path in (
        ("Enabler review page", page),
        ("Canonical proposal", proposal),
        ("Hash-bound packet", packet),
    ):
        if path.exists():
            print(f"{label}: {path.as_uri()}")
            print(f"Repository-relative {label.lower()}: {path.relative_to(root).as_posix()}")
        else:
            print(f"{label} has not been generated: {path}")


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
        "execution_mode": "wave-contribution",
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
        "> **Generated proposed packet.** Resolve the capability-wide decision register and classify every decision by its binding Wave. Each pre-Wave approval then binds only that Wave's exact decision inventory together with every slice plan assigned to it at one immutable commit; inherited and future decisions remain nonbinding context.\n\n"
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
        sections.append(
            heading + "\n\n" + (task_lines if heading.startswith("## 9.") else "Complete this section before approval.")
        )
    body = (
        f"# {slice_['id']} - {slice_['title']}\n\n"
        "> **Generated proposed plan.** Complete this plan using the Vision, Systems Design, authoritative backlog, approved experience reference, and current primary research. It authorizes only its ordered slice after its binding capability decisions and this slice's complete Wave packet are approved.\n\n"
        f"> **Review surface.** Run `python tools/planctl.py --repo . wave review {slice_.get('wave', 'W?')}` and use the generated complete Wave packet.\n\n"
        + "\n\n".join(sections)
        + "\n"
    )
    write_plan(path, meta, body)
    return path


def run_validator(root: Path, tool: str, capability: str, approved: bool, wave: str | None = None) -> int:
    command = [sys.executable, str(root / "tools" / tool), "--repo", str(root), "--capability", capability]
    if wave:
        command.extend(["--wave", wave])
    if approved:
        command.append("--require-approved")
    return subprocess.run(command, check=False).returncode


def validate(root: Path, capability: str, approved: bool, wave: str | None = None) -> int:
    first = run_validator(root, "capability_plan_check.py", capability, approved, wave)
    second = run_validator(root, "slice_plan_check.py", capability, approved, wave)
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
                "binding_waves": decision.get("binding_waves"),
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
        raise ValueError(
            "Feedback was generated from a different capability-plan revision; regenerate the review site and re-export"
        )
    return feedback


def apply_feedback(
    root: Path, capability: str, feedback_path: Path, *, archive: bool = True, regenerate: bool = True
) -> Path | None:
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
        stamp = re.sub(r"[^0-9T]+", "-", str(feedback.get("reviewed_at") or datetime.now(UTC).isoformat())).strip("-")[
            :32
        ]
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
            raise ValueError(
                f"{decision.get('id')}: planning placeholders must be replaced by researched candidates before recommendation adoption"
            )
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
    print("The capability decisions and slice plans remain proposed until the complete Wave packet is approved.")
    return 0


def approve(
    root: Path,
    capability: str,
    feedback_path: Path | None,
    approver: str,
    commit: str,
    wave: str | None = None,
) -> int:
    plan_path = capability_plan_path(root, capability)
    all_slice_paths = slice_plan_paths(root, capability)
    selected_slice_paths = []
    for path in all_slice_paths:
        slice_meta, _ = frontmatter(path)
        if wave is None or slice_meta.get("wave") == wave:
            selected_slice_paths.append(path)
    if wave and not selected_slice_paths:
        raise ValueError(f"{capability} has no slice plan in {wave}")
    tracked_paths = [plan_path, *selected_slice_paths]
    originals = {path: path.read_text(encoding="utf-8") for path in tracked_paths}
    try:
        if feedback_path:
            apply_feedback(root, capability, feedback_path, archive=True, regenerate=False)
        meta, body = frontmatter(plan_path)
        unresolved = [
            item["id"]
            for item in meta.get("decisions", [])
            if item.get("status") != "accepted" or not item.get("selected_option")
        ]
        if meta.get("open_blocking_decisions") or unresolved or meta.get("decision_completion") != "complete":
            raise ValueError(
                "Capability decisions are not complete. Finish the researched packet and run adopt-recommendations, or apply a complete review-site override record."
            )
        approved_at = datetime.now(UTC).isoformat()
        if meta.get("status") != "approved":
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
        if validate(root, capability, True, wave):
            raise ValueError("Approval-mode validation failed; all plan changes were rolled back")
    except Exception:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")
        generate_review(root, capability)
        raise
    return 0


def validate_wave(root: Path, wave_id: str, approved: bool) -> int:
    data, _ = load_backlog(root)
    wave = next((item for item in data.get("waves", []) if item.get("id") == wave_id), None)
    if wave is None:
        raise ValueError(f"Unknown Wave {wave_id}")
    contributing = wave_capabilities(data, wave_id)
    if not contributing:
        raise ValueError(f"{wave_id} has no contributing capability slices")
    failures = 0
    expected_capability_ids = [str(capability["id"]) for capability in contributing]
    expected_slice_ids = [
        str(slice_["id"])
        for capability in contributing
        for slice_ in capability.get("slices", [])
        if slice_.get("wave") == wave_id
    ]
    expected_decision_ids: list[str] = []
    for capability in contributing:
        capability_id = str(capability["id"])
        if capability_id == "CAP-00" and not capability_plan_path(root, capability_id).exists():
            continue  # W0 predates planctl packets and is bound by its migrated approval record.
        if not capability_plan_path(root, capability_id).exists():
            print(f"ERROR: missing capability plan for {capability_id}", file=sys.stderr)
            failures += 1
            continue
        capability_meta, _ = frontmatter(capability_plan_path(root, capability_id))
        expected_decision_ids.extend(
            str(decision["id"])
            for decision in capability_meta.get("decisions", [])
            if wave_id in (decision.get("binding_waves") or [])
        )
        failures += int(bool(run_validator(root, "capability_plan_check.py", capability_id, approved, wave_id)))
        failures += int(bool(run_validator(root, "slice_plan_check.py", capability_id, approved, wave_id)))
    if approved:
        wave_approval = wave.get("approval") or {}
        if wave_approval.get("status") != "APPROVED":
            print(f"ERROR: {wave_id} pre-Wave packet is not explicitly APPROVED", file=sys.stderr)
            failures += 1
        for field, expected in (
            ("capability_ids", expected_capability_ids),
            ("decision_ids", expected_decision_ids),
            ("slice_ids", expected_slice_ids),
        ):
            if wave_approval.get(field) != expected:
                print(f"ERROR: {wave_id} approval {field} is not the exact Wave inventory", file=sys.stderr)
                failures += 1
        for capability in contributing:
            capability_id = str(capability["id"])
            if capability_id == "CAP-00":
                continue
            for path in slice_plan_paths(root, capability_id):
                slice_meta, _ = frontmatter(path)
                if slice_meta.get("wave") != wave_id:
                    continue
                slice_approval = slice_meta.get("approval") or {}
                for slice_field, wave_field in (
                    ("approved_by", "approved_by"),
                    ("approved_at", "approved_at"),
                    ("approved_commit", "approved_commit"),
                ):
                    if slice_approval.get(slice_field) != wave_approval.get(wave_field):
                        print(
                            f"ERROR: {slice_meta.get('slice_id')} approval {slice_field} is not bound to the "
                            f"exact {wave_id} approval",
                            file=sys.stderr,
                        )
                        failures += 1
    failures += int(
        bool(
            subprocess.run(
                [sys.executable, str(root / "tools/plan_review_check.py"), "--repo", str(root)], check=False
            ).returncode
        )
    )
    return 1 if failures else 0


def prepare_wave(root: Path, wave_id: str) -> list[Path]:
    data, _ = load_backlog(root)
    contributing = wave_capabilities(data, wave_id)
    if not contributing:
        raise ValueError(f"Unknown or empty Wave {wave_id}")
    created: list[Path] = []
    for capability in contributing:
        capability_id = str(capability["id"])
        if capability_id == "CAP-00":
            continue
        cap_path = capability_plan_path(root, capability_id)
        if not cap_path.exists():
            created.append(scaffold_capability(root, capability))
        for slice_ in capability.get("slices", []):
            if slice_.get("wave") != wave_id:
                continue
            expected = root / "planning" / "slice-plans" / capability_id / f"{slice_['id']}-{slug(slice_['title'])}.md"
            if not expected.exists():
                created.append(scaffold_slice(root, capability, slice_))
    generate_review(root)
    return created


def _json_document(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return document, payload


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _schema_errors(document: dict[str, Any], schema_path: Path, label: str) -> list[str]:
    try:
        schema, _ = _json_document(schema_path)
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError, json.JSONDecodeError, SchemaError) as exc:
        return [f"{label}: schema is unavailable or invalid: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    return [
        f"{label}: schema error at {'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in errors
    ]


def _safe_ecr_file(root: Path, relative: object) -> Path | None:
    if (
        not isinstance(relative, str)
        or "\\" in relative
        or ":" in relative
        or re.search(r"(?:^|/)\.{1,2}(?:/|$)", relative)
    ):
        return None
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or not relative.startswith("planning/enabler-change-requests/")
    ):
        return None
    candidate = root.joinpath(*pure.parts)
    current = root
    junction = getattr(os.path, "isjunction", lambda _path: False)
    for part in pure.parts:
        current = current / part
        if (current.exists() or current.is_symlink()) and (current.is_symlink() or junction(current)):
            return None
    path = candidate.resolve()
    expected = (root / "planning" / "enabler-change-requests").resolve()
    try:
        path.relative_to(expected)
    except ValueError:
        return None
    return path


def _git_blob(root: Path, commit: str, relative: str) -> bytes | None:
    completed = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=root, capture_output=True, check=False)
    return completed.stdout if completed.returncode == 0 else None


def _git_commit_exists(root: Path, commit: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _git_is_ancestor(root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _approval_introduction_commit(root: Path, relative: str) -> str | None:
    completed = subprocess.run(
        ["git", "log", "--format=%H", "--diff-filter=A", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    commits = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return commits[0] if completed.returncode == 0 and len(commits) == 1 else None


def _historical_wave_approval(root: Path, commit: str, wave_id: str) -> dict[str, Any] | None:
    payload = _git_blob(root, commit, "planning/backlog.yaml")
    if payload is None:
        return None
    try:
        document = yaml.safe_load(payload.decode("utf-8"))
    except UnicodeError, yaml.YAMLError:
        return None
    if not isinstance(document, dict):
        return None
    wave = next((item for item in document.get("waves", []) if item.get("id") == wave_id), None)
    return (wave or {}).get("approval")


def _packet_file_errors(root: Path, packet: dict[str, Any], packet_commit: str | None = None) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item in packet.get("files", []):
        relative = item.get("path") if isinstance(item, dict) else None
        if not isinstance(relative, str) or relative in seen:
            errors.append("ECR packet file inventory contains a duplicate or invalid path")
            continue
        seen.add(relative)
        path = _safe_ecr_file(root, relative)
        if path is None:
            errors.append(f"ECR packet file path is unsafe: {relative!r}")
            continue
        try:
            payload = path.read_bytes()
        except OSError as exc:
            errors.append(f"ECR packet file is unreadable: {relative}: {exc}")
            continue
        if hashlib.sha256(payload).hexdigest() != item.get("sha256"):
            errors.append(f"ECR packet file hash mismatch: {relative}")
        if packet_commit and _git_blob(root, packet_commit, relative) != payload:
            errors.append(f"ECR packet file differs from {packet_commit}: {relative}")
    roles = [item.get("role") for item in packet.get("files", []) if isinstance(item, dict)]
    for required in ("canonical-proposal", "proposal-schema", "human-review"):
        if roles.count(required) != 1:
            errors.append(f"ECR packet must contain exactly one {required} file")
    return errors


def _approval_record_errors(
    root: Path,
    packet: dict[str, Any],
    record: dict[str, Any],
    payload: bytes,
    *,
    approval_relative: str,
    require_committed_history: bool,
) -> list[str]:
    errors = _schema_errors(
        record,
        root / "planning" / "wave-amendment-approvals" / "wave-amendment-approval.schema.json",
        "Wave amendment approval",
    )
    amendment_id = packet.get("proposedAmendmentId")
    packet_relative = f"planning/enabler-change-requests/{packet.get('changeRequestId')}.packet.json"
    proposal: dict[str, Any] = next(
        (
            candidate
            for item in packet.get("files", [])
            if (candidate := _json_object(item)).get("role") == "canonical-proposal"
        ),
        {},
    )
    packet_reference = _json_object(record.get("packet"))
    effective = _json_object(record.get("effectiveBase"))
    authority = _json_object(packet.get("authority"))
    authority_chain = _json_object(packet.get("authorityChain"))
    review = _json_object(record.get("independentPacketReview"))
    bootstrap = _json_object(packet.get("bootstrapUnit"))
    expected_common = (
        ("amendmentId", record.get("amendmentId"), amendment_id),
        ("changeRequestId", record.get("changeRequestId"), packet.get("changeRequestId")),
        ("targetWave", record.get("targetWave"), packet.get("targetWave")),
        ("bootstrapUnit", record.get("bootstrapUnit"), bootstrap.get("id")),
        ("packet.path", packet_reference.get("path"), packet_relative),
        ("packet.proposalPath", packet_reference.get("proposalPath"), proposal.get("path")),
        ("packet.proposalSha256", packet_reference.get("proposalSha256"), proposal.get("sha256")),
    )
    expected: tuple[tuple[str, Any, Any], ...]
    if packet.get("schemaVersion") in {"2.0-proposal", "3.0-proposal"}:
        expected = (
            *expected_common,
            ("effectiveBase", effective, authority_chain),
        )
    else:
        expected = (
            *expected_common,
            (
                "effectiveBase.originalPacketCommit",
                effective.get("originalPacketCommit"),
                authority.get("originalWavePacketCommit"),
            ),
            (
                "effectiveBase.originalApprovalRecordCommit",
                effective.get("originalApprovalRecordCommit"),
                authority.get("originalApprovalRecordCommit"),
            ),
            ("effectiveBase.legacyAmendmentId", effective.get("legacyAmendmentId"), authority.get("legacyAmendmentId")),
            (
                "effectiveBase.legacyAmendmentPacketCommit",
                effective.get("legacyAmendmentPacketCommit"),
                authority.get("legacyAmendmentPacketCommit"),
            ),
            (
                "effectiveBase.legacyAmendmentRecordCommit",
                effective.get("legacyAmendmentRecordCommit"),
                authority.get("legacyAmendmentRecordCommit"),
            ),
            (
                "effectiveBase.effectivePacketCommit",
                effective.get("effectivePacketCommit"),
                authority.get("effectiveBasePacketCommit"),
            ),
        )
    for field, actual, wanted in expected:
        if actual != wanted:
            errors.append(f"Wave amendment approval {field} does not match the ECR packet")
    if record.get("authorizedTaskIds") != packet.get("authorizedTaskIds"):
        errors.append("Wave amendment approval task inventory does not match the ECR packet")
    if not isinstance(record.get("approvedBy"), str) or not record["approvedBy"].strip():
        errors.append("Wave amendment approval requires a non-empty human approver identity")
    if review.get("result") != "APPROVED" or review.get("candidateCommit") != packet_reference.get("commit"):
        errors.append("Wave amendment approval requires an APPROVED independent review of the exact packet commit")
    if review.get("reviewer") == record.get("approvedBy"):
        errors.append("Wave amendment packet reviewer must be independent from the human approver")
    packet_commit = packet_reference.get("commit")
    if not isinstance(packet_commit, str) or re.fullmatch(r"[0-9a-f]{40}", packet_commit) is None:
        errors.append("Wave amendment approval packet commit must be a full lowercase Git SHA")
    else:
        packet_path = ecr_packet_path(root, str(packet.get("changeRequestId")))
        try:
            packet_payload = packet_path.read_bytes()
        except OSError:
            packet_payload = b""
        if hashlib.sha256(packet_payload).hexdigest() != packet_reference.get("sha256"):
            errors.append("Wave amendment approval packet hash does not match the current packet")
        if not _git_commit_exists(root, packet_commit):
            errors.append("Wave amendment approval packet commit does not exist")
        elif _git_blob(root, packet_commit, packet_relative) != packet_payload:
            errors.append("Wave amendment approval packet differs from its immutable Git blob")
        if packet.get("schemaVersion") in {"2.0-proposal", "3.0-proposal"}:
            frozen = _json_object(packet.get("authorityChain")).get("orderedAmendments") or []
            latest_state = str(_json_object(frozen[-1]).get("effectiveStateCommit") or "") if frozen else ""
            if latest_state and not _git_is_ancestor(root, latest_state, packet_commit):
                errors.append("Wave amendment packet does not descend from the latest predecessor effective state")
        errors.extend(_packet_file_errors(root, packet, packet_commit))
    if require_committed_history:
        introduced = _approval_introduction_commit(root, approval_relative)
        if introduced is None:
            errors.append("Wave amendment approval must have exactly one Git introduction commit")
        else:
            if _git_blob(root, introduced, approval_relative) != payload:
                errors.append("Wave amendment approval was changed after its introduction commit")
            if not _git_is_ancestor(root, introduced):
                errors.append("Wave amendment approval introduction is not on current history")
            if isinstance(packet_commit, str) and not _git_is_ancestor(root, packet_commit, introduced):
                errors.append("Wave amendment approval introduction does not descend from its packet commit")
    return errors


def _authority_history_errors(root: Path, packet: dict[str, Any]) -> list[str]:
    if packet.get("schemaVersion") in {"2.0-proposal", "3.0-proposal"}:
        return _authority_chain_v2_errors(root, packet)
    errors: list[str] = []
    authority = _json_object(packet.get("authority"))
    wave_id = str(packet.get("targetWave"))
    original = _historical_wave_approval(root, str(authority.get("originalApprovalRecordCommit")), wave_id)
    if original is None or original.get("approved_commit") != authority.get("originalWavePacketCommit"):
        errors.append("ECR original Wave authority does not match its historical approval record")
    legacy_id = authority.get("legacyAmendmentId")
    if not isinstance(legacy_id, str) or AMENDMENT_ID_PATTERN.fullmatch(legacy_id) is None:
        errors.append("ECR legacy amendment identity is invalid")
        return errors
    legacy_path = root / "planning" / "wave-amendment-approvals" / f"{legacy_id}.json"
    try:
        legacy, _ = _json_document(legacy_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"ECR legacy amendment record is unavailable: {exc}")
        return errors
    errors.extend(
        _schema_errors(
            legacy,
            root / "planning" / "wave-amendment-approvals" / "wave-amendment-approval.schema.json",
            "Legacy Wave amendment approval",
        )
    )
    migration = _json_object(legacy.get("migration"))
    legacy_packet = _json_object(legacy.get("packet"))
    legacy_base = _json_object(legacy.get("effectiveBase"))
    checks = (
        (legacy.get("amendmentId"), legacy_id, "legacy amendment identity"),
        (legacy.get("targetWave"), wave_id, "legacy target Wave"),
        (legacy_packet.get("commit"), authority.get("legacyAmendmentPacketCommit"), "legacy packet commit"),
        (
            migration.get("historicalRecordCommit"),
            authority.get("legacyAmendmentRecordCommit"),
            "legacy approval record commit",
        ),
        (
            legacy_base.get("originalPacketCommit"),
            authority.get("originalWavePacketCommit"),
            "legacy original packet commit",
        ),
        (
            legacy_base.get("originalApprovalRecordCommit"),
            authority.get("originalApprovalRecordCommit"),
            "legacy original approval record commit",
        ),
    )
    for actual, wanted, label in checks:
        if actual != wanted:
            errors.append(f"ECR {label} does not match the approved authority chain")
    migrated = migration.get("effectiveApproval")
    historical = _historical_wave_approval(root, str(authority.get("legacyAmendmentRecordCommit")), wave_id)
    try:
        backlog, _ = load_backlog(root)
        current_wave = next((item for item in backlog.get("waves", []) if item.get("id") == wave_id), None)
        current = (current_wave or {}).get("approval")
    except OSError, yaml.YAMLError:
        current = None
    if migrated != historical:
        errors.append("ECR migrated legacy approval does not match its historical record")
    if migrated != current:
        errors.append("ECR migrated legacy approval does not reproduce the current Wave authorization")
    ordered_commits = (
        authority.get("originalWavePacketCommit"),
        authority.get("originalApprovalRecordCommit"),
        authority.get("legacyAmendmentPacketCommit"),
        authority.get("legacyAmendmentRecordCommit"),
    )
    for commit in ordered_commits:
        if not isinstance(commit, str) or not _git_commit_exists(root, commit) or not _git_is_ancestor(root, commit):
            errors.append(f"ECR authority commit is missing or not on current history: {commit}")
    for ancestor, descendant in pairwise(ordered_commits):
        if (
            isinstance(ancestor, str)
            and isinstance(descendant, str)
            and not _git_is_ancestor(root, ancestor, descendant)
        ):
            errors.append(f"ECR authority chain is forked: {ancestor} is not an ancestor of {descendant}")
    return errors


def _authority_chain_v2_errors(root: Path, packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    chain = _json_object(packet.get("authorityChain"))
    wave_base = _json_object(chain.get("waveBase"))
    wave_id = str(packet.get("targetWave") or "")
    try:
        backlog, _ = load_backlog(root)
    except (OSError, yaml.YAMLError) as exc:
        return [f"ECR authority backlog is unavailable: {exc}"]
    bases = {str(item.get("wave_id")): item for item in backlog.get("wave_approval_bases", [])}
    base = _json_object(bases.get(wave_id))
    if (
        wave_base.get("waveId") != wave_id
        or wave_base.get("packetCommit") != base.get("packet_commit")
        or wave_base.get("approvalRecordCommit") != base.get("record_commit")
    ):
        errors.append("ECR v2 Wave base differs from the immutable backlog authority")
    actual = [item for item in backlog.get("wave_amendments", []) if item.get("target_wave") == wave_id]
    frozen = chain.get("orderedAmendments")
    if not isinstance(frozen, list):
        return [*errors, "ECR v2 ordered amendment authority is missing"]
    expected_ids = [f"{wave_id}.A{index:02d}" for index in range(1, len(frozen) + 1)]
    frozen_ids = [str(_json_object(item).get("id")) for item in frozen]
    if frozen_ids != expected_ids or len(frozen_ids) != len(set(frozen_ids)):
        errors.append("ECR v2 predecessor chain is gapped, reordered, duplicated, or forked")
    proposed = str(packet.get("proposedAmendmentId") or "")
    if len(actual) not in {len(frozen), len(frozen) + 1} or (
        len(actual) == len(frozen) + 1 and actual[-1].get("id") != proposed
    ):
        errors.append("ECR v2 packet does not freeze the complete predecessor chain or its one appended proposal")
    ordered_commits: list[str] = [
        str(wave_base.get("packetCommit") or ""),
        str(wave_base.get("approvalRecordCommit") or ""),
    ]
    ancestry_pairs: list[tuple[str, str]] = [(ordered_commits[0], ordered_commits[1])]
    for packet_item, backlog_item in zip(frozen, actual, strict=False):
        item = _json_object(packet_item)
        reference = _json_object(item.get("approvalReference"))
        backlog_reference = _json_object(backlog_item.get("approval_reference"))
        expected = (
            (item.get("id"), backlog_item.get("id"), "identity"),
            (item.get("changeRequestId"), backlog_item.get("change_request_id"), "change request"),
            (item.get("status"), (backlog_item.get("lifecycle") or {}).get("status"), "status"),
            (reference.get("path"), backlog_reference.get("path"), "approval path"),
            (reference.get("sha256"), backlog_reference.get("sha256"), "approval hash"),
            (
                reference.get("introductionCommit"),
                backlog_reference.get("introduction_commit"),
                "approval introduction",
            ),
        )
        for current, wanted, label in expected:
            if current != wanted:
                errors.append(f"ECR v2 {item.get('id')} {label} differs from predecessor authority")
        approval_path = root.joinpath(*PurePosixPath(str(reference.get("path") or "")).parts)
        try:
            approval_payload = approval_path.read_bytes()
            approval_record = json.loads(approval_payload)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"ECR v2 {item.get('id')} approval record is unavailable: {exc}")
            approval_record = {}
            approval_payload = b""
        if approval_payload and hashlib.sha256(approval_payload).hexdigest() != reference.get("sha256"):
            errors.append(f"ECR v2 {item.get('id')} approval hash mismatch")
        if approval_record.get("amendmentId") != item.get("id"):
            errors.append(f"ECR v2 {item.get('id')} approval identity mismatch")
        packet_commit = str(item.get("packetCommit") or "")
        approval_commit = str(reference.get("introductionCommit") or "")
        state_commit = str(item.get("effectiveStateCommit") or "")
        ordered_commits.extend((packet_commit, approval_commit, state_commit))
        ancestry_pairs.extend(((packet_commit, approval_commit), (approval_commit, state_commit)))
        historical = (
            _git_blob(root, state_commit, "planning/backlog.yaml") if _git_commit_exists(root, state_commit) else None
        )
        if historical is None:
            errors.append(f"ECR v2 {item.get('id')} effective-state commit is unavailable")
        else:
            try:
                state = yaml.safe_load(historical.decode("utf-8"))
                historical_item = next(
                    candidate for candidate in state.get("wave_amendments", []) if candidate.get("id") == item.get("id")
                )
            except UnicodeError, yaml.YAMLError, StopIteration, AttributeError:
                historical_item = None
            if (historical_item or {}).get("lifecycle", {}).get("status") != "ADOPTED":
                errors.append(f"ECR v2 {item.get('id')} effective state is not ADOPTED")
    if proposed != f"{wave_id}.A{len(frozen) + 1:02d}":
        errors.append("ECR v2 proposed amendment is not the next consecutive authority identity")
    existing_ecr_numbers = [
        int(str(_json_object(item).get("changeRequestId")).removeprefix("ECR-"))
        for item in frozen
        if re.fullmatch(r"ECR-[0-9]{4}", str(_json_object(item).get("changeRequestId") or ""))
    ]
    next_ecr = max(existing_ecr_numbers, default=0) + 1
    if packet.get("changeRequestId") != f"ECR-{next_ecr:04d}":
        errors.append("ECR v2 change-request identity is not consecutive")
    authorized = [str(item) for item in packet.get("authorizedTaskIds", [])]
    inventory = [str(_json_object(item).get("id")) for item in packet.get("taskInventory", [])]
    expected_tasks = [f"{proposed}.T{index:02d}" for index in range(1, len(inventory) + 1)]
    if authorized != inventory or inventory != expected_tasks:
        errors.append("ECR v2 task authority/inventory is not exact, ordered, and amendment-bound")
    bootstrap_id = str(_json_object(packet.get("bootstrapUnit")).get("id") or "")
    if bootstrap_id != f"{proposed}.B00":
        errors.append("ECR v2 bootstrap identity is outside the proposed amendment namespace")
    for task in packet.get("taskInventory", []):
        dependencies = _json_object(task).get("dependencies") or []
        if bootstrap_id not in dependencies:
            errors.append(f"ECR v2 task {_json_object(task).get('id')} does not depend on the approved bootstrap")
    hold_id = str(_json_object(packet.get("activationBoundary")).get("recoveryHoldId") or "")
    holds = (backlog.get("control_plane") or {}).get("recovery_holds", [])
    matching_hold = next((hold for hold in holds if hold.get("id") == hold_id), None)
    proposed_is_adopted = bool(
        len(actual) == len(frozen) + 1 and (actual[-1].get("lifecycle") or {}).get("status") == "ADOPTED"
    )
    if (
        matching_hold is None
        or matching_hold.get("target_wave") != wave_id
        or (
            matching_hold.get("status") != "ACTIVE"
            and not (matching_hold.get("status") == "RELEASED" and proposed_is_adopted)
        )
        or (matching_hold.get("bootstrap") or {}).get("status") != "APPROVED"
        or (matching_hold.get("post_bootstrap") or {}).get("required_amendment_id") != proposed
        or (matching_hold.get("post_bootstrap") or {}).get("required_change_request_id")
        != packet.get("changeRequestId")
        or (matching_hold.get("post_bootstrap") or {}).get("required_proposed_task_ids") != authorized
    ):
        errors.append("ECR v2 does not bind the active independently approved recovery hold")
    if packet.get("schemaVersion") == "3.0-proposal":
        recovery = _json_object(packet.get("recoveryAuthority"))
        packet_reference = _json_object(recovery.get("packetReference"))
        approval_reference = _json_object(recovery.get("approvalReference"))
        bootstrap_reference = _json_object(recovery.get("bootstrap"))
        hold_bootstrap = _json_object((matching_hold or {}).get("bootstrap"))
        attempts = hold_bootstrap.get("attempts") or []
        latest_attempt = _json_object(attempts[-1]) if attempts else {}
        ledger_reference = _json_object(latest_attempt.get("ledger"))
        ledger_path = root.joinpath(*PurePosixPath(str(ledger_reference.get("path") or "")).parts)
        try:
            ledger_payload = ledger_path.read_bytes()
            ledger = json.loads(ledger_payload)
        except OSError, UnicodeError, json.JSONDecodeError:
            ledger_payload = b""
            ledger = {}
        expected_recovery = (
            (recovery.get("recoveryRequestId"), (matching_hold or {}).get("recovery_request_id")),
            (recovery.get("holdId"), hold_id),
            (recovery.get("holdStatus"), "ACTIVE"),
            (packet_reference, _json_object((matching_hold or {}).get("packet_reference"))),
            (approval_reference, _json_object((matching_hold or {}).get("approval_reference"))),
            (bootstrap_reference.get("id"), hold_bootstrap.get("id")),
            (bootstrap_reference.get("status"), "APPROVED"),
            (bootstrap_reference.get("attemptId"), latest_attempt.get("id")),
            (bootstrap_reference.get("candidateCommit"), latest_attempt.get("implementation_commit")),
            (bootstrap_reference.get("reviewedStateCommit"), ledger.get("reviewedStateCommit")),
            (bootstrap_reference.get("reviewLedger"), ledger_reference),
        )
        if any(current != wanted for current, wanted in expected_recovery):
            errors.append("ECR v3 recovery authority differs from the exact active hold and approved bootstrap")
        if (
            not ledger_payload
            or hashlib.sha256(ledger_payload).hexdigest() != ledger_reference.get("sha256")
            or ledger.get("result") != "approved"
            or ledger.get("candidateCommit") != latest_attempt.get("implementation_commit")
            or (latest_attempt.get("review") or {}).get("result") != "approved"
        ):
            errors.append("ECR v3 recovery bootstrap review is not exact, immutable, and APPROVED")
        active_holds = [hold for hold in holds if hold.get("status") == "ACTIVE"]
        if not proposed_is_adopted and active_holds != [matching_hold]:
            errors.append("ECR v3 requires its recovery hold to be the sole ACTIVE hold before adoption")
    for commit in ordered_commits:
        if (
            not re.fullmatch(r"[0-9a-f]{40}", commit)
            or not _git_commit_exists(root, commit)
            or not _git_is_ancestor(root, commit)
        ):
            errors.append(f"ECR v2 authority commit is missing or not on current history: {commit}")
    for ancestor, descendant in ancestry_pairs:
        if (
            _git_commit_exists(root, ancestor)
            and _git_commit_exists(root, descendant)
            and not _git_is_ancestor(root, ancestor, descendant)
        ):
            errors.append(f"ECR v2 authority chain is forked: {ancestor} is not an ancestor of {descendant}")
    return errors


def ecr_validation_errors(root: Path, change_request_id: str, *, require_approved: bool) -> list[str]:
    packet_path = ecr_packet_path(root, change_request_id)
    try:
        packet, packet_payload = _json_document(packet_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"ECR packet is unavailable or invalid: {exc}"]
    schema_name = {
        "1.0-proposal": "enabler-change-request.schema.json",
        "2.0-proposal": "enabler-change-request.v2.schema.json",
        "3.0-proposal": "enabler-change-request.v3.schema.json",
    }.get(str(packet.get("schemaVersion")))
    if schema_name is None:
        errors = [f"ECR packet uses an unsupported schema version: {packet.get('schemaVersion')}"]
    else:
        errors = _schema_errors(
            packet,
            root / "planning" / "enabler-change-requests" / schema_name,
            "ECR packet",
        )
    if packet.get("changeRequestId") != change_request_id:
        errors.append("ECR packet identity does not match the requested change request")
    errors.extend(_packet_file_errors(root, packet))
    errors.extend(_authority_history_errors(root, packet))
    amendment_id = packet.get("proposedAmendmentId")
    approval_relative = f"planning/wave-amendment-approvals/{amendment_id}.json"
    approval_path = root.joinpath(*PurePosixPath(approval_relative).parts)
    if not approval_path.exists():
        if require_approved:
            errors.append(f"ECR has no immutable approval record: {approval_relative}")
        return errors
    try:
        record, approval_payload = _json_document(approval_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Wave amendment approval is unavailable or invalid: {exc}")
        return errors
    errors.extend(
        _approval_record_errors(
            root,
            packet,
            record,
            approval_payload,
            approval_relative=approval_relative,
            require_committed_history=require_approved,
        )
    )
    if require_approved:
        packet_reference = _json_object(record.get("packet"))
        if hashlib.sha256(packet_payload).hexdigest() != packet_reference.get("sha256"):
            errors.append("Approved ECR packet SHA-256 does not match the current packet")
    return errors


def validate_ecr(root: Path, change_request_id: str, *, require_approved: bool) -> int:
    errors = ecr_validation_errors(root, change_request_id, require_approved=require_approved)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if not errors:
        state = "approved and history-bound" if require_approved else "structurally and historically valid"
        print(f"{change_request_id} is {state}.")
    return 1 if errors else 0


def approve_ecr(
    root: Path,
    change_request_id: str,
    *,
    record_path: Path,
    approver: str,
    commit: str,
) -> Path:
    packet_path = ecr_packet_path(root, change_request_id)
    packet, _ = _json_document(packet_path)
    amendment_id = packet.get("proposedAmendmentId")
    if not isinstance(amendment_id, str) or AMENDMENT_ID_PATTERN.fullmatch(amendment_id) is None:
        raise ValueError("ECR packet has an invalid proposed amendment identity")
    destination = root / "planning" / "wave-amendment-approvals" / f"{amendment_id}.json"
    if destination.exists():
        raise ValueError(f"{amendment_id} already has an immutable approval record; duplicate approval is forbidden")
    if not approver.strip():
        raise ValueError("ECR approval requires a non-empty human approver identity")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("ECR approval commit must be a full lowercase Git SHA")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    ).stdout.strip()
    if head != commit:
        raise ValueError("ECR approval commit must equal the current immutable Git HEAD")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False)
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError("ECR approval requires a clean worktree so the reviewed packet is exactly commit-bound")
    preliminary = ecr_validation_errors(root, change_request_id, require_approved=False)
    if preliminary:
        raise ValueError("ECR packet validation failed: " + "; ".join(preliminary))
    record, payload = _json_document(record_path)
    if record.get("approvedBy") != approver:
        raise ValueError("Approval record approvedBy must equal --by")
    if (record.get("packet") or {}).get("commit") != commit:
        raise ValueError("Approval record packet commit must equal --commit")
    relative = destination.relative_to(root).as_posix()
    record_errors = _approval_record_errors(
        root,
        packet,
        record,
        payload,
        approval_relative=relative,
        require_committed_history=False,
    )
    if record_errors:
        raise ValueError("ECR approval record validation failed: " + "; ".join(record_errors))
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise ValueError(f"{amendment_id} approval appeared concurrently; no file was overwritten") from exc
    return destination


def approve_wave(root: Path, wave_id: str, approver: str, commit: str, note: str = "") -> int:
    data, _ = load_backlog(root)
    wave = next((item for item in data.get("waves", []) if item.get("id") == wave_id), None)
    if wave is None:
        raise ValueError(f"Unknown Wave {wave_id}")
    approval = wave.get("approval") or {}
    if approval.get("status") == "APPROVED":
        raise ValueError(
            f"{wave_id} is already approved at {approval.get('approved_commit')}; "
            "use the append-only ECR/Wave-amendment workflow"
        )
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Wave approval commit must be a full lowercase Git SHA")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    ).stdout.strip()
    if head != commit:
        raise ValueError("Wave approval commit must equal the current immutable Git HEAD")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False)
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError("Wave approval requires a clean worktree so the reviewed packet is exactly commit-bound")

    contributing = wave_capabilities(data, wave_id)
    capability_ids = [str(capability["id"]) for capability in contributing]
    decision_ids: list[str] = []
    slice_ids = [
        str(slice_["id"])
        for capability in contributing
        for slice_ in capability.get("slices", [])
        if slice_.get("wave") == wave_id
    ]
    paths: list[Path] = []
    for capability in contributing:
        capability_id = str(capability["id"])
        cap_path = capability_plan_path(root, capability_id)
        if capability_id != "CAP-00":
            if not cap_path.exists():
                raise ValueError(f"Missing capability plan for {capability_id}")
            paths.append(cap_path)
            cap_meta, _ = frontmatter(cap_path)
            unclassified = [item.get("id") for item in cap_meta.get("decisions", []) if not item.get("binding_waves")]
            if unclassified:
                raise ValueError(f"{capability_id}: decisions lack explicit Wave classification: {unclassified}")
            binding_ids = [
                str(item["id"])
                for item in cap_meta.get("decisions", [])
                if wave_id in (item.get("binding_waves") or [])
            ]
            if not binding_ids:
                raise ValueError(f"{capability_id}: no decisions are binding in {wave_id}")
            decision_ids.extend(binding_ids)
        selected = []
        for path in slice_plan_paths(root, capability_id):
            meta, _ = frontmatter(path)
            if meta.get("wave") == wave_id:
                selected.append(path)
        if capability_id != "CAP-00" and len(selected) != len(
            [slice_ for slice_ in capability.get("slices", []) if slice_.get("wave") == wave_id]
        ):
            raise ValueError(f"{capability_id}/{wave_id}: missing canonical slice plans")
        paths.extend(selected)

    backlog_path = root / "planning" / "backlog.yaml"
    originals = {path: path.read_text(encoding="utf-8") for path in [backlog_path, *paths]}
    try:
        approved_at = datetime.now(UTC).isoformat()
        for capability in contributing:
            capability_id = str(capability["id"])
            if capability_id == "CAP-00":
                continue
            cap_path = capability_plan_path(root, capability_id)
            meta, _ = frontmatter(cap_path)
            unresolved = [
                item.get("id")
                for item in meta.get("decisions", [])
                if item.get("status") != "accepted" or not item.get("selected_option")
            ]
            if meta.get("open_blocking_decisions") or unresolved or meta.get("decision_completion") != "complete":
                raise ValueError(f"{capability_id}: capability decisions are incomplete: {unresolved}")
            for path in slice_plan_paths(root, capability_id):
                slice_meta, slice_body = frontmatter(path)
                if slice_meta.get("wave") != wave_id:
                    continue
                slice_meta["status"] = "approved"
                slice_meta["approval"] = {
                    "status": "approved",
                    "approved_by": approver,
                    "approved_at": approved_at,
                    "approved_commit": commit,
                }
                write_plan(path, slice_meta, slice_body)

        wave["approval"] = {
            "status": "APPROVED",
            "approved_by": approver,
            "approved_at": approved_at,
            "approved_commit": commit,
            "capability_ids": capability_ids,
            "decision_ids": decision_ids,
            "slice_ids": slice_ids,
            "notes": note or None,
        }
        backlog_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
        subprocess.run([sys.executable, str(root / "tools/backlog_views.py"), "--repo", str(root)], check=True)
        generate_review(root)
        if validate_wave(root, wave_id, True):
            raise ValueError("Wave approval validation failed; all source changes were rolled back")
    except Exception:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")
        subprocess.run([sys.executable, str(root / "tools/backlog_views.py"), "--repo", str(root)], check=False)
        generate_review(root)
        raise
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    wave_parser = sub.add_parser("wave")
    wave_sub = wave_parser.add_subparsers(dest="wave_command", required=True)
    for name in ("prepare", "review", "validate", "ready"):
        command = wave_sub.add_parser(name)
        command.add_argument("wave")
        if name in {"validate", "ready"}:
            command.add_argument("--require-approved", action="store_true")
    wave_approve = wave_sub.add_parser("approve")
    wave_approve.add_argument("wave")
    wave_approve.add_argument("--by", required=True)
    wave_approve.add_argument("--commit", required=True)
    wave_approve.add_argument("--note", default="")

    ecr_parser = sub.add_parser("ecr")
    ecr_sub = ecr_parser.add_subparsers(dest="ecr_command", required=True)
    for name in ("review", "validate"):
        command = ecr_sub.add_parser(name)
        command.add_argument("change_request")
        if name == "validate":
            command.add_argument("--require-approved", action="store_true")
    ecr_approve = ecr_sub.add_parser("approve")
    ecr_approve.add_argument("change_request")
    ecr_approve.add_argument("--record", required=True)
    ecr_approve.add_argument("--by", required=True)
    ecr_approve.add_argument("--commit", required=True)

    for name in ("prepare", "validate", "ready", "decisions", "review", "adopt-recommendations"):
        command = sub.add_parser(name)
        command.add_argument("capability")
        if name in ("validate", "ready", "review"):
            command.add_argument("--wave")
        if name in ("validate", "ready"):
            command.add_argument("--require-approved", action="store_true")

    apply_parser = sub.add_parser("apply-feedback")
    apply_parser.add_argument("capability")
    apply_parser.add_argument("feedback")

    approve_parser = sub.add_parser("approve")
    approve_parser.add_argument("capability")
    approve_parser.add_argument("--feedback")
    approve_parser.add_argument("--wave", required=True)
    approve_parser.add_argument("--by", required=True)
    approve_parser.add_argument("--commit", required=True)

    args = parser.parse_args()
    root = Path(args.repo).resolve()
    data, caps = load_backlog(root)

    if args.command == "wave":
        wave_ids = {str(item.get("id")) for item in data.get("waves", [])}
        if args.wave not in wave_ids:
            print(f"Unknown Wave {args.wave}", file=sys.stderr)
            return 2
        try:
            if args.wave_command == "prepare":
                wave_created = prepare_wave(root, args.wave)
                for path in wave_created:
                    print("Created", path.relative_to(root))
                if not wave_created:
                    print(f"All planning artifacts already exist for {args.wave}.")
                print_wave_review_link(root, args.wave)
                return 0
            if args.wave_command == "review":
                result = generate_review(root)
                print_wave_review_link(root, args.wave)
                return result
            if args.wave_command == "approve":
                result = approve_wave(root, args.wave, args.by, args.commit, args.note)
                print(
                    f"Approved the complete {args.wave} packet—every {args.wave}-binding capability decision and "
                    f"Wave slice plan—at immutable commit {args.commit}."
                )
                print_wave_review_link(root, args.wave)
                return result
            generate_review(root)
            require_approved = True if args.wave_command == "ready" else args.require_approved
            result = validate_wave(root, args.wave, require_approved)
            if result and args.wave_command == "ready":
                print(
                    "Wave is not ready. Classify every contributing capability decision, resolve the decisions "
                    "binding in this Wave, approve every Wave slice plan, and record one commit-bound pre-Wave "
                    "approval using the linked page.",
                    file=sys.stderr,
                )
            print_wave_review_link(root, args.wave)
            return result
        except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, subprocess.CalledProcessError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            generate_review(root)
            print_wave_review_link(root, args.wave)
            return 1

    if args.command == "ecr":
        try:
            if args.ecr_command == "review":
                result = validate_ecr(root, args.change_request, require_approved=False)
                print_ecr_review_links(root, args.change_request)
                return result
            if args.ecr_command == "validate":
                result = validate_ecr(
                    root,
                    args.change_request,
                    require_approved=args.require_approved,
                )
                print_ecr_review_links(root, args.change_request)
                return result
            destination = approve_ecr(
                root,
                args.change_request,
                record_path=Path(args.record).resolve(),
                approver=args.by,
                commit=args.commit,
            )
            print(f"Appended immutable approval record: {destination.relative_to(root).as_posix()}")
            print(
                "Commit this new record; approval history validation remains pending until that introduction commit exists."
            )
            print_ecr_review_links(root, args.change_request)
            return 0
        except (OSError, ValueError, json.JSONDecodeError, SchemaError, yaml.YAMLError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            print_ecr_review_links(root, args.change_request)
            return 1

    requested_capability = args.capability
    capability = requested_capability
    if capability not in caps:
        matches = [cid for cid, candidate in caps.items() if candidate.get("alias") == requested_capability]
        if len(matches) != 1:
            print(f"Unknown capability {requested_capability}", file=sys.stderr)
            return 2
        capability = matches[0]
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
            print(
                "Generated placeholders remain proposed until researched. After authoring decisions, use `planctl wave review WN`; approve the complete Wave packet before its campaign starts."
            )
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
            print("The capability and slice plans remain unapproved until the complete Wave approval command is run.")
            print(
                "If feedback used Other, the brief description is now a canonical candidate; detailed rationale remains in the archived feedback record."
            )
            print_review_link(root, capability)
            return 0

        if args.command == "approve":
            feedback = Path(args.feedback).resolve() if args.feedback else None
            result = approve(root, capability, feedback, args.by, args.commit, args.wave)
            print(f"Approved {capability}'s decision packet and {args.wave} slice plans at commit {args.commit}.")
            print_review_link(root, capability)
            return result

        generate_review(root, capability)
        if args.command == "validate":
            result = validate(root, capability, args.require_approved, args.wave)
            print_review_link(root, capability)
            return result
        if args.command == "ready":
            result = validate(root, capability, True, args.wave)
            if result:
                print(
                    "Legacy capability-scoped readiness is not satisfied. Use the complete Wave approval workflow for new execution.",
                    file=sys.stderr,
                )
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
