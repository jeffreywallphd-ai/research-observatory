# Documentation guide

This file is the repository's high-level document router. It delegates detailed procedure; it does not duplicate every rule.

## Authority map

| Need | Read |
|---|---|
| Product purpose, users, workflows, principles, non-goals | `product/vision.md` |
| Architecture, services, data, deployment, security, platform model | Accepted `adr/` records, then `architecture/README.md` and `architecture/source/systems-design.md` |
| Source precedence, mismatch handling, document change control | `governance/repository-governance.md` |
| Capability campaign, verification, evidence, CI, and stop rules | `automation/project-automation-guide.md` |
| Coding-agent claims, task flow, and evidence | `automation/codex-tracking-guide.md` |
| Static decision-review behavior and feedback format | `automation/planning-review-site.md` |
| Current work identity and plan lifecycle | `../planning/README.md` |
| Approved visual/workflow reference | `../design/ui-reference/STYLE_GUIDE.md`, `WORKFLOW_CATALOG.md`, and `prototype-index.html` |
| Desktop implementation conformance and visual baselines | `automation/ui-conformance-verification.md` |

## Required reading by work type

### Ordinary implementation task

1. Root `AGENTS.md`.
2. `../planning/README.md` and the active capability/slice/task.
3. Accepted ADRs and affected architecture sections.
4. Affected UI/workflow contracts when user-facing.
5. The task-specific verification profile.

### Capability planning or approval

1. Root `AGENTS.md`.
2. `../planning/README.md`.
3. Complete capability packet and every contained slice plan.
4. `automation/planning-review-site.md`.
5. The generated capability review page.

### Architecture change

1. Vision and relevant workflows.
2. Accepted ADRs and Systems Design.
3. Affected capability/slice plans.
4. Repository governance mismatch protocol.
5. New or superseding ADR before implementation.

### Experience change

1. Vision and workflow catalog.
2. Approved UI reference and style guide.
3. Affected page/capability contracts.
4. Design-first procedure in the automation guide.
5. Approved new reference before product code.

## Document rules

- Do not use chat history as durable project memory.
- Do not copy work status into prose; the backlog remains authoritative.
- Do not use generated review HTML as a canonical plan; update Markdown and regenerate.
- Do not silently make a package/bootstrap guide into repository authority.
- Keep summaries brief and link to the canonical source.
- When a change affects several documents, update the highest-authority source first, then derived guidance and validators.
