# Design-first UI change gating

`tools/ui_change_gate.py` is the pull-request and foundation guard for researcher-facing implementation. It compares an immutable Git base and head, rather than trusting the working tree, and activates when renderer files under the governed UI roots in `ui-change-policy.json` change.

Every activated change must add exactly one contract at `artifacts/evidence/ui-change/<task-id>.json`. The contract must match `design/ui-change.schema.json`, list the exact changed implementation files, cite the exact approved reference ID/version/package SHA-256 and approval commit, identify the claimed task owner, and match the task's `experience_change` field in `planning/backlog.yaml`. The task must be active and its full `base_sha` must equal the validated range base. Governed implementation entries must be regular Git blobs; symlinks, gitlinks, trees, and other redirected object types fail closed.

## Change kinds

- `intentional-design-change` changes a normative route, navigation, token, workflow, required region, interaction, accessibility behavior, or theme behavior. The base and head reference IDs must differ. The new `APPROVAL.yaml` must declare `approval_kind: human`, use an `approved_by: human:<identity>` distinct from the implementation agent, supersede the base reference, and be committed after the change base but strictly before every implementation commit. The task requires `human-and-agent-review`.
- `approved-reference-implementation` creates implementation that conforms to the unchanged approved reference, including first implementation of an already approved page or workflow. It cites focused conformance evidence and does not alter the reference.
- `defect-restoration` returns drifted code to the unchanged approved reference. It records the defect, expected approved behavior, and focused passing restoration evidence; no new design approval is needed. Until CAP-00.S06.T04 installs a governed implementation-conformance verifier, the task must retain `human-and-agent-review` so a self-asserted restoration cannot classify arbitrary new behavior as a defect fix.

Changing both the approved reference and implementation in one commit is rejected because approval must be a distinct earlier commit. An implementation agent cannot self-approve by changing identity labels: intentional approval must use a human identity, differ from `implementationAgent`, match the approval record, and remain protected by the repository's human review gate.

## Commands

For a task branch, validate the whole task/PR range:

```powershell
.venv\Scripts\python.exe tools\ui_change_gate.py --repo . --base <task-base-sha> --head HEAD
```

The foundation profile uses `UI_CHANGE_BASE_SHA` when CI supplies the pull-request or push base. A manual dispatch requires an explicit immutable base SHA. Locally, the gate uses the sole active task's governed `base_sha` when that task carries `experience_change`, fails on ambiguous or invalid active-task state, and falls back to `HEAD^` only when no UI task is active. CI performs a full-history checkout so commit ordering and ancestry are verifiable. The pull-request template records the same lineage for reviewers, but prose or a checked box cannot replace the committed contract.

The gate fails for a missing, extra, malformed, renamed, or stale contract; incomplete changed-file coverage; unknown or mismatched task metadata; forged reference hashes; a nonhuman or self approval; same-commit approval and implementation; intentional implementation without a newer approved reference; or restoration/conformance work that also modifies the reference.

## Resumed amendment restoration (opt-in 1.1)

An immutable amendment task may resume after one separately approved, executed,
independently qualified and ADOPTED immediate paused-parent correction. It must
not rewrite its original `base_sha` or add fields forbidden by its approved task
schema. For this case only, a `schemaVersion: "1.1"` defect-restoration contract
adds `amendmentAuthority`: the correction ID, exact adoption and explicit parent
reactivation commits, separately attributed inherited/resumed UI file inventories,
and a committed independent restoration-classification reference. Top-level
`changedFiles` still covers the entire original-base range. A path may belong to
both segments; the full inventory is not the resumed three-file-style subset.

This lane authenticates the existing approval introductions, reviewed immutable
packets/task definitions, exact paused parent, actual adoption checkpoint and
independent task/exit ledgers. Every inherited UI-changing commit must occur in
one reviewed correction submission range, after reference publication. The new
reference must equal its reviewed proposal except enumerated publication metadata;
the superseded reference is checked at its original Git snapshot. Return preserves
the exact paused parent, and explicit activation preserves the original task base.
Ordinary Wave work and release gates stay unchanged. Nested/competing corrections,
unattributed edits, hidden add/revert paths, renames/type changes and merge ambiguity
are not supported. Existing narrow authority helpers read clean current authority,
so this opt-in contract requires `--head HEAD`; v1.0 historical validation is unchanged.

The independent `independent-ui-restoration-disposition` record binds the task/base,
immutable task-definition hash, classified producer commit, complete resumed UI
commit/path lists, current reference package, paired product/reference capture
manifest and independent visual disposition. It explicitly states whether the
approved task allows the restoration and explains the normative basis; an agent's
self-labelled fix or self-hashed manifest does not grant this judgment. A later UI
or reference edit, even if reverted, requires fresh classification. Later control-only
commits may retain it. Full capture validity and every task criterion remain the
formal evidence/review responsibility; this record is not task approval.

Only this authenticated lane substitutes approved amendment/conformance authority
for the impossible amendment `experience_change`/`review_gate` fields. All ordinary
v1.0 denials remain in force. Gate/schema/quality changes still require the existing
exact control-only independent maintenance attestation, including late maintenance;
there is no blanket exemption. The maintenance envelope includes this canonical
contract document. Active tasks in an adopted correction's returned parent select
their original base even before a UI contract exists, never an evidence-only
`HEAD^` fallback. Git-bound approval records and the repository review process are
the authority boundary, not cryptographic authentication of a person's identity.

Strictly additive Python inventory is distinct from changing gate behavior. A
single-parent commit may add canonical, newly introduced regular Python files
under `services/`, `tests/` or `tools/` to `quality-scope.json`, before or after UI
implementation. Existing entries retain their order; metadata and governed roots
remain unchanged. The commit may not also change UI implementation or any other
UI gate control. Every commit is checked, including intermediate changes later
reverted. Missing, pre-existing or redirected sources, removal/reordering, and
all other quality-scope changes still require the existing independent control
maintenance process. This does not alter task or reference authority.

For an opt-in resumed amendment, authenticate its adopted correction before
classifying inherited control changes. An exact control-changing commit inside
one completed, independently reviewed correction submission is inherited work,
not self-modification by the resumed task. Its entire changed-path inventory
must be covered by that reviewed range. The range comes from authenticated
approval/submission/review/adoption records, never caller-supplied contract data.
Unknown, overlapping, extra-path, merge and later unreviewed changes remain denied;
the original task base and full per-commit traversal do not change.

Earlier bounded maintenance can use its existing
`bounded-governance-maintenance-independent-review` carrier instead of a newer
GOV-MAINT projection. Recognition authenticates its sole-parent candidate,
evidence-only and review-only deliveries, immutable full source hashes/blobs,
independent accepted disposition with no findings, and control-only scope before
the authenticated correction task start. It does not create a retrospective
approval or authorize product/launcher changes. Subsequent control modifications
still need their own exact review. The complete public UI gate must pass; these
individual provenance checks are not task completion evidence on their own.
