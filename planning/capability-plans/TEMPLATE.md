---
plan_schema_version: "1.1"
document_type: capability-decision-plan
baseline: "1.3"
supplemental_release: "1.3.4"
planning_policy_version: "initiation-assessment-1.0"
initiation_assessment:
  policy_version: "1.0"
  assessed_at: "YYYY-MM-DDTHH:MM:SSZ"
  scope_reference: "full Git commit or sha256:<digest> of the pre-assessment scope"
  estimation_unit: "one consistent effort unit"
  planned_items:
    - work_id: "CAP-XX.SYY.TZZ"
      effort: 10
  pre_assessment_planned_effort: 10
  refactoring_items: []
  cumulative_capability_refactoring_effort: 0
  capability_refactoring_share: 0
  budget_statement: "R <= 0.15 * P"
  major_refactor_disposition: "None identified"
  wave_refreshes:
    - wave: "W?"
      assessed_at: "YYYY-MM-DDTHH:MM:SSZ"
      scope_reference: "full Git commit or sha256:<digest> of the Wave pre-assessment scope"
      planned_items:
        - work_id: "CAP-XX.SYY.TZZ"
          effort: 10
      pre_assessment_planned_effort: 10
      refactoring_item_ids: []
      refactoring_effort: 0
      refactoring_share: 0
      cumulative_capability_refactoring_effort: 0
      budget_statement: "R <= 0.15 * P"
      reestimate_rationale: "None; estimates match the capability baseline"
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

## Version 1.3.4 — governed pre-research template and completed authored defaults

Every authored capability packet now preselects its researched best-in-class recommendation for every material decision. These selections are treated as **completed decisions** by automation, but each decision must also be classified by its binding Wave before that Wave can be approved. The static planning site is a confirmation-and-override surface for the complete pre-Wave gate, not a mandatory decision-selection step. A non-recommended override requires rationale. Once the exact Wave-binding decisions and Wave slice plans are approved, execution proceeds continuously slice by slice and pauses only under the classified infeasibility/external-dependency/design-gate rules.

All slices in `CAP-01` through `CAP-19` have individual implementation plans. If a future slice plan is missing, `planctl wave prepare` creates the governed template, but the planning agent must research candidates, replace placeholders, preselect the strongest recommendation, classify every decision, and pass decision-complete validation before requesting pre-Wave approval.
# CAP-XX — Capability decision and execution plan

> **Template state.** This blank template intentionally starts pending because its candidates are placeholders. It must not be treated as a completed capability packet. The planning agent researches all slices, replaces every placeholder with credible candidates and an explicit best-in-class recommendation, and runs `python tools/planctl.py --repo . adopt-recommendations CAP-XX`. That command records each researched recommendation as the selected accepted default, clears blockers, and makes the authored packet decision-complete. All shipped CAP-01 through CAP-19 packets are already in that completed-decision state; implementation approval remains separate.

> **Static review page.** Generate with `python tools/planctl.py --repo . review CAP-XX`. The researched recommendation for every decision must already be selected, accepted, and classified by binding Wave. Reviewers confirm those defaults or override a selection with rationale, inspect every linked slice page, and then approve the complete active Wave packet. A feedback export is needed only when recording overrides or notes.


> **Wave-scoped planning gate.** Inspect the complete capability and resolve capability-wide material decisions once. Classify each decision by the Wave where it becomes binding. Create every missing slice plan, but approve only the decisions and ordered slices in the Wave being activated. Inherited and future decisions remain visible as nonbinding context until their own Wave approval.

> **Initiation assessment.** While this plan is proposed, compare the tested
> current implementation with the Vision, accepted architecture, current
> best-practice sources, and the proposed outcome. Record a capability baseline
> and each applicable Wave refresh in Section 0A. Identify assessment-added
> technical-debt refactoring and prove that it is no more than 15% of the
> pre-assessment planned implementation effort at both capability and Wave scope.
> Route major refactoring outside initiation planning. Approval freezes the
> adapted plan; this requirement does not reopen an earlier approved Wave.

<div class="visual-flow"><span>Inventory every slice</span><b>→</b><span>Compare and classify decisions</span><b>→</b><span>Confirm Wave-binding decisions</span><b>→</b><span>Approve the complete Wave</span><b>→</b><span>Execute the Wave continuously</span></div>

## 0. Control and authority
## 0A. Initiation assessment and planning adaptation

Record the tested implementation baseline, Vision/architecture/best-practice
fit, plan adaptations, and necessary support improvements. The front matter
binds the pre-assessment scope reference, common estimation unit, itemized
planned-work denominator, itemized refactoring allocations, explicit
`R <= 0.15 * P` calculation, and major-refactor disposition. Refactoring
allocations are cumulative across Wave refreshes; a later refresh cannot reset
the capability numerator. Each Wave refresh identifies exactly the allocations
introduced there, and the Wave validator deduplicates them across capabilities.
Any post-baseline estimate change requires reconciliation and rationale.

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

Every capability-wide decision section must be complete. Wave approval mode requires `decision_completion: complete`, an empty `open_blocking_decisions`, every decision classified by `binding_waves`, every binding decision `status: accepted` with a selected option, every active-Wave slice plan approved at the same immutable commit, required ADR/UI-reference approvals complete, and exact Wave approval inventory metadata.
