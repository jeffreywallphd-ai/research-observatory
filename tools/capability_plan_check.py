#!/usr/bin/env python3
"""Validate capability decision plans and wave-scoped slice approval gates."""

from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
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
INITIATION_POLICY = "initiation-assessment-1.0"
FIFTEEN_PERCENT = Decimal("0.15")


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


def wave_number(wave_id: str) -> int | None:
    match = re.fullmatch(r"W([0-9]|1[01])", wave_id)
    return int(match.group(1)) if match else None


def wave_requires_initiation_assessment(wave_id: str) -> bool:
    number = wave_number(wave_id)
    return number is not None and number >= 2


def _effort(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite() or number <= 0:
        return None
    return number


def _required_text(record: dict[str, Any], field: str, label: str, errors: list[str]) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: {field} is required")
        return ""
    return value.strip()


def _planned_items(
    value: Any, *, work_waves: dict[str, str], label: str, errors: list[str]
) -> tuple[dict[str, Decimal], Decimal]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: planned_items must be a non-empty list")
        return {}, Decimal(0)
    items: dict[str, Decimal] = {}
    for index, item in enumerate(value):
        item_label = f"{label}.planned_items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label}: expected an object")
            continue
        work_id = item.get("work_id")
        effort = _effort(item.get("effort"))
        if not isinstance(work_id, str) or work_id not in work_waves:
            errors.append(f"{item_label}: work_id must name an atomic task in this capability")
            continue
        if work_id in items:
            errors.append(f"{item_label}: duplicate work_id {work_id}")
        if effort is None:
            errors.append(f"{item_label}: effort must be a positive finite number")
            continue
        items[work_id] = effort
    return items, sum(items.values(), Decimal(0))


def initiation_assessment_errors(
    meta: dict[str, Any],
    body: str,
    capability: dict[str, Any],
    wave_id: str,
) -> list[str]:
    """Validate only the objective bounds of the prospective planning assessment."""

    if not wave_requires_initiation_assessment(wave_id):
        return []
    capability_id = str(capability.get("id"))
    errors: list[str] = []
    if meta.get("planning_policy_version") != INITIATION_POLICY:
        errors.append(f"{capability_id}: planning_policy_version must be {INITIATION_POLICY}")
    if "## 0A. Initiation assessment and planning adaptation" not in body:
        errors.append(f"{capability_id}: missing heading ## 0A. Initiation assessment and planning adaptation")
    assessment = meta.get("initiation_assessment")
    if not isinstance(assessment, dict):
        errors.append(f"{capability_id}: initiation_assessment must be completed for {wave_id}")
        return errors
    if assessment.get("policy_version") != "1.0":
        errors.append(f"{capability_id}: initiation_assessment.policy_version must be 1.0")
    assessment_label = f"{capability_id}.initiation_assessment"
    _required_text(assessment, "assessed_at", assessment_label, errors)
    _required_text(assessment, "estimation_unit", assessment_label, errors)
    _required_text(assessment, "implementation_baseline", assessment_label, errors)
    _required_text(assessment, "vision_architecture_best_practice_fit", assessment_label, errors)

    work_waves = {
        str(task.get("id")): str(slice_.get("wave"))
        for slice_ in capability.get("slices", [])
        for task in slice_.get("tasks", [])
        if task.get("id")
    }
    baseline_items, baseline_effort = _planned_items(
        assessment.get("planned_items"),
        work_waves=work_waves,
        label=f"{capability_id}.initiation_assessment",
        errors=errors,
    )

    refactoring_value = assessment.get("refactoring_items")
    if not isinstance(refactoring_value, list):
        errors.append(f"{capability_id}: refactoring_items must be a list")
        refactoring_value = []
    refactoring: dict[str, dict[str, Any]] = {}
    included_effort = Decimal(0)
    capability_waves = {str(slice_.get("wave")) for slice_ in capability.get("slices", [])}
    for index, item in enumerate(refactoring_value):
        label = f"{capability_id}.initiation_assessment.refactoring_items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: expected an object")
            continue
        allocation_id = item.get("id")
        work_id = item.get("work_id")
        effort = _effort(item.get("effort"))
        introduced_wave = item.get("introduced_in_wave")
        disposition = item.get("disposition")
        if not isinstance(allocation_id, str) or not allocation_id.strip():
            errors.append(f"{label}: id is required")
            continue
        if allocation_id in refactoring:
            errors.append(f"{label}: duplicate allocation id {allocation_id}")
        if not isinstance(work_id, str) or work_id not in work_waves:
            errors.append(f"{label}: work_id must name an atomic task in this capability")
        if effort is None:
            errors.append(f"{label}: effort must be a positive finite number")
        if introduced_wave not in capability_waves:
            errors.append(f"{label}: introduced_in_wave must be a capability Wave")
        if (
            disposition == "included"
            and isinstance(work_id, str)
            and work_id in work_waves
            and introduced_wave != work_waves[work_id]
        ):
            errors.append(f"{label}: included refactoring must be charged to the Wave containing work_id")
        if item.get("changes_existing_implementation") is not True:
            errors.append(f"{label}: changes_existing_implementation must be true")
        if not isinstance(item.get("major_refactor"), bool):
            errors.append(f"{label}: major_refactor must be boolean")
        if disposition not in {"included", "future-enabler", "roadmap-architecture-decision"}:
            errors.append(f"{label}: disposition is invalid")
        if item.get("major_refactor") is True and disposition == "included":
            errors.append(f"{label}: a major refactor cannot be included in initiation planning")
        _required_text(item, "description", label, errors)
        refactoring[allocation_id] = item
        if disposition == "included" and effort is not None:
            included_effort += effort

    if included_effort > FIFTEEN_PERCENT * baseline_effort:
        errors.append(
            f"{capability_id}: capability refactoring budget exceeds 15% ({included_effort} > 0.15 * {baseline_effort})"
        )
    major_disposition = _required_text(
        assessment, "major_refactor_disposition", f"{capability_id}.initiation_assessment", errors
    )
    if any(
        item.get("major_refactor") is True for item in refactoring.values()
    ) and major_disposition.lower().startswith("none"):
        errors.append(f"{capability_id}: major_refactor_disposition must identify routed major work")

    refreshes = assessment.get("wave_refreshes")
    if not isinstance(refreshes, list):
        errors.append(f"{capability_id}: wave_refreshes must be a list")
        return errors
    refresh_by_wave: dict[str, dict[str, Any]] = {}
    refresh_numbers: list[int] = []
    for index, refresh in enumerate(refreshes):
        label = f"{capability_id}.initiation_assessment.wave_refreshes[{index}]"
        if not isinstance(refresh, dict):
            errors.append(f"{label}: expected an object")
            continue
        refresh_wave = refresh.get("wave")
        number = wave_number(str(refresh_wave))
        if refresh_wave not in capability_waves or number is None:
            errors.append(f"{label}: wave must be a capability Wave")
            continue
        if refresh_wave in refresh_by_wave:
            errors.append(f"{label}: duplicate Wave refresh {refresh_wave}")
        refresh_by_wave[str(refresh_wave)] = refresh
        refresh_numbers.append(number)
        _required_text(refresh, "assessed_at", label, errors)
        _required_text(refresh, "material_changes", label, errors)
        _required_text(refresh, "plan_adaptations", label, errors)
        _required_text(refresh, "support_improvements", label, errors)
        _required_text(refresh, "major_refactor_disposition", label, errors)
    if refresh_numbers != sorted(refresh_numbers):
        errors.append(f"{capability_id}: wave_refreshes must be in Wave order")
    if wave_id not in refresh_by_wave:
        errors.append(f"{capability_id}: missing initiation assessment refresh for {wave_id}")

    wave_effort = sum(
        (effort for work_id, effort in baseline_items.items() if work_waves.get(work_id) == wave_id),
        Decimal(0),
    )
    wave_refactoring_effort = sum(
        (
            _effort(item.get("effort")) or Decimal(0)
            for item in refactoring.values()
            if item.get("introduced_in_wave") == wave_id and item.get("disposition") == "included"
        ),
        Decimal(0),
    )
    if not wave_effort:
        errors.append(f"{capability_id}: {wave_id} assessment has no itemized pre-assessment planned effort")
    elif wave_refactoring_effort > FIFTEEN_PERCENT * wave_effort:
        errors.append(
            f"{capability_id}: {wave_id} refactoring budget exceeds 15% "
            f"({wave_refactoring_effort:g} > 0.15 * {wave_effort:g})"
        )
    return errors


def wave_initiation_rollup_errors(entries: list[tuple[str, dict[str, Any], dict[str, Any]]], wave_id: str) -> list[str]:
    """Recompute the deduplicated cross-capability Wave refactoring budget."""

    if not wave_requires_initiation_assessment(wave_id):
        return []
    errors: list[str] = []
    planned_ids: set[str] = set()
    allocation_ids: set[str] = set()
    planned_effort = Decimal(0)
    refactoring_effort = Decimal(0)
    for _capability_id, meta, capability in entries:
        assessment = meta.get("initiation_assessment")
        if not isinstance(assessment, dict):
            continue
        wave_work_ids = {
            str(task.get("id"))
            for slice_ in capability.get("slices", [])
            if slice_.get("wave") == wave_id
            for task in slice_.get("tasks", [])
            if task.get("id")
        }
        for item in assessment.get("planned_items", []):
            if not isinstance(item, dict) or not isinstance(item.get("work_id"), str):
                continue
            work_id = str(item["work_id"])
            if work_id not in wave_work_ids:
                continue
            if work_id in planned_ids:
                errors.append(f"{wave_id}: planned work {work_id} is counted by more than one capability")
                continue
            planned_ids.add(work_id)
            planned_effort += _effort(item.get("effort")) or Decimal(0)
        for item in assessment.get("refactoring_items", []):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            allocation_id = str(item["id"])
            if item.get("introduced_in_wave") != wave_id or item.get("disposition") != "included":
                continue
            if allocation_id in allocation_ids:
                errors.append(f"{wave_id}: refactoring allocation {allocation_id} is counted more than once")
                continue
            allocation_ids.add(allocation_id)
            refactoring_effort += _effort(item.get("effort")) or Decimal(0)
    if not planned_effort:
        errors.append(f"{wave_id}: initiation assessment Wave roll-up has no planned effort")
    elif refactoring_effort > FIFTEEN_PERCENT * planned_effort:
        errors.append(
            f"{wave_id}: deduplicated Wave refactoring budget exceeds 15% "
            f"({refactoring_effort:g} > 0.15 * {planned_effort:g})"
        )
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--capability", action="append", help="Validate only the named capability; repeatable")
    ap.add_argument("--wave", help="Require slice-plan approval only for this wave")
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
            binding_waves = d.get("binding_waves")
            if recommendation not in candidates:
                errors.append(f"{cid}: {d.get('id')} recommendation must be one of candidates")
            if selected_option is not None and selected_option not in candidates:
                errors.append(f"{cid}: {d.get('id')} selected_option must be one of candidates")
            if binding_waves:
                capability_waves = {str(slice_.get("wave")) for slice_ in cap.get("slices", [])}
                invalid_waves = sorted(set(binding_waves) - capability_waves)
                if invalid_waves:
                    errors.append(
                        f"{cid}: {d.get('id')} binding_waves are outside the capability slice map: {invalid_waves}"
                    )

        if ns.wave:
            unclassified = [d.get("id") for d in decisions if not d.get("binding_waves")]
            if unclassified:
                errors.append(f"{cid}: decisions lack explicit Wave classification: {unclassified}")
            binding_ids = [d.get("id") for d in decisions if ns.wave in (d.get("binding_waves") or [])]
            if not binding_ids:
                errors.append(f"{cid}: no decisions are binding in requested wave {ns.wave}")
            errors.extend(initiation_assessment_errors(meta, body, cap, ns.wave))

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
            if meta.get("decision_completion") != "complete":
                errors.append(f"{cid}: decision_completion must be complete")
            if meta.get("open_blocking_decisions"):
                errors.append(f"{cid}: open_blocking_decisions must be empty")
            if ns.wave:
                wave: dict[str, Any] = next(
                    (item for item in backlog.get("waves", []) if item.get("id") == ns.wave), {}
                )
                wave_approval = wave.get("approval") or {}
                expected_ids = [d.get("id") for d in decisions if ns.wave in (d.get("binding_waves") or [])]
                approved_ids = set(wave_approval.get("decision_ids") or [])
                if wave_approval.get("status") != "APPROVED":
                    errors.append(f"{cid}: {ns.wave} pre-Wave approval is not APPROVED")
                missing_ids = [decision_id for decision_id in expected_ids if decision_id not in approved_ids]
                if missing_ids:
                    errors.append(f"{cid}: {ns.wave} approval omits binding decisions {missing_ids}")
                decisions_to_confirm = [d for d in decisions if d.get("id") in expected_ids]
            else:
                if meta.get("status") != "approved":
                    errors.append(f"{cid}: status must be approved")
                if approval.get("status") != "approved":
                    errors.append(f"{cid}: approval.status must be approved")
                for key in ("approved_by", "approved_at", "approved_commit"):
                    if not approval.get(key):
                        errors.append(f"{cid}: approval.{key} is required")
                decisions_to_confirm = decisions
            for d in decisions_to_confirm:
                if d.get("status") != "accepted":
                    errors.append(f"{cid}: decision {d.get('id')} must be accepted")
                if not d.get("selected_option"):
                    errors.append(f"{cid}: decision {d.get('id')} requires selected_option")
            approved_slice_ids = [
                slice_["id"] for slice_ in cap.get("slices", []) if ns.wave is None or slice_.get("wave") == ns.wave
            ]
            if ns.wave and not approved_slice_ids:
                errors.append(f"{cid}: no slices exist in requested wave {ns.wave}")
            for sid in approved_slice_ids:
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
    print(
        f"Valid capability decision plans: {len(paths)}; scope={scope}; wave={ns.wave or 'all'}; "
        f"approval_required={ns.require_approved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
