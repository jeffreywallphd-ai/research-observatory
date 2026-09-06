# Repository document and architecture governance

## Purpose

Define which repository artifact controls each decision, how inconsistencies are handled, and how planning, architecture, experience, and implementation remain complementary.

## Source precedence

1. Tested code, schemas, migrations, and executable behavior establish current behavior.
2. Accepted ADRs govern their explicit decisions.
3. Systems Design governs remaining architecture.
4. Vision governs product purpose, workflows, principles, and non-goals.
5. Backlog governs work identity, dependency, wave, gate, and state.
6. Approved capability and slice plans govern planned implementation.
7. Approved UI reference governs user-facing experience contracts.
8. Repository automation documents govern AI operating procedure.

Current behavior does not silently redefine intended architecture. If code and authority differ, record the mismatch and either restore the implementation or approve the authoritative change.

During proposed Wave and capability planning, tested code supplies the current
implementation baseline but does not receive a preference merely because it
already exists. Within accepted architecture, product Vision and current
best-practice evidence guide plan adaptation. Major changes to accepted
architecture still require the normal mismatch and ADR route.

## Repository entry points

- `AGENTS.md` - concise AI operating rules.
- `docs/README.md` - document routing.
- `planning/README.md` - planning lifecycle and delegation.

These are the repository entry authorities, not an unconditional reading list.
Read AGENTS.md first; use docs/README.md to locate an unknown authority and
planning/README.md before selecting or changing planned work. Follow their
section-level triggers; do not recursively read every linked document. External
setup guides cannot replace repository authority.

## Change routing

| Change | Update first | Then |
|---|---|---|
| Product purpose/workflow/non-goal | Vision | Architecture/plans/UI reference as affected |
| Architecture decision | ADR or Systems Design | Plans, tests, operational docs |
| Work decomposition or sequencing | Backlog | Capability/slice plans and generated views |
| Proposed Wave/capability initiation adaptation | Capability and slice plans | Wave review packet before approval |
| Material implementation decision | Capability/slice plan and required ADR | Review site, approval, implementation |
| Intentional UI/UX change | Governed UI reference | Plans, implementation, conformance evidence |
| Current behavior correction | Code/tests | Evidence and affected documentation |
| Automation/evidence-control defect preserving approved authority | Bounded maintenance increment under GOV-MIG-0001 | Risk-selected checks and independent control review; no new GRR/GCR |
| Defect restoring already approved product behavior | Original task authority and bounded correction | Focused regression and integration evidence, independent disposition; no new product approval |

The GRR/GCR descriptions retained in older documents are historical validation
instructions, not a route for new work. The current maintenance rule in
`../automation/governance-automation-simplification.md` supersedes that route.
Changes to approved scope, security authority, migration guarantees, governed
references or release criteria require append-only amendment and explicit human
approval, including reductions or replacements. Destructive/irreversible
actions, external effects, substantial spend and release decisions also require
human authority. Existing approval must actually cover the action; routine
restoration or maintenance preserving that authority needs no new product gate.

## Mismatch protocol

1. Stop only if the mismatch is material to the active work.
2. Identify the highest-authority conflicting artifacts.
3. Record the mismatch, affected scope, and safe interim state.
4. Present alternatives and a recommendation when a decision is needed.
5. Update and approve the authoritative artifact before dependent implementation.
6. Regenerate derived pages and rerun validators.
7. Preserve the prior version and rationale.

## Package separation

The repository may have been created from an external setup pack. Package-level `START_HERE`, manifests, and installation scripts are not repository authorities unless explicitly archived. Repository operation must remain complete when the package is absent.
