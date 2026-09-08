# Linked UI correction compatibility repair

Predecessor: `6fbb0eae475f95902216ba93ad4b782e93c84e68`.
Risk tier: 2 (evidence/control authority). W1 is quiescent and PAUSED;
W1.C03.T01 is not yet claimed. No product edits are authorized by this note.

## Mismatch and bounded remedy

The linked correction procedure authorizes restoration of an approved completed
task, but the UI gate cannot represent that procedure: correction tasks are not
discovered, their IDs are rejected, their full base is missed, immutable tasks
lack the gate's legacy metadata fields, and submission rejects the required
task-owned UI contract path. The first affected restoration is CAP-03.S06.T03,
whose native reproduction is retained as CAP-07.S01.NATIVE-F01.

Repair only `tools/ui_change_gate.py`, `design/ui-change.schema.json`,
`tools/taskctl.py`, their existing `tests/foundation/test_ui_change_gate.py` and
`tests/foundation/test_taskctl_workflow.py`, and
`docs/automation/design-first-ui-changes.md`. This note is the delivery record.
Use the existing defect-restoration contract and authenticated correction
origin/spec/history/Wave authority. Select the real full active correction base;
enforce current branch, owner, worktree and unexpired lease; preserve exact
approved reference lineage and admitted UI scope, including intermediate commits.
Admit only the canonical UI evidence path owned by that correction.

Do not change `corrective_contract`, backlog/spec schemas, frozen tasks or
approvals, original evidence/adverse history, product/reference behavior, human
release authority, security policy, migration guarantees or check thresholds.
No new controller, amendment, approval layer or optional refactoring is included.
Ordinary and amendment UI denials remain in force. Current independent task
review and focused conformance still decide whether a proposed restoration is
faithful to its approved contract; a receipt or C-ID is not authority by itself.

## Verification and completion

Before product work: regression-first real-Git tests for a valid correction and
full-base selection; missing/forged origin, spec, history, identity, lease,
reference and evidence; foreign/extra/renamed/reverted UI paths; and ambiguous
active work. Replay existing UI-gate and linked-correction tests, schema,
affected quality and backlog validation. Commit the control-only candidate and
verify stable inputs; preserve failures and obtain independent control review
before local integration or W1.C03.T01 claim. Broader product/native/full Wave
qualification remains fresh and separate. Recovery is a reviewed forward fix,
never deletion of earlier evidence or bypass of the failing gate.

Independent preflight: `agent:/root/cap07_slice_review` confirmed this route and
the explicit lease-expiration and intermediate-path checks. Implementation:
`agent:/root/quality_control_review`; main owns publication and no self-approval.
