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

## Repository entry points

- `AGENTS.md` - concise AI operating rules.
- `docs/README.md` - document routing.
- `planning/README.md` - planning lifecycle and delegation.

These files are mandatory and may not be replaced by external setup guides.

## Change routing

| Change | Update first | Then |
|---|---|---|
| Product purpose/workflow/non-goal | Vision | Architecture/plans/UI reference as affected |
| Architecture decision | ADR or Systems Design | Plans, tests, operational docs |
| Work decomposition or sequencing | Backlog | Capability/slice plans and generated views |
| Material implementation decision | Capability/slice plan and required ADR | Review site, approval, implementation |
| Intentional UI/UX change | Governed UI reference | Plans, implementation, conformance evidence |
| Current behavior correction | Code/tests | Evidence and affected documentation |

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
