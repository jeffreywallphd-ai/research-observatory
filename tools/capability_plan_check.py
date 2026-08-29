#!/usr/bin/env python3
"""Validate capability decision plans and wave-scoped slice approval gates."""

from __future__ import annotations

import argparse
import json
import math
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
INITIATION_POLICY = "initiation-assessment-1.0"
BUDGET_STATEMENT = "R <= 0.15 * P"
SCOPE_REFERENCE_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")


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


def _effort(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _same_number(actual: Any, expected: float) -> bool:
    value = _nonnegative(actual)
    return value is not None and math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-9)


def _required_text(record: dict[str, Any], field: str, label: str, errors: list[str]) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: {field} is required")
        return ""
    return value.strip()


def _planned_items(
    value: Any, *, valid_work_ids: set[str], label: str, errors: list[str]
) -> tuple[dict[str, float], float]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: planned_items must be a non-empty list")
        return {}, 0.0
    items: dict[str, float] = {}
    for index, item in enumerate(value):
        item_label = f"{label}.planned_items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label}: expected an object")
            continue
        work_id = item.get("work_id")
        effort = _effort(item.get("effort"))
        if not isinstance(work_id, str) or work_id not in valid_work_ids:
            errors.append(f"{item_label}: work_id must name a task or slice in this capability")
            continue
        if work_id in items:
            errors.append(f"{item_label}: duplicate work_id {work_id}")
        if effort is None:
            errors.append(f"{item_label}: effort must be a finite positive number")
            continue
        items[work_id] = effort
    return items, sum(items.values())


def initiation_assessment_errors(
    meta: dict[str, Any], body: str, capability: dict[str, Any], wave_id: str
) -> list[str]:
    """Validate the prospective assessment embedded in an existing Wave packet."""

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
    _required_text(assessment, "assessed_at", f"{capability_id}.initiation_assessment", errors)
    scope_reference = _required_text(assessment, "scope_reference", f"{capability_id}.initiation_assessment", errors)
    if scope_reference and not SCOPE_REFERENCE_PATTERN.fullmatch(scope_reference):
        errors.append(f"{capability_id}: initiation_assessment.scope_reference must be a full commit or sha256 digest")
    _required_text(assessment, "estimation_unit", f"{capability_id}.initiation_assessment", errors)

    valid_work_ids = {
        str(work.get("id"))
        for slice_ in capability.get("slices", [])
        for work in [slice_, *slice_.get("tasks", [])]
        if work.get("id")
    }
    baseline_items, baseline_effort = _planned_items(
        assessment.get("planned_items"),
        valid_work_ids=valid_work_ids,
        label=f"{capability_id}.initiation_assessment",
        errors=errors,
    )
    if not _same_number(assessment.get("pre_assessment_planned_effort"), baseline_effort):
        errors.append(
            f"{capability_id}: pre_assessment_planned_effort must equal the itemized capability "
            f"baseline {baseline_effort:g}"
        )

    refactoring_value = assessment.get("refactoring_items")
    if not isinstance(refactoring_value, list):
        errors.append(f"{capability_id}: refactoring_items must be a list")
        refactoring_value = []
    refactoring: dict[str, dict[str, Any]] = {}
    included_effort = 0.0
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
        if not isinstance(work_id, str) or work_id not in valid_work_ids:
            errors.append(f"{label}: work_id must name a task or slice in this capability")
        if effort is None:
            errors.append(f"{label}: effort must be a finite positive number")
        if introduced_wave not in capability_waves:
            errors.append(f"{label}: introduced_in_wave must be a capability Wave")
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

    if not _same_number(assessment.get("cumulative_capability_refactoring_effort"), included_effort):
        errors.append(
            f"{capability_id}: cumulative_capability_refactoring_effort must equal included "
            f"allocations {included_effort:g}"
        )
    capability_share = included_effort / baseline_effort if baseline_effort else math.inf
    if not _same_number(assessment.get("capability_refactoring_share"), capability_share):
        errors.append(f"{capability_id}: capability_refactoring_share must equal {capability_share:g}")
    if included_effort > 0.15 * baseline_effort + 1e-9:
        errors.append(
            f"{capability_id}: capability refactoring budget exceeds 15% "
            f"({included_effort:g} > 0.15 * {baseline_effort:g})"
        )
    if assessment.get("budget_statement") != BUDGET_STATEMENT:
        errors.append(f"{capability_id}: budget_statement must be {BUDGET_STATEMENT}")
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
        refresh_scope = _required_text(refresh, "scope_reference", label, errors)
        if refresh_scope and not SCOPE_REFERENCE_PATTERN.fullmatch(refresh_scope):
            errors.append(f"{label}: scope_reference must be a full commit or sha256 digest")
        wave_work_ids = {
            str(work.get("id"))
            for slice_ in capability.get("slices", [])
            if slice_.get("wave") == refresh_wave
            for work in [slice_, *slice_.get("tasks", [])]
            if work.get("id")
        }
        wave_items, wave_effort = _planned_items(
            refresh.get("planned_items"), valid_work_ids=wave_work_ids, label=label, errors=errors
        )
        if not _same_number(refresh.get("pre_assessment_planned_effort"), wave_effort):
            errors.append(f"{label}: pre_assessment_planned_effort must equal itemized Wave effort {wave_effort:g}")
        refactoring_ids = refresh.get("refactoring_item_ids")
        if not isinstance(refactoring_ids, list) or len(refactoring_ids) != len(set(refactoring_ids)):
            errors.append(f"{label}: refactoring_item_ids must be a unique list")
            refactoring_ids = []
        expected_ids = {
            allocation_id
            for allocation_id, item in refactoring.items()
            if item.get("introduced_in_wave") == refresh_wave and item.get("disposition") == "included"
        }
        if set(refactoring_ids) != expected_ids:
            errors.append(
                f"{label}: refactoring_item_ids must exactly identify included allocations {sorted(expected_ids)}"
            )
        wave_refactoring_effort = sum(
            _effort(refactoring[allocation_id].get("effort")) or 0.0
            for allocation_id in set(refactoring_ids)
            if allocation_id in refactoring and refactoring[allocation_id].get("disposition") == "included"
        )
        if not _same_number(refresh.get("refactoring_effort"), wave_refactoring_effort):
            errors.append(f"{label}: refactoring_effort must equal {wave_refactoring_effort:g}")
        wave_share = wave_refactoring_effort / wave_effort if wave_effort else math.inf
        if not _same_number(refresh.get("refactoring_share"), wave_share):
            errors.append(f"{label}: refactoring_share must equal {wave_share:g}")
        if wave_refactoring_effort > 0.15 * wave_effort + 1e-9:
            errors.append(
                f"{label}: refactoring budget exceeds 15% ({wave_refactoring_effort:g} > 0.15 * {wave_effort:g})"
            )
        cumulative = sum(
            _effort(item.get("effort")) or 0.0
            for item in refactoring.values()
            if item.get("disposition") == "included"
            and (wave_number(str(item.get("introduced_in_wave"))) or 99) <= number
        )
        if not _same_number(refresh.get("cumulative_capability_refactoring_effort"), cumulative):
            errors.append(f"{label}: cumulative_capability_refactoring_effort must equal {cumulative:g}")
        if refresh.get("budget_statement") != BUDGET_STATEMENT:
            errors.append(f"{label}: budget_statement must be {BUDGET_STATEMENT}")
        rationale = _required_text(refresh, "reestimate_rationale", label, errors)
        reestimated = any(
            work_id in baseline_items and not math.isclose(effort, baseline_items[work_id])
            for work_id, effort in wave_items.items()
        )
        if reestimated and rationale.lower().startswith(("none", "not applicable", "n/a")):
            errors.append(f"{label}: reestimate_rationale must reconcile changed estimates")
        _required_text(refresh, "major_refactor_disposition", label, errors)
    if refresh_numbers != sorted(refresh_numbers):
        errors.append(f"{capability_id}: wave_refreshes must be in Wave order")
    if wave_id not in refresh_by_wave:
        errors.append(f"{capability_id}: missing initiation assessment refresh for {wave_id}")
    return errors


def wave_initiation_rollup_errors(entries: list[tuple[str, dict[str, Any]]], wave_id: str) -> list[str]:
    """Recompute the deduplicated cross-capability Wave refactoring budget."""

    if not wave_requires_initiation_assessment(wave_id):
        return []
    errors: list[str] = []
    planned_ids: set[str] = set()
    allocation_ids: set[str] = set()
    planned_effort = 0.0
    refactoring_effort = 0.0
    for _capability_id, meta in entries:
        assessment = meta.get("initiation_assessment")
        if not isinstance(assessment, dict):
            continue
        refresh = next(
            (
                item
                for item in assessment.get("wave_refreshes", [])
                if isinstance(item, dict) and item.get("wave") == wave_id
            ),
            None,
        )
        if not isinstance(refresh, dict):
            continue
        for item in refresh.get("planned_items", []):
            if not isinstance(item, dict) or not isinstance(item.get("work_id"), str):
                continue
            work_id = str(item["work_id"])
            if work_id in planned_ids:
                errors.append(f"{wave_id}: planned work {work_id} is counted by more than one capability")
                continue
            planned_ids.add(work_id)
            planned_effort += _effort(item.get("effort")) or 0.0
        refactoring = {
            item.get("id"): item
            for item in assessment.get("refactoring_items", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for allocation_id in refresh.get("refactoring_item_ids", []):
            if not isinstance(allocation_id, str) or allocation_id not in refactoring:
                continue
            if allocation_id in allocation_ids:
                errors.append(f"{wave_id}: refactoring allocation {allocation_id} is counted more than once")
                continue
            allocation_ids.add(allocation_id)
            refactoring_effort += _effort(refactoring[allocation_id].get("effort")) or 0.0
    if not planned_effort:
        errors.append(f"{wave_id}: initiation assessment Wave roll-up has no planned effort")
    elif refactoring_effort > 0.15 * planned_effort + 1e-9:
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
