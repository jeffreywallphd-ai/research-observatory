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
