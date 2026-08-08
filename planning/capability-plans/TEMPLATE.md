---
plan_schema_version: "1.1"
document_type: capability-decision-plan
baseline: "1.3"
supplemental_release: "1.3.4"
capability_id: "CAP-XX"
title: "Replace with capability title"
status: proposed
execution_mode: long-running-capability-campaign
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


> **One-time capability planning gate.** Inspect every slice and task before implementation. Create every missing slice plan from the governed template. Present credible candidates and a recommendation for each material choice, adopt every researched recommendation as the completed selected default, resolve any ADR or experience-reference changes, approve every slice plan and this packet at an immutable commit, and only then start the long-running capability campaign.

<div class="visual-flow"><span>Inventory every slice</span><b>→</b><span>Compare candidates</span><b>→</b><span>Accept decisions</span><b>→</b><span>Approve all plans</span><b>→</b><span>Execute continuously</span></div>

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

Every section must be complete. Approval mode requires `status: approved`, `decision_completion: complete`, an empty `open_blocking_decisions`, every decision `status: accepted` with a selected option from its candidates, every slice plan approved, required ADR/UI-reference approvals complete, and immutable approval metadata.
