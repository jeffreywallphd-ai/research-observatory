# Documentation guide

AGENTS.md is the operating entry point. Use this router only when locating an
authority or when a task triggers a row below. Read the applicable section and
its stated prerequisites completely; do not read all linked documents.
An unchanged section already available in context need not be re-read.
Expand reading when scope changes, a material contradiction appears, or the
current evidence cannot answer the task.

## Authority and reading routes

| Trigger or question | Read |
|---|---|
| Product purpose, users, workflows, or non-goals are being planned or changed | Relevant sections of [Vision](product/vision.md). |
| Implementation touches an architectural boundary | Applicable accepted [ADRs](adr/) and affected [Systems Design](architecture/source/systems-design.md) sections; use the [architecture map](architecture/README.md) if ownership is unclear. |
| A material source conflict or document-authority change is found | [Repository governance](governance/repository-governance.md); apply its mismatch protocol before dependent changes. |
| Meaning/origin of Waves, gates, capabilities, slices, or approval scope is unclear | Relevant [delivery-control model](governance/delivery-control-model.md) sections. Historical sections are not current command recipes. |
| Selecting/changing planned work or preparing a Wave | [Planning entry/lifecycle](../planning/README.md#default-planning-and-execution-lifecycle); follow its conditional section map. |
| Claiming/resuming/submitting/reviewing a task | Matching [task-operation](automation/codex-tracking-guide.md) section; current backlog task and approved capability/slice scope. |
| A task has just been claimed, or a finding exposes a missed risk | [Task-start planning](automation/task-start-planning.md); only the dimensions the change can affect. |
| Correcting completed work, repairing controls, selecting/repeating checks, or considering evidence reuse | Matching section in the [efficiency reading map](automation/workflow-efficiency.md#reading-map). |
| Closing a slice/checkpoint/Wave, choosing verification breadth, or integrating main | Matching [automation-guide](automation/project-automation-guide.md) section. |
| Making a decision/approval request or stopping at a gate | [Decision-complete handoff](automation/project-automation-guide.md#31-decision-complete-stopped-gate-handoff). Read [review-site instructions](automation/planning-review-site.md) only for the operation involved: navigation, feedback, approval, or generation. |
| Restoring or changing user-facing behavior | Affected approved [style](../design/ui-reference/STYLE_GUIDE.md), [workflow](../design/ui-reference/WORKFLOW_CATALOG.md), page contracts and linked HTML. For intentional change, also read [design-first governance](automation/project-automation-guide.md#6-design-first-experience-reference-governance); for implementation proof, [UI conformance](automation/ui-conformance-verification.md). |
| Modifying a governance adapter/kernel or interpreting its historical evidence | Relevant [migration-design](automation/governance-automation-simplification.md) sections after its status paragraph; no live authority from a design or shadow receipt. |

Read-only questions do not trigger task claims, Wave preparation, document
generation, or edits. A user-facing change does not require reading unrelated
reference pages. New Wave planning does require every contribution binding in
that Wave, not only the first capability.

## Document rules

- Use the backlog for live identity/state; do not maintain competing prose status.
- Preserve durable decisions in canonical records, not chat history alone.
- Update the highest-authority affected source first, then derived guidance and
  validators. Generated review HTML is not a canonical plan.
- Keep one detailed procedure per subject; use conditional links elsewhere.
- Repository instructions remain authoritative without an external setup pack.
