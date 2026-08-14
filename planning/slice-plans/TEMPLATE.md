---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-XX
capability_plan: planning/capability-plans/CAP-XX.md
planning_gate: capability-decision-complete
slice_id: CAP-XX.SYY
title: Replace with slice title
status: proposed
wave: W?
priority: P?
deployment_profiles: []
platform_targets: []
task_ids: []
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---

## Version 1.3.4 — completed recommendation defaults and full CAP-01 through CAP-19 planning

Every authored capability packet now preselects its researched best-in-class recommendation for every material decision and classifies it by binding Wave. These selections are treated as **completed decisions** by automation. The static planning site is a confirmation-and-override surface for the complete pre-Wave approval gate, not a mandatory decision-selection step. A non-recommended override requires rationale. Once the exact Wave-binding decisions and Wave slice plans are approved, execution proceeds continuously slice by slice and pauses only under the classified infeasibility/external-dependency/design-gate rules.

All slices in `CAP-01` through `CAP-19` have individual implementation plans. If a future slice plan is missing, `planctl wave prepare` creates the governed template, but the planning agent must research candidates, replace placeholders, preselect the strongest recommendation, classify every decision, and pass decision-complete validation before requesting pre-Wave approval.
# CAP-XX.SYY — Slice title

> **Static review page.** This slice is rendered under `planning/review-site/CAP-XX/`; begin at the capability page so all cross-slice decisions are resolved once before implementation.


> **Implementation gate.** Before implementation, the capability decision packet must be decision-complete, its decisions must be Wave-classified, this plan and every peer plan in the active Wave must be approved at the same immutable commit, required ADRs/reference changes must be approved, and `python tools/planctl.py wave ready WN --require-approved` must pass. The planning agent must create this plan from the canonical template if it is missing.

<div class="visual-flow"><span>Decide capability</span><b>→</b><span>Approve slice plan</span><b>→</b><span>Execute tasks</span><b>→</b><span>Integrate and review</span></div>

## 0. Plan control

Replace with the required slice-specific implementation contract.
## 1. Purpose and contribution to the larger vision

Replace with the required slice-specific implementation contract.
## 2. Scope

Replace with the required slice-specific implementation contract.
## 3. Authority, dependencies, and campaign stop conditions

Replace with the required slice-specific implementation contract.
## 4. Selected implementation decisions

Replace with the required slice-specific implementation contract.
## 5. Architecture and implementation design

Replace with the required slice-specific implementation contract.
## 6. User experience and approved reference

Replace with the required slice-specific implementation contract.
## 7. Security, privacy, rights and research integrity

Replace with the required slice-specific implementation contract.
## 8. Failure, cancellation, restart and recovery

Replace with the required slice-specific implementation contract.
## 9. Task-by-task implementation plan

Replace with the required implementation detail. For Section 9, include every authoritative backlog task with objective, dependencies, ordered implementation, acceptance criteria, evidence and review.
## 10. Slice-wide verification matrix

Replace with the required slice-specific implementation contract.
## 11. Performance and resource budgets

Replace with the required slice-specific implementation contract.
## 12. Observability and provenance

Replace with the required slice-specific implementation contract.
## 13. Adjacent-slice handoffs

Replace with the required slice-specific implementation contract.
## 14. Migration and backward compatibility

Replace with the required slice-specific implementation contract.
## 15. Required slice evidence bundle

Replace with the required slice-specific implementation contract.
## 16. Definition of Ready

Replace with the required slice-specific implementation contract.
## 17. Definition of Done

Replace with the required slice-specific implementation contract.
## 18. Risks and mitigations

Replace with the required slice-specific implementation contract.
## 19. Required ADRs and human decisions

Replace with the required slice-specific implementation contract.
## 20. Research and standards basis

Replace with the required slice-specific implementation contract.
## 21. AI implementation runbook

Replace with the required slice-specific implementation contract.
