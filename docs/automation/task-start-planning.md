# Task-start acceptance closure

This is a lightweight implementation-planning pass performed after `taskctl
claim` and before product code is changed. It closes the gap between an approved
task description and the exact behaviors, boundaries, fixtures, and tests that
will prove it. It is prospective guidance for newly claimed work.

It is not a new task state, controller, plan approval, human gate, or substitute
for commit-bound evidence and independent review. The approved Wave, capability,
slice, backlog task, accepted ADRs, and governed experience reference remain the
authority. If this pass reveals new consequential scope or an unmet mandatory
gate, use the existing stop/amendment/replanning path.

## Tailoring rule

Use the smallest form that exposes the task's credible risks. A low-risk local
change may need only a few bullets. A high-risk contract, migration, security,
evidence-control, or multi-layer experience change may need the full table.

- Include a row only when the task can plausibly affect it.
- Mark an ambiguous dimension `N/A` with one sentence; do not fill matrices for
  appearance.
- Reuse working notes or the evidence draft. Commit a separate worksheet only
  when it materially improves implementation or review.
- Do not replay full profiles or request approval merely because this pass
  exists.
- Time-box exploration once the material acceptance surface is closed. Adjacent
  improvements remain backlog candidates unless they expose a material safety
  or correctness defect.

When a worksheet should be retained and displayed with the generated planning
review surface, use the task-keyed path
`artifacts/evidence/<TASK-ID>.task-start.md`. The review-site generator discovers
that exact path from the authoritative backlog task identity, records its hash,
and displays it only on the matching task page. Worksheet absence is
non-blocking; ad hoc notes elsewhere are not implicitly assigned to a task.

## Step 1: Freeze the task authority

Record or link the task ID, claim base, objective, acceptance criteria,
dependencies, approved slice section, governing ADRs/contracts, applicable UI
reference, and explicit non-goals. Confirm the current implementation and exact
historical fixtures at the affected boundary. Do not reconstruct an
approximation when an authoritative predecessor fixture exists.

## Step 2: Build the acceptance-closure map

Use this compact structure. Combine rows when that makes the proof clearer.

| Dimension | Question | Planned proof |
|---|---|---|
| Criterion/outcome | What observable behavior closes each criterion, and what must remain unchanged? | Named behavioral test, contract check, or artifact. |
| State and invariant | Which legal transitions, atomic relationships, monotonic values, or fail-closed rules can break? | Transition table plus positive/negative test. |
| Identity and authority | Which IDs, revisions, hashes, actors, policy fields, source records, or ownership boundaries decide authority? | Exact field inventory and substitution/denial test. |
| Compatibility/predecessor | Which prior schema, database, project, packet, client, or artifact must still load or be rejected explicitly? | Exact historical fixture and expected bridge/rejection. |
| Failure/cancellation/recovery | What material interruption, retry, corruption, denial, or ambiguous result can occur? | Deterministic fault and canonical post-failure state. |
| Principal boundary | What real boundary must work without mocks: process, persistence, generated client, filesystem, platform, renderer/Core, import/export? | One focused vertical proof at the narrowest real boundary. |
| Governed experience | Which approved regions, actions, semantic states, focus/accessibility behavior, or disclosure text can change? | Reference mapping and focused conformance test. |
| Evidence truth | Which check actually establishes each claim, and what broader coverage is deferred? | Criterion-to-check map with bounded rationale. |

For schemas and stateful controls, prefer a small state-transition/invariant
table over narrative. For identity-sensitive work, enumerate authority-bearing
fields before implementation. For migration or compatibility work, use exact
predecessor bytes. For a cross-layer behavior, identify one real end-to-end
principal boundary instead of relying only on parallel unit doubles.

## Step 3: Convert material rows into tests

Before production code where practical:

1. add a failing behavioral test for each material new rule;
2. add characterization coverage for current behavior that must be preserved;
3. add at least one material failure, denial, retry, restart, or compatibility
   case when the task risk exposes it; and
4. select the narrowest real-boundary proof that can detect wiring or authority
   gaps hidden by mocks.

Tests should challenge the intended contract, not merely mirror the proposed
implementation. If a test cannot be written first, record why and name the
other deterministic proof that will close the row.

## Step 4: Optional read-only adversarial preflight

When an independent agent is available, request a short design preflight before
editing for work that touches migrations/destructive I/O, public or
cross-process contracts, authentication/security/evidence controls, or
multi-layer UI/export behavior. Give it the frozen task authority and
acceptance-closure map. Ask for missing invariants, identity substitutions,
historical fixtures, failure paths, and real-boundary proofs.

The preflight is advisory and read-only. It does not approve the task, create a
review round, or require human approval. Incorporate relevant gaps into the map
and tests. If it exposes a genuine authority conflict or mandatory stop
condition, follow the existing governance path.

## Step 5: Learn from the first adverse review

If independent review finds a blocking defect, add the missed acceptance row
before remediation. State the immediate root cause, add the smallest test that
would have detected it before implementation, and replay prior findings plus
the incremental risk boundary. The formal third-submission root-cause control
remains unchanged; this earlier learning step does not add a transition.

## Suggested working-note form

```text
Task / claim base:
Approved authority and non-goals:
Current implementation and exact predecessor fixtures:

Material acceptance rows:
- Criterion -> observable outcome -> proof
- Invariant/authority field -> substitution or failure -> proof
- Compatibility/recovery boundary -> exact fixture -> proof
- Real principal boundary -> focused vertical proof
- Governed experience state (or N/A with reason)

First tests before product code:
Deferred broader coverage and why:
Adversarial preflight: not indicated | requested | incorporated
Mandatory gate discovered: none | <gate and handoff>
```
