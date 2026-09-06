---
plan_schema_version: "1.1"
document_type: capability-decision-plan
baseline: "1.3"
supplemental_release: "1.3.4"
planning_policy_version: "initiation-assessment-2.0"
initiation_assessment:
  policy_version: "2.0"
  assessed_at: "YYYY-MM-DDTHH:MM:SSZ"
  estimation_unit: "one consistent effort unit"
  implementation_baseline: "Tested strengths, weaknesses, debt, and reusable boundaries"
  vision_architecture_best_practice_fit: "Whether the proposed outcome and plan remain the best fit"
  planned_items:
    - work_id: "CAP-XX.SYY.TZZ"
      effort: 10
  refactoring_items: [] # each allocation names one task; slice IDs are not effort units
  major_refactor_disposition: "None identified"
  wave_refreshes:
    - wave: "W?"
      assessed_at: "YYYY-MM-DDTHH:MM:SSZ"
      material_changes: "What changed since the capability assessment, or None"
      plan_adaptations: "How the proposed plan changed, or None"
      support_improvements: "Bounded implementation improvements added, or None"
      major_refactor_disposition: "None identified"
capability_id: "CAP-XX"
title: "Replace with capability title"
status: proposed
execution_mode: wave-scoped-capability-increments
decision_completion: pending
open_blocking_decisions:
  - CAP-XX-D01
slice_ids: []
decisions:
  - id: CAP-XX-D01
    title: "Replace with material capability decision"
    candidates:
      - "Recommended candidate"
      - "Credible alternative"
    recommendation: "Recommended candidate"
    recommendation_basis: "Compare functionality, security, privacy and rights, portability, maintainability, licensing, resource use, recovery, evaluation quality, and downstream compatibility."
    selected_option: null
    status: recommended
    required_adr: null
    # Add binding_waves only after classifying the decision, for example: [W1]
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---

# CAP-XX — Capability decision and execution plan

> **Template state.** Pending placeholders do not authorize implementation. Research and select credible recommendations for upcoming-Wave binding decisions; retain distant decisions as provisional. Do not run whole-capability recommendation adoption merely to clear future placeholders. Resolve all current blockers before requesting complete Wave approval.

> **Static review page.** Generate with `python tools/planctl.py --repo . wave review WN`. Reviewers confirm the upcoming Wave's selected binding decisions, inspect its contributing slices, and record overrides with rationale. Future context may remain unresolved. Feedback records changes, not execution approval.


> **Wave-scoped planning gate.** Inspect the capability outcome and dependencies. Resolve decisions and missing slice plans binding in the upcoming Wave; future decisions and slice designs may remain provisional. Classify decisions by their binding Wave. Approval covers only the complete upcoming Wave; inherited and future context is not new authority.

> **Initiation assessment.** While this plan is proposed, compare the tested
> current implementation with the Vision, accepted architecture, current
> best-practice sources, and the proposed outcome. Record a capability baseline
> and each applicable Wave refresh in Section 0A. Unapproved planning has no
> 15% cap; major redesign is allowed through required architecture and approval
> routes. Freeze the selected implementation estimate with the Wave. Later
> supplemental refactoring shares its locked-Wave 15% budget, including changes
> to past-Wave software. Future contributions remain provisional, not prematurely
> decision-complete. This requirement does not reopen an earlier approved Wave.

<div class="visual-flow"><span>Inventory every slice</span><b>→</b><span>Compare and classify decisions</span><b>→</b><span>Confirm Wave-binding decisions</span><b>→</b><span>Approve the complete Wave</span><b>→</b><span>Execute the Wave continuously</span></div>

## 0. Control and authority
## 0A. Initiation assessment and planning adaptation

Record the tested implementation baseline, Vision/architecture/best-practice
fit, plan adaptations, and necessary support improvements. The front matter
records one common estimation unit, the complete final upcoming-Wave atomic-task
estimate, planned refactoring allocations, and major-redesign authority or
disposition. Validation checks identities, coverage, units and duplicate
allocations, not an initiation percentage cap. Independent review checks
architecture and planning judgment. Approval freezes the selected scope and
estimate; use [execution accounting](../README.md#locked-wave-refactoring-budget)
for subsequent supplemental refactoring. Distant Wave details remain forecasts.

## 1. Capability outcome and production-ready exit
## 2. Slice map and end-to-end dependency logic
## 3. Decision-making protocol
## 4. Decision register
## 5. Cross-slice architecture contract
## 6. Experience and workflow contract
## 7. Security, privacy, rights and research-integrity decisions
## 8. Capability-wide verification strategy
## 9. Long-running execution contract
## 10. Plan and approval checklist
## 11. Research and technical basis
## 12. Approval record

For the upcoming Wave, every binding decision must be accepted with a selected
option, its blocker IDs resolved, each contributing slice plan approved at the
same immutable commit, required ADR/reference approvals complete, and the Wave
inventory exact. Decisions carry their `binding_waves` classification. Global
`decision_completion` and blockers may remain pending for future decisions.
Do not change inherited approved decision bytes to clear a planning checklist.
