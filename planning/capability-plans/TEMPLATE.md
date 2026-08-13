---
plan_schema_version: "1.1"
document_type: capability-decision-plan
baseline: "1.3"
supplemental_release: "1.3.4"
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
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---

## Version 1.3.4 — governed pre-research template and completed authored defaults

Every authored capability packet now preselects its researched best-in-class recommendation for every material decision. These selections are treated as **completed decisions** by automation. The static planning site is a confirmation-and-override surface plus the single capability approval gate, not a mandatory decision-selection step. A non-recommended override requires rationale. Once capability and slice plans are approved, execution proceeds continuously slice by slice and pauses only under the classified infeasibility/external-dependency/design-gate rules.

All slices in `CAP-01` through `CAP-19` have individual implementation plans. If a future slice plan is missing, `planctl prepare` creates the governed template, but the planning agent must research candidates, replace placeholders, preselect the strongest recommendation, and pass decision-complete validation before requesting capability approval.
# CAP-XX — Capability decision and execution plan

> **Template state.** This blank template intentionally starts pending because its candidates are placeholders. It must not be treated as a completed capability packet. The planning agent researches all slices, replaces every placeholder with credible candidates and an explicit best-in-class recommendation, and runs `python tools/planctl.py --repo . adopt-recommendations CAP-XX`. That command records each researched recommendation as the selected accepted default, clears blockers, and makes the authored packet decision-complete. All shipped CAP-01 through CAP-19 packets are already in that completed-decision state; implementation approval remains separate.

> **Static review page.** Generate with `python tools/planctl.py --repo . review CAP-XX`. The researched recommendation for every decision must already be selected and accepted. Reviewers confirm those defaults or override a selection with rationale, inspect every linked slice page, and then use the single capability approval gate. A feedback export is needed only when recording overrides or notes.


> **Progressive capability planning gate.** Inspect the complete capability and resolve capability-wide material decisions once. Create every missing slice plan, but require detailed approval only for the ordered slices in the wave being activated. Future-wave plans remain visible for dependency analysis and may remain proposed until their gate. Start only the approved capability-wave increment.

<div class="visual-flow"><span>Inventory every slice</span><b>→</b><span>Compare candidates</span><b>→</b><span>Accept capability decisions</span><b>→</b><span>Approve active-wave plans</span><b>→</b><span>Execute the increment continuously</span></div>

## 0. Control and authority
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

Every capability-wide decision section must be complete. Approval mode requires `status: approved`, `decision_completion: complete`, an empty `open_blocking_decisions`, every decision `status: accepted` with a selected option, every active-wave slice plan approved, required ADR/UI-reference approvals complete, and immutable approval metadata.
